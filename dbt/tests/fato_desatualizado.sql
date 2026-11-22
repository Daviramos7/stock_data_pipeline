-- Freshness (severity error): para cada bolsa, a última data no fato tem que ser o
-- último pregão do calendário ANTES de var('hoje'), com tolerância de 1 pregão (aceita
-- o penúltimo). var('hoje') tem default a data atual; os testes e o CI passam outra:
--   dbt build --vars "{hoje: '2026-11-23'}"
-- Uma linha devolvida = bolsa atrasada (ou sem dado nenhum).
{{ config(severity='error') }}
{% set hoje = var('hoje', modules.datetime.date.today().isoformat()) %}
with pregoes as (
    select bolsa, data,
           row_number() over (partition by bolsa order by data desc) as n
    from {{ ref('dim_calendario') }}
    where eh_pregao and data < cast('{{ hoje }}' as date)
),
minimo as (
    -- n = 2: o penúltimo pregão antes de hoje (tolerância de 1 pregão)
    select bolsa,
           max(case when n = 1 then data end) as ultimo_pregao,
           max(case when n = 2 then data end) as minimo_aceito
    from pregoes where n <= 2 group by bolsa
),
ultimo_fato as (
    select bolsa, max(data) as ultima_data from {{ ref('fato_cotacao_diaria') }} group by bolsa
)
select m.bolsa, m.ultimo_pregao, m.minimo_aceito, u.ultima_data,
       '{{ hoje }}' as hoje
from minimo m
join (select distinct bolsa from {{ ref('dim_ativo') }}) a using (bolsa)
left join ultimo_fato u using (bolsa)
where u.ultima_data is null or u.ultima_data < m.minimo_aceito
