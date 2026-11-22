-- Volume 0 em dia de pregão (severity warn), só nos últimos var('janela_volume_zero')
-- pregões de cada bolsa até var('hoje') (contados no dim_calendario, não em dias corridos).
-- Volume 0 com OHLC = fechamento anterior é o Yahoo repetindo a linha de ontem: interessa
-- como sintoma de falha RECENTE do fornecedor. O histórico (14 linhas, sem fonte externa
-- pra triar) foi medido e documentado em docs/fase6/alertas.md, fora do alerta.
{{ config(severity='warn') }}
{% set hoje = var('hoje', modules.datetime.date.today().isoformat()) %}
with janela as (
    select bolsa, data
    from (
        select bolsa, data,
               row_number() over (partition by bolsa order by data desc) as n
        from {{ ref('dim_calendario') }}
        where eh_pregao and data <= cast('{{ hoje }}' as date)
    )
    where n <= {{ var('janela_volume_zero') }}
),
r as (
    select ticker, bolsa, data, close, volume,
           lag(close) over (partition by ticker order by data) as close_anterior
    from {{ ref('fato_cotacao_diaria') }}
)
select r.ticker, r.bolsa, r.data, r.close, r.close_anterior, r.volume
from r
join janela j on j.bolsa = r.bolsa and j.data = r.data
where r.volume = 0
