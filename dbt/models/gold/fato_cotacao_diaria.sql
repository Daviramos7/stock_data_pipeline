-- Grão: ticker × data (pregão). Chaves: ticker -> dim_ativo; (bolsa, data) -> dim_calendario.
select
    c.ticker,
    c.data,
    c.bolsa,
    c.open, c.high, c.low, c.close,
    c.adj_close,
    c.fator_ajuste,
    c.open_ajustado, c.high_ajustado, c.low_ajustado,
    c.volume,
    c.dividends,
    c.splits,
    i.retorno_diario,
    i.sma_20, i.sma_50,
    i.bollinger_sup, i.bollinger_inf,
    i.rsi_14,
    i.volatilidade_anual,
    c.ingest_date
from {{ ref('int_cotacoes_ajustadas') }} c
join {{ ref('int_indicadores') }} i using (ticker, data)
order by c.ticker, c.data
