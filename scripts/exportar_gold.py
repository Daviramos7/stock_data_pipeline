"""Exporta o gold do DuckDB para Parquet (o que a Fase 5 publica na Release).

Rodar depois do `dbt build`:  python scripts/exportar_gold.py [--db ...] [--saida ...]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parent.parent
TABELAS = {
    "fato_cotacao_diaria": "order by ticker, data",
    "dim_ativo": "order by ticker",
    "dim_calendario": "order by bolsa, data",
}


def exportar(db: Path, saida: Path) -> dict[str, int]:
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


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, default=RAIZ / "data" / "warehouse.duckdb")
    p.add_argument("--saida", type=Path, default=RAIZ / "data" / "gold")
    a = p.parse_args()
    for tabela, n in exportar(a.db, a.saida).items():
        arq = a.saida / f"{tabela}.parquet"
        print(f"{arq}: {n} linhas, {arq.stat().st_size} bytes")


if __name__ == "__main__":
    main()
