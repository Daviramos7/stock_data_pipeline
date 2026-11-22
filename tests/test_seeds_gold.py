"""Os seeds versionados do dbt não podem descolar dos scripts que os geram."""
import csv
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SEEDS = RAIZ / "dbt" / "seeds"


def _ler(nome):
    with (SEEDS / nome).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_dim_ativo_bate_com_config():
    import importlib.util
    spec = importlib.util.spec_from_file_location("gda", RAIZ / "scripts" / "gerar_dim_ativo.py")
    gda = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gda)
    assert _ler("dim_ativo.csv") == gda.gerar_linhas()


def test_dim_calendario_bate_com_lib():
    pytest.importorskip("exchange_calendars")  # só no ambiente do pipeline
    import importlib.util
    spec = importlib.util.spec_from_file_location("gc", RAIZ / "scripts" / "gerar_calendario.py")
    gc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gc)
    esperado = [dict(bolsa=b, data=d, eh_pregao="true" if p else "false") for b, d, p in gc.gerar_linhas()]
    assert _ler("dim_calendario.csv") == esperado


@pytest.mark.parametrize("data,eh_pregao", [
    ("2023-11-20", "true"),   # antes do feriado nacional
    ("2020-11-20", "true"),   # pregão normal (Yahoo não tem a linha: ver excecoes_fonte.csv)
    ("2024-11-20", "false"),  # Consciência Negra, feriado nacional desde 2024
    ("2025-11-20", "false"),
    ("2026-11-20", "false"),
    ("2017-06-15", "false"),  # Corpus Christi (Yahoo tem linha-fantasma)
])
def test_feriados_b3_conferidos(data, eh_pregao):
    linha = [r for r in _ler("dim_calendario.csv") if r["bolsa"] == "B3" and r["data"] == data]
    assert linha and linha[0]["eh_pregao"] == eh_pregao
