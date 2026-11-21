"""Formatação de valores para exibição."""


def moeda_do_ticker(ticker):
    return "R$" if ticker.upper().endswith(".SA") else "US$"
