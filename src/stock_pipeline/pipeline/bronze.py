"""Bronze: bruto do yfinance particionado por data de ingestão.

Caminho determinístico: data/bronze/ingest_date=YYYY-MM-DD/cotacoes.parquet.
Rodar de novo no mesmo dia regrava o MESMO arquivo. A gravação faz merge com o que
já está lá (o novo ganha em (ticker, data)): assim um `diario` depois de um `backfill`
no mesmo dia não troca 11 anos de bruto por 7 dias. Mesmos dados -> mesmo arquivo.
"""
from datetime import date
from pathlib import Path

import pandas as pd

from .esquema import SCHEMA_COM_INGESTAO, gravar_parquet, ler_parquet

ARQUIVO = "cotacoes.parquet"


def caminho_bronze(base: Path, ingest_date: date) -> Path:
    return Path(base) / "bronze" / f"ingest_date={ingest_date.isoformat()}" / ARQUIVO


def gravar_bronze(df: pd.DataFrame, base: Path, ingest_date: date) -> Path:
    caminho = caminho_bronze(base, ingest_date)
    novo = df.copy()
    novo["ingest_date"] = ingest_date
    if caminho.exists():
        novo = pd.concat([ler_parquet(caminho), novo], ignore_index=True)
    novo = (novo.drop_duplicates(["ticker", "data"], keep="last")
                .sort_values(["ticker", "data"]).reset_index(drop=True))
    gravar_parquet(novo, caminho, SCHEMA_COM_INGESTAO)
    return caminho


def ler_bronze(base: Path) -> pd.DataFrame:
    arquivos = sorted((Path(base) / "bronze").glob(f"ingest_date=*/{ARQUIVO}"))
    if not arquivos:
        return SCHEMA_COM_INGESTAO.empty_table().to_pandas()
    return pd.concat([ler_parquet(a) for a in arquivos], ignore_index=True)
