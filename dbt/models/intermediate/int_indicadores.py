"""Indicadores por ticker sobre o histórico inteiro, com o OHLC ajustado.

Única fonte de verdade: stock_pipeline.indicators.processar_indicadores (a mesma
função do app, testada contra a lib `ta`). Nada de RSI reimplementado em SQL.
"""
import pandas as pd

from stock_pipeline.indicators import processar_indicadores

SAIDA = {
    "SMA_20": "sma_20",
    "SMA_50": "sma_50",
    "Bollinger_Upper": "bollinger_sup",
    "Bollinger_Lower": "bollinger_inf",
    "RSI": "rsi_14",
    "Retorno_Diario": "retorno_diario",
    "Volatilidade_Anual": "volatilidade_anual",
}


def model(dbt, session):
    dbt.config(materialized="table")
    base = dbt.ref("int_cotacoes_ajustadas").df()
    entrada = base.rename(columns={
        "open_ajustado": "abertura", "high_ajustado": "maxima",
        "low_ajustado": "minima", "adj_close": "fechamento",
    })[["ticker", "data", "abertura", "maxima", "minima", "fechamento", "volume"]]

    partes = []
    for _, df in entrada.groupby("ticker", sort=True):
        df = df.sort_values("data").reset_index(drop=True)
        calc, _ = processar_indicadores(df)
        partes.append(calc[["ticker", "data", *SAIDA]].rename(columns=SAIDA))
    saida = pd.concat(partes, ignore_index=True)
    saida["data"] = saida["data"].dt.date  # DATE no DuckDB, como o resto do gold
    return saida
