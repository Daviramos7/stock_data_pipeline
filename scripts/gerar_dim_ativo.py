"""Gera o seed dbt/seeds/dim_ativo.csv a partir de stock_pipeline.config.TICKER_MAP.

Regra: ticker com sufixo .SA é B3/BR/BRL/America/Sao_Paulo; o resto é
NYSE-NASDAQ/EUA/USD/America/New_York. tests/test_dim_ativo.py garante que o
seed versionado não descola do config.

Uso: python scripts/gerar_dim_ativo.py
"""
from __future__ import annotations

import csv
from pathlib import Path

from stock_pipeline.config import TICKER_MAP

COLUNAS = ["ticker", "nome", "bolsa", "mercado", "moeda", "fuso"]
SAIDA = Path(__file__).resolve().parent.parent / "dbt" / "seeds" / "dim_ativo.csv"


def linha_ativo(ticker: str, nome: str) -> dict[str, str]:
    if ticker.endswith(".SA"):
        return dict(ticker=ticker, nome=nome, bolsa="B3", mercado="BR",
                    moeda="BRL", fuso="America/Sao_Paulo")
    return dict(ticker=ticker, nome=nome, bolsa="NYSE-NASDAQ", mercado="EUA",
                moeda="USD", fuso="America/New_York")


def gerar_linhas() -> list[dict[str, str]]:
    return [linha_ativo(t, n) for t, n in sorted(TICKER_MAP.items())]


def main() -> None:
    linhas = gerar_linhas()
    with SAIDA.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS, lineterminator="\n")
        w.writeheader()
        w.writerows(linhas)
    print(f"{SAIDA}: {len(linhas)} ativos")


if __name__ == "__main__":
    main()
