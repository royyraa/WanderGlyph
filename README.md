# Location Mapper

A Python toolkit for analyzing GPS data from JSON files, identifying the counties/states covered, and generating interactive maps.

## Features

- Parse GPS coordinate data from JSON files
- Map coordinates to counties and states (US)
- Generate interactive web-based maps with multiple layers:
  - Counties with points highlighted
  - State boundaries
  - Heatmap of point density
  - Clustered markers
  - Recent path trajectory
  - Coverage statistics

## Requirements

- Python 3.7+
- Required packages listed in `requirements.txt`
- County and State shapefiles (TIGER/Line from US Census Bureau)

## Installation

1. Clone this repository
2. Install dependencies:
