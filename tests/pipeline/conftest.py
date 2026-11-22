"""Fake do yf.download: mesmo formato do yfinance 1.8 (MultiIndex Price/Ticker), sem rede."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

CAMPOS_YF = ["Adj Close", "Close", "Dividends", "High", "Low", "Open", "Stock Splits", "Volume"]
HOJE = date(2024, 3, 20)  # quarta-feira
TICKERS = ["AAA.SA", "BBB"]


def serie(ticker: str, inicio="2024-01-02", fim="2024-03-29", feriados=()) -> pd.DataFrame:
    """Pregões (dias úteis) com preços determinísticos. Vai além de HOJE de propósito."""
    datas = pd.bdate_range(inicio, fim)
    datas = datas[~datas.isin(pd.to_datetime(list(feriados)))]
    base = 10.0 if ticker.endswith(".SA") else 100.0
    close = base + np.arange(len(datas)) * 0.1
    return pd.DataFrame({
        "Open": close - 0.05, "High": close + 0.5, "Low": close - 0.5, "Close": close,
        "Adj Close": close * 0.9, "Volume": np.arange(len(datas)) * 10 + 1000,
        "Dividends": 0.0, "Stock Splits": 0.0,
    }, index=pd.DatetimeIndex(datas, name="Date"))


class FakeYF:
    """Chamável com a assinatura do yf.download. Registra cada chamada."""

    def __init__(self, dados: dict[str, pd.DataFrame]):
        self.dados = dados
        self.chamadas: list[dict] = []
        self.falhar_tickers: set[str] = set()  # comportamento real: coluna toda NaN
        self.lancar_n = 0                       # lança exceção nas N primeiras chamadas
        self.vazio = False                      # devolve DataFrame vazio

    def __call__(self, *, tickers, start, end, **kwargs):
        self.chamadas.append({"tickers": list(tickers), "start": start, "end": end, **kwargs})
        if self.lancar_n > 0:
            self.lancar_n -= 1
            raise ConnectionError("rede caiu (fake)")
        if self.vazio:
            return pd.DataFrame()
        partes = {}
        for t in tickers:
            df = self.dados[t]
            df = df[(df.index >= pd.Timestamp(start)) & (df.index < pd.Timestamp(end))]
            if t in self.falhar_tickers:
                df = df.iloc[0:0]
            partes[t] = df[CAMPOS_YF]
        largo = pd.concat(partes, axis=1)  # união das datas -> NaN onde o ticker não tem pregão
        largo.columns = largo.columns.swaplevel(0, 1)
        largo.columns.names = ["Price", "Ticker"]
        return largo.sort_index(axis=1)


@pytest.fixture
def fake():
    # AAA.SA sem pregão em 2024-02-12/13 (carnaval) e 2024-03-15; BBB negocia todo dia útil.
    return FakeYF({
        "AAA.SA": serie("AAA.SA", feriados=["2024-02-12", "2024-02-13", "2024-03-15"]),
        "BBB": serie("BBB"),
    })


@pytest.fixture
def sem_sleep():
    esperas: list[float] = []
    return esperas, esperas.append
