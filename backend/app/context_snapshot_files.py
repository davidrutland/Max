"""Independent snapshot copies; no database or inference operations.

Caller must verify checkpoint/message boundary and source readiness before copying.
A successful copy is NOT a database status update: caller commits that separately.
"""
import errno
import fcntl
import os
from pathlib import Path
import re
import shutil
import tempfile

FICLONE = 0x40049409
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,254}\Z")


class SnapshotFileError(RuntimeError):
    pass


def _name(value: str) -> str:
    if not isinstance(value, str) or not _NAME.fullmatch(value) or value in (".", ".."):
        raise SnapshotFileError("Snapshot must be a safe basename")
    return value


class SnapshotFileStore:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        if not self.directory.is_dir() or self.directory.is_symlink():
            raise SnapshotFileError("Snapshot directory must already exist and not be a symlink")

    def copy_for_fork(self, source: str, destination: str, *, fork_point_verified: bool) -> Path:
        """Create an independent destination, never overwrite an existing snapshot.

        The verified flag is a caller assertion, not proof of message alignment.
        """
        source = _name(source)
        destination = _name(destination)
        if source == destination:
            raise SnapshotFileError("Source and destination must differ")
        if fork_point_verified is not True:
            raise SnapshotFileError("Fork checkpoint boundary not verified")
        src = self.directory / source
        dst = self.directory / destination
        temp_name = None
        try:
            # O_NOFOLLOW prevents a malicious symlink source from being followed.
            fd = os.open(src, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(fd, "rb") as reader:
                import stat
                if not stat.S_ISREG(os.fstat(reader.fileno()).st_mode):
                    raise SnapshotFileError("Source is not a regular file")
                if dst.exists() or dst.is_symlink():
                    raise SnapshotFileError("Destination already exists")
                temp_fd, temp_name = tempfile.mkstemp(prefix=".fork-", suffix=".tmp", dir=self.directory)
                with os.fdopen(temp_fd, "wb") as writer:
                    try:
                        fcntl.ioctl(writer.fileno(), FICLONE, reader.fileno())
                    except OSError as exc:
                        if exc.errno not in (errno.EOPNOTSUPP, errno.ENOTTY, errno.EINVAL, errno.EXDEV, errno.ENOSYS):
                            raise
                        reader.seek(0)
                        writer.seek(0)
                        writer.truncate(0)
                        shutil.copyfileobj(reader, writer, length=1024 * 1024)
                    writer.flush()
                    os.fsync(writer.fileno())
            # Atomic no-clobber publish: hard-link a fully written temporary inode.
            os.link(temp_name, dst, follow_symlinks=False)
            os.unlink(temp_name)
            temp_name = None
            dir_fd = os.open(self.directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
            return dst
        except (OSError, SnapshotFileError) as exc:
            if isinstance(exc, SnapshotFileError):
                raise
            raise SnapshotFileError(f"Snapshot copy failed: {exc}") from exc
        finally:
            if temp_name is not None:
                try:
                    os.unlink(temp_name)
                except FileNotFoundError:
                    pass
