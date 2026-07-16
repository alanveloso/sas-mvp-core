"""Lightweight geospatial helpers (no GIS dependencies).

GeoJSON rings use [longitude, latitude] as required by RFC 7946.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

EARTH_RADIUS_M = 6_371_000.0


def is_point_in_polygon(
    lat: float, lng: float, polygon: Sequence[Sequence[float]]
) -> bool:
    """Ray-casting point-in-polygon.

    Args:
        lat: Point latitude (degrees).
        lng: Point longitude (degrees).
        polygon: Linear ring as [[lon, lat], ...] (GeoJSON order).
    """
    return _point_in_ring(lng, lat, polygon)


def _point_in_ring(lon: float, lat: float, ring: Sequence[Sequence[float]]) -> bool:
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = float(ring[i][0]), float(ring[i][1])
        xj, yj = float(ring[j][0]), float(ring[j][1])
        if ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-30) + xi
        ):
            inside = not inside
        j = i
    return inside


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _dist_point_segment_m(
    lat: float,
    lon: float,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Approximate distance from point to a great-circle segment (local projection)."""
    lat0 = math.radians(lat)

    def to_xy(la: float, lo: float) -> tuple[float, float]:
        return (
            (math.radians(lo) - math.radians(lon)) * math.cos(lat0) * EARTH_RADIUS_M,
            (math.radians(la) - math.radians(lat)) * EARTH_RADIUS_M,
        )

    ax, ay = to_xy(lat1, lon1)
    bx, by = to_xy(lat2, lon2)
    abx, aby = bx - ax, by - ay
    denom = abx * abx + aby * aby
    if denom == 0:
        return math.hypot(ax, ay)
    t = max(0.0, min(1.0, (-ax * abx + -ay * aby) / denom))
    return math.hypot(ax + t * abx, ay + t * aby)


def distance_to_ring_m(
    lat: float, lon: float, ring: Sequence[Sequence[float]]
) -> float:
    """Minimum distance (meters) from point to polygon ring; 0 if inside."""
    if _point_in_ring(lon, lat, ring):
        return 0.0
    if len(ring) < 2:
        return float("inf")
    best = float("inf")
    for i in range(len(ring) - 1):
        a, b = ring[i], ring[i + 1]
        d = _dist_point_segment_m(
            lat, lon, float(a[1]), float(a[0]), float(b[1]), float(b[0])
        )
        if d < best:
            best = d
    return best


def _ring_bbox(
    ring: Sequence[Sequence[float]],
) -> tuple[float, float, float, float] | None:
    if not ring:
        return None
    lons = [float(p[0]) for p in ring]
    lats = [float(p[1]) for p in ring]
    return min(lons), min(lats), max(lons), max(lats)


def _expand_bbox_m(
    bbox: tuple[float, float, float, float],
    meters: float,
    lat_ref: float,
) -> tuple[float, float, float, float]:
    min_lon, min_lat, max_lon, max_lat = bbox
    dlat = meters / 111_320.0
    cos_lat = max(0.2, abs(math.cos(math.radians(lat_ref))))
    dlon = meters / (111_320.0 * cos_lat)
    return min_lon - dlon, min_lat - dlat, max_lon + dlon, max_lat + dlat


def _in_bbox(
    lon: float, lat: float, bbox: tuple[float, float, float, float]
) -> bool:
    return bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]


def iter_geojson_rings(zone: dict[str, Any] | None) -> list[list[list[float]]]:
    """Extract outer rings from a GeoJSON FeatureCollection / Geometry."""
    if not zone:
        return []
    rings: list[list[list[float]]] = []

    def _from_geom(geom: dict[str, Any]) -> None:
        gtype = geom.get("type")
        coords = geom.get("coordinates") or []
        if gtype == "Polygon" and coords:
            rings.append(coords[0])
        elif gtype == "MultiPolygon":
            for poly in coords:
                if poly:
                    rings.append(poly[0])

    ztype = zone.get("type")
    if ztype == "FeatureCollection":
        for feature in zone.get("features") or []:
            geom = feature.get("geometry") or {}
            if isinstance(geom, dict):
                _from_geom(geom)
    elif ztype == "Feature":
        geom = zone.get("geometry") or {}
        if isinstance(geom, dict):
            _from_geom(geom)
    elif ztype in ("Polygon", "MultiPolygon"):
        _from_geom(zone)
    return rings


def point_in_geojson(lat: float, lon: float, zone: dict[str, Any] | None) -> bool:
    for ring in iter_geojson_rings(zone):
        if _point_in_ring(lon, lat, ring):
            return True
    return False


def distance_to_geojson_m(
    lat: float, lon: float, zone: dict[str, Any] | None
) -> float:
    """Minimum distance to any ring in the GeoJSON; 0 if inside."""
    best = float("inf")
    for ring in iter_geojson_rings(zone):
        bbox = _ring_bbox(ring)
        if bbox is not None:
            # Skip rings whose expanded bbox cannot be within ~1 km (speed).
            expanded = _expand_bbox_m(bbox, 1_000.0, lat)
            if not _in_bbox(lon, lat, expanded) and not _point_in_ring(lon, lat, ring):
                # Still need a lower bound — use corner distance as rough filter.
                corners = [
                    (bbox[1], bbox[0]),
                    (bbox[1], bbox[2]),
                    (bbox[3], bbox[0]),
                    (bbox[3], bbox[2]),
                ]
                rough = min(haversine_m(lat, lon, cla, clo) for cla, clo in corners)
                if rough > best:
                    continue
        d = distance_to_ring_m(lat, lon, ring)
        if d < best:
            best = d
            if best == 0.0:
                return 0.0
    return best


def within_geojson_buffer_m(
    lat: float,
    lon: float,
    zone: dict[str, Any] | None,
    buffer_m: float,
) -> bool:
    """True if point is inside zone or within buffer_m of its boundary."""
    if not zone:
        return False
    for ring in iter_geojson_rings(zone):
        bbox = _ring_bbox(ring)
        if bbox is not None:
            expanded = _expand_bbox_m(bbox, buffer_m + 5.0, lat)
            if not _in_bbox(lon, lat, expanded):
                continue
        if distance_to_ring_m(lat, lon, ring) <= buffer_m:
            return True
    return False
