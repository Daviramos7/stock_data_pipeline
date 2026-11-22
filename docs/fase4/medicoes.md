# Fase 4 — medições do gold (dbt-duckdb)

Medido em **22/11/2026 (domingo), ~16:28 BRT**, numa máquina local: AMD Ryzen 7 5700X (8 núcleos),
31,9 GB de RAM, Windows 11 Home (build 26200), Python 3.13.9, dbt-core 1.12.7, dbt-duckdb 1.11.1,
duckdb 2.0.1, exchange_calendars 4.13.3, pandas 2.3.3. Fonte: `data/silver/cotacoes.parquet` da
Fase 3 (29 708 linhas, baixado em 22/11/2026). Nenhum download nesta fase. Nada estimado.

Preparação (uma vez, da raiz): `pip install -r requirements-pipeline.txt` e `pip install -e .`
(o PYTHONPATH=src não é mais necessário).

## 1. `dbt build` no dado real

```powershell
Set-Location dbt
Measure-Command { ..\venv\Scripts\dbt.exe build --profiles-dir . }
```

| Rodada | Measure-Command | Resultado |
| --- | ---: | --- |
| 1 | 6,82 s | PASS=35 WARN=1 ERROR=0 TOTAL=36 |
| 2 | 6,31 s | PASS=35 WARN=1 ERROR=0 TOTAL=36 |
| 3 | 6,40 s | PASS=35 WARN=1 ERROR=0 TOTAL=36 |

- O `elapsed_time` do `target/run_results.json` numa 4ª rodada deu **1,56 s**. O resto do Measure-Command é a subida do dbt (parse e import).
- O nó mais caro é o `int_indicadores` (Python model, 10 tickers): **0,67 s**.
- `dbt docs generate` funciona e escreve `target/index.html` (1 818 461 bytes) e `catalog.json` (8 974 bytes). Nada disso vai pro git.

## 2. Linhas

| Objeto | Linhas |
| --- | ---: |
| silver (entrada) | 29 708 |
| linhas-fantasma descartadas (`excecoes_fonte`) | 54 (9 dias × 6 tickers B3) |
| `fato_cotacao_diaria` | **29 654** (B3 17 694 · NYSE-NASDAQ 11 960) |
| `dim_ativo` | 10 |
| `dim_calendario` | 9 496 (2 bolsas × 4 748 dias corridos; 6 493 pregões) |

## 3. Gold exportado (`python scripts/exportar_gold.py`, Parquet zstd)

| Arquivo | Bytes |
| --- | ---: |
| `data/gold/fato_cotacao_diaria.parquet` | 2 818 907 |
| `data/gold/dim_ativo.parquet` | 1 505 |
| `data/gold/dim_calendario.parquet` | 11 690 |
| `data/warehouse.duckdb` (não publicado) | 8 138 752 |

## 4. Warns do `dbt build` (salto > 25% no adj_close sem provento/split)

Limiar em `dbt_project.yml` (`vars.limiar_salto: 0.25`). É warn porque pode ser movimento real.

| Ticker | Data | adj anterior | adj no dia | Variação |
| --- | --- | ---: | ---: | ---: |
| PETR4.SA | 2020-03-09 | 6,1644 | 4,3337 | −29,7% |
| MGLU3.SA | 2015-07-31 | 0,7157 | 0,9377 | +31,0% |
| MGLU3.SA | 2015-12-28 | 0,3853 | 0,5289 | +37,3% |
| MGLU3.SA | 2016-10-27 | 2,2692 | 2,9708 | +30,9% |
| MGLU3.SA | 2023-11-16 | 14,9925 | 18,7620 | +25,1% |
| MGLU3.SA | 2026-10-26 | 12,6900 | 5,3000 | −58,2% |
| BBAS3.SA | 2026-10-26 | 24,7200 | 17,4700 | −29,3% |
| NVDA | 2016-11-11 | 1,6626 | 2,1582 | +29,8% |

PETR4 em 09/03/2020 é o crash do petróleo/Covid. Os dois de 26/10/2026 abrem em gap com volume
5 a 11 vezes o normal e o preço não volta nos dias seguintes, o que parece movimento de mercado.
**A causa não foi verificada.** Os outros também não foram conferidos um a um.

## 5. CI (job `dbt`, simulado localmente)

Venv limpo em Python 3.13.9 (Windows), instalando só por `requirements-pipeline.txt`,
`requirements-dev.txt` e `pip install -e .`: `pip check` sem conflito, pytest 50 passed,
silver sintético de 240 linhas (2 tickers × 120 pregões, mesmo hash em duas gerações),
`dbt build` PASS=36, export ok. O runner Linux do GitHub não foi testado (não há push nesta fase).
