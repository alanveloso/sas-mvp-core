"""CBSD-to-SAS v1.2 routes."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import get_db
from models.models import Cbsd, Grant
from schemas.registration import RegistrationBatchRequest
from schemas.spectrum_inquiry import SpectrumInquiryBatchRequest
from services.registration_service import process_registration
from services.spectrum_inquiry_service import process_spectrum_inquiry

router = APIRouter(prefix="/v1.2", tags=["cbsd-sas"])


@router.post("/registration")
def registration(body: RegistrationBatchRequest, db: Session = Depends(get_db)):
    responses = process_registration(db, body.registrationRequest)
    return JSONResponse({"registrationResponse": responses})


@router.post("/grant")
async def grant(body: dict[str, Any], db: Session = Depends(get_db)):
    """Minimal Grant for REG_2 / REG_4 re-registration flows."""
    responses = []
    for req in body.get("grantRequest") or []:
        cbsd_id = req.get("cbsdId")
        if not cbsd_id:
            responses.append({"response": {"responseCode": 102}})
            continue
        cbsd = db.query(Cbsd).filter_by(cbsd_id=cbsd_id).first()
        if not cbsd:
            responses.append(
                {"cbsdId": cbsd_id, "response": {"responseCode": 103}}
            )
            continue
        grant_id = f"grant/{uuid.uuid4().hex}"
        expire = datetime.utcnow() + timedelta(days=7)
        db.add(
            Grant(
                grant_id=grant_id,
                cbsd_id=cbsd_id,
                channel_type="GAA",
                grant_expire_time=expire,
                heartbeat_interval=60,
                grant_json=json.dumps(req),
            )
        )
        responses.append(
            {
                "cbsdId": cbsd_id,
                "grantId": grant_id,
                "grantExpireTime": expire.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "heartbeatInterval": 60,
                "channelType": "GAA",
                "response": {"responseCode": 0},
            }
        )
    db.commit()
    return JSONResponse({"grantResponse": responses})


@router.post("/heartbeat")
async def heartbeat(body: dict[str, Any], db: Session = Depends(get_db)):
    """Minimal Heartbeat for REG_2 / REG_4 re-registration flows."""
    responses = []
    for req in body.get("heartbeatRequest") or []:
        cbsd_id = req.get("cbsdId")
        grant_id = req.get("grantId")
        grant = (
            db.query(Grant)
            .filter_by(grant_id=grant_id, cbsd_id=cbsd_id)
            .first()
        )
        if not grant or grant.terminated:
            # After re-registration grants are terminated → 103 with past transmitExpireTime
            past = datetime.utcnow() - timedelta(seconds=1)
            responses.append(
                {
                    "cbsdId": cbsd_id,
                    "grantId": grant_id,
                    "transmitExpireTime": past.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "response": {"responseCode": 103},
                }
            )
            continue
        # Keep short so REG_4 re-registration wait stays fast; HBT suite will refine later.
        tx_expire = datetime.utcnow().replace(microsecond=0) + timedelta(seconds=15)
        grant.transmit_expire_time = tx_expire
        responses.append(
            {
                "cbsdId": cbsd_id,
                "grantId": grant_id,
                "transmitExpireTime": tx_expire.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "grantExpireTime": grant.grant_expire_time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "heartbeatInterval": grant.heartbeat_interval,
                "response": {"responseCode": 0},
            }
        )
    db.commit()
    return JSONResponse({"heartbeatResponse": responses})


@router.post("/spectrumInquiry")
def spectrum_inquiry(
    body: SpectrumInquiryBatchRequest, db: Session = Depends(get_db)
):
    responses = process_spectrum_inquiry(db, body.spectrumInquiryRequest)
    return JSONResponse({"spectrumInquiryResponse": responses})


@router.post("/relinquishment")
async def relinquishment(body: dict[str, Any], db: Session = Depends(get_db)):
    responses = []
    for req in body.get("relinquishmentRequest") or []:
        grant = (
            db.query(Grant)
            .filter_by(grant_id=req.get("grantId"), cbsd_id=req.get("cbsdId"))
            .first()
        )
        if grant:
            grant.terminated = True
        responses.append(
            {
                "cbsdId": req.get("cbsdId"),
                "grantId": req.get("grantId"),
                "response": {"responseCode": 0},
            }
        )
    db.commit()
    return JSONResponse({"relinquishmentResponse": responses})


@router.post("/deregistration")
async def deregistration(body: dict[str, Any], db: Session = Depends(get_db)):
    responses = []
    for req in body.get("deregistrationRequest") or []:
        cbsd_id = req.get("cbsdId")
        if not cbsd_id:
            responses.append({"response": {"responseCode": 102}})
            continue
        cbsd = db.query(Cbsd).filter_by(cbsd_id=cbsd_id).first()
        if cbsd:
            for grant in db.query(Grant).filter_by(cbsd_id=cbsd_id).all():
                grant.terminated = True
            db.delete(cbsd)
        responses.append(
            {"cbsdId": cbsd_id, "response": {"responseCode": 0}}
        )
    db.commit()
    return JSONResponse({"deregistrationResponse": responses})
