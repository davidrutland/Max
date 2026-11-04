"""Authenticated, streamed incoming binary uploads. Never parse uploaded content."""
import os
import secrets
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import auth, models
from app.database import get_db

router = APIRouter(prefix="/api/uploads", tags=["uploads"])
ROOT = Path(os.environ.get("INCOMING_UPLOAD_PATH", "/data/incoming_uploads"))


def max_bytes():
    value = int(os.environ.get("MAX_FILE_UPLOAD_MIB", "1024"))
    if value < 1:
        raise ValueError("MAX_FILE_UPLOAD_MIB must be positive")
    return value * 1024 * 1024


@router.post("")
async def upload(file: UploadFile = File(...), user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    from app.upload_lifecycle import reclaim
    reclaim(db, ROOT, user.id, stale_only=True)
    identifier = secrets.token_hex(24)
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=ROOT)
    size = 0
    try:
        with os.fdopen(fd, "wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes():
                    raise HTTPException(413, "File exceeds configured upload limit")
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, ROOT / identifier)
        name = Path((file.filename or "upload").replace("\\", "/")).name[:255] or "upload"
        record = models.IncomingUpload(id=identifier, user_id=user.id, filename=name, size=size,
                                       mime_type=(file.content_type or "application/octet-stream")[:255])
        db.add(record)
        db.commit()
        return {"id": identifier, "name": name, "size": size}
    except BaseException:
        db.rollback()
        (ROOT / identifier).unlink(missing_ok=True)
        raise
    finally:
        Path(temporary).unlink(missing_ok=True)
        await file.close()


@router.get("/{identifier}/download")
def download(identifier: str, user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    record = db.query(models.IncomingUpload).filter_by(id=identifier, user_id=user.id).first()
    if not record:
        raise HTTPException(404, "Upload not found")
    path = ROOT / record.id
    if not path.is_file() or path.is_symlink():
        raise HTTPException(404, "Upload unavailable")
    return FileResponse(path, filename=record.filename, media_type="application/octet-stream",
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


@router.delete("/{identifier}", status_code=204)
def delete_unused(identifier: str, user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    record = db.query(models.IncomingUpload).filter_by(id=identifier, user_id=user.id).first()
    if record is None:
        raise HTTPException(404, "Upload not found")
    from app.upload_lifecycle import referenced_ids
    if identifier in referenced_ids(db, user.id):
        raise HTTPException(409, "Upload is attached to a chat message")
    (ROOT / identifier).unlink(missing_ok=True)
    db.delete(record)
    db.commit()
