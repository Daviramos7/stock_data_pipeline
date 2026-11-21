"""Equivalência: processar_indicadores do pacote src/ dá a mesma saída congelada (sem rede)."""
from pathlib import Path

import pandas as pd
import pytest

from stock_pipeline.indicators import processar_indicadores

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _ler(nome):
    return pd.read_csv(FIXTURES / nome, parse_dates=["data"])


@pytest.mark.parametrize("ticker", ["petr4", "aapl"])
def test_saida_igual_a_congelada(ticker):
    entrada = _ler(f"{ticker}_entrada.csv")
    esperado = _ler(f"{ticker}_saida.csv")
    obtido, _ = processar_indicadores(entrada)
    pd.testing.assert_frame_equal(obtido, esperado, check_exact=False, rtol=1e-12)


def test_deterministico():
    entrada = _ler("petr4_entrada.csv")
    a, _ = processar_indicadores(entrada)
    b, _ = processar_indicadores(entrada)
    pd.testing.assert_frame_equal(a, b, check_exact=True)
