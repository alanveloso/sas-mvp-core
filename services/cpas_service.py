"""CPAS / peer FAD sync — UUT acts as SAS↔SAS client during daily activities."""

from __future__ import annotations

import json
import logging
import ssl
import threading
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from database import SessionLocal
from models.models import Cbsd, Grant, PeerFadRecord, PeerSas
from services.fad_service import fad_cbsd_id
from services.meas_report import clear_admin_flags, set_admin_flag
from services.mtls_auth import ALLOWED_CIPHERS

logger = logging.getLogger(__name__)

FLAG_CPAS_RUNNING = "cpas_running"

ROOT = Path(__file__).resolve().parent.parent
HARNESS_CERTS = ROOT.parent / "src" / "harness" / "certs"
# Present the UUT SAS identity when pulling peer FADs (mTLS client).
CLIENT_CERT = HARNESS_CERTS / "server.cert"
CLIENT_KEY = HARNESS_CERTS / "server.key"
CA_CERT = HARNESS_CERTS / "ca.cert"

_cpas_lock = threading.Lock()
_cpas_thread: threading.Thread | None = None


def is_cpas_running(db: Session) -> bool:
    from services.meas_report import admin_flag_set

    return admin_flag_set(db, FLAG_CPAS_RUNNING)


def get_daily_activities_completed(db: Session) -> bool:
    return not is_cpas_running(db)


def trigger_daily_activities(db: Session) -> None:
    """Mark CPAS running and start peer FAD sync in a background thread."""
    global _cpas_thread
    set_admin_flag(db, FLAG_CPAS_RUNNING)

    with _cpas_lock:
        if _cpas_thread is not None and _cpas_thread.is_alive():
            return
        _cpas_thread = threading.Thread(
            target=_run_cpas_worker,
            name="cpas-peer-sync",
            daemon=True,
        )
        _cpas_thread.start()


def _run_cpas_worker() -> None:
    db = SessionLocal()
    try:
        run_peer_fad_sync(db)
        apply_peer_conflict_to_local_grants(db)
    except Exception:
        logger.exception("CPAS peer FAD sync failed")
    finally:
        try:
            clear_admin_flags(db, FLAG_CPAS_RUNNING)
        except Exception:
            logger.exception("Failed to clear CPAS running flag")
        db.close()


def _client_ssl_context() -> ssl.SSLContext:
    """mTLS client context compatible with SasTestHarnessServer / WINNF ciphers."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = False  # Peer URLs use localhost / harness hostnames.
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_verify_locations(cafile=str(CA_CERT))
    ctx.load_cert_chain(certfile=str(CLIENT_CERT), keyfile=str(CLIENT_KEY))
    ctx.set_ciphers(":".join(ALLOWED_CIPHERS))
    return ctx


def _httpx_client() -> httpx.Client:
    return httpx.Client(
        verify=_client_ssl_context(),
        timeout=30.0,
    )


def run_peer_fad_sync(db: Session) -> None:
    """GET dump + cbsd activity files from every injected peer and persist records."""
    peers = db.query(PeerSas).all()
    if not peers:
        return

    with _httpx_client() as client:
        for peer in peers:
            try:
                _sync_one_peer(db, client, peer)
            except Exception:
                logger.exception(
                    "Failed to sync peer SAS id=%s url=%s", peer.id, peer.url
                )
    db.commit()


def _sync_one_peer(db: Session, client: httpx.Client, peer: PeerSas) -> None:
    base = (peer.url or "").rstrip("/")
    if not base:
        return

    dump_url = f"{base}/dump"
    resp = client.get(dump_url)
    resp.raise_for_status()
    manifesto = resp.json()
    files = manifesto.get("files") or []

    for file_meta in files:
        if not isinstance(file_meta, dict):
            continue
        record_type = file_meta.get("recordType")
        # Focus on CBSD records for GRA_5 / GRA_6; still store zone/esc for later.
        if record_type == "coordination":
            continue
        file_url = file_meta.get("url")
        if not file_url:
            continue
        file_resp = client.get(file_url)
        file_resp.raise_for_status()
        envelope = file_resp.json()
        records = envelope.get("recordData") or []
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            record_id = str(record.get("id") or "")
            if not record_id:
                continue
            _upsert_peer_record(
                db,
                peer_sas_id=peer.id,
                record_type=str(record_type or "unknown"),
                record_id=record_id,
                record=record,
            )


def _upsert_peer_record(
    db: Session,
    *,
    peer_sas_id: int,
    record_type: str,
    record_id: str,
    record: dict[str, Any],
) -> None:
    existing = (
        db.query(PeerFadRecord)
        .filter_by(
            peer_sas_id=peer_sas_id,
            record_type=record_type,
            record_id=record_id,
        )
        .first()
    )
    payload = json.dumps(record)
    if existing:
        existing.data_json = payload
    else:
        db.add(
            PeerFadRecord(
                peer_sas_id=peer_sas_id,
                record_type=record_type,
                record_id=record_id,
                data_json=payload,
            )
        )


def _peer_cbsd_records(db: Session) -> list[dict[str, Any]]:
    rows = db.query(PeerFadRecord).filter_by(record_type="cbsd").all()
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            data = json.loads(row.data_json or "{}")
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            out.append(data)
    return out


def _active_peer_grants(record: dict[str, Any]) -> list[dict[str, Any]]:
    grants = record.get("grants") or []
    if not isinstance(grants, list):
        return []
    active: list[dict[str, Any]] = []
    for g in grants:
        if not isinstance(g, dict):
            continue
        if g.get("terminated") is True:
            continue
        active.append(g)
    return active


def peer_has_grant_for_cbsd(db: Session, cbsd: Cbsd) -> bool:
    """True when any peer FAD CBSD record matches this local CBSD and has an active grant."""
    target_id = fad_cbsd_id(cbsd.fcc_id, cbsd.cbsd_serial_number)
    for record in _peer_cbsd_records(db):
        if record.get("id") != target_id:
            continue
        if _active_peer_grants(record):
            return True
    return False


def apply_peer_conflict_to_local_grants(db: Session) -> None:
    """GRA_6 / FAD_2 prep: terminate local grants when the same CBSD appears on a peer."""
    changed = False
    for cbsd in db.query(Cbsd).all():
        if not peer_has_grant_for_cbsd(db, cbsd):
            continue
        grants = (
            db.query(Grant)
            .filter_by(cbsd_id=cbsd.cbsd_id, terminated=False)
            .all()
        )
        for grant in grants:
            grant.terminated = True
            changed = True
    if changed:
        db.commit()
