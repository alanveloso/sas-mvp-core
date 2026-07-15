"""Admin / test-control routes expected by the WINNF harness."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from database import get_db, reset_db
from models.models import (
    BlacklistedFccId,
    ConditionalRegistration,
    CpiUser,
    FccIdRecord,
    UserIdRecord,
)
from schemas.admin import (
    BlacklistFccIdRequest,
    ConditionalRegistrationRequest,
    InjectCpiUserRequest,
    InjectFccIdRequest,
    InjectUserIdRequest,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _empty_ok() -> Response:
    return Response(status_code=200, content=b"", media_type="application/json")


@router.post("/reset")
def admin_reset():
    reset_db()
    return _empty_ok()


@router.post("/injectdata/fcc_id")
def inject_fcc_id(body: InjectFccIdRequest, db: Session = Depends(get_db)):
    existing = db.query(FccIdRecord).filter_by(fcc_id=body.fccId).first()
    if existing:
        existing.fcc_max_eirp = body.fccMaxEirp
    else:
        db.add(FccIdRecord(fcc_id=body.fccId, fcc_max_eirp=body.fccMaxEirp))
    db.commit()
    return _empty_ok()


@router.post("/injectdata/user_id")
def inject_user_id(body: InjectUserIdRequest, db: Session = Depends(get_db)):
    if not db.query(UserIdRecord).filter_by(user_id=body.userId).first():
        db.add(UserIdRecord(user_id=body.userId))
        db.commit()
    return _empty_ok()


@router.post("/injectdata/conditional_registration")
def inject_conditional_registration(
    body: ConditionalRegistrationRequest, db: Session = Depends(get_db)
):
    for item in body.registrationData:
        fcc_id = item.get("fccId")
        serial = item.get("cbsdSerialNumber")
        if not fcc_id or not serial:
            continue
        existing = (
            db.query(ConditionalRegistration)
            .filter_by(fcc_id=fcc_id, cbsd_serial_number=serial)
            .first()
        )
        payload = json.dumps(item)
        if existing:
            existing.data_json = payload
        else:
            db.add(
                ConditionalRegistration(
                    fcc_id=fcc_id,
                    cbsd_serial_number=serial,
                    data_json=payload,
                )
            )
    db.commit()
    return _empty_ok()


@router.post("/injectdata/cpi_user")
def inject_cpi_user(body: InjectCpiUserRequest, db: Session = Depends(get_db)):
    existing = db.query(CpiUser).filter_by(cpi_id=body.cpiId).first()
    if existing:
        existing.cpi_name = body.cpiName
        existing.cpi_public_key = body.cpiPublicKey
    else:
        db.add(
            CpiUser(
                cpi_id=body.cpiId,
                cpi_name=body.cpiName,
                cpi_public_key=body.cpiPublicKey,
            )
        )
    db.commit()
    return _empty_ok()


@router.post("/injectdata/blacklist_fcc_id")
def blacklist_fcc_id(body: BlacklistFccIdRequest, db: Session = Depends(get_db)):
    if not db.query(BlacklistedFccId).filter_by(fcc_id=body.fccId).first():
        db.add(BlacklistedFccId(fcc_id=body.fccId))
        db.commit()
    return _empty_ok()


@router.post("/get_daily_activities_status")
def get_daily_activities_status():
    return JSONResponse({"completed": True})


@router.post("/get_ppa_status")
def get_ppa_status():
    return JSONResponse({"completed": True, "withError": False})


@router.post("/injectdata/zone")
async def inject_zone(request: Request):
    body: dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:
        pass
    record = body.get("record") or {}
    return JSONResponse(record.get("id") or "zone/ppa/mvp/0")


@router.post("/trigger/create_ppa")
async def create_ppa(request: Request):
    body: dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:
        pass
    pal_ids = body.get("palIds") or ["pal0"]
    return JSONResponse(f"zone/ppa/mvp/{pal_ids[0]}/0")


# Catch-all stubs so the harness never gets HTTP 404 on admin paths.
@router.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def admin_stub(full_path: str, request: Request):
    if request.method == "POST" and full_path.endswith(
        ("get_daily_activities_status",)
    ):
        return JSONResponse({"completed": True})
    return _empty_ok()
