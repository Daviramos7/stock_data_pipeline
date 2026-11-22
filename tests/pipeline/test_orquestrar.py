"""Fase 5: orquestrador. Sem rede e sem dbt: as etapas são fakes injetados."""
import json
from datetime import date, datetime, timezone

import pytest

# O orquestrador importa o gold, que depende do duckdb (requirements-pipeline.txt).
# O job "smoke" do CI usa só o ambiente do app e pula este arquivo; o job "dbt" roda ele.
pytest.importorskip("duckdb", reason="requer requirements-pipeline.txt (roda no job dbt do CI)")

from stock_pipeline.pipeline import cli
from stock_pipeline.pipeline.orquestrar import (
    FalhaEtapa, caminho_last_run, caminho_publicar, contar_dbt, janela, orquestrar,
)

HOJE = date(2026, 11, 23)  # segunda
AGORA = datetime(2026, 11, 23, 9, 17, 5, tzinfo=timezone.utc)
ENV_ACTIONS = {"GITHUB_SHA": "abc123", "GITHUB_REPOSITORY": "dono/repo",
               "GITHUB_RUN_ID": "42", "GITHUB_SERVER_URL": "https://github.com"}
CAMPOS = {"iniciado_em_utc", "iniciado_em_brt", "modo", "status", "etapa_falhou", "erro",
          "linhas_silver", "linhas_fato", "tickers_ok", "tickers_falha", "dbt",
          "commit_sha", "run_url", "inicio", "fim_exclusivo", "duracao_s"}


def ingestao_ok(ctx):
    ctx.resultado.update(tickers_ok=["AAA.SA", "BBB"], tickers_falha={}, linhas_silver=100)


def dbt_ok(ctx):
    ctx.resultado["dbt"] = {"pass": 35, "warn": 1, "error": 0, "skip": 0}


def export_ok(ctx):
    ctx.resultado["linhas_fato"] = 98


def falha(ctx):
    raise FalhaEtapa("quebrou (fake)")


def rodar(base, **etapas):
    padrao = {"ingestao": ingestao_ok, "dbt": dbt_ok, "export": export_ok}
    return orquestrar(base, modo="diario", hoje=HOJE, agora=lambda: AGORA, env=ENV_ACTIONS,
                      **{**padrao, **etapas})


def test_sucesso_cria_publicar_e_last_run(tmp_path):
    r = rodar(tmp_path)
    assert r["status"] == "ok" and r["etapa_falhou"] is None
    assert caminho_publicar(tmp_path).exists()
    gravado = json.loads(caminho_last_run(tmp_path).read_text(encoding="utf-8"))
    assert CAMPOS <= set(gravado)
    assert gravado["linhas_silver"] == 100 and gravado["linhas_fato"] == 98
    assert gravado["tickers_ok"] == ["AAA.SA", "BBB"] and gravado["tickers_falha"] == {}
    assert gravado["dbt"] == {"pass": 35, "warn": 1, "error": 0, "skip": 0}
    assert gravado["iniciado_em_utc"] == "2026-11-23T09:17:05+00:00"
    assert gravado["iniciado_em_brt"] == "2026-11-23T06:17:05-03:00"
    assert gravado["commit_sha"] == "abc123"
    assert gravado["run_url"] == "https://github.com/dono/repo/actions/runs/42"
    assert set(gravado["duracao_s"]) == {"ingestao", "dbt", "export", "total"}


@pytest.mark.parametrize("etapa", ["ingestao", "dbt", "export"])
def test_falha_em_qualquer_etapa_nao_publica(tmp_path, etapa):
    chamadas = []

    def marca(nome, fn):
        def _fn(ctx):
            chamadas.append(nome)
            fn(ctx)
        return _fn

    etapas = {"ingestao": marca("ingestao", ingestao_ok), "dbt": marca("dbt", dbt_ok),
              "export": marca("export", export_ok)}
    etapas[etapa] = marca(etapa, falha)
    r = rodar(tmp_path, **etapas)

    assert r["status"] == "falha" and r["etapa_falhou"] == etapa
    assert "quebrou (fake)" in r["erro"]
    assert not caminho_publicar(tmp_path).exists()
    assert json.loads(caminho_last_run(tmp_path).read_text(encoding="utf-8"))["status"] == "falha"
    assert chamadas[-1] == etapa  # para na etapa que falhou
    assert chamadas == ["ingestao", "dbt", "export"][:len(chamadas)]


def test_publicar_velho_e_apagado_quando_falha(tmp_path):
    rodar(tmp_path)
    assert caminho_publicar(tmp_path).exists()
    rodar(tmp_path, dbt=falha)
    assert not caminho_publicar(tmp_path).exists()


def test_excecao_inesperada_tambem_conta_como_falha(tmp_path):
    def explode(ctx):
        raise KeyError("coluna")

    r = rodar(tmp_path, export=explode)
    assert r["status"] == "falha" and r["etapa_falhou"] == "export"
    assert r["erro"].startswith("KeyError")


def test_sem_env_do_actions_campos_ficam_nulos(tmp_path):
    r = orquestrar(tmp_path, modo="diario", hoje=HOJE, agora=lambda: AGORA, env={},
                   ingestao=ingestao_ok, dbt=dbt_ok, export=export_ok)
    assert r["commit_sha"] is None and r["run_url"] is None


def test_ingestao_padrao_falha_com_ticker_falho(tmp_path, monkeypatch):
    def executar_fake(base, **kw):
        return {"tickers_ok": ["BBB"], "tickers_falha": {"AAA.SA": "retorno vazio"},
                "falhas_rebaixa": {}, "linhas_silver": 10}

    monkeypatch.setattr(cli, "executar", executar_fake)
    r = orquestrar(tmp_path, modo="diario", hoje=HOJE, agora=lambda: AGORA, env={},
                   dbt=dbt_ok, export=export_ok)
    assert r["status"] == "falha" and r["etapa_falhou"] == "ingestao"
    assert r["tickers_falha"] == {"AAA.SA": "retorno vazio"} and r["linhas_silver"] == 10
    assert not caminho_publicar(tmp_path).exists()


def test_janela():
    assert janela("diario", HOJE, None, None) == (date(2026, 11, 16), HOJE)
    assert janela("backfill", HOJE, None, None) == (date(2015, 1, 1), HOJE)
    assert janela("backfill", HOJE, date(2020, 1, 1), date(2020, 1, 31)) == (
        date(2020, 1, 1), date(2020, 2, 1))
    with pytest.raises(ValueError):
        janela("semanal", HOJE, None, None)


def test_contar_dbt(tmp_path):
    rr = tmp_path / "run_results.json"
    status = ["pass", "success", "success", "warn", "error", "fail", "skipped"]
    rr.write_text(json.dumps({"results": [{"status": s} for s in status]}), encoding="utf-8")
    assert contar_dbt(rr) == {"pass": 3, "warn": 1, "error": 2, "skip": 1}


def test_cli_orquestrar_exit_code(tmp_path, monkeypatch):
    import stock_pipeline.pipeline.orquestrar as mod

    def fake(base, *, modo, inicio, fim):
        assert (modo, inicio, fim) == ("backfill", date(2015, 1, 1), date(2015, 1, 31))
        return {"status": estado}

    monkeypatch.setattr(mod, "orquestrar", fake)
    argv = ["--data-dir", str(tmp_path), "orquestrar", "--modo", "backfill",
            "--inicio", "2015-01-01", "--fim", "2015-01-31"]
    estado = "ok"
    assert cli.main(argv) == 0
    estado = "falha"
    assert cli.main(argv) == 1


def test_linhas_silver_lidas_do_arquivo_quando_a_ingestao_cai_antes(tmp_path):
    import pandas as pd

    from stock_pipeline.pipeline.silver import caminho_silver

    caminho_silver(tmp_path).parent.mkdir(parents=True)
    pd.DataFrame({"x": range(7)}).to_parquet(caminho_silver(tmp_path))
    r = rodar(tmp_path, ingestao=falha)
    assert r["status"] == "falha" and r["linhas_silver"] == 7


def test_cli_simular_falha_cai_na_ingestao_sem_publicar(tmp_path, monkeypatch):
    import stock_pipeline.pipeline.orquestrar as mod

    def nao_pode(ctx):
        raise AssertionError("com --simular-falha o dbt/export não podem rodar")

    monkeypatch.setattr(mod, "dbt_padrao", nao_pode)
    monkeypatch.setattr(mod, "export_padrao", nao_pode)
    monkeypatch.setattr(mod.orquestrar, "__kwdefaults__",
                        {**mod.orquestrar.__kwdefaults__, "dbt": nao_pode, "export": nao_pode})
    argv = ["--data-dir", str(tmp_path), "orquestrar", "--modo", "diario", "--simular-falha"]
    assert cli.main(argv) == 1
    gravado = json.loads(caminho_last_run(tmp_path).read_text(encoding="utf-8"))
    assert gravado["status"] == "falha" and gravado["etapa_falhou"] == "ingestao"
    assert "simulada" in gravado["erro"]
    assert not caminho_publicar(tmp_path).exists()
