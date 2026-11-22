"""leitura_gold: formato, filtro de datas, ticker inexistente, gold quebrado (sem rede)."""
import urllib.error

import numpy as np
import pandas as pd
import pytest

from gold_fixture import LAST_RUN, escrever_gold, montar_fato
from stock_pipeline import leitura_gold
from stock_pipeline.indicators import processar_indicadores
from stock_pipeline.leitura_gold import (
    COLUNAS_APP,
    GoldIndisponivel,
    carregar_gold,
    serie_do_ticker,
    ultima_data_por_bolsa,
)


@pytest.fixture(scope="module")
def gold_dir(tmp_path_factory):
    return escrever_gold(tmp_path_factory.mktemp("gold"))


@pytest.fixture(scope="module")
def gold(gold_dir):
    return carregar_gold(str(gold_dir))


def test_carrega_tres_partes(gold):
    fato, dim, last_run = gold
    assert len(fato) == 10 * 300
    assert pd.api.types.is_datetime64_any_dtype(fato["data"])
    assert set(dim["ticker"]) == set(fato["ticker"])
    assert last_run == LAST_RUN


def test_env_gold_base_url(gold_dir, monkeypatch):
    monkeypatch.setenv("GOLD_BASE_URL", str(gold_dir))
    assert leitura_gold.base_url() == str(gold_dir)
    fato, _, _ = carregar_gold()
    assert len(fato) == 3000


def test_default_e_a_release(monkeypatch):
    monkeypatch.delenv("GOLD_BASE_URL", raising=False)
    assert leitura_gold.base_url().endswith("/releases/download/data-latest")


def test_formato_igual_ao_app(gold):
    fato, _, _ = gold
    s = serie_do_ticker(fato, "PETR4.SA", "2026-01-01", "2026-11-30")
    assert list(s.columns) == COLUNAS_APP
    # mesmas colunas, na mesma ordem, que o caminho antigo (baixar_cotacoes + processar_indicadores)
    antigo, _ = processar_indicadores(s[["data", "abertura", "maxima", "minima", "fechamento", "volume"]])
    assert list(antigo.columns) == COLUNAS_APP
    assert pd.api.types.is_datetime64_any_dtype(s["data"])
    assert s["data"].is_monotonic_increasing


def test_usa_preco_ajustado(gold):
    fato, _, _ = gold
    s = serie_do_ticker(fato, "AAPL", "2000-01-01", "2030-01-01")
    linhas = fato[fato["ticker"] == "AAPL"].sort_values("data")
    np.testing.assert_allclose(s["fechamento"], linhas["adj_close"])
    np.testing.assert_allclose(s["abertura"], linhas["open_ajustado"])
    assert not np.allclose(s["fechamento"], linhas["close"])


def test_filtro_de_datas_e_indicadores_do_historico(gold):
    fato, _, _ = gold
    s = serie_do_ticker(fato, "PETR4.SA", "2026-10-01", "2026-10-31")
    assert s["data"].min() >= pd.Timestamp("2026-10-01")
    assert s["data"].max() <= pd.Timestamp("2026-10-31")
    assert len(s) == len(pd.bdate_range("2026-10-01", "2026-10-31"))
    # janela curta, mas SMA_50/RSI já vêm preenchidos (calculados no histórico inteiro)
    assert s[["SMA_50", "RSI", "Volatilidade_Anual"]].notna().all().all()


def test_filtro_inclui_extremos(gold):
    fato, _, _ = gold
    s = serie_do_ticker(fato, "AAPL", "2026-11-20", "2026-11-20")
    assert list(s["data"]) == [pd.Timestamp("2026-11-20")]


def test_ticker_inexistente_vazio(gold):
    fato, _, _ = gold
    s = serie_do_ticker(fato, "XXXX3.SA", "2026-01-01", "2026-11-30")
    assert s.empty
    assert list(s.columns) == COLUNAS_APP


def test_ultima_data_por_bolsa(gold):
    fato, _, _ = gold
    assert ultima_data_por_bolsa(fato) == {
        "B3": pd.Timestamp("2026-11-19"), "NYSE-NASDAQ": pd.Timestamp("2026-11-20")
    }


def test_colunas_faltando_no_fato(tmp_path):
    escrever_gold(tmp_path, fato=montar_fato().drop(columns=["rsi_14"]))
    with pytest.raises(GoldIndisponivel, match="rsi_14"):
        carregar_gold(str(tmp_path))


def test_colunas_faltando_na_dim(tmp_path):
    from gold_fixture import montar_dim_ativo
    escrever_gold(tmp_path, dim_ativo=montar_dim_ativo().drop(columns=["moeda"]))
    with pytest.raises(GoldIndisponivel, match="moeda"):
        carregar_gold(str(tmp_path))


def test_parquet_corrompido(tmp_path):
    escrever_gold(tmp_path)
    (tmp_path / "fato_cotacao_diaria.parquet").write_bytes(b"isso nao e parquet")
    with pytest.raises(GoldIndisponivel):
        carregar_gold(str(tmp_path))


def test_pasta_inexistente(tmp_path):
    with pytest.raises(GoldIndisponivel):
        carregar_gold(str(tmp_path / "nao_existe"))


def test_last_run_ausente_nao_derruba(tmp_path):
    escrever_gold(tmp_path, last_run=None)
    fato, _, last_run = carregar_gold(str(tmp_path))
    assert last_run == {} and not fato.empty


def test_http_tenta_duas_vezes_com_timeout(monkeypatch):
    chamadas = []

    def falso_urlopen(req, timeout):
        chamadas.append((req.full_url, timeout))
        raise urllib.error.URLError("sem rede")

    monkeypatch.setattr(leitura_gold.urllib.request, "urlopen", falso_urlopen)
    monkeypatch.setattr(leitura_gold, "ESPERA_ENTRE_TENTATIVAS_S", 0)
    with pytest.raises(GoldIndisponivel, match="2 tentativas"):
        carregar_gold("https://exemplo.invalido/data-latest")
    assert chamadas == [("https://exemplo.invalido/data-latest/fato_cotacao_diaria.parquet", 10)] * 2


def test_http_segunda_tentativa_salva(monkeypatch, gold_dir):
    estado = {"n": 0}

    class Resp:
        def __init__(self, dados):
            self.dados = dados

        def read(self):
            return self.dados

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def falso_urlopen(req, timeout):
        estado["n"] += 1
        if estado["n"] == 1:
            raise TimeoutError("lento")
        nome = req.full_url.rsplit("/", 1)[1]
        return Resp((gold_dir / nome).read_bytes())

    monkeypatch.setattr(leitura_gold.urllib.request, "urlopen", falso_urlopen)
    monkeypatch.setattr(leitura_gold, "ESPERA_ENTRE_TENTATIVAS_S", 0)
    fato, dim, last_run = carregar_gold("https://exemplo.invalido/data-latest")
    assert len(fato) == 3000 and last_run == LAST_RUN
