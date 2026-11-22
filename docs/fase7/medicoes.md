# Fase 7 — medições do app lendo do gold

Medido em **22/11/2026**, com rede (internet doméstica), contra o gold público da Release `data-latest`
gerado pelo run de 22/11/2026 15:16 BRT (status `ok`). Comando, da raiz:

```powershell
$env:PYTHONIOENCODING = "utf-8"
.\venv\Scripts\python.exe docs\fase7\medir.py
```

A saída abaixo é literal (só os avisos `No runtime found` do Streamlit foram omitidos).

- Data: 2026-11-22 15:24 BRT
- Máquina: Windows-11-10.0.26200-SP0, AMD64 Family 25 Model 33 Stepping 2, AuthenticAMD, Python 3.13.9
- Gold: `https://github.com/Daviramos7/stock_data_pipeline/releases/download/data-latest`
- streamlit 1.51.0, pandas 2.3.3

## Tempo de abrir (5 repetições, segundos)

| Medida | Mediana | Mín | Máx | Repetições |
| --- | ---: | ---: | ---: | --- |
| `carregar_gold()` sozinho (download + leitura) | 1.55 | 1.51 | 1.65 | 1.65, 1.51, 1.52, 1.58, 1.55 |
| App frio (cache vazio): AppTest `run()` completo | 1.62 | 1.54 | 2.06 | 2.06, 1.62, 1.62, 1.54, 1.64 |
| App quente (gold em cache): AppTest `run()` completo | 0.04 | 0.04 | 0.05 | 0.04, 0.04, 0.04, 0.04, 0.05 |
| App antigo frio (fallback forçado: yfinance ao vivo, PETR4 1 ano) | 0.74 | 0.60 | 1.14 | 1.14, 0.74, 0.60, 0.74, 0.76 |

Gold lido: 29654 linhas no fato; last_run 2026-11-22T15:16:59-03:00 status `ok`.

## KPIs do último pregão: app novo (gold) × app antigo (yfinance ao vivo)

| Ticker | Janela | Último pregão (novo / antigo) | Métrica | Novo (gold) | Antigo (yfinance) | Novo − Antigo |
| --- | --- | --- | --- | ---: | ---: | ---: |
| PETR4.SA | 2025-11-19 a 2026-11-19 | 2026-11-19 / 2026-11-19 | Preço (fechamento ajustado) | 42.669998 | 42.669998 | +0.00e+00 |
| PETR4.SA | 2025-11-19 a 2026-11-19 | 2026-11-19 / 2026-11-19 | SMA20 | 48.360500 | 48.360500 | +0.00e+00 |
| PETR4.SA | 2025-11-19 a 2026-11-19 | 2026-11-19 / 2026-11-19 | RSI(14) | 28.261930 | 28.261929 | +1.27e-07 |
| PETR4.SA | 2025-11-19 a 2026-11-19 | 2026-11-19 / 2026-11-19 | Volatilidade anual % | 41.458116 | 41.458116 | -6.39e-14 |
| AAPL | 2025-11-20 a 2026-11-20 | 2026-11-20 / 2026-11-20 | Preço (fechamento ajustado) | 342.559998 | 342.559998 | +0.00e+00 |
| AAPL | 2025-11-20 a 2026-11-20 | 2026-11-20 / 2026-11-20 | SMA20 | 347.306572 | 347.306572 | +0.00e+00 |
| AAPL | 2025-11-20 a 2026-11-20 | 2026-11-20 / 2026-11-20 | RSI(14) | 46.589004 | 46.589004 | +2.24e-08 |
| AAPL | 2025-11-20 a 2026-11-20 | 2026-11-20 / 2026-11-20 | Volatilidade anual % | 27.598771 | 27.598771 | -6.04e-14 |

## Começo da janela (onde os dois podem diferir)

| Ticker | n-ésimo pregão | Data | RSI novo | RSI antigo | SMA50 novo | SMA50 antigo |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| PETR4.SA | 1 | 2025-11-19 | 66.6066 | nan | 28.3191 | nan |
| PETR4.SA | 15 | 2025-12-10 | 51.2618 | 42.2689 | 28.4262 | nan |
| PETR4.SA | 50 | 2026-02-03 | 82.2329 | 82.5130 | 30.0024 | 30.0024 |
| PETR4.SA | 120 | 2026-05-19 | 48.3833 | 48.3823 | 44.3456 | 44.3456 |
| PETR4.SA | pregões: novo 248, antigo 248, em comum 248 | | | | | |
| AAPL | 1 | 2025-11-20 | 51.7628 | nan | 257.6386 | nan |
| AAPL | 15 | 2025-12-11 | 57.2467 | 60.2543 | 266.3680 | nan |
| AAPL | 50 | 2026-02-03 | 61.5503 | 61.7532 | 267.4333 | 267.4333 |
| AAPL | 120 | 2026-05-14 | 74.8259 | 74.8281 | 264.7383 | 264.7383 |
| AAPL | pregões: novo 252, antigo 252, em comum 252 | | | | | |

## Leitura

**Tempo.** Com cache vazio o app novo é *mais lento* para abrir que o antigo (mediana 1,62 s × 0,74 s): ele
baixa o fato inteiro (10 tickers desde 2015, 2.820.427 bytes medidos com `curl -sL -w "%{size_download}"`
no mesmo dia), enquanto o antigo baixa um ticker × 1 ano. Quase todo o tempo frio é o download
(`carregar_gold()` sozinho: 1,55 s). Em troca, com o gold em cache (`ttl=1800`) qualquer ticker ou período
abre em 0,04 s, enquanto o app antigo vai ao Yahoo a cada combinação nova de ticker e datas e depende do
Yahoo estar de pé. O cache é por processo: no Streamlit Cloud, o primeiro visitante depois de 30 min paga
o download, os seguintes não.

Limites da medida: AppTest roda o script em processo, sem navegador nem websocket; mede download +
leitura + render do script, não o tempo até a página pintar no navegador. A rede é a de casa, não a do
Streamlit Cloud.

**KPIs.** No último pregão, preço e SMA20 são idênticos (mesmo `adj_close`), a volatilidade difere em
~1e-13 (ponto flutuante) e o RSI em ~1e-7. É o mesmo efeito explicado em
[`docs/fase4/comparacao_app_gold.md`](../fase4/comparacao_app_gold.md): o RSI de Wilder é uma média
exponencial e o gold carrega o histórico inteiro, o app antigo só a janela de 1 ano. No começo da janela a
diferença é grande (RSI do 15º pregão: 51,3 × 42,3 no PETR4) e o app antigo dá NaN no SMA50 até o 50º
pregão; o gold já vem aquecido. Isso é a melhoria esperada (ADR-001, decisão 6), não regressão.

As datas da janela são as do app novo (fim = último pregão do gold do ticker); para o antigo foi usado o
mesmo intervalo, para comparar linha a linha.
