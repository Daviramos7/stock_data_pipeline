"""Exporta o gold do DuckDB para Parquet (o que a Fase 5 publica na Release).

Rodar depois do `dbt build`:  python scripts/exportar_gold.py [--db ...] [--saida ...]
A lógica mora em `stock_pipeline.pipeline.gold` (o orquestrador usa a mesma função).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from stock_pipeline.pipeline.gold import exportar

RAIZ = Path(__file__).resolve().parent.parent


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
