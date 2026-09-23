## Methods

Comparison was performed on a real-world forest road polygon (2 features, ~3.5 ha, EPSG:3763) against three existing tools — Grass v.voronoi.skeleton, BecaGis Tools (Skeleton), MJ Centerline Extractor — and Road Centerline Extractor (the plugin under development, v2.0.0).

**Reference skeleton.** The source polygon was rasterized at 0.5 m resolution and reduced to a single-pixel-wide skeleton using a standard morphological thinning algorithm (`skimage.morphology.skeletonize`). This provides a ground truth independent of any of the four tools under comparison.

**Network coverage.** For each tool, every reference-skeleton pixel was tested against the tool's output; a pixel was considered covered if a line fell within 2 m of it. Coverage is reported as the percentage of reference pixels covered. This metric isolates completeness of processing from geometric accuracy: a tool that fails to generate output over part of a polygon scores low here regardless of how accurate its output is elsewhere.

**Centeredness.** A Euclidean distance transform was computed on the same raster, giving, for every interior pixel, its distance to the nearest polygon boundary. Each tool's output line was sampled at 1 m intervals; at each sample point, the distance-to-boundary value was compared against the local maximum of the same field within a 7 m window, taken as an estimate of the true medial-axis value for that cross-section. The mean ratio across all samples is reported as centeredness, where 100% indicates the line lies exactly on the corridor's geometric center and lower values indicate lateral offset toward one edge.

**Note.** A high score on one metric does not imply a high score on the other, so neither should be read in isolation. BecaGis Tools (Skeleton) illustrates this: it obtains the highest centeredness score (92.5%) alongside the lowest coverage (19.6%), indicating that its output is accurate only on the limited portion of the network it successfully processes.
