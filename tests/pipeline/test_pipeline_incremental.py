"""Fase 3: bronze/silver incremental e idempotente, sem rede (fetcher falso injetado)."""
import hashlib
import json
from datetime import date, timedelta

import pandas as pd
import pytest
from conftest import HOJE, TICKERS

from stock_pipeline.pipeline.bronze import caminho_bronze, gravar_bronze, ler_bronze
from stock_pipeline.pipeline.cli import executar
from stock_pipeline.pipeline.fetch import FalhaDownload, baixar_bruto, fim_exclusivo_seguro, janela_diaria
from stock_pipeline.pipeline.run_log import ler_log
from stock_pipeline.pipeline.silver import caminho_rejeitadas, caminho_silver, construir_silver, ler_silver

ONTEM = HOJE - timedelta(days=1)


def backfill(base, fake, sleep, hoje=HOJE, inicio=date(2024, 1, 1)):
    return executar(base, modo="backfill", inicio=inicio, fim=hoje, hoje=hoje,
                    tickers=TICKERS, fetcher=fake, sleep=sleep)


def diario(base, fake, sleep, hoje=HOJE):
    inicio, fim = janela_diaria(hoje)
    return executar(base, modo="diario", inicio=inicio, fim=fim, hoje=hoje,
                    tickers=TICKERS, fetcher=fake, sleep=sleep)


def sha256(caminho):
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def linhas_do(df, ticker):
    return df[df["ticker"] == ticker].drop(columns="ingest_date").reset_index(drop=True)


# --- idempotência ----------------------------------------------------------------

def test_diario_duas_vezes_da_silver_identico(tmp_path, fake, sem_sleep):
    _, sleep = sem_sleep
    backfill(tmp_path, fake, sleep)
    diario(tmp_path, fake, sleep)
    silver_1, hash_1 = ler_silver(tmp_path), sha256(caminho_silver(tmp_path))
    bronze_1 = sha256(caminho_bronze(tmp_path, HOJE))

    diario(tmp_path, fake, sleep)

    pd.testing.assert_frame_equal(ler_silver(tmp_path), silver_1)
    assert sha256(caminho_silver(tmp_path)) == hash_1
    assert sha256(caminho_bronze(tmp_path, HOJE)) == bronze_1
    assert len(ler_log(tmp_path, HOJE)["execucoes"]) == 3  # log anexa, não sobrescreve


def test_diario_depois_do_backfill_no_mesmo_dia_nao_encolhe_o_bronze(tmp_path, fake, sem_sleep):
    _, sleep = sem_sleep
    backfill(tmp_path, fake, sleep)
    antes = len(ler_bronze(tmp_path))
    diario(tmp_path, fake, sleep)
    assert len(ler_bronze(tmp_path)) == antes


def test_silver_ordenado_e_tipado(tmp_path, fake, sem_sleep):
    _, sleep = sem_sleep
    backfill(tmp_path, fake, sleep)
    silver = ler_silver(tmp_path)
    assert list(silver.columns) == ["ticker", "data", "open", "high", "low", "close", "adj_close",
                                    "volume", "dividends", "splits", "ingest_date"]
    assert silver.equals(silver.sort_values(["ticker", "data"]).reset_index(drop=True))
    assert not silver.duplicated(["ticker", "data"]).any()
    assert silver["volume"].dtype == "int64"
    assert isinstance(silver["data"].iloc[0], date)


def test_feriado_do_ticker_nao_vira_linha(tmp_path, fake, sem_sleep):
    _, sleep = sem_sleep
    backfill(tmp_path, fake, sleep)
    silver = ler_silver(tmp_path)
    carnaval = date(2024, 2, 12)
    assert carnaval not in set(silver.loc[silver["ticker"] == "AAA.SA", "data"])
    assert carnaval in set(silver.loc[silver["ticker"] == "BBB", "data"])


# --- dedup ----------------------------------------------------------------------

def test_dedup_fica_o_ingest_date_mais_recente(tmp_path, fake):
    bruto = baixar_bruto(["BBB"], date(2024, 1, 2), date(2024, 1, 4), hoje=HOJE, fetcher=fake)
    velho = bruto.copy()
    novo = bruto.copy()
    novo["close"] = novo["close"] + 1
    gravar_bronze(velho, tmp_path, date(2024, 1, 10))
    gravar_bronze(novo, tmp_path, date(2024, 1, 11))

    silver, _ = construir_silver(tmp_path)

    assert len(silver) == len(bruto)
    assert silver["close"].tolist() == novo["close"].tolist()
    assert set(silver["ingest_date"]) == {date(2024, 1, 11)}


# --- falha / vazio não apagam -----------------------------------------------------

def test_falha_de_um_ticker_nao_apaga_o_silver_dele(tmp_path, fake, sem_sleep):
    _, sleep = sem_sleep
    backfill(tmp_path, fake, sleep, hoje=ONTEM)
    bbb_antes = linhas_do(ler_silver(tmp_path), "BBB")

    fake.falhar_tickers = {"BBB"}
    execucao = diario(tmp_path, fake, sleep)

    pd.testing.assert_frame_equal(linhas_do(ler_silver(tmp_path), "BBB"), bbb_antes)
    assert "BBB" in execucao["tickers_falha"]
    assert execucao["tickers_ok"] == ["AAA.SA"]
    log = ler_log(tmp_path, HOJE)["execucoes"][-1]
    assert "BBB" in log["tickers_falha"]


def test_excecao_em_todas_as_tentativas_nao_apaga_nada(tmp_path, fake, sem_sleep):
    _, sleep = sem_sleep
    backfill(tmp_path, fake, sleep, hoje=ONTEM)
    antes, hash_antes = ler_silver(tmp_path), sha256(caminho_silver(tmp_path))

    fake.lancar_n = 99
    execucao = diario(tmp_path, fake, sleep)

    pd.testing.assert_frame_equal(ler_silver(tmp_path), antes)
    assert sha256(caminho_silver(tmp_path)) == hash_antes
    assert set(execucao["tickers_falha"]) == set(TICKERS)
    assert "ConnectionError" in execucao["tickers_falha"]["BBB"]
    assert not caminho_bronze(tmp_path, HOJE).exists()


def test_retorno_vazio_nao_apaga_nada(tmp_path, fake, sem_sleep):
    _, sleep = sem_sleep
    backfill(tmp_path, fake, sleep, hoje=ONTEM)
    antes = ler_silver(tmp_path)

    fake.vazio = True
    execucao = diario(tmp_path, fake, sleep)

    pd.testing.assert_frame_equal(ler_silver(tmp_path), antes)
    assert set(execucao["tickers_falha"]) == set(TICKERS)
    assert "vazio" in execucao["tickers_falha"]["AAA.SA"]


# --- retry ----------------------------------------------------------------------

def test_retry_falha_duas_vezes_e_acerta_na_terceira(fake, sem_sleep):
    esperas, sleep = sem_sleep
    fake.lancar_n = 2
    dados = baixar_bruto(TICKERS, date(2024, 3, 1), HOJE, hoje=HOJE, fetcher=fake, sleep=sleep)
    assert len(fake.chamadas) == 3
    assert esperas == [2, 4]
    assert set(dados["ticker"]) == set(TICKERS)


def test_retry_falha_tres_vezes_registra_falha(tmp_path, fake, sem_sleep):
    esperas, sleep = sem_sleep
    fake.lancar_n = 3
    with pytest.raises(FalhaDownload):
        baixar_bruto(TICKERS, date(2024, 3, 1), HOJE, hoje=HOJE, fetcher=fake, sleep=sleep)
    assert len(fake.chamadas) == 3
    assert esperas == [2, 4]

    fake.lancar_n = 3
    execucao = diario(tmp_path, fake, sleep)
    assert set(execucao["tickers_falha"]) == set(TICKERS)
    assert ler_log(tmp_path, HOJE)["execucoes"][-1]["tickers_ok"] == []


def test_batch_e_uma_chamada_so_com_dados_brutos(fake, sem_sleep):
    _, sleep = sem_sleep
    baixar_bruto(TICKERS, date(2024, 3, 1), HOJE, hoje=HOJE, fetcher=fake, sleep=sleep)
    assert len(fake.chamadas) == 1
    chamada = fake.chamadas[0]
    assert chamada["tickers"] == TICKERS
    assert chamada["auto_adjust"] is False and chamada["actions"] is True


# --- ações corporativas -----------------------------------------------------------

def test_dividendo_novo_na_janela_rebaixa_historico_do_ticker(tmp_path, fake, sem_sleep):
    _, sleep = sem_sleep
    backfill(tmp_path, fake, sleep, hoje=ONTEM)
    fake.chamadas.clear()

    # Provento em 18/03: o Yahoo reescreve o Adj Close de todo o passado do ticker.
    df = fake.dados["BBB"]
    df.loc["2024-03-18", "Dividends"] = 0.5
    df["Adj Close"] = df["Close"] * 0.8
    execucao = diario(tmp_path, fake, sleep)

    assert execucao["acoes_corporativas"] == {
        "BBB": [{"data": "2024-03-18", "tipo": "dividendo", "valor": 0.5}]}
    assert execucao["historicos_rebaixados"] == ["BBB"]
    rebaixas = [c for c in fake.chamadas if c["start"] == "2015-01-01"]
    assert [c["tickers"] for c in rebaixas] == [["BBB"]]

    silver = ler_silver(tmp_path)
    bbb = silver[silver["ticker"] == "BBB"]
    assert (bbb["adj_close"] == bbb["close"] * 0.8).all()  # passado inteiro reescrito
    assert set(bbb["ingest_date"]) == {HOJE}
    aaa = silver[silver["ticker"] == "AAA.SA"]
    assert (aaa["adj_close"] == aaa["close"] * 0.9).all()  # outro ticker intocado

    fake.chamadas.clear()
    segunda = diario(tmp_path, fake, sleep)
    assert segunda["acoes_corporativas"] == {}
    assert not [c for c in fake.chamadas if c["start"] == "2015-01-01"]


def test_split_novo_tambem_dispara_rebaixa(tmp_path, fake, sem_sleep):
    _, sleep = sem_sleep
    backfill(tmp_path, fake, sleep, hoje=ONTEM)
    fake.dados["AAA.SA"].loc["2024-03-18", "Stock Splits"] = 2.0
    execucao = diario(tmp_path, fake, sleep)
    assert execucao["acoes_corporativas"]["AAA.SA"][0]["tipo"] == "split"
    assert execucao["historicos_rebaixados"] == ["AAA.SA"]


def test_backfill_nao_procura_acoes_corporativas(tmp_path, fake, sem_sleep):
    _, sleep = sem_sleep
    fake.dados["BBB"].loc["2024-03-18", "Dividends"] = 0.5
    execucao = backfill(tmp_path, fake, sleep)
    assert execucao["acoes_corporativas"] == {}
    assert len(fake.chamadas) == 1


# --- validação --------------------------------------------------------------------

def test_preco_zero_e_high_menor_que_low_vao_pra_rejeitadas(tmp_path, fake, sem_sleep):
    _, sleep = sem_sleep
    fake.dados["BBB"].loc["2024-03-05", "Close"] = 0.0
    fake.dados["AAA.SA"].loc["2024-03-06", "High"] = 1.0  # abaixo do Low
    backfill(tmp_path, fake, sleep)

    silver = ler_silver(tmp_path)
    rejeitadas = pd.read_parquet(caminho_rejeitadas(tmp_path))
    chaves = set(zip(rejeitadas["ticker"], rejeitadas["data"]))
    assert chaves == {("BBB", date(2024, 3, 5)), ("AAA.SA", date(2024, 3, 6))}
    assert "close<=0_ou_nulo" in rejeitadas.set_index("ticker").loc["BBB", "motivo"]
    assert rejeitadas.set_index("ticker").loc["AAA.SA", "motivo"] == "high<low"
    assert not set(zip(silver["ticker"], silver["data"])) & chaves
    assert (silver[["open", "high", "low", "close", "adj_close"]] > 0).all().all()


def test_versao_nova_invalida_nao_derruba_a_antiga_valida(tmp_path, fake):
    bruto = baixar_bruto(["BBB"], date(2024, 1, 2), date(2024, 1, 3), hoje=HOJE, fetcher=fake)
    gravar_bronze(bruto, tmp_path, date(2024, 1, 10))
    ruim = bruto.assign(close=0.0)
    gravar_bronze(ruim, tmp_path, date(2024, 1, 11))

    silver, rejeitadas = construir_silver(tmp_path)

    assert silver["close"].tolist() == bruto["close"].tolist()
    assert len(rejeitadas) == 1


# --- só pregões fechados ------------------------------------------------------------

@pytest.mark.parametrize("fim", [HOJE - timedelta(days=3), HOJE, HOJE + timedelta(days=1),
                                 HOJE + timedelta(days=400)])
def test_fim_exclusivo_nunca_passa_de_hoje(fim):
    assert fim_exclusivo_seguro(fim, HOJE) <= HOJE


def test_nenhum_dado_de_hoje_ou_futuro_entra(tmp_path, fake, sem_sleep):
    _, sleep = sem_sleep
    executar(tmp_path, modo="backfill", inicio=date(2024, 1, 1), fim=date(2030, 1, 1), hoje=HOJE,
             tickers=TICKERS, fetcher=fake, sleep=sleep)
    assert all(date.fromisoformat(c["end"]) <= HOJE for c in fake.chamadas)
    assert max(ler_bronze(tmp_path)["data"]) == ONTEM
    assert max(ler_silver(tmp_path)["data"]) < HOJE


def test_fetcher_que_devolve_o_pregao_de_hoje_e_cortado(fake):
    def fetcher_teimoso(**kwargs):
        kwargs["end"] = "2024-03-29"  # ignora o end, como um bug de API faria
        return fake(**kwargs)

    dados = baixar_bruto(TICKERS, date(2024, 3, 1), HOJE, hoje=HOJE, fetcher=fetcher_teimoso)
    assert max(dados["data"]) < HOJE


def test_run_log_tem_os_campos_da_missao(tmp_path, fake, sem_sleep):
    _, sleep = sem_sleep
    diario(tmp_path, fake, sleep)
    registro = json.loads((tmp_path / "_runs" / f"{HOJE.isoformat()}.json").read_text("utf-8"))
    execucao = registro["execucoes"][0]
    for campo in ("tickers_ok", "tickers_falha", "linhas_baixadas", "acoes_corporativas",
                  "linhas_silver", "duracao_s"):
        assert campo in execucao
