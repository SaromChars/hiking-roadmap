import io, json, urllib.parse, os, sys
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(__file__))
import fetch


class Resp:
    def __init__(self, b): self.b = b
    def read(self): return self.b
    def __enter__(self): return self
    def __exit__(self, *a): return False


def png_bytes(r, g, b):
    im = Image.new('RGB', (256, 256), (r, g, b))
    buf = io.BytesIO(); im.save(buf, 'PNG'); return buf.getvalue()


def test_merc_known():
    fx, fy = fetch.merc(23.18, 113.29, 14)
    # brief says 'near' (13347, 7106); true value is inside old tile range x 13346-13349, y 7104-7109
    assert int(fx) == 13347 and abs(fy - 7106) < 1.5 and 7104 <= int(fy) <= 7109


def test_cache_hit(tmp_path, monkeypatch):
    calls = []
    def fake(req, timeout=None):
        calls.append(1); return Resp(b'abc')
    monkeypatch.setattr(fetch.urllib.request, 'urlopen', fake)
    t = 'http://x/{z}/{x}/{y}.png'
    assert fetch.fetch_tile(t, 5, 1, 2, str(tmp_path)) == b'abc'
    assert fetch.fetch_tile(t, 5, 1, 2, str(tmp_path)) == b'abc'
    assert len(calls) == 1


def test_retry(tmp_path, monkeypatch):
    calls = []
    def fake(req, timeout=None):
        calls.append(1)
        if len(calls) < 3: raise OSError('boom')
        return Resp(b'ok')
    monkeypatch.setattr(fetch.urllib.request, 'urlopen', fake)
    monkeypatch.setattr(fetch.time, 'sleep', lambda s: None)
    assert fetch.fetch_tile('http://x/{z}/{x}/{y}', 1, 0, 0, str(tmp_path)) == b'ok'
    assert len(calls) == 3


def test_decode_terrarium():
    # R*256+G+B/256-32768 : (128,10,128) -> 10.5 ; (127,0,0) -> negative
    a = fetch.decode_terrarium(png_bytes(128, 10, 128))
    assert a.shape == (256, 256) and abs(a[0, 0] - 10.5) < 1e-6
    assert fetch.decode_terrarium(png_bytes(127, 0, 0)).max() == -256


def test_dem_clip_and_georef(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, 'CACHE', str(tmp_path))
    monkeypatch.setattr(fetch, 'fetch_tile', lambda t, z, x, y, c: png_bytes(127, 0, 0) if x == 13346 else png_bytes(128, 5, 0))
    h, g = fetch.dem((23.140, 23.222, 113.262, 113.326), 14)
    assert g['z'] == 14 and g['x0'] == 13346 and g['y0'] == 7104
    assert h.min() >= 0 and h.shape[1] % 256 == 0 and h.shape[0] % 256 == 0
    assert h[0, 0] == 0 and h.max() == 5


def test_satellite_size(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, 'fetch_tile', lambda t, z, x, y, c: png_bytes(10, 200, 30))
    im = fetch.satellite((23.140, 23.222, 113.262, 113.326), 14)
    assert max(im.size) <= 3000 and im.size[1] == 3000 and im.size[0] < 3000
    assert im.getpixel((5, 5)) == (10, 200, 30)


def test_overpass_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, 'CACHE', str(tmp_path))
    calls = []
    def fake(req, timeout=None):
        calls.append(req); return Resp(json.dumps({'elements': [{'id': 1}]}).encode())
    monkeypatch.setattr(fetch.urllib.request, 'urlopen', fake)
    bb = (23.14, 23.22, 113.26, 113.32)
    assert fetch.overpass(bb) == [{'id': 1}]
    assert fetch.overpass(bb) == [{'id': 1}]
    assert len(calls) == 1
    q = urllib.parse.unquote_plus(calls[0].data.decode())
    for k in ('highway', 'peak', 'viewpoint', 'place_of_worship', 'aerialway', 'out geom'):
        assert k in q
    assert calls[0].get_header('User-agent') == 'gz-hiking-3d/1.0'


def test_overpass_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, 'CACHE', str(tmp_path))
    monkeypatch.setattr(fetch.time, 'sleep', lambda s: None)
    def fake(req, timeout=None):
        if 'overpass-api.de' in req.full_url: raise OSError('504')
        return Resp(b'{"elements": []}')
    monkeypatch.setattr(fetch.urllib.request, 'urlopen', fake)
    assert fetch.overpass((1, 2, 3, 4)) == []
