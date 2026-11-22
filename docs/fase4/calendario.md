# Fase 4 — calendário de pregão × silver

Conferência de 22/11/2026: `dbt/seeds/dim_calendario.csv` (exchange_calendars 4.13.3, BVMF e XNYS)
contra todas as datas de `data/silver/cotacoes.parquet` (2015-01-02 a 2026-11-20).

- **NYSE (XNYS)**: 2 990 pregões na lib = 2 990 datas no silver. Nenhuma divergência.
- **B3 (BVMF)**: 2 950 pregões na lib × 2 958 datas no silver. Todas as divergências são do Yahoo, nenhuma da lib:
  - 9 dias de 2017/2018 com linha no silver em feriado (Corpus Christi, 7/9, 12/10, 2/11, 15/11, 20/11, 25/12, 29/12/2017 e 25/01/2018), em todos os 6 tickers. São linhas-fantasma: volume 0 e OHLC = fechamento anterior (conferido em PETR4).
  - 20/11/2020: a lib marca pregão e o silver não tem a linha. **Teve pregão**: o Ibovespa fechou em −0,59% a 106 042 pts ([IstoÉ Dinheiro, 20/11/2020](https://www.istoedinheiro.com.br/bolsa-fecha-em-baixa-de-059-a-106-04248-pontos-mas-avanca-126-na-semana)). Quem falha é o Yahoo.
- **20/11 (Consciência Negra)**: a lib marca sem pregão em 2024, 2025 e 2026 (feriado nacional desde 2024, [nota da B3](https://www.b3.com.br/pt_br/noticias/veja-como-sera-o-funcionamento-da-b3-no-feriado-nacional-de-zumbi-e-consciencia-negra.htm)) e com pregão em 2023 e 2020, o que bate com o silver e com a fonte acima.

Como a lib não errou, `EXCECOES` em `scripts/gerar_calendario.py` está vazia. As falhas da
fonte ficam em `dbt/seeds/excecoes_fonte.csv`: as `linha_fantasma` são descartadas do fato, e o
`pregao_ausente_na_fonte` é ignorado pelo teste `pregao_faltando`. Só o que está listado ali é
perdoado: qualquer caso novo derruba o `dbt build` (com o seed vazio, os testes falham com 54 e 6
linhas, conferido).

Também visto e não tratado: 14 linhas com volume 0 em dia de pregão de verdade (ex.: 29/05/2017
em todos os tickers B3). Nenhum teste pedido pega isso. Fica como candidato a teste `warn`.
