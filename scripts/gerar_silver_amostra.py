"""Gera um silver SINTÉTICO, pequeno e determinístico, para o job `dbt` do CI (sem rede).

2 tickers (PETR4.SA na B3, AAPL na NYSE), N pregões cada a partir de 2026-05-04,
seguindo dbt/seeds/dim_calendario.csv (então os testes de pregão faltando e de
linha em dia sem pregão têm que passar). Passeio aleatório com seed fixa, um
dividendo por ticker (adj_close < close antes da data-ex) e OHLC coerente
(low <= open/close <= high). Mesmo esquema de data/silver/cotacoes.parquet.

Uso: python scripts/gerar_silver_amostra.py --saida data/amostra/cotacoes.parquet [--pregoes 120]
"""
from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
CALENDARIO = RAIZ / "dbt" / "seeds" / "dim_calendario.csv"
TICKERS = {"PETR4.SA": ("B3", 30.0, 0.8), "AAPL": ("NYSE-NASDAQ", 200.0, 0.25)}
INICIO = "2026-05-04"


def pregoes(bolsa: str, n: int) -> list[date]:
    with CALENDARIO.open(encoding="utf-8", newline="") as f:
        dias = [r["data"] for r in csv.DictReader(f)
                if r["bolsa"] == bolsa and r["eh_pregao"] == "true" and r["data"] >= INICIO]
    return [date.fromisoformat(d) for d in sorted(dias)[:n]]


def gerar(n: int) -> pd.DataFrame:
    rng = np.random.default_rng(20261122)
    partes = []
    for ticker, (bolsa, preco0, dividendo) in TICKERS.items():
        datas = pregoes(bolsa, n)
        ret = rng.normal(0.0005, 0.015, len(datas))
        close = preco0 * np.cumprod(1 + ret)
        open_ = close * (1 + rng.normal(0, 0.005, len(datas)))
        high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.01, len(datas)))
        low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.01, len(datas)))
        div = np.zeros(len(datas))
        ex = len(datas) // 2
        div[ex] = dividendo
        # Ajuste por provento como o Yahoo: antes da data-ex, fator = 1 - div / close do dia anterior.
        fator = np.ones(len(datas))
        fator[:ex] = 1 - dividendo / close[ex - 1]
        partes.append(pd.DataFrame({
            "ticker": ticker, "data": datas,
            "open": open_, "high": high, "low": low, "close": close, "adj_close": close * fator,
            "volume": rng.integers(1_000_000, 50_000_000, len(datas)).astype("int64"),
            "dividends": div, "splits": 0.0, "ingest_date": date(2026, 11, 22),
        }))
    return pd.concat(partes, ignore_index=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--saida", type=Path, required=True)
    p.add_argument("--pregoes", type=int, default=120)
    a = p.parse_args()
    df = gerar(a.pregoes)
    a.saida.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(a.saida, index=False)
    print(f"{a.saida}: {len(df)} linhas, {df.ticker.nunique()} tickers, {df.data.min()} a {df.data.max()}")


if __name__ == "__main__":
    main()
