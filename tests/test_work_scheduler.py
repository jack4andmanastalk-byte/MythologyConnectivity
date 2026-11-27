"""Race and lifecycle tests for the local parallel-work scheduler."""
from __future__ import annotations

import json
import multiprocessing
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import work_scheduler as scheduler  # noqa: E402


SAMPLE_CATALOG = {
    "schema": "arena.work-queue/1",
    "scheduler": {"default_lease_seconds": 600},
    "tasks": [
        {"id": "BASE", "title": "base task", "priority": 1, "depends_on": [], "requires_paths": []},
        {"id": "FOLLOWUP", "title": "dependent task", "priority": 2,
         "depends_on": ["BASE"], "requires_paths": []},
        {"id": "WITH-FILE", "title": "requires an input", "priority": 3,
         "depends_on": [], "requires_paths": ["inputs/source.txt"]},
    ],
}


def _competing_claim(state_path: str, worker: str, queue: multiprocessing.Queue) -> None:
    try:
        result = scheduler.claim_task(SAMPLE_CATALOG, Path(state_path), worker, "BASE", lease_seconds=600)
        queue.put(("ok", worker, result["claim_token"]))
    except scheduler.SchedulerError as exc:
        queue.put(("error", worker, str(exc)))


class WorkSchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state = self.root / ".work_scheduler" / "claims.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_two_processes_cannot_claim_the_same_task(self) -> None:
        queue: multiprocessing.Queue = multiprocessing.Queue()
        processes = [
            multiprocessing.Process(target=_competing_claim, args=(str(self.state), worker, queue))
            for worker in ("chat-one", "chat-two")
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(10)
            self.assertEqual(process.exitcode, 0)
        outcomes = [queue.get(timeout=2) for _ in processes]
        self.assertEqual(sum(result[0] == "ok" for result in outcomes), 1)
        self.assertEqual(sum(result[0] == "error" for result in outcomes), 1)
        winner = next(result for result in outcomes if result[0] == "ok")
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(state["tasks"]["BASE"]["worker"], winner[1])
        self.assertNotIn(winner[2], self.state.read_text(encoding="utf-8"))

    def test_claim_token_controls_heartbeat_completion_and_release(self) -> None:
        claim = scheduler.claim_task(SAMPLE_CATALOG, self.state, "chat-a", "BASE", lease_seconds=600)
        with self.assertRaises(scheduler.SchedulerError):
            scheduler.complete_task(self.state, "BASE", "not-the-token")
        heartbeat = scheduler.heartbeat_task(self.state, "BASE", claim["claim_token"], lease_seconds=1200)
        self.assertEqual(heartbeat["status"], "claimed")
        released = scheduler.release_task(self.state, "BASE", claim["claim_token"], reason="handoff")
        self.assertEqual(released["status"], "open")
        claim2 = scheduler.claim_task(SAMPLE_CATALOG, self.state, "chat-b", "BASE", lease_seconds=600)
        done = scheduler.complete_task(self.state, "BASE", claim2["claim_token"], reason="done")
        self.assertEqual(done["status"], "completed")
        with self.assertRaises(scheduler.SchedulerError):
            scheduler.claim_task(SAMPLE_CATALOG, self.state, "chat-c", "BASE")

    def test_dependencies_and_required_paths_gate_claims(self) -> None:
        with self.assertRaisesRegex(scheduler.SchedulerError, "dependency BASE"):
            scheduler.claim_task(SAMPLE_CATALOG, self.state, "chat-a", "FOLLOWUP")
        with self.assertRaisesRegex(scheduler.SchedulerError, "required path is missing"):
            scheduler.claim_task(SAMPLE_CATALOG, self.state, "chat-a", "WITH-FILE", root=self.root)
        self.assertFalse(scheduler.status_report(SAMPLE_CATALOG, self.state, self.root)["tasks"][2]["ready"])

        parent = scheduler.claim_task(SAMPLE_CATALOG, self.state, "chat-a", "BASE")
        scheduler.complete_task(self.state, "BASE", parent["claim_token"])
        child = scheduler.claim_task(SAMPLE_CATALOG, self.state, "chat-a", "FOLLOWUP")
        self.assertEqual(child["task_id"], "FOLLOWUP")

        required = self.root / "inputs/source.txt"
        required.parent.mkdir(parents=True)
        required.write_text("source", encoding="utf-8")
        file_task = scheduler.claim_task(SAMPLE_CATALOG, self.state, "chat-b", "WITH-FILE", root=self.root)
        self.assertEqual(file_task["task_id"], "WITH-FILE")

    def test_expired_lease_reopens_task_for_another_chat(self) -> None:
        original = scheduler.claim_task(SAMPLE_CATALOG, self.state, "chat-a", "BASE", lease_seconds=600)
        with scheduler.locked_state(self.state) as state:
            state["tasks"]["BASE"]["lease_expires_epoch"] = 0
        replacement = scheduler.claim_task(SAMPLE_CATALOG, self.state, "chat-b", "BASE", lease_seconds=600)
        self.assertNotEqual(original["claim_token"], replacement["claim_token"])
        report = scheduler.status_report(SAMPLE_CATALOG, self.state)
        base = next(row for row in report["tasks"] if row["id"] == "BASE")
        self.assertEqual(base["worker"], "chat-b")

    def test_catalog_dependency_cycle_is_rejected(self) -> None:
        catalog = dict(SAMPLE_CATALOG)
        catalog["tasks"] = [
            {"id": "A", "title": "A", "depends_on": ["B"]},
            {"id": "B", "title": "B", "depends_on": ["A"]},
        ]
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as stream:
            json.dump(catalog, stream)
            path = Path(stream.name)
        try:
            with self.assertRaisesRegex(scheduler.SchedulerError, "dependency cycle"):
                scheduler.load_catalog(path)
        finally:
            path.unlink()

    def test_catalog_changes_cannot_reuse_old_state_silently(self) -> None:
        scheduler.claim_task(SAMPLE_CATALOG, self.state, "chat-a", "BASE")
        changed = json.loads(json.dumps(SAMPLE_CATALOG))
        changed["tasks"][0]["title"] = "changed definition"
        with self.assertRaisesRegex(scheduler.SchedulerError, "differs from the catalog"):
            scheduler.claim_next(changed, self.state, "chat-b")

    def test_required_path_cannot_escape_repository(self) -> None:
        task = {"id": "ESCAPE", "title": "escape", "requires_paths": ["../outside"]}
        state = {"tasks": {}}
        self.assertIn("required path escapes repository root", scheduler._task_blockers(task, state, self.root)[0])

    def test_repository_queue_loads_and_claim_next_uses_priority(self) -> None:
        catalog = scheduler.load_catalog(scheduler.DEFAULT_CATALOG)
        claim = scheduler.claim_next(catalog, self.state, "chat-priority", root=ROOT)
        self.assertEqual(claim["task_id"], "V17-SOURCE-RECOVERY")
        self.assertTrue(claim["claim_token"])


if __name__ == "__main__":
    unittest.main()
