"""Relinquishment business logic aligned with WINNF_FT_S_RLQ expectations."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from models.models import Cbsd, Grant

SUCCESS = 0
MISSING_PARAM = 102
INVALID_PARAM = 103


def _resp(
    code: int,
    *,
    cbsd_id: str | None = None,
    grant_id: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {"response": {"responseCode": code}}
    if cbsd_id is not None:
        out["cbsdId"] = cbsd_id
    if grant_id is not None:
        out["grantId"] = grant_id
    return out


def process_relinquishment(
    db: Session, requests: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    responses: list[dict[str, Any]] = []

    for req in requests:
        cbsd_id = req.get("cbsdId")
        grant_id = req.get("grantId")

        # Missing cbsdId and/or grantId → 102.
        # Echo cbsdId only when provided (RLQ_5); never echo grantId on missing-param.
        if not cbsd_id or not grant_id:
            responses.append(
                _resp(MISSING_PARAM, cbsd_id=cbsd_id if cbsd_id else None)
            )
            continue

        cbsd = db.query(Cbsd).filter_by(cbsd_id=cbsd_id).first()
        if not cbsd:
            # Unknown CBSD → 103 without echoing identifiers (RLQ_3).
            responses.append(_resp(INVALID_PARAM))
            continue

        grant = (
            db.query(Grant)
            .filter_by(grant_id=grant_id, cbsd_id=cbsd_id, terminated=False)
            .first()
        )
        if not grant:
            # Unknown / foreign / already relinquished grant → 103, echo cbsdId only.
            responses.append(_resp(INVALID_PARAM, cbsd_id=cbsd_id))
            continue

        grant.terminated = True
        responses.append(_resp(SUCCESS, cbsd_id=cbsd_id, grant_id=grant_id))

    db.commit()
    return responses
