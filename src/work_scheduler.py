#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local, file-backed work allocator for parallel Arena chats.

The lock and state file must be on the same shared filesystem for all workers.
This tool does not coordinate isolated clones or separate sandboxes.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import secrets
import stat
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "config/work_queue.json"
DEFAULT_STATE = ROOT / ".work_scheduler/work_scheduler_state.json"
STATE_SCHEMA = "arena.work-scheduler-state/1"


class SchedulerError(Exception):
    """A user-correctable scheduler error."""


def _now() -> float:
    return time.time()


def _iso(epoch: float | None = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_now() if epoch is None else epoch))


def _new_state() -> dict[str, Any]:
    return {"schema": STATE_SCHEMA, "updated_at": _iso(), "tasks": {}, "events": []}


def _catalog_digest(catalog: dict[str, Any]) -> str:
    canonical = json.dumps(catalog, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _bind_catalog(state: dict[str, Any], catalog: dict[str, Any]) -> str:
    digest = _catalog_digest(catalog)
    current = state.get("catalog_sha256")
    if current is not None and current != digest:
        raise SchedulerError(
            "work queue differs from the catalog already bound to this state file; "
            "use a matching checkout/state file or intentionally reset the local queue state"
        )
    state["catalog_sha256"] = digest
    return digest


def load_catalog(path: Path = DEFAULT_CATALOG) -> dict[str, Any]:
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SchedulerError(f"work queue not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SchedulerError(f"invalid work queue JSON in {path}: {exc}") from exc
    if not isinstance(catalog, dict) or catalog.get("schema") != "arena.work-queue/1":
        raise SchedulerError(f"unsupported work queue schema in {path}")
    scheduler_settings = catalog.get("scheduler")
    if not isinstance(scheduler_settings, dict):
        raise SchedulerError("work queue 'scheduler' settings are required")
    default_lease = scheduler_settings.get("default_lease_seconds")
    if not isinstance(default_lease, int) or isinstance(default_lease, bool) or default_lease <= 0:
        raise SchedulerError("scheduler.default_lease_seconds must be a positive integer")
    tasks = catalog.get("tasks")
    if not isinstance(tasks, list):
        raise SchedulerError("work queue 'tasks' must be a list")
    seen: set[str] = set()
    for task in tasks:
        if not isinstance(task, dict):
            raise SchedulerError("each work queue task must be an object")
        task_id = task.get("id")
        if not isinstance(task_id, str) or not task_id.strip():
            raise SchedulerError("each task needs a non-empty string id")
        if task_id in seen:
            raise SchedulerError(f"duplicate work queue task id: {task_id}")
        seen.add(task_id)
        if not isinstance(task.get("title"), str) or not task["title"].strip():
            raise SchedulerError(f"task {task_id}: missing title")
        if not isinstance(task.get("priority", 100), int) or isinstance(task.get("priority", 100), bool):
            raise SchedulerError(f"task {task_id}: priority must be an integer")
        dependencies = task.get("depends_on", [])
        if not isinstance(dependencies, list) or not all(isinstance(value, str) for value in dependencies):
            raise SchedulerError(f"task {task_id}: depends_on must be a list of task ids")
        required_paths = task.get("requires_paths", [])
        if not isinstance(required_paths, list) or not all(isinstance(value, str) for value in required_paths):
            raise SchedulerError(f"task {task_id}: requires_paths must be a list of relative paths")
        for relative in required_paths:
            path = Path(relative)
            if path.is_absolute() or ".." in path.parts:
                raise SchedulerError(f"task {task_id}: required path must stay inside the repository: {relative}")
        if "acceptance" in task and (not isinstance(task["acceptance"], list)
                                     or not all(isinstance(item, str) for item in task["acceptance"])):
            raise SchedulerError(f"task {task_id}: acceptance must be a list of strings")
        if "description" in task and not isinstance(task["description"], str):
            raise SchedulerError(f"task {task_id}: description must be a string")
    for task in tasks:
        for dependency in task.get("depends_on", []):
            if dependency not in seen:
                raise SchedulerError(f"task {task['id']}: unknown dependency {dependency}")
            if dependency == task["id"]:
                raise SchedulerError(f"task {task['id']}: task cannot depend on itself")

    # Reject indirect dependency cycles during startup, rather than leave the queue stuck.
    by_id = {task["id"]: task for task in tasks}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise SchedulerError(f"work queue dependency cycle includes {task_id}")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in by_id[task_id].get("depends_on", []):
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task in by_id:
        visit(task)
    return catalog


def _append_event(state: dict[str, Any], action: str, task_id: str, **fields: Any) -> None:
    event = {"at": _iso(), "action": action, "task_id": task_id}
    event.update(fields)
    state.setdefault("events", []).append(event)


def _expire_claims(state: dict[str, Any], now: float) -> None:
    for task_id, entry in state.setdefault("tasks", {}).items():
        if (entry.get("status") == "claimed"
                and float(entry.get("lease_expires_epoch", 0)) <= now):
            worker = entry.get("worker", "unknown")
            attempts = int(entry.get("attempts", 1))
            state["tasks"][task_id] = {"status": "open", "attempts": attempts}
            _append_event(state, "lease_expired", task_id, worker=worker)


def _state_context(path: Path) -> Iterator[dict[str, Any]]:
    """Acquire an inter-process exclusive lock and atomically persist mutations."""
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    private_mode = stat.S_IRUSR | stat.S_IWUSR
    lock_fd = os.open(lock_path, flags, private_mode)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        if path.exists():
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise SchedulerError(f"invalid scheduler state JSON in {path}: {exc}") from exc
            if not isinstance(state, dict) or state.get("schema") != STATE_SCHEMA:
                raise SchedulerError(f"unsupported scheduler state schema in {path}")
            if not isinstance(state.get("tasks"), dict) or not isinstance(state.get("events"), list):
                raise SchedulerError(f"malformed scheduler state in {path}")
        else:
            state = _new_state()

        try:
            yield state
        finally:
            state["updated_at"] = _iso()
            _atomic_write_json(path, state)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


@contextlib.contextmanager
def locked_state(path: Path) -> Iterator[dict[str, Any]]:
    yield from _state_context(path)


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_name, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(temp_name, path)
        dir_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_name)
        raise


def _entry(state: dict[str, Any], task_id: str) -> dict[str, Any]:
    return state.setdefault("tasks", {}).get(task_id, {"status": "open", "attempts": 0})


def _task_blockers(task: dict[str, Any], state: dict[str, Any], root: Path) -> list[str]:
    blockers = []
    for dependency in task.get("depends_on", []):
        if _entry(state, dependency).get("status") != "completed":
            blockers.append(f"dependency {dependency} is not completed")
    repository = root.resolve()
    for relative in task.get("requires_paths", []):
        required = (repository / relative).resolve()
        if not required.is_relative_to(repository):
            blockers.append(f"required path escapes repository root: {relative}")
        elif not required.exists():
            blockers.append(f"required path is missing: {relative}")
    return blockers


def _active_task_for_worker(state: dict[str, Any], worker: str) -> str | None:
    for task_id, entry in state.get("tasks", {}).items():
        if entry.get("status") == "claimed" and entry.get("worker") == worker:
            return task_id
    return None


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _resolve_lease_seconds(value: int | None, catalog: dict[str, Any] | None = None) -> int:
    if value is None:
        settings = catalog.get("scheduler") if isinstance(catalog, dict) else None
        if not isinstance(settings, dict):
            settings = load_catalog(DEFAULT_CATALOG).get("scheduler")
        value = settings.get("default_lease_seconds")
    _check_token("valid", value)
    return value


def _claim(task: dict[str, Any], state: dict[str, Any], worker: str, lease_seconds: int) -> dict[str, Any]:
    task_id = task["id"]
    attempts = int(_entry(state, task_id).get("attempts", 0)) + 1
    now = _now()
    token = secrets.token_urlsafe()
    entry = {
        "status": "claimed",
        "worker": worker,
        "token_sha256": _token_hash(token),
        "claimed_at": _iso(now),
        "lease_expires_epoch": now + lease_seconds,
        "attempts": attempts,
    }
    state["tasks"][task_id] = entry
    _append_event(state, "claimed", task_id, worker=worker, lease_expires_at=_iso(entry["lease_expires_epoch"]))
    return {
        "task_id": task_id,
        "title": task["title"],
        "description": task.get("description", ""),
        "acceptance": task.get("acceptance", []),
        "worker": worker,
        "claim_token": token,
        "claimed_at": entry["claimed_at"],
        "lease_expires_at": _iso(entry["lease_expires_epoch"]),
        "lease_seconds": lease_seconds,
    }


def claim_task(catalog: dict[str, Any], state_path: Path, worker: str, task_id: str,
               root: Path = ROOT, lease_seconds: int | None = None) -> dict[str, Any]:
    lease_seconds = _resolve_lease_seconds(lease_seconds, catalog)
    _check_worker(worker, lease_seconds)
    task = next((item for item in catalog["tasks"] if item["id"] == task_id), None)
    if task is None:
        raise SchedulerError(f"unknown task id: {task_id}")
    with locked_state(state_path) as state:
        _bind_catalog(state, catalog)
        now = _now()
        _expire_claims(state, now)
        active = _active_task_for_worker(state, worker)
        if active:
            raise SchedulerError(f"worker {worker!r} already holds {active}; complete or release it first")
        current = _entry(state, task_id)
        if current.get("status") == "completed":
            raise SchedulerError(f"task {task_id} is already completed")
        if current.get("status") == "claimed":
            raise SchedulerError(
                f"task {task_id} is claimed by {current.get('worker')} until "
                f"{_iso(float(current['lease_expires_epoch']))}"
            )
        blockers = _task_blockers(task, state, root)
        if blockers:
            raise SchedulerError(f"task {task_id} is not ready: " + "; ".join(blockers))
        return _claim(task, state, worker, lease_seconds)


def claim_next(catalog: dict[str, Any], state_path: Path, worker: str,
               root: Path = ROOT, lease_seconds: int | None = None) -> dict[str, Any]:
    lease_seconds = _resolve_lease_seconds(lease_seconds, catalog)
    _check_worker(worker, lease_seconds)
    with locked_state(state_path) as state:
        _bind_catalog(state, catalog)
        now = _now()
        _expire_claims(state, now)
        active = _active_task_for_worker(state, worker)
        if active:
            raise SchedulerError(f"worker {worker!r} already holds {active}; complete or release it first")
        ordered = sorted(enumerate(catalog["tasks"]), key=lambda pair: (pair[1].get("priority", 100), pair[0]))
        for _, task in ordered:
            current = _entry(state, task["id"])
            if current.get("status") != "open":
                continue
            if not _task_blockers(task, state, root):
                return _claim(task, state, worker, lease_seconds)
        pending = [task["id"] for task in catalog["tasks"] if _entry(state, task["id"]).get("status") != "completed"]
        raise SchedulerError("no ready task is available; pending tasks: " + (", ".join(pending) or "none"))


def heartbeat_task(state_path: Path, task_id: str, token: str, lease_seconds: int | None = None) -> dict[str, Any]:
    lease_seconds = _resolve_lease_seconds(lease_seconds)
    _check_token(token, lease_seconds)
    with locked_state(state_path) as state:
        now = _now()
        _expire_claims(state, now)
        entry = _authorized_claim(state, task_id, token)
        entry["lease_expires_epoch"] = now + lease_seconds
        entry["last_heartbeat_at"] = _iso(now)
        return {"task_id": task_id, "worker": entry["worker"], "status": "claimed",
                "lease_expires_at": _iso(entry["lease_expires_epoch"]), "lease_seconds": lease_seconds}


def complete_task(state_path: Path, task_id: str, token: str, reason: str = "") -> dict[str, Any]:
    _check_token(token)
    with locked_state(state_path) as state:
        _expire_claims(state, _now())
        entry = _authorized_claim(state, task_id, token)
        worker = entry["worker"]
        attempts = int(entry.get("attempts", 1))
        completed_at = _iso()
        state["tasks"][task_id] = {"status": "completed", "worker": worker,
                                   "completed_at": completed_at, "attempts": attempts}
        _append_event(state, "completed", task_id, worker=worker, reason=reason)
        return {"task_id": task_id, "status": "completed", "worker": worker, "completed_at": completed_at}


def release_task(state_path: Path, task_id: str, token: str, reason: str = "") -> dict[str, Any]:
    _check_token(token)
    with locked_state(state_path) as state:
        _expire_claims(state, _now())
        entry = _authorized_claim(state, task_id, token)
        worker = entry["worker"]
        attempts = int(entry.get("attempts", 1))
        state["tasks"][task_id] = {"status": "open", "attempts": attempts}
        _append_event(state, "released", task_id, worker=worker, reason=reason)
        return {"task_id": task_id, "status": "open", "released_by": worker}


def _authorized_claim(state: dict[str, Any], task_id: str, token: str) -> dict[str, Any]:
    entry = _entry(state, task_id)
    if entry.get("status") != "claimed":
        raise SchedulerError(f"task {task_id} is not currently claimed")
    if not secrets.compare_digest(str(entry.get("token_sha256", "")), _token_hash(token)):
        raise SchedulerError("claim token does not match; only the active claimant can change this task")
    return entry


def _check_worker(worker: str, lease_seconds: int) -> None:
    if not isinstance(worker, str) or not worker.strip() or len(worker) > 200:
        raise SchedulerError("worker must be a non-empty unique session/chat identifier (max 200 characters)")
    _check_token("valid", lease_seconds)


def _check_token(token: str, lease_seconds: int | None = None) -> None:
    if not isinstance(token, str) or not token.strip():
        raise SchedulerError("a claim token is required")
    if lease_seconds is not None and (not isinstance(lease_seconds, int)
                                      or isinstance(lease_seconds, bool) or lease_seconds <= 0):
        raise SchedulerError("lease seconds must be a positive integer")


def status_report(catalog: dict[str, Any], state_path: Path, root: Path = ROOT) -> dict[str, Any]:
    with locked_state(state_path) as state:
        catalog_hash = _bind_catalog(state, catalog)
        _expire_claims(state, _now())
        tasks_out = []
        for task in catalog["tasks"]:
            entry = _entry(state, task["id"])
            record = {"id": task["id"], "title": task["title"], "priority": task.get("priority", 100),
                      "status": entry.get("status", "open")}
            if entry.get("status") == "claimed":
                record.update(worker=entry.get("worker"), claimed_at=entry.get("claimed_at"),
                              lease_expires_at=_iso(float(entry["lease_expires_epoch"])))
            elif entry.get("status") == "completed":
                record.update(worker=entry.get("worker"), completed_at=entry.get("completed_at"))
            blockers = _task_blockers(task, state, root)
            record["ready"] = (record["status"] == "open" and not blockers)
            record["blockers"] = blockers
            tasks_out.append(record)
        return {"schema": catalog["schema"], "catalog_sha256": catalog_hash,
                "state_file": str(state_path), "tasks": tasks_out}


def _json_print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Atomic local scheduler for parallel work claims")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG, help="shared task catalog JSON")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE, help="shared claim state file")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root for required-path checks")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("worker-id", help="print a fresh unique worker/session identifier")
    commands.add_parser("status", help="show open, claimed, completed, and blocked tasks")
    claim_next_parser = commands.add_parser("claim-next", help="atomically claim the highest-priority ready task")
    claim_next_parser.add_argument("--worker", required=True, help="unique Arena chat/session identifier")
    claim_next_parser.add_argument("--lease-seconds", type=int, default=None)
    claim_parser = commands.add_parser("claim", help="atomically claim one named task")
    claim_parser.add_argument("task_id")
    claim_parser.add_argument("--worker", required=True)
    claim_parser.add_argument("--lease-seconds", type=int, default=None)
    for name, help_text in (("heartbeat", "renew an active claim"), ("complete", "mark an active claim complete"),
                            ("release", "release an active claim back to the queue")):
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("task_id")
        sub.add_argument("--token", required=True, help="secret token returned by claim/claim-next")
        if name == "heartbeat":
            sub.add_argument("--lease-seconds", type=int, default=None)
        else:
            sub.add_argument("--reason", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "worker-id":
            print("arena-" + secrets.token_hex(8))
            return 0
        catalog = load_catalog(args.catalog)
        if args.command == "status":
            _json_print(status_report(catalog, args.state, args.root))
        elif args.command == "claim-next":
            _json_print(claim_next(catalog, args.state, args.worker, args.root, args.lease_seconds))
        elif args.command == "claim":
            _json_print(claim_task(catalog, args.state, args.worker, args.task_id, args.root, args.lease_seconds))
        elif args.command == "heartbeat":
            lease_seconds = (args.lease_seconds if args.lease_seconds is not None
                             else catalog["scheduler"]["default_lease_seconds"])
            _json_print(heartbeat_task(args.state, args.task_id, args.token, lease_seconds))
        elif args.command == "complete":
            _json_print(complete_task(args.state, args.task_id, args.token, args.reason))
        elif args.command == "release":
            _json_print(release_task(args.state, args.task_id, args.token, args.reason))
        else:  # pragma: no cover - argparse enforces the command set.
            raise SchedulerError(f"unknown command: {args.command}")
        return 0
    except SchedulerError as exc:
        print(f"[scheduler] {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"[scheduler] filesystem/lock error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
