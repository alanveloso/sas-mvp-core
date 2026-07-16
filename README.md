# Spectrum Access System (SAS) MVP

MVP de um **Spectrum Access System** centralizado para a banda CBRS (3550–3700 MHz), implementado como API REST clássica. O objetivo não é um produto comercial de RF, e sim um *baseline* robusto e validado para **benchmark acadêmico e de pesquisa** — permitindo comparar métricas de rede como latência, convergência de estado e overhead de federação SAS-to-SAS.

O UUT (Unit Under Test) vive em [`sas_mvp_core/`](sas_mvp_core/) e foi validado contra o *harness* oficial da WInnForum (**WINNF-TS-0061**).

---

## Arquitetura e Tecnologias

| Camada | Tecnologia |
|--------|------------|
| Runtime / API | Python 3, **FastAPI** (assíncrono) |
| Persistência | **SQLite** + **SQLAlchemy** |
| Cliente HTTP (CPAS / peer FAD) | **httpx** |
| Servidor TLS | **Uvicorn** com mTLS (RSA `:9000`, ECDSA `:9001`) |
| Protocolo CBSD ↔ SAS | REST `v1.2` |
| Protocolo SAS ↔ SAS | REST `v1.3` (FAD, ESC sensor) |

```
CBSD / Harness ──mTLS──► https://localhost:9000  (RSA)
                      ► https://localhost:9001  (ECDSA)
                              │
                              ▼
                     sas_mvp_core (FastAPI)
                              │
                              ▼
                          SQLite (ORM)
```

---

## Cobertura de Testes Oficiais (100% Pass)

O sistema **passa nas 14 suítes** do WInnForum (WINNF-TS-0061) exercitadas neste repositório:

| Domínio | Suítes | Fluxos cobertos |
|---------|--------|-----------------|
| **CBSD ↔ SAS** | REG, SIQ, GRA, HBT, RLQ, DRG | Registration, Spectrum Inquiry, Grant, Heartbeat, Relinquishment, Deregistration |
| **SAS ↔ SAS** | FAD, SSS | Full Activity Dump, segurança mTLS peer-to-peer |
| **CPAS** | (integrado em FAD / GRA / MCP-like) | Motor de atividades diárias: conflitos Peer-PPA e ESC |
| **Borda e regras federais** | EXZ, BPR, EPR, QPR, WDB, FDB | Exclusion Zones, Border Protection, ESC, Quiet Zones, Whitelist DB, Federal DB |

Destaques:

- Fluxos CBSD-SAS completos com autenticação mTLS e *batch* (`MaximumBatchSize: 100`).
- Federação SAS-SAS: manifesto FAD, download de arquivos e rejeição de peers não injetados.
- CPAS resolve conflitos entre grants locais e proteções importadas do peer (PPA / ESC).

---

## Decisões Pragmáticas e Limitações

Este MVP prioriza **reprodutibilidade e desempenho de rede** sobre fidelidade absoluta de radiofrequência física.

### Ambiente *flat-earth* (NED)

Os *tiles* USGS NED de elevação (~dezenas de GB no [Common-Data](https://github.com/Wireless-Innovation-Forum/Common-Data)) **não são obrigatórios** para rodar o harness localmente. O driver de terreno opera em modo *flat-earth* por padrão (`reference_models.geo.drive`), evitando falhas por *tiles* ausentes.

Para usar NED real (quando os dados estiverem instalados em `data/geo/ned/`):

```bash
export SAS_USE_REAL_NED=1
```

### Matemática geoespacial (IAP)

Cálculos de IAP / proteção espacial foram **simplificados e otimizados** para o caminho crítico do protocolo (estado, latência, federação), não para simular propagação ITM de alta fidelidade. Contornos e *ray-casting* de polígonos bastam para as asserções das suítes oficiais.

### Compatibilidade de ambiente (Python 3.12 / fuso horário)

- O *harness* original usava `ssl.wrap_socket`, removido no Python 3.12. Neste repositório o código foi atualizado para `SSLContext.wrap_socket` (ex.: `src/harness/database.py`, `sas_test_harness.py`).
- A suíte **FDB_8** exige o fuso `US/Pacific`. Em hosts sem zoneinfo legado, instale dados de timezone atualizados:

```bash
pip install tzdata pytz --upgrade
python3 -c "import pytz; pytz.timezone('US/Pacific')"
```

---

## Configuração e Instalação Local

### 1. Clonar o repositório

```bash
git clone <url-deste-repositorio>
cd Spectrum-Access-System
```

### 2. Ambiente virtual e dependências

```bash
python3 -m venv .venv
source .venv/bin/activate

# Dependências do UUT (SAS MVP)
pip install -r sas_mvp_core/requirements.txt

# Dependências do harness WInnForum (já incluídas na raiz, se for validar testes)
pip install -r requirements.txt
pip install tzdata pytz --upgrade   # necessário para FDB_8
```

Dependências de sistema comuns ao harness (conforme a WInnForum): `libgeos`, `libgdal`, etc. Em Linux, use o `conda-environment.yml` da raiz como alternativa.

### 3. Certificados TLS de teste

O UUT espera os certificados gerados pelo script do harness:

```bash
cd src/harness/certs
bash generate_fake_certs.sh
cd ../../..
```

### 4. Subir o SAS MVP (portas 9000 / 9001)

```bash
cd sas_mvp_core
python main.py
```

Isso inicia:

- `https://0.0.0.0:9000` — mTLS RSA (CBSD, Admin, SAS-SAS RSA)
- `https://0.0.0.0:9001` — mTLS ECDSA (ex.: SSS_3 / SSS_4)

Mantenha o processo ativo em um terminal enquanto roda o harness em outro.

---

## Como Validar com os Testes Oficiais (WInnForum Harness)

Este repositório **já embute** o harness em `src/harness/`. Se preferir a fonte oficial:

```bash
git clone https://github.com/Wireless-Innovation-Forum/CBRS-SAS-Test-Harness.git
```

(Em seguida, aponte a configuração e os certificados para o UUT local, ou use o `src/harness` deste projeto.)

### Configurar `sas.cfg`

Arquivo: [`src/harness/sas.cfg`](src/harness/sas.cfg)

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

Resumo:

| Interface | Base URL | Versão |
|-----------|----------|--------|
| Admin (teste) | `localhost:9000` | — |
| CBSD ↔ SAS | `localhost:9000` / `:9001` | **v1.2** |
| SAS ↔ SAS | `localhost:9000` / `:9001` | **v1.3** |

### Rodar as suítes

Com o UUT no ar e o venv ativo:

```bash
cd src/harness

# Exemplo: Registration
python3 -m unittest testcases.WINNF_FT_S_REG_testcase -v

# Outras suítes CBSD-SAS
python3 -m unittest testcases.WINNF_FT_S_SIQ_testcase -v
python3 -m unittest testcases.WINNF_FT_S_GRA_testcase -v
python3 -m unittest testcases.WINNF_FT_S_HBT_testcase -v
python3 -m unittest testcases.WINNF_FT_S_RLQ_testcase -v
python3 -m unittest testcases.WINNF_FT_S_DRG_testcase -v

# Federação e segurança
python3 -m unittest testcases.WINNF_FT_S_FAD_testcase -v
python3 -m unittest testcases.WINNF_FT_S_SSS_testcase -v

# Borda / federal
python3 -m unittest testcases.WINNF_FT_S_EXZ_testcase -v
python3 -m unittest testcases.WINNF_FT_S_BPR_testcase -v
python3 -m unittest testcases.WINNF_FT_S_EPR_testcase -v
python3 -m unittest testcases.WINNF_FT_S_QPR_testcase -v
python3 -m unittest testcases.WINNF_FT_S_WDB_testcase -v
python3 -m unittest testcases.WINNF_FT_S_FDB_testcase -v
```

Caso isolado (exemplo FAD_2):

```bash
python3 -m unittest testcases.WINNF_FT_S_FAD_testcase.FullActivityDumpTestcase.test_WINNF_FT_S_FAD_2 -v
```

---

## Estrutura do Projeto (resumo)

```
sas_mvp_core/          # UUT — FastAPI + SQLite + CPAS
src/harness/           # WInnForum Test Harness (WINNF-TS-0061)
src/harness/sas.cfg    # URLs e versões apontando para o UUT
prompts/               # Fases de implementação / documentação
```

---

## Licença e Atribuição

O *harness* e modelos de referência em `src/` seguem a licença e autoria do [Wireless Innovation Forum](https://github.com/Wireless-Innovation-Forum). O MVP em `sas_mvp_core/` é um artefato de pesquisa para benchmark de sistemas SAS centralizados.
