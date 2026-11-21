"""Download de cotações via yfinance."""
import time
from datetime import timedelta

import pandas as pd
import yfinance as yf


def baixar_cotacoes(ticker, data_inicio, data_fim):
    inicio = time.time()
    
    data_fim_yf = data_fim + timedelta(days=1)
    dados = yf.download(ticker, start=data_inicio, end=data_fim_yf, auto_adjust=True, progress=False)
    
    if dados.empty:
        return pd.DataFrame(), 0.0

    if isinstance(dados.columns, pd.MultiIndex):
        dados.columns = dados.columns.get_level_values(0)

    dados = dados.reset_index()
    dados.columns = dados.columns.str.lower()
    
    mapa_colunas = {
        "date": "data", "datetime": "data",
        "open": "abertura", "high": "maxima",
        "low": "minima", "close": "fechamento", "volume": "volume"
    }
    dados = dados.rename(columns=mapa_colunas)
    
    dados['data'] = pd.to_datetime(dados['data']).dt.tz_localize(None)
    
    colunas_finais = ['data', 'abertura', 'maxima', 'minima', 'fechamento', 'volume']
    dados = dados[colunas_finais]
    
    tempo_total = time.time() - inicio
    return dados, tempo_total
