# -----------------------------------------------------------------------
# Road Centerline Extractor - core geometry pipeline
#
# Pure shapely/networkx implementation, deliberately free of any QGIS or
# Qt imports so it can be tested outside QGIS. The QGIS Processing
# algorithm (algorithm.py) is a thin wrapper around this module.
#
# From v2.0.0, this replaces the pipeline previously embedded directly
# in processor.py (v1.x): same core logic (Voronoi skeleton -> graph ->
# branch merge -> spur pruning -> endpoint extension -> width-based
# trimming -> line merge), now exposed as a Processing algorithm instead
# of an interactive dialog, plus an exact-intersection fix to endpoint
# extension (previously approximated via fixed-step sampling, which
# could leave the line short of the polygon boundary at narrow,
# tapering dead-end tips).
#
# Copyright (C) 2026 Roberto Geraldes
# Licensed under the GNU General Public License v2 or later.
# -----------------------------------------------------------------------

import numpy as np
import networkx as nx
from centerline.geometry import Centerline
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import linemerge, unary_union, nearest_points


class ProcessingCanceled(Exception):
    """Raised internally when the caller requests cancellation."""


class CenterlineCore:
    """Extracts a cleaned centerline network from a single polygon.

    Parameters
    ----------
    spur_min_length : float
        Absolute floor: branches shorter than this are removed. 0
        disables the absolute floor (width-relative pruning, below,
        still applies).
    min_width : float
        Sections of the polygon narrower than this are excluded from
        the output. It does not affect the shape or resolution of the
        extracted centerline - only which sections are kept.
        0 disables the filter.
    extend_to_boundary : bool
        If True, dead-end tips are extended outward to touch the
        polygon boundary exactly, maximizing network coverage. If
        False (default), tips are left at the last genuine skeleton
        vertex, which is equidistant from the polygon walls that
        generated it - trading a small amount of coverage at each
        dead end for centering accuracy that holds all the way to the
        tip, instead of drifting toward one wall as the extension
        approaches an asymmetric corner.
    spur_width_ratio : float
        Safety floor for spur pruning, always applied in addition to
        spur_min_length: a leaf branch is also removed if it is
        shorter than this many times the local polygon width at its
        base. Genuine network branches are typically many widths
        long; branches on the order of one width or less are
        characteristic Voronoi noise near convergent tips (visible as
        a short spurious fork right at a dead end) rather than real
        structure, regardless of the absolute spur_min_length setting.
    is_canceled : callable, optional
        Zero-argument callable returning True when the caller wants to
        abort. Checked between pipeline stages; raises
        ProcessingCanceled when it fires.
    """

    def __init__(self, spur_min_length=9.0, min_width=4.0,
                 extend_to_boundary=False, spur_width_ratio=1.2,
                 is_canceled=None):
        self.spur_min_length = spur_min_length
        self.min_width = min_width
        self.extend_to_boundary = extend_to_boundary
        self.spur_width_ratio = spur_width_ratio
        self._is_canceled = is_canceled

    # -- cancellation ----------------------------------------------------

    def _check_canceled(self):
        if self._is_canceled is not None and self._is_canceled():
            raise ProcessingCanceled()

    # -- graph construction ---------------------------------------------

    def _build_graph(self, lines):
        graph = nx.Graph()
        for line in lines:
            coords = [(round(c[0], 4), round(c[1], 4)) for c in line.coords]
            for i in range(len(coords) - 1):
                p1 = coords[i]
                p2 = coords[i + 1]
                dist = np.hypot(p2[0] - p1[0], p2[1] - p1[1])
                if dist > 0 and p1 != p2:
                    graph.add_edge(p1, p2, weight=dist)
        return graph

    def _merge_graph_to_branches(self, graph):
        merged = nx.Graph()
        visited_edges = set()

        def edge_key(u, v):
            return (min(str(u), str(v)), max(str(u), str(v)))

        start_nodes = [n for n, d in graph.degree() if d != 2]
        if not start_nodes:
            start_nodes = [list(graph.nodes())[0]]

        for start in start_nodes:
            for neighbor in list(graph.neighbors(start)):
                ek = edge_key(start, neighbor)
                if ek in visited_edges:
                    continue
                path = [start, neighbor]
                total_len = graph[start][neighbor]['weight']
                visited_edges.add(ek)
                prev, current = start, neighbor
                while graph.degree(current) == 2:
                    nxt = [n for n in graph.neighbors(current) if n != prev]
                    if not nxt:
                        break
                    nxt = nxt[0]
                    ek2 = edge_key(current, nxt)
                    if ek2 in visited_edges:
                        break
                    total_len += graph[current][nxt]['weight']
                    visited_edges.add(ek2)
                    path.append(nxt)
                    prev, current = current, nxt
                merged.add_edge(start, current, weight=total_len, path=path)
        return merged

    def _prune_spurs(self, graph, min_len, shapely_polygon, width_ratio):
        changed = True
        while changed:
            changed = False
            leaves = [n for n, d in graph.degree() if d == 1]
            for leaf in leaves:
                if leaf not in graph:
                    continue
                nbrs = list(graph.neighbors(leaf))
                if not nbrs:
                    continue
                nbr = nbrs[0]
                edge_len = graph[leaf][nbr]['weight']
                threshold = min_len
                if width_ratio > 0:
                    local_width = self._local_width_at_point(
                        leaf, shapely_polygon)
                    threshold = max(threshold, local_width * width_ratio)
                if threshold > 0 and edge_len < threshold:
                    graph.remove_edge(leaf, nbr)
                    if graph.degree(leaf) == 0:
                        graph.remove_node(leaf)
                    changed = True
        return graph

    # -- endpoint extension ----------------------------------------------

    def _extend_endpoint(self, endpoint_coord, direction_coord,
                         shapely_polygon, max_extension):
        """Extend a dead-end tip outward to the polygon boundary.

        Casts a ray from the endpoint, away from the previous skeleton
        point, and takes its exact intersection with the polygon
        boundary - rather than sampling at fixed steps, which used to
        leave the line short of the true boundary by roughly one step
        length at narrow, tapering tips.
        """
        ex, ey = endpoint_coord
        dx, dy = direction_coord
        seg_len = np.hypot(dx - ex, dy - ey)
        if seg_len == 0:
            return endpoint_coord
        ux = (ex - dx) / seg_len
        uy = (ey - dy) / seg_len

        ray_len = max(max_extension, seg_len) * 4.0 + 1.0
        ray = LineString([(ex, ey), (ex + ux * ray_len, ey + uy * ray_len)])
        inter = ray.intersection(shapely_polygon.boundary)

        candidates = []
        if not inter.is_empty:
            geoms = inter.geoms if hasattr(inter, 'geoms') else [inter]
            for g in geoms:
                if isinstance(g, Point):
                    candidates.append(g)
                elif hasattr(g, 'coords'):
                    candidates.extend(Point(c) for c in g.coords)

        if candidates:
            # nearest crossing forward along the ray
            candidates.sort(
                key=lambda p: (p.x - ex) ** 2 + (p.y - ey) ** 2)
            nearest = candidates[0]
            t = (nearest.x - ex) * ux + (nearest.y - ey) * uy
            if 0 < t <= max_extension * 1.5:
                return (nearest.x, nearest.y)

        # Fallback for degenerate cases where the ray finds no crossing
        # (e.g. endpoint already effectively on the boundary).
        boundary_pt = nearest_points(
            Point(ex, ey), shapely_polygon.boundary)[1]
        candidate = (boundary_pt.x, boundary_pt.y)
        dot = (candidate[0] - ex) * ux + (candidate[1] - ey) * uy
        if dot > 0:
            return candidate
        return endpoint_coord

    # -- width filtering ---------------------------------------------------

    def _local_width_at_point(self, point_coord, shapely_polygon):
        """Approximate local polygon width at a centerline point.

        Distance from the point to the nearest polygon boundary, doubled
        (inscribed-circle diameter).
        """
        pt = Point(point_coord)
        return shapely_polygon.boundary.distance(pt) * 2.0

    def _trim_path_by_width(self, path_coords, shapely_polygon, min_width):
        """Split the path into sub-segments where local width >= min_width.

        Narrow sections are dropped; a narrow section in the middle of a
        path therefore splits it in two. Returns a list of coordinate
        lists (possibly empty).
        """
        if len(path_coords) < 2:
            return []
        if min_width <= 0:
            return [list(path_coords)]

        widths = [self._local_width_at_point(c, shapely_polygon)
                  for c in path_coords]

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

    # -- main entry point --------------------------------------------------

    def process_polygon(self, shapely_polygon):
        """Run the full pipeline on one polygon.

        Returns a list of shapely LineString parts (individual sections
        between junctions), or an empty list when nothing valid remains.
        Raises ProcessingCanceled if the caller requested cancellation.
        """
        shapely_polygon = shapely_polygon.buffer(0)
        if not shapely_polygon.is_valid or shapely_polygon.is_empty:
            return []

        minx, miny, maxx, maxy = shapely_polygon.bounds
        max_ext = max(maxx - minx, maxy - miny) * 0.15

        self._check_canceled()

        # Default interpolation. Note: min_width has no influence on the
        # skeleton shape or resolution; it is applied later as a filter.
        cl = Centerline(shapely_polygon)
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

        self._check_canceled()

        g_micro = self._build_graph(lines)
        if g_micro.number_of_edges() == 0:
            return []

        g_merged = self._merge_graph_to_branches(g_micro)
        if g_merged.number_of_edges() == 0:
            return []

        self._check_canceled()

        g_pruned = self._prune_spurs(
            g_merged, self.spur_min_length, shapely_polygon,
            self.spur_width_ratio)
        if g_pruned.number_of_edges() == 0:
            return []

        leaf_nodes = {n for n, d in g_pruned.degree() if d == 1}

        self._check_canceled()

        raw_lines = []
        for u, v, data in g_pruned.edges(data=True):
            path_coords = list(data.get('path', [u, v]))
            if len(path_coords) < 2:
                continue
            if self.extend_to_boundary:
                if path_coords[0] in leaf_nodes:
                    new_start = self._extend_endpoint(
                        path_coords[0], path_coords[1], shapely_polygon,
                        max_ext)
                    if new_start != path_coords[0]:
                        path_coords = [new_start] + path_coords
                if path_coords[-1] in leaf_nodes:
                    new_end = self._extend_endpoint(
                        path_coords[-1], path_coords[-2], shapely_polygon,
                        max_ext)
                    if new_end != path_coords[-1]:
                        path_coords = path_coords + [new_end]
            valid_segments = self._trim_path_by_width(
                path_coords, shapely_polygon, self.min_width)
            for seg in valid_segments:
                if len(seg) >= 2:
                    raw_lines.append(LineString(seg))

        if not raw_lines:
            return []

        self._check_canceled()

        multi = unary_union(raw_lines)
        try:
            merged = linemerge(multi)
        except Exception:
            merged = multi

        if isinstance(merged, LineString):
            parts = [merged]
        elif isinstance(merged, MultiLineString):
            parts = list(merged.geoms)
        else:
            parts = [merged]

        return [p for p in parts if not p.is_empty and p.length >= 0.1]
