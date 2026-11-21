"""Gráficos Plotly."""
import plotly.graph_objects as go
from plotly.subplots import make_subplots


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
