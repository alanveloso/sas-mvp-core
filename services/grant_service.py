"""Grant business logic aligned with WINNF_FT_S_GRA expectations (MVP simulation)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from models.models import BlacklistedFccId, Cbsd, FccIdRecord, Grant
from services.spectrum_inquiry_service import (
    CBRS_HIGH_HZ,
    CBRS_LOW_HZ,
    _load_injected,
    _overlaps,
    _pal_freq,
    _point_in_geojson,
)

SUCCESS = 0
BLACKLISTED = 101
MISSING_PARAM = 102
INVALID_PARAM = 103
UNSUPPORTED_SPECTRUM = 300
INTERFERENCE = 400
GRANT_CONFLICT = 401

HEARTBEAT_INTERVAL_SEC = 60
DEFAULT_GRANT_DAYS = 7
CAT_A_MAX_EIRP_10MHZ = 30.0
CAT_B_MAX_EIRP_10MHZ = 47.0


def _resp(code: int, *, cbsd_id: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"response": {"responseCode": code}}
    if cbsd_id is not None:
        out["cbsdId"] = cbsd_id
    return out


def _cbsd_reg(cbsd: Cbsd) -> dict[str, Any]:
    try:
        return json.loads(cbsd.registration_json or "{}")
    except json.JSONDecodeError:
        return {}


def _cbsd_location(cbsd: Cbsd) -> tuple[float | None, float | None]:
    inst = _cbsd_reg(cbsd).get("installationParam") or {}
    lat, lon = inst.get("latitude"), inst.get("longitude")
    if lat is None or lon is None:
        return None, None
    return float(lat), float(lon)


def _max_allowed_eirp_mhz(cbsd: Cbsd, fcc_max_eirp: float) -> float:
    """WINNF: maxEirp is dBm/MHz; category limits are dBm/10 MHz."""
    reg = _cbsd_reg(cbsd)
    cat = (reg.get("cbsdCategory") or cbsd.cbsd_category or "A").upper()
    default = CAT_A_MAX_EIRP_10MHZ if cat == "A" else CAT_B_MAX_EIRP_10MHZ
    caps = [default, float(fcc_max_eirp)]
    eirp_cap = (reg.get("installationParam") or {}).get("eirpCapability")
    if eirp_cap is not None:
        caps.append(float(eirp_cap))
    return min(caps) - 10.0


def _parse_freq(
    op: dict[str, Any] | None,
) -> tuple[int | None, int | None, int | None]:
    """Return (error_code, low, high). error_code set on failure."""
    if op is None:
        return MISSING_PARAM, None, None
    freq = op.get("operationFrequencyRange")
    if not isinstance(freq, dict):
        return MISSING_PARAM, None, None
    if "lowFrequency" not in freq or "highFrequency" not in freq:
        return MISSING_PARAM, None, None
    low, high = freq.get("lowFrequency"), freq.get("highFrequency")
    if low is None or high is None:
        return MISSING_PARAM, None, None
    try:
        low_i, high_i = int(low), int(high)
    except (TypeError, ValueError):
        return INVALID_PARAM, None, None
    if high_i <= low_i:
        return INVALID_PARAM, None, None
    # Fully or partially outside CBRS → 300.
    if low_i < CBRS_LOW_HZ or high_i > CBRS_HIGH_HZ:
        return UNSUPPORTED_SPECTRUM, None, None
    return None, low_i, high_i


def _active_grants(db: Session, cbsd_id: str) -> list[Grant]:
    return (
        db.query(Grant)
        .filter_by(cbsd_id=cbsd_id, terminated=False)
        .all()
    )


def _has_freq_conflict(
    existing: list[Grant],
    low: int,
    high: int,
    *,
    also_pending: list[tuple[int, int]] | None = None,
) -> bool:
    for g in existing:
        if _overlaps(g.low_frequency, g.high_frequency, low, high):
            return True
    for plow, phigh in also_pending or []:
        if _overlaps(plow, phigh, low, high):
            return True
    return False


def _ppa_pal_context(
    db: Session, cbsd: Cbsd
) -> list[dict[str, Any]]:
    """Return list of {low, high, in_cluster, in_ppa, license_exp} for linked PPAs."""
    lat, lon = _cbsd_location(cbsd)
    pals = _load_injected(db, "pal")
    zones = _load_injected(db, "zone")
    pal_by_id = {p.get("palId"): p for p in pals if p.get("palId")}
    contexts: list[dict[str, Any]] = []

    for zone_payload in zones:
        record = zone_payload.get("record") or zone_payload
        if record.get("usage") != "PPA" and "ppaInfo" not in record:
            continue
        ppa_info = record.get("ppaInfo") or {}
        cluster = set(ppa_info.get("cbsdReferenceId") or [])
        in_cluster = cbsd.cbsd_id in cluster
        in_ppa = False
        if lat is not None and lon is not None:
            in_ppa = _point_in_geojson(lat, lon, record.get("zone"))

        for pal_id in ppa_info.get("palId") or []:
            pal = pal_by_id.get(pal_id)
            if not pal:
                continue
            pf = _pal_freq(pal)
            if not pf:
                continue
            license_exp = (pal.get("license") or {}).get("licenseExpiration")
            contexts.append(
                {
                    "low": pf[0],
                    "high": pf[1],
                    "in_cluster": in_cluster,
                    "in_ppa": in_ppa,
                    "license_exp": license_exp,
                }
            )
    return contexts


def _resolve_channel(
    contexts: list[dict[str, Any]], low: int, high: int
) -> tuple[int | None, str | None, datetime | None]:
    """
    Return (error_code, channel_type, pal_license_exp).
    error_code None means OK.
    """
    covering_pal: list[dict[str, Any]] = []
    overlapping_pal: list[dict[str, Any]] = []
    for ctx in contexts:
        if _overlaps(low, high, ctx["low"], ctx["high"]):
            overlapping_pal.append(ctx)
            if low >= ctx["low"] and high <= ctx["high"]:
                covering_pal.append(ctx)

    # Inside claimed PPA but not in cluster → interference on PAL overlap.
    for ctx in overlapping_pal:
        if ctx["in_ppa"] and not ctx["in_cluster"]:
            return INTERFERENCE, None, None

    # Mix of PAL + GAA: request overlaps PAL for cluster member but not fully inside.
    for ctx in overlapping_pal:
        if ctx["in_cluster"] and not (low >= ctx["low"] and high <= ctx["high"]):
            return INVALID_PARAM, None, None

    if covering_pal:
        for ctx in covering_pal:
            if ctx["in_cluster"]:
                exp = None
                if ctx.get("license_exp"):
                    try:
                        exp = datetime.strptime(
                            ctx["license_exp"], "%Y-%m-%dT%H:%M:%SZ"
                        )
                    except (TypeError, ValueError):
                        exp = None
                return None, "PAL", exp
        # Fully inside a PAL channel but not authorized → interference.
        return INTERFERENCE, None, None

    return None, "GAA", None


def _grant_expire_time(pal_license_exp: datetime | None) -> datetime:
    default = datetime.utcnow() + timedelta(days=DEFAULT_GRANT_DAYS)
    if pal_license_exp is None:
        return default
    # Must be ≤ PAL licenseExpiration (GRA.13).
    return min(default, pal_license_exp)


def process_grant(db: Session, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    responses: list[dict[str, Any]] = []
    # Frequencies approved earlier in this same batch (conflict within batch).
    pending_by_cbsd: dict[str, list[tuple[int, int]]] = {}

    for req in requests:
        cbsd_id = req.get("cbsdId")
        if not cbsd_id:
            responses.append(_resp(MISSING_PARAM))
            continue

        cbsd = db.query(Cbsd).filter_by(cbsd_id=cbsd_id).first()
        if not cbsd:
            # Unknown CBSD → 103 without echoing cbsdId (GRA.3).
            responses.append(_resp(INVALID_PARAM))
            continue

        if db.query(BlacklistedFccId).filter_by(fcc_id=cbsd.fcc_id).first():
            responses.append(_resp(BLACKLISTED, cbsd_id=cbsd_id))
            continue

        op = req.get("operationParam")
        if not isinstance(op, dict):
            responses.append(_resp(MISSING_PARAM, cbsd_id=cbsd_id))
            continue
        if "maxEirp" not in op or op.get("maxEirp") is None:
            responses.append(_resp(MISSING_PARAM, cbsd_id=cbsd_id))
            continue

        freq_err, low, high = _parse_freq(op)
        if freq_err is not None:
            responses.append(_resp(freq_err, cbsd_id=cbsd_id))
            continue
        assert low is not None and high is not None

        try:
            max_eirp = float(op["maxEirp"])
        except (TypeError, ValueError):
            responses.append(_resp(INVALID_PARAM, cbsd_id=cbsd_id))
            continue

        fcc = db.query(FccIdRecord).filter_by(fcc_id=cbsd.fcc_id).first()
        fcc_max = float(fcc.fcc_max_eirp) if fcc else CAT_B_MAX_EIRP_10MHZ
        if max_eirp > _max_allowed_eirp_mhz(cbsd, fcc_max):
            responses.append(_resp(INVALID_PARAM, cbsd_id=cbsd_id))
            continue

        contexts = _ppa_pal_context(db, cbsd)
        ch_err, channel_type, pal_exp = _resolve_channel(contexts, low, high)
        if ch_err is not None:
            responses.append(_resp(ch_err, cbsd_id=cbsd_id))
            continue
        assert channel_type is not None

        existing = _active_grants(db, cbsd_id)
        pending = pending_by_cbsd.get(cbsd_id, [])
        if _has_freq_conflict(existing, low, high, also_pending=pending):
            responses.append(_resp(GRANT_CONFLICT, cbsd_id=cbsd_id))
            continue

        grant_id = f"grant/{uuid.uuid4().hex}"
        expire = _grant_expire_time(pal_exp)
        db.add(
            Grant(
                grant_id=grant_id,
                cbsd_pk=cbsd.id,
                cbsd_id=cbsd_id,
                channel_type=channel_type,
                low_frequency=low,
                high_frequency=high,
                max_eirp=max_eirp,
                grant_expire_time=expire,
                heartbeat_interval=HEARTBEAT_INTERVAL_SEC,
                grant_json=json.dumps(req),
            )
        )
        pending_by_cbsd.setdefault(cbsd_id, []).append((low, high))
        responses.append(
            {
                "cbsdId": cbsd_id,
                "grantId": grant_id,
                "grantExpireTime": expire.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "heartbeatInterval": HEARTBEAT_INTERVAL_SEC,
                "channelType": channel_type,
                "response": {"responseCode": SUCCESS},
            }
        )

    db.commit()
    return responses
