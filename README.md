# 广州徒步地形 hiking-roadmap

广州 19 处徒步地点的三维地形与路线演示（three.js）。纯静态站点，GitHub Pages 托管。

**在线地址**：https://saromchars.github.io/hiking-roadmap/

## 目录

- `docs/` — 发布到 GitHub Pages 的静态站点（Pages 源 = main 分支 `/docs`）。
  - `index.html` 单文件页面；`site/sites.json` 地点清单；`site/gzmap.json` + `site/gzrelief.jpg` 总览地图；`site/<id>/` 每处的 `terrain.json`、`satellite.jpg`、`thumb.jpg`、`meta.json`。
- `build/` — Python 构建管线。`build_site.py <id>|all` 生成单个地点；`build_map.py` 生成总览地图；产物默认写到 `build/out/`，需要再复制到 `docs/`。

## 重新构建

```bash
cd build
python3 -m pytest .          # 25 项测试
python3 build_site.py all    # 抓取 DEM/卫星/OSM 并生成全部地点（联网，带缓存）
python3 build_map.py         # 生成总览地图
```

## 数据来源

- 影像：Esri World Imagery
- 高程：AWS Terrain Tiles
- 地名、路网、区界：© OpenStreetMap 贡献者（ODbL）
