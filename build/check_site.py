"""Schema checker for built site packages.   Usage: python3 gz/check_site.py <id>|all"""
import base64, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out', 'site')
FIELDS = ('id', 'name', 'district', 'sub', 'note', 'desc', 'exag', 'defaultRoute', 'W', 'H', 'NX', 'NY',
          'bbox', 'h', 'trails', 'roads', 'cable', 'pois', 'routes', 'skipped')
MAX_BYTES = 6 * 1024 * 1024


def check_site(site_id, out_root=OUT):
    d = os.path.join(out_root, site_id)
    path = os.path.join(d, 'terrain.json')
    if not os.path.exists(path):
        return [f'{site_id}: terrain.json not found']
    try:
        with open(path, encoding='utf-8') as f:
            t = json.load(f)
    except ValueError as e:
        return [f'{site_id}: terrain.json is not valid JSON: {e}']
    errs = [f'{site_id}: missing field {k}' for k in FIELDS if k not in t]
    nx, ny = t.get('NX'), t.get('NY')
    for k, v in (('NX', nx), ('NY', ny)):
        if isinstance(v, int) and v > 400:
            errs.append(f'{site_id}: {k}={v} > 400')
    if isinstance(nx, int) and isinstance(ny, int) and 'h' in t:
        try:
            n = len(base64.b64decode(t['h']))
        except ValueError:
            n = -1
        if n != (nx + 1) * (ny + 1) * 2:
            errs.append(f'{site_id}: h length {n} bytes != (NX+1)*(NY+1)*2 = {(nx + 1) * (ny + 1) * 2}')
    for i, p in enumerate(t.get('pois', [])):
        if not (isinstance(p.get('p'), list) and len(p['p']) == 2):
            errs.append(f"{site_id}: poi #{i} {p.get('n')} missing p")
    ids = set()
    for r in t.get('routes', []):
        ids.add(r.get('id'))
        if not r.get('segs'):
            errs.append(f"{site_id}: route {r.get('id')} has no segments")
        for j, s in enumerate(r.get('segs') or []):
            if len(s.get('p') or []) < 2:
                errs.append(f"{site_id}: route {r.get('id')} seg {j} has < 2 points")
    if 'defaultRoute' in t and t.get('routes') and t['defaultRoute'] not in ids:
        errs.append(f"{site_id}: defaultRoute {t['defaultRoute']} is not a built route")
    if not os.path.exists(os.path.join(d, 'satellite.jpg')):
        errs.append(f'{site_id}: satellite.jpg not found')
    size = sum(os.path.getsize(os.path.join(d, f)) for f in os.listdir(d))
    if size > MAX_BYTES:
        errs.append(f'{site_id}: site dir is {size / 1048576:.2f} MB > 6 MB')
    return errs


def main(arg, out_root=OUT):
    if arg == 'all':
        ids = sorted(n for n in os.listdir(out_root) if os.path.isdir(os.path.join(out_root, n)))
    else:
        ids = [arg]
    errs = []
    for i in ids:
        e = check_site(i, out_root)
        d = os.path.join(out_root, i)
        size = sum(os.path.getsize(os.path.join(d, f)) for f in os.listdir(d)) if os.path.isdir(d) else 0
        print(f'{i}: ' + ('OK' if not e else f'{len(e)} error(s)') + f'  ({size / 1048576:.2f} MB)')
        for x in e:
            print('  ' + x)
        errs += e
    return errs


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('usage: check_site.py <id>|all')
    sys.exit(1 if main(sys.argv[1]) else 0)
