# Spectrum Access System Core (`sas-core`)

Reference implementation of a **Spectrum Access System (SAS)** for the CBRS band (3550–3700 MHz), aligned with WInnForum specifications. `sas-core` is a runnable FastAPI service — designed as a **reusable component** for research, benchmarking, and prototypes that need a WINNF-compliant SAS.

This is not a commercial RF product. It is a robust, validated *baseline* for comparing metrics such as grant latency, state convergence, and SAS-to-SAS federation overhead.

Protocol conformance is verified externally with the [WInnForum CBRS SAS Test Harness](https://github.com/Wireless-Innovation-Forum/CBRS-SAS-Test-Harness) (**WINNF-TS-0061**).

---

## What `sas-core` exposes

| Interface | Prefix / version | Authentication | Purpose |
|-----------|------------------|----------------|---------|
| **CBSD ↔ SAS** | `/v1.2` | mTLS (CBSD certificate) | Registration, Spectrum Inquiry, Grant, Heartbeat, Relinquishment, Deregistration |
| **SAS ↔ SAS** | `/v1.3` | mTLS (authorized peer SAS) | Full Activity Dump (FAD), ESC sensor export |
| **Admin** | `/admin` | mTLS (harness / operator) | Test data injection, CPAS triggers, database sync |

Dual TLS server (Uvicorn):

- `https://0.0.0.0:9000` — RSA (CBSD, Admin, SAS-SAS RSA)
- `https://0.0.0.0:9001` — ECDSA (SAS-SAS ECDSA, e.g. SSS suite)

```
CBSD / peer SAS ──mTLS──► sas-core (FastAPI)
                              │
                              ▼
                          SQLite (SQLAlchemy)
```

---

## Internal architecture

| Layer | Contents |
|-------|----------|
| `routes/` | CBSD endpoints (`cbsd_routes`), SAS-SAS (`sas_sas_routes`), Admin (`admin_routes`) |
| `services/` | Business logic: registration, inquiry, grant, heartbeat, FAD, CPAS, zones, PAL, border rules |
| `models/` | ORM entities: CBSD, Grant, PalRecord, PeerSas, FadDump, etc. |
| `schemas/` | Pydantic validation for WINNF payloads |
| `database.py` | SQLite, `init_db()`, `reset_db()` |

Stack: Python 3, FastAPI, SQLAlchemy, Pydantic, httpx (CPAS client / database sync), Uvicorn with mTLS.

---

## Implemented domains

`sas-core` covers the full CBSD-SAS lifecycle and the federated flows required by the official harness:

| Domain | Scope in core |
|--------|---------------|
| **CBSD registration & lifecycle** | Registration, Spectrum Inquiry, Grant, Heartbeat, Relinquishment, Deregistration |
| **PAL / GAA** | PAL licenses (`pal_records`), PPA zones, GAA channels; rules by PPA cluster and `userId` |
| **SAS-SAS federation** | Full Activity Dump generation and download; peer record import |
| **CPAS** | Daily activities: peer-PPA conflicts, ESC, FSS/GWBL/EXZ/DPA sync |
| **Border & federal rules** | Exclusion Zones, Border Protection (Canada), Quiet Zones, Federal DB, Whitelist DB |

**Validated WINNF suites (14):** REG, SIQ, GRA, HBT, RLQ, DRG, FAD, SSS, EXZ, BPR, EPR, QPR, WDB, FDB.

---

## Core limitations

These choices are **intentional** in this repository. They affect RF fidelity only, not protocol conformance as tested by the harness:

- **SQLite persistence** — suitable for benchmarking and prototypes; not a distributed production backend.
- **Simplified geometry** (`services/geometry.py`) — ray-casting and Haversine instead of high-fidelity ITM propagation models.
- **Pragmatic IAP** — spatial protections tuned for protocol state and latency, not full physical simulation.
- **Batch size up to 100** — aligned with the harness `MaximumBatchSize`.

---

## Installation and running

### 1. Clone and set up the environment

```bash
git clone <sas-core-repository-url>
cd sas-core

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. mTLS certificates

The server expects test certificates at the relative path `../src/harness/certs/` (WInnForum harness default). Generate them with the official script:

```bash
git clone https://github.com/Wireless-Innovation-Forum/CBRS-SAS-Test-Harness.git /tmp/cbrs-harness
cd /tmp/cbrs-harness/certs
bash generate_fake_certs.sh

# Adjust the path to match your local layout, for example:
mkdir -p ../src/harness
cp -r /tmp/cbrs-harness/certs ../src/harness/
```

Required files: `server.cert`, `server.key`, `server-ecc.cert`, `server-ecc.key`, `ca.cert`.

### 3. Start the service

```bash
python main.py
```

The SQLite database (`sas_mvp.db`) is created automatically on startup.

---

## Validation with the WInnForum harness

The harness is **not part of** this repository. To validate `sas-core`:

1. Keep the service running (`python main.py`).
2. Configure the harness `sas.cfg` to point at `localhost:9000` / `:9001` (versions `v1.2` / `v1.3`).
3. Run the desired suites:

```bash
cd <path-to-harness>
python3 -m unittest testcases.WINNF_FT_S_REG_testcase -v
python3 -m unittest testcases.WINNF_FT_S_SIQ_testcase -v
python3 -m unittest testcases.WINNF_FT_S_GRA_testcase -v
# … additional suites as needed
```

Minimal `sas.cfg` example:

```ini
[SasConfig]
AdminApiBaseUrl: localhost:9000
CbsdSasRsaBaseUrl: localhost:9000
CbsdSasEcBaseUrl: localhost:9001
SasSasRsaBaseUrl: localhost:9000
SasSasEcBaseUrl: localhost:9001
CbsdSasVersion: v1.2
SasSasVersion: v1.3
AdminId: sas_admin_id
MaximumBatchSize: 100
```

**Environment note:** suite FDB_8 requires the `US/Pacific` timezone. Install `tzdata` if needed:

```bash
pip install tzdata pytz --upgrade
```

---

## Repository layout

```
sas-core/
├── main.py              # FastAPI + Uvicorn entrypoint (9000/9001)
├── database.py          # SQLite / SQLAlchemy
├── requirements.txt
├── routes/              # CBSD v1.2, SAS-SAS v1.3, /admin
├── services/            # Business logic
├── models/              # ORM
└── schemas/             # Pydantic
```

---

## License

`sas-core` is licensed under the **Apache License, Version 2.0**. See [LICENSE](LICENSE) for the full text.

```text
Copyright 2026 Alan Veloso

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
```

**Third-party components:** the WInnForum CBRS SAS Test Harness and its reference models are separate works, subject to the license and attribution of the [Wireless Innovation Forum](https://github.com/Wireless-Innovation-Forum). Using `sas-core` does not grant any rights to WINNF specifications or harness code beyond their respective licenses.
