"""Gold pequeno e determinístico, escrito em disco, para testar leitura_gold e o app sem rede.

Tem o mesmo esquema de `fato_cotacao_diaria`/`dim_ativo` publicados na Release. Os
indicadores saem de `processar_indicadores` sobre o histórico inteiro (como o dbt faz),
e o preço bruto difere do ajustado (fator_ajuste < 1) para pegar troca de coluna.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from stock_pipeline.config import TICKER_MAP
from stock_pipeline.indicators import processar_indicadores

ULTIMA_DATA = {"B3": pd.Timestamp("2026-11-19"), "NYSE-NASDAQ": pd.Timestamp("2026-11-20")}
PREGOES = 300

LAST_RUN = {
    "iniciado_em_utc": "2026-11-22T18:16:59+00:00",
    "iniciado_em_brt": "2026-11-22T15:16:59-03:00",
    "status": "ok",
    "run_url": "https://github.com/Daviramos7/stock_data_pipeline/actions/runs/1",
}


def _bolsa(ticker: str) -> str:
    return "B3" if ticker.endswith(".SA") else "NYSE-NASDAQ"


def montar_fato() -> pd.DataFrame:
    partes = []
    for i, ticker in enumerate(TICKER_MAP):
        bolsa = _bolsa(ticker)
        datas = pd.bdate_range(end=ULTIMA_DATA[bolsa], periods=PREGOES)
        rng = np.random.default_rng(100 + i)
        adj = 30.0 * np.exp(np.cumsum(rng.normal(0, 0.02, PREGOES)))
        base = pd.DataFrame({
            "data": datas,
            "abertura": adj * (1 + rng.normal(0, 0.005, PREGOES)),
            "fechamento": adj,
            "volume": rng.integers(1_000_000, 9_000_000, PREGOES),
        })
        base["maxima"] = base[["abertura", "fechamento"]].max(axis=1) * 1.01
        base["minima"] = base[["abertura", "fechamento"]].min(axis=1) * 0.99
        ind, _ = processar_indicadores(base)
        fator = 0.9
        partes.append(pd.DataFrame({
            "ticker": ticker,
            "data": ind["data"].dt.date,  # no parquet real `data` é date, não timestamp
            "bolsa": bolsa,
            "open": ind["abertura"] / fator,
            "high": ind["maxima"] / fator,
            "low": ind["minima"] / fator,
            "close": ind["fechamento"] / fator,
            "adj_close": ind["fechamento"],
            "fator_ajuste": fator,
            "open_ajustado": ind["abertura"],
            "high_ajustado": ind["maxima"],
            "low_ajustado": ind["minima"],
            "volume": ind["volume"].astype("int64"),
            "dividends": 0.0,
            "splits": 0.0,
            "retorno_diario": ind["Retorno_Diario"],
            "sma_20": ind["SMA_20"],
            "sma_50": ind["SMA_50"],
            "bollinger_sup": ind["Bollinger_Upper"],
            "bollinger_inf": ind["Bollinger_Lower"],
            "rsi_14": ind["RSI"],
            "volatilidade_anual": ind["Volatilidade_Anual"],
            "ingest_date": "2026-11-22",
        }))
    return pd.concat(partes, ignore_index=True)


def montar_dim_ativo() -> pd.DataFrame:
    return pd.DataFrame([
        {"ticker": t, "nome": n, "bolsa": _bolsa(t),
         "mercado": "BR" if t.endswith(".SA") else "EUA",
         "moeda": "BRL" if t.endswith(".SA") else "USD",
         "fuso": "America/Sao_Paulo" if t.endswith(".SA") else "America/New_York"}
        for t, n in TICKER_MAP.items()
    ])


def escrever_gold(destino: Path, fato: pd.DataFrame | None = None,
                  dim_ativo: pd.DataFrame | None = None, last_run: dict | None = LAST_RUN) -> Path:
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    (montar_fato() if fato is None else fato).to_parquet(destino / "fato_cotacao_diaria.parquet")
    (montar_dim_ativo() if dim_ativo is None else dim_ativo).to_parquet(destino / "dim_ativo.parquet")
    if last_run is not None:
        (destino / "last_run.json").write_text(json.dumps(last_run), encoding="utf-8")
    return destino
