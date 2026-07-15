"""CBSD-to-SAS v1.2 routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import get_db
from models.models import Cbsd, Grant
from schemas.grant import GrantBatchRequest
from schemas.heartbeat import HeartbeatBatchRequest
from schemas.registration import RegistrationBatchRequest
from schemas.spectrum_inquiry import SpectrumInquiryBatchRequest
from services.grant_service import process_grant
from services.heartbeat_service import process_heartbeat
from services.registration_service import process_registration
from services.spectrum_inquiry_service import process_spectrum_inquiry

router = APIRouter(prefix="/v1.2", tags=["cbsd-sas"])


@router.post("/registration")
def registration(body: RegistrationBatchRequest, db: Session = Depends(get_db)):
    responses = process_registration(db, body.registrationRequest)
    return JSONResponse({"registrationResponse": responses})


@router.post("/grant")
def grant(body: GrantBatchRequest, db: Session = Depends(get_db)):
    responses = process_grant(db, body.grantRequest)
    return JSONResponse({"grantResponse": responses})


@router.post("/heartbeat")
def heartbeat(body: HeartbeatBatchRequest, db: Session = Depends(get_db)):
    responses = process_heartbeat(db, body.heartbeatRequest)
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
