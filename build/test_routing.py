import math, os, sys
import pytest
sys.path.insert(0, os.path.dirname(__file__))
import routing
from routing import Graph, RouteError, seg_stats

BBOX = (23.0, 23.1, 113.0, 113.1)


def way(coords, hw='path', **tags):
    return {'type': 'way', 'tags': {'highway': hw, **tags},
            'geometry': [{'lat': la, 'lon': lo} for la, lo in coords]}


def grid_elements():
    # 3x3 grid, spacing 0.001 deg
    els = []
    for i in range(3):
        els.append(way([(23.05 + i * .001, 113.05 + j * .001) for j in range(3)], name='row%d' % i))
        els.append(way([(23.05 + j * .001, 113.05 + i * .001) for j in range(3)]))
    return els


def test_shortest_on_toy():
    g = Graph.from_osm(grid_elements(), BBOX)
    a = g.km(23.05, 113.05); b = g.km(23.052, 113.052)
    s = g.walk(a, b, 'A', 'B')
    assert s['mode'] == 'walk' and s['from'] == 'A' and s['to'] == 'B'
    assert s['snap'] == [0, 0]
    assert len(s['p']) == 5
    assert s['p'][0] == [round(a[0], 4), round(a[1], 4)]
    assert s['p'][-1] == [round(b[0], 4), round(b[1], 4)]


def test_disconnected_raises():
    els = grid_elements() + [way([(23.08, 113.08), (23.08, 113.081)])]
    g = Graph.from_osm(els, BBOX)
    with pytest.raises(RouteError, match='X.*Y'):
        g.walk(g.km(23.05, 113.05), g.km(23.08, 113.081), 'X', 'Y')


def test_far_snap_raises():
    g = Graph.from_osm(grid_elements(), BBOX)
    with pytest.raises(RouteError):
        g.walk(g.km(23.05, 113.05), g.km(23.06, 113.06), 'A', 'Far')


def test_filters_highway_and_private():
    els = [way([(23.05, 113.05), (23.05, 113.051)], hw='motorway'),
           way([(23.06, 113.05), (23.06, 113.051)], access='private')]
    assert len(Graph.from_osm(els, BBOX).XY) == 0


def test_stats_flat():
    seg = {'mode': 'walk', 'p': [[0, 0], [1, 0]]}
    s = seg_stats(seg, lambda x, y: 100.0)
    assert s['dist'] == pytest.approx(1.0)
    assert s['up'] == 0 and s['down'] == 0
    exp = 1 / (6 * math.exp(-3.5 * 0.05) * 0.85)
    assert s['time'] == pytest.approx(exp, rel=0.01)


def test_stats_cable():
    seg = {'mode': 'cable', 'p': [[0, 0], [1, 0]]}
    s = seg_stats(seg, lambda x, y: 0.0)
    assert s['time'] == pytest.approx(1000 / 2.5 / 3600, rel=0.01)


def test_stats_climb():
    seg = {'mode': 'walk', 'p': [[0, 0], [1, 0]]}
    s = seg_stats(seg, lambda x, y: 100 * x)
    assert s['up'] == pytest.approx(100, rel=0.05) and s['down'] == 0


def test_walk_end_point_not_near_duplicate():
    """A POI a fraction of a metre off its snap node must replace, not follow, the last vertex:
    near-coincident points + index-based smoothing gave absurd Tobler times (hours for ~1 m)."""
    g = Graph.from_osm(grid_elements(), BBOX)
    a = g.km(23.05, 113.05)
    bx, by = g.km(23.052, 113.052)
    s = g.walk(a, (bx + 0.0003, by), 'A', 'B')
    gaps = [math.dist(p, q) for p, q in zip(s['p'], s['p'][1:])]
    assert min(gaps) >= 0.008 - 1e-4
    assert s['p'][-1] == [round(bx + 0.0003, 4), round(by, 4)]


def test_via_length_weighted():
    # 0.008 deg unnamed path (80%) then 0.002 deg named road (20%), straight line west->east
    els = [way([(23.05, 113.050 + i * .001) for i in range(9)], hw='path'),
           way([(23.05, 113.058), (23.05, 113.059), (23.05, 113.060)], hw='tertiary', name='芙峰路')]
    g = Graph.from_osm(els, BBOX)
    s = g.walk(g.km(23.05, 113.05), g.km(23.05, 113.06), 'A', 'B')
    assert s['via'][0] == '山间小路'
    assert s['via'] == ['山间小路', '芙峰路']


def test_via_drops_small_share_and_unnamed_road():
    # 0.009 unnamed residential (90%) + 0.001 named path (10%, dropped)
    els = [way([(23.05, 113.050 + i * .001) for i in range(10)], hw='residential'),
           way([(23.05, 113.059), (23.05, 113.060)], hw='path', name='小径')]
    g = Graph.from_osm(els, BBOX)
    s = g.walk(g.km(23.05, 113.05), g.km(23.05, 113.06), 'A', 'B')
    assert s['via'] == ['无名道路']
