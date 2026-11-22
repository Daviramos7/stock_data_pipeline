"""Cálculo dos indicadores técnicos."""
import time


def processar_indicadores(df):
    inicio_calc = time.time()
    df = df.copy()
    
    df['SMA_20'] = df['fechamento'].rolling(window=20).mean()
    df['SMA_50'] = df['fechamento'].rolling(window=50).mean()
    
    std = df['fechamento'].rolling(window=20).std()
    df['Bollinger_Upper'] = df['SMA_20'] + (std * 2)
    df['Bollinger_Lower'] = df['SMA_20'] - (std * 2)
    
    delta = df['fechamento'].diff()
    # RSI de Wilder (14): média exponencial com alpha = 1/14.
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    df['Retorno_Diario'] = df['fechamento'].pct_change()
    df['Volatilidade_Anual'] = df['Retorno_Diario'].rolling(window=21).std() * (252**0.5) * 100
    
    tempo_calc = time.time() - inicio_calc
    return df, tempo_calc
