"""Fase 6: coletor de alertas. Lê last_run.json e o run_results.json do dbt e devolve
uma lista de alertas, um por PROBLEMA (não por dia), cada um com chave estável.

    python -m stock_pipeline.pipeline.cli --data-dir data alertas --saida data/alertas.json

Quem transforma isso em Issue é scripts/publicar_alertas.py (ciclo de vida em
docs/fase6/alertas.md). Aqui não tem rede: os exemplos de linhas vêm de rodar o
`compiled_code` de cada teste no warehouse DuckDB (só leitura), e essa consulta é
injetável (`consultar`), então os testes passam um fake.

Escopo: `escopo` diz o que este run de fato verificou. Se o dbt nem rodou (a ingestão
caiu antes), "dbt:" fica de fora e as Issues de teste dbt não são fechadas por engano.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

MAX_EXEMPLOS = 20
CHAVE_FALHA = "falha-pipeline"
PREFIXO_DBT = "dbt:"

STATUS_ERRO = {"fail", "error", "runtime error"}
STATUS_AVISO = {"warn"}

# O que fazer, por teste. O texto genérico cobre o resto.
O_QUE_FAZER = {
    "salto_sem_evento": (
        "Para cada linha: procurar a causa (fato relevante, grupamento/desdobramento, "
        "provento fora da data, erro do Yahoo). Se o salto é real e explicado, registrar em "
        "`dbt/seeds/eventos_conhecidos.csv` com `fonte_url` e abrir PR: a Issue fecha sozinha "
        "no run seguinte ao merge. Se é erro da fonte, corrigir na origem (silver) e não no seed."
    ),
    "volume_zero_em_pregao": (
        "Volume 0 com OHLC igual ao fechamento anterior é o Yahoo repetindo a linha de ontem. "
        "Conferir se houve negociação no dia (site da B3 / RI). Se a linha é falsa, avaliar "
        "rebaixar o ticker; se o pregão foi suspenso para o papel, é dado real."
    ),
    "fato_desatualizado": (
        "O gold não tem o último pregão da bolsa. Ver no log do run se a ingestão trouxe "
        "linhas (Yahoo atrasado ou fora do ar) e rodar o workflow de novo mais tarde. Se "
        "persistir por mais de 1 pregão, conferir o calendário (`dim_calendario`)."
    ),
    "pregao_faltando": (
        "Há pregão no calendário sem linha no fato. Rodar um backfill do intervalo; se a fonte "
        "realmente não tem o dia, registrar em `excecoes_fonte.csv` como "
        "`pregao_ausente_na_fonte` com a evidência de que houve pregão."
    ),
    "linha_sem_pregao": (
        "Linha em dia sem pregão. Conferir o feriado no calendário; se é linha-fantasma do "
        "Yahoo, registrar em `excecoes_fonte.csv` como `linha_fantasma`."
    ),
}
O_QUE_FAZER_PADRAO = ("Abrir o log do run, rodar `dbt build` localmente com o mesmo silver e "
                      "corrigir o dado ou o teste. A Issue fecha sozinha quando o teste passar.")
O_QUE_FAZER_FALHA = (
    "Abrir o log do run e ver a etapa que caiu. Nada foi publicado na Release (o gold de ontem "
    "continua valendo). Erro de rede/Yahoo costuma passar sozinho no próximo run; se repetir, "
    "rodar `workflow_dispatch` e investigar. A Issue fecha sozinha no primeiro run que passar."
)


@dataclass
class Alerta:
    chave: str
    severidade: str  # "erro" | "aviso"
    titulo: str
    corpo: str
    # Hash do conteúdo que importa (sem link nem data): o publicador só comenta de novo
    # quando ela muda (ou depois de 7 dias).
    assinatura: str


def _assinatura(*partes) -> str:
    bruto = json.dumps(partes, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:16]


def _nome_no(unique_id: str) -> str:
    """`test.<pacote>.<nome>[.<hash>]` -> nome (o hash muda; o nome não)."""
    partes = unique_id.split(".")
    return partes[2] if len(partes) >= 3 else unique_id


def _fmt(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float):
        return f"{valor:.4f}"
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    return str(valor).replace("|", "\\|")


def _tabela(linhas: list[dict], colunas: list[str] | None = None) -> str:
    if not linhas:
        return ""
    colunas = colunas or list(linhas[0])
    cab = "| " + " | ".join(colunas) + " |\n| " + " | ".join("---" for _ in colunas) + " |\n"
    return cab + "".join("| " + " | ".join(_fmt(l.get(c)) for c in colunas) + " |\n" for l in linhas)


def _exemplos_salto(linhas: list[dict]) -> str:
    fmt = []
    for l in linhas:
        div, split = l.get("dividends") or 0, l.get("splits") or 0
        fmt.append({
            "ticker": l.get("ticker"),
            "data": l.get("data"),
            "adj anterior → adj": f"{_fmt(l.get('adj_anterior'))} → {_fmt(l.get('adj_close'))}",
            "variação": f"{l['variacao'] * 100:+.1f}%" if l.get("variacao") is not None else "",
            "dividendo/split no dia": "sim" if (div or split) else "não",
            "provento/split a ≤3 pregões": str(l.get("eventos_vizinhos") or 0),
        })
    return _tabela(fmt)


def _rodape(run_url: str | None, o_que_fazer: str) -> str:
    link = f"[run]({run_url})" if run_url else "(sem link: execução local)"
    return f"\n**Run:** {link}\n\n**O que fazer:** {o_que_fazer}\n"


def alerta_falha(last_run: dict | None, run_url: str | None) -> Alerta | None:
    if last_run is None:
        etapa, erro = "antes_do_orquestrador", "data/last_run.json não existe (o orquestrador nem rodou)"
        tickers = {}
    elif last_run.get("status") == "ok":
        return None
    else:
        etapa = last_run.get("etapa_falhou") or "desconhecida"
        erro = last_run.get("erro") or "sem mensagem"
        tickers = last_run.get("tickers_falha") or {}
    corpo = (f"O pipeline diário falhou na etapa **`{etapa}`**.\n\n"
             f"```\n{erro}\n```\n")
    if tickers:
        itens = sorted(tickers.items())
        corpo += f"\n**Tickers com falha ({len(itens)}):**\n\n" + _tabela(
            [{"ticker": t, "motivo": m} for t, m in itens[:MAX_EXEMPLOS]])
    corpo += _rodape(run_url, O_QUE_FAZER_FALHA)
    return Alerta(chave=CHAVE_FALHA, severidade="erro",
                  titulo=f"Pipeline falhou na etapa {etapa}", corpo=corpo,
                  assinatura=_assinatura(CHAVE_FALHA, etapa, erro, sorted(tickers)))


def alertas_dbt(run_results: dict, run_url: str | None,
                consultar: Callable[[str], list[dict]] | None) -> list[Alerta]:
    alertas = []
    for r in run_results.get("results", []):
        status = r.get("status")
        if status in STATUS_ERRO:
            severidade = "erro"
        elif status in STATUS_AVISO:
            severidade = "aviso"
        else:
            continue
        nome = _nome_no(r["unique_id"])
        tipo_no = r["unique_id"].split(".")[0]
        chave = PREFIXO_DBT + nome
        falhas = r.get("failures")

        exemplos, nota = [], ""
        if tipo_no == "test" and r.get("compiled_code") and consultar:
            try:
                exemplos = consultar(r["compiled_code"])
            except Exception as erro:  # sem exemplo é ruim, mas não pode derrubar o alerta
                log.warning("não consegui listar exemplos de %s: %s", nome, erro)
                nota = f"\n_(não consegui listar exemplos: `{type(erro).__name__}`)_\n"
        n = falhas if falhas is not None else len(exemplos)
        mostrados = exemplos[:MAX_EXEMPLOS]

        if tipo_no == "test":
            corpo = (f"O teste dbt **`{nome}`** terminou com **{status.upper()}** "
                     f"({severidade}): **{n} linha(s)**.\n\n")
        else:
            corpo = f"O nó dbt **`{nome}`** ({tipo_no}) terminou com **{status.upper()}**.\n\n"
        if r.get("message"):
            corpo += f"Mensagem do dbt: `{r['message']}`\n\n"
        if mostrados:
            corpo += (f"**Exemplos ({len(mostrados)} de {n}):**\n\n"
                      + (_exemplos_salto(mostrados) if nome == "salto_sem_evento" else _tabela(mostrados)))
            if n and n > len(mostrados):
                corpo += f"\n… e mais {n - len(mostrados)}.\n"
        corpo += nota
        corpo += _rodape(run_url, O_QUE_FAZER.get(nome, O_QUE_FAZER_PADRAO))

        titulo = (f"Teste dbt {nome}: {n} linha(s) ({severidade})" if tipo_no == "test"
                  else f"dbt {tipo_no} {nome} com {status}")
        alertas.append(Alerta(chave=chave, severidade=severidade, titulo=titulo, corpo=corpo,
                              assinatura=_assinatura(chave, severidade, n,
                                                     [{k: _fmt(v) for k, v in e.items()} for e in exemplos])))
    return alertas


def _run_results_valido(run_results: dict | None, last_run: dict | None) -> bool:
    """Descarta um run_results.json de uma rodada anterior à deste last_run."""
    if not run_results:
        return False
    if not last_run or last_run.get("etapa_falhou") == "ingestao":
        return False  # o dbt não rodou neste run
    gerado = (run_results.get("metadata") or {}).get("generated_at")
    iniciado = last_run.get("iniciado_em_utc")
    if gerado and iniciado:
        try:
            g = datetime.fromisoformat(gerado.replace("Z", "+00:00"))
            i = datetime.fromisoformat(iniciado)
            return g >= i
        except ValueError:
            return True
    return True


def coletar(last_run: dict | None, run_results: dict | None, *,
            consultar: Callable[[str], list[dict]] | None = None,
            run_url: str | None = None) -> dict:
    """Devolve {"run_url", "escopo", "alertas": [...]} pronto pra virar alertas.json."""
    run_url = run_url or (last_run or {}).get("run_url")
    alertas: list[Alerta] = []
    escopo = [CHAVE_FALHA]
    falha = alerta_falha(last_run, run_url)
    if falha:
        alertas.append(falha)
    if _run_results_valido(run_results, last_run):
        escopo.append(PREFIXO_DBT)
        alertas.extend(alertas_dbt(run_results, run_url, consultar))
    ordem = {"erro": 0, "aviso": 1}
    alertas.sort(key=lambda a: (ordem[a.severidade], a.chave))
    return {
        "run_url": run_url,
        "data_run": (last_run or {}).get("iniciado_em_brt", "")[:10] or date.today().isoformat(),
        "escopo": escopo,
        "alertas": [asdict(a) for a in alertas],
    }


def consultar_duckdb(warehouse: Path) -> Callable[[str], list[dict]] | None:
    """Consulta só-leitura no warehouse; None se ele não existe (não há exemplos)."""
    if not Path(warehouse).exists():
        return None

    def consultar(sql: str) -> list[dict]:
        import duckdb

        with duckdb.connect(str(warehouse), read_only=True) as con:
            # Quebras de linha: o SQL do teste pode terminar num comentário "-- ...".
            # order by all: os mesmos 20 exemplos na mesma ordem todo dia; senão a assinatura
            # muda à toa e o publicador comenta todo dia (o anti-spam depende disso).
            cur = con.execute(f"select * from (\n{sql}\n) order by all limit {MAX_EXEMPLOS}")
            colunas = [d[0] for d in cur.description]
            return [dict(zip(colunas, linha)) for linha in cur.fetchall()]

    return consultar


def _ler_json(caminho: Path | None) -> dict | None:
    if caminho is None or not Path(caminho).exists():
        return None
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def _gravar_json_atomico(caminho: Path, dados: dict) -> None:
    # Cópia do de orquestrar.py: importar aquele módulo puxa o duckdb (gold.py), e o
    # coletor tem que rodar (e ser testado) sem ele.
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(tmp, caminho)


def gerar(*, last_run: Path, run_results: Path | None, warehouse: Path, saida: Path) -> dict:
    resultado = coletar(_ler_json(last_run), _ler_json(run_results),
                        consultar=consultar_duckdb(warehouse))
    _gravar_json_atomico(Path(saida), resultado)
    return resultado
