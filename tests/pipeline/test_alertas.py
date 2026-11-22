"""Fase 6: coletor de alertas. Sem rede e sem DuckDB: a consulta dos exemplos é um fake."""
import json
from datetime import date
from pathlib import Path

import pytest

from stock_pipeline.pipeline.alertas import MAX_EXEMPLOS, coletar, consultar_duckdb, gerar
from stock_pipeline.pipeline.cli import main

FIX = Path(__file__).parent / "fixtures"


def ler(nome):
    return json.loads((FIX / nome).read_text(encoding="utf-8"))


SALTOS = [
    {"ticker": "MGLU3.SA", "data": date(2026, 10, 26), "adj_anterior": 12.69, "adj_close": 5.30,
     "variacao": -0.5823, "dividends": 0.0, "splits": 0.0, "eventos_vizinhos": 0},
    {"ticker": "BBAS3.SA", "data": date(2026, 10, 26), "adj_anterior": 24.72, "adj_close": 17.47,
     "variacao": -0.2933, "dividends": 0.0, "splits": 0.0, "eventos_vizinhos": 1},
]


def fake_consulta(sql):
    if "salto" in sql:
        return SALTOS
    if "volume" in sql:
        return [{"ticker": "VALE3.SA", "data": date(2024, 4, 26), "volume": 0}] * 25
    return [{"bolsa": "B3", "ultima_data": date(2026, 11, 19)}]


def por_chave(resultado):
    return {a["chave"]: a for a in resultado["alertas"]}


def test_run_ok_gera_so_alertas_de_teste():
    r = coletar(ler("last_run_ok.json"), ler("run_results.json"), consultar=fake_consulta)
    alertas = por_chave(r)
    assert set(alertas) == {"dbt:salto_sem_evento", "dbt:volume_zero_em_pregao",
                            "dbt:fato_desatualizado"}
    assert r["escopo"] == ["falha-pipeline", "dbt:"]
    assert alertas["dbt:fato_desatualizado"]["severidade"] == "erro"  # status fail
    assert alertas["dbt:salto_sem_evento"]["severidade"] == "aviso"   # status warn
    # erros primeiro
    assert r["alertas"][0]["chave"] == "dbt:fato_desatualizado"
    assert r["data_run"] == "2026-11-23"


def test_corpo_do_salto_tem_ticker_data_variacao_e_evento():
    corpo = por_chave(coletar(ler("last_run_ok.json"), ler("run_results.json"),
                              consultar=fake_consulta))["dbt:salto_sem_evento"]["corpo"]
    assert "MGLU3.SA" in corpo and "BBAS3.SA" in corpo and "2026-10-26" in corpo
    assert "-58.2%" in corpo and "-29.3%" in corpo
    assert "dividendo/split no dia" in corpo and "| não |" in corpo
    assert "eventos_conhecidos.csv" in corpo           # o que fazer
    assert "actions/runs/111" in corpo                 # link do run
    assert "**2 linha(s)**" in corpo


def test_exemplos_limitados_a_20_com_contagem_total():
    corpo = por_chave(coletar(ler("last_run_ok.json"), ler("run_results.json"),
                              consultar=fake_consulta))["dbt:volume_zero_em_pregao"]["corpo"]
    assert f"Exemplos ({MAX_EXEMPLOS} de 25)" in corpo
    assert "e mais 5" in corpo
    assert corpo.count("VALE3.SA") == MAX_EXEMPLOS


def test_falha_de_etapa_vira_falha_pipeline_e_nao_olha_dbt():
    r = coletar(ler("last_run_falha_ingestao.json"), ler("run_results.json"),
                consultar=fake_consulta)
    assert [a["chave"] for a in r["alertas"]] == ["falha-pipeline"]
    assert r["escopo"] == ["falha-pipeline"]  # dbt não rodou: Issues dbt:* não podem fechar
    a = r["alertas"][0]
    assert a["severidade"] == "erro"
    assert "`ingestao`" in a["corpo"] and "PETR4.SA" in a["corpo"] and "runs/222" in a["corpo"]


def test_falha_no_dbt_gera_falha_pipeline_e_alertas_dbt():
    last_run = {**ler("last_run_ok.json"), "status": "falha", "etapa_falhou": "dbt",
                "erro": "FalhaEtapa: dbt build saiu com código 1"}
    chaves = [a["chave"] for a in coletar(last_run, ler("run_results.json"),
                                          consultar=fake_consulta)["alertas"]]
    assert chaves[:2] == ["dbt:fato_desatualizado", "falha-pipeline"]
    assert "dbt:salto_sem_evento" in chaves


def test_sem_last_run_e_falha_antes_do_orquestrador():
    r = coletar(None, None)
    assert r["alertas"][0]["chave"] == "falha-pipeline"
    assert "antes_do_orquestrador" in r["alertas"][0]["titulo"]


def test_run_results_velho_e_ignorado():
    velho = ler("run_results.json")
    velho["metadata"]["generated_at"] = "2026-11-20T09:25:00Z"
    r = coletar(ler("last_run_ok.json"), velho, consultar=fake_consulta)
    assert r["alertas"] == [] and r["escopo"] == ["falha-pipeline"]


def test_assinatura_estavel_e_sensivel_ao_conteudo():
    def assinatura(consulta, url):
        lr = {**ler("last_run_ok.json"), "run_url": url}
        return por_chave(coletar(lr, ler("run_results.json"), consultar=consulta))[
            "dbt:salto_sem_evento"]["assinatura"]

    a = assinatura(fake_consulta, "https://x/runs/1")
    assert a == assinatura(fake_consulta, "https://x/runs/2")  # link muda, assinatura não

    def outra(sql):
        return SALTOS[:1] if "salto" in sql else fake_consulta(sql)
    assert a != assinatura(outra, "https://x/runs/1")


def test_erro_na_consulta_nao_derruba_o_alerta():
    def quebra(sql):
        raise RuntimeError("warehouse trancado")
    alertas = por_chave(coletar(ler("last_run_ok.json"), ler("run_results.json"), consultar=quebra))
    assert "não consegui listar exemplos" in alertas["dbt:salto_sem_evento"]["corpo"]
    assert "**2 linha(s)**" in alertas["dbt:salto_sem_evento"]["corpo"]  # contagem vem do dbt


def test_cli_alertas_grava_json(tmp_path, capsys):
    (tmp_path / "_dbt" / "target").mkdir(parents=True)
    (tmp_path / "last_run.json").write_text((FIX / "last_run_ok.json").read_text("utf-8"), "utf-8")
    (tmp_path / "_dbt" / "target" / "run_results.json").write_text(
        (FIX / "run_results.json").read_text("utf-8"), "utf-8")
    saida = tmp_path / "alertas.json"
    assert main(["--data-dir", str(tmp_path), "alertas", "--saida", str(saida)]) == 0
    gravado = json.loads(saida.read_text(encoding="utf-8"))
    assert len(gravado["alertas"]) == 3  # sem warehouse: sem exemplos, mas com contagem
    assert "3 alerta(s)" in capsys.readouterr().out


def test_consulta_duckdb_aceita_sql_terminando_em_comentario(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    db = tmp_path / "w.duckdb"
    with duckdb.connect(str(db)) as con:
        con.execute("create table t as select (n * 7) % 30 as n from range(30) r(n)")  # embaralhado
    consulta = consultar_duckdb(db)
    linhas = consulta("-- cabeçalho\nselect n from t -- fim")
    assert linhas == [{"n": i} for i in range(MAX_EXEMPLOS)]  # ordenado e cortado em 20
    assert consulta("select n from t") == linhas              # determinístico
    assert consultar_duckdb(tmp_path / "nao_existe.duckdb") is None


def test_gerar_sem_run_results(tmp_path):
    (tmp_path / "lr.json").write_text((FIX / "last_run_ok.json").read_text("utf-8"), "utf-8")
    r = gerar(last_run=tmp_path / "lr.json", run_results=tmp_path / "nada.json",
              warehouse=tmp_path / "nada.duckdb", saida=tmp_path / "a.json")
    assert r["alertas"] == []
