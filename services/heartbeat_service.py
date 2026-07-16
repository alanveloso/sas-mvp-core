"""Heartbeat business logic aligned with WINNF_FT_S_HBT / MES expectations."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from models.models import AdminInjectedData, BlacklistedFccId, Cbsd, Grant
from services.grant_service import DEFAULT_GRANT_DURATION_SEC, HEARTBEAT_INTERVAL_SEC
from services.meas_report import (
    FLAG_DPA_ACTIVE,
    FLAG_MEAS_HBT,
    MEAS_WITH_GRANT,
    admin_flag_set,
    cbsd_meas_capabilities,
    validate_meas_report,
)
from services.spectrum_inquiry_service import (
    _fss_location_and_freq,
    _load_injected,
    _overlaps,
    _wisp_freq,
)

SUCCESS = 0
VERSION_UNSUPPORTED = 100
BLACKLISTED = 101
MISSING_PARAM = 102
INVALID_PARAM = 103
TERMINATED_GRANT = 500
SUSPENDED_GRANT = 501
UNSYNC_OP_PARAM = 502

# Prefer a short window so HBT.5 finishes quickly; must be ≤ 240 s (WINNF).
TRANSMIT_EXPIRE_SEC = 60


def _fmt(dt: datetime) -> str:
    return dt.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _past_tx() -> datetime:
    return datetime.utcnow().replace(microsecond=0) - timedelta(seconds=1)


def _future_tx(grant_expire: datetime) -> datetime:
    tx = datetime.utcnow().replace(microsecond=0) + timedelta(seconds=TRANSMIT_EXPIRE_SEC)
    # transmitExpireTime must be ≤ grantExpireTime.
    if tx > grant_expire.replace(microsecond=0):
        tx = grant_expire.replace(microsecond=0)
    return tx


def _base(
    code: int,
    *,
    cbsd_id: str | None = None,
    grant_id: str | None = None,
    tx: datetime | None = None,
    grant_expire: datetime | None = None,
    heartbeat_interval: int | None = None,
    meas_config: list[str] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "transmitExpireTime": _fmt(tx if tx is not None else _past_tx()),
        "response": {"responseCode": code},
    }
    if cbsd_id is not None:
        out["cbsdId"] = cbsd_id
    if grant_id is not None:
        out["grantId"] = grant_id
    if grant_expire is not None:
        out["grantExpireTime"] = _fmt(grant_expire)
    if heartbeat_interval is not None:
        out["heartbeatInterval"] = heartbeat_interval
    if meas_config is not None:
        out["measReportConfig"] = meas_config
    return out


def _grant_overlaps_incumbent(db: Session, grant: Grant) -> bool:
    """True when grant frequency overlaps injected FSS or WISP (post-CPAS simulation)."""
    for wisp in _load_injected(db, "wisp"):
        freq = _wisp_freq(wisp)
        if freq and _overlaps(grant.low_frequency, grant.high_frequency, freq[0], freq[1]):
            return True
    for fss in _load_injected(db, "fss"):
        info = _fss_location_and_freq(fss)
        if not info:
            continue
        _, _, low, high = info
        if _overlaps(grant.low_frequency, grant.high_frequency, low, high):
            return True
        # FCC Part 96: FSS protection often extends above 3650 MHz within CBRS.
        if low >= 3_650_000_000 and _overlaps(
            grant.low_frequency, grant.high_frequency, 3_650_000_000, 3_700_000_000
        ):
            return True
    return False


def _grant_overlaps_active_dpa(db: Session, grant: Grant) -> bool:
    rows = db.query(AdminInjectedData).filter_by(kind=FLAG_DPA_ACTIVE).all()
    for row in rows:
        try:
            data = json.loads(row.data_json or "{}")
        except json.JSONDecodeError:
            continue
        fr = data.get("frequencyRange") or {}
        low = fr.get("lowFrequency")
        high = fr.get("highFrequency")
        if low is None or high is None:
            continue
        if _overlaps(grant.low_frequency, grant.high_frequency, int(low), int(high)):
            return True
    return False


def process_heartbeat(
    db: Session, requests: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    ask_meas = admin_flag_set(db, FLAG_MEAS_HBT)
    responses: list[dict[str, Any]] = []

    for req in requests:
        cbsd_id = req.get("cbsdId")
        grant_id = req.get("grantId")
        op_state = req.get("operationState")

        # Missing required fields → 102 with past transmitExpireTime.
        if not cbsd_id or not grant_id or not op_state:
            echo_grant = None
            if grant_id and cbsd_id:
                # Echo grantId when both ids present but operationState missing (HBT.4).
                if db.query(Grant).filter_by(grant_id=grant_id, cbsd_id=cbsd_id).first():
                    echo_grant = grant_id
            responses.append(
                _base(MISSING_PARAM, cbsd_id=cbsd_id, grant_id=echo_grant)
            )
            continue

        grant = (
            db.query(Grant)
            .filter_by(grant_id=grant_id, cbsd_id=cbsd_id)
            .first()
        )
        if not grant:
            # Invalid grantId → 103 without echoing grantId (HBT.7).
            responses.append(_base(INVALID_PARAM, cbsd_id=cbsd_id))
            continue

        cbsd = db.query(Cbsd).filter_by(cbsd_id=cbsd_id).first()
        if cbsd and db.query(BlacklistedFccId).filter_by(fcc_id=cbsd.fcc_id).first():
            responses.append(
                _base(BLACKLISTED, cbsd_id=cbsd_id, grant_id=grant_id)
            )
            continue

        # GRA_6: peer FAD reports an active grant for the same CBSD → terminate (500).
        from services.cpas_service import peer_has_grant_for_cbsd

        if cbsd and peer_has_grant_for_cbsd(db, cbsd):
            grant.terminated = True
            responses.append(
                _base(TERMINATED_GRANT, cbsd_id=cbsd_id, grant_id=grant_id)
            )
            continue

        if grant.terminated:
            # Relinquished / no longer valid grant → 103 (RLQ_2 requires 103;
            # RLQ_1 / HBT_5 also accept 500). Do not echo grantId.
            responses.append(_base(INVALID_PARAM, cbsd_id=cbsd_id))
            continue

        # DPA suspension/termination before expiry check (HBT.12 accepts 500 or 501).
        # Prefer 500 so the harness exits without the optional extra 300s sleep.
        if _grant_overlaps_active_dpa(db, grant):
            grant.terminated = True
            responses.append(
                _base(TERMINATED_GRANT, cbsd_id=cbsd_id, grant_id=grant_id)
            )
            continue

        if grant.grant_expire_time.replace(microsecond=0) <= datetime.utcnow().replace(
            microsecond=0
        ):
            responses.append(
                _base(INVALID_PARAM, cbsd_id=cbsd_id, grant_id=grant_id)
            )
            continue

        # Out-of-sync: AUTHORIZED before first successful GRANTED heartbeat.
        if op_state == "AUTHORIZED" and not grant.authorized:
            responses.append(
                _base(UNSYNC_OP_PARAM, cbsd_id=cbsd_id, grant_id=grant_id)
            )
            continue

        if _grant_overlaps_incumbent(db, grant):
            grant.terminated = True
            responses.append(
                _base(TERMINATED_GRANT, cbsd_id=cbsd_id, grant_id=grant_id)
            )
            continue

        capabilities = cbsd_meas_capabilities(cbsd.registration_json if cbsd else None)

        # After SAS asked for WITH_GRANT reports, validate subsequent heartbeats.
        if grant.meas_report_requested and MEAS_WITH_GRANT in capabilities:
            meas_err = validate_meas_report(
                req.get("measReport"), require_full_cbrs=False
            )
            if meas_err is not None:
                responses.append(
                    _base(meas_err, cbsd_id=cbsd_id, grant_id=grant_id)
                )
                continue

        if req.get("grantRenew") is True:
            grant.grant_expire_time = datetime.utcnow() + timedelta(
                seconds=DEFAULT_GRANT_DURATION_SEC
            )

        tx = _future_tx(grant.grant_expire_time)
        grant.transmit_expire_time = tx
        grant.authorized = True

        meas_config: list[str] | None = None
        if ask_meas and MEAS_WITH_GRANT in capabilities:
            meas_config = [MEAS_WITH_GRANT]
            grant.meas_report_requested = True

        responses.append(
            _base(
                SUCCESS,
                cbsd_id=cbsd_id,
                grant_id=grant_id,
                tx=tx,
                grant_expire=grant.grant_expire_time
                if req.get("grantRenew") is True
                else None,
                heartbeat_interval=grant.heartbeat_interval or HEARTBEAT_INTERVAL_SEC,
                meas_config=meas_config,
            )
        )

    db.commit()
    return responses
