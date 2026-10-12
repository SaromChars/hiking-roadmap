"""Batch 3b: 增城 (派潭) mountain sites. Same schema as gz/sites_cfg.py."""

SITES = [
    {
        'id': 'niuguzhang',
        'name': '牛牯嶂',
        'district': '增城',
        'bbox': (23.535, 23.590, 113.815, 113.885),
        'sat_z': 16,
        'peak': '牛牯嶂主峰',
        'exag': 1.2,   # ~1000 m relief: the 1.5 default looks needle-like
        'note': 'OSM 上的山径只通到次峰，主峰最后约 400 米没有标注路线，所以各条路线都止于次峰；DEM 精度约 30 m，山顶会被削平。',
        'desc': {
            # keys are display names: the viewer strips the site-name prefix (牛牯嶂主峰 -> 主峰)
            '主峰': ['牛牯嶂主峰', 'OSM 标注海拔 1084.3 米，是增城区内已标注的最高山峰之一。OSM 上没有通到主峰的路径，路线止于西南约 400 米的次峰。'],
            '次峰': ['牛牯嶂次峰', '主峰西南侧的次峰，OSM 标注海拔 1070 米。南坡几条山径在这里汇合。'],
            '灵山': ['登山起点', '南麓山脚的村落（OSM 标为灵山），南坡上山的路从这一带出发。'],
            '灵山水电站': ['水电站', '灵山村北侧山谷里的小水电站。'],
            '小猪兜水库': ['山间水库', '次峰正南方山腰上的水库，DEM 高程约 640 米，西线山径经过库边。'],
            '大猪兜水库': ['山间水库', '次峰东南方山腰上的水库，DEM 高程约 560 米，东线经过这里。'],
            '豆腐墩': ['山峰', '东南方向的小山头，标注海拔 544 米。'],
            '亚婆髻': ['山峰', '东南角的山峰，标注海拔 673 米。'],
            '马骝头顶': ['山峰', '牛牯嶂以西山脊上的山峰，标注海拔 820 米。'],
        },
        'poi_only': ['牛牯嶂主峰', '牛牯嶂次峰', '马骝头顶', '亚婆髻', '豆腐墩', '灵山', '灵山水电站', '小猪兜水库',
                     '大猪兜水库'],
        'pois_extra': [
            # OSM names 牛牯嶂（主）/牛牯嶂（次）; renamed because the viewer would strip them to "（主）"/"（次）"
            {'n': '牛牯嶂主峰', 'lat': 23.57112, 'lon': 113.85064, 'k': 'peak', 'ele': '1084.3'},
            {'n': '牛牯嶂次峰', 'lat': 23.56893, 'lon': 113.84744, 'k': 'peak', 'ele': '1070'},
            {'n': '灵山', 'lat': 23.54164, 'lon': 113.84166, 'k': 'gate'},
            {'n': '灵山水电站', 'lat': 23.54410, 'lon': 113.84336, 'k': 'spot'},
            # reservoirs: shore vertex closest to the path network
            {'n': '小猪兜水库', 'lat': 23.55800, 'lon': 113.84408, 'k': 'spot'},
            {'n': '大猪兜水库', 'lat': 23.55837, 'lon': 113.85417, 'k': 'spot'},
        ],
        'defaultRoute': 'west',
        'routes': [
            {'id': 'west', 'name': '小猪兜西线上次峰', 'tag': '南麓 · 西线',
             'desc': '从南麓灵山出发，经小猪兜水库沿南坡山径一路上到牛牯嶂次峰，几乎全程上坡。',
             'segs': [('灵山', '小猪兜水库'), ('小猪兜水库', '牛牯嶂次峰')]},
            {'id': 'east', 'name': '大猪兜东线上次峰', 'tag': '水景',
             'desc': '从灵山向北进山，经大猪兜水库上到牛牯嶂次峰。',
             'segs': [('灵山', '大猪兜水库'), ('大猪兜水库', '牛牯嶂次峰')]},
            {'id': 'loop', 'name': '双水库环线', 'tag': '环线 · 进阶',
             'desc': '灵山出发，经小猪兜水库上次峰，再经大猪兜水库下山回到灵山，爬升超过一千米。',
             'segs': [('灵山', '小猪兜水库'), ('小猪兜水库', '牛牯嶂次峰'), ('牛牯嶂次峰', '大猪兜水库'),
                      ('大猪兜水库', '灵山')]},
        ],
    },
    {
        'id': 'baishuizhai',
        'name': '白水寨风景名胜区',   # not '白水寨': the viewer would strip 白水寨山 -> 山
        'district': '增城',
        'bbox': (23.572, 23.618, 113.728, 113.800),
        'sat_z': 16,
        'exag': 1.2,   # ~990 m relief
        'peak': '白水寨山',
        'note': '右侧数字是 OpenStreetMap 标注的海拔，没有标注的取 DEM 高程（≈）；DEM 精度约 30 m，山顶会被削平，瀑布旁的台阶路和山径取自 OSM。',
        'desc': {
            '白水寨山': ['山峰', '天池东北侧的山峰，OSM 标注海拔 828 米，有山径从天池一带上来。'],
            '烧伤岭': ['山峰', '景区东北部的高峰，OSM 标注海拔 1009 米，与白水寨山之间有山径相连。'],
            '大尖山': ['山峰', '天池西北侧的山峰，标注海拔 879 米，OSM 上没有通往峰顶的路径。'],
            '风景名胜区(西南门)': ['西南门', '白水寨风景名胜区西南门一带，旁边是游客问询中心和地质公园博物馆。'],
            '广州增城地质公园博物馆': ['博物馆', '西南门旁的地质公园博物馆。'],
            '白水寨景区': ['瀑布 · 天梯', '白水寨以落差很大的瀑布闻名，瀑布旁有一段很长的登山台阶（俗称天梯），从谷底一直通到上方的天池。'],
            '仙姑天池': ['山顶湖', '瀑布上方山谷里的湖，DEM 高程约 600 米，天梯台阶的终点在湖边。'],
            '瀑布': ['瀑布', '东侧山谷里 OSM 标注的一处瀑布，东线山径从旁经过。'],
            '石马龙水库': ['水库', '西南门南侧的水库。'],
        },
        'poi_only': ['白水寨山', '烧伤岭', '大尖山', '风景名胜区(西南门)', '广州增城地质公园博物馆', '白水寨景区', '仙姑天池',
                     '瀑布', '石马龙水库'],
        'pois_extra': [
            {'n': '风景名胜区(西南门)', 'lat': 23.58192, 'lon': 113.75683, 'k': 'gate'},
            {'n': '广州增城地质公园博物馆', 'lat': 23.58372, 'lon': 113.75754, 'k': 'spot'},
            # water bodies: shore vertex closest to the path network
            {'n': '仙姑天池', 'lat': 23.59872, 'lon': 113.75335, 'k': 'spot'},
            {'n': '石马龙水库', 'lat': 23.57568, 'lon': 113.75633, 'k': 'spot'},
            # OSM has two nodes named 瀑布 in the eastern valley; the upper one is used
            {'n': '瀑布', 'lat': 23.59793, 'lon': 113.78387, 'k': 'spot'},
        ],
        'defaultRoute': 'tianti',
        'routes': [
            {'id': 'tianti', 'name': '瀑布天梯线', 'tag': '瀑布 · 台阶',
             'desc': '从西南门进景区，沿瀑布旁的台阶路（天梯）一路上到天池，台阶多、坡度陡。',
             'segs': [('风景名胜区(西南门)', '白水寨景区'), ('白水寨景区', '仙姑天池')]},
            {'id': 'summit', 'name': '天梯登白水寨山', 'tag': '登顶',
             'desc': '走天梯上到天池后，继续沿山径向东北登上白水寨山。',
             'segs': [('风景名胜区(西南门)', '白水寨景区'), ('白水寨景区', '仙姑天池'), ('仙姑天池', '白水寨山')]},
            {'id': 'east', 'name': '东谷登烧伤岭', 'tag': '东谷',
             'desc': '从西南门向东进入东侧山谷，经瀑布沿山径登上千米高的烧伤岭。',
             'segs': [('风景名胜区(西南门)', '瀑布'), ('瀑布', '烧伤岭')]},
            {'id': 'loop', 'name': '天池—烧伤岭大环线', 'tag': '环线 · 进阶',
             'desc': '西南门走天梯上天池，登白水寨山后沿山径向东到烧伤岭，再经东侧山谷的瀑布下山回到西南门。',
             'segs': [('风景名胜区(西南门)', '白水寨景区'), ('白水寨景区', '仙姑天池'), ('仙姑天池', '白水寨山'),
                      ('白水寨山', '烧伤岭'), ('烧伤岭', '瀑布'), ('瀑布', '风景名胜区(西南门)')]},
        ],
    },
]

# fenghuang_zc (凤凰山 748.3 m, 增城/从化交界, 23.5304,113.7113) is intentionally absent: OSM (checked
# 2026-10) has no path/track on the mountain -- the nearest mapped way of any kind is an unclassified
# village road ~740 m from the summit, so no real-path route can be built. Add it once trails are mapped.

# baijianghu (白江湖森林公园, 增城, ~23.511,113.892) is intentionally absent: OSM (checked 2026-10) maps
# no path/footway/steps there -- only unnamed access roads/tracks -- and no named place on that network
# (the lake itself is unnamed; the park polygon is ~400 m from the nearest way). The only named point
# near any way is 梳脑山 (680 m), on a separate network with no second named endpoint, so no real
# route between named places can be built. Add it once trails / named spots are mapped.
