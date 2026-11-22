# Fase 5: orquestração diária (GitHub Actions + Release `data-latest`)

Decisões de base: ADR-001, decisões 1 (Actions cron + `workflow_dispatch`), 3 (gold como asset de
Release fixa + `last_run.json` commitado) e 5 (só pregão fechado).

## 1. Fluxo

```
cron 09:17 UTC seg–sáb ─┐
workflow_dispatch ──────┴─> job `pipeline` (ubuntu-latest, timeout 20 min, concurrency "pipeline")
   │
   ├─ checkout → Python 3.13 (cache pip) → pip install -r requirements-pipeline.txt -e .
   │
   ├─ baixar estado: gh release download data-latest  bronze.tar.gz + silver.parquet
   │     └─ Release ou asset ausente → 1ª execução: força backfill desde 2015-01-01 (warning no log)
   │
   ├─ python -m stock_pipeline.pipeline.cli --data-dir data orquestrar --modo ...
   │     1. ingestão (diario = últimos 7 dias corridos | backfill = [inicio, fim])  ── falha? ─┐
   │     2. dbt build (cwd dbt/; ERROR falha, WARN passa)                          ── falha? ─┤
   │     3. export do gold → data/gold/*.parquet                                   ── falha? ─┤
   │     4. data/last_run.json (sempre)   +   data/PUBLICAR (só se 1–3 deram certo)           │
   │                                                                                           │
   ├─ [só com sucesso e na main] publicar na Release:                                exit 1 ◄─┘
   │     por asset: apaga X.anterior → renomeia X para X.anterior → sobe o X novo
   │     (bronze.tar.gz, silver.parquet, fato_cotacao_diaria / dim_ativo / dim_calendario .parquet, last_run.json)
   │
   └─ [sempre, na main] commit de status/last_run.json:  "chore(pipeline): run <data> <status> [skip ci]"
```

- Falha em qualquer etapa: o orquestrador sai com código 1, não cria `PUBLICAR`, a Release fica
  como estava e o job termina vermelho (a Fase 6 transforma isso em Issue). O `last_run.json` com
  `status: "falha"` e `etapa_falhou` é commitado do mesmo jeito.
- Na ingestão, ticker com falha também conta como falha. É a mesma regra do exit code da Fase 3.
- `PUBLICAR` de uma execução anterior é apagado no começo de cada execução.
- O commit do status usa o `GITHUB_TOKEN`. Push feito com ele não dispara outros workflows, então
  não há loop (o `[skip ci]` é redundância).
- Nenhum segredo além do `GITHUB_TOKEN` padrão (`permissions: contents: write`).
- Publicar e commitar só acontecem quando o run é da `main`. Um dispatch em outra branch roda
  tudo, mas não toca na Release nem na main.

### Campos do `last_run.json`

`iniciado_em_utc`, `iniciado_em_brt`, `modo`, `inicio`, `fim_exclusivo`, `status` (ok|falha),
`etapa_falhou` (ingestao|dbt|export|null), `erro`, `linhas_silver`, `linhas_fato`, `linhas_gold`,
`tickers_ok`, `tickers_falha`, `falhas_rebaixa`, `dbt` (pass/warn/error/skip, lido do
`run_results.json`), `duracao_s` por etapa, `commit_sha` (`GITHUB_SHA`) e `run_url` (montado de
`GITHUB_SERVER_URL`/`GITHUB_REPOSITORY`/`GITHUB_RUN_ID`). Fora do Actions, esses dois ficam `null`.

## 2. Horários

`cron: "17 9 * * 1-6"`: 09:17 UTC, que é **06:17 BRT** (o Brasil não tem horário de verão desde 2019),
de segunda a sábado. Cada run pega os pregões já fechados até o dia anterior: o de segunda cobre
até a sexta e o de sábado cobre a sexta. Domingo não roda. O minuto quebrado foge do pico das :00,
quando o GitHub mais atrasa e descarta jobs agendados. O horário do cron não é garantido: o
GitHub pode atrasar o início. O `hoje` do pipeline é `date.today()` do runner (UTC), que às 09:17 UTC
é o mesmo dia do Brasil.

## 3. Backfill manual

Actions → **pipeline** → *Run workflow* → `modo = backfill`, `inicio = AAAA-MM-DD` (vazio = 2015-01-01),
`fim = AAAA-MM-DD` (inclusivo; vazio = ontem). O estado da Release é baixado antes. O backfill grava
na partição de bronze do dia (merge por ticker+data, o novo ganha), e o silver é reconstruído a partir de todo o bronze.

Localmente (nunca publica nada):

```powershell
.\venv\Scripts\python.exe -m stock_pipeline.pipeline.cli --data-dir <pasta> orquestrar --modo backfill --inicio 2015-01-01 --fim 2026-11-21
.\venv\Scripts\python.exe -m stock_pipeline.pipeline.cli --data-dir <pasta> orquestrar --modo diario
```

O `dbt build` do orquestrador recebe `SILVER_PATH`/`DUCKDB_PATH` absolutos da pasta e grava
`target/` e `logs/` em `<pasta>/_dbt/`. Por isso uma pasta temporária não mexe em `dbt/target` nem no `data/` real.

## 4. Rollback (`.anterior`)

Cada publicação guarda um nível de rollback: antes de subir `X`, o `X` atual vira `X.anterior`
(o `.anterior` mais velho é apagado). Para voltar um run:

```bash
gh release download data-latest --pattern '*.anterior' --dir rollback
cd rollback && for f in *.anterior; do mv "$f" "${f%.anterior}"; done
gh release upload data-latest * --clobber     # os .anterior continuam lá
```

Limitações:
- É **um** nível só. Dois runs ruins seguidos apagam o estado bom.
- O asset fica fora do ar por alguns segundos entre o rename e o upload (a troca é feita asset a asset).
- Se o job morrer no meio da publicação, a Release pode ficar com alguns assets novos e outros
  já renomeados para `.anterior`. Se faltar `bronze.tar.gz` ou `silver.parquet`, o run seguinte cai
  no caminho de 1ª execução (backfill desde 2015). Isso reconstrói tudo, só fica mais lento.

## 5. Limites e custo da Release

Na documentação do GitHub ("About releases", lida em 22/11/2026): *"Each file included in a release must be
under 2 GiB. There is no limit on the total size of a release, nor bandwidth usage."* e *"Up to 1000
release assets may be associated with a single release."* Releases não têm custo e não pedem cartão. O repo é
público, e por isso os minutos do Actions também não são cobrados (informação de plano, não conferida nesta fase).

Tamanho dos assets no ensaio (seção 6): `bronze.tar.gz` 892 666 B, `silver.parquet` 1 188 237 B,
`fato_cotacao_diaria.parquet` 2 819 272 B, `dim_calendario.parquet` 11 690 B, `dim_ativo.parquet`
1 505 B, `last_run.json` 876 B. São **~4,9 MB** no total, contra o teto de 2 GiB por arquivo. Com os `.anterior`, a Release fica com ~10 MB.

A Release é criada como **pre-release** para não aparecer como "Latest" na página do repo.

Link público de leitura do gold (só existe depois do 1º run com sucesso):
`https://github.com/Daviramos7/stock_data_pipeline/releases/download/data-latest/fato_cotacao_diaria.parquet`

## 6. Ensaio local (sem gh, sem publicar)

Medido em **22/11/2026 (domingo), 13:58–14:05 BRT**, na mesma máquina da Fase 4: AMD Ryzen 7 5700X,
31,9 GB de RAM, Windows 11 Home (build 26200), Python 3.13.9, dbt-core 1.12.7, dbt-duckdb 1.11.1, duckdb 2.0.1.
Pasta base temporária no scratchpad. O `data/` real não foi tocado: o sha256 do silver real é o mesmo antes e depois (`0880693c…`).
O ensaio baixou dados de verdade do yfinance.

| Comando | Wall (Measure-Command) | ingestão | dbt | export | Resultado |
| --- | ---: | ---: | ---: | ---: | --- |
| `orquestrar --modo backfill --inicio 2015-01-01 --fim 2026-11-21` (pasta vazia) | não medido¹ | 3,23 s | 6,96 s | 0,10 s | ok, PASS=35 WARN=1 ERROR=0 |
| o mesmo, de novo | 9,46 s | — | — | — | ok |
| `orquestrar --modo diario` (1º) | 8,44 s | 2,21 s | 5,25 s | 0,10 s | ok, PUBLICAR criado |
| `orquestrar --modo diario` (2º) | 8,39 s | 2,20 s | 5,27 s | 0,10 s | ok, PUBLICAR criado |

¹ A 1ª rodada foi cronometrada só pelo `duracao_s.total` do `last_run.json`: **10,29 s**.

Linhas: silver **29 708**, `fato_cotacao_diaria` **29 654**, `dim_ativo` **10**, `dim_calendario` **9 496**.
Os números de linhas batem com `docs/fase4/medicoes.md`.

O sha256 do silver é o mesmo nos dois diários (`a2031531c73c6236…`), então o diário é idempotente.

Diferença com o gold da Fase 4: as linhas são as mesmas, mas o `fato_cotacao_diaria.parquet` tem
2 819 272 B contra 2 818 907 B. Comparando o silver real (baixado mais cedo no mesmo dia) com o do ensaio,
open/high/low/close/volume são **idênticos** em todas as linhas. Só o `adj_close` difere, em 20 617
linhas, com diferença relativa máxima de **1,4e-6**, que é ruído de float do ajuste que o Yahoo recalcula a cada download.
Essa diferença se espalha para `fator_ajuste`, preços ajustados e indicadores do fato.

O que o ensaio **não** cobriu: `gh release download/upload`, rename de asset pela API, o commit do
status e o runner Linux. Isso só dá para testar no 1º run real, depois do merge.
