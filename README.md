# SAS MVP Core

Backend MVP de Spectrum Access System (FastAPI + SQLite) para benchmark contra a suíte WINNF.

## Subir o servidor

```bash
cd sas_mvp_core
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

O servidor escuta em `https://0.0.0.0:9000` usando os certificados de `src/harness/certs/` (gere com `bash generate_fake_certs.sh` se necessário). mTLS de negócio não é validado — o transporte HTTPS basta para o harness.

## Rodar testes de Registration

Com o servidor ativo:

```bash
cd src/harness && python -m unittest testcases.WINNF_FT_S_REG_testcase -v
```
