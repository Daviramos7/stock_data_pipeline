"""Indicadores do app contra referência externa (lib `ta`) ou reimplementação independente.

Usa só as fixtures de entrada (sem rede). A `ta` é dependência de teste (requirements-dev.txt).
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator
from ta.volatility import BollingerBands

from stock_pipeline.indicators import processar_indicadores

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TICKERS = ["petr4", "aapl"]


@pytest.fixture(params=TICKERS)
def dados(request):
    entrada = pd.read_csv(FIXTURES / f"{request.param}_entrada.csv", parse_dates=["data"])
    saida, _ = processar_indicadores(entrada)
    return entrada["fechamento"], saida


def _iguais(obtido, esperado, rtol):
    # Mesmas posições de NaN e valores iguais dentro da tolerância.
    np.testing.assert_array_equal(obtido.isna().to_numpy(), esperado.isna().to_numpy())
    np.testing.assert_allclose(obtido.to_numpy(), esperado.to_numpy(), rtol=rtol, equal_nan=True)


@pytest.mark.parametrize("janela", [20, 50])
def test_sma_igual_ta(dados, janela):
    fechamento, saida = dados
    ref = SMAIndicator(fechamento, window=janela).sma_indicator()
    _iguais(saida[f"SMA_{janela}"], ref, rtol=1e-12)


def test_bollinger_igual_ta_com_conversao_ddof(dados):
    """O app usa desvio padrão AMOSTRAL (pandas rolling std, ddof=1) — escolha consciente, mantida.

    A `ta` usa desvio POPULACIONAL (ddof=0). Para comparar, converte o desvio da `ta`:
        std_amostral = std_populacional * sqrt(n / (n - 1)), com n = 20.
    """
    fechamento, saida = dados
    n = 20
    bb = BollingerBands(fechamento, window=n, window_dev=2)
    media = bb.bollinger_mavg()
    std_pop = (bb.bollinger_hband() - media) / 2
    std_amostral = std_pop * np.sqrt(n / (n - 1))

    _iguais(saida["Bollinger_Upper"], media + 2 * std_amostral, rtol=1e-12)
    _iguais(saida["Bollinger_Lower"], media - 2 * std_amostral, rtol=1e-12)

    # Sanidade: sem a conversão as bandas NÃO batem (a diferença de ddof é real).
    validos = saida["Bollinger_Upper"].notna()
    assert not np.allclose(saida.loc[validos, "Bollinger_Upper"], bb.bollinger_hband()[validos], rtol=1e-9)


def test_volatilidade_anual_igual_reimplementacao_numpy(dados):
    """Reimplementação independente: loop simples, std amostral de 21 retornos, anualizada (252) em %."""
    fechamento, saida = dados
    precos = fechamento.to_numpy()
    retornos = np.full(len(precos), np.nan)
    retornos[1:] = precos[1:] / precos[:-1] - 1

    janela = 21
    esperado = np.full(len(precos), np.nan)
    for i in range(len(precos)):
        bloco = retornos[i - janela + 1 : i + 1] if i >= janela - 1 else None
        if bloco is not None and not np.isnan(bloco).any():
            esperado[i] = np.std(bloco, ddof=1) * np.sqrt(252) * 100

    obtido = saida["Volatilidade_Anual"].to_numpy()
    np.testing.assert_array_equal(np.isnan(obtido), np.isnan(esperado))
    np.testing.assert_allclose(obtido, esperado, rtol=1e-9, equal_nan=True)


def test_rsi_igual_wilder_ta(dados):
    """RSI de Wilder (14): média exponencial com alpha = 1/14, igual ao da `ta`.

    Antes era média simples de 14 (Cutler); a troca está no CHANGELOG (v2).
    """
    fechamento, saida = dados
    ref = RSIIndicator(fechamento, window=14).rsi()
    _iguais(saida["RSI"], ref, rtol=1e-9)
