"""Log de execução em data/_runs/<ingest_date>.json.

Cada execução do dia é ANEXADA à lista `execucoes`: rodar de novo no mesmo dia não
apaga o registro de uma falha anterior.
"""
import json
import os
from datetime import date
from pathlib import Path


def caminho_log(base: Path, ingest_date: date) -> Path:
    return Path(base) / "_runs" / f"{ingest_date.isoformat()}.json"


def ler_log(base: Path, ingest_date: date) -> dict:
    caminho = caminho_log(base, ingest_date)
    if not caminho.exists():
        return {"ingest_date": ingest_date.isoformat(), "execucoes": []}
    return json.loads(caminho.read_text(encoding="utf-8"))


def registrar(base: Path, ingest_date: date, execucao: dict) -> Path:
    log = ler_log(base, ingest_date)
    log["execucoes"].append(execucao)
    caminho = caminho_log(base, ingest_date)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, caminho)
    return caminho
