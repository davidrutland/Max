import base64
import io
from PIL import Image
import pytest
from app import config
from app.tools import sandbox
from app.tools.registry import ToolResult


def test_resize_and_no_upscale(monkeypatch):
    monkeypatch.setattr(config, 'SANDBOX_VISION_MAX_DIMENSION', 720)
    for dimensions, expected in [((1920, 1080), (720, 405)), ((320, 240), (320, 240))]:
        data = io.BytesIO()
        Image.new('RGB', dimensions, 'red').save(data, 'PNG')
        result = sandbox._vision_image(data.getvalue(), '/workspace/test.png')
        assert isinstance(result, ToolResult)
        encoded = result.images[0].split(',', 1)[1]
        assert Image.open(io.BytesIO(base64.b64decode(encoded))).size == expected


def test_svg_render(monkeypatch):
    monkeypatch.setattr(config, 'SANDBOX_VISION_MAX_DIMENSION', 720)
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="720"><rect width="1440" height="720" fill="red"/></svg>'
    result = sandbox._vision_image(svg, '/workspace/dog.svg')
    image = Image.open(io.BytesIO(base64.b64decode(result.images[0].split(',', 1)[1])))
    assert image.size == (720, 360)


def test_svg_external_rejected():
    with pytest.raises(ValueError, match='unsupported external'):
        sandbox._vision_image(b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><image href="file:///etc/passwd"/></svg>', '/workspace/x.svg')


@pytest.mark.asyncio
async def test_tool_fetch(monkeypatch):
    data = io.BytesIO()
    Image.new('RGB', (8, 8)).save(data, 'PNG')
    async def fetch(path):
        assert path == '/workspace/p.png'
        return data.getvalue()
    monkeypatch.setattr(sandbox, 'fetch_attachment', fetch)
    result = await sandbox._sandbox_view_image({'path': 'p.png'})
    assert isinstance(result, ToolResult) and result.images
    assert (await sandbox._sandbox_view_image({'path': '../escape.png'})).startswith('ERROR:')

@pytest.mark.parametrize('format,extension', [
    ('JPEG', 'jpg'), ('WEBP', 'webp'), ('GIF', 'gif'),
    ('BMP', 'bmp'), ('TIFF', 'tiff'),
])
def test_common_raster_formats(format, extension):
    data = io.BytesIO()
    Image.new('RGB', (80, 40), 'blue').save(data, format=format)
    result = sandbox._vision_image(data.getvalue(), f'/workspace/image.{extension}')
    image = Image.open(io.BytesIO(base64.b64decode(result.images[0].split(',', 1)[1])))
    assert image.size == (80, 40)


def test_bad_image_rejected():
    with pytest.raises(ValueError, match='unsupported or invalid'):
        sandbox._vision_image(b'not an image', '/workspace/bad.png')


def test_svg_script_rejected():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><script>alert(1)</script></svg>'
    with pytest.raises(ValueError, match='unsupported external'):
        sandbox._vision_image(svg, '/workspace/x.svg')


def test_svg_renderer_network_fetch_disabled(monkeypatch):
    # Verify the renderer itself gets a deny-all fetcher, not just regex screening.
    from cairosvg.surface import PNGSurface
    original = PNGSurface.convert
    observed = []
    def intercept(**kwargs):
        observed.append(kwargs['url_fetcher'])
        with pytest.raises(ValueError, match='external resources are disabled'):
            kwargs['url_fetcher']('file:///etc/passwd', 'image/png')
        return original(**kwargs)
    monkeypatch.setattr(PNGSurface, 'convert', intercept)
    sandbox._vision_image(b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>', '/workspace/x.svg')
    assert observed


def test_gzip_svg_expansion_limit():
    import gzip
    data = gzip.compress(b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">' + b' ' * (sandbox.VISION_MAX_INPUT_BYTES + 1) + b'</svg>')
    with pytest.raises(ValueError, match='expanded SVG exceeds size limit'):
        sandbox._vision_image(data, '/workspace/huge.svgz')
