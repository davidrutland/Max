"""Authenticated access to immutable, message-owned artifacts."""
from pathlib import Path, PurePosixPath
from io import BytesIO
from zipfile import ZipFile, BadZipFile
from datetime import datetime, timedelta, timezone
import jwt
from app.config import SECRET_KEY
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth, models, artifact_store
from app.database import get_db

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


def owned_artifact(db: Session, identifier: str, user: models.User) -> models.Artifact:
    artifact = db.scalar(
        select(models.Artifact)
        .join(models.ArtifactReference, models.ArtifactReference.artifact_id == models.Artifact.id)
        .join(models.Message, models.Message.id == models.ArtifactReference.message_id)
        .join(models.Chat, models.Chat.id == models.Message.chat_id)
        .where(models.Artifact.id == identifier, models.Chat.user_id == user.id)
        .limit(1)
    )
    if artifact is None:
        raise HTTPException(404, "Attachment not found")
    return artifact


@router.get("/{identifier}/download")
def download(identifier: str, user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    artifact = owned_artifact(db, identifier, user)
    try:
        path = artifact_store.resolve(identifier)
    except ValueError:
        raise HTTPException(404, "Attachment not found")
    if not path.is_file() or path.is_symlink():
        raise HTTPException(404, "Attachment data unavailable")
    return FileResponse(
        path, media_type="application/octet-stream", filename=Path(artifact.filename).name,
        content_disposition_type="attachment",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"},
    )


@router.post("/{identifier}/preview-ticket")
def preview_ticket(identifier: str, user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    artifact = owned_artifact(db, identifier, user)
    if Path(artifact.filename).suffix.lower() not in {".html", ".htm", ".zip"}:
        raise HTTPException(415, "Interactive preview not supported")
    token = jwt.encode({"purpose": "artifact-preview", "artifact": identifier,
                        "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
                       SECRET_KEY, algorithm="HS256")
    return {"ticket": token}


MAX_ZIP_ENTRIES = 256
MAX_ZIP_TOTAL = 32 * 1024 * 1024
MAX_ZIP_ENTRY = 8 * 1024 * 1024
ZIP_TYPES = {".html": "text/html", ".htm": "text/html", ".js": "text/javascript",
             ".mjs": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
             ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
             ".gif": "image/gif", ".webp": "image/webp", ".woff": "font/woff",
             ".woff2": "font/woff2", ".json": "application/json", ".txt": "text/plain"}


def zip_asset(blob: bytes, requested: str):
    """Return a bounded, allowlisted ZIP asset; never extract onto the filesystem."""
    if not requested or requested.startswith("/") or "\\" in requested or "\x00" in requested:
        raise ValueError("Invalid ZIP path")
    parts = PurePosixPath(requested).parts
    if any(part in ("..", ".") for part in requested.split("/")) or not parts:
        raise ValueError("Invalid ZIP path")
    name = "/".join(parts)
    mime = ZIP_TYPES.get(PurePosixPath(name).suffix.lower())
    if not mime:
        raise ValueError("Unsupported asset type")
    try:
        with ZipFile(BytesIO(blob)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ZIP_ENTRIES or sum(x.file_size for x in entries) > MAX_ZIP_TOTAL:
                raise ValueError("ZIP exceeds preview limits")
            matches = [x for x in entries if x.filename == name and not x.is_dir()]
            if len(matches) != 1 or matches[0].file_size > MAX_ZIP_ENTRY:
                raise ValueError("Missing or oversized asset")
            entry = matches[0]
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Symlink forbidden")
            with archive.open(entry) as stream:
                content = stream.read(MAX_ZIP_ENTRY + 1)
            if len(content) != entry.file_size or len(content) > MAX_ZIP_ENTRY:
                raise ValueError("Invalid ZIP entry size")
            return content, mime
    except (BadZipFile, RuntimeError, OSError) as exc:
        raise ValueError("Invalid ZIP") from exc


@router.get("/isolated/{ticket}/{asset_path:path}")
@router.get("/isolated/{ticket}")
def isolated_preview(ticket: str, asset_path: str = "", db: Session = Depends(get_db)):
    # Exposed only through nginx /preview/; the CSP sandbox enforces an opaque origin.
    try:
        claims = jwt.decode(ticket, SECRET_KEY, algorithms=["HS256"])
        if claims.get("purpose") != "artifact-preview":
            raise ValueError("Wrong token purpose")
        identifier = claims["artifact"]
        artifact = db.get(models.Artifact, identifier)
        if artifact is None or Path(artifact.filename).suffix.lower() not in {".html", ".htm", ".zip"}:
            raise ValueError("Unsupported artifact")
        if not db.scalar(select(models.ArtifactReference).where(models.ArtifactReference.artifact_id == identifier).limit(1)):
            raise ValueError("No live references")
        path = artifact_store.resolve(identifier)
        if path.is_symlink() or not path.is_file():
            raise ValueError("Missing artifact")
        content = path.read_bytes()
        if Path(artifact.filename).suffix.lower() == ".zip":
            content, mime = zip_asset(content, asset_path or "index.html")
        else:
            if asset_path:
                raise ValueError("Single HTML artifact has no assets")
            mime = "text/html"
    except (jwt.PyJWTError, KeyError, ValueError, OSError):
        if not asset_path:
            return Response(
                content=(
                    '<!doctype html><html lang="en"><meta charset="utf-8">'
                    '<meta name="viewport" content="width=device-width, initial-scale=1">'
                    '<title>Preview unavailable</title>'
                    '<body style="background:#171717;color:#eee;font:16px system-ui;'
                    'padding:2rem;line-height:1.5">'
                    '<h2>Preview unavailable</h2>'
                    '<p>This file couldn\'t be displayed.</p>'
                    '<p>You can still download the original using the Download link above.</p>'
                    '</body></html>'
                ),
                status_code=404,
                media_type="text/html",
                headers={
                    "Content-Security-Policy": "sandbox allow-scripts; default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'self'",
                    "Cache-Control": "no-store",
                    "Referrer-Policy": "no-referrer",
                    "X-Content-Type-Options": "nosniff",
                },
            )
        raise HTTPException(404, "Preview unavailable")
    return Response(content, media_type=mime, headers={
        "Content-Security-Policy": "sandbox allow-scripts; default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; media-src 'self' blob:; connect-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none'; frame-ancestors 'self'",
        "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff", "Cross-Origin-Resource-Policy": "cross-origin",
    })
