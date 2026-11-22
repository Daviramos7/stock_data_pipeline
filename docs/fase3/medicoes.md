# Fase 3 — medições do pipeline bronze/silver

Medido em **22/11/2026 (domingo), 13:06–13:07 BRT**, numa máquina local:
AMD Ryzen 7 5700X (8 núcleos), 31,9 GB de RAM, Windows 11 Home (build 26200),
Python 3.13.9, pandas 2.3.3, pyarrow 21.0.0, yfinance 1.8.0. Rede doméstica.
Tudo abaixo saiu dos comandos listados e do `data/_runs/2026-11-22.json`. Nada estimado.

Os comandos rodam da raiz do repo com `$env:PYTHONPATH = "src"` (PowerShell).

## 1. Backfill

```powershell
Measure-Command { .\venv\Scripts\python.exe -m stock_pipeline.pipeline.cli backfill --inicio 2015-01-01 --fim 2026-11-21 }
```

- Saída: código 0, 10/10 tickers ok, 0 falhas, 0 ações corporativas (backfill não procura: já baixa tudo).
- Tempo: **3,303 s** no run log (download + bronze + silver) · **4,02 s** no `Measure-Command` (inclui a subida do Python).
- Uma chamada batch do yfinance para os 10 tickers.

| Ticker | Linhas | Primeiro pregão | Último pregão |
| --- | ---: | --- | --- |
| AAPL | 2990 | 2015-01-02 | 2026-11-20 |
| GOOGL | 2990 | 2015-01-02 | 2026-11-20 |
| MSFT | 2990 | 2015-01-02 | 2026-11-20 |
| NVDA | 2990 | 2015-01-02 | 2026-11-20 |
| BBAS3.SA | 2958 | 2015-01-02 | 2026-11-19 |
| ITUB4.SA | 2958 | 2015-01-02 | 2026-11-19 |
| MGLU3.SA | 2958 | 2015-01-02 | 2026-11-19 |
| PETR4.SA | 2958 | 2015-01-02 | 2026-11-19 |
| VALE3.SA | 2958 | 2015-01-02 | 2026-11-19 |
| WEGE3.SA | 2958 | 2015-01-02 | 2026-11-19 |
| **Total silver** | **29 708** | | |

- Linhas rejeitadas na validação: **0**.
- Proventos no histórico: 566 linhas com dividendo > 0 e 19 com split > 0 (inclui NVDA 4:1 em 2021-07-20 e 10:1 em 2024-06-10).

Tamanhos (`ls -l`, bytes):

| Arquivo | Bytes |
| --- | ---: |
| `data/bronze/ingest_date=2026-11-22/cotacoes.parquet` | 1 188 271 |
| `data/silver/cotacoes.parquet` | 1 188 271 |
| `data/silver/_rejeitadas.parquet` (0 linhas, só esquema) | 5 440 |
| `data/_runs/2026-11-22.json` (após o backfill) | 953 |

Bronze e silver têm o mesmo tamanho aqui porque, com uma única ingestão, o conteúdo é o mesmo.

## 2. Diário 2× seguidas (idempotência)

```powershell
.\venv\Scripts\python.exe -m stock_pipeline.pipeline.cli diario   # 2 vezes, uma atrás da outra
Get-FileHash data\silver\cotacoes.parquet                          # antes e depois de cada uma
```

| Momento | SHA-256 do silver | Tempo (`Measure-Command`) | `duracao_s` no log |
| --- | --- | ---: | ---: |
| Depois do backfill | `0880693C…EABE266A` | — | — |
| Depois do diário 1 | `0880693C…EABE266A` | 3,01 s | 2,312 |
| Depois do diário 2 | `0880693C…EABE266A` | 4,75 s | 4,057 |

Hash completo: `0880693C04C26A5F02E47502ABDFE4B8FBBE65AE0922A9ED2FE450B7EABE266A`.
O bronze do dia teve o mesmo hash depois dos dois diários (`C5FD99FC…7FD5922E`).

**Por que não entrou linha nova:** hoje é domingo. O diário pega 7 dias corridos com fim exclusivo
em hoje: janela [2026-11-15, 2026-11-22). Os pregões dessa janela (5 nos EUA, de 16 a 20/11, e 4 na B3,
sem o 20/11) já tinham vindo no backfill. O diário só reprocessou a janela, o Yahoo devolveu os mesmos
valores, o merge por (ticker, data) não mudou nada e o silver saiu byte a byte igual. Nenhum provento
novo na janela, então nenhum histórico foi rebaixado. Os tempos de 2 a 4 s variam com a rede.

## 3. Feriado de 20/11/2026 (Consciência Negra, sexta)

Consulta no silver depois do backfill:

- **Não existe** linha em 2026-11-20 para BBAS3.SA, ITUB4.SA, MGLU3.SA, PETR4.SA, VALE3.SA, WEGE3.SA (último pregão: 19/11).
- **Existe** linha em 2026-11-20 para AAPL, GOOGL, MSFT, NVDA.

No batch, o yfinance devolve o .SA com linha toda NaN nesse dia (o índice é a união dos calendários).
O `fetch.py` descarta essas linhas. Sem isso, entrariam 6 linhas vazias.

## 4. CI

`tests/pipeline/` entra no `pytest` do CI pelo `testpaths = tests`. Os 23 testes usam um fake do
`yf.download`: não tocam a rede.
