"""
SAS MVP entrypoint — HTTPS on port 9000 for the WINNF harness.

Usage (from sas_mvp_core/):
  .venv/bin/python main.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

# Allow `python main.py` and `uvicorn main:app` from sas_mvp_core/
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from database import init_db
from routes.admin_routes import router as admin_router
from routes.cbsd_routes import router as cbsd_router

HARNESS_CERTS = ROOT.parent / "src" / "harness" / "certs"
SSL_CERTFILE = HARNESS_CERTS / "server.cert"
SSL_KEYFILE = HARNESS_CERTS / "server.key"

app = FastAPI(title="SAS MVP Core", version="0.1.0")
app.include_router(admin_router)
app.include_router(cbsd_router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.post("/{version}/registration")
async def registration_unsupported_version(version: str, request: Request):
    """REG_10 / REG_13: unsupported CBSD-SAS protocol version → responseCode 100."""
    if version == "v1.2":
        # Concrete /v1.2/registration route should handle this; reject accidental hits.
        return JSONResponse({"detail": "Use /v1.2/registration"}, status_code=500)
    body = await request.json()
    requests = body.get("registrationRequest") or []
    responses = [{"response": {"responseCode": 100}} for _ in requests]
    return JSONResponse({"registrationResponse": responses})


@app.post("/{version}/heartbeat")
async def heartbeat_unsupported_version(version: str, request: Request):
    """HBT_3: unsupported CBSD-SAS protocol version → responseCode 100."""
    if version == "v1.2":
        return JSONResponse({"detail": "Use /v1.2/heartbeat"}, status_code=500)
    body = await request.json()
    past_s = (datetime.utcnow() - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    responses = []
    for req in body.get("heartbeatRequest") or []:
        responses.append(
            {
                "cbsdId": req.get("cbsdId"),
                "grantId": req.get("grantId"),
                "transmitExpireTime": past_s,
                "response": {"responseCode": 100},
            }
        )
    return JSONResponse({"heartbeatResponse": responses})


def main():
    import uvicorn

    if not SSL_CERTFILE.exists() or not SSL_KEYFILE.exists():
        raise SystemExit(
            f"Certificados TLS não encontrados em {HARNESS_CERTS}. "
            "Execute: cd src/harness/certs && bash generate_fake_certs.sh"
        )

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=9000,
        ssl_certfile=str(SSL_CERTFILE),
        ssl_keyfile=str(SSL_KEYFILE),
        reload=False,
    )


if __name__ == "__main__":
    main()
