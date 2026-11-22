"""Linha de comando do pipeline.

    python -m stock_pipeline.pipeline.cli diario
    python -m stock_pipeline.pipeline.cli backfill --inicio 2015-01-01 --fim 2026-11-21
    python -m stock_pipeline.pipeline.cli orquestrar --modo diario|backfill [--inicio --fim]

`orquestrar` (Fase 5) encadeia ingestão, dbt build e export do gold; ver orquestrar.py.

`--fim` do backfill é o último dia INCLUSIVO (é cortado pra ontem se passar).
Sai com código 1 se algum ticker falhou (útil pro alerta da Fase 5).
"""
import argparse
import json
import logging
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from ..config import TICKER_MAP
from .acoes_corporativas import detectar_novas, rebaixar_historicos
from .bronze import gravar_bronze
from .fetch import FalhaDownload, baixar_bruto, fim_exclusivo_seguro, janela_diaria
from .run_log import registrar
from .silver import construir_silver, ler_silver

TICKERS = list(TICKER_MAP)
LOOKBACK_DIAS = 7


def executar(base: Path, *, modo: str, inicio: date, fim: date, hoje: date | None = None,
             tickers=None, fetcher=None, sleep=None) -> dict:
    """Roda uma ingestão [inicio, fim) e reconstrói o silver. `fim` é exclusivo."""
    t0 = time.perf_counter()
    hoje = hoje or date.today()
    tickers = list(tickers or TICKERS)
    fim = fim_exclusivo_seguro(fim, hoje)
    extra = {"sleep": sleep} if sleep else {}
    base = Path(base)

    silver_antes = ler_silver(base)
    falhas: dict[str, str] = {}
    try:
        janela = baixar_bruto(tickers, inicio, fim, hoje=hoje, fetcher=fetcher, **extra)
    except FalhaDownload as erro:
        janela = None
        falhas = {t: f"download falhou: {erro}" for t in tickers}

    linhas = {}
    if janela is not None:
        janela = janela[janela["ticker"].isin(tickers)]
        linhas = {t: int(n) for t, n in janela["ticker"].value_counts().sort_index().items()}
        falhas.update({t: "retorno vazio pra este ticker" for t in tickers if t not in linhas})
        if linhas:
            gravar_bronze(janela, base, hoje)

    acoes, rebaixados, falhas_rebaixa = {}, [], {}
    if modo == "diario" and linhas:
        acoes = detectar_novas(janela, silver_antes)
        if acoes:
            historico, falhas_rebaixa = rebaixar_historicos(
                sorted(acoes), fim, hoje=hoje, fetcher=fetcher, sleep=sleep)
            if not historico.empty:
                gravar_bronze(historico, base, hoje)
                rebaixados = sorted(historico["ticker"].unique().tolist())

    silver, rejeitadas = construir_silver(base)

    execucao = {
        "modo": modo,
        "iniciado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
        "inicio": inicio.isoformat(),
        "fim_exclusivo": fim.isoformat(),
        "tickers_ok": sorted(linhas),
        "tickers_falha": dict(sorted(falhas.items())),
        "linhas_baixadas": linhas,
        "acoes_corporativas": acoes,
        "historicos_rebaixados": rebaixados,
        "falhas_rebaixa": falhas_rebaixa,
        "linhas_silver": int(len(silver)),
        "linhas_rejeitadas": int(len(rejeitadas)),
        "duracao_s": round(time.perf_counter() - t0, 3),
    }
    registrar(base, hoje, execucao)
    return execucao


def _data(texto: str) -> date:
    return date.fromisoformat(texto)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="stock_pipeline.pipeline.cli")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("diario", help=f"reprocessa os últimos {LOOKBACK_DIAS} dias corridos")
    backfill = sub.add_parser("backfill", help="baixa um intervalo inteiro")
    backfill.add_argument("--inicio", type=_data, required=True)
    backfill.add_argument("--fim", type=_data, required=True, help="último dia, inclusivo")
    orq = sub.add_parser("orquestrar", help="ingestão + dbt build + export do gold + last_run.json")
    orq.add_argument("--modo", choices=["diario", "backfill"], default="diario")
    orq.add_argument("--inicio", type=_data, help="backfill: padrão 2015-01-01")
    orq.add_argument("--fim", type=_data, help="backfill: último dia, inclusivo (padrão ontem)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if args.comando == "orquestrar":
        from .orquestrar import orquestrar

        resultado = orquestrar(args.data_dir, modo=args.modo, inicio=args.inicio, fim=args.fim)
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
        return 0 if resultado["status"] == "ok" else 1
    hoje = date.today()
    if args.comando == "diario":
        inicio, fim = janela_diaria(hoje, LOOKBACK_DIAS)
    else:
        inicio, fim = args.inicio, args.fim + timedelta(days=1)

    execucao = executar(args.data_dir, modo=args.comando, inicio=inicio, fim=fim, hoje=hoje)
    print(json.dumps(execucao, ensure_ascii=False, indent=2))
    return 1 if execucao["tickers_falha"] or execucao["falhas_rebaixa"] else 0


if __name__ == "__main__":
    sys.exit(main())
