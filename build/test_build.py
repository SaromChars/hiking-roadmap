import base64, json, os, sys
import pytest
sys.path.insert(0, os.path.dirname(__file__))
import build_site, check_site
from build_site import default_exag, simplify


def test_default_exag():
    assert default_exag(380, 0) == pytest.approx(1.5)
    assert default_exag(80, 0) == pytest.approx(3.0)
    assert default_exag(200, 0) == pytest.approx(2.25)
    assert default_exag(1000, 600) == pytest.approx(1.5)


def test_simplify_drops_collinear():
    pts = [(0, 0), (1, 0.001), (2, 0), (2, 1)]
    assert simplify(pts, 0.012) == [(0, 0), (2, 0), (2, 1)]


def test_skipped_entry_carries_chinese_name():
    class StubGraph:
        def walk(self, *a):
            raise build_site.routing.RouteError('snap 300 m > 150 m')
    cfg = {'routes': [
        {'id': 'south', 'name': '南门登顶', 'tag': 't', 'desc': 'd', 'segs': [['甲', '乙']]},
        {'id': 'cable', 'name': '索道线', 'tag': 't', 'desc': 'd', 'segs': ['CABLE']},
        {'id': 'ghost', 'name': '幽灵线', 'tag': 't', 'desc': 'd', 'segs': [['甲', '丙']]}]}
    pois = [{'n': '甲', 'p': [0, 0]}, {'n': '乙', 'p': [1, 1]}]
    routes, skipped, stats = build_site.build_routes(cfg, StubGraph(), pois, [], None, None)
    assert routes == [] and stats == {}
    assert [(k['route'], k['name']) for k in skipped] == [('south', '南门登顶'), ('cable', '索道线'), ('ghost', '幽灵线')]
    assert all(k['reason'] for k in skipped)
    assert 'snap' in skipped[0]['reason'] and 'aerialway' in skipped[1]['reason'] and 'unknown point' in skipped[2]['reason']


def test_check_site_flags_errors(tmp_path):
    d = tmp_path / 'x'
    d.mkdir()
    bad = {'id': 'x', 'NX': 500, 'NY': 2, 'h': base64.b64encode(b'\0' * 4).decode(),
           'pois': [{'n': 'a'}], 'routes': [{'id': 'r', 'segs': []},
                                           {'id': 's', 'segs': [{'p': [[0, 0]]}]}]}
    (d / 'terrain.json').write_text(json.dumps(bad))
    errs = check_site.check_site('x', str(tmp_path))
    text = '\n'.join(errs)
    for frag in ('missing field', 'h length', 'NX', 'no segments', '< 2 points', 'missing p'):
        assert frag in text, frag


def test_schema(tmp_path):
    """Builds Baiyun from the warm cache into a temp dir; check_site must report no errors."""
    build_site.build('baiyun', str(tmp_path))
    assert check_site.check_site('baiyun', str(tmp_path)) == []
    t = json.load(open(tmp_path / 'baiyun' / 'terrain.json', encoding='utf-8'))
    names = {p['n'] for p in t['pois']}
    old = json.load(open(os.path.join(os.path.dirname(__file__), '..', 'web3d', 'terrain3d.json'),
                         encoding='utf-8'))
    assert {p['n'] for p in old['pois']} <= names
    assert [r['id'] for r in t['routes']] == ['south', 'cable', 'east', 'north', 'traverse',
                                              'west', 'meihua', 'kezi', 'wulong', 'wuxian', 'woshan', 'heshu', 'huangpo']
    assert t['defaultRoute'] == 'cable' and t['skipped'] == []
    assert t['exag'] == 1.5 and t['cable']
    sites = json.load(open(tmp_path / 'sites.json', encoding='utf-8'))
    assert sites[0]['id'] == 'baiyun' and sites[0]['thumb'] == 'site/baiyun/thumb.jpg'


def test_poi_kind_classification():
    k = build_site.poi_kind
    assert k({'name': '火炉山', 'natural': 'peak', 'ele': '323'}, 'node') == ('peak', 'peak')
    assert k({'name': '某峰', 'natural': 'peak', 'amenity': 'x'}, 'node') == (None, None)
    assert k({'name': '火炉山南门'}, 'node') == ('gate', 'gate')
    assert k({'name': '火炉山南门'}, 'way') == (None, None)          # gate areas are not point gates
    assert k({'name': '登山口', 'highway': 'trailhead'}, 'node') == ('gate', 'gate')
    assert k({'name': '观景台', 'tourism': 'viewpoint'}, 'node') == ('spot', 'viewpoint')
    assert k({'name': '某景点', 'tourism': 'attraction'}, 'way') == ('spot', 'attraction')
    assert k({'name': '能仁寺', 'amenity': 'place_of_worship'}, 'way') == ('spot', 'temple')
    assert k({'name': '某水库', 'water': 'reservoir'}, 'way') == ('spot', 'reservoir')
    assert k({'natural': 'peak'}, 'node') == (None, None)            # unnamed
    assert k({'name': '某路', 'highway': 'path'}, 'way') == (None, None)


def test_make_meta_peak_none_and_sites_json(tmp_path):
    import numpy as np
    Hh = np.array([[10.0, 20.0], [30.0, 140.0]])
    hfun = lambda x, y: 50.0
    pois = [{'n': '甲峰', 'p': [0.1, 0.1], 'k': 'peak', 'ele': '123'}]
    stats = {'a': {'km': 1.24, 'up': 30, 'walk_up': 30}, 'b': {'km': 3.86, 'up': 60, 'walk_up': 60}}
    routes = [{'id': 'a'}, {'id': 'b'}]
    cfg = {'name': '某植物园', 'district': '天河', 'peak': None}
    m = build_site.make_meta('garden', cfg, pois, hfun, Hh, routes, stats)
    assert m['peak'] is None and m['ele'] is None
    assert m['routes'] == 2 and m['km_range'] == [1.2, 3.9] and m['difficulty'] == '易'
    m2 = build_site.make_meta('hill', dict(cfg, peak='甲峰'), pois, hfun, Hh, routes, stats)
    assert m2['peak'] == '甲峰' and m2['ele'] == 123
    assert build_site.make_meta('dem', dict(cfg, peak='乙峰'), pois, hfun, Hh, routes, stats)['ele'] == 140
    for mm in (m, m2):
        d = tmp_path / mm['id']; d.mkdir()
        (d / 'meta.json').write_text(json.dumps(mm, ensure_ascii=False), encoding='utf-8')
    build_site.write_sites_json(str(tmp_path))
    sites = json.load(open(tmp_path / 'sites.json', encoding='utf-8'))
    assert {s['id']: s['peak'] for s in sites} == {'garden': None, 'hill': '甲峰'}
