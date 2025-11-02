import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import time
from datetime import timedelta, date

st.set_page_config(
    page_title="Dashboard de Ações",
    page_icon="📈",
    layout="wide"
)

TICKER_MAP = {
    "PETR4.SA": "Petrobras",
    "MGLU3.SA": "Magazine Luiza",
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "GOOGL": "Google"
}

@st.cache_data(ttl=3600)
def carregar_dados_api(ticker, data_inicio, data_fim):
    print(f"[{time.strftime('%H:%M:%S')}] Buscando dados da API para {ticker}...")
    data_fim_yf = data_fim + timedelta(days=1)
    
    dados = yf.download(ticker, start=data_inicio, end=data_fim_yf, auto_adjust=True)
    
    if dados.empty:
        return pd.DataFrame()

    if isinstance(dados.columns, pd.MultiIndex):
        dados.columns = dados.columns.get_level_values(0)

    dados = dados.reset_index()
    dados['ticker'] = ticker
    dados.columns = dados.columns.str.lower()
    
    dados = dados.rename(columns={
        "date": "data",
        "open": "abertura",
        "high": "maxima",
        "low": "minima",
        "close": "fechamento"
    })
    
    dados['data'] = pd.to_datetime(dados['data']).dt.tz_localize(None)
    
    colunas_finais = ['data', 'ticker', 'abertura', 'maxima', 'minima', 'fechamento', 'volume']
    colunas_existentes = [col for col in colunas_finais if col in dados.columns]
    
    print(f"[{time.strftime('%H:%M:%S')}] Carga de {len(dados)} registros da API concluída.")
    return dados[colunas_existentes]

def calcular_medias_moveis(df, janelas=[7, 21]):
    df_calculado = df.copy()
    for janela in janelas:
        nome_coluna = f"mm_{janela}d"
        df_calculado[nome_coluna] = df_calculado['fechamento'].rolling(window=janela).mean()
    return df_calculado

def criar_grafico_plotly(df, ticker):
    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df['data'],
        open=df['abertura'],
        high=df['maxima'],
        low=df['minima'],
        close=df['fechamento'],
        name='Candlestick',
        increasing_line_color='green',
        decreasing_line_color='red'
    ))

    if 'mm_7d' in df.columns:
        fig.add_trace(go.Scatter(
            x=df['data'], 
            y=df['mm_7d'],
            mode='lines',
            name='Média Móvel 7 Dias',
            line=dict(color='orange', width=1, dash='dot')
        ))
    
    if 'mm_21d' in df.columns:
        fig.add_trace(go.Scatter(
            x=df['data'], 
            y=df['mm_21d'],
            mode='lines',
            name='Média Móvel 21 Dias',
            line=dict(color='purple', width=1, dash='dot')
        ))

    fig.update_layout(
        title=f'Análise Histórica - {ticker}',
        xaxis_title='Data',
        yaxis_title='Preço (R$ ou U$)',
        legend_title='Métricas',
        hovermode="x unified",
        xaxis_rangeslider_visible=False,
        dragmode=False # Trava o "arrastar" do gráfico
    )
    
    fig.update_xaxes(fixedrange=True) # Trava o zoom/pan do eixo X
    fig.update_yaxes(fixedrange=True) # Trava o zoom/pan do eixo Y
    
    return fig

st.title("📈 Dashboard de Análise de Ações (Live API)")

st.sidebar.header("Filtros")

ticker_selecionado = st.sidebar.selectbox(
    "Selecione o Ticker:",
    options=TICKER_MAP.keys(), 
    format_func=lambda ticker: f"{ticker} - {TICKER_MAP[ticker]}" 
)

data_max_global = date.today()
data_min_global = data_max_global - timedelta(days=365*5)
data_inicio_padrao = data_max_global - timedelta(days=180)

data_inicio = st.sidebar.date_input(
    "Data Início",
    value=data_inicio_padrao,
    min_value=data_min_global,
    max_value=data_max_global
)

data_fim = st.sidebar.date_input(
    "Data Fim",
    value=data_max_global,
    min_value=data_inicio,
    max_value=data_max_global
)

st.header(f"Analisando: {ticker_selecionado} ({TICKER_MAP[ticker_selecionado]})")

df_filtrado_final = carregar_dados_api(ticker_selecionado, data_inicio, data_fim)

if not df_filtrado_final.empty:
    df_filtrado_final = df_filtrado_final.sort_values(by='data')
    df_analise = calcular_medias_moveis(df_filtrado_final, janelas=[7, 21])
    
    ultimo_dia = df_analise.iloc[-1]
    
    if len(df_analise) > 1:
        penultimo_dia = df_analise.iloc[-2]
        ultimo_fechamento = ultimo_dia['fechamento']
        delta_fechamento_abs = ultimo_dia['fechamento'] - penultimo_dia['fechamento']
        delta_fechamento_pct = (delta_fechamento_abs / penultimo_dia['fechamento']) * 100
    else:
        ultimo_fechamento = ultimo_dia['fechamento']
        delta_fechamento_abs = 0
        delta_fechamento_pct = 0
    
    st.metric(
        label=f"Último Fechamento ({ultimo_dia['data'].strftime('%d/%m')})",
        value=f"{ultimo_fechamento:.2f}",
        delta=f"{delta_fechamento_abs:.2f} ({delta_fechamento_pct:.2f}%)"
    )
    st.metric(
        label="Máxima (no período)",
        value=f"{df_analise['maxima'].max():.2f}"
    )
    st.metric(
        label="Mínima (no período)",
        value=f"{df_analise['minima'].min():.2f}"
    )
        
    st.divider()

    tab_grafico, tab_dados = st.tabs(["📈 Gráfico", "🗃️ Dados Detalhados"])

    with tab_grafico:
        fig = criar_grafico_plotly(df_analise, ticker_selecionado)
        st.plotly_chart(fig, use_container_width=True)
    
    with tab_dados:
        st.subheader(f"Dados Detalhados ({data_inicio.strftime('%d/%m/%Y')} até {data_fim.strftime('%d/%m/%Y')})")
        st.dataframe(df_analise.sort_values(by='data', ascending=False), use_container_width=True)
    
else:
    st.warning("Nenhum dado encontrado para o ticker e período selecionados na API do Yahoo Finance.")