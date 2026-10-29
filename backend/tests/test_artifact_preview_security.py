"""Adversarial, side-effect-free tests for the ZIP preview asset reader."""
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED, ZipInfo
import pytest

from app.routers.artifacts import zip_asset, MAX_ZIP_ENTRIES, MAX_ZIP_ENTRY, MAX_ZIP_TOTAL


def archive(files):
    stream = BytesIO()
    with ZipFile(stream, 'w', ZIP_DEFLATED) as output:
        for name, content in files:
            output.writestr(name, content)
    return stream.getvalue()


def rejected(blob, path):
    with pytest.raises(ValueError):
        zip_asset(blob, path)


def test_valid_relative_assets():
    blob = archive([('index.html', b'<h1>OK</h1>'), ('js/app.js', b'console.log(1)')])
    assert zip_asset(blob, 'index.html') == (b'<h1>OK</h1>', 'text/html')
    assert zip_asset(blob, 'js/app.js') == (b'console.log(1)', 'text/javascript')


@pytest.mark.parametrize('path', [
    '', '../index.html', 'dir/../index.html', './index.html', '/index.html',
    'dir\\index.html', 'index.html\x00', 'https://example.com/index.html',
    'index.html/../../secret.txt',
])
def test_invalid_requested_paths(path):
    rejected(archive([('index.html', b'ok')]), path)


def test_unsupported_extension():
    rejected(archive([('evil.exe', b'bad')]), 'evil.exe')


def test_missing_asset():
    rejected(archive([('index.html', b'ok')]), 'missing.html')


def test_duplicate_entries():
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        blob = archive([('index.html', b'first'), ('index.html', b'second')])
    rejected(blob, 'index.html')


def test_symlink_entry():
    stream = BytesIO()
    info = ZipInfo('index.html')
    info.create_system = 3
    info.external_attr = (0o120777 << 16)
    with ZipFile(stream, 'w') as output:
        output.writestr(info, b'/etc/passwd')
    rejected(stream.getvalue(), 'index.html')


def test_too_many_entries():
    blob = archive([('index.html', b'ok')] + [(f'{i}.txt', b'x') for i in range(MAX_ZIP_ENTRIES)])
    rejected(blob, 'index.html')


def test_oversized_entry():
    blob = archive([('index.html', b'x' * (MAX_ZIP_ENTRY + 1))])
    rejected(blob, 'index.html')


def test_oversized_total():
    chunk = b'x' * (MAX_ZIP_ENTRY - 1)
    blob = archive([(f'{i}.txt', chunk) for i in range(MAX_ZIP_TOTAL // len(chunk) + 1)])
    rejected(blob, '0.txt')


def test_invalid_archive():
    rejected(b'not a ZIP file', 'index.html')
