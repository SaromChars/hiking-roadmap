"""Build per-site data packages: gz/out/site/<id>/{terrain.json,satellite.jpg,thumb.jpg,meta.json}
plus the list gz/out/site/sites.json.   Usage: python3 gz/build_site.py <id>|all
       python3 gz/build_site.py <id> --inspect [--bbox lat0,lat1,lon0,lon1]   (prints candidates, writes nothing)"""
import base64, glob, json, math, os, sys
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fetch, routing, sites_cfg

OUT = os.path.join(HERE, 'out', 'site')
TRAIL_HW = {'path', 'footway', 'steps', 'track'}
ROAD_HW = {'motorway', 'trunk', 'primary', 'secondary'}
GRID_KM, GRID_MAX = 0.025, 400


def default_exag(hmax, hmin):
    """Relief >= 300 m -> 1.5, <= 100 m -> 3.0, linear in between."""
    r = hmax - hmin
    if r >= 300:
        return 1.5
    if r <= 100:
        return 3.0
    return round(3.0 - 1.5 * (r - 100) / 200, 2)


def simplify(pts, eps):
    """Douglas-Peucker (iterative)."""
    pts = [tuple(p) for p in pts]
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        (x0, y0), (x1, y1) = pts[i], pts[j]
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        best, bk = -1.0, -1
        for k in range(i + 1, j):
            px, py = pts[k]
            d = (abs(dy * (px - x0) - dx * (py - y0)) / L) if L > 0 else math.hypot(px - x0, py - y0)
            if d > best:
                best, bk = d, k
        if bk >= 0 and best > eps:
            keep[bk] = True
            stack += [(i, bk), (bk, j)]
    return [p for p, k in zip(pts, keep) if k]


def _r3(pts):
    return [[round(x, 3), round(y, 3)] for x, y in pts]


# ---------------------------------------------------------------- terrain grid
def height_grid(bbox, latc, W, H):
    """DEM mosaic -> bilinear lat/lon-linear grid (row 0 = south), lightly smoothed. Metres."""
    lat0, lat1, lon0, lon1 = bbox
    NX = min(GRID_MAX, max(2, round(W / GRID_KM)))
    NY = min(GRID_MAX, max(2, round(H / GRID_KM)))
    mos, g = fetch.dem(bbox, 14)
    z, x0, y0 = g['z'], g['x0'], g['y0']
    lat = lat0 + (lat1 - lat0) * np.arange(NY + 1) / NY
    lon = lon0 + (lon1 - lon0) * np.arange(NX + 1) / NX
    lonc = (lon0 + lon1) / 2
    gx = np.array([(fetch.merc(latc, l, z)[0] - x0) * 256 for l in lon])
    gy = np.array([(fetch.merc(l, lonc, z)[1] - y0) * 256 for l in lat])
    X = np.broadcast_to(gx[None, :], (NY + 1, NX + 1))
    Y = np.broadcast_to(gy[:, None], (NY + 1, NX + 1))
    i = np.clip(np.floor(X).astype(int), 0, mos.shape[1] - 2)
    j = np.clip(np.floor(Y).astype(int), 0, mos.shape[0] - 2)
    u, v = X - i, Y - j
    Hh = (mos[j, i] * (1 - u) * (1 - v) + mos[j, i + 1] * u * (1 - v)
          + mos[j + 1, i] * (1 - u) * v + mos[j + 1, i + 1] * u * v)
    P = np.pad(Hh, 1, mode='edge')
    Hh = .6 * Hh + .4 * sliding_window_view(P, (3, 3)).mean(axis=(2, 3))
    return Hh, NX, NY


def make_hfun(Hh, NX, NY, W, H):
    def h(x, y):
        fx = min(max(x / W * NX, 0), NX - 1e-9); fy = min(max(y / H * NY, 0), NY - 1e-9)
        i, j = int(fx), int(fy); u, v = fx - i, fy - j
        return (Hh[j, i] * (1 - u) * (1 - v) + Hh[j, i + 1] * u * (1 - v)
                + Hh[j + 1, i] * (1 - u) * v + Hh[j + 1, i + 1] * u * v)
    return h


# ---------------------------------------------------------------- OSM layers
def _inside(geo, bbox):
    lat0, lat1, lon0, lon1 = bbox
    return any(lat0 <= p['lat'] <= lat1 and lon0 <= p['lon'] <= lon1 for p in geo)


def lines(elements, bbox, g):
    trails, roads, cable, cable_osm_name = [], [], [], None
    for e in elements:
        if e.get('type') != 'way' or not e.get('geometry') or not _inside(e['geometry'], bbox):
            continue
        tg = e.get('tags', {})
        pts = [g.km(p['lat'], p['lon']) for p in e['geometry']]
        hw = tg.get('highway')
        if hw in TRAIL_HW:
            trails.append(_r3(simplify(pts, .012)))
        elif hw in ROAD_HW:
            roads.append({'k': hw[0], 'p': _r3(simplify(pts, .02))})
        elif tg.get('aerialway') in ('cable_car', 'gondola') and len(pts) > len(cable):
            cable, cable_osm_name = _r3(pts), tg.get('name')
    return trails, roads, cable, cable_osm_name


def _centroid(e):
    if e['type'] == 'node':
        return e['lat'], e['lon']
    if e.get('center'):
        return e['center']['lat'], e['center']['lon']
    geo = e.get('geometry') or []
    if not geo:
        return None
    return sum(p['lat'] for p in geo) / len(geo), sum(p['lon'] for p in geo) / len(geo)


def poi_kind(tags, etype):
    """Classify an OSM element as a POI candidate -> (kind, class) with kind in peak/gate/spot
    and class in peak/gate/attraction/viewpoint/temple/reservoir, or (None, None).
    Named highway elements are only gates when they are trailheads (main pipeline skips highways)."""
    n = tags.get('name') or ''
    if not n:
        return None, None
    if tags.get('natural') == 'peak' and not tags.get('amenity'):
        return 'peak', 'peak'
    if (('门' in n or '入口' in n) and etype == 'node') or tags.get('highway') == 'trailhead':
        return 'gate', 'gate'
    if tags.get('tourism') in ('attraction', 'viewpoint'):
        return 'spot', tags['tourism']
    if tags.get('amenity') == 'place_of_worship':
        return 'spot', 'temple'
    if tags.get('water') == 'reservoir':
        return 'spot', 'reservoir'
    return None, None


def auto_pois(elements, bbox, g, limit=40):
    """Named peaks, attractions, viewpoints, places of worship, reservoirs, 门/入口 nodes.
    Ordered peak (with ele, highest first) > spot > gate; capped at `limit`."""
    lat0, lat1, lon0, lon1 = bbox
    found = {}
    for e in elements:
        tg = e.get('tags', {}); n = tg.get('name')
        if not n or e.get('type') not in ('node', 'way') or tg.get('highway'):
            continue
        k = poi_kind(tg, e['type'])[0]
        if not k:
            continue
        c = _centroid(e)
        if not c or not (lat0 <= c[0] <= lat1 and lon0 <= c[1] <= lon1):
            continue
        ele = tg.get('ele') if k == 'peak' else None
        prev = found.get(n)
        if prev and (prev['ele'] or not ele):   # keep first, unless this duplicate has an ele
            continue
        x, y = g.km(*c)
        found[n] = {'n': n, 'p': [round(x, 3), round(y, 3)], 'k': k, 'ele': ele}

    def rank(p):
        if p['k'] == 'peak' and p['ele']:
            return (0, -_num(p['ele']))
        return ({'peak': 1, 'spot': 2, 'gate': 3}[p['k']], 0)
    return sorted(found.values(), key=rank)[:limit]


def _num(s):
    try:
        return float(str(s).replace('m', '').strip())
    except ValueError:
        return 0.0


def site_pois(cfg, elements, bbox, g):
    # with a whitelist the cap is applied by the whitelist itself
    auto = auto_pois(elements, bbox, g, limit=None if cfg.get('poi_only') else 40)
    by = {p['n']: p for p in auto}
    order = [p['n'] for p in auto]
    for x in cfg.get('pois_extra', []):
        if 'p' in x:
            p = [round(x['p'][0], 3), round(x['p'][1], 3)]
        else:
            p = [round(v, 3) for v in g.km(x['lat'], x['lon'])]
        if x['n'] not in by:
            order.append(x['n'])
        by[x['n']] = {'n': x['n'], 'p': p, 'k': x.get('k', 'spot'), 'ele': x.get('ele')}
    if cfg.get('poi_only'):
        missing = [n for n in cfg['poi_only'] if n not in by]
        if missing:
            raise ValueError(f"{cfg['id']}: poi_only names not found: {missing}")
        order = list(cfg['poi_only'])
    return [by[n] for n in order]


# ---------------------------------------------------------------- routes
def build_routes(cfg, g, pois, cable, cable_name, hfun):
    P = {p['n']: p['p'] for p in pois}
    if cable:
        P['索道下站'], P['索道上站'] = cable[0], cable[-1]
    routes, skipped, stats = [], [], {}
    for r in cfg['routes']:
        segs, fail = [], None
        for s in r['segs']:
            if s == 'CABLE':
                if not cable:
                    fail = {'from': '索道下站', 'to': '索道上站', 'reason': 'no aerialway in bbox'}
                    break
                segs.append({'from': '索道下站', 'to': '索道上站', 'mode': 'cable',
                             'via': [cable_name] if cable_name else [], 'p': cable})
                continue
            a, b = s
            if a not in P or b not in P:
                fail = {'from': a, 'to': b, 'reason': f'unknown point {a if a not in P else b}'}
                break
            try:
                segs.append(g.walk(P[a], P[b], a, b))
            except routing.RouteError as e:
                fail = {'from': a, 'to': b, 'reason': str(e)}
                break
        if fail:
            skipped.append({'route': r['id'], 'name': r['name'], **fail})
            continue
        st = [routing.seg_stats(s, hfun) for s in segs]
        stats[r['id']] = {'km': sum(x['dist'] for x in st), 'up': sum(x['up'] for x in st),
                          'walk_up': sum(x['up'] for x, s in zip(st, segs) if s['mode'] == 'walk')}
        routes.append({k: r[k] for k in ('id', 'name', 'tag', 'desc')} | {'segs': segs})
    return routes, skipped, stats


def difficulty(stats):
    km = max(s['km'] for s in stats.values()); up = max(s['walk_up'] for s in stats.values())   # cable climb is not hiking
    if km < 5 and up < 300:
        return '易'
    if km > 12 or up > 700:
        return '难'
    return '中'


def sub_line(bbox, W, H):
    lat0, lat1, lon0, lon1 = bbox
    return f'{lat0:.2f}–{lat1:.2f}°N · {lon0:.2f}–{lon1:.2f}°E · {W:.1f} × {H:.1f} km'


# ---------------------------------------------------------------- main
def build(site_id, out_root=OUT, log=print):
    cfg = sites_cfg.BY_ID[site_id]
    bbox = tuple(cfg['bbox'])
    lat0, lat1, lon0, lon1 = bbox
    latc = cfg.get('latc', (lat0 + lat1) / 2)
    W = round((lon1 - lon0) * 111.32 * math.cos(math.radians(latc)), 3)
    H = round((lat1 - lat0) * 110.57, 3)

    els = fetch.overpass(bbox)
    g = routing.Graph.from_osm(els, bbox, latc)
    Hh, NX, NY = height_grid(bbox, latc, W, H)
    hfun = make_hfun(Hh, NX, NY, W, H)

    trails, roads, cable, cable_osm = lines(els, bbox, g)
    if cable and hfun(*cable[0]) > hfun(*cable[-1]):
        cable = cable[::-1]                       # lower station first
    cable_name = cfg.get('cable_name') or cable_osm
    pois = site_pois(cfg, els, bbox, g)
    routes, skipped, stats = build_routes(cfg, g, pois, cable, cable_name, hfun)
    for s in skipped:
        log(f"  SKIP {s['route']}: {s['from']} -> {s['to']}: {s['reason']}")
    if not routes:
        raise RuntimeError(f'{site_id}: no routes could be built')
    default = cfg.get('defaultRoute')
    if default not in {r['id'] for r in routes}:
        default = routes[0]['id']

    q = np.round(Hh * 10).astype('<u2')
    exag = cfg.get('exag') or default_exag(float(Hh.max()), float(Hh.min()))
    data = {'id': site_id, 'name': cfg['name'], 'district': cfg['district'],
            'sub': sub_line(bbox, W, H), 'note': cfg.get('note', ''), 'desc': cfg.get('desc', {}),
            'exag': exag, 'defaultRoute': default,
            'W': W, 'H': H, 'NX': NX, 'NY': NY, 'bbox': list(bbox),
            'h': base64.b64encode(q.tobytes()).decode(),
            'trails': trails, 'roads': roads, 'cable': cable, 'pois': pois,
            'routes': routes, 'skipped': skipped}

    d = os.path.join(out_root, site_id)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'terrain.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    img = fetch.satellite(bbox, cfg.get('sat_z', 16), cfg.get('sat_max_side', 3000))
    img.save(os.path.join(d, 'satellite.jpg'), quality=84, optimize=True, progressive=True)
    th = img.copy(); th.thumbnail((480, 480))
    th.save(os.path.join(d, 'thumb.jpg'), quality=80, optimize=True)

    meta = make_meta(site_id, cfg, pois, hfun, Hh, routes, stats)
    with open(os.path.join(d, 'meta.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    write_sites_json(out_root)

    log(f"{site_id}: NX={NX} NY={NY} hmax={Hh.max():.0f} hmin={Hh.min():.0f} exag={exag} "
        f"trails={len(trails)} roads={len(roads)} cable={len(cable)} pois={len(pois)} "
        f"routes={len(routes)} skipped={len(skipped)} difficulty={meta['difficulty']}")
    for r in routes:
        s = stats[r['id']]
        log(f"  {r['id']:9s} {s['km']:5.2f} km  up {s['up']:4.0f} m (walk {s['walk_up']:4.0f} m)  segs {len(r['segs'])}")
    return data, meta


def inspect(site_id, bbox=None, log=print):
    """Fetch/cache OSM for the bbox and print graph components + named POI candidates (no output files)."""
    cfg = sites_cfg.BY_ID.get(site_id, {})
    bbox = tuple(bbox or cfg['bbox'])
    lat0, lat1, lon0, lon1 = bbox
    latc = cfg.get('latc', (lat0 + lat1) / 2) if cfg.get('bbox') and tuple(cfg['bbox']) == bbox else (lat0 + lat1) / 2
    els = fetch.overpass(bbox)
    extra = fetch.overpass_extra(bbox)
    g = routing.Graph.from_osm(els, bbox, latc)
    W = (lon1 - lon0) * 111.32 * math.cos(math.radians(latc)); H = (lat1 - lat0) * 110.57
    log(f'{site_id}: bbox={bbox} {W:.2f} x {H:.2f} km, {len(els)} + {len(extra)} elements, {len(g.XY)} graph nodes')
    sizes = {}
    for k, c in g.comp.items():
        sizes[c] = sizes.get(c, 0) + 1
    big = sorted(sizes.items(), key=lambda kv: -kv[1])
    log('components (id: nodes): ' + ', '.join(f'{c}:{n}' for c, n in big[:12])
        + (f' ... (+{len(big) - 12} smaller)' if len(big) > 12 else ''))
    seen, rows = set(), []
    for e in els + extra:
        tg = e.get('tags', {}); n = tg.get('name')
        k, cls = poi_kind(tg, e.get('type'))
        if not k:
            if n and ('登山' in n) and e.get('type') == 'node':
                k, cls = 'gate', 'gate'
            elif n and tg.get('natural') == 'water' and e.get('type') in ('way', 'relation'):
                k, cls = 'spot', 'water'
            elif n and tg.get('leisure') in ('park', 'garden', 'nature_reserve'):
                k, cls = 'spot', 'park'
            elif n and e.get('type') in ('way', 'relation') and ('门' in n or '入口' in n) and not tg.get('highway'):
                k, cls = 'gate', 'gate-area'
            else:
                continue
        c = _centroid(e)
        if not c or not (lat0 <= c[0] <= lat1 and lon0 <= c[1] <= lon1) or (n, cls) in seen:
            continue
        seen.add((n, cls))
        x, y = g.km(*c)
        if g.XY:
            nn = g.near((x, y)); snap = math.dist(g.XY[nn], (x, y)) * 1000; comp = g.comp[nn]
        else:
            snap, comp = float('nan'), -1
        rows.append((cls, n, tg.get('ele', ''), x, y, snap, comp, c))
    order = ['peak', 'gate', 'gate-area', 'attraction', 'viewpoint', 'reservoir', 'water', 'temple', 'park']
    rows.sort(key=lambda r: (order.index(r[0]), -_num(r[2]) if r[2] else 0, r[1]))
    log(f'{len(rows)} candidates  (class name ele x_km y_km snap_m comp lat lon)')
    for cls, n, ele, x, y, snap, comp, c in rows:
        log(f'  {cls:10s} {n:24s} {ele:>6s} {x:6.3f} {y:6.3f} {snap:6.0f} {comp:4d}  {c[0]:.5f} {c[1]:.5f}')
    return rows


def make_meta(site_id, cfg, pois, hfun, Hh, routes, stats):
    """List-card metadata. cfg['peak'] may be None (e.g. gardens): then peak and ele are null."""
    name = cfg.get('peak')
    ele = None
    if name:
        peak = next((p for p in pois if p['n'] == name), None)
        if peak and peak.get('ele'):
            ele = _num(peak['ele'])
        elif peak:   # DEM max within 300 m of the peak
            x, y = peak['p']
            ele = max(hfun(x + dx * .1, y + dy * .1) for dx in range(-3, 4) for dy in range(-3, 4))
        else:        # unknown peak name: whole-grid max
            ele = float(Hh.max())
        ele = int(ele) if float(ele).is_integer() else round(float(ele), 1)
    kms = [s['km'] for s in stats.values()]
    return {'id': site_id, 'name': cfg['name'], 'district': cfg['district'], 'peak': name or None,
            'ele': ele, 'routes': len(routes), 'km_range': [round(min(kms), 1), round(max(kms), 1)],
            'difficulty': difficulty(stats), 'thumb': f'site/{site_id}/thumb.jpg'}


def write_sites_json(out_root=OUT):
    order = {s['id']: i for i, s in enumerate(sites_cfg.SITES)}
    metas = []
    for p in glob.glob(os.path.join(out_root, '*', 'meta.json')):
        with open(p, encoding='utf-8') as f:
            metas.append(json.load(f))
    metas.sort(key=lambda m: (order.get(m['id'], 1e9), m['id']))
    with open(os.path.join(out_root, 'sites.json'), 'w', encoding='utf-8') as f:
        json.dump(metas, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    args = sys.argv[1:]
    if '--inspect' in args:
        args.remove('--inspect')
        bb = None
        if '--bbox' in args:
            i = args.index('--bbox'); bb = tuple(float(v) for v in args[i + 1].split(',')); del args[i:i + 2]
        if len(args) != 1 or (args[0] not in sites_cfg.BY_ID and not bb):
            sys.exit('usage: build_site.py <id> --inspect [--bbox lat0,lat1,lon0,lon1]')
        inspect(args[0], bb)
        sys.exit(0)
    if len(args) != 1:
        sys.exit('usage: build_site.py <id>|all')
    ids = [s['id'] for s in sites_cfg.SITES] if args[0] == 'all' else [args[0]]
    for i in ids:
        if i not in sites_cfg.BY_ID:
            sys.exit(f'unknown site {i}')
        build(i)
