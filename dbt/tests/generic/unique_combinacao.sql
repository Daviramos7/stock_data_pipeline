{% test unique_combinacao(model, colunas) %}
select {{ colunas | join(', ') }}, count(*) as n
from {{ model }}
group by {{ colunas | join(', ') }}
having count(*) > 1
{% endtest %}
