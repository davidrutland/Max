import pytest
from app import artifact_store


def test_publish_immutable_and_remove(tmp_path):
    original = bytearray(b'example')
    key = artifact_store.publish(original, root=tmp_path)
    original[:] = b'changed'
    assert artifact_store.resolve(key, root=tmp_path).read_bytes() == b'example'
    artifact_store.remove(key, root=tmp_path)
    assert not artifact_store.resolve(key, root=tmp_path).exists()


def test_reject_path_traversal(tmp_path):
    for key in ('../secret', 'g' * 48, '/etc/passwd'):
        with pytest.raises(ValueError):
            artifact_store.resolve(key, root=tmp_path)


def test_size_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(artifact_store, 'MAX_BYTES', 2)
    with pytest.raises(ValueError):
        artifact_store.publish(b'123', root=tmp_path)
    assert not list(tmp_path.iterdir())
