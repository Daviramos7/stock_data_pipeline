# Fase 4 — comparação app × gold

Medido em **22/11/2026**, sem rede, na mesma máquina de `medicoes.md`. Comando (da raiz, depois de `dbt build` e `scripts/exportar_gold.py`):

```powershell
$env:PYTHONIOENCODING = "utf-8"
.\venv\Scripts\python.exe scripts\comparar_app_gold.py --hoje 2026-11-22
```

## O que é comparado

- **App**: o dashboard baixa com `auto_adjust=True` (fechamento = ajustado) a janela padrão da sidebar, `[hoje − 365 dias, hoje]`, e roda `processar_indicadores` só nela. Sem rede, essa saída é simulada com o `adj_close` do **silver** na mesma janela. É o mesmo dado que o Yahoo devolveria em 22/11/2026, porque o silver foi baixado nesse dia.
- **Gold**: `fato_cotacao_diaria`, com a mesma função aplicada ao **histórico inteiro** (2015-01-02 em diante) do ticker.

## Último pregão

| Ticker | Último pregão | Métrica | App (1 ano) | Gold (histórico) | Gold - App | Pregões na janela |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| PETR4.SA | 2026-11-19 | fechamento ajustado | 42.669998 | 42.669998 | +0.00e+00 | 246 |
| PETR4.SA | 2026-11-19 | SMA20 | 48.360500 | 48.360500 | +0.00e+00 | 246 |
| PETR4.SA | 2026-11-19 | RSI(14) | 28.261929 | 28.261930 | +1.20e-07 | 246 |
| PETR4.SA | 2026-11-19 | Volatilidade anual % | 41.458116 | 41.458116 | +1.14e-13 | 246 |
| AAPL | 2026-11-20 | fechamento ajustado | 342.559998 | 342.559998 | +0.00e+00 | 250 |
| AAPL | 2026-11-20 | SMA20 | 347.306572 | 347.306572 | +0.00e+00 | 250 |
| AAPL | 2026-11-20 | RSI(14) | 46.589004 | 46.589004 | +1.11e-07 | 250 |
| AAPL | 2026-11-20 | Volatilidade anual % | 27.598771 | 27.598771 | -1.53e-13 | 250 |

No último pregão os dois são iguais na prática, e a teoria explica por quê:

- **Fechamento ajustado**: mesmo dado (adj_close do silver).
- **SMA20 e volatilidade (21 pregões)**: são janelas fixas e só dependem dos últimos 20 ou 21 pregões. O histórico extra do gold não entra na conta. A diferença de 1e-13 é arredondamento de ponto flutuante.
- **RSI de Wilder (14)**: é uma média exponencial com alpha = 1/14, então depende de toda a série desde o início. O peso da condição inicial cai com (13/14)^n. Depois de ~245 pregões, (13/14)^230 ≈ 4e-8, e por isso sobra uma diferença de ~1e-7 no RSI.

## Onde a diferença aparece: começo da janela do app

| Ticker | n-ésimo pregão da janela | Data | RSI app | RSI gold | SMA50 app | SMA50 gold |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| PETR4.SA | 1 | 2025-11-24 | NaN | 62.2183 | NaN | 28.3654 |
| PETR4.SA | 14 | 2025-12-11 | 35.8918 | 45.0421 | NaN | 28.4268 |
| PETR4.SA | 15 | 2025-12-12 | 39.9745 | 47.3773 | NaN | 28.4361 |
| PETR4.SA | 20 | 2025-12-19 | 37.5137 | 43.0472 | NaN | 28.4729 |
| PETR4.SA | 50 | 2026-02-05 | 74.5460 | 74.3360 | 30.2118 | 30.2118 |
| PETR4.SA | 60 | 2026-02-23 | 72.2269 | 72.1492 | 31.4048 | 31.4048 |
| PETR4.SA | 120 | 2026-05-21 | 43.9387 | 43.9396 | 44.4489 | 44.4489 |
| PETR4.SA | 240 | 2026-11-11 | 25.8620 | 25.8620 | 51.0022 | 51.0022 |
| AAPL | 1 | 2025-11-24 | NaN | 65.1702 | NaN | 259.1751 |
| AAPL | 14 | 2025-12-12 | 50.5503 | 57.6536 | NaN | 266.7945 |
| AAPL | 15 | 2025-12-15 | 37.9354 | 49.2358 | NaN | 267.1202 |
| AAPL | 20 | 2025-12-22 | 34.7216 | 44.0573 | NaN | 268.9930 |
| AAPL | 50 | 2026-02-05 | 67.1600 | 67.1143 | 267.7255 | 267.7255 |
| AAPL | 60 | 2026-02-20 | 49.5747 | 49.7028 | 265.2334 | 265.2334 |
| AAPL | 120 | 2026-05-18 | 71.6756 | 71.6749 | 266.3516 | 266.3516 |
| AAPL | 240 | 2026-11-06 | 51.4643 | 51.4643 | 335.7587 | 335.7587 |

- **RSI**: nas primeiras semanas da janela do app, o RSI do app parte "do zero" e chega a errar 7 a 11 pontos em relação ao gold (ex.: AAPL no 15º pregão, 37,9 × 49,2). Em ~50 pregões a diferença cai para décimos e em ~120 para milésimos. O gold está certo desde o primeiro dia da janela, porque já vem aquecido pelo histórico.
- **SMA50 (e SMA20, Bollinger, volatilidade)**: o app dá NaN nos primeiros 49 (19, 19, 21) pregões da janela, e o gold já tem valor. A partir daí os dois são idênticos.
- Conclusão para a Fase 7: ler do gold não muda o que o app mostra no fim da janela. Muda o começo, que deixa de ter buraco e RSI "frio". Isso é melhoria esperada (ADR-001, decisão 6), não regressão.

Nada aqui foi estimado: as tabelas são a saída literal do comando acima.
