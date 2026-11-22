-- Linha em dia sem pregão (severity error): o fato não pode ter linha em dia que o
-- calendário da bolsa marca como não-pregão, nem em dia fora do calendário.
{{ config(severity='error') }}
select f.ticker, f.bolsa, f.data, c.eh_pregao
from {{ ref('fato_cotacao_diaria') }} f
left join {{ ref('dim_calendario') }} c on c.bolsa = f.bolsa and c.data = f.data
where c.eh_pregao is distinct from true
