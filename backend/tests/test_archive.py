"""Archive and restore conversations without losing their contents."""

from app import models
from app.database import SessionLocal


async def test_archive_restore_preserves_chat_and_messages(admin):
    created = await admin.post("/api/chats", json={"title": "Keep this"})
    assert created.status_code == 200, created.text

    chat = created.json()
    chat_id = chat["id"]
    assert chat["archived"] is False

    with SessionLocal() as db:
        db.add(models.Message(
            chat_id=chat_id,
            role="user",
            content="Important original message",
        ))
        db.commit()

    original_updated_at = chat["updated_at"]

    archived = await admin.patch(
        f"/api/chats/{chat_id}", json={"archived": True}
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["archived"] is True
    assert archived.json()["updated_at"] == original_updated_at

    listed = (await admin.get("/api/chats")).json()
    assert any(c["id"] == chat_id and c["archived"] for c in listed)

    detail = await admin.get(f"/api/chats/{chat_id}")
    assert detail.status_code == 200
    assert detail.json()["archived"] is True
    assert any(
        m["content"] == "Important original message"
        for m in detail.json()["messages"]
    )

    restored = await admin.patch(
        f"/api/chats/{chat_id}", json={"archived": False}
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["archived"] is False
    assert restored.json()["updated_at"] == original_updated_at

    detail = (await admin.get(f"/api/chats/{chat_id}")).json()
    assert detail["archived"] is False
    assert any(
        m["content"] == "Important original message"
        for m in detail["messages"]
    )
