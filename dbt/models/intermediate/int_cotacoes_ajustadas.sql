-- Preço ajustado no estilo auto_adjust=True do yfinance: OHLC × (adj_close / close).
-- Descarta só as linhas-fantasma listadas em excecoes_fonte (falha conhecida do Yahoo);
-- qualquer outra linha em dia sem pregão segue e derruba o teste linha_sem_pregao.
with cot as (
    select s.*, a.bolsa
    from {{ ref('stg_cotacoes') }} s
    join {{ ref('dim_ativo') }} a using (ticker)
),
fantasmas as (
    select bolsa, data from {{ ref('excecoes_fonte') }} where tipo = 'linha_fantasma'
)
select
    cot.ticker,
    cot.data,
    cot.bolsa,
    cot.open, cot.high, cot.low, cot.close,
    cot.adj_close,
    cot.adj_close / cot.close                  as fator_ajuste,
    cot.open * (cot.adj_close / cot.close)     as open_ajustado,
    cot.high * (cot.adj_close / cot.close)     as high_ajustado,
    cot.low  * (cot.adj_close / cot.close)     as low_ajustado,
    cot.volume,
    cot.dividends,
    cot.splits,
    cot.ingest_date
from cot
anti join fantasmas f on f.bolsa = cot.bolsa and f.data = cot.data
