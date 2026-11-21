"""Propriedades básicas dos indicadores numa série sintética (sem fixture)."""
import math

import pandas as pd
import pytest

from stock_pipeline.indicators import processar_indicadores


@pytest.fixture
def serie_crescente():
    # 60 dias, fechamento 10, 11, ..., 69: só altas.
    fechamento = [10.0 + i for i in range(60)]
    return pd.DataFrame({
        "data": pd.date_range("2024-01-01", periods=60, freq="D"),
        "fechamento": fechamento,
    })


def test_sma20_ultimo_dia_e_media_dos_20_ultimos(serie_crescente):
    df, _ = processar_indicadores(serie_crescente)
    ultimos_20 = [10.0 + i for i in range(40, 60)]  # 50..69
    media_manual = sum(ultimos_20) / 20  # 59.5
    assert media_manual == 59.5
    assert df["SMA_20"].iloc[-1] == pytest.approx(media_manual)


def test_rsi_100_em_serie_so_de_altas(serie_crescente):
    df, _ = processar_indicadores(serie_crescente)
    rsi_validos = df["RSI"].dropna()
    assert len(rsi_validos) > 0
    assert (rsi_validos == 100.0).all()


def test_volatilidade_nan_nas_primeiras_21_linhas(serie_crescente):
    df, _ = processar_indicadores(serie_crescente)
    vol = df["Volatilidade_Anual"]
    assert vol.iloc[:21].isna().all()
    assert not math.isnan(vol.iloc[21])
