-- Salto de adj_close (severity warn): variação diária absoluta acima de var('limiar_salto')
-- (25%) sem dividendo nem split no dia. Ação brasileira não tem limite de oscilação
-- diário, mas 25% num dia é raro o bastante para merecer olho humano; é warn porque
-- pode ser movimento real (ex.: crash de mar/2020), não erro de dado.
{{ config(severity='warn') }}
with r as (
    select ticker, data, adj_close, dividends, splits,
           lag(adj_close) over (partition by ticker order by data) as adj_anterior
    from {{ ref('fato_cotacao_diaria') }}
)
select ticker, data, adj_anterior, adj_close,
       adj_close / adj_anterior - 1 as variacao
from r
where adj_anterior is not null
  and abs(adj_close / adj_anterior - 1) > {{ var('limiar_salto') }}
  and coalesce(dividends, 0) = 0
  and coalesce(splits, 0) = 0
