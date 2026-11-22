"""Compara o último pregão do gold com o que o app calcula hoje (janela de 1 ano).

Sem rede: a "saída do app" é simulada aplicando processar_indicadores ao adj_close
do silver só na janela [hoje - 365 dias, hoje], que é o padrão da sidebar do
dashboard (auto_adjust=True ⇒ fechamento = adj_close). O gold usa o histórico inteiro.

Uso: python scripts/comparar_app_gold.py --hoje 2026-11-22 [--tickers PETR4.SA AAPL]
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from stock_pipeline.indicators import processar_indicadores

RAIZ = Path(__file__).resolve().parent.parent
CAMPOS = [("fechamento ajustado", "fechamento", "adj_close"), ("SMA20", "SMA_20", "sma_20"),
          ("RSI(14)", "RSI", "rsi_14"), ("Volatilidade anual %", "Volatilidade_Anual", "volatilidade_anual")]


def comparar(ticker: str, hoje: date, silver: pd.DataFrame, gold: pd.DataFrame) -> list[dict]:
    s = silver[(silver.ticker == ticker)].copy()
    s["data"] = pd.to_datetime(s["data"])
    janela = s[(s.data >= pd.Timestamp(hoje - timedelta(days=365))) & (s.data <= pd.Timestamp(hoje))]
    app_in = janela.rename(columns={"adj_close": "fechamento"})[["data", "fechamento"]]
    app, _ = processar_indicadores(app_in.sort_values("data").reset_index(drop=True))
    g = gold[gold.ticker == ticker].sort_values("data")
    ult_app, ult_gold = app.iloc[-1], g.iloc[-1]
    assert ult_app["data"] == pd.Timestamp(ult_gold["data"]), (ult_app["data"], ult_gold["data"])
    out = []
    for rotulo, col_app, col_gold in CAMPOS:
        va, vg = float(ult_app[col_app]), float(ult_gold[col_gold])
        out.append(dict(ticker=ticker, data=ult_gold["data"].date(), metrica=rotulo, app_1ano=va,
                        gold=vg, dif=vg - va, pregoes_janela=len(app)))
    return out


def divergencia_na_janela(ticker, hoje, silver, gold, posicoes=(1, 14, 15, 20, 50, 60, 120, 240)):
    """RSI/SMA50 do app × gold no n-ésimo pregão da janela de 1 ano (onde o início da série pesa)."""
    s = silver[silver.ticker == ticker].copy()
    s["data"] = pd.to_datetime(s["data"])
    janela = s[(s.data >= pd.Timestamp(hoje - timedelta(days=365))) & (s.data <= pd.Timestamp(hoje))]
    app, _ = processar_indicadores(janela.rename(columns={"adj_close": "fechamento"})[["data", "fechamento"]]
                                   .sort_values("data").reset_index(drop=True))
    g = gold[gold.ticker == ticker].set_index("data")
    out = []
    for n in posicoes:
        if n > len(app):
            continue
        linha = app.iloc[n - 1]
        gl = g.loc[linha["data"]]
        out.append(dict(ticker=ticker, n=n, data=linha["data"].date(), rsi_app=linha["RSI"], rsi_gold=gl["rsi_14"],
                        sma50_app=linha["SMA_50"], sma50_gold=gl["sma_50"]))
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hoje", type=date.fromisoformat, default=date.today())
    p.add_argument("--tickers", nargs="+", default=["PETR4.SA", "AAPL"])
    a = p.parse_args()
    silver = pd.read_parquet(RAIZ / "data" / "silver" / "cotacoes.parquet")
    gold = pd.read_parquet(RAIZ / "data" / "gold" / "fato_cotacao_diaria.parquet")
    gold["data"] = pd.to_datetime(gold["data"])
    linhas = [l for t in a.tickers for l in comparar(t, a.hoje, silver, gold)]
    print("| Ticker | Último pregão | Métrica | App (1 ano) | Gold (histórico) | Gold - App | Pregões na janela |")
    print("| --- | --- | --- | ---: | ---: | ---: | ---: |")
    for l in linhas:
        print(f"| {l['ticker']} | {l['data']} | {l['metrica']} | {l['app_1ano']:.6f} | {l['gold']:.6f} "
              f"| {l['dif']:+.2e} | {l['pregoes_janela']} |")
    print()
    print("| Ticker | n-ésimo pregão da janela | Data | RSI app | RSI gold | SMA50 app | SMA50 gold |")
    print("| --- | ---: | --- | ---: | ---: | ---: | ---: |")
    for t in a.tickers:
        for d in divergencia_na_janela(t, a.hoje, silver, gold):
            f = lambda v: "NaN" if pd.isna(v) else f"{v:.4f}"
            print(f"| {d['ticker']} | {d['n']} | {d['data']} | {f(d['rsi_app'])} | {f(d['rsi_gold'])} "
                  f"| {f(d['sma50_app'])} | {f(d['sma50_gold'])} |")


if __name__ == "__main__":
    main()
