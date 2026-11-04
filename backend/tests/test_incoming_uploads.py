"""Stage 1 binary upload: integrity, limits and ownership."""
import io
import os
import zipfile
import tarfile
import pytest
from app.routers import uploads
from conftest import register

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.fixture(autouse=True)
def isolated_uploads(monkeypatch, tmp_path):
    monkeypatch.setattr(uploads, 'ROOT', tmp_path)
    monkeypatch.setenv('MAX_FILE_UPLOAD_MIB', '2')

@pytest.mark.anyio
@pytest.mark.parametrize('name,data', [
    ('picture.png', b'\x89PNG\r\n\x1a\n' + os.urandom(2048)),
    ('archive.tar.gz', b'\x1f\x8b' + os.urandom(8192)),
    ('unknown.weird', os.urandom(4096)),
    ('empty.zip', b''),
])
async def test_round_trip(admin, name, data):
    resp = await admin.post('/api/uploads', files={'file': (name, data, 'application/octet-stream')})
    assert resp.status_code == 200, resp.text
    assert resp.json()['name'] == name
    assert resp.json()['size'] == len(data)
    downloaded = await admin.get(f"/api/uploads/{resp.json()['id']}/download")
    assert downloaded.status_code == 200
    assert downloaded.content == data

@pytest.mark.anyio
async def test_rejects_oversize_without_leaving_file(admin):
    resp = await admin.post('/api/uploads', files={'file': ('large.zip', b'x' * (2 * 1024 * 1024 + 1))})
    assert resp.status_code == 413
    assert not list(uploads.ROOT.iterdir())

@pytest.mark.anyio
async def test_ownership(admin, user_client):
    uploaded = await admin.post('/api/uploads', files={'file': ('secret.zip', b'private')})
    identifier = uploaded.json()['id']
    assert (await user_client.get(f'/api/uploads/{identifier}/download')).status_code == 401
    await register(user_client, 'second')
    assert (await user_client.get(f'/api/uploads/{identifier}/download')).status_code == 404

@pytest.mark.anyio
async def test_filename_traversal_removed(admin):
    resp = await admin.post('/api/uploads', files={'file': ('../../oops.zip', b'content')})
    assert resp.status_code == 200
    assert resp.json()['name'] == 'oops.zip'

@pytest.mark.anyio
async def test_real_zip_and_tar_gz(admin):
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, 'w') as z:
        z.writestr('dog/one.jpg', b'\xff\xd8\xff' + os.urandom(500))
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode='w:gz') as t:
        data = b'photo' * 100
        info = tarfile.TarInfo('dog/two.jpg')
        info.size = len(data)
        t.addfile(info, io.BytesIO(data))
    for name, blob in [('photos.zip', zip_buf.getvalue()), ('photos.tar.gz', tar_buf.getvalue())]:
        response = await admin.post('/api/uploads', files={'file': (name, blob)})
        assert response.status_code == 200, response.text
        downloaded = await admin.get(f"/api/uploads/{response.json()['id']}/download")
        assert downloaded.content == blob

@pytest.mark.anyio
async def test_remove_unsent_upload(admin):
    response = await admin.post('/api/uploads', files={'file': ('unused.zip', b'payload')})
    identifier = response.json()['id']
    assert (await admin.delete(f'/api/uploads/{identifier}')).status_code == 204
    assert (await admin.get(f'/api/uploads/{identifier}/download')).status_code == 404
    assert not (uploads.ROOT / identifier).exists()

@pytest.mark.anyio
async def test_references_survive_until_last_chat_deleted(admin):
    from app.database import SessionLocal
    from app import models
    from app.upload_lifecycle import ids_in_chat, reclaim_after_change
    response = await admin.post('/api/uploads', files={'file': ('shared.zip', b'payload')})
    identifier = response.json()['id']
    with SessionLocal() as db:
        user = db.query(models.User).first()
        first = models.Chat(user_id=user.id, title='one')
        second = models.Chat(user_id=user.id, title='two')
        db.add_all([first, second]); db.flush()
        db.add_all([models.Message(chat_id=c.id, role='user', content='file', attachments=[{'name':'shared.zip','upload_id':identifier}]) for c in (first, second)])
        db.commit()
        first_id, second_id = first.id, second.id
    assert (await admin.delete(f'/api/uploads/{identifier}')).status_code == 409
    assert (await admin.delete(f'/api/chats/{first_id}')).status_code == 204
    assert (await admin.get(f'/api/uploads/{identifier}/download')).status_code == 200
    assert (await admin.delete(f'/api/chats/{second_id}')).status_code == 204
    assert (await admin.get(f'/api/uploads/{identifier}/download')).status_code == 404
    assert not (uploads.ROOT / identifier).exists()

@pytest.mark.anyio
async def test_stale_unattached_upload_reclaimed_on_next_upload(admin):
    import datetime
    from app.database import SessionLocal
    from app import models
    first = await admin.post('/api/uploads', files={'file': ('old.zip', b'old')})
    old_id = first.json()['id']
    with SessionLocal() as db:
        record = db.get(models.IncomingUpload, old_id)
        record.created_at = models.utcnow() - datetime.timedelta(hours=25)
        db.commit()
    fresh = await admin.post('/api/uploads', files={'file': ('fresh.zip', b'fresh')})
    assert fresh.status_code == 200
    assert (await admin.get(f'/api/uploads/{old_id}/download')).status_code == 404
    assert not (uploads.ROOT / old_id).exists()

@pytest.mark.anyio
async def test_edit_message_reclaims_upload_from_discarded_future(admin):
    from app.database import SessionLocal
    from app import models
    uploaded = await admin.post('/api/uploads', files={'file': ('future.zip', b'payload')})
    identifier = uploaded.json()['id']
    await admin.post('/api/servers', json={'name': 's', 'host': '127.0.0.1', 'port': 1})
    chat_id = (await admin.post('/api/chats', json={'title': 'edit test'})).json()['id']
    with SessionLocal() as db:
        db.add(models.Message(chat_id=chat_id, role='assistant', content='first'))
        db.flush()
        first_id = db.query(models.Message.id).filter_by(chat_id=chat_id).first()[0]
        db.add(models.Message(chat_id=chat_id, role='user', content='later', attachments=[{'name':'future.zip','upload_id':identifier}]))
        db.commit()
    response = await admin.put(f'/api/chats/{chat_id}/messages/{first_id}', json={'content':'edited', 'server_id':1, 'model':'m'})
    assert response.status_code == 200, response.text
    assert (await admin.get(f'/api/uploads/{identifier}/download')).status_code == 404
    assert not (uploads.ROOT / identifier).exists()
