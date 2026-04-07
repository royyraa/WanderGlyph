# WanderGlyph

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Made with ❤️](https://img.shields.io/badge/Made%20with-%E2%9D%A4-red.svg)](#)

<p align="center">
  <img src="png/logo.png" alt="WanderGlyph Logo" width="300"/>
</p>

**WanderGlyph** is a Python tool that turns your Google Timeline GPS export into a rich, interactive travel map — showing every U.S. county, state, or country you've ever visited, with activity trails, heatmaps, and year-over-year breakdowns.

---

## ✨ Features

- 🗺️ **County / State / Country** aggregation levels
- 🎨 **Three map themes** — Light, Dark, Satellite
- 🏠 **Home county highlight** — gold marker for your home base
- 🔥 **Heatmap** with colour gradient showing GPS density
- 🚶 **Activity segments** — walking, driving, cycling, transit, flying — each as a separate toggleable layer
- 📌 **Notable visits** — places you've stopped at
- 📅 **Year-over-year layers** — see how your travel grew over time
- 📱 **Recent GPS path** — your last 100 recorded points as a trail
- 📊 **Coverage statistics** — counties %, states, avg points per county
- 📋 **JSON summary report** — exportable stats file
- 📥 **Auto-download shapefiles** — no manual setup required
- ⚡ **Spatial join cache** — re-runs on the same file are instant
- 📁 **Multi-file / directory input** — combine multiple Timeline exports
- 📆 **Date range filtering** — isolate any time period
- 📱 **Mobile-friendly** — responsive layout, touch-optimised markers

---

## 📦 Requirements

- Python 3.10+
- Dependencies listed in [`requirements.txt`](./requirements.txt)
- A Google Timeline JSON export (see below)

---

## 🚀 Installation

```bash
git clone https://github.com/yourusername/wanderglyph.git
cd wanderglyph
pip install -r requirements.txt
```

Shapefiles (U.S. counties, states, world countries) are downloaded automatically on first run when you pass `--auto-download`. No manual setup needed.

---

## 📤 How to Export Your Google Timeline Data

1. Go to [Google Takeout](https://takeout.google.com/)
2. Deselect all, then select **Location History (Timeline)**
3. Choose **JSON** format and export
4. Extract the downloaded `.zip` — you'll find one or more `Timeline.json` files

---

## 📖 Usage

### Basic

```bash
python wanderglyph.py --json-file Timeline.json
```

### With options

```bash
python wanderglyph.py \
  --json-file Timeline.json \
  --theme dark \
  --home-county "Travis County, TX" \
  --add-markers \
  --open
```

### Multiple files or a whole directory

```bash
# Two files
python wanderglyph.py --json-file 2023.json 2024.json --theme dark

# Entire folder
python wanderglyph.py --json-file ~/Takeout/Location\ History/
```

### Filter by date range

```bash
python wanderglyph.py --json-file Timeline.json \
  --start-date 2024-01-01 --end-date 2024-12-31 \
  --theme light
```

### State or country level

```bash
# State level
python wanderglyph.py --json-file Timeline.json --level state

# World map (downloads world shapefile automatically)
python wanderglyph.py --json-file Timeline.json --level country \
  --auto-download --theme satellite
```

### Export extras

```bash
python wanderglyph.py --json-file Timeline.json \
  --export-geojson counties.geojson \
  --export-points  points.geojson \
  --summary        summary.json
```

---

## 🚩 Full CLI Reference

| Flag | Default | Description |
|---|---|---|
| `--json-file PATH [PATH ...]` | **required** | One or more JSON files, or a directory |
| `--output-map FILE` | `output_map.html` | Output HTML filename |
| `--project-dir DIR` | `.` | Directory for shapefiles |
| `--auto-download` | off | Download missing shapefiles automatically |
| `--start-date YYYY-MM-DD` | — | Only include points on/after this date |
| `--end-date YYYY-MM-DD` | — | Only include points on/before this date |
| `--level` | `county` | Aggregation level: `county` `state` `country` |
| `--theme` | `light` | Map theme: `light` `dark` `satellite` |
| `--home-county "Name, ST"` | — | Highlight home county in gold e.g. `"Travis County, TX"` |
| `--add-markers` | off | Add clustered GPS markers |
| `--export-geojson FILE` | — | Export matched regions as GeoJSON |
| `--export-points FILE` | — | Export GPS points as GeoJSON |
| `--summary FILE` | — | Write JSON summary report |
| `--open` | off | Open map in browser after generating |
| `--no-cache` | off | Skip cache, always recompute spatial join |
| `--clear-cache` | — | Delete all cached results and exit |
| `--verbose / -v` | off | Enable debug logging |

---

## 🎨 Color Scheme

### Map themes

| Theme | County fill | State borders | Base map |
|---|---|---|---|
| `light` | Blue `#3b82f6` | Red `#ef4444` | CartoDB Positron |
| `dark` | Teal `#2dd4bf` | Red `#ef4444` | CartoDB Dark Matter |
| `satellite` | Green `#34d399` | Red `#ef4444` | ESRI World Imagery |

### Activity segment colours (all themes)

| Activity | Colour |
|---|---|
| Walking / Running / Hiking | Green |
| Cycling | Orange |
| Driving / In vehicle | Blue |
| Train / Bus / Subway / Ferry | Purple |
| Flying | Red |
| Other | Grey |

### Special layers

| Layer | Colour |
|---|---|
| 🏠 Home county | Gold `#f59e0b` |
| 📌 Notable visits | Amber `#fbbf24` |
| 🔥 Heatmap | Blue → Orange → Red gradient |
| 📱 Recent path | Green |

---

## 🗂️ Project Structure

```
WanderGlyph/
├── wanderglyph.py        # CLI entry point
├── requirements.txt
├── src/
│   ├── core.py           # Orchestration
│   ├── data_loader.py    # JSON parsing, shapefile loading
│   ├── geo_utils.py      # Spatial join, home county lookup
│   ├── visualization.py  # Folium map generation
│   ├── coordinates.py    # Coordinate extraction
│   ├── cache.py          # Spatial join result caching
│   ├── downloader.py     # Auto-download shapefiles
│   └── summary.py        # JSON summary report
└── png/
    └── logo.png
```

---

## 📍 Example Output

- Interactive map of all visited counties / states / countries
- Heatmap of GPS point density
- Activity trails coloured by transport type
- Year-by-year point layers
- Coverage statistics panel

![usage](png/usage.png)

---

## 🛠️ Contributing

Fork → Branch → Commit → Push → PR 🚀

WanderGlyph is actively developed. Got a feature idea or bug report?  
Open an issue or reach out at **royyraa@outlook.com**

---

## 📄 License

This project is licensed under the [MIT License](./LICENSE).
