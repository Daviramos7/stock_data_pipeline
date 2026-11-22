"""Esquema único das tabelas do pipeline e gravação atômica de Parquet."""
import os
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

COLUNAS_PRECO = ["open", "high", "low", "close", "adj_close"]
COLUNAS_LONGAS = ["ticker", "data", *COLUNAS_PRECO, "volume", "dividends", "splits"]

# Nomes do yfinance (auto_adjust=False, actions=True) -> nomes do pipeline.
MAPA_YF = {
    "Open": "open", "High": "high", "Low": "low", "Close": "close",
    "Adj Close": "adj_close", "Volume": "volume",
    "Dividends": "dividends", "Stock Splits": "splits",
}

_CAMPOS = [
    pa.field("ticker", pa.string()),
    pa.field("data", pa.date32()),
    *[pa.field(c, pa.float64()) for c in COLUNAS_PRECO],
    pa.field("volume", pa.int64()),
    pa.field("dividends", pa.float64()),
    pa.field("splits", pa.float64()),
]
SCHEMA_LONGO = pa.schema(_CAMPOS)
SCHEMA_COM_INGESTAO = pa.schema([*_CAMPOS, pa.field("ingest_date", pa.date32())])


def vazio_longo() -> pd.DataFrame:
    return SCHEMA_LONGO.empty_table().to_pandas()


def gravar_parquet(df: pd.DataFrame, caminho: Path, schema: pa.Schema) -> None:
    """Grava num .tmp e troca de nome: ou fica o arquivo velho, ou o novo inteiro."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tabela = pa.Table.from_pandas(df[schema.names], schema=schema, preserve_index=False)
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    pq.write_table(tabela, tmp)
    os.replace(tmp, caminho)


def ler_parquet(caminho: Path) -> pd.DataFrame:
    # partitioning=None: sem isso o pyarrow lê "ingest_date=..." da pasta e cria coluna duplicada.
    return pq.read_table(caminho, partitioning=None).to_pandas()
