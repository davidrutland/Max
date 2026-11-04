"""Stage 2: import requires a persisted attachment owned by the active chat."""
import pytest
from app import models
from app.database import SessionLocal
from app.routers import chats, uploads
from app.tools import sandbox


@pytest.mark.anyio
async def test_import_authorized_chat_only(admin, monkeypatch, tmp_path):
    monkeypatch.setattr(uploads, 'ROOT', tmp_path)
    response = await admin.post('/api/uploads', files={'file': ('sample.bin', b'original bytes')})
    assert response.status_code == 200
    identifier = response.json()['id']
    with SessionLocal() as db:
        user = db.query(models.User).first()
        owned = models.Chat(user_id=user.id, title='owned')
        other = models.Chat(user_id=user.id, title='other')
        db.add_all([owned, other]); db.flush()
        db.add(models.Message(chat_id=owned.id, role='user', content='attachment', attachments=[{'name':'sample.bin', 'upload_id':identifier}]))
        db.commit()
        owner_id, owned_id, other_id = user.id, owned.id, other.id

    calls = []
    async def fake_import(path, filename, mime):
        calls.append((path.read_bytes(), filename))
        return '/workspace/max-upload-unique-sample.bin'
    monkeypatch.setattr(sandbox, 'import_uploaded_file', fake_import)
    assert 'not attached' in await chats._import_chat_upload(other_id, owner_id, identifier)
    assert 'not attached' in await chats._import_chat_upload(owned_id, owner_id + 999, identifier)
    assert calls == []
    result = await chats._import_chat_upload(owned_id, owner_id, identifier)
    assert '/workspace/max-upload-unique-sample.bin' in result
    assert calls == [(b'original bytes', 'sample.bin')]


def test_inject_binary_reference():
    messages = [{'role':'user', 'content':'inspect', 'attachments':[{'name':'photo.png','upload_id':'test123'}]}]
    result = chats._inject_attachments(messages)
    assert 'sandbox_import_upload' in result[0]['content']
    assert 'test123' in result[0]['content']

@pytest.mark.anyio
async def test_import_transfers_exact_bytes_to_openhands(monkeypatch, tmp_path):
    import hashlib
    import httpx
    payload = bytes(range(256)) * 4096
    source = tmp_path / 'original.bin'
    source.write_bytes(payload)
    captured = {}

    async def fake_conversation():
        return 'sandbox-conversation'

    def handler(request):
        assert request.method == 'POST'
        assert request.url.path == '/api/conversations/sandbox-conversation/file/upload'
        destination = request.url.params['path']
        assert destination.startswith('/workspace/max-upload-')
        assert destination.endswith('-original.bin')
        body = request.read()
        assert payload in body
        captured['hash'] = hashlib.sha256(payload).hexdigest()
        captured['destination'] = destination
        return httpx.Response(200, json={'ok': True})

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs['transport'] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr(sandbox, '_conversation', fake_conversation)
    monkeypatch.setattr(sandbox.httpx, 'AsyncClient', fake_client)
    result = await sandbox.import_uploaded_file(source, 'original.bin', 'application/octet-stream')
    assert result == captured['destination']
    assert captured['hash'] == hashlib.sha256(source.read_bytes()).hexdigest()


@pytest.mark.anyio
async def test_import_rejects_missing_and_symlink_sources(tmp_path):
    import pytest
    missing = tmp_path / 'missing.bin'
    with pytest.raises(ValueError):
        await sandbox.import_uploaded_file(missing, 'missing.bin', 'application/octet-stream')
    link = tmp_path / 'link.bin'
    target = tmp_path / 'target.bin'
    target.write_bytes(b'secret')
    link.symlink_to(target)
    with pytest.raises(ValueError):
        await sandbox.import_uploaded_file(link, 'link.bin', 'application/octet-stream')
