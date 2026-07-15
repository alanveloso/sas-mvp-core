# SAS MVP Core

Backend MVP de Spectrum Access System (FastAPI + SQLite) para benchmark contra a suíte WINNF.

## Subir o servidor

```bash
cd sas_mvp_core
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

O servidor escuta em `https://0.0.0.0:9000` usando os certificados de `src/harness/certs/` (gere com `bash generate_fake_certs.sh` se necessário).

## Rodar testes

Com o servidor ativo:

```bash
# Registration
cd src/harness && python3 -m unittest testcases.WINNF_FT_S_REG_testcase -v

# Spectrum Inquiry
cd src/harness && python3 -m unittest testcases.WINNF_FT_S_SIQ_testcase -v

# Grant
cd src/harness && python3 -m unittest testcases.WINNF_FT_S_GRA_testcase -v

# Heartbeat
cd src/harness && python3 -m unittest testcases.WINNF_FT_S_HBT_testcase -v

# Measurement Report
cd src/harness && python3 -m unittest testcases.WINNF_FT_S_MES_testcase -v
```

---

## Limitações: o que está fora do MVP

O MVP implementa o fluxo CBSD→SAS (Registration, Spectrum Inquiry, Grant, Heartbeat) com regras simuladas e stubs admin. Alguns testes WINNF exigem capacidades de certificação completa que **ainda não fazem parte deste MVP**.

### 1. Binding certificado cliente ↔ CBSD (mTLS de negócio)

| Item | Detalhe |
|------|---------|
| **Testes afetados** | `GRA_4` (e testes equivalentes de segurança CBSD) |
| **O que o teste espera** | Grant do `cbsdId` do device A usando o cert do device C → `responseCode: 103` |
| **O que falta** | Extrair o certificado cliente da conexão TLS, associá-lo ao CBSD no Registration e rejeitar Grant/Heartbeat/etc. se o cert não for o do dono do `cbsdId` |
| **Estado atual** | HTTPS com `server.cert`/`server.key` basta para o harness falar com a UUT. **Não** há `ssl_ca_certs` / `CERT_REQUIRED` nem mapeamento CN/fingerprint → CBSD |

Para habilitar isso depois: configurar o Uvicorn/FastAPI com CA do harness, exigir cert cliente, persistir fingerprint/CN no `Cbsd` no Registration e validar em cada endpoint CBSD.

### 2. Peer SAS + Full Activity Dump (FAD) + CPAS

| Item | Detalhe |
|------|---------|
| **Testes afetados** | `GRA_5`, `GRA_6` (também IPR, PPR, FAD, SSS, MCP em fases futuras) |
| **O que o teste espera** | Outro SAS (Test Harness) injeta grants via FAD; após CPAS, a UUT detecta conflito (`401` no Grant ou `500` no Heartbeat) |
| **O que falta** | |
| | • Consumir `InjectPeerSas` de verdade (`certificateHash` + `url`) |
| | • Cliente SAS↔SAS: puxar dump do peer (`GET /v1.3/dump` e arquivos) |
| | • Processar FAD (registros CBSD/grant do peer) e usar no CPAS |
| | • Motor CPAS / daily activities real (hoje o trigger só retorna `completed: true`) |
| **Estado atual** | Stub `POST /admin/injectdata/peer_sas` → HTTP 200 (evita 404). Sem sincronização nem análise de conflito entre SASes |

### 3. DPA activation no caminho Grant → Heartbeat

| Item | Detalhe |
|------|---------|
| **Testes afetados** | `GRA_1` (sleep 240s + regras PAL avançadas); `HBT_12` cobre suspensão básica |
| **O que o teste espera** | Após `TriggerDpaActivation`, o grant fica suspenso no heartbeat (`501`) ou é recusado no grant (`400`) |
| **Estado atual** | `HBT_12`: DPA ativa é persistida e Heartbeat retorna `501`. Graçãos PAL com IAP completo / `GRA_1` podem exigir mais fidelidade |

### 4. Outros itens tipicamente fora do MVP mínimo

| Capacidade | Usado por | Nota |
|------------|-----------|------|
| SAS↔SAS dump (`/v1.3/dump`, ESC sensor) | FAD, SSS, MCP | Fora do fluxo CBSD→SAS do MVP |
| Modelos de propagação / IAP / proteção real FSS/DPA | FPR, GPR, IPR, PPR | SIQ/GRA/HBT usam regras geométricas/frequência simplificadas |
| Blacklist por FCC ID + serial | Interface admin (pouco usada) | Só blacklist por `fccId` está no MVP |

---

## O que a fase Heartbeat *já* cobre no MVP

Com `POST /v1.2/heartbeat` + triggers MES:

- Sucesso `GRANTED` → `AUTHORIZED`, `transmitExpireTime` futuro e ≤ 240 s
- `grantRenew` estende `grantExpireTime`
- Parâmetros faltando → `102` (tx no passado)
- `grantId` inválido → `103` (sem ecoar `grantId`)
- Blacklist → `101`
- Grant terminado / expirado → `103`/`500`
- Estado dessincronizado (`AUTHORIZED` sem HB prévio) → `502`
- Conflito com FSS/WISP injetados → `500`
- DPA ativa na faixa do grant → `501`
- Versão de protocolo sem suporte → `100`
- MES: `measReportConfig` + validação de `measReport` em Registration/SIQ/Grant/Heartbeat
