"""Overview map for the list page: Guangzhou district outlines (OSM), a hillshade image and each
site's marker position.   Usage: python3 gz/build_map.py   (run after build_site.py)
Writes gz/out/site/gzmap.json and gz/out/site/gzrelief.jpg."""
import glob, json, math, os, sys
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fetch

OUT = os.path.join(HERE, 'out', 'site')
Q = ('[out:json][timeout:180];area["name"="广州市"]["admin_level"="5"]->.a;'
     'rel(area.a)["admin_level"="6"]["boundary"="administrative"];out geom;')


def rings(rel):
    """Join outer member ways into closed rings of (lon, lat)."""
    segs = [[(p['lon'], p['lat']) for p in m['geometry']] for m in rel['members']
            if m['type'] == 'way' and m.get('role', 'outer') in ('outer', '') and m.get('geometry')]
    out = []
    while segs:
        ring = segs.pop(0)
        while ring[0] != ring[-1]:
            for i, s in enumerate(segs):
                if s[0] == ring[-1]: ring += s[1:]
                elif s[-1] == ring[-1]: ring += s[::-1][1:]
                elif s[-1] == ring[0]: ring = s + ring[1:]
                elif s[0] == ring[0]: ring = s[::-1] + ring[1:]
                else: continue
                segs.pop(i)
                break
            else:
                break   # open ring (data gap): keep what we have
        out.append(ring)
    return out


def simplify(pts, tol):
    """Douglas–Peucker on (x, y) tuples, iterative."""
    if len(pts) < 3: return pts
    if pts[0] == pts[-1]:   # closed ring: split at the vertex farthest from the start
        a = np.array(pts)
        m = int(np.hypot(*(a - a[0]).T).argmax())
        return simplify(pts[:m + 1], tol)[:-1] + simplify(pts[m:], tol)
    a = np.array(pts)
    keep = np.zeros(len(a), bool); keep[0] = keep[-1] = True
    stack = [(0, len(a) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1: continue
        p, q = a[i], a[j]
        d = q - p
        n = math.hypot(*d) or 1e-12
        seg = a[i + 1:j]
        dist = np.abs(d[0] * (seg[:, 1] - p[1]) - d[1] * (seg[:, 0] - p[0])) / n
        k = int(dist.argmax())
        if dist[k] > tol:
            keep[i + 1 + k] = True
            stack += [(i, i + 1 + k), (i + 1 + k, j)]
    return [pts[i] for i in np.flatnonzero(keep)]


def site_points():
    """Marker = main peak if it is a POI, else bbox centre."""
    pts = {}
    for p in sorted(glob.glob(os.path.join(OUT, '*', 'terrain.json'))):
        with open(p, encoding='utf-8') as f:
            t = json.load(f)
        lat0, lat1, lon0, lon1 = t['bbox']
        latc = (lat0 + lat1) / 2
        with open(os.path.join(os.path.dirname(p), 'meta.json'), encoding='utf-8') as f:
            peak = json.load(f).get('peak')
        poi = next((q for q in t['pois'] if peak and q['n'] == peak), None)
        if poi:
            x, y = poi['p']
            ll = [lat0 + y / 110.57, lon0 + x / (111.32 * math.cos(math.radians(latc)))]
        else:
            ll = [latc, (lon0 + lon1) / 2]
        pts[t['id']] = [round(ll[0], 5), round(ll[1], 5)]
    return pts


def relief(bbox, z=10, px=1100):
    """Hillshade (NW light) of the terrarium DEM, as an equirectangular greyscale JPEG."""
    H, g = fetch.dem(bbox, z=z)
    lat0, lat1, lon0, lon1 = bbox
    n = 2 ** z
    def tile_xy(lat, lon):
        fx, fy = fetch.merc(lat, lon, z)
        return (fx - g['x0']) * 256, (fy - g['y0']) * 256
    w = px; h = int(px * (lat1 - lat0) / ((lon1 - lon0) * math.cos(math.radians((lat0 + lat1) / 2))))
    lons = np.linspace(lon0, lon1, w); lats = np.linspace(lat1, lat0, h)
    xs = np.array([tile_xy(lat0, l)[0] for l in lons]); ys = np.array([tile_xy(l, lon0)[1] for l in lats])
    ix = np.clip(xs.astype(int), 0, H.shape[1] - 1); iy = np.clip(ys.astype(int), 0, H.shape[0] - 1)
    E = H[iy[:, None], ix[None, :]].astype(float)
    cell = (lon1 - lon0) * 111320 * math.cos(math.radians((lat0 + lat1) / 2)) / w
    gy, gx = np.gradient(E, cell)
    k = 2.2   # vertical exaggeration for the shading
    slope = np.arctan(k * np.hypot(gx, gy)); aspect = np.arctan2(-gx, gy)
    az, alt = math.radians(315), math.radians(45)
    shade = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    shade = np.clip(shade, 0, 1)
    # flat ground stays white (multiplied over the land colour in the page); higher ground a bit darker
    tint = np.clip(E / 900, 0, 1)
    v = 255 + (shade - math.sin(alt)) * 230 - tint * 45
    return Image.fromarray(np.clip(v, 0, 255).astype(np.uint8)), (w, h)


def main():
    els = fetch.overpass_q(Q)
    districts, allpts = [], []
    for rel in sorted(els, key=lambda e: e['id']):
        rs = [simplify(r, 0.0012) for r in rings(rel)]
        rs = [r for r in rs if len(r) >= 4]
        for r in rs: allpts += r
        districts.append({'name': rel['tags'].get('name', ''), 'rings': [[[round(x, 4), round(y, 4)] for x, y in r] for r in rs]})
    lons = [p[0] for p in allpts]; lats = [p[1] for p in allpts]
    pad = 0.02
    bbox = (min(lats) - pad, max(lats) + pad, min(lons) - pad, max(lons) + pad)
    img, (w, h) = relief(bbox)
    img.save(os.path.join(OUT, 'gzrelief.jpg'), quality=82)
    data = {'bbox': [round(v, 4) for v in bbox], 'img': [w, h], 'districts': districts, 'sites': site_points()}
    with open(os.path.join(OUT, 'gzmap.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    print('districts', len(districts), 'points', sum(len(r) for d in districts for r in d['rings']),
          'sites', len(data['sites']), 'img', w, h,
          'json KB', os.path.getsize(os.path.join(OUT, 'gzmap.json')) // 1024,
          'jpg KB', os.path.getsize(os.path.join(OUT, 'gzrelief.jpg')) // 1024)


if __name__ == '__main__':
    main()
