-- Pregão faltando (severity error): dia de pregão da bolsa do ticker, entre o primeiro
-- e o último dado do ticker, sem linha no fato. Ignora só os pregões que a fonte
-- reconhecidamente não tem (excecoes_fonte.tipo = 'pregao_ausente_na_fonte').
{{ config(severity='error') }}
with limites as (
    select ticker, bolsa, min(data) as primeiro, max(data) as ultimo
    from {{ ref('fato_cotacao_diaria') }}
    group by ticker, bolsa
),
esperado as (
    select l.ticker, l.bolsa, c.data
    from limites l
    join {{ ref('dim_calendario') }} c
      on c.bolsa = l.bolsa and c.eh_pregao and c.data between l.primeiro and l.ultimo
)
select e.*
from esperado e
left join {{ ref('fato_cotacao_diaria') }} f on f.ticker = e.ticker and f.data = e.data
left join {{ ref('excecoes_fonte') }} x
  on x.bolsa = e.bolsa and x.data = e.data and x.tipo = 'pregao_ausente_na_fonte'
where f.ticker is null and x.bolsa is null
