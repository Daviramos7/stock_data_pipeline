import sys
from pathlib import Path

# O Streamlit Cloud roda `streamlit run dashboard.py` a partir da raiz do repo,
# sem instalar o pacote; por isso colocamos src/ no path antes de importá-lo.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import streamlit as st
from datetime import timedelta, date

from stock_pipeline.config import TICKER_MAP
from stock_pipeline.formatting import moeda_do_ticker
from stock_pipeline.ingestion import baixar_cotacoes
from stock_pipeline.indicators import processar_indicadores
from stock_pipeline.charts import criar_grafico_avancado

st.set_page_config(
    page_title="Dashboard Pro - Análise Técnica",
    page_icon="📊",
    layout="wide"
)

@st.cache_data(ttl=3600)
def carregar_dados_api(ticker, data_inicio, data_fim):
    return baixar_cotacoes(ticker, data_inicio, data_fim)

st.title("📈 Dashboard de Análise Quantitativa")
st.caption("Projeto educacional. Não é recomendação de investimento. Dados: Yahoo Finance (yfinance, não oficial).")

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

    if len(df_analise) < 2:
        st.warning("Escolha um período com pelo menos 2 pregões.")
        st.stop()

    col1, col2, col3, col4 = st.columns(4)
    ultimo = df_analise.iloc[-1]
    penultimo = df_analise.iloc[-2]
    
    var_preco = ultimo['fechamento'] - penultimo['fechamento']
    var_pct = (var_preco / penultimo['fechamento']) * 100
    
    col1.metric("Preço Atual", f"{moeda_do_ticker(ticker_selecionado)} {ultimo['fechamento']:.2f}", f"{var_pct:.2f}%")
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