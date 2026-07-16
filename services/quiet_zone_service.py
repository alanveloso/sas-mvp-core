"""Quiet-zone / FCC field-office registration gates (WINNF QPR)."""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

# National Radio Quiet Zone (NRAO / NRRO) — 47 CFR § 1.924(a) NAD-83 bounds.
NRQZ_NORTH = 39.0 + 15.0 / 60.0 + 0.4 / 3600.0  # 39°15′0.4″ N
NRQZ_SOUTH = 37.0 + 30.0 / 60.0 + 0.4 / 3600.0  # 37°30′0.4″ N
NRQZ_EAST = -(78.0 + 29.0 / 60.0 + 59.0 / 3600.0)  # 78°29′59.0″ W
NRQZ_WEST = -(80.0 + 29.0 / 60.0 + 59.2 / 3600.0)  # 80°29′59.2″ W

# QPR.6: registration rejected within 2.4 km of an FCC field office.
FCC_OFFICE_REG_RADIUS_KM = 2.4

_FCC_CSV = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "fcc"
    / "fcc_field_office_locations.csv"
)
_fcc_offices: list[dict[str, float]] | None = None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def _load_fcc_offices() -> list[dict[str, float]]:
    global _fcc_offices
    if _fcc_offices is not None:
        return _fcc_offices
    offices: list[dict[str, float]] = []
    if _FCC_CSV.is_file():
        with _FCC_CSV.open(newline="") as fh:
            for row in csv.reader(fh):
                if len(row) < 3:
                    continue
                try:
                    offices.append(
                        {"latitude": float(row[1]), "longitude": float(row[2])}
                    )
                except ValueError:
                    continue
    _fcc_offices = offices
    return offices


def in_nrao_nrro_quiet_zone(lat: float, lon: float) -> bool:
    return NRQZ_SOUTH <= lat <= NRQZ_NORTH and NRQZ_WEST <= lon <= NRQZ_EAST


def near_fcc_field_office(
    lat: float, lon: float, *, radius_km: float = FCC_OFFICE_REG_RADIUS_KM
) -> bool:
    for office in _load_fcc_offices():
        if _haversine_km(lat, lon, office["latitude"], office["longitude"]) <= radius_km:
            return True
    return False


def registration_blocked_by_quiet_zone(installation: dict[str, Any]) -> bool:
    """True when Registration must be rejected (QPR.2 / QPR.6)."""
    try:
        lat = float(installation["latitude"])
        lon = float(installation["longitude"])
    except (KeyError, TypeError, ValueError):
        return False
    if in_nrao_nrro_quiet_zone(lat, lon):
        return True
    if near_fcc_field_office(lat, lon):
        return True
    return False
