import pytest

from stock_pipeline.formatting import moeda_do_ticker


@pytest.mark.parametrize("ticker, esperado", [
    ("PETR4.SA", "R$"),
    ("petr4.sa", "R$"),
    ("AAPL", "US$"),
])
def test_moeda_do_ticker(ticker, esperado):
    assert moeda_do_ticker(ticker) == esperado
