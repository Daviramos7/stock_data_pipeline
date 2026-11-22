"""Download bruto em batch (uma chamada pra todos os tickers) com retry.

Comportamento do yfinance 1.8 que molda este módulo (medido em 22/11/2026):
- num batch, ticker que falha NÃO lança exceção: vira coluna toda NaN e só sai um print;
- o índice do batch é a união das datas, então num feriado da B3 o .SA aparece
  com linha toda NaN porque a bolsa americana abriu. Essas linhas são descartadas.
"""
import logging
import time
from datetime import date, timedelta

import pandas as pd

from .esquema import COLUNAS_LONGAS, MAPA_YF, vazio_longo

log = logging.getLogger(__name__)

TENTATIVAS = 3
ESPERA_BASE_S = 2  # 2s, 4s, 8s


class FalhaDownload(RuntimeError):
    """O batch inteiro falhou depois de todas as tentativas."""


def fim_exclusivo_seguro(fim: date, hoje: date) -> date:
    """`fim` exclusivo nunca passa de hoje: só pregão fechado (no máximo ontem)."""
    return min(fim, hoje)


def _fetcher_padrao(**kwargs):
    import yfinance as yf

    return yf.download(**kwargs)


def _para_longo(bruto: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    if bruto is None or bruto.empty:
        return vazio_longo()

    if isinstance(bruto.columns, pd.MultiIndex):
        nivel = "Ticker" if "Ticker" in bruto.columns.names else 1
        longo = bruto.stack(level=nivel, future_stack=True)
        longo.index = longo.index.set_names(["data", "ticker"])
        longo = longo.reset_index()
    elif len(tickers) == 1:
        longo = bruto.rename_axis("data").reset_index()
        longo["ticker"] = tickers[0]
    else:
        raise ValueError("formato inesperado do yfinance: colunas sem nível de ticker")

    longo = longo.rename(columns=MAPA_YF)
    for coluna in ("dividends", "splits"):
        if coluna not in longo:
            longo[coluna] = 0.0
    faltando = set(COLUNAS_LONGAS) - set(longo.columns)
    if faltando:
        raise ValueError(f"colunas faltando no retorno do yfinance: {sorted(faltando)}")

    # Linha toda NaN = artefato da união de calendários (feriado) ou ticker que falhou.
    longo = longo.dropna(subset=["open", "high", "low", "close", "adj_close", "volume"], how="all")
    longo["data"] = pd.to_datetime(longo["data"]).dt.tz_localize(None).dt.date
    longo["dividends"] = longo["dividends"].fillna(0.0).astype("float64")
    longo["splits"] = longo["splits"].fillna(0.0).astype("float64")
    longo["volume"] = longo["volume"].round().astype("Int64")
    longo["ticker"] = longo["ticker"].astype(str)
    return longo[COLUNAS_LONGAS].sort_values(["ticker", "data"]).reset_index(drop=True)


def baixar_bruto(tickers, inicio: date, fim: date, *, hoje: date | None = None,
                 fetcher=None, sleep=time.sleep) -> pd.DataFrame:
    """Baixa [inicio, fim) bruto, em formato longo.

    Tenta 3 vezes (espera 2s, 4s, 8s) se a chamada lança exceção ou volta vazia
    pra TODOS os tickers. Ticker ausente num resultado parcial não dispara retry:
    o chamador registra como falha. Esgotadas as tentativas, lança FalhaDownload.
    """
    tickers = list(tickers)
    hoje = hoje or date.today()
    fim = fim_exclusivo_seguro(fim, hoje)
    if inicio >= fim:
        return vazio_longo()
    fetcher = fetcher or _fetcher_padrao

    ultimo_erro = "sem dados"
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            bruto = fetcher(
                tickers=tickers, start=inicio.isoformat(), end=fim.isoformat(),
                auto_adjust=False, actions=True, progress=False,
                group_by="column", threads=True,
            )
            longo = _para_longo(bruto, tickers)
            longo = longo[longo["data"] < hoje]  # defesa extra: nada do pregão em curso
            if not longo.empty:
                return longo.reset_index(drop=True)
            ultimo_erro = "retorno vazio"
        except Exception as erro:  # noqa: BLE001 — qualquer erro de rede/API conta como tentativa
            ultimo_erro = f"{type(erro).__name__}: {erro}"
        log.warning("tentativa %d/%d falhou: %s", tentativa, TENTATIVAS, ultimo_erro)
        if tentativa < TENTATIVAS:
            sleep(ESPERA_BASE_S * 2 ** (tentativa - 1))
    raise FalhaDownload(ultimo_erro)


def janela_diaria(hoje: date, lookback_dias: int = 7) -> tuple[date, date]:
    return hoje - timedelta(days=lookback_dias), hoje
