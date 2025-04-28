# Wanderglyph

[![Python](https://img.shields.io/badge/Python-3.7%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Made with ❤️](https://img.shields.io/badge/Made%20with-%E2%9D%A4-red.svg)](#)

**Wanderglyph** is a Python toolkit for visualizing and analyzing GPS journeys with interactive maps, heatmaps, and detailed coverage summaries.

---

## ✨ Features

- 📍 Parse GPS coordinate data from JSON files
- 🗺️ Map coordinates to U.S. counties and states
- 🌐 Generate interactive web-based maps with:
  - Highlighted counties and GPS points
  - State boundaries
  - Heatmaps showing point density
  - Clustered location markers
  - Recent path trajectories
  - Coverage statistics and summaries

---

## 📦 Requirements

- Python 3.7+
- Packages listed in [`requirements.txt`](./requirements.txt)
- U.S. county and state shapefiles (TIGER/Line datasets from the [U.S. Census Bureau](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html))

---

## 🚀 Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/wanderglyph.git
   cd wanderglyph

