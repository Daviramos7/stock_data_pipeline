# 📈 Dashboard de Análise Quantitativa de Ações

> Dashboard interativo de análise técnica que baixa cotações sob demanda do Yahoo Finance, com cache de 1 h. Em evolução para um pipeline de dados de verdade (v2).

> ⚠️ **Projeto educacional. Não é recomendação de investimento.** Dados do Yahoo Finance via `yfinance` (não oficial).

### 🔴 Live Demo
**[https://stockdatapipeline-jnuaqfhrnt8jts3ymssrsp.streamlit.app/](https://stockdatapipeline-jnuaqfhrnt8jts3ymssrsp.streamlit.app/)**

![Prévia do Dashboard](./img/preview.jpg)

---

## ⚡ Performance

Os números de performance publicados antes foram retirados por não serem reproduzíveis. Eles estão sendo re-medidos com método documentado: veja [ADR-001](docs/adr/ADR-001-stack.md) e os scripts/saídas em [docs/fase0/](docs/fase0/).

---

## 🛠️ Stack

![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)
![Plotly](https://img.shields.io/badge/Plotly-3F4F75?style=for-the-badge&logo=plotly&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white)
![NumPy](https://img.shields.io/badge/NumPy-013243?style=for-the-badge&logo=numpy&logoColor=white)

---

## 📋 Sobre o Projeto

Dashboard de análise técnica de ações construído com Streamlit e hospedado na Streamlit Community Cloud. Baixa cotações sob demanda do Yahoo Finance (`yfinance`, não oficial) com cache de 1 h, calcula indicadores técnicos com NumPy/Pandas e exibe visualizações interativas com Plotly.

---

## ✨ Funcionalidades

- **Filtros dinâmicos** por ticker (PETR4, VALE3, AAPL, NVDA e outros) e período personalizado
- **Gráfico de Candlestick** interativo com Plotly (abertura, máxima, mínima, fechamento)
- **Indicadores técnicos:**
  - Médias Móveis Simples (SMA 20 e SMA 50)
  - Bandas de Bollinger (±2 desvios padrão, janela 20)
  - RSI — Índice de Força Relativa (janela 14)
  - Volatilidade Anual (janela 21, anualizada por √252)
  - Retorno Diário percentual
- **KPIs em destaque:** preço atual, variação %, RSI, volatilidade e tendência vs SMA 20
- **Cache inteligente** com `@st.cache_data` — chamadas repetidas não rebatem a API
- **Aba de dados brutos** com tabela completa ordenável

---

## 🏗️ Arquitetura

```
yfinance (sob demanda)
       │
       ▼
  @st.cache_data (TTL 3600s)
       │
       ▼
  Transformação com Pandas
  (normalização, renomeação, datas)
       │
       ▼
  Cálculo de Indicadores (NumPy/Pandas)
  SMA · Bollinger · RSI · Volatilidade
       │
       ▼
  Visualização Plotly → Streamlit Cloud
```

---

## 🗺️ Roadmap v2

- Camadas bronze/silver/gold com carga incremental
- Transformações com dbt-duckdb
- Ingestão diária via GitHub Actions
- Testes + CI
- Alerta de qualidade de dados

Detalhes e justificativas no [ADR-001](docs/adr/ADR-001-stack.md).

---

## 🚀 Executar Localmente

```bash
# Clone o repositório
git clone https://github.com/Daviramos7/stock_data_pipeline
cd stock_data_pipeline

# Crie e ative o ambiente virtual
python -m venv venv
.\venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Instale as dependências
pip install -r requirements.txt

# Execute o dashboard
streamlit run dashboard.py
```

---

## 📄 Licença

Copyright © 2026 por Davi Ramos Ferreira. Todos os Direitos Reservados.

---

**Desenvolvido com 💙 por [Davi Ramos Ferreira](https://github.com/Daviramos7)**
