# 广州徒步 3D（第一批）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把白云山单页改造成"列表入口 + 单地点 3D 视图"的多地点站点，并上线第一批 7 处城区近郊地点。

**Architecture:** Python 构建管线按站点配置生成 `site/<id>/terrain.json` + `site/<id>/satellite.jpg`，并汇总 `site/sites.json`。前端 `index.html` 无 hash 时显示列表，`#<id>` 时加载该地点（切换地点 = 改 hash + `location.reload()`，不做场景拆卸）。白云山数据迁入同一结构。

**Tech Stack:** Python 3.10 + numpy + Pillow；three.js r128（jsdelivr UMD）；Overpass（overpass-api.de / kumi.systems，带 UA）、AWS terrarium DEM、Esri World Imagery。

**Spec:** `gz/DESIGN.md`

（工作目录 = scratchpad；非 git 仓库，"Commit" 步骤改为把产物复制到 `gz/out/` 并在本地预览。）

## Global Constraints
- 每处 2–5 条路线，只用 OSM 真实路网；起终点吸附距离 > 150 m 的路段不得生成，改为在页面注明。
- 步速：Tobler `6*exp(-3.5*|slope+0.05|)*0.85` km/h；索道 2.5 m/s；步行大卡 `W*(0.55*km+0.0095*up_m+0.0025*down_m)`，索道 `W*1.3*h`。
- 卫星纹理长边 ≤ 3000 px，JPEG q84；高程网格每边 ≤ 400；单地点数据 ≤ 6 MB。
- 坐标系：km 框内 `x=(lon-LON0)*111.32*cos(latc)`，`y=(lat-LAT0)*110.57`；`h` 为 base64 Uint16（分米），row 0 = 南。
- 发布到原链接 https://claude.ai/artifact/1siKSN9VYjxVdBbWwLbtG3 ，单次发布 ≤ 64 MB。
- 界面文字全部中文；一屏布局不纵向滚动（≥960px）。

## Review Focus
1. 地点 bbox 内路网分成多块：路线两端落在不同连通块 → 构建报错并跳过该路段，而不是生成跨越空地的直线。（Task 2 测试 `test_disconnected_raises`）
2. hash 是未知 id 或空 → 显示列表，不报错。（Task 4 检查 `#nope`）
3. 地点没有索道 → 隐藏"索道"开关、无缆车厢，路线动画只用小公仔。（Task 4 检查火炉山页无 `tCable`）
4. 平缓地点（番禺丘陵类、华南植物园）高差小 → 夸张系数默认值随高差自适应，地形不至于"纸片"。（Task 3 `default_exag` 测试）
5. 外网瓦片/Overpass 偶发失败 → 下载带重试与本地缓存，重跑不重复下载。（Task 1 测试 `test_cache_hit`）

---

### Task 1: 通用数据抓取（DEM、卫星、OSM）带缓存

**Files:**
- Create: `gz/fetch.py`
- Test: `gz/test_fetch.py`

**Interfaces:**
- Produces:
  - `merc(lat, lon, z) -> (fx, fy)` 瓦片浮点坐标
  - `fetch_tile(url_tmpl, z, x, y, cache_dir) -> bytes`（3 次重试，命中缓存不发请求）
  - `dem(bbox, z=14) -> (np.ndarray heights_m, georef)`；`georef` 含 `x0,y0,z`
  - `satellite(bbox, z) -> PIL.Image`（已重采样为等经纬，长边 ≤ 3000）
  - `overpass(bbox) -> list[element]`，查询 highway 路网（含 geometry）、natural=peak、tourism=attraction|viewpoint、amenity=place_of_worship、named water、aerialway；结果缓存到 `gz/cache/osm_<hash>.json`

- [ ] Step 1: 写测试 `test_merc_known`（`merc(23.18,113.29,14)` 的整数部分 == (13347, 7106) 附近，与白云山已用的 x 13346–13349 / y 7104–7109 一致）、`test_cache_hit`（第二次调用不触发网络：monkeypatch urlopen 计数 == 1）。
- [ ] Step 2: `python3 -m pytest gz/test_fetch.py` → FAIL
- [ ] Step 3: 实现；terrarium 解码 `R*256+G+B/256-32768`，低于 0 截为 0。
- [ ] Step 4: 测试 PASS；对白云山 bbox 跑 `dem()`，最大值与旧 `big.npy` 相差 < 1 m。

### Task 2: 路网图与路线分析

**Files:**
- Create: `gz/routing.py`
- Test: `gz/test_routing.py`

**Interfaces:**
- Consumes: `overpass()` 元素
- Produces:
  - `Graph.from_osm(elements, bbox) -> Graph`（highway 集合与 `routes.py` 的 OK 相同；保留全部连通块，记录 `comp[node]`）
  - `Graph.walk(a_xy, b_xy, a_name, b_name) -> seg dict`（字段同现有：`from,to,mode='walk',via,p,snap`）；两端吸附 > 150 m 或不在同一连通块 → `raise RouteError`
  - `seg_stats(seg, hfun) -> dict(dist,up,down,time)`（与前端 `analyse` 同口径：10 m 采样、±3 平滑）

- [ ] Step 1: 测试 `test_shortest_on_toy`（3×3 网格图，最短路径节点序列正确）、`test_disconnected_raises`、`test_stats_flat`（平地 1 km：up=down=0，time ≈ 1/(6*exp(-0.175)*0.85) h ±1%）。
- [ ] Step 2: FAIL
- [ ] Step 3: 实现（从 `routes.py` 抽取，去掉全局变量与白云山硬编码）。
- [ ] Step 4: PASS；用新代码重算白云山 5 条路线，各段距离与现 `terrain3d.json` 相差 < 2%。

### Task 3: 站点构建器与配置

**Files:**
- Create: `gz/sites_cfg.py`（每处：`id,name,district,bbox,latc,peak,desc{},pois_extra[],routes[]`）
- Create: `gz/build_site.py`（CLI：`python3 gz/build_site.py <id>|all`）
- Create: `gz/check_site.py`
- Test: `gz/test_build.py`

**Interfaces:**
- Produces（`site/<id>/terrain.json`）：现有字段 `W,H,NX,NY,bbox,h,trails,roads,cable,pois,routes` + 新增 `id,name,district,sub,note,desc{名:[类,文]},exag,defaultRoute`。
- `site/sites.json`：`[{id,name,district,peak,ele,routes:int,km_range:[min,max],difficulty:'易'|'中'|'难',thumb}]`
- `default_exag(hmax, hmin) -> float`：高差 ≥ 300 m → 1.5；≤ 100 m → 3.0；之间线性。
- POI 自动选取：bbox 内有名峰、景点、观景台、寺庙、水库、名称含"门/入口"的节点，按 峰(有 ele) > 景点 > 门 排序，上限 40；`pois_extra` 可手工追加。

- [ ] Step 1: 测试 `test_default_exag`（(380,0)→1.5，(80,0)→3.0，(200,0)→2.25）、`test_schema`（构建白云山后 `check_site` 返回空错误列表）。
- [ ] Step 2: FAIL
- [ ] Step 3: 实现 builder；白云山配置复刻现有 5 条路线、索道、34 个 POI 与 DESC（从 index.html 移入 json）。
- [ ] Step 4: PASS；`check_site.py baiyun` 输出 OK，数据大小 ≤ 6 MB。

### Task 4: 前端改为列表 + 数据驱动视图

**Files:**
- Create: `gz/out/index.html`（由 `web3d/index.html` 改造）

**Interfaces:**
- Consumes: `site/sites.json`、`site/<id>/terrain.json`、`site/<id>/satellite.jpg`

- [ ] Step 1: 列表视图：卡片网格（名称、区、主峰海拔、路线数、距离范围、难度），点击 → `location.hash=id; location.reload()`；视图页头部加"← 全部地点"。
- [ ] Step 2: 去硬编码：标题/坐标/尺寸/说明/DESC/默认路线/夸张系数/`toLL` 的纬度全部取自 json；无 `cable` 时隐藏 `tCable` 并跳过缆车构建；DISP 去前缀改为去掉 `json.name` 前缀。
- [ ] Step 3: 本地预览 `python3 -m http.server 8765`（根 = `gz/out`），headless Chrome 截图：列表、`#baiyun`、`#nope`；三张均无控制台报错，`#baiyun` 与 Version 6 外观一致。

### Task 5: 第一批 7 处数据

**Files:**
- Modify: `gz/sites_cfg.py`（新增 huolu, fenghuang_th, longyandong, scbg, maofeng, tianlu, longtou）

- [ ] Step 1: 每处先 `build_site.py <id> --inspect`：输出连通块大小、候选入口/山顶 POI 列表。
- [ ] Step 2: 按经典线路为每处写 2–5 条路线（起点为公园门/入口，终点为主峰或环线），写简短 desc。
- [ ] Step 3: `build_site.py all && check_site.py all` → 全部 OK；记录 RouteError 被跳过的路段。
- [ ] Step 4: 每处截图人工检查：路线贴合卫星图上的山路、峰名位置正确。

### Task 6: 发布

- [ ] Step 1: 发布 `gz/out/index.html` + `site/**` 到原链接（files 映射；超 64 MB 分两次）。
- [ ] Step 2: 读回已发布页面确认列表含 8 处、任选 2 处可加载。
