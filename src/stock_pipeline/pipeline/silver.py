"""Silver: todo o bronze tipado, validado e deduplicado por (ticker, data).

Ordem: valida ANTES de deduplicar. Se a versão mais nova de um (ticker, data) vier
inválida (ex.: close = 0), a versão válida mais antiga continua no silver em vez de
sumir. "Nunca apagar dado bom" vale mais do que a ordem literal tipa->dedup->valida.
"""
from pathlib import Path

import pandas as pd
import pyarrow as pa

from .bronze import ler_bronze
from .esquema import COLUNAS_PRECO, SCHEMA_COM_INGESTAO, gravar_parquet, ler_parquet

SCHEMA_REJEITADAS = pa.schema([*SCHEMA_COM_INGESTAO, pa.field("motivo", pa.string())])


def caminho_silver(base: Path) -> Path:
    return Path(base) / "silver" / "cotacoes.parquet"


def caminho_rejeitadas(base: Path) -> Path:
    return Path(base) / "silver" / "_rejeitadas.parquet"


def ler_silver(base: Path) -> pd.DataFrame:
    caminho = caminho_silver(base)
    if not caminho.exists():
        return SCHEMA_COM_INGESTAO.empty_table().to_pandas()
    return ler_parquet(caminho)


def _motivos(df: pd.DataFrame) -> pd.Series:
    """Motivo(s) da rejeição por linha, separados por ';'. Vazio = linha válida."""
    regras = {f"{c}<=0_ou_nulo": ~(df[c] > 0) for c in COLUNAS_PRECO}
    regras["high<low"] = ~(df["high"] >= df["low"])
    regras["volume<0_ou_nulo"] = ~(df["volume"] >= 0)
    motivo = pd.Series("", index=df.index, dtype=object)
    for nome, falhou in regras.items():
        falhou = falhou.fillna(True).astype(bool)  # comparação com nulo = inválida
        motivo = motivo.where(~falhou, motivo + nome + ";")
    return motivo.str.rstrip(";")


def construir_silver(base: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reconstrói silver e rejeitadas a partir de todo o bronze e grava os dois."""
    bronze = ler_bronze(base)
    for coluna in [*COLUNAS_PRECO, "dividends", "splits"]:
        bronze[coluna] = bronze[coluna].astype("float64")
    bronze["volume"] = bronze["volume"].astype("Int64")

    motivo = _motivos(bronze)
    invalidas = motivo != ""
    rejeitadas = bronze[invalidas].assign(motivo=motivo[invalidas])
    rejeitadas = rejeitadas.sort_values(["ticker", "data", "ingest_date"]).reset_index(drop=True)

    silver = (bronze[~invalidas]
              .sort_values(["ticker", "data", "ingest_date"])
              .drop_duplicates(["ticker", "data"], keep="last")
              .reset_index(drop=True))
    silver["volume"] = silver["volume"].astype("int64")

    gravar_parquet(silver, caminho_silver(base), SCHEMA_COM_INGESTAO)
    gravar_parquet(rejeitadas, caminho_rejeitadas(base), SCHEMA_REJEITADAS)
    return silver, rejeitadas
