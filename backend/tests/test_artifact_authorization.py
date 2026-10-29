"""Artifact authorization and ticket redemption, using the existing isolated test DB."""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy.orm import Session

from conftest import register
from app import models
from app.config import SECRET_KEY
from app.database import engine
from app.routers import artifacts


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def published(monkeypatch, tmp_path):
    identifier = "a" * 48
    file_path = tmp_path / identifier
    file_path.write_text("<h1>Private test artifact</h1>")
    original_resolve = artifacts.artifact_store.resolve

    def resolve(value):
        original_resolve(value)  # retain identifier validation
        return tmp_path / value

    monkeypatch.setattr(artifacts.artifact_store, "resolve", resolve)
    with Session(engine) as db:
        chat = models.Chat(user_id=1, title="Test")
        db.add(chat)
        db.flush()
        message = models.Message(chat_id=chat.id, role="assistant", content="attached")
        db.add(message)
        db.flush()
        db.add(models.Artifact(id=identifier, filename="private.html", mime_type="text/html", size=file_path.stat().st_size))
        db.add(models.ArtifactReference(message_id=message.id, artifact_id=identifier))
        db.commit()
    return identifier


def ticket(identifier, *, purpose="artifact-preview", expires=300):
    return jwt.encode({"purpose": purpose, "artifact": identifier,
                       "exp": datetime.now(timezone.utc) + timedelta(seconds=expires)},
                      SECRET_KEY, algorithm="HS256")


@pytest.mark.anyio
async def test_other_user_cannot_download_or_issue_ticket(admin, user_client, published):
    await register(user_client, "outsider")
    assert (await admin.get(f"/api/artifacts/{published}/download")).status_code == 200
    assert (await admin.post(f"/api/artifacts/{published}/preview-ticket")).status_code == 200
    assert (await user_client.get(f"/api/artifacts/{published}/download")).status_code == 404
    assert (await user_client.post(f"/api/artifacts/{published}/preview-ticket")).status_code == 404


@pytest.mark.anyio
async def test_unauthenticated_access_denied(admin, user_client, published):
    assert (await user_client.get(f"/api/artifacts/{published}/download")).status_code == 401
    assert (await user_client.post(f"/api/artifacts/{published}/preview-ticket")).status_code == 401


@pytest.mark.anyio
async def test_preview_ticket_rejects_expiry_purpose_and_forgery(admin, published):
    valid = ticket(published)
    assert (await admin.get(f"/api/artifacts/isolated/{valid}")).status_code == 200
    for invalid in (ticket(published, expires=-10), ticket(published, purpose="wrong"), valid[:-1] + ("a" if valid[-1] != "a" else "b")):
        assert (await admin.get(f"/api/artifacts/isolated/{invalid}")).status_code == 404


@pytest.mark.anyio
async def test_ticket_stops_working_after_final_reference_removed(admin, published):
    valid = ticket(published)
    assert (await admin.get(f"/api/artifacts/isolated/{valid}")).status_code == 200
    with Session(engine) as db:
        db.query(models.ArtifactReference).filter_by(artifact_id=published).delete()
        db.commit()
    assert (await admin.get(f"/api/artifacts/isolated/{valid}")).status_code == 404
