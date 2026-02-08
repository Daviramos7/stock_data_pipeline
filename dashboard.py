import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
from datetime import timedelta, date

st.set_page_config(
    page_title="Dashboard Pro - Análise Técnica",
    page_icon="📊",
    layout="wide"
)

TICKER_MAP = {
    "PETR4.SA": "Petrobras",
    "VALE3.SA": "Vale",
    "ITUB4.SA": "Itaú Unibanco",
    "BBAS3.SA": "Banco do Brasil",
    "WEGE3.SA": "WEG",
    "MGLU3.SA": "Magazine Luiza",
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "GOOGL": "Google",
    "NVDA": "Nvidia"
}

@st.cache_data(ttl=3600)
def carregar_dados_api(ticker, data_inicio, data_fim):
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

def processar_indicadores(df):
    inicio_calc = time.time()
    df = df.copy()
    
    df['SMA_20'] = df['fechamento'].rolling(window=20).mean()
    df['SMA_50'] = df['fechamento'].rolling(window=50).mean()
    
    std = df['fechamento'].rolling(window=20).std()
    df['Bollinger_Upper'] = df['SMA_20'] + (std * 2)
    df['Bollinger_Lower'] = df['SMA_20'] - (std * 2)
    
    delta = df['fechamento'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    df['Retorno_Diario'] = df['fechamento'].pct_change()
    df['Volatilidade_Anual'] = df['Retorno_Diario'].rolling(window=21).std() * (252**0.5) * 100
    
    tempo_calc = time.time() - inicio_calc
    return df, tempo_calc

def criar_grafico_avancado(df, ticker):
    fig = make_subplots(
        rows=2, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.05, 
        row_heights=[0.7, 0.3],
        subplot_titles=(f"Preço e Bandas de Bollinger - {ticker}", "RSI (Índice de Força Relativa)")
    )

    fig.add_trace(go.Candlestick(
        x=df['data'], open=df['abertura'], high=df['maxima'],
        low=df['minima'], close=df['fechamento'], name='Preço'
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=df['data'], y=df['Bollinger_Upper'], 
        line=dict(color='rgba(173, 216, 230, 0.5)', width=1), name='Bollinger Sup'
    ), row=1, col=1)
    
    fig.add_trace(go.Scatter(
        x=df['data'], y=df['Bollinger_Lower'], 
        line=dict(color='rgba(173, 216, 230, 0.5)', width=1), 
        fill='tonexty', fillcolor='rgba(173, 216, 230, 0.1)', name='Bollinger Inf'
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=df['data'], y=df['SMA_20'], 
        line=dict(color='orange', width=1.5), name='Média 20d'
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=df['data'], y=df['RSI'], 
        line=dict(color='purple', width=2), name='RSI'
    ), row=2, col=1)

    fig.add_shape(type="line", x0=df['data'].iloc[0], x1=df['data'].iloc[-1], y0=70, y1=70,
                  line=dict(color="red", width=1, dash="dot"), row=2, col=1)
    fig.add_shape(type="line", x0=df['data'].iloc[0], x1=df['data'].iloc[-1], y0=30, y1=30,
                  line=dict(color="green", width=1, dash="dot"), row=2, col=1)

    fig.update_layout(
        height=800,
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    
    fig.update_yaxes(title_text="Preço", row=1, col=1)
    fig.update_yaxes(title_text="RSI (0-100)", range=[0, 100], row=2, col=1)
    
    return fig

st.title("📈 Dashboard de Análise Quantitativa")

st.sidebar.header("Configurações")
ticker_selecionado = st.sidebar.selectbox("Ativo:", options=TICKER_MAP.keys(), format_func=lambda t: f"{t} - {TICKER_MAP[t]}")

data_fim = date.today()
data_inicio = st.sidebar.date_input("Início:", value=data_fim - timedelta(days=365), max_value=data_fim)
data_fim_input = st.sidebar.date_input("Fim:", value=data_fim, min_value=data_inicio, max_value=data_fim)

df_raw, tempo_download = carregar_dados_api(ticker_selecionado, data_inicio, data_fim_input)

if not df_raw.empty:
    df_raw = df_raw.sort_values(by='data')
    df_analise, tempo_calc = processar_indicadores(df_raw)
    
    linhas_proc = len(df_analise)
    velocidade = linhas_proc / tempo_calc if tempo_calc > 0 else 0

    st.sidebar.markdown("---")
    st.sidebar.subheader("🚀 Performance (Benchmark)")
    st.sidebar.metric("Download (API)", f"{tempo_download:.4f} s")
    st.sidebar.metric("Cálculo (CPU)", f"{tempo_calc:.4f} s")
    st.sidebar.caption(f"Processou {linhas_proc} registros a {velocidade:,.0f} reg/s")

    col1, col2, col3, col4 = st.columns(4)
    ultimo = df_analise.iloc[-1]
    penultimo = df_analise.iloc[-2]
    
    var_preco = ultimo['fechamento'] - penultimo['fechamento']
    var_pct = (var_preco / penultimo['fechamento']) * 100
    
    col1.metric("Preço Atual", f"R$ {ultimo['fechamento']:.2f}", f"{var_pct:.2f}%")
    col2.metric("RSI (14d)", f"{ultimo['RSI']:.1f}", delta=None)
    col3.metric("Volatilidade Anual", f"{ultimo['Volatilidade_Anual']:.1f}%")
    
    tendencia = "Alta" if ultimo['fechamento'] > ultimo['SMA_20'] else "Baixa"
    cor_tend = "normal" if tendencia == "Alta" else "off"
    col4.metric("Tendência (20d)", tendencia, delta_color=cor_tend)

    tab1, tab2 = st.tabs(["📊 Gráfico Técnico", "🗃️ Base de Dados"])
    
    with tab1:
        fig = criar_grafico_avancado(df_analise, ticker_selecionado)
        st.plotly_chart(fig, use_container_width=True)
        
    with tab2:
        st.dataframe(df_analise.sort_values('data', ascending=False), use_container_width=True)

else:
    st.error("Falha ao carregar dados. Verifique o ticker ou o período.")