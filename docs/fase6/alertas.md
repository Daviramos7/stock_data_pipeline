# Fase 6: qualidade e alerta por Issue no GitHub

Princípio: alerta bom é raro e acionável. É **uma Issue por problema** (não por dia), com
dedup, comentário só quando muda e fechamento automático quando o problema some. O único
segredo é o `GITHUB_TOKEN` do workflow. Não tem e-mail nem Telegram: o GitHub já notifica
o dono do repositório quando uma Issue é aberta.

Fluxo no `pipeline.yml`: **Orquestrar** → Publicar na Release → **Alertas** → Commitar status.

```
data/last_run.json ─┐
                    ├─ cli alertas ─> data/alertas.json ─> scripts/publicar_alertas.py ─> Issues
data/_dbt/target/   │   (stock_pipeline/pipeline/alertas.py)        (gh issue list/create/comment/close)
  run_results.json ─┘   exemplos: compiled_code de cada teste no warehouse.duckdb (só leitura)
```

## O que é checado

| Chave | Severidade | O que é |
| --- | --- | --- |
| `falha-pipeline` | erro | Uma etapa do orquestrador caiu (ingestão, dbt ou export), ou ele nem rodou. Nada é publicado. |
| `dbt:fato_desatualizado` | erro | Freshness: a última data do fato, por bolsa, tem que ser o último pregão do calendário **antes** de `hoje`, com tolerância de 1 pregão. |
| `dbt:pregao_faltando` | erro | Há pregão no calendário sem linha no fato (ignora `pregao_ausente_na_fonte`). |
| `dbt:linha_sem_pregao` | erro | Linha em dia sem pregão (ignora `linha_fantasma`). |
| `dbt:<outros testes>` | erro | Chave única, `not_null`, preço positivo, high ≥ low, relacionamentos, testes dos seeds. |
| `dbt:salto_sem_evento` | aviso | \|variação diária do adj_close\| > 25%, sem provento nem split no dia e fora de `eventos_conhecidos.csv`. |
| `dbt:volume_zero_em_pregao` | aviso | Volume 0 em dia de pregão, só nos últimos `janela_volume_zero` (10) pregões de cada bolsa até `hoje`. |

Severidade: teste dbt com status `fail`/`error` vira **erro**; `warn` vira **aviso**. O
erro deixa o job vermelho (é o orquestrador que falha, não o passo de alertas); o aviso não.

Corpo da Issue: o que aconteceu, quantas linhas (contagem do próprio dbt), até 20 exemplos
(`order by all`, então são sempre os mesmos e na mesma ordem), link do run e "o que fazer".
No salto, os exemplos trazem ticker, data, adj_close antes → depois, variação %, se houve
dividendo/split no dia e quantos pregões com provento/split há a até 3 pregões (o Yahoo às
vezes data o evento no dia vizinho).

A data de referência do freshness é a var `hoje` (default: a data atual). Para testar:
`cd dbt; dbt test --select fato_desatualizado --vars "{hoje: '2026-11-25'}"`. O job `dbt`
do CI passa como `hoje` o dia seguinte ao fim do silver sintético.

## Ciclo de vida da Issue

Só são consideradas Issues **abertas** com o rótulo `alerta-pipeline` e o marcador
`<!-- chave: X -->` no corpo. Issue com o rótulo mas sem marcador (aberta por gente) é ignorada.

1. **Abre**: chave apareceu e não há Issue aberta com ela → cria `[pipeline] <título>` com os
   rótulos `alerta-pipeline` + `alerta:erro` ou `alerta:aviso`.
2. **Comenta**: chave continua aparecendo → comenta "Ainda ocorrendo em <data>, run <url>"
   **só** se a assinatura mudou (hash do conteúdo: contagem + exemplos, sem link e sem data)
   ou se o último comentário do bot tem 7 dias ou mais. Se mudou, o comentário traz o corpo novo.
3. **Fecha**: Issue aberta cuja chave não apareceu neste run → comenta "Resolvido no run <url>"
   e fecha. Só vale para chaves que o run de fato verificou (`escopo`): se a ingestão caiu e
   o dbt nem rodou, as Issues `dbt:*` ficam como estão.
4. Se o problema voltar depois de fechado, abre uma Issue nova.

Robustez: o passo nunca derruba o job (`continue-on-error` e o script sai 0; erro na API
vira `::warning::`). Se não der pra listar as Issues abertas, não publica nada (melhor do
que abrir duplicata). Se o comentário de "resolvido" falhar, a Issue não é fechada calada.

Rodar local (sem escrever nada no GitHub):

```
python -m stock_pipeline.pipeline.cli --data-dir data alertas --saida data/alertas.json
python scripts/publicar_alertas.py --alertas data/alertas.json --dry-run
```

## Como registrar um evento conhecido

Para um salto que é real e está explicado (grupamento, fato relevante, oferta, crash de mercado):

1. Achar a fonte primária (fato relevante na CVM/RI, comunicado da B3) ou uma notícia confiável.
2. Acrescentar uma linha em `dbt/seeds/eventos_conhecidos.csv`:
   `ticker,data,tipo,descricao,fonte_url`, por exemplo
   `XXXX3.SA,2026-01-02,grupamento,"Grupamento 10:1 aprovado em AGE",https://...`.
   `fonte_url` é obrigatório (teste `not_null`); (ticker, data) é único e o ticker tem que existir em `dim_ativo`.
3. Abrir PR. No primeiro run depois do merge, a linha some do teste e, se não sobrar
   nenhuma, a Issue de saltos fecha sozinha (se sobrar, ela recebe comentário com o conteúdo novo).

Salto que é **erro da fonte** não entra no seed: é dado errado e tem que ser tratado na origem.

## Como testar a falha de propósito

`Actions → pipeline → Run workflow` com **`simular_falha: true`**. O orquestrador falha na
ingestão sem baixar nada (`orquestrar --simular-falha`), não cria `data/PUBLICAR` (nada vai
pra Release), o job fica vermelho e abre a Issue `falha-pipeline`. No agendado o input não
existe e vale `false`. O próximo run normal fecha a Issue.

## Linhas-fantasma: medição e decisão (pendência da Fase 4)

Pergunta: dá pra rejeitar as linhas-fantasma já no silver, por uma regra sobre o próprio
dado, e tirar as entradas `linha_fantasma` de `excecoes_fonte.csv`?

Medição no silver real (`data/silver/cotacoes.parquet`, 29 708 linhas, 22/11/2026), regra
candidata **volume = 0 E open = high = low = close = fechamento anterior**:

| Grupo | Linhas | Batem na regra |
| --- | ---: | ---: |
| Linhas-fantasma (9 feriados B3 de 2017/18 × 6 tickers) | 54 | 54 |
| Volume 0 em pregão real (calendário BVMF) | 14 | **14** |

As 14 de pregão real têm exatamente a mesma assinatura: o Yahoo repete a linha do dia
anterior (2017-05-29 nos 6 tickers B3; ITUB4 2017-11-06; BBAS3/MGLU3 2022-05-16 e 2023-06-02;
WEGE3 2022-09-26; VALE3/BBAS3 2024-04-26). Sem o calendário, o dado sozinho não distingue
uma da outra, e o silver não conhece o calendário (é papel do gold).

**Decisão: não rejeitar no silver.** A regra pegaria pregões reais e apagaria linhas que,
mesmo suspeitas, são de dias em que houve pregão (rejeitar ali abriria buraco e derrubaria
`pregao_faltando`). A exceção continua no gold (`excecoes_fonte.csv`, tipo `linha_fantasma`),
e as 14 de pregão real ficam documentadas aqui (lista acima), **fora do alerta**.

### Janela do teste de volume 0

Para essas 14 linhas não há fonte externa que permita triar (o Yahoo só repete a linha
anterior), então um alerta sobre elas nunca fecharia e viraria ruído. Volume 0 interessa
como sintoma de falha **recente** do fornecedor: o teste `volume_zero_em_pregao` olha só os
últimos `var('janela_volume_zero')` pregões de cada bolsa até `var('hoje')` (default 10,
em `dbt/dbt_project.yml`), contados no `dim_calendario` e não em dias corridos. No dado
real de 22/11/2026 ele passa; num silver sintético com volume 0 no último pregão e outro
fora da janela, ele dá WARN 1 (só o recente).
