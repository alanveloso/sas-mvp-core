"""Full Activity Dump generation for SAS↔SAS (v1.3) server role."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from models.models import (
    AdminInjectedData,
    Cbsd,
    EscSensor,
    FadDump,
    FadFile,
    Grant,
)

# Matches src/harness/sas.cfg AdminId / SasSasRsaBaseUrl.
SAS_ADMIN_ID = "sas_admin_id"
FAD_PUBLIC_BASE = "https://localhost:9000"
SAS_SAS_VERSION = "v1.3"

_REGISTRATION_FIELDS = (
    "fccId",
    "cbsdCategory",
    "callSign",
    "airInterface",
    "measCapability",
    "installationParam",
    "groupingParam",
)


def cbsd_reference_id(fcc_id: str, serial_number: str) -> str:
    """SAS↔SAS CBSD reference: {fccId}/{sha1(serialNumber)}."""
    digest = hashlib.sha1(serial_number.encode("utf-8")).hexdigest()
    return f"{fcc_id}/{digest}"


def fad_cbsd_id(fcc_id: str, serial_number: str) -> str:
    return f"cbsd/{cbsd_reference_id(fcc_id, serial_number)}"


def rewrite_esc_sensor_id(record_id: str | None) -> str:
    """Force esc_sensor/{AdminId}/... prefix required by FAD_1."""
    if not record_id:
        return f"esc_sensor/{SAS_ADMIN_ID}/0"
    parts = record_id.split("/")
    if len(parts) >= 3 and parts[0] == "esc_sensor":
        return f"esc_sensor/{SAS_ADMIN_ID}/{'/'.join(parts[2:])}"
    if len(parts) >= 2 and parts[0] == "esc_sensor":
        return f"esc_sensor/{SAS_ADMIN_ID}/{parts[1]}"
    return f"esc_sensor/{SAS_ADMIN_ID}/{record_id}"


def rewrite_zone_id(zone_id: str | None, *, fallback_suffix: str = "0") -> str:
    """Force zone/ppa/{AdminId}/... prefix required by FAD_1."""
    if not zone_id:
        return f"zone/ppa/{SAS_ADMIN_ID}/{fallback_suffix}"
    parts = zone_id.split("/")
    if len(parts) >= 3 and parts[0] == "zone" and parts[1] == "ppa":
        rest = "/".join(parts[3:]) if len(parts) > 3 else fallback_suffix
        return f"zone/ppa/{SAS_ADMIN_ID}/{rest}"
    return f"zone/ppa/{SAS_ADMIN_ID}/{fallback_suffix}"


def _fmt_utc(dt: datetime) -> str:
    return dt.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha1_of(content: str) -> str:
    return hashlib.sha1(content.encode("utf-8")).hexdigest()


def _build_registration(reg: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in _REGISTRATION_FIELDS:
        if key in reg and reg[key] is not None:
            out[key] = copy.deepcopy(reg[key])

    inst = out.get("installationParam")
    if isinstance(inst, dict):
        inst = dict(inst)
        azimuth = inst.get("antennaAzimuth")
        beamwidth = inst.get("antennaBeamwidth")
        # Omni default when azimuth is absent (FAD_1 / WINNF-TS-0061).
        if azimuth is None:
            inst["antennaBeamwidth"] = 360
        elif beamwidth is None:
            pass
        out["installationParam"] = inst
    return out


def _operation_param_from_grant(grant: Grant) -> dict[str, Any]:
    try:
        req = json.loads(grant.grant_json or "{}")
    except json.JSONDecodeError:
        req = {}
    op = req.get("operationParam")
    if isinstance(op, dict) and "operationFrequencyRange" in op:
        return copy.deepcopy(op)
    return {
        "maxEirp": grant.max_eirp,
        "operationFrequencyRange": {
            "lowFrequency": grant.low_frequency,
            "highFrequency": grant.high_frequency,
        },
    }


def _build_grant_record(grant: Grant) -> dict[str, Any]:
    op = _operation_param_from_grant(grant)
    return {
        "id": grant.grant_id,
        "channelType": grant.channel_type,
        "grantExpireTime": _fmt_utc(grant.grant_expire_time),
        "operationParam": op,
        "requestedOperationParam": copy.deepcopy(op),
        "terminated": bool(grant.terminated),
    }


def _build_cbsd_records(db: Session) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    cbsds = db.query(Cbsd).order_by(Cbsd.id).all()
    for cbsd in cbsds:
        try:
            reg = json.loads(cbsd.registration_json or "{}")
        except json.JSONDecodeError:
            reg = {}
        grants = (
            db.query(Grant)
            .filter_by(cbsd_pk=cbsd.id, terminated=False)
            .order_by(Grant.id)
            .all()
        )
        records.append(
            {
                "id": fad_cbsd_id(cbsd.fcc_id, cbsd.cbsd_serial_number),
                "registration": _build_registration(reg),
                "grants": [_build_grant_record(g) for g in grants],
            }
        )
    return records


def _operational_to_reference_id(ref: str, db: Session) -> str:
    """Convert operational cbsdId ({fcc}/{serial}) to SAS↔SAS reference id."""
    cbsd = db.query(Cbsd).filter_by(cbsd_id=ref).first()
    if cbsd:
        return cbsd_reference_id(cbsd.fcc_id, cbsd.cbsd_serial_number)
    # Already a reference id, or unknown — pass through if it looks hashed.
    parts = ref.split("/")
    if len(parts) == 2 and len(parts[1]) == 40:
        return ref
    if ref.startswith("cbsd/"):
        return ref[len("cbsd/") :]
    # Last resort: treat as fccId/serial and hash serial.
    if len(parts) == 2:
        return cbsd_reference_id(parts[0], parts[1])
    return ref


def _build_zone_records(db: Session) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    rows = (
        db.query(AdminInjectedData)
        .filter_by(kind="zone")
        .order_by(AdminInjectedData.id)
        .all()
    )
    for row in rows:
        try:
            payload = json.loads(row.data_json or "{}")
        except json.JSONDecodeError:
            continue
        record = copy.deepcopy(payload.get("record") or payload)
        if not isinstance(record, dict):
            continue
        if record.get("usage") not in (None, "PPA") and "ppaInfo" not in record:
            continue
        record["id"] = rewrite_zone_id(record.get("id"), fallback_suffix=str(row.id))
        ppa_info = record.get("ppaInfo")
        if isinstance(ppa_info, dict):
            refs = ppa_info.get("cbsdReferenceId") or []
            ppa_info["cbsdReferenceId"] = [
                _operational_to_reference_id(str(r), db) for r in refs
            ]
            record["ppaInfo"] = ppa_info
        records.append(record)
    return records


def _build_esc_records(db: Session) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in db.query(EscSensor).order_by(EscSensor.id).all():
        try:
            record = json.loads(row.data_json or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        record = copy.deepcopy(record)
        record["id"] = row.record_id
        records.append(record)
    return records


def _make_dump_file(
    *,
    record_type: str,
    filename: str,
    record_data: list[dict[str, Any]],
    timestamp: str,
) -> tuple[dict[str, Any], str, str]:
    """Return (manifest entry, url_path, content_json)."""
    envelope = {
        "startTime": timestamp,
        "endTime": timestamp,
        "recordData": record_data,
    }
    content = json.dumps(envelope, separators=(",", ":"), ensure_ascii=False)
    url_path = f"/{SAS_SAS_VERSION}/{record_type}/{filename}"
    entry = {
        "url": f"{FAD_PUBLIC_BASE}{url_path}",
        "checksum": _sha1_of(content),
        "size": len(content.encode("utf-8")),
        "version": SAS_SAS_VERSION,
        "recordType": record_type,
    }
    return entry, url_path, content


def create_full_activity_dump(db: Session) -> FadDump:
    """Generate and persist a ready FullActivityDump + files."""
    now = datetime.utcnow().replace(microsecond=0)
    timestamp = _fmt_utc(now)

    cbsd_data = _build_cbsd_records(db)
    zone_data = _build_zone_records(db)
    esc_data = _build_esc_records(db)

    file_specs = [
        ("cbsd", "activity_dump_file_cbsd0.json", cbsd_data),
        ("zone", "activity_dump_file_zone0.json", zone_data),
        ("esc_sensor", "activity_dump_file_esc_sensor0.json", esc_data),
        ("coordination", "activity_dump_file_coordination0.json", []),
    ]

    files_meta: list[dict[str, Any]] = []
    file_rows: list[tuple[str, str, str, dict[str, Any]]] = []
    for record_type, filename, data in file_specs:
        entry, url_path, content = _make_dump_file(
            record_type=record_type,
            filename=filename,
            record_data=data,
            timestamp=timestamp,
        )
        files_meta.append(entry)
        file_rows.append((record_type, url_path, content, entry))

    manifest = {
        "files": files_meta,
        "generationDateTime": timestamp,
        "description": "Full activity dump files",
    }

    dump = FadDump(
        generation_datetime=timestamp,
        description=manifest["description"],
        manifest_json=json.dumps(manifest, separators=(",", ":"), ensure_ascii=False),
        ready=True,
    )
    db.add(dump)
    db.flush()

    for record_type, url_path, content, entry in file_rows:
        db.add(
            FadFile(
                dump_id=dump.id,
                record_type=record_type,
                url_path=url_path,
                checksum=entry["checksum"],
                size=entry["size"],
                content_json=content,
            )
        )
    db.commit()
    db.refresh(dump)
    return dump


def get_latest_ready_dump(db: Session) -> FadDump | None:
    return (
        db.query(FadDump)
        .filter_by(ready=True)
        .order_by(FadDump.id.desc())
        .first()
    )


def get_dump_file_by_path(db: Session, url_path: str) -> FadFile | None:
    dump = get_latest_ready_dump(db)
    if dump is None:
        return None
    normalized = url_path if url_path.startswith("/") else f"/{url_path}"
    row = (
        db.query(FadFile)
        .filter_by(dump_id=dump.id, url_path=normalized)
        .first()
    )
    if row:
        return row
    filename = normalized.rsplit("/", 1)[-1]
    return (
        db.query(FadFile)
        .filter(FadFile.dump_id == dump.id, FadFile.url_path.endswith("/" + filename))
        .first()
    )
