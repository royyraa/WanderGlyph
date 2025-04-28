# WanderGlyph

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
2. Install the dependencies:
   ```bash
   pip install -r requirements.txt
3. Download the required TIGER/Line shapefiles and place them in the appropriate directory.

## 📖 Usage

Analyze your GPS JSON data easily:

```bash
python wanderglyph.py --input your_data.json --output results/
```

Options:
- `--input`: Path to your JSON file containing GPS coordinates.
- `--output`: Directory where the generated maps and statistics will be saved.

See all available options and help:

```bash
python wanderglyph.py --help
```

---

## 📍 Example Outputs

- Interactive maps of visited counties
- Heatmaps illustrating point density
- Trajectory paths showcasing recent movements
- Statistics on county and state coverage

*(Add screenshots or demo images here!)*

---

## 🛠️ Contributing

Want to make Wanderglyph even better?

1. Fork the repository
2. Create a new branch:

    ```bash
    git checkout -b feature/YourFeature
    ```

3. Commit your changes:

    ```bash
    git commit -m "Add Your Feature"
    ```

4. Push to the branch:

    ```bash
    git push origin feature/YourFeature
    ```

5. Open a Pull Request

---

## 📄 License

This project is licensed under the [MIT License](./LICENSE).

---


