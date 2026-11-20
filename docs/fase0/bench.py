"""Fase 0 — medição. Reusa as funções do dashboard.py original (extraídas via AST, sem importar o Streamlit).
Uso: python -I bench.py /caminho/para/dashboard.py
"""
import ast, sys, time, statistics as st, datetime as dt, platform
import pandas as pd, numpy as np, yfinance as yf

src = open(sys.argv[1]).read()
tree = ast.parse(src)
fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("carregar_dados_api", "processar_indicadores")]
for f in fns:
    f.decorator_list = []  # tira o @st.cache_data
ns = {"pd": pd, "np": np, "yf": yf, "time": time, "timedelta": dt.timedelta}
exec(compile(ast.Module(body=fns, type_ignores=[]), "dashboard_fns", "exec"), ns)
carregar, processar = ns["carregar_dados_api"], ns["processar_indicadores"]

TICKERS = ["PETR4.SA", "VALE3.SA", "ITUB4.SA", "BBAS3.SA", "WEGE3.SA", "MGLU3.SA", "AAPL", "MSFT", "GOOGL", "NVDA"]
fim = dt.date(2026, 11, 18); ini = fim - dt.timedelta(days=365)   # janela padrão do app (365 dias)
print(f"# medição {dt.datetime.now().isoformat(timespec='seconds')} | py {platform.python_version()} | yfinance {yf.__version__} | pandas {pd.__version__}")
print(f"# janela {ini}..{fim}\n")

# 1) download + indicadores, como o app faz (1 ticker por vez), 3 rodadas
dl, calc, rows = [], [], []
for rodada in range(3):
    for t in TICKERS:
        df, td = carregar(t, ini, fim)
        df = df.sort_values("data")
        _, tc = processar(df)
        dl.append(td); calc.append(tc); rows.append(len(df))
        time.sleep(0.5)
def p(xs, q): return float(np.percentile(xs, q))
print("## download (por ticker, 30 chamadas)")
print(f"mediana {st.median(dl):.3f}s | p90 {p(dl,90):.3f}s | min {min(dl):.3f}s | max {max(dl):.3f}s")
print("## indicadores com time.time (como o app mede)")
print(f"mediana {st.median(calc)*1000:.2f}ms | linhas/ticker {min(rows)}–{max(rows)}")

# indicadores com perf_counter e repetição (medição mais honesta)
df, _ = carregar("PETR4.SA", ini, fim); df = df.sort_values("data")
reps = []
for _ in range(200):
    t0 = time.perf_counter(); processar(df); reps.append(time.perf_counter() - t0)
print(f"## indicadores perf_counter, 200 reps, {len(df)} linhas: mediana {st.median(reps)*1000:.2f}ms → {len(df)/st.median(reps):,.0f} linhas/s")

# 2) batch: 10 tickers numa chamada só
t0 = time.perf_counter(); b = yf.download(TICKERS, start=ini, end=fim + dt.timedelta(days=1), auto_adjust=True, progress=False, group_by="ticker"); tb = time.perf_counter() - t0
print(f"## batch 10 tickers numa chamada: {tb:.2f}s, shape {b.shape}")

# 3) profundidade do histórico
print("\n## histórico máximo (period='max')")
for t in ["PETR4.SA", "MGLU3.SA", "AAPL", "NVDA"]:
    h = yf.Ticker(t).history(period="max", auto_adjust=False)
    print(f"{t}: {h.index.min().date()} → {h.index.max().date()} ({len(h)} pregões) tz={h.index.tz}")

# 4) feriados: o que volta em dia sem pregão
print("\n## feriados")
checks = {"PETR4.SA": ["2025-11-20", "2026-02-16", "2026-02-17", "2026-02-18", "2026-04-03", "2026-04-21"],
          "AAPL": ["2025-11-27", "2025-11-28", "2026-07-03", "2026-04-03"]}
for t, dias in checks.items():
    h = yf.Ticker(t).history(start="2025-11-15", end="2026-07-10", auto_adjust=False)
    idx = set(h.index.date.astype(str)) if hasattr(h.index.date, "astype") else {str(d) for d in h.index.date}
    for d in dias:
        print(f"{t} {d}: {'TEM linha' if d in idx else 'sem linha'}" + (f" (vol={int(h.loc[h.index.date.astype(str)==d,'Volume'].iloc[0]) if d in idx else ''})" if d in idx else ""))
h = yf.Ticker("PETR4.SA").history(start="2026-02-17", end="2026-02-19", auto_adjust=False)
print("Quarta de Cinzas PETR4:\n", h[["Open","High","Low","Close","Volume"]])

# 5) ajuste de proventos/splits
print("\n## ajustes")
for t in ["PETR4.SA", "NVDA"]:
    tk = yf.Ticker(t)
    a = tk.history(start="2024-01-01", end="2026-11-19", auto_adjust=True)
    r = tk.history(start="2024-01-01", end="2026-11-19", auto_adjust=False)
    print(f"{t}: Close bruto 1º dia {r['Close'].iloc[0]:.2f} | Adj Close {r['Adj Close'].iloc[0]:.2f} | auto_adjust Close {a['Close'].iloc[0]:.2f}")
    print(f"  dividendos no período: {int((r['Dividends']>0).sum())} | splits: {r.loc[r['Stock Splits']>0,'Stock Splits'].to_dict()}")
r = yf.Ticker("NVDA").history(start="2024-06-05", end="2024-06-13", auto_adjust=False)
print("NVDA em volta do split 10:1 (06/2024), Close já vem dividido retroativamente?\n", r[["Close","Stock Splits"]])

# 6) rajada pra ver rate limit (60 chamadas seguidas, sem sleep)
print("\n## rajada 60 chamadas 1y sem pausa")
ok = err = 0; t0 = time.perf_counter(); erros = {}
for i in range(60):
    try:
        d = yf.download(TICKERS[i % 10], period="1y", progress=False, auto_adjust=True)
        if d.empty: err += 1; erros["vazio"] = erros.get("vazio", 0) + 1
        else: ok += 1
    except Exception as e:
        err += 1; erros[type(e).__name__] = erros.get(type(e).__name__, 0) + 1
print(f"ok {ok} | falha {err} {erros} | {time.perf_counter()-t0:.1f}s")
