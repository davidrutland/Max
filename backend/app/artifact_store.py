"""Immutable published artifact blobs. No chat/tool ownership decisions belong here.

Callers must commit a database reference before exposing an artifact. Files without
references can be reclaimed by a later reconciliation pass.
"""
from pathlib import Path
import os
import secrets
import tempfile

ROOT = Path(os.environ.get('ARTIFACT_STORE_PATH', '/data/artifacts'))
MAX_BYTES = 100 * 1024 * 1024


def publish(data: bytes, *, root: Path = ROOT) -> str:
    """Atomically publish bytes under an opaque identifier; never trust filenames."""
    if len(data) > MAX_BYTES:
        raise ValueError('artifact exceeds 100 MiB')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    identifier = secrets.token_hex(24)
    fd, temporary = tempfile.mkstemp(prefix='.pending-', dir=root)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, root / identifier)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return identifier


def resolve(identifier: str, *, root: Path = ROOT) -> Path:
    if len(identifier) != 48 or any(c not in '0123456789abcdef' for c in identifier):
        raise ValueError('invalid artifact identifier')
    return root / identifier


def remove(identifier: str, *, root: Path = ROOT) -> None:
    resolve(identifier, root=root).unlink(missing_ok=True)


def reconcile(db, *, root: Path = ROOT):
    """Remove blobs absent from the database after interrupted publication.

    Run only during startup, before accepting concurrent chat writes.
    """
    from app import models
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    known = {identifier for (identifier,) in db.query(models.Artifact.id).all()}
    for path in root.iterdir():
        if not path.is_file() and not path.is_symlink():
            continue
        if path.name.startswith('.pending-') or (
            len(path.name) == 48 and all(c in '0123456789abcdef' for c in path.name)
            and path.name not in known
        ):
            path.unlink(missing_ok=True)
