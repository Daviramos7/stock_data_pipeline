import sys
from pathlib import Path

# O Streamlit Cloud roda `streamlit run dashboard.py` a partir da raiz do repo,
# sem instalar o pacote; por isso colocamos src/ no path antes de importá-lo.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import streamlit as st
import pandas as pd
from datetime import timedelta, date

from stock_pipeline.config import TICKER_MAP
from stock_pipeline.formatting import moeda_do_ticker
from stock_pipeline.ingestion import baixar_cotacoes
from stock_pipeline.indicators import processar_indicadores
from stock_pipeline.charts import criar_grafico_avancado
from stock_pipeline.leitura_gold import (
    GoldIndisponivel,
    carregar_gold,
    serie_do_ticker,
    ultima_data_por_bolsa,
)

URL_DOCS = "https://github.com/Daviramos7/stock_data_pipeline/tree/main/docs"

st.set_page_config(
    page_title="Dashboard Pro - Análise Técnica",
    page_icon="📊",
    layout="wide"
)


@st.cache_data(ttl=1800, show_spinner="Carregando o gold do pipeline...")
def carregar_gold_cache():
    return carregar_gold()


@st.cache_data(ttl=3600)
def carregar_dados_api(ticker, data_inicio, data_fim):
    return baixar_cotacoes(ticker, data_inicio, data_fim)


st.title("📈 Dashboard de Análise Quantitativa")
st.caption("Projeto educacional. Não é recomendação de investimento. Dados: Yahoo Finance (yfinance, não oficial).")

# Gold do pipeline diário; se não der, o app continua com o caminho antigo (yfinance na hora).
try:
    fato, dim_ativo, last_run = carregar_gold_cache()
    erro_gold = None
except GoldIndisponivel as e:
    fato, dim_ativo, last_run = None, None, {}
    erro_gold = str(e)

st.sidebar.header("Configurações")
ticker_selecionado = st.sidebar.selectbox("Ativo:", options=TICKER_MAP.keys(), format_func=lambda t: f"{t} - {TICKER_MAP[t]}")

if fato is not None:
    datas_ticker = fato.loc[fato["ticker"] == ticker_selecionado, "data"]
    usar_gold = not datas_ticker.empty
    if not usar_gold:
        erro_gold = f"o gold não tem linhas de {ticker_selecionado}"
else:
    usar_gold = False

data_fim = datas_ticker.max().date() if usar_gold else date.today()
data_inicio = st.sidebar.date_input("Início:", value=data_fim - timedelta(days=365), max_value=data_fim)
data_fim_input = st.sidebar.date_input("Fim:", value=data_fim, min_value=data_inicio, max_value=data_fim)

if usar_gold:
    df_analise = serie_do_ticker(fato, ticker_selecionado, data_inicio, data_fim_input)
else:
    df_raw, _ = carregar_dados_api(ticker_selecionado, data_inicio, data_fim_input)
    if df_raw.empty:
        df_analise = df_raw
    else:
        df_analise, _ = processar_indicadores(df_raw.sort_values(by='data'))

st.sidebar.markdown("---")
st.sidebar.subheader("🗄️ Fonte dos dados")
if usar_gold:
    st.sidebar.markdown("**Fonte:** `gold (pipeline diário)`")
    for bolsa, ultima in sorted(ultima_data_por_bolsa(fato).items()):
        st.sidebar.markdown(f"- Último pregão {bolsa}: **{ultima:%d/%m/%Y}**")
    if last_run:
        brt = pd.Timestamp(last_run["iniciado_em_brt"]) if last_run.get("iniciado_em_brt") else None
        horario = f"{brt:%d/%m/%Y %H:%M} BRT" if brt is not None else "?"
        status = last_run.get("status", "?")
        icone = "✅" if status == "ok" else "⚠️"
        st.sidebar.markdown(f"- Último run: {horario} · status {icone} `{status}`")
        if last_run.get("run_url"):
            st.sidebar.markdown(f"- [Ver o run no GitHub Actions]({last_run['run_url']})")
    else:
        st.sidebar.caption("last_run.json indisponível.")
    st.sidebar.markdown(f"- [Como o pipeline funciona (docs)]({URL_DOCS})")
else:
    st.warning(
        "Os dados do pipeline (gold) estão indisponíveis agora "
        f"({erro_gold}). Mostrando dados baixados ao vivo do Yahoo Finance: "
        "o começo do período pode ter indicadores vazios ou \"frios\"."
    )
    st.sidebar.markdown("**Fonte:** `yfinance ao vivo (fallback)`")
    st.sidebar.markdown(f"- [Como o pipeline funciona (docs)]({URL_DOCS})")

if not df_analise.empty:
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
        st.plotly_chart(fig, width="stretch")

    with tab2:
        st.dataframe(df_analise.sort_values('data', ascending=False), width="stretch")

else:
    st.error("Falha ao carregar dados. Verifique o ticker ou o período.")
