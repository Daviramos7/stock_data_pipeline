import time, yfinance as yf, datetime as dt
T=["PETR4.SA","VALE3.SA","ITUB4.SA","BBAS3.SA","WEGE3.SA","MGLU3.SA","AAPL","MSFT","GOOGL","NVDA"]
fim=dt.date(2026,11,19); ini=dt.date(2025,11,18)
for r in range(2):
    ts=[]
    for t in T:
        t0=time.perf_counter(); yf.download(t,start=ini,end=fim,auto_adjust=True,progress=False); ts.append(time.perf_counter()-t0)
    ts.sort(); print(f"rodada {r+1}: mediana {ts[5]:.3f}s min {ts[0]:.3f} max {ts[-1]:.3f}")
