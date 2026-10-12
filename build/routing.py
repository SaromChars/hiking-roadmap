"""Path graph from OSM ways + route analysis (extracted from routes.py / web3d analyse())."""
import heapq, math
from collections import Counter

OK = {'path', 'footway', 'steps', 'track', 'service', 'tertiary', 'unclassified', 'residential',
      'pedestrian', 'living_street', 'tertiary_link'}
SNAP_MAX_KM = 0.150
PATH_HW = {'path', 'footway', 'steps', 'track'}
UNNAMED_PATH, UNNAMED_ROAD = '山间小路', '无名道路'
VIA_MIN_SHARE = 0.15


class RouteError(Exception):
    pass


def _key(p):
    return (round(p['lat'], 7), round(p['lon'], 7))


class Graph:
    def __init__(self, lat0, lon0, latc):
        self.lat0, self.lon0, self.latc = lat0, lon0, latc
        self.cos = math.cos(math.radians(latc))
        self.G = {}; self.XY = {}; self.NAME = {}; self.HW = {}; self.comp = {}

    def km(self, lat, lon):
        return ((lon - self.lon0) * 111.32 * self.cos, (lat - self.lat0) * 110.57)

    @classmethod
    def from_osm(cls, elements, bbox, latc=None):
        lat0, lat1, lon0, lon1 = bbox
        g = cls(lat0, lon0, (lat0 + lat1) / 2 if latc is None else latc)
        for e in elements:
            if e.get('type') != 'way':
                continue
            tg = e.get('tags', {}); hw = tg.get('highway')
            if hw not in OK or tg.get('access') in ('private', 'no'):
                continue
            geo = e.get('geometry')
            if not geo:
                continue
            pen = (1.0 if hw in ('path', 'footway', 'steps', 'track', 'pedestrian')
                   else 1.15 if hw in ('service', 'unclassified', 'tertiary') else 1.6)
            for a, b in zip(geo, geo[1:]):
                ka, kb = _key(a), _key(b)
                g.XY[ka] = g.km(*ka); g.XY[kb] = g.km(*kb)
                L = math.dist(g.XY[ka], g.XY[kb])
                g.G.setdefault(ka, []).append((kb, L * pen, L))
                g.G.setdefault(kb, []).append((ka, L * pen, L))
                g.HW[(ka, kb)] = g.HW[(kb, ka)] = hw
                if tg.get('name') and '？' not in tg['name']:
                    g.NAME[(ka, kb)] = g.NAME[(kb, ka)] = tg['name']
        g._components()
        return g

    def _components(self):
        n = 0
        for s in self.G:
            if s in self.comp:
                continue
            self.comp[s] = n; st = [s]
            while st:
                u = st.pop()
                for v, _, _ in self.G[u]:
                    if v not in self.comp:
                        self.comp[v] = n; st.append(v)
            n += 1

    def near(self, xy):
        x, y = xy
        return min(self.XY, key=lambda k: (self.XY[k][0] - x) ** 2 + (self.XY[k][1] - y) ** 2)

    def _dij(self, a, b):
        dist = {a: 0}; prev = {}; pq = [(0, a)]
        while pq:
            du, u = heapq.heappop(pq)
            if u == b:
                break
            if du > dist[u]:
                continue
            for v, w, _ in self.G[u]:
                nd = du + w
                if nd < dist.get(v, 1e18):
                    dist[v] = nd; prev[v] = u; heapq.heappush(pq, (nd, v))
        path = [b]
        while path[-1] != a:
            path.append(prev[path[-1]])
        return path[::-1]

    def _via(self, path):
        """Length-weighted way names of a leg: unnamed paths -> 山间小路, unnamed roads -> 无名道路;
        top 2 by length, each with share >= VIA_MIN_SHARE."""
        c = Counter()
        for u, v in zip(path, path[1:]):
            n = self.NAME.get((u, v))
            if not n:
                n = UNNAMED_PATH if self.HW.get((u, v)) in PATH_HW else UNNAMED_ROAD
            c[n] += math.dist(self.XY[u], self.XY[v])
        tot = sum(c.values())
        if tot <= 0:
            return []
        return [n for n, L in c.most_common(2) if L / tot >= VIA_MIN_SHARE]

    def walk(self, a_xy, b_xy, a_name, b_name):
        label = f'{a_name} -> {b_name}'
        if not self.XY:
            raise RouteError(f'{label}: empty graph')
        na, nb = self.near(a_xy), self.near(b_xy)
        snap = (math.dist(self.XY[na], a_xy), math.dist(self.XY[nb], b_xy))
        for nm, s in zip((a_name, b_name), snap):
            if s > SNAP_MAX_KM:
                raise RouteError(f'{label}: {nm} is {s * 1000:.0f} m from nearest path (max 150 m)')
        if self.comp[na] != self.comp[nb]:
            raise RouteError(f'{label}: endpoints are in different path components')
        path = self._dij(na, nb)
        pts = [list(a_xy)] + [list(self.XY[k]) for k in path] + [list(b_xy)]
        via = self._via(path)
        out = [pts[0]]
        for p in pts[1:]:
            if math.dist(p, out[-1]) > 0.008:
                out.append(p)
        if out[-1] != pts[-1]:
            if len(out) > 1 and math.dist(out[-1], pts[-1]) <= 0.008:
                out[-1] = pts[-1]          # avoid a near-duplicate final vertex (breaks slope/time)
            else:
                out.append(pts[-1])
        return {'from': a_name, 'to': b_name, 'mode': 'walk', 'via': via,
                'p': [[round(x, 4), round(y, 4)] for x, y in out],
                'snap': [round(s * 1000) for s in snap]}


def _densify(pts, step):
    out = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        m = max(1, math.ceil(math.hypot(x1 - x0, y1 - y0) / step))
        for t in range(m):
            out.append((x0 + (x1 - x0) * t / m, y0 + (y1 - y0) * t / m))
    out.append(tuple(pts[-1]))
    return out


def seg_stats(seg, hfun):
    """Mirror of web3d/index.html analyse(): 10 m resample, +-3 smoothing, Tobler (cable 2.5 m/s)."""
    pts = _densify(seg['p'], .01)
    raw = [hfun(x, y) for x, y in pts]
    n = len(raw)
    hs = []
    for i in range(n):
        w = raw[max(0, i - 3):min(n, i + 4)]
        hs.append(sum(w) / len(w))
    dist = up = down = tsec = 0.0
    for i in range(1, n):
        dd = math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
        dh = hs[i] - hs[i - 1]
        if seg.get('mode') == 'cable':
            tsec += math.hypot(dd * 1000, dh) / 2.5
        else:
            v = 6 * math.exp(-3.5 * abs((dh / (dd * 1000) if dd > 0 else 0) + .05)) * .85
            tsec += dd / v * 3600
        dist += dd
        if dh > 0: up += dh
        else: down -= dh
    return {'dist': dist, 'up': up, 'down': down, 'time': tsec / 3600}
