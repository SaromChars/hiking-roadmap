"""Generic data fetching with caching: DEM (terrarium), satellite (ArcGIS), OSM (Overpass).
bbox everywhere is (lat0, lat1, lon0, lon1)."""
import hashlib, io, json, math, os, time, urllib.parse, urllib.request
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.environ.get('GZ_CACHE') or os.path.join(HERE, 'cache')
UA = 'gz-hiking-3d/1.0'
DEM_URL = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'
SAT_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
OVERPASS_URLS = ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter']


def merc(lat, lon, z):
    """Lat/lon -> float tile coordinates (fx, fy) at zoom z."""
    n = 2 ** z
    r = math.radians(lat)
    return ((lon + 180) / 360 * n, (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n)


def _http(url, data=None, timeout=60):
    """Single network entry point (patch urllib.request.urlopen in tests)."""
    req = urllib.request.Request(url, data=data, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_tile(url_tmpl, z, x, y, cache_dir):
    """Download a tile (3 attempts, backoff); cached on disk, cache hits make no request."""
    sub = hashlib.md5(url_tmpl.encode()).hexdigest()[:8]
    path = os.path.join(cache_dir, f'{sub}_{z}_{x}_{y}.tile')
    if os.path.exists(path):
        with open(path, 'rb') as f:
            return f.read()
    err = None
    for i in range(3):
        try:
            b = _http(url_tmpl.format(z=z, x=x, y=y))
            os.makedirs(cache_dir, exist_ok=True)
            with open(path + '.tmp', 'wb') as f:
                f.write(b)
            os.replace(path + '.tmp', path)
            return b
        except Exception as e:
            err = e
            if i < 2:
                time.sleep(1.5 * (i + 1))
    raise RuntimeError(f'tile {z}/{x}/{y} failed: {err}')


def _tile_range(bbox, z):
    lat0, lat1, lon0, lon1 = bbox
    fx0, fy1 = merc(lat0, lon0, z)   # south-west
    fx1, fy0 = merc(lat1, lon1, z)   # north-east
    return int(fx0), int(fx1), int(fy0), int(fy1)


def _tile_dir():
    return os.path.join(CACHE, 'tiles')


def decode_terrarium(png):
    a = np.asarray(Image.open(io.BytesIO(png)).convert('RGB')).astype(np.float64)
    return a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768


def dem(bbox, z=14):
    """Stitched terrarium mosaic (metres, negatives clipped to 0) of tiles covering bbox.
    Returns (heights, {'x0','y0','z'}) where x0,y0 = top-left tile indices."""
    x0, x1, y0, y1 = _tile_range(bbox, z)
    out = np.zeros(((y1 - y0 + 1) * 256, (x1 - x0 + 1) * 256))
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            h = decode_terrarium(fetch_tile(DEM_URL, z, x, y, _tile_dir()))
            out[(y - y0) * 256:(y - y0 + 1) * 256, (x - x0) * 256:(x - x0 + 1) * 256] = h
    return np.clip(out, 0, None), {'x0': x0, 'y0': y0, 'z': z}


def satellite(bbox, z, max_side=3000):
    """Satellite mosaic resampled to equirect (north up, lat/lon linear), long side <= max_side."""
    lat0, lat1, lon0, lon1 = bbox
    x0, x1, y0, y1 = _tile_range(bbox, z)
    mos = Image.new('RGB', ((x1 - x0 + 1) * 256, (y1 - y0 + 1) * 256))
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            t = Image.open(io.BytesIO(fetch_tile(SAT_URL, z, x, y, _tile_dir()))).convert('RGB')
            mos.paste(t, ((x - x0) * 256, (y - y0) * 256))
    M = np.asarray(mos)
    clat = (lat0 + lat1) / 2
    wkm = (lon1 - lon0) * 111.32 * math.cos(math.radians(clat))
    hkm = (lat1 - lat0) * 110.57
    if wkm >= hkm:
        W, H = max_side, max(1, round(max_side * hkm / wkm))
    else:
        W, H = max(1, round(max_side * wkm / hkm)), max_side
    lons = lon0 + (lon1 - lon0) * (np.arange(W) + .5) / W
    lats = lat1 - (lat1 - lat0) * (np.arange(H) + .5) / H
    px = (np.array([merc(clat, l, z)[0] for l in lons]) - x0) * 256
    py = (np.array([merc(l, lons[0], z)[1] for l in lats]) - y0) * 256
    ix = np.clip(px.astype(int), 0, M.shape[1] - 1)
    iy = np.clip(py.astype(int), 0, M.shape[0] - 1)
    return Image.fromarray(M[iy[:, None], ix[None, :]])


def _query(bbox):
    lat0, lat1, lon0, lon1 = bbox
    b = f'{lat0},{lon0},{lat1},{lon1}'
    return (f'[out:json][timeout:120];('
            f'way["highway"]({b});'
            f'node["natural"="peak"]({b});'
            f'node["tourism"~"^(attraction|viewpoint)$"]({b});'
            f'node["amenity"="place_of_worship"]({b});way["amenity"="place_of_worship"]({b});'
            f'way["natural"="water"]["name"]({b});way["waterway"]["name"]({b});'
            f'way["aerialway"]({b});node["aerialway"]({b});'
            f');out geom;')


def _extra_query(bbox):
    """Named entrances/trailheads and water relations the main query misses (for --inspect)."""
    lat0, lat1, lon0, lon1 = bbox
    b = f'{lat0},{lon0},{lat1},{lon1}'
    return (f'[out:json][timeout:120];('
            f'nwr["name"~"门|入口|登山口|登山道"]({b});'
            f'node["highway"="trailhead"]({b});node["entrance"]["name"]({b});'
            f'relation["natural"="water"]["name"]({b});way["water"="reservoir"]["name"]({b});'
            f'nwr["leisure"~"^(park|garden|nature_reserve)$"]["name"]({b});'
            f');out center tags;')


def overpass(bbox):
    """OSM elements (with geometry) for bbox; cached in cache/osm_<hash>.json."""
    return overpass_q(_query(bbox))


def overpass_extra(bbox):
    """Supplementary named entrances / water bodies / parks (elements carry 'center' for ways)."""
    return overpass_q(_extra_query(bbox))


def overpass_q(q):
    path = os.path.join(CACHE, 'osm_' + hashlib.md5(q.encode()).hexdigest()[:12] + '.json')
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    body = urllib.parse.urlencode({'data': q}).encode()
    err = None
    for i in range(3):
        for u in OVERPASS_URLS:
            try:
                els = json.loads(_http(u, data=body, timeout=180))['elements']
                os.makedirs(CACHE, exist_ok=True)
                with open(path + '.tmp', 'w', encoding='utf-8') as f:
                    json.dump(els, f, ensure_ascii=False)
                os.replace(path + '.tmp', path)
                return els
            except Exception as e:
                err = e
        time.sleep(3 * (i + 1))
    raise RuntimeError(f'overpass failed: {err}')
