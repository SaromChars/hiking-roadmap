# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

广州徒步地点的三维地形 + 路线演示站点（three.js r128 UMD，同源托管在 `docs/vendor/`——jsDelivr 在大陆约一半网络连不上，不要改回 CDN）。纯静态站点，GitHub Pages 从 main 分支 `/docs` 发布：https://www.saromchars.tech/hiking-roadmap/ 。界面文字全部为中文。

- `build/` — Python 3 构建管线（numpy + Pillow，无 requirements 文件），抓取 DEM / 卫星图 / OSM，生成每个地点的数据包。
- `docs/` — 发布产物：单文件 `index.html` + `site/` 数据。**构建产物默认写到 `build/out/site/`（已 gitignore），需要手动复制到 `docs/site/` 才会上线。**

## 常用命令

所有命令在 `build/` 目录下运行：

```bash
python3 -m pytest .                          # 全部测试
python3 -m pytest test_routing.py::test_disconnected_raises   # 单个测试
python3 build_site.py <id>                   # 构建单个地点（联网，带缓存）
python3 build_site.py all                    # 构建全部地点
python3 build_site.py <id> --inspect [--bbox lat0,lat1,lon0,lon1]   # 打印连通块与候选 POI，不写文件；配置新地点时先用它
python3 check_site.py <id>|all               # 校验 build/out/site 下产物的 schema 与体积
python3 build_map.py                         # 生成总览地图 gzmap.json + gzrelief.jpg（须在 build_site 之后）
cp -R out/site/. ../docs/site/               # 发布产物
```

本地预览：`python3 -m http.server -d docs 8765`，打开 `/`（列表）或 `/#<id>`（单个地点）。

测试说明：
- `test_fetch.py` / `test_routing.py` 通过 monkeypatch `urllib.request.urlopen` 离线运行。
- `test_build.py::test_schema` 会真实构建白云山（依赖 `build/cache/` 已有缓存，否则联网），并读取 `../web3d/terrain3d.json` —— 该旧文件不在本仓库中，所以这个测试在本仓库里会失败；`check_baiyun_routes.py` 同样依赖它。
- 缓存目录可用环境变量 `GZ_CACHE` 覆盖（默认 `build/cache/`）。

## 架构

数据流：`sites_cfg.py`（配置）→ `fetch.py`（下载 + 磁盘缓存）→ `routing.py`（OSM 路网图 + Dijkstra）→ `build_site.py`（组装 JSON / 图片）→ `check_site.py`（校验）→ `docs/index.html`（按需 fetch 渲染）。

**站点配置**：`sites_cfg.py` 定义 `SITES` 列表（字段说明见其模块 docstring），并在文件末尾自动 import 同目录所有 `sites_*.py`（按文件名顺序追加各自的 `SITES`）。新增一批地点 = 新建 `sites_<group>.py`，不要改动其他批次文件。`SITES` 的顺序决定列表页 `sites.json` 的顺序。路线段 `(from_name, to_name)` 按 POI 名称解析（另有 `索道下站`/`索道上站`），字符串 `'CABLE'` 表示索道段。

**产物**（每个地点 `site/<id>/`）：`terrain.json`（地形网格 + 路网 + POI + 路线）、`satellite.jpg`、`thumb.jpg`、`meta.json`；`site/sites.json` 由所有 `meta.json` 汇总而成。

**前端**：`docs/index.html` 无 hash 时显示列表 + 总览地图；`#<id>` 时加载该地点；未知 id 回退到列表。切换地点 = 改 hash + `location.reload()`（不做场景拆卸）。页面完全由 `terrain.json` 驱动，没有 `cable` 时隐藏索道开关与缆车。

## 关键约束（改动构建或前端时需保持一致）

- **路线只用 OSM 真实路网，不编造。** 起终点吸附 > 150 m 或两端不在同一连通块 → `RouteError`，该路段被跳过并记入 `skipped`（前端注明），而不是画直线。整个地点建不出任何路线时报错。例：龙头山因 OSM 无山径被刻意排除（见 `sites_cfg.py` 末尾注释）。
- 坐标系：bbox 一律为 `(lat0, lat1, lon0, lon1)`；km 坐标 `x=(lon-lon0)*111.32*cos(latc)`，`y=(lat-lat0)*110.57`。`h` 为 base64 的小端 Uint16（单位分米），row 0 = 南。
- 体积上限：高程网格每边 ≤ 400；卫星图长边 ≤ 3000 px（JPEG q84）；单个地点目录 ≤ 6 MB（`check_site` 会检查）。
- 计算口径前后端一致：Tobler 步速 `6*exp(-3.5*|slope+0.05|)*0.85` km/h；索道 2.5 m/s；步行大卡 `W*(0.55*km+0.0095*上升m+0.0025*下降m)`；距离统计按 10 m 采样、±3 点平滑。
- 地形夸张系数 `default_exag`：高差 ≥ 300 m → 1.5，≤ 100 m → 3.0，中间线性；配置里可用 `exag` 覆盖。
- 数据来源署名：Esri World Imagery、AWS Terrain Tiles、© OpenStreetMap 贡献者（ODbL）。

## 历史文档

`build/DESIGN.md`（设计意图与目标）和 `build/PLAN.md`（第一批实施计划）写于迁入本仓库之前：其中的 `gz/` 路径对应现在的 `build/`，`web3d/` 和 Artifact 发布链接已不再适用（现在通过 GitHub Pages 发布）。代码 docstring 里的 `gz/...` 也是同样的旧路径。
