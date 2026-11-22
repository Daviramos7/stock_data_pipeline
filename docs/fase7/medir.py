"""Fase 7: mede o app lendo do gold público (rede) e compara com o app antigo (yfinance).

Da raiz:  $env:PYTHONIOENCODING="utf-8"; .\\venv\\Scripts\\python.exe docs\\fase7\\medir.py
Imprime Markdown (as tabelas de docs/fase7/medicoes.md). Usa o GOLD_BASE_URL padrão (Release data-latest).
"""
from __future__ import annotations

import os
import platform
import statistics
import sys
import time
from datetime import timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

from stock_pipeline.indicators import processar_indicadores  # noqa: E402
from stock_pipeline.ingestion import baixar_cotacoes  # noqa: E402
from stock_pipeline.leitura_gold import base_url, carregar_gold, serie_do_ticker  # noqa: E402

APP = str(RAIZ / "dashboard.py")
REPS = 5


def cronometro(f):
    t = time.perf_counter()
    r = f()
    return time.perf_counter() - t, r


def rodar_app():
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception, at.exception
    fonte = " ".join(m.value for m in at.sidebar.markdown)
    assert "gold (pipeline diário)" in fonte, "app caiu no fallback durante a medição"
    return at


def medir_tempos():
    os.environ.pop("GOLD_BASE_URL", None)
    so_gold, frio, quente = [], [], []
    for _ in range(REPS):
        st.cache_data.clear()
        so_gold.append(cronometro(carregar_gold)[0])
        st.cache_data.clear()
        frio.append(cronometro(rodar_app)[0])
        quente.append(cronometro(rodar_app)[0])  # cache do carregar_gold já cheio
    return so_gold, frio, quente


def medir_app_antigo():
    """Mesmo dashboard com o gold forçado a falhar: caminho antigo (yfinance na hora)."""
    os.environ["GOLD_BASE_URL"] = str(RAIZ / "_gold_inexistente_para_medicao")
    tempos = []
    try:
        for _ in range(REPS):
            st.cache_data.clear()
            t, at = cronometro(lambda: AppTest.from_file(APP, default_timeout=120).run())
            assert not at.exception, at.exception
            assert "yfinance ao vivo (fallback)" in " ".join(m.value for m in at.sidebar.markdown)
            assert len(at.metric) == 4
            tempos.append(t)
    finally:
        os.environ.pop("GOLD_BASE_URL", None)
    return tempos


def linha_tempo(nome, xs):
    fmt = ", ".join(f"{x:.2f}" for x in xs)
    return f"| {nome} | {statistics.median(xs):.2f} | {min(xs):.2f} | {max(xs):.2f} | {fmt} |"


def comparar(fato, ticker):
    fim = fato.loc[fato["ticker"] == ticker, "data"].max().date()
    inicio = fim - timedelta(days=365)
    novo = serie_do_ticker(fato, ticker, inicio, fim)
    bruto, _ = baixar_cotacoes(ticker, inicio, fim)
    antigo, _ = processar_indicadores(bruto.sort_values("data"))
    return inicio, fim, novo.reset_index(drop=True), antigo.reset_index(drop=True)


def main():
    print(f"- Data: {pd.Timestamp.now(tz='America/Sao_Paulo'):%Y-%m-%d %H:%M} BRT")
    print(f"- Máquina: {platform.platform()}, {platform.processor()}, Python {platform.python_version()}")
    print(f"- Gold: `{base_url()}`")
    print(f"- streamlit {st.__version__}, pandas {pd.__version__}\n")

    so_gold, frio, quente = medir_tempos()
    antigo = medir_app_antigo()
    print(f"## Tempo de abrir ({REPS} repetições, segundos)\n")
    print("| Medida | Mediana | Mín | Máx | Repetições |")
    print("| --- | ---: | ---: | ---: | --- |")
    print(linha_tempo("`carregar_gold()` sozinho (download + leitura)", so_gold))
    print(linha_tempo("App frio (cache vazio): AppTest `run()` completo", frio))
    print(linha_tempo("App quente (gold em cache): AppTest `run()` completo", quente))
    print(linha_tempo("App antigo frio (fallback forçado: yfinance ao vivo, PETR4 1 ano)", antigo))

    fato, _, last_run = carregar_gold()
    print(f"\nGold lido: {len(fato)} linhas no fato; last_run {last_run.get('iniciado_em_brt')} "
          f"status `{last_run.get('status')}`.\n")

    print("## KPIs do último pregão: app novo (gold) × app antigo (yfinance ao vivo)\n")
    print("| Ticker | Janela | Último pregão (novo / antigo) | Métrica | Novo (gold) | Antigo (yfinance) | Novo − Antigo |")
    print("| --- | --- | --- | --- | ---: | ---: | ---: |")
    detalhes = {}
    for ticker in ["PETR4.SA", "AAPL"]:
        inicio, fim, novo, antigo = comparar(fato, ticker)
        detalhes[ticker] = (novo, antigo)
        u_n, u_a = novo.iloc[-1], antigo.iloc[-1]
        datas = f"{u_n['data']:%Y-%m-%d} / {u_a['data']:%Y-%m-%d}"
        for nome, col in [("Preço (fechamento ajustado)", "fechamento"), ("SMA20", "SMA_20"),
                          ("RSI(14)", "RSI"), ("Volatilidade anual %", "Volatilidade_Anual")]:
            print(f"| {ticker} | {inicio} a {fim} | {datas} | {nome} | {u_n[col]:.6f} | "
                  f"{u_a[col]:.6f} | {u_n[col] - u_a[col]:+.2e} |")

    print("\n## Começo da janela (onde os dois podem diferir)\n")
    print("| Ticker | n-ésimo pregão | Data | RSI novo | RSI antigo | SMA50 novo | SMA50 antigo |")
    print("| --- | ---: | --- | ---: | ---: | ---: | ---: |")
    for ticker, (novo, antigo) in detalhes.items():
        juntos = novo.merge(antigo, on="data", suffixes=("_n", "_a"))
        for n in [1, 15, 50, 120]:
            if n <= len(juntos):
                r = juntos.iloc[n - 1]
                print(f"| {ticker} | {n} | {r['data']:%Y-%m-%d} | {r['RSI_n']:.4f} | {r['RSI_a']:.4f} | "
                      f"{r['SMA_50_n']:.4f} | {r['SMA_50_a']:.4f} |")
        print(f"| {ticker} | pregões: novo {len(novo)}, antigo {len(antigo)}, em comum {len(juntos)} | | | | | |")


if __name__ == "__main__":
    main()
