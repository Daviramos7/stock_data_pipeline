"""Fase 6: publicador de Issues. Sem rede: um GitHub fake em memória."""
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("publicar_alertas", RAIZ / "scripts" / "publicar_alertas.py")
pa = importlib.util.module_from_spec(_spec)
sys.modules["publicar_alertas"] = pa  # @dataclass precisa achar o módulo
_spec.loader.exec_module(pa)

T0 = datetime(2026, 11, 23, 9, 30, tzinfo=timezone.utc)


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


class FakeGitHub:
    def __init__(self, falhar=()):
        self.issues = {}  # numero -> dict no formato do `gh issue list --json`
        self.agora = T0
        self.falhar = set(falhar)
        self.chamadas = []

    def _talvez_falhar(self, op):
        self.chamadas.append(op)
        if op in self.falhar:
            raise RuntimeError(f"HTTP 502 em {op}")

    def listar_abertas(self):
        self._talvez_falhar("listar")
        return [dict(i, comments=list(i["comments"])) for i in self.issues.values() if i["state"] == "open"]

    def criar(self, titulo, corpo, rotulos):
        self._talvez_falhar("criar")
        n = len(self.issues) + 1
        self.issues[n] = {"number": n, "title": titulo, "body": corpo, "labels": rotulos,
                          "createdAt": iso(self.agora), "comments": [], "state": "open"}
        return f"https://github.com/x/y/issues/{n}"

    def comentar(self, numero, corpo):
        self._talvez_falhar("comentar")
        self.issues[numero]["comments"].append({"body": corpo, "createdAt": iso(self.agora)})

    def fechar(self, numero):
        self._talvez_falhar("fechar")
        self.issues[numero]["state"] = "closed"

    def rodar(self, dados, quando=None):
        self.agora = quando or self.agora
        return pa.publicar(dados, self, agora=self.agora)


def alerta(chave="dbt:salto_sem_evento", sev="aviso", assinatura="aaa", titulo="Teste dbt salto"):
    return {"chave": chave, "severidade": sev, "titulo": titulo,
            "corpo": f"corpo de {chave} ({assinatura})", "assinatura": assinatura}


def dados(*alertas, escopo=("falha-pipeline", "dbt:"), url="https://x/actions/runs/1", data="2026-11-23"):
    return {"run_url": url, "data_run": data, "escopo": list(escopo), "alertas": list(alertas)}


def test_cria_issue_com_marcador_titulo_e_rotulos():
    gh = FakeGitHub()
    gh.rodar(dados(alerta(), alerta("falha-pipeline", "erro", "f1", "Pipeline falhou")))
    assert len(gh.issues) == 2
    issue = next(i for i in gh.issues.values() if "falha-pipeline" in i["body"])
    assert issue["title"] == "[pipeline] Pipeline falhou"
    assert issue["labels"] == ["alerta-pipeline", "alerta:erro"]
    assert issue["body"].startswith("<!-- chave: falha-pipeline -->\n<!-- assinatura: f1 -->")


def test_repeticao_igual_nao_comenta_antes_de_7_dias():
    gh = FakeGitHub()
    gh.rodar(dados(alerta()))
    for dia in range(1, 7):
        acoes = gh.rodar(dados(alerta()), T0 + timedelta(days=dia))
        assert acoes == []
    assert gh.issues[1]["comments"] == [] and len(gh.issues) == 1


def test_repeticao_igual_comenta_depois_de_7_dias_e_reinicia_a_contagem():
    gh = FakeGitHub()
    gh.rodar(dados(alerta()))
    gh.rodar(dados(alerta(), url="https://x/runs/8", data="2026-11-30"), T0 + timedelta(days=7))
    comentarios = gh.issues[1]["comments"]
    assert len(comentarios) == 1
    assert "Ainda ocorrendo em 2026-11-30" in comentarios[0]["body"]
    assert "https://x/runs/8" in comentarios[0]["body"]
    assert "conteúdo mudou" not in comentarios[0]["body"]
    gh.rodar(dados(alerta()), T0 + timedelta(days=10))  # 3 dias depois do comentário
    assert len(gh.issues[1]["comments"]) == 1


def test_conteudo_mudou_comenta_no_dia_seguinte_com_o_corpo_novo():
    gh = FakeGitHub()
    gh.rodar(dados(alerta(assinatura="aaa")))
    gh.rodar(dados(alerta(assinatura="bbb")), T0 + timedelta(days=1))
    c = gh.issues[1]["comments"]
    assert len(c) == 1 and "<!-- assinatura: bbb -->" in c[0]["body"]
    assert "corpo de dbt:salto_sem_evento (bbb)" in c[0]["body"]
    # e a assinatura nova passa a valer: repetir bbb no dia seguinte não comenta
    gh.rodar(dados(alerta(assinatura="bbb")), T0 + timedelta(days=2))
    assert len(gh.issues[1]["comments"]) == 1


def test_chave_ausente_comenta_resolvido_e_fecha():
    gh = FakeGitHub()
    gh.rodar(dados(alerta("falha-pipeline", "erro", "f1"), alerta()))
    gh.rodar(dados(alerta(), url="https://x/runs/2"), T0 + timedelta(days=1))
    falha = next(i for i in gh.issues.values() if "falha-pipeline" in i["body"])
    assert falha["state"] == "closed"
    assert "Resolvido" in falha["comments"][-1]["body"] and "runs/2" in falha["comments"][-1]["body"]
    salto = next(i for i in gh.issues.values() if "salto" in i["body"])
    assert salto["state"] == "open"


def test_fora_do_escopo_nao_fecha():
    """Run que caiu na ingestão: o dbt não rodou, a Issue de salto não pode fechar."""
    gh = FakeGitHub()
    gh.rodar(dados(alerta()))
    gh.rodar(dados(alerta("falha-pipeline", "erro", "f1"), escopo=["falha-pipeline"]),
             T0 + timedelta(days=1))
    salto = next(i for i in gh.issues.values() if "salto" in i["body"])
    assert salto["state"] == "open" and salto["comments"] == []
    assert len(gh.issues) == 2


def test_issue_fechada_e_problema_volta_abre_nova():
    gh = FakeGitHub()
    gh.rodar(dados(alerta()))
    gh.rodar(dados(), T0 + timedelta(days=1))
    gh.rodar(dados(alerta()), T0 + timedelta(days=2))
    assert [i["state"] for i in gh.issues.values()] == ["closed", "open"]


def test_issue_humana_com_rotulo_mas_sem_marcador_e_ignorada():
    gh = FakeGitHub()
    gh.issues[1] = {"number": 1, "title": "dúvida", "body": "sem marcador", "labels": ["alerta-pipeline"],
                    "createdAt": iso(T0), "comments": [], "state": "open"}
    gh.rodar(dados())
    assert gh.issues[1]["state"] == "open" and gh.issues[1]["comments"] == []


def test_erro_na_api_nao_propaga_e_nao_fecha_calado(capsys):
    gh = FakeGitHub()
    gh.rodar(dados(alerta()))
    gh.falhar = {"comentar"}
    gh.rodar(dados(alerta("falha-pipeline", "erro", "f1")), T0 + timedelta(days=1))
    out = capsys.readouterr().out
    assert "::warning::falhou: COMENTAR #1" in out
    assert gh.issues[1]["state"] == "open"  # o "resolvido" falhou: não fecha sem explicar
    assert len(gh.issues) == 2               # mas a criação da outra seguiu


def test_falha_ao_listar_nao_cria_nada(capsys):
    gh = FakeGitHub(falhar={"listar"})
    assert gh.rodar(dados(alerta())) == []
    assert gh.issues == {}
    assert "::warning::não consegui listar" in capsys.readouterr().out


def test_dry_run_nao_escreve(capsys):
    gh = FakeGitHub()
    gh.rodar(dados(alerta()))
    acoes = pa.publicar(dados(alerta("falha-pipeline", "erro", "f1")), gh,
                        agora=T0 + timedelta(days=1), dry_run=True)
    assert [a.tipo for a in acoes] == ["criar", "comentar", "fechar"]
    assert gh.chamadas == ["listar", "criar", "listar"]  # nenhuma escrita no dry-run
    out = capsys.readouterr().out
    assert "[dry-run] CRIAR Issue '[pipeline] Teste dbt salto'" in out
    assert "[dry-run] FECHAR #1" in out


def test_main_sai_zero_mesmo_quebrando(tmp_path, capsys):
    assert pa.main(["--alertas", str(tmp_path / "nao_existe.json")]) == 0
    arq = tmp_path / "a.json"
    arq.write_text(json.dumps(dados(alerta())), encoding="utf-8")

    class Quebrado:
        def listar_abertas(self):
            return [{"number": 1}]  # sem createdAt/body: provoca exceção inesperada no plano

    assert pa.main(["--alertas", str(arq)], cliente=Quebrado()) == 0
    assert "::warning::" in capsys.readouterr().out


def test_cliente_gh_monta_comandos():
    chamadas = []

    class Proc:
        returncode, stdout, stderr = 0, "[]", ""

    def executar(cmd, **kw):
        chamadas.append((cmd, kw.get("input")))
        return Proc()

    gh = pa.ClienteGh(executar=executar)
    assert gh.listar_abertas() == []
    gh.criar("[pipeline] t", "corpo", ["alerta-pipeline", "alerta:aviso"])
    gh.comentar(7, "oi")
    gh.fechar(7)
    assert chamadas[0][0][:6] == ["gh", "issue", "list", "--label", "alerta-pipeline", "--state"]
    assert chamadas[1] == (["gh", "issue", "create", "--title", "[pipeline] t", "--body-file", "-",
                            "--label", "alerta-pipeline", "--label", "alerta:aviso"], "corpo")
    assert chamadas[2] == (["gh", "issue", "comment", "7", "--body-file", "-"], "oi")
    assert chamadas[3][0] == ["gh", "issue", "close", "7", "--reason", "completed"]

    Proc.returncode, Proc.stderr = 1, "HTTP 403"
    with pytest.raises(RuntimeError, match="403"):
        gh.fechar(7)
