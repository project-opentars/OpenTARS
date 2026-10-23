"""5.0: rotinas agendadas (tars_rotinas.py): horários, pré-aprovação, perdidas, arquivo 0600."""

import datetime as dt
import os
import stat
import tempfile

from _util import RAIZ  # noqa: F401

import tars_i18n
import tars_rotinas as R

D = dt.datetime
pasta = tempfile.mkdtemp(prefix="opentars-agenda-")
caminho = os.path.join(pasta, "agenda.json")
relogio = {"agora": D(2026, 10, 6, 7, 0)}      # terça-feira
ag = R.Agenda(caminho, agora=lambda: relogio["agora"])

# --- ler hora e dias ---------------------------------------------------------
assert R.ler_hora("8") == (8, 0) and R.ler_hora("8h30") == (8, 30) and R.ler_hora("08:05") == (8, 5)
assert R.ler_hora("25:00") is None and R.ler_hora("abc") is None and R.ler_hora("") is None
assert R.ler_dias("segunda a sexta") == [0, 1, 2, 3, 4] and R.ler_dias("sáb, dom") == [5, 6]
assert R.ler_dias(["seg", "quarta", 4]) == [0, 2, 4] and R.ler_dias("fim de semana") == [5, 6]
assert R.ler_dias(None) == [] and R.ler_dias("nada") == []

# --- quando ------------------------------------------------------------------
assert R.normalizar_quando({"tipo": "diaria", "hora": "8h"}) == ({"tipo": "diaria", "hora": "08:00"}, None)
assert R.normalizar_quando({"tipo": "diaria", "hora": "99"})[1] == "hora"
assert R.normalizar_quando({"tipo": "semanal", "hora": "9", "dias": []})[1] == "dias"
assert R.normalizar_quando({"tipo": "intervalo", "cada_minutos": 2})[1] == "intervalo"
assert R.normalizar_quando({"tipo": "uma_vez", "data": "ontem"})[1] == "data"
assert R.normalizar_quando({"tipo": "mensal"})[1] == "tipo" and R.normalizar_quando("x")[1] == "tipo"

d = {"tipo": "diaria", "hora": "08:00"}
assert R.proxima_execucao(d, D(2026, 10, 6, 7, 0)) == D(2026, 10, 6, 8, 0)
assert R.proxima_execucao(d, D(2026, 10, 6, 8, 0)) == D(2026, 10, 7, 8, 0), "estritamente depois"
s = {"tipo": "semanal", "hora": "09:30", "dias": [0, 4]}           # segunda e sexta
assert R.proxima_execucao(s, D(2026, 10, 6, 7, 0)) == D(2026, 10, 9, 9, 30)    # terça -> sexta
assert R.proxima_execucao(s, D(2026, 10, 9, 10, 0)) == D(2026, 10, 12, 9, 30)  # sexta tarde -> segunda
i = {"tipo": "intervalo", "cada_minutos": 30}
assert R.proxima_execucao(i, D(2026, 10, 6, 7, 10), criada=D(2026, 10, 6, 7, 0)) == D(2026, 10, 6, 7, 30)
u = {"tipo": "uma_vez", "data": "2026-10-06T10:00:00"}
assert R.proxima_execucao(u, D(2026, 10, 6, 7, 0)) == D(2026, 10, 6, 10, 0)
assert R.proxima_execucao(u, D(2026, 10, 6, 11, 0)) is None

t = tars_i18n.t
assert R.descrever_quando(d, t) == t("rot.q_diaria", hora="08:00") and "08:00" in R.descrever_quando(d, t)
assert "seg" in R.descrever_quando(s, t).lower() and "09:30" in R.descrever_quando(s, t)

# --- ações arriscadas ------------------------------------------------------------
assert R.categoria_do_comando("rm -rf ~/lixo") == "apagar"
assert R.categoria_do_comando("git push origin main") == "enviar"
assert R.categoria_do_comando("curl -X POST https://x.org -d a=1") == "enviar"
assert R.categoria_do_comando("sudo apt install vlc") == "instalar"
assert R.categoria_do_comando("pip install requests") == "instalar"
assert R.categoria_do_comando("ls -la ~") is None and R.categoria_do_comando("curl https://x.org") is None
assert R.categoria_do_comando("git pull") is None

# --- fala_de_rotina ----------------------------------------------------------------
for frase in ("agende uma limpeza todo dia às 8h", "toda segunda abre o jornal", "a cada 30 minutos confere o email",
              "schedule a backup every morning", "cria uma rotina de backup"):
    assert R.fala_de_rotina(frase), frase
for frase in ("abre o navegador", "que horas são", "lembra que meu navegador é o brave"):
    assert not R.fala_de_rotina(frase), frase

# --- criar, listar, arquivo ------------------------------------------------------------
r, erro = ag.criar("Jornal", "abre o site do jornal", {"tipo": "diaria", "hora": "8h"}, permitidas=["apagar", "xyz"])
assert erro is None and r["permitidas"] == ["apagar"] and r["ativa"] and r["aprovada"]
assert r["proxima"] == "2026-10-06T08:00:00", r["proxima"]
assert stat.S_IMODE(os.stat(caminho).st_mode) == 0o600
assert ag.criar("", "x", d)[1] == "nome" and ag.criar("a", "", d)[1] == "pedido"
assert ag.criar("a", "x" * 501, d)[1] == "pedido" and ag.criar("a", "x", {"tipo": "diaria"})[1] == "hora"
for n in range(R.LIMITE_ROTINAS - 1):
    assert ag.criar(f"r{n}", "pedido", i)[1] is None
assert ag.criar("a mais", "x", d)[1] == "limite"
for x in ag.listar()[1:]:
    ag.apagar(x["id"])
assert [x["nome"] for x in ag.listar()] == ["Jornal"]
assert ag.achar_por_nome("jornal")["id"] == r["id"] and ag.achar_por_nome("zzz") is None

# --- autorização -------------------------------------------------------------------------
assert R.autorizado(r, "rm -rf ~/lixo") and not R.autorizado(r, "git push") and not R.autorizado(r, "ls")
nao_aprovada = dict(r, aprovada=False)
assert not R.autorizado(nao_aprovada, "rm -rf ~/lixo")

# --- devidas: ainda cedo, na hora, pulada --------------------------------------------------
assert ag.devidas() == ([], [])
relogio["agora"] = D(2026, 10, 6, 8, 2)
rodar, perdidas = ag.devidas()
assert [x["nome"] for x in rodar] == ["Jornal"] and perdidas == []
ag.registrar(r["id"], "ok", "feito", agora=relogio["agora"])
x = ag.obter(r["id"])
assert x["ultima"]["resultado"] == "ok" and x["proxima"] == "2026-10-07T08:00:00"
assert ag.devidas() == ([], []), "não roda duas vezes"

relogio["agora"] = D(2026, 10, 7, 9, 30)       # o PC estava desligado às 8h
rodar, perdidas = ag.devidas()
assert rodar == [] and [p["nome"] for p in perdidas] == ["Jornal"]
x = ag.obter(r["id"])
assert x["ultima"]["resultado"] == "perdida" and x["proxima"] == "2026-10-08T08:00:00"
assert ag.devidas() == ([], []), "a perdida só é avisada uma vez"

# --- uma vez: some depois de rodar ---------------------------------------------------------
relogio["agora"] = D(2026, 10, 8, 7, 0)
u1, _ = ag.criar("Uma vez", "faz isso", {"tipo": "uma_vez", "data": "2026-10-08T07:30:00"})
relogio["agora"] = D(2026, 10, 8, 7, 31)
rodar, _ = ag.devidas()
assert [x["nome"] for x in rodar] == ["Uma vez"]
ag.registrar(u1["id"], "ok", agora=relogio["agora"])
x = ag.obter(u1["id"])
assert x["proxima"] is None and x["ativa"] is False

# --- criada pela IA: desligada e sem aprovação; só ligar depois de aprovar ----------------------
ia, _ = ag.criar("Da IA", "apaga o cache", d, permitidas=["apagar"], ativa=False, aprovada=False, origem="ia")
assert ia["ativa"] is False and ia["aprovada"] is False and ia["origem"] == "ia"
x, _ = ag.atualizar(ia["id"], ativa=True)
assert x["ativa"] is False, "ligar sem aprovar não liga"
x, _ = ag.atualizar(ia["id"], aprovada=True, ativa=True)
assert x["ativa"] and x["aprovada"]
x, _ = ag.atualizar(ia["id"], pedido="apaga tudo")                # mudou o pedido: precisa aprovar de novo
assert x["aprovada"] is False and x["ativa"] is False
assert ag.atualizar("nada", ativa=True)[1] == "inexistente"
assert ag.atualizar(ia["id"], quando={"tipo": "x"})[1] == "tipo"

# --- apagar --------------------------------------------------------------------------------------------
assert ag.apagar(ia["id"]) and not ag.apagar(ia["id"])
n = len(ag.listar())
assert ag.apagar_tudo() == n and ag.listar() == []

# --- arquivo estragado não derruba ------------------------------------------------------------------------
open(caminho, "w").write("{ isso não é json")
assert ag.listar() == []
assert ag.criar("de novo", "x", d)[1] is None

# --- textos ------------------------------------------------------------------------------------------------
import json
pt = json.load(open(os.path.join(RAIZ, "idiomas", "pt_BR.json"), encoding="utf-8"))
en = json.load(open(os.path.join(RAIZ, "idiomas", "en.json"), encoding="utf-8"))
assert {k for k in pt if k.startswith("rot.")} == {k for k in en if k.startswith("rot.")}
print("test_rotinas: OK")
