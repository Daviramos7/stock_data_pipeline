"""Leitura do gold publicado na Release `data-latest` (Fase 7).

O app lê daqui em vez de baixar do yfinance na hora. Só usa stdlib + pandas/pyarrow
(o que o Streamlit Cloud já instala): nada de dbt, duckdb ou fsspec.

`GOLD_BASE_URL` pode ser uma URL http(s) ou um caminho local (usado nos testes).
"""
from __future__ import annotations

import io
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

GOLD_BASE_URL_PADRAO = (
    "https://github.com/Daviramos7/stock_data_pipeline/releases/download/data-latest"
)
TIMEOUT_S = 10
TENTATIVAS = 2
ESPERA_ENTRE_TENTATIVAS_S = 1.0

COLUNAS_FATO = {
    "ticker", "data", "bolsa", "open_ajustado", "high_ajustado", "low_ajustado",
    "adj_close", "volume", "sma_20", "sma_50", "bollinger_sup", "bollinger_inf",
    "rsi_14", "retorno_diario", "volatilidade_anual",
}
COLUNAS_DIM_ATIVO = {"ticker", "nome", "bolsa", "moeda"}

# gold -> nome que o app (processar_indicadores / charts) usa hoje.
# OHLC ajustado + adj_close equivalem ao auto_adjust=True do app antigo.
MAPA_COLUNAS_APP = {
    "data": "data",
    "open_ajustado": "abertura",
    "high_ajustado": "maxima",
    "low_ajustado": "minima",
    "adj_close": "fechamento",
    "volume": "volume",
    "sma_20": "SMA_20",
    "sma_50": "SMA_50",
    "bollinger_sup": "Bollinger_Upper",
    "bollinger_inf": "Bollinger_Lower",
    "rsi_14": "RSI",
    "retorno_diario": "Retorno_Diario",
    "volatilidade_anual": "Volatilidade_Anual",
}
COLUNAS_APP = list(MAPA_COLUNAS_APP.values())


class GoldIndisponivel(Exception):
    """O gold não pôde ser baixado/lido ou veio sem as colunas mínimas."""


def base_url() -> str:
    return os.environ.get("GOLD_BASE_URL", "").strip() or GOLD_BASE_URL_PADRAO


def _eh_http(base: str) -> bool:
    return base.lower().startswith(("http://", "https://"))


def _baixar(base: str, nome: str) -> bytes:
    """Bytes de `<base>/<nome>`. HTTP: timeout de 10 s e 2 tentativas."""
    if not _eh_http(base):
        caminho = Path(base.removeprefix("file://")) / nome
        try:
            return caminho.read_bytes()
        except OSError as e:
            raise GoldIndisponivel(f"não consegui ler {caminho}: {e}") from e

    url = f"{base.rstrip('/')}/{nome}"
    ultimo_erro: Exception | None = None
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "stock-data-pipeline-app"})
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            ultimo_erro = e
            if tentativa < TENTATIVAS:
                time.sleep(ESPERA_ENTRE_TENTATIVAS_S)
    raise GoldIndisponivel(f"falha ao baixar {url} após {TENTATIVAS} tentativas: {ultimo_erro}")


def _ler_parquet(dados: bytes, nome: str, colunas: set[str]) -> pd.DataFrame:
    try:
        df = pd.read_parquet(io.BytesIO(dados))
    except Exception as e:  # pyarrow levanta tipos variados para arquivo corrompido
        raise GoldIndisponivel(f"{nome} não é um parquet legível: {e}") from e
    faltando = colunas - set(df.columns)
    if faltando:
        raise GoldIndisponivel(f"{nome} sem colunas obrigatórias: {sorted(faltando)}")
    if df.empty:
        raise GoldIndisponivel(f"{nome} está vazio")
    return df


def carregar_gold(base: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Baixa e valida o gold. Devolve (fato, dim_ativo, last_run).

    `last_run.json` é informativo (barra lateral): se faltar, vem `{}` em vez de erro,
    porque os dados em si continuam válidos. Fato e dim_ativo são obrigatórios.
    """
    base = base or base_url()
    fato = _ler_parquet(
        _baixar(base, "fato_cotacao_diaria.parquet"), "fato_cotacao_diaria", COLUNAS_FATO
    )
    dim_ativo = _ler_parquet(_baixar(base, "dim_ativo.parquet"), "dim_ativo", COLUNAS_DIM_ATIVO)
    fato["data"] = pd.to_datetime(fato["data"])

    try:
        last_run = json.loads(_baixar(base, "last_run.json").decode("utf-8"))
        if not isinstance(last_run, dict):
            last_run = {}
    except (GoldIndisponivel, ValueError):
        last_run = {}
    return fato, dim_ativo, last_run


def serie_do_ticker(fato: pd.DataFrame, ticker: str, inicio, fim) -> pd.DataFrame:
    """Série do ticker no formato do app, com indicadores do gold (histórico inteiro).

    O filtro de período vem DEPOIS dos indicadores, então o começo da janela já
    vem "aquecido" (docs/fase4/comparacao_app_gold.md). Ticker sem linhas → DataFrame vazio.
    """
    df = fato.loc[fato["ticker"] == ticker, list(MAPA_COLUNAS_APP)].rename(columns=MAPA_COLUNAS_APP)
    df["data"] = pd.to_datetime(df["data"])
    df = df.sort_values("data")
    mascara = (df["data"] >= pd.Timestamp(inicio)) & (df["data"] <= pd.Timestamp(fim))
    return df.loc[mascara, COLUNAS_APP].reset_index(drop=True)


def ultima_data_por_bolsa(fato: pd.DataFrame) -> dict[str, pd.Timestamp]:
    return {b: pd.Timestamp(d) for b, d in fato.groupby("bolsa")["data"].max().items()}
