"""Manual check: rebuild Baiyun walk segments with gz.routing and compare to web3d/terrain3d.json."""
import json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fetch, routing

ROOT = os.path.dirname(HERE)
t = json.load(open(os.path.join(ROOT, 'web3d', 'terrain3d.json')))
bbox = tuple(t['bbox'])
g = routing.Graph.from_osm(fetch.overpass(bbox), bbox)
P = {p['n']: p['p'] for p in t['pois']}
P['索道下站'] = t['cable'][0]; P['索道上站'] = t['cable'][-1]
plen = lambda p: sum(math.dist(a, b) for a, b in zip(p, p[1:]))
worst = 0
for r in t['routes']:
    for s in r['segs']:
        if s['mode'] != 'walk':
            continue
        try:
            n = g.walk(P[s['from']], P[s['to']], s['from'], s['to'])
        except routing.RouteError as e:
            print(r['id'], 'ERROR', e); worst = 1; continue
        a, b = plen(s['p']), plen(n['p'])
        d = (b - a) / a; worst = max(worst, abs(d))
        print(f"{r['id']:9s} {s['from']}->{s['to']}: old {a:.3f} km new {b:.3f} km diff {d*100:+.2f}% snap {n['snap']} {'OK' if abs(d) < .02 else 'DIFF>2%'}")
print('worst', f'{worst*100:.2f}%')
