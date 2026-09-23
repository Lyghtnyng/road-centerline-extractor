# Road Centerline Extractor

A QGIS Processing algorithm that extracts clean, topologically segmented centerlines from corridor-shaped polygons — roads, rivers, or any similar elongated network represented as polygon geometry.

**Version 2.0.0** generalizes this plugin beyond roads and replaces the interactive dialog with a Processing Toolbox algorithm. See [Changelog](#changelog) below for what changed and why.

## What it does

Given a polygon layer, the algorithm computes a Voronoi-based skeleton and, optionally:

- **Segments at T-junctions and intersections**, so each section between two nodes is an individual feature, ready for per-segment classification (road class, surface type, etc.) without manual editing.
- **Prunes short spurious branches** below a configurable minimum length — a known artefact of Voronoi-based skeletonization near irregular boundary segments, not real network structure.
- **Filters out sections narrower than a minimum width**, excluding passing bays, local widenings, and other non-corridor artefacts.
- **Reports length per feature**, converted at generation time to the unit of choice (meters, kilometers, miles, feet).

All three optional steps are independent parameters — there is no separate "road mode" or "river mode". A river layer, for instance, would typically run with T-junction segmentation off and pruning/width thresholds tuned to its own scale.

Because it's implemented as a `QgsProcessingAlgorithm`, it's available from the Processing Toolbox, batch processing, Graphical Models, and the Python console — not only as a one-off interactive tool.

## Why

QGIS has no native tool for turning a corridor polygon into a segmented, network-aware centerline. Existing options in the ecosystem can extract a raw skeleton, but tend to break down on irregular or densely branching geometry, and none combine extraction with junction-aware segmentation, spur pruning, and width filtering in a single tool. See the benchmark below for a direct comparison.

## Benchmark

Tested against `Grass v.voronoi.skeleton`, `BecaGis Tools (Skeleton)`, and `MJ Centerline Extractor` on a real forest road polygon (2 features, ~3.5 ha). Two metrics were used:

- **Network coverage** — the percentage of a raster-derived reference skeleton (tool-agnostic ground truth) that each tool's output actually reaches, within a 2 m tolerance.
- **Centeredness** — how closely each output line tracks the true medial axis of the polygon, measured via a distance-transform comparison against the reference raster.

| Tool | Features | Total length | Network coverage | Centeredness |
|---|---|---|---|---|
| **Road Centerline Extractor** | 30 | 8,170 m | 99.9% | 91.4% |
| Grass v.voronoi.skeleton | 15 | 4,276 m | 50.5% | 90.7% |
| BecaGis Tools (Skeleton) | 2 | 1,691 m | 19.6% | 92.5% |
| MJ Centerline Extractor | 1 | 8,254 m | 100.0% | 86.7% |

Coverage and centeredness are independent — a high score on one does not imply a high score on the other. BecaGis Tools (Skeleton) illustrates this: its output is accurate on the small fraction of the network it manages to process (92.5% centeredness) but fails outright on the rest (19.6% coverage).

This plugin's centeredness (91.4%) sits within margin of the unprocessed, raw Voronoi skeleton (91.5% on the same data), indicating that segmentation, pruning, and trimming do not measurably degrade centering accuracy relative to the underlying extraction method. This was tested on a single dataset and would benefit from replication on other polygon geometries.

The figures above come from v1.x output, with tips extended to the polygon boundary. **v2.0.0 changes the default tip behavior**: dead-end tips are now left at the last genuine skeleton point instead of being stretched to the boundary (see "Extend tips to polygon boundary" in Changelog), which is a deliberate trade-off — on the same dataset, network coverage drops slightly (99.9% → 99.8%) while centeredness improves (91.4% → 91.5%), since the un-extended tip stays equidistant from the polygon walls that generated it rather than drifting toward one wall as it approaches an asymmetric corner. The old, full-coverage behavior remains available via that toggle; when enabled, an exact boundary-intersection fix (replacing the previous fixed-step sampling) further reduces the residual shortfall at narrow tapering tips, from 14 to 7 uncovered reference points out of 14,605 in testing. These figures are validated against the core algorithm directly; a full re-run through the v2.0.0 Processing algorithm inside QGIS is still pending.

Full methodology: [`docs/methodology.md`](docs/methodology.md).

## Installation

Search for **Road Centerline Extractor** in the QGIS Plugin Manager, or install manually from this repository.

## Usage

1. Open the Processing Toolbox (`Processing → Toolbox`).
2. Find **Road Centerline Extractor → Extract Centerlines**.
3. Select a polygon layer, set the parameters you need, and run — interactively, as a batch process, or from a Model.

## Parameters

| Parameter | Description |
|---|---|
| Input polygon layer | The corridor polygons to process. |
| Segment at T-junctions | If enabled, splits output into individual features at intersections. |
| Minimum width | Sections of the polygon narrower than this value are excluded from the output. Does not affect the shape or resolution of the extracted centerline — only which sections are kept. |
| Spur pruning length | Branches shorter than this length are removed. A width-relative safety floor (roughly one local polygon width) is always applied on top of this value. |
| Extend tips to polygon boundary | Off by default. When off, dead-end tips stop at the last genuine skeleton point (equidistant from the polygon walls). When on, tips are stretched to touch the polygon boundary exactly, maximizing coverage at a small cost to centering accuracy near the tip. |
| Output length unit | Unit used for the length attribute (m, km, mi, ft). |

## Requirements

The input layer must use a projected, metric CRS. Geographic CRS (degrees) are not supported, since width and pruning parameters are interpreted in the layer's map units.

## Changelog

**2.0.0**
- BREAKING: the interactive dialog has been removed. The plugin is now exposed exclusively as a Processing Toolbox algorithm, enabling batch processing, use in Graphical Models, and console access.
- Generalized beyond roads: works on any corridor-shaped polygon. No separate "road mode" — segmentation, pruning, and width filtering are independent parameters.
- Added: "Segment at T-junctions" toggle (previously always on).
- Added: "Extend tips to polygon boundary" toggle, off by default. Dead-end tips are left at the last genuine skeleton point (equidistant from the polygon walls) rather than stretched to the boundary — trading a little network coverage for centering accuracy that holds all the way to the tip. Enable it to restore full-coverage behavior.
- Added: a width-relative safety floor to spur pruning, on top of the existing length threshold — a branch shorter than roughly one local polygon width is now treated as skeleton noise regardless of the absolute setting.
- Fixed: input CRS is validated before running; geographic CRS are now rejected with a clear message instead of silently producing incorrect results.
- Fixed: processing can be cancelled cooperatively; the previous abrupt thread termination has been removed.
- Fixed: the minimum-width parameter's description no longer implies it affects skeleton resolution — it only filters which sections are kept.
- Fixed: endpoint extension (when enabled) now uses an exact boundary intersection instead of fixed-step sampling, reducing the shortfall previously left at narrow tapering tips.

**1.1.0 and earlier**
- Initial dialog-based releases.

## License

GNU General Public License v2 or later. See [`LICENSE`](LICENSE).
