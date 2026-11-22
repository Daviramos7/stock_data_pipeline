{% test expressao_verdadeira(model, expressao) %}
select * from {{ model }} where not ({{ expressao }})
{% endtest %}
