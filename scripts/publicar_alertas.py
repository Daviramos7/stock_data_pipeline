"""Fase 6: transforma data/alertas.json em Issues do GitHub (uma por PROBLEMA).

    python scripts/publicar_alertas.py --alertas data/alertas.json [--dry-run]

Ciclo de vida (docs/fase6/alertas.md), só em Issues ABERTAS com o rótulo `alerta-pipeline`
e o marcador `<!-- chave: X -->` no corpo:
- chave nova                 -> cria a Issue `[pipeline] <título>` (rótulos alerta-pipeline + alerta:<sev>);
- chave já aberta            -> comenta "ainda ocorrendo" SÓ se a assinatura (conteúdo) mudou
                                ou se o último comentário do bot tem 7 dias ou mais (anti-spam);
- aberta e ausente neste run -> comenta "resolvido" e fecha, mas só se a chave está no `escopo`
                                que o run verificou (se o dbt não rodou, Issue dbt:* fica como está).

Nunca derruba o job: erro na API vira `::warning::` e o script sai 0. Quem deixa o job
vermelho é o orquestrador. Usa o `gh` (GH_TOKEN do workflow); nenhum outro segredo.
`--dry-run` lê as Issues abertas (se o gh tiver acesso) e só IMPRIME o que faria.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROTULO = "alerta-pipeline"
ANTI_SPAM = timedelta(days=7)
RE_CHAVE = re.compile(r"<!-- chave: (\S+) -->")
RE_ASSINATURA = re.compile(r"<!-- assinatura: (\w+) -->")


def aviso(msg: str) -> None:
    print(f"::warning::{msg}", flush=True)


def _instante(texto: str) -> datetime:
    return datetime.fromisoformat(texto.replace("Z", "+00:00"))


# --- cliente do GitHub ----------------------------------------------------------

class ClienteGh:
    """Cliente real: `gh` via subprocess (o token vem de GH_TOKEN no ambiente)."""

    def __init__(self, executar=subprocess.run):
        self._executar = executar

    def _gh(self, *args: str, entrada: str | None = None) -> str:
        proc = self._executar(["gh", *args], input=entrada, text=True, encoding="utf-8",
                              capture_output=True)
        if proc.returncode != 0:
            raise RuntimeError(f"gh {args[0]} {args[1] if len(args) > 1 else ''}: "
                               f"{(proc.stderr or '').strip()[:300]}")
        return proc.stdout

    def listar_abertas(self) -> list[dict]:
        saida = self._gh("issue", "list", "--label", ROTULO, "--state", "open", "--limit", "200",
                         "--json", "number,title,body,createdAt,comments")
        return json.loads(saida or "[]")

    def criar(self, titulo: str, corpo: str, rotulos: list[str]) -> str:
        args = ["issue", "create", "--title", titulo, "--body-file", "-"]
        for r in rotulos:
            args += ["--label", r]
        return self._gh(*args, entrada=corpo).strip()

    def comentar(self, numero: int, corpo: str) -> None:
        self._gh("issue", "comment", str(numero), "--body-file", "-", entrada=corpo)

    def fechar(self, numero: int) -> None:
        self._gh("issue", "close", str(numero), "--reason", "completed")


# --- plano (puro) ---------------------------------------------------------------

@dataclass
class Acao:
    tipo: str  # "criar" | "comentar" | "fechar"
    chave: str
    titulo: str = ""
    corpo: str = ""
    rotulos: tuple[str, ...] = ()
    numero: int | None = None
    motivo: str = ""


def _estado_issue(issue: dict) -> tuple[str | None, datetime]:
    """(última assinatura, instante da última atualização do bot) de uma Issue."""
    assinatura = None
    m = RE_ASSINATURA.search(issue.get("body") or "")
    if m:
        assinatura = m.group(1)
    ultimo = _instante(issue["createdAt"])
    for c in sorted(issue.get("comments") or [], key=lambda c: c["createdAt"]):
        m = RE_ASSINATURA.search(c.get("body") or "")
        if m:  # só comentário do bot (tem o marcador) conta pro anti-spam
            assinatura, ultimo = m.group(1), _instante(c["createdAt"])
    return assinatura, ultimo


def _no_escopo(chave: str, escopo: list[str]) -> bool:
    return any(chave == e or (e.endswith(":") and chave.startswith(e)) for e in escopo)


def _link(run_url: str | None) -> str:
    return f"[run]({run_url})" if run_url else "execução local (sem link)"


def planejar(dados: dict, abertas: list[dict], agora: datetime) -> list[Acao]:
    run_url, data_run = dados.get("run_url"), dados.get("data_run") or agora.date().isoformat()
    escopo = dados.get("escopo") or []
    por_chave: dict[str, dict] = {}
    for issue in sorted(abertas, key=lambda i: i["number"]):
        m = RE_CHAVE.search(issue.get("body") or "")
        if not m:
            continue  # Issue com o rótulo mas sem marcador: humana, não mexe
        if m.group(1) in por_chave:
            aviso(f"Issues duplicadas para a chave {m.group(1)}: usando #{por_chave[m.group(1)]['number']}")
            continue
        por_chave[m.group(1)] = issue

    acoes: list[Acao] = []
    vistas = set()
    for a in dados.get("alertas", []):
        chave, assin = a["chave"], a["assinatura"]
        vistas.add(chave)
        marcas = f"<!-- chave: {chave} -->\n<!-- assinatura: {assin} -->\n"
        issue = por_chave.get(chave)
        if issue is None:
            acoes.append(Acao("criar", chave, titulo=f"[pipeline] {a['titulo']}",
                              corpo=marcas + a["corpo"],
                              rotulos=(ROTULO, f"alerta:{a['severidade']}"), motivo="chave nova"))
            continue
        assin_antiga, ultimo = _estado_issue(issue)
        mudou = assin_antiga != assin
        velho = agora - ultimo >= ANTI_SPAM
        if not (mudou or velho):
            continue  # anti-spam: mesmo conteúdo e comentado há menos de 7 dias
        corpo = (f"<!-- assinatura: {assin} -->\nAinda ocorrendo em {data_run}, {_link(run_url)}.\n")
        if mudou:
            corpo += f"\n**O conteúdo mudou desde o último aviso:**\n\n{a['corpo']}"
        acoes.append(Acao("comentar", chave, corpo=corpo, numero=issue["number"],
                          motivo="conteúdo mudou" if mudou else "7 dias sem aviso"))

    for chave, issue in por_chave.items():
        if chave in vistas or not _no_escopo(chave, escopo):
            continue
        acoes.append(Acao("comentar", chave, numero=issue["number"], motivo="resolvido",
                          corpo=f"Resolvido no run de {data_run}, {_link(run_url)}. Fechando."))
        acoes.append(Acao("fechar", chave, numero=issue["number"], motivo="resolvido"))
    return acoes


# --- execução -------------------------------------------------------------------

def descrever(acao: Acao) -> str:
    if acao.tipo == "criar":
        return f"CRIAR Issue {acao.titulo!r} rótulos={list(acao.rotulos)} ({acao.motivo})"
    return f"{acao.tipo.upper()} #{acao.numero} chave={acao.chave} ({acao.motivo})"


def executar(acoes: list[Acao], cliente) -> int:
    """Executa uma a uma; erro numa ação vira aviso e não impede as outras. Devolve nº de erros."""
    erros = 0
    fechar_bloqueado = set()
    for acao in acoes:
        if acao.tipo == "fechar" and acao.numero in fechar_bloqueado:
            continue  # o comentário de "resolvido" falhou: não fecha calado
        try:
            if acao.tipo == "criar":
                cliente.criar(acao.titulo, acao.corpo, list(acao.rotulos))
            elif acao.tipo == "comentar":
                cliente.comentar(acao.numero, acao.corpo)
            elif acao.tipo == "fechar":
                cliente.fechar(acao.numero)
            print(descrever(acao), flush=True)
        except Exception as erro:
            erros += 1
            if acao.tipo == "comentar" and acao.motivo == "resolvido":
                fechar_bloqueado.add(acao.numero)
            aviso(f"falhou: {descrever(acao)}: {erro}")
    return erros


def publicar(dados: dict, cliente, *, agora: datetime | None = None,
             dry_run: bool = False) -> list[Acao]:
    agora = agora or datetime.now(timezone.utc)
    try:
        abertas = cliente.listar_abertas()
    except Exception as erro:
        if not dry_run:
            # Sem a lista não dá pra deduplicar: melhor não fazer nada do que abrir duplicata.
            aviso(f"não consegui listar as Issues abertas ({erro}); nada foi publicado")
            return []
        aviso(f"dry-run sem acesso ao GitHub ({erro}); supondo nenhuma Issue aberta")
        abertas = []
    acoes = planejar(dados, abertas, agora)
    if dry_run:
        print(f"[dry-run] {len(acoes)} ação(ões); {len(abertas)} Issue(s) aberta(s) com {ROTULO}")
        for acao in acoes:
            print(f"[dry-run] {descrever(acao)}")
            if acao.tipo == "criar":
                print("\n".join("    " + l for l in acao.corpo.splitlines()))
        return acoes
    executar(acoes, cliente)
    return acoes


def main(argv=None, cliente=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--alertas", type=Path, default=Path("data/alertas.json"))
    p.add_argument("--dry-run", action="store_true", help="só imprime o que faria")
    a = p.parse_args(argv)
    try:
        dados = json.loads(a.alertas.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        aviso(f"não consegui ler {a.alertas}: {erro}")
        return 0
    try:
        publicar(dados, cliente or ClienteGh(), dry_run=a.dry_run)
    except Exception as erro:  # rede de segurança: alerta nunca derruba o job
        aviso(f"publicar_alertas quebrou: {type(erro).__name__}: {erro}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
