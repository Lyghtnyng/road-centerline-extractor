# Road Centerline Extractor

A QGIS plugin that converts road polygon layers into clean centerlines, with automatic segmentation at T-junctions and intersections.

## Features

- Extracts centerlines from road polygon layers
- Automatically segments output at T-junctions, allowing each road segment to be individually classified
- Spur pruning to remove skeleton artifacts
- Minimum road width filtering
- Length reporting in meters, kilometers, miles or feet

## Requirements

The following Python libraries are required:

- `centerline`
- `networkx`
- `shapely`

Install them in the QGIS Python Console:

```python
import subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "centerline", "networkx", "shapely"])
```

## Usage

1. Load a road polygon layer in QGIS
2. Open the plugin: **Plugins → Road Centerline Extractor**
3. Select the polygon layer
4. Set the minimum road width (meters)
5. Set the spur pruning length
6. Choose the output file
7. Click **Run**

## Author

Roberto Geraldes  
rob.filipe007@hotmail.com

## License

GNU General Public License v2 or later
