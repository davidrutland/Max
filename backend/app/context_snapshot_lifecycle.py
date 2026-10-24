"""Commit a verified fork snapshot copy to SQLite.

No model operations, no implicit fork-point verification. Caller must serialize
this operation against saves/deletes and verify the exact message boundary.
"""
from pathlib import Path
import os
import stat

from sqlalchemy.orm import Session

from app.context_binding_repository import (
    BindingError, get_binding, confirm_fork_snapshot_copy,
)
from app.context_snapshot_files import SnapshotFileStore, SnapshotFileError


class SnapshotLifecycleError(RuntimeError):
    pass


def _valid_file(path: Path) -> bool:
    try:
        info = path.lstat()
        return stat.S_ISREG(info.st_mode) and info.st_size > 0
    except FileNotFoundError:
        return False


def inherit_fork_snapshot(db: Session, store: SnapshotFileStore,
                          source_chat_id: int, fork_chat_id: int, user_id: int,
                          *, fork_point_verified: bool) -> Path:
    """Copy then commit status. Requires exclusive control of these snapshots.

    Only invoke after caller has independently verified that the parent's saved
    snapshot is exactly at the fork point. This function cannot prove that.
    """
    if fork_point_verified is not True:
        raise SnapshotLifecycleError("Fork point not verified")
    source = get_binding(db, source_chat_id, user_id)
    fork = get_binding(db, fork_chat_id, user_id)
    if source is None or fork is None or source_chat_id == fork_chat_id:
        raise SnapshotLifecycleError("Missing or identical bindings")
    if source.snapshot_status != "ready" or fork.snapshot_status != "absent":
        raise SnapshotLifecycleError("Source must be ready and fork absent")
    if not source.snapshot_path or not fork.snapshot_path or source.snapshot_path == fork.snapshot_path:
        raise SnapshotLifecycleError("Independent snapshot filenames required")
    from app.context_binding_repository import COMPATIBILITY_FIELDS
    if any(getattr(source, k) != getattr(fork, k) for k in COMPATIBILITY_FIELDS):
        raise SnapshotLifecycleError("Incompatible fork identity")
    src = store.directory / source.snapshot_path
    dst = store.directory / fork.snapshot_path
    if not _valid_file(src):
        raise SnapshotLifecycleError("Source snapshot missing or empty")
    copied = False
    try:
        store.copy_for_fork(source.snapshot_path, fork.snapshot_path,
                            fork_point_verified=True)
        copied = True
        if not _valid_file(dst) or dst.stat().st_size != src.stat().st_size:
            raise SnapshotLifecycleError("Copied snapshot failed size verification")
        confirm_fork_snapshot_copy(db, source_chat_id, fork_chat_id, user_id,
                                   fork_point_verified=True)
        db.commit()
        return dst
    except Exception:
        db.rollback()
        if copied:
            # Best effort cleanup. Never touch the parent's file.
            try:
                dst.unlink()
            except FileNotFoundError:
                pass
        raise
