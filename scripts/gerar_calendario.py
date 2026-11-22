"""Gera o seed dbt/seeds/dim_calendario.csv (B3 e NYSE, 2015-01-01 a 2027-12-31).

Uma linha por (bolsa, dia corrido), com eh_pregao = true/false. Fonte: a lib
exchange_calendars (BVMF para a B3, XNYS para NYSE; a NASDAQ segue o mesmo
calendário de feriados da NYSE, por isso as duas ficam juntas em "NYSE-NASDAQ").

Conferência feita em 22/11/2026 contra data/silver/cotacoes.parquet (2015-01-02 a
2026-11-20), ver docs/fase4/calendario.md:
- NYSE: 2990 pregões na lib = 2990 datas no silver, sem divergência.
- B3: a lib acerta 20/11 (feriado nacional desde 2024; pregão normal em 2023 e
  em 20/11/2020). As divergências encontradas foram erro do Yahoo, não da lib:
  linhas-fantasma (volume 0) em feriados de 2017/2018 e 20/11/2020 ausente.
  Essas ficam em dbt/seeds/excecoes_fonte.csv, não aqui.

EXCECOES existe para o dia em que a lib errar o que a bolsa realmente fez
(ex.: fechamento extraordinário). Cada entrada precisa de fonte. Hoje está vazia
porque nenhuma divergência da lib foi encontrada.

Uso: python scripts/gerar_calendario.py
"""
from __future__ import annotations

import csv
from pathlib import Path

import exchange_calendars as xc
import pandas as pd

INICIO = "2015-01-01"
FIM = "2027-12-31"
BOLSAS = {"B3": "BVMF", "NYSE-NASDAQ": "XNYS"}

# (bolsa, "AAAA-MM-DD") -> eh_pregao real. Toda entrada exige comentário com a fonte.
EXCECOES: dict[tuple[str, str], bool] = {}

SAIDA = Path(__file__).resolve().parent.parent / "dbt" / "seeds" / "dim_calendario.csv"


def gerar_linhas() -> list[tuple[str, str, bool]]:
    dias = pd.date_range(INICIO, FIM, freq="D")
    linhas = []
    for bolsa, codigo in BOLSAS.items():
        cal = xc.get_calendar(codigo, start=INICIO, end=FIM)
        pregoes = {d.strftime("%Y-%m-%d") for d in cal.sessions}
        for dia in dias:
            chave = dia.strftime("%Y-%m-%d")
            eh_pregao = EXCECOES.get((bolsa, chave), chave in pregoes)
            linhas.append((bolsa, chave, eh_pregao))
    return linhas


def main() -> None:
    linhas = gerar_linhas()
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    with SAIDA.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["bolsa", "data", "eh_pregao"])
        w.writerows((b, d, "true" if p else "false") for b, d, p in linhas)
    total = sum(p for _, _, p in linhas)
    print(f"{SAIDA}: {len(linhas)} dias, {total} pregões")


if __name__ == "__main__":
    main()
