-- Silver da Fase 3, sem transformação além de tipos. Caminho via var silver_path.
select
    cast(ticker as varchar)      as ticker,
    cast(data as date)           as data,
    cast(open as double)         as open,
    cast(high as double)         as high,
    cast(low as double)          as low,
    cast(close as double)        as close,
    cast(adj_close as double)    as adj_close,
    cast(volume as bigint)       as volume,
    cast(dividends as double)    as dividends,
    cast(splits as double)       as splits,
    cast(ingest_date as date)    as ingest_date
from read_parquet('{{ var("silver_path") }}')
