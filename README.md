# 📈 Dashboard de Análise de Ações (Projeto DE/DS)

> ### 🚀 Teste o aplicativo ao vivo:
> **[https://stockdatapipeline-jnuaqfhrnt8jts3ymssrsp.streamlit.app/](https://stockdatapipeline-jnuaqfhrnt8jts3ymssrsp.streamlit.app/)**

![Prévia do Dashboard]
(img/preview.jpg)
---

### 🛠️ Tecnologias Utilizadas

![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)
![Plotly](https://img.shields.io/badge/Plotly-3F4F75?style=for-the-badge&logo=plotly&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white)
![YFinance](https://img.shields.io/badge/YFinance-000000?style=for-the-badge)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-336791?style=for-the-badge&logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)

---

## 📋 Sobre o Projeto

Este é um projeto *full-stack* de dados que demonstra um ciclo completo de **Engenharia de Dados (DE)** e **Ciência de Dados (DS)**.

O projeto é dividido em duas partes principais:

1.  **Pipeline de Dados (Local):** Um script ETL (`etl.py`) que extrai dados financeiros da API do Yahoo Finance, trata-os e os armazena de forma incremental em um banco de dados PostgreSQL rodando em um container Docker.
2.  **Dashboard Interativo (Nuvem):** Um aplicativo web (`dashboard.py`) construído com Streamlit que busca dados *ao vivo* da API, calcula indicadores e exibe análises visuais, hospedado na Streamlit Community Cloud.

## ✨ Funcionalidades do Dashboard (Live App)

O dashboard ao vivo permite ao usuário:

* **Busca de dados em tempo real** da API do Yahoo Finance (`yfinance`).
* **Filtros dinâmicos** por Ticker (com o nome da empresa, ex: "PETR4.SA - Petrobras").
* **Seleção de período** interativa com seletores de Data Início e Data Fim.
* **Visualização de gráficos de Candlestick** (com `Plotly`) para análise de abertura, máxima, mínima e fechamento.
* **Cálculo de indicadores técnicos**, como Médias Móveis Simples (MMS) de 7 e 21 dias.
* **Cards de Métricas (KPIs)** no topo, mostrando o último preço, variação percentual e valores máximos/mínimos do período.
* **Layout limpo** com Abas para "Gráfico" e "Dados Detalhados".

## 🏗️ Arquitetura do Projeto

### 1. Pipeline de Engenharia de Dados (Execução Local)

Esta parte do projeto (`etl.py`) simula um ambiente de produção local para coleta e armazenamento de dados.

* **Extração (E):** Conexão com a API do `yfinance` para buscar o histórico de preços.
* **Transformação (T):** Limpeza e padronização dos dados usando `pandas` (ex: tratamento de colunas, normalização de datas).
* **Carga (L):** Conexão com o `PostgreSQL` (rodando no `Docker`) usando `sqlalchemy`.
* **Inteligência do Pipeline:** O script utiliza uma lógica de **carga incremental** (lendo a última data do banco) e **UPSERT** (deletando o último dia para evitar duplicatas) para garantir que o banco esteja sempre atualizado sem redundância.

### 2. Dashboard de Ciência de Dados (Deploy na Nuvem)

Esta parte (`dashboard.py`) é o aplicativo público hospedado na Streamlit Community Cloud.

* **Arquitetura Serverless:** Para o deploy, o app **não** se conecta ao banco de dados local (PostgreSQL/Docker). Em vez disso, ele foi refatorado para ser *stateless*.
* **Busca de Dados (Live):** O dashboard chama a API do `yfinance` diretamente com base nos filtros selecionados pelo usuário.
* **Performance:** A função de busca de dados utiliza o cache do Streamlit (`@st.cache_data`) para garantir que chamadas de API repetidas (para o mesmo ticker/data) não sejam feitas desnecessariamente.

## 🚀 Como Executar

Este repositório contém os arquivos necessários para o deploy na nuvem.

1.  Clone o repositório.
2.  Crie um ambiente virtual (`python -m venv venv`).
3.  Ative o ambiente (`.\venv\Scripts\activate.bat`).
4.  Instale as dependências: `pip install -r requirements.txt`
5.  Execute o dashboard: `streamlit run dashboard.py`
