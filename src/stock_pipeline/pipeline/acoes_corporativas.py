"""Proventos e desdobramentos: evento novo reescreve o passado (ADR-001, decisão 4).

Se a janela baixada traz dividendo/split numa data em que o silver ainda não tinha
esse evento, o histórico inteiro do ticker é rebaixado desde 2015-01-01 (1 chamada
por ticker) e vai pro bronze do dia, onde ganha das versões antigas no dedup.
"""
from datetime import date

import pandas as pd

from .esquema import vazio_longo
from .fetch import FalhaDownload, baixar_bruto

INICIO_HISTORICO = date(2015, 1, 1)


def _eventos(df: pd.DataFrame) -> pd.DataFrame:
    linhas = []
    for tipo, coluna in (("dividendo", "dividends"), ("split", "splits")):
        com_evento = df[df[coluna].fillna(0) > 0]
        linhas.append(pd.DataFrame({
            "ticker": com_evento["ticker"], "data": com_evento["data"],
            "tipo": tipo, "valor": com_evento[coluna],
        }))
    return pd.concat(linhas, ignore_index=True)


def detectar_novas(janela: pd.DataFrame, silver: pd.DataFrame) -> dict[str, list[dict]]:
    """Eventos da janela cujo (ticker, data, tipo) ainda não existe no silver."""
    novos = _eventos(janela)
    if novos.empty:
        return {}
    conhecidos = _eventos(silver)[["ticker", "data", "tipo"]]
    novos = novos.merge(conhecidos, on=["ticker", "data", "tipo"], how="left", indicator=True)
    novos = novos[novos["_merge"] == "left_only"].sort_values(["ticker", "data", "tipo"])
    resultado: dict[str, list[dict]] = {}
    for linha in novos.itertuples(index=False):
        resultado.setdefault(linha.ticker, []).append(
            {"data": linha.data.isoformat(), "tipo": linha.tipo, "valor": float(linha.valor)})
    return resultado


def rebaixar_historicos(tickers, fim: date, *, hoje: date, fetcher=None, sleep=None
                        ) -> tuple[pd.DataFrame, dict[str, str]]:
    """Rebaixa [2015-01-01, fim) de cada ticker. Devolve (dados, falhas por ticker)."""
    partes, falhas = [], {}
    extra = {"sleep": sleep} if sleep else {}
    for ticker in tickers:
        try:
            dados = baixar_bruto([ticker], INICIO_HISTORICO, fim, hoje=hoje, fetcher=fetcher, **extra)
        except FalhaDownload as erro:
            falhas[ticker] = f"rebaixa falhou: {erro}"
            continue
        partes.append(dados[dados["ticker"] == ticker])
    if not partes:
        return vazio_longo(), falhas
    return pd.concat(partes, ignore_index=True), falhas
