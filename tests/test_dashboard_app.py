"""O dashboard de verdade (streamlit AppTest) lendo um gold de fixture local, sem rede."""
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from gold_fixture import escrever_gold, montar_fato
from stock_pipeline.formatting import moeda_do_ticker

APP = str(Path(__file__).resolve().parent.parent / "dashboard.py")
TIMEOUT = 60


@pytest.fixture(scope="module")
def gold_dir(tmp_path_factory):
    return escrever_gold(tmp_path_factory.mktemp("gold_app"))


@pytest.fixture(autouse=True)
def cache_limpo():
    st.cache_data.clear()
    yield
    st.cache_data.clear()


@pytest.fixture
def sem_yfinance(monkeypatch):
    """Qualquer chamada ao yfinance falha o teste: no modo gold ele não pode ser usado."""
    import yfinance

    def proibido(*a, **k):
        raise AssertionError("yfinance não deveria ser chamado com o gold disponível")

    monkeypatch.setattr(yfinance, "download", proibido)


def _textos(elementos):
    return " ".join(e.value for e in elementos)


def _abrir(monkeypatch, base, ticker=None):
    monkeypatch.setenv("GOLD_BASE_URL", str(base))
    at = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    if ticker:
        at.sidebar.selectbox[0].select(ticker).run()
    return at


@pytest.mark.parametrize("ticker", ["PETR4.SA", "AAPL"])
def test_abre_com_fonte_gold(monkeypatch, gold_dir, sem_yfinance, ticker):
    at = _abrir(monkeypatch, gold_dir, ticker)
    assert not at.exception, at.exception
    assert not at.error
    assert not at.warning
    assert "gold (pipeline diário)" in _textos(at.sidebar.markdown)
    assert "yfinance ao vivo" not in _textos(at.sidebar.markdown)
    assert len(at.metric) == 4
    # data máxima do seletor = última data do gold daquele ticker
    esperado = date(2026, 11, 19) if ticker.endswith(".SA") else date(2026, 11, 20)
    assert at.sidebar.date_input[1].value == esperado
    assert "Não é recomendação de investimento" in at.caption[0].value


@pytest.mark.parametrize("ticker", ["PETR4.SA", "AAPL"])
def test_kpis_batem_com_o_gold(monkeypatch, gold_dir, sem_yfinance, ticker):
    at = _abrir(monkeypatch, gold_dir, ticker)
    fato = montar_fato()
    linhas = fato[fato["ticker"] == ticker].sort_values("data")
    ult, pen = linhas.iloc[-1], linhas.iloc[-2]

    # KPIs exibidos (strings formatadas) = formato da linha do gold
    metricas = {m.label: m for m in at.metric}
    var = (ult["adj_close"] - pen["adj_close"]) / pen["adj_close"] * 100
    assert metricas["Preço Atual"].value == f"{moeda_do_ticker(ticker)} {ult['adj_close']:.2f}"
    assert metricas["Preço Atual"].delta == f"{var:.2f}%"
    assert metricas["RSI (14d)"].value == f"{ult['rsi_14']:.1f}"
    assert metricas["Volatilidade Anual"].value == f"{ult['volatilidade_anual']:.1f}%"
    tendencia = "Alta" if ult["adj_close"] > ult["sma_20"] else "Baixa"
    assert metricas["Tendência (20d)"].value == tendencia

    # Números por trás dos KPIs (tabela da aba "Base de Dados"): rtol 1e-9
    tabela = at.dataframe[0].value
    topo = tabela.iloc[0]  # ordenada da mais recente pra mais antiga
    assert pd.Timestamp(topo["data"]) == pd.Timestamp(ult["data"])
    np.testing.assert_allclose(
        [topo["fechamento"], topo["RSI"], topo["Volatilidade_Anual"], topo["SMA_20"]],
        [ult["adj_close"], ult["rsi_14"], ult["volatilidade_anual"], ult["sma_20"]],
        rtol=1e-9,
    )


def _yf_falso(chamadas):
    def download(ticker, start, end, **kwargs):
        chamadas.append((ticker, start, end, kwargs.get("auto_adjust")))
        datas = pd.bdate_range(start, pd.Timestamp(end) - pd.Timedelta(days=1), name="Date")
        n = len(datas)
        preco = 20 + np.cumsum(np.random.default_rng(7).normal(0, 0.3, n))
        return pd.DataFrame({
            "Open": preco, "High": preco * 1.01, "Low": preco * 0.99,
            "Close": preco, "Volume": np.full(n, 1_000_000),
        }, index=datas)
    return download


def test_gold_invalido_cai_pro_yfinance(monkeypatch, tmp_path):
    import yfinance
    chamadas = []
    monkeypatch.setattr(yfinance, "download", _yf_falso(chamadas))
    at = _abrir(monkeypatch, tmp_path / "gold_que_nao_existe")
    assert not at.exception, at.exception
    assert any("indisponíveis" in w.value for w in at.warning)
    assert "yfinance ao vivo (fallback)" in _textos(at.sidebar.markdown)
    assert "gold (pipeline diário)" not in _textos(at.sidebar.markdown)
    assert len(at.metric) == 4  # app de pé, com os KPIs do caminho antigo
    assert chamadas and chamadas[0][3] is True  # auto_adjust=True, como antes
    assert at.sidebar.date_input[1].value == date.today()


def test_gold_com_colunas_faltando_tambem_cai(monkeypatch, tmp_path):
    import yfinance
    monkeypatch.setattr(yfinance, "download", _yf_falso([]))
    escrever_gold(tmp_path, fato=montar_fato().drop(columns=["adj_close"]))
    at = _abrir(monkeypatch, tmp_path)
    assert not at.exception, at.exception
    assert any("adj_close" in w.value for w in at.warning)
    assert "yfinance ao vivo (fallback)" in _textos(at.sidebar.markdown)


def test_periodo_curto_mostra_aviso(monkeypatch, gold_dir, sem_yfinance):
    at = _abrir(monkeypatch, gold_dir, "PETR4.SA")
    at.sidebar.date_input[0].set_value(date(2026, 11, 19)).run()
    assert not at.exception, at.exception
    assert any("pelo menos 2 pregões" in w.value for w in at.warning)
    assert len(at.metric) == 0
