# ADR-001 — Stack da v2 (status: APROVADO em 19/11/2026)

Fase 0 · scripts de medição em `docs/fase0/`.

## Contexto medido (19/11/2026 ~09:30 BRT, ambiente cloud Linux, Python 3.13.18, yfinance 1.8.0, pandas 3.0.5)
Comandos: `python -I docs/fase0/bench.py dashboard.py` e `python -I docs/fase0/cold.py` (3 processos novos). Saída bruta em `docs/fase0/bench_out.txt`.

| Medida | Valor |
| --- | --- |
| Download 1 ticker / 1 ano, processo novo (frio) | mediana 0,18–0,25 s, máx 0,86 s |
| Mesmo download repetido no mesmo processo (cache interno do yfinance) | ~0,02 s |
| 10 tickers numa chamada só (batch) | 0,17 s |
| Indicadores, 248 linhas, perf_counter, 200 reps | mediana 2,17 ms (~114 mil linhas/s) |
| Rajada de 60 downloads sem pausa | 60/60 ok, 10,7 s |
| Histórico máximo | PETR4 desde 2000-01-03; AAPL desde 1980; MGLU3 desde 2011 |

Observações:
- Os números de desempenho do README atual (0,81 s; 76 mil reg/s; 0,0033 s) não são reproduzíveis: o app mede com `time.time` e, quando o `st.cache_data` acerta, mostra o tempo de uma execução antiga. Serão medidos de novo na Fase 7.
- Curl puro na API do Yahoo tomou HTTP 429; yfinance passou. IP compartilhado de CI é risco conhecido.
- Feriado: dia sem pregão não vem (sem linha vazia) → "pregão faltando" exige calendário próprio.
- Ajustes: o Close "bruto" do Yahoo já vem ajustado por split (NVDA, 10:1 em 10/06/2024); `auto_adjust=True` também ajusta dividendo (PETR4 em 02/01/2024: 37,78 bruto × 26,03 ajustado). Todo provento reescreve o passado.

## Decisões
1. **Orquestrador: GitHub Actions cron** + `workflow_dispatch` com datas pra backfill. Airflow/Dagster exigiriam host 24/7 e são desproporcionais pra 1 requisição/dia.
2. **Formato: Parquet + DuckDB (dbt-duckdb).** Idempotência por partição de data de ingestão + merge por (ticker, data).
3. **Gold: Parquet como asset de uma GitHub Release fixa (`data-latest`)**, lido pelo Streamlit via URL com cache. O workflow commita um `last_run.json` (mantém o schedule ativo e serve de prova de execução).
4. **Bronze guarda o bruto** (com Dividends e Stock Splits); provento/split novo → rebaixa o histórico do ticker. Silver/gold calculam o ajustado.
5. Ingestão só de pregões fechados.
6. **Fase 1 é refatoração pura** (saída idêntica). Indicadores sobre o histórico inteiro na Fase 4.
7. **RSI:** Fase 2 trava a versão atual com teste; depois troca para Wilder com nota no changelog.
8. **Backfill desde 2015-01-01.**
9. **Alerta: Issue automática no GitHub.**

Custo: R$ 0. Não é recomendação de investimento.
