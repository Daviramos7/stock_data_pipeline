"""Orquestrador da Fase 5: ingestão -> dbt build -> export do gold -> last_run.json.

    python -m stock_pipeline.pipeline.cli --data-dir data orquestrar --modo diario
    python -m stock_pipeline.pipeline.cli --data-dir data orquestrar --modo backfill --inicio 2015-01-01

Regra: se QUALQUER etapa falhar, para ali, o status é "falha" e o arquivo
`<base>/PUBLICAR` NÃO existe (o workflow só sobe pra Release quando ele existe).
Um PUBLICAR velho de outra execução é apagado logo no começo.

Cada etapa é uma função injetável (os testes trocam por fakes, sem rede e sem dbt).
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import pyarrow.parquet as pq

from . import gold
from .fetch import janela_diaria
from .silver import caminho_silver

log = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parents[3]
DIR_DBT = RAIZ / "dbt"
BRT = ZoneInfo("America/Sao_Paulo")
INICIO_BACKFILL = date(2015, 1, 1)  # ADR-001, decisão 8
LOOKBACK_DIAS = 7
ETAPAS = ("ingestao", "dbt", "export")


class FalhaEtapa(RuntimeError):
    """Uma etapa terminou, mas com resultado que impede publicar."""


@dataclass
class Contexto:
    base: Path
    modo: str
    inicio: date
    fim_exclusivo: date
    hoje: date
    resultado: dict = field(default_factory=dict)  # o que vai pro last_run.json


def caminho_publicar(base: Path) -> Path:
    return Path(base) / "PUBLICAR"


def caminho_last_run(base: Path) -> Path:
    return Path(base) / "last_run.json"


def caminho_warehouse(base: Path) -> Path:
    return Path(base) / "warehouse.duckdb"


def caminho_gold(base: Path) -> Path:
    return Path(base) / "gold"


def janela(modo: str, hoje: date, inicio: date | None, fim: date | None) -> tuple[date, date]:
    """[inicio, fim_exclusivo). No backfill `fim` é inclusivo e o padrão é ontem."""
    if modo == "diario":
        return janela_diaria(hoje, LOOKBACK_DIAS)
    if modo == "backfill":
        inicio = inicio or INICIO_BACKFILL
        fim = fim or (hoje - timedelta(days=1))
        return inicio, fim + timedelta(days=1)
    raise ValueError(f"modo desconhecido: {modo!r}")


# --- etapas padrão -------------------------------------------------------------

def ingestao_padrao(ctx: Contexto) -> None:
    from .cli import executar  # import tardio: cli importa este módulo

    execucao = executar(ctx.base, modo=ctx.modo, inicio=ctx.inicio, fim=ctx.fim_exclusivo,
                        hoje=ctx.hoje)
    ctx.resultado["tickers_ok"] = execucao["tickers_ok"]
    ctx.resultado["tickers_falha"] = execucao["tickers_falha"]
    ctx.resultado["falhas_rebaixa"] = execucao["falhas_rebaixa"]
    ctx.resultado["linhas_silver"] = execucao["linhas_silver"]
    if execucao["tickers_falha"] or execucao["falhas_rebaixa"]:
        raise FalhaEtapa(f"tickers com falha: {sorted(execucao['tickers_falha'])} "
                         f"rebaixa: {sorted(execucao['falhas_rebaixa'])}")


def _executavel_dbt() -> str:
    nome = "dbt.exe" if os.name == "nt" else "dbt"
    vizinho = Path(sys.executable).with_name(nome)  # o dbt do mesmo venv
    if vizinho.exists():
        return str(vizinho)
    achado = shutil.which("dbt")
    if not achado:
        raise FalhaEtapa("executável do dbt não encontrado")
    return achado


def contar_dbt(run_results: Path) -> dict[str, int]:
    """pass/warn/error/skip a partir do target/run_results.json do dbt."""
    contagem = {"pass": 0, "warn": 0, "error": 0, "skip": 0}
    mapa = {"pass": "pass", "success": "pass", "warn": "warn",
            "error": "error", "fail": "error", "runtime error": "error", "skipped": "skip"}
    for r in json.loads(run_results.read_text(encoding="utf-8"))["results"]:
        contagem[mapa.get(r["status"], "error")] += 1
    return contagem


def dbt_padrao(ctx: Contexto) -> None:
    """`dbt build` com cwd dbt/. Exit != 0 (ERROR) falha; WARN passa."""
    base = ctx.base.resolve()
    alvo = base / "_dbt" / "target"  # fora do repo: um base temporário não suja dbt/target
    env = {**os.environ,
           "SILVER_PATH": caminho_silver(base).as_posix(),
           "DUCKDB_PATH": caminho_warehouse(base).as_posix()}
    run_results = alvo / "run_results.json"
    run_results.unlink(missing_ok=True)  # nunca contar o resultado de uma rodada velha
    cmd = [_executavel_dbt(), "build", "--profiles-dir", ".",
           "--target-path", str(alvo), "--log-path", str(base / "_dbt" / "logs")]
    proc = subprocess.run(cmd, cwd=DIR_DBT, env=env, text=True, encoding="utf-8",
                          errors="replace", capture_output=True)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if run_results.exists():
        ctx.resultado["dbt"] = contar_dbt(run_results)
    if proc.returncode != 0:
        raise FalhaEtapa(f"dbt build saiu com código {proc.returncode}")
    if ctx.resultado.get("dbt", {}).get("error"):
        raise FalhaEtapa("dbt build com ERROR")


def export_padrao(ctx: Contexto) -> None:
    linhas = gold.exportar(caminho_warehouse(ctx.base), caminho_gold(ctx.base))
    ctx.resultado["linhas_gold"] = linhas
    ctx.resultado["linhas_fato"] = linhas["fato_cotacao_diaria"]


# --- orquestração --------------------------------------------------------------

def _github(env) -> dict:
    sha = env.get("GITHUB_SHA")
    url = None
    if env.get("GITHUB_RUN_ID") and env.get("GITHUB_REPOSITORY"):
        servidor = env.get("GITHUB_SERVER_URL", "https://github.com")
        url = f"{servidor}/{env['GITHUB_REPOSITORY']}/actions/runs/{env['GITHUB_RUN_ID']}"
    return {"commit_sha": sha, "run_url": url}


def _linhas_silver(base: Path) -> int | None:
    caminho = caminho_silver(base)
    if not caminho.exists():
        return None
    return pq.ParquetFile(caminho).metadata.num_rows


def gravar_json_atomico(caminho: Path, dados: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, caminho)


def orquestrar(base: Path, *, modo: str, inicio: date | None = None, fim: date | None = None,
               hoje: date | None = None,
               ingestao: Callable[[Contexto], None] = ingestao_padrao,
               dbt: Callable[[Contexto], None] = dbt_padrao,
               export: Callable[[Contexto], None] = export_padrao,
               agora: Callable[[], datetime] | None = None,
               env=None) -> dict:
    """Roda as etapas em ordem e grava last_run.json (sempre) e PUBLICAR (só no sucesso)."""
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    caminho_publicar(base).unlink(missing_ok=True)
    env = os.environ if env is None else env
    agora = agora or (lambda: datetime.now(timezone.utc))
    hoje = hoje or date.today()

    t0 = time.perf_counter()
    instante = agora().astimezone(timezone.utc)
    ini, fim_excl = janela(modo, hoje, inicio, fim)
    ctx = Contexto(base=base, modo=modo, inicio=ini, fim_exclusivo=fim_excl, hoje=hoje)
    ctx.resultado.update({
        "iniciado_em_utc": instante.isoformat(timespec="seconds"),
        "iniciado_em_brt": instante.astimezone(BRT).isoformat(timespec="seconds"),
        "modo": modo,
        "inicio": ini.isoformat(),
        "fim_exclusivo": fim_excl.isoformat(),
        "status": None,
        "etapa_falhou": None,
        "erro": None,
        "linhas_silver": None,
        "linhas_fato": None,
        "tickers_ok": [],
        "tickers_falha": {},
        "dbt": {"pass": 0, "warn": 0, "error": 0, "skip": 0},
        "duracao_s": {},
        **_github(env),
    })

    for nome, etapa in zip(ETAPAS, (ingestao, dbt, export)):
        t_etapa = time.perf_counter()
        try:
            etapa(ctx)
        except Exception as erro:  # qualquer erro numa etapa = execução não publicável
            log.exception("etapa %s falhou", nome)
            ctx.resultado.update(status="falha", etapa_falhou=nome,
                                 erro=f"{type(erro).__name__}: {erro}")
            break
        finally:
            ctx.resultado["duracao_s"][nome] = round(time.perf_counter() - t_etapa, 3)
    else:
        ctx.resultado["status"] = "ok"

    if ctx.resultado["linhas_silver"] is None:
        ctx.resultado["linhas_silver"] = _linhas_silver(base)
    ctx.resultado["duracao_s"]["total"] = round(time.perf_counter() - t0, 3)
    gravar_json_atomico(caminho_last_run(base), ctx.resultado)
    if ctx.resultado["status"] == "ok":
        caminho_publicar(base).write_text(ctx.resultado["iniciado_em_utc"] + "\n", encoding="utf-8")
    return ctx.resultado
