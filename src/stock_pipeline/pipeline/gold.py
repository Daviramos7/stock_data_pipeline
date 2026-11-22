"""Export do gold: tabelas do DuckDB (depois do `dbt build`) para Parquet zstd.

É o que a Fase 5 publica na Release `data-latest`. Usado pelo orquestrador e por
`scripts/exportar_gold.py`.
"""
from __future__ import annotations

from pathlib import Path

import duckdb

TABELAS = {
    "fato_cotacao_diaria": "order by ticker, data",
    "dim_ativo": "order by ticker",
    "dim_calendario": "order by bolsa, data",
}


def exportar(db: Path, saida: Path) -> dict[str, int]:
    """Grava `<saida>/<tabela>.parquet` para cada tabela do gold e devolve as linhas."""
    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    linhas = {}
    with duckdb.connect(str(db), read_only=True) as con:
        for tabela, ordem in TABELAS.items():
            destino = (saida / f"{tabela}.parquet").as_posix()
            con.execute(
                f"copy (select * from {tabela} {ordem}) to '{destino}' "
                "(format parquet, compression zstd)"
            )
            linhas[tabela] = con.execute(f"select count(*) from {tabela}").fetchone()[0]
    return linhas
