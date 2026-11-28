# -*- coding: utf-8 -*-
"""
analysis_io.py -- 解析パイプラインの出力先解決・原子的書き込み・排他ロックを 1 か所に集める。

背景（`docs/path_connectivity_validity_review_20261128_ja.md` §11・§13）:
  これまで `outputs/` は全モジュールが `ROOT / "outputs"` を直書きし、`write_text` /
  `to_csv` で上書きしていた。`write_text` は原子的ではないため、書き込み中の
  ファイルを読むと必ず壊れた中間状態が読める（実測: 読み手の 6810 回が
  JSONDecodeError、CSV は 958 回エラー）。並列に走らせると `manifest.sha256` だけが
  別時点を指すこともある。

  ここでは 3 つだけを提供する。数値・判定規則は持たない。

  1. `output_dir()`       -- 出力先を設定と環境変数から解決する（ワーカーごとに分けられる）
  2. `*_atomic()`         -- tempfile + os.replace による原子的書き込み
  3. `directory_lock()`   -- 同一出力先への二重起動を「黙って上書き」せず失敗させる

出力先の解決順（上が優先）:
  1. 環境変数 `ANALYSIS_OUTPUT_DIR`（`make OUTDIR=runs/w1` が設定する）
  2. `config/analysis.json` の `outputs.dir`（既定 `outputs`）
  どちらもリポジトリルートからの相対パスとして解決する。
"""
from __future__ import annotations

import contextlib
import errno
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config/analysis.json"
ENV_VAR = "ANALYSIS_OUTPUT_DIR"

# 設定が読めない場面（テスト・初期化前）でも壊れないようにする既定値
_DEFAULT_DIR = "outputs"
_DEFAULT_LOCK = ".lock"


def _config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8")).get("outputs", {})
    except (OSError, json.JSONDecodeError):
        return {}


def output_dir(create: bool = True) -> Path:
    """出力ディレクトリを解決して返す。`create=True` なら作る。"""
    raw = os.environ.get(ENV_VAR) or _config().get("dir") or _DEFAULT_DIR
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def lock_path(out: Path | None = None) -> Path:
    out = out or output_dir()
    return out / _config().get("lock", _DEFAULT_LOCK)


# --------------------------------------------------------------- atomic writes
def _atomic_bytes(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_name)
        raise
    return path


def write_text_atomic(path: Path, text: str, encoding: str = "utf-8") -> Path:
    return _atomic_bytes(Path(path), text.encode(encoding))


def write_json_atomic(path: Path, payload: Any, indent: int = 2, newline: bool = True) -> Path:
    text = json.dumps(payload, ensure_ascii=False, indent=indent)
    return write_text_atomic(Path(path), text + ("\n" if newline else ""))


def write_dataframe_atomic(frame, path: Path, **kwargs) -> Path:
    """pandas の DataFrame を原子的に CSV 化する。pandas は呼び出し側で用意する。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            frame.to_csv(stream, **kwargs)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_name)
        raise
    return path


# ---------------------------------------------------------------------- locking
class OutputLocked(RuntimeError):
    """同一出力ディレクトリを別プロセスが使用中。"""


@contextlib.contextmanager
def directory_lock(out: Path | None = None, wait: float = 0.0, poll: float = 0.1) -> Iterator[Path]:
    """出力ディレクトリの排他ロックを取る。

    `wait=0`（既定）では取れなければ即座に `OutputLocked` を送出する。
    黙って上書きするより、失敗して「別のワーカーが書いている」と伝える方が安全である。
    ロックはプロセス終了で OS が解放する（`flock`）。
    """
    out = out or output_dir()
    out.mkdir(parents=True, exist_ok=True)
    target = lock_path(out)
    handle = open(target, "a+b")
    try:
        try:
            _try_lock(handle)
        except OSError as exc:
            if exc.errno not in (errno.EACCES, errno.EAGAIN):
                raise
            if wait <= 0:
                raise OutputLocked(
                    f"{target} は別のプロセスが使用中である。"
                    f"別ワーカーで走っていないなら {target} を確認するか、"
                    f"出力先を分ける（ANALYSIS_OUTPUT_DIR / make OUTDIR=...）。"
                ) from exc
            deadline = time.monotonic() + wait
            while True:
                if time.monotonic() >= deadline:
                    raise OutputLocked(f"{target} のロックを {wait} 秒待っても取れなかった") from exc
                time.sleep(poll)
                try:
                    _try_lock(handle)
                    break
                except OSError as inner:
                    if inner.errno not in (errno.EACCES, errno.EAGAIN):
                        raise
        try:
            yield target
        finally:
            with contextlib.suppress(OSError):
                _unlock(handle)
    finally:
        handle.close()


if os.name == "nt":  # pragma: no cover - CI は Linux
    import msvcrt

    def _try_lock(handle) -> None:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(handle) -> None:
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _try_lock(handle) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(handle) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
