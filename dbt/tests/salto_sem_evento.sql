-- Salto de adj_close (severity warn): variação diária absoluta acima de var('limiar_salto')
-- (25%) sem dividendo nem split no dia. Ação brasileira não tem limite de oscilação
-- diário, mas 25% num dia é raro o bastante para merecer olho humano; é warn porque
-- pode ser movimento real (ex.: crash de mar/2020), não erro de dado.
-- Ignora o que já foi triado em eventos_conhecidos (ticker, data, com fonte).
-- eventos_vizinhos: quantos pregões com provento/split há a até 3 pregões do salto
-- (o Yahoo às vezes data o evento num dia vizinho); ajuda a triagem, não filtra nada.
{{ config(severity='warn') }}
with r as (
    select ticker, data, adj_close, dividends, splits,
           lag(adj_close) over (partition by ticker order by data) as adj_anterior,
           sum(case when coalesce(dividends, 0) <> 0 or coalesce(splits, 0) <> 0 then 1 else 0 end)
               over (partition by ticker order by data rows between 3 preceding and 3 following)
               as eventos_vizinhos
    from {{ ref('fato_cotacao_diaria') }}
)
select r.ticker, r.data, r.adj_anterior, r.adj_close,
       r.adj_close / r.adj_anterior - 1 as variacao,
       coalesce(r.dividends, 0) as dividends, coalesce(r.splits, 0) as splits,
       r.eventos_vizinhos
from r
left join {{ ref('eventos_conhecidos') }} e on e.ticker = r.ticker and e.data = r.data
where r.adj_anterior is not null
  and abs(r.adj_close / r.adj_anterior - 1) > {{ var('limiar_salto') }}
  and coalesce(r.dividends, 0) = 0
  and coalesce(r.splits, 0) = 0
  and e.ticker is null
