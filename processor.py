# Copyright (C) 2026 Roberto Geraldes <rob.filipe007@hotmail.com>
# Road Centerline Extractor - QGIS Plugin
# Licensed under GNU GPL v2 or later
import json
import numpy as np
from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY,
    QgsField, QgsVectorFileWriter, QgsCoordinateTransformContext
)
from qgis.PyQt.QtCore import QVariant

try:
    import networkx as nx
    from centerline.geometry import Centerline
    from shapely.geometry import shape, MultiLineString, LineString, Point
    from shapely.ops import nearest_points
except ImportError:
    pass


class CenterlineProcessor:
    def __init__(self, layer, output_path, spur_min_length, road_width,
                 unit_factor, unit_short, progress_callback=None):
        self.layer = layer
        self.output_path = output_path
        self.spur_min_length = spur_min_length
        self.road_width = road_width          # minimum road width in meters
        self.unit_factor = unit_factor
        self.unit_short = unit_short
        self.progress_callback = progress_callback

    def _report(self, percent, message=''):
        if self.progress_callback:
            self.progress_callback(percent, message)

    def _build_graph(self, lines):
        G = nx.Graph()
        for line in lines:
            coords = list(line.coords)
            for i in range(len(coords) - 1):
                p1 = coords[i]
                p2 = coords[i + 1]
                dist = np.hypot(p2[0] - p1[0], p2[1] - p1[1])
                if dist > 0:
                    G.add_edge(p1, p2, weight=dist)
        return G

    def _merge_graph_to_branches(self, G):
        G2 = nx.Graph()
        visited_edges = set()

        def edge_key(u, v):
            return (min(str(u), str(v)), max(str(u), str(v)))

        start_nodes = [n for n, d in G.degree() if d != 2]
        if not start_nodes:
            start_nodes = [list(G.nodes())[0]]

        for start in start_nodes:
            for neighbor in list(G.neighbors(start)):
                ek = edge_key(start, neighbor)
                if ek in visited_edges:
                    continue
                path = [start, neighbor]
                total_len = G[start][neighbor]['weight']
                visited_edges.add(ek)
                prev, current = start, neighbor
                while G.degree(current) == 2:
                    nxt = [n for n in G.neighbors(current) if n != prev]
                    if not nxt:
                        break
                    nxt = nxt[0]
                    ek2 = edge_key(current, nxt)
                    if ek2 in visited_edges:
                        break
                    total_len += G[current][nxt]['weight']
                    visited_edges.add(ek2)
                    path.append(nxt)
                    prev, current = current, nxt
                G2.add_edge(start, current, weight=total_len, path=path)
        return G2

    def _prune_spurs(self, G, min_len):
        changed = True
        while changed:
            changed = False
            leaves = [n for n, d in G.degree() if d == 1]
            for leaf in leaves:
                if leaf not in G:
                    continue
                nbrs = list(G.neighbors(leaf))
                if not nbrs:
                    continue
                nbr = nbrs[0]
                if G[leaf][nbr]['weight'] < min_len:
                    G.remove_edge(leaf, nbr)
                    if G.degree(leaf) == 0:
                        G.remove_node(leaf)
                    changed = True
        return G

    def _extend_endpoint(self, endpoint_coord, direction_coord, shapely_polygon, max_extension):
        ex, ey = endpoint_coord
        dx, dy = direction_coord
        seg_len = np.hypot(dx - ex, dy - ey)
        if seg_len == 0:
            return endpoint_coord
        ux = (ex - dx) / seg_len
        uy = (ey - dy) / seg_len
        best = endpoint_coord
        for t in np.linspace(0, max_extension, 80):
            candidate = Point(ex + ux * t, ey + uy * t)
            if shapely_polygon.contains(candidate):
                best = (ex + ux * t, ey + uy * t)
            else:
                break
        if best == endpoint_coord:
            boundary_pt = nearest_points(Point(ex, ey), shapely_polygon.boundary)[1]
            candidate = (boundary_pt.x, boundary_pt.y)
            dot = (candidate[0] - ex) * ux + (candidate[1] - ey) * uy
            if dot > 0:
                best = candidate
        return best

    def _local_width_at_point(self, point_coord, shapely_polygon):
        """
        Estimate the local width of the polygon at a given centerline point.
        Uses the inscribed circle radius: distance from the point to the
        nearest polygon boundary * 2 = approximate local width.
        """
        pt = Point(point_coord)
        dist_to_boundary = shapely_polygon.boundary.distance(pt)
        return dist_to_boundary * 2.0

    def _trim_path_by_width(self, path_coords, shapely_polygon, min_width):
        """
        Walk the path from both ends and trim any coordinates where the
        local polygon width is below min_width.
        Returns None if the entire path is too narrow.
        Also splits the path into valid sub-segments if a narrow section
        appears in the middle.
        """
        if len(path_coords) < 2:
            return []

        # Compute width at each point
        widths = [self._local_width_at_point(c, shapely_polygon) for c in path_coords]

        # Split path into sub-segments where width >= min_width
        segments = []
        current_seg = []
        for coord, w in zip(path_coords, widths):
            if w >= min_width:
                current_seg.append(coord)
            else:
                if len(current_seg) >= 2:
                    segments.append(current_seg)
                current_seg = []
        if len(current_seg) >= 2:
            segments.append(current_seg)

        return segments

    def run(self):
        crs = self.layer.crs().authid()
        total = self.layer.featureCount()
        field_name = f'length_{self.unit_short}'

        out_layer = QgsVectorLayer(f'LineString?crs={crs}', 'centerlines', 'memory')
        pr = out_layer.dataProvider()
        pr.addAttributes([
            QgsField('orig_id', QVariant.Int),
            QgsField(field_name, QVariant.Double)
        ])
        out_layer.updateFields()

        ok = 0
        skipped = 0
        self._report(0, f'Processing {total} polygon(s)...')
        self._report(0, f'Minimum road width filter: {self.road_width} m')

        for i, feat in enumerate(self.layer.getFeatures()):
            try:
                geom = feat.geometry()
                bbox = geom.boundingBox()
                max_ext = max(bbox.width(), bbox.height()) * 0.15

                geom_json = json.loads(geom.asJson())
                shapely_geom = shape(geom_json).buffer(0)

                if not shapely_geom.is_valid or shapely_geom.is_empty:
                    skipped += 1
                    continue

                # Use default interpolation (no road_width influence on skeleton quality)
                cl = Centerline(shapely_geom)
                cl_geom = cl.geometry

                if isinstance(cl_geom, LineString):
                    lines = [cl_geom]
                elif isinstance(cl_geom, MultiLineString):
                    lines = list(cl_geom.geoms)
                else:
                    try:
                        lines = list(cl_geom.geoms)
                    except Exception:
                        lines = [cl_geom]

                G_micro = self._build_graph(lines)
                if G_micro.number_of_edges() == 0:
                    skipped += 1
                    continue

                G_merged = self._merge_graph_to_branches(G_micro)
                if G_merged.number_of_edges() == 0:
                    skipped += 1
                    continue

                G_pruned = self._prune_spurs(G_merged, self.spur_min_length)
                if G_pruned.number_of_edges() == 0:
                    skipped += 1
                    continue

                leaf_nodes = {n for n, d in G_pruned.degree() if d == 1}

                for u, v, data in G_pruned.edges(data=True):
                    path_coords = list(data.get('path', [u, v]))
                    if len(path_coords) < 2:
                        continue

                    # Extend endpoints to polygon tips first
                    if path_coords[0] in leaf_nodes:
                        new_start = self._extend_endpoint(
                            path_coords[0], path_coords[1], shapely_geom, max_ext)
                        if new_start != path_coords[0]:
                            path_coords = [new_start] + path_coords
                    if path_coords[-1] in leaf_nodes:
                        new_end = self._extend_endpoint(
                            path_coords[-1], path_coords[-2], shapely_geom, max_ext)
                        if new_end != path_coords[-1]:
                            path_coords = path_coords + [new_end]

                    # Now trim/split by minimum road width.
                    # Any section where the polygon is narrower than min_width is removed.
                    valid_segments = self._trim_path_by_width(
                        path_coords, shapely_geom, self.road_width
                    )

                    for seg in valid_segments:
                        if len(seg) < 2:
                            continue
                        qgs_line = QgsGeometry.fromPolylineXY(
                            [QgsPointXY(x, y) for x, y in seg]
                        )
                        length_converted = round(qgs_line.length() * self.unit_factor, 4)
                        out_feat = QgsFeature()
                        out_feat.setGeometry(qgs_line)
                        out_feat.setAttributes([feat.id(), length_converted])
                        pr.addFeature(out_feat)

                ok += 1

            except Exception as e:
                skipped += 1
                self._report(int(i / total * 100), f'Skipped feature {feat.id()}: {str(e)}')

            pct = int((i + 1) / total * 95)
            if i % 5 == 0 or i == total - 1:
                self._report(pct, f'  Feature {i+1}/{total} — OK: {ok}, Skipped: {skipped}')

        self._report(96, 'Saving output file...')
        out_layer.updateExtents()

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = 'GPKG' if self.output_path.lower().endswith('.gpkg') else 'ESRI Shapefile'
        options.fileEncoding = 'UTF-8'

        error = QgsVectorFileWriter.writeAsVectorFormatV3(
            out_layer, self.output_path, QgsCoordinateTransformContext(), options
        )
        if error[0] != QgsVectorFileWriter.NoError:
            raise RuntimeError(f'Failed to save output file: {error[1]}')

        self._report(100, f'Done! Processed: {ok}, Skipped: {skipped}')
        return out_layer