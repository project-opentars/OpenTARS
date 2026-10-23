"""5.0 Tesseract: rotinas agendadas na janela Qt (timer, execução, avisos, pré-aprovação, bandeja), com o núcleo
de verdade contra um Ollama de mentira e um relógio controlado."""

import json
import os
import stat
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CASA = tempfile.mkdtemp(prefix="opentars-casa-")
os.environ["HOME"] = CASA
os.environ["TARS_ARQUIVO_SESSOES"] = os.path.join(CASA, "sessoes.json")
os.environ["TARS_ARQUIVO_AGENDA"] = os.path.join(CASA, "agenda.json")
os.environ["TARS_ARQUIVO_NUVEM"] = os.path.join(CASA, "nuvem.json")
os.environ["TARS_ARQUIVO_PRIMEIRO_USO"] = os.path.join(CASA, "primeiro_uso.json")

from _util import RAIZ  # noqa: E402,F401

try:
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton
except ImportError:
    print("test_qt_rotinas: PULADO (PySide6 não instalado)")
    sys.exit(0)

chats = []


class Falso(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, dados, codigo=200):
        corpo = json.dumps(dados).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        if self.path == "/api/version":
            return self._json({"version": "0.12.9"})
        if self.path == "/api/tags":
            return self._json({"models": [{"name": "qwen3:4b", "model": "qwen3:4b", "size": 3_000_000_000, "details": {
                "family": "qwen3", "parameter_size": "4.0B", "quantization_level": "Q4_K_M"}}]})
        if self.path == "/api/ps":
            return self._json({"models": []})
        self._json({}, 404)

    def do_POST(self):
        corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path == "/api/show":
            return self._json({"capabilities": ["completion", "tools"], "details": {
                "family": "qwen3", "parameter_size": "4.0B", "quantization_level": "Q4_K_M"}, "model_info": {}, "parameters": ""})
        if self.path == "/api/generate":
            return self._json({"model": corpo.get("model"), "done": True, "response": ""})
        if self.path == "/api/chat":
            chats.append(corpo)
            linhas = [{"model": "qwen3:4b", "message": {"role": "assistant", "content": "Pronto, **feito**."}, "done": False},
                      {"model": "qwen3:4b", "message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"}]
            dados = ("\n".join(json.dumps(l) for l in linhas) + "\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)
            return
        self._json({}, 404)


servidor = ThreadingHTTPServer(("127.0.0.1", 0), Falso)
threading.Thread(target=servidor.serve_forever, daemon=True).start()
os.environ["OLLAMA_HOST"] = f"127.0.0.1:{servidor.server_address[1]}"

from _util import carregar_tars  # noqa: E402

tars = carregar_tars()
tars.avisos_de_ambiente = lambda: []
tars.detectar_gpu = lambda forcar=False: None
tars.escolher_modelo = lambda texto, tarefa=None, complexa=False: tars.modelo_manual or "qwen3:4b"
tars.aquecer_ajudante = lambda: None

import tars_historico  # noqa: E402
import tars_i18n  # noqa: E402
import tars_primeiro_uso as pu  # noqa: E402
from tars_i18n import t  # noqa: E402
from tars_qt.primeiro_uso import criar_aplicativo  # noqa: E402
from tars_qt.principal import JanelaPrincipal  # noqa: E402
from tars_qt.conversa import CartaoAprovacao, MensagemIA  # noqa: E402

app = criar_aplicativo(["teste"])
SAIDA = os.environ.get("TARS_CAPTURAS")


def esperar(cond, segundos=15, o_que=""):
    fim = time.time() + segundos
    while time.time() < fim:
        app.processEvents()
        if cond():
            return
        QTest.qWait(20)
    raise AssertionError(f"tempo esgotado: {o_que}")


def foto(j, nome):
    if SAIDA:
        QTest.qWait(500)
        j.grab().save(os.path.join(SAIDA, nome + ".png"))


def textos(widget):
    return [l.text() for l in widget.findChildren(QLabel)]


def mensagens_ia(j):
    return j.area.findChildren(MensagemIA)



import datetime as dt  # noqa: E402

import tars_rotinas as agenda_lib  # noqa: E402

relogio = [dt.datetime(2026, 10, 6, 7, 59, 0)]
tars.agenda = agenda_lib.Agenda(os.path.join(CASA, "agenda.json"), agora=lambda: relogio[0])
historico = tars_historico.Historico(os.path.join(CASA, "historico.json"))
j = JanelaPrincipal(tars, historico=historico, capturar_stdout=False)
j.resize(1200, 780)
j.show()
esperar(lambda: j._modelos, o_que="modelos carregados")
assert j.agenda is tars.agenda and not j.faixa.isVisibleTo(j)
falas = []
j.voz.falar = lambda *a, **k: falas.append(a)

# --- criar pelo formulário -------------------------------------------------------------------------
j.abrir_config("rotinas")
pr = j.config.paginas["rotinas"]
assert any(t("rot.vazia") in x for x in textos(pr))
pr._abrir_form(None)
pr.f_nome.setText("Jornal")
pr.f_pedido.setPlainText("abra o navegador")
pr.f_hora.setText("08:00")
pr._salvar()
assert [r["nome"] for r in tars.agenda.listar()] == ["Jornal"], tars.agenda.listar()
assert any("Jornal" in x for x in textos(pr)) and not pr.form.isVisibleTo(pr)
pr._abrir_form(None)
pr.f_nome.setText("")
pr._salvar()
assert pr.erro.isVisibleTo(pr) and pr.erro.text() == t("rot.erro_nome"), pr.erro.text()
pr.form.hide()
foto(j, "rotinas_lista")
print("OK: criar rotina pelo formulário; erro de validação aparece")

# --- na hora: roda sozinha, em conversa própria, sem falar --------------------------------------------
j._tick_agenda()
assert j._rotina_em_curso is None, "ainda não é 08:00"
relogio[0] = dt.datetime(2026, 10, 6, 8, 1, 0)
j.abrir_config("geral")
j._tick_agenda()
assert j._rotina_em_curso is not None and tars.ROTINA_ATUAL["nome"] == "Jornal"
assert j.pilha.currentIndex() == 0 and j.cabecalho.titulo.text() == t("rot.titulo_conversa", nome="Jornal")
esperar(lambda: j._rotina_em_curso is None and not j.ponte.esta_ocupado, o_que="rotina terminou")
assert tars.ROTINA_ATUAL is None
u = tars.agenda.listar()[0]
assert u["ultima"]["resultado"] == "ok" and u["proxima"].startswith("2026-10-07T08:00"), u
assert j.faixa.isVisibleTo(j) and j.faixa.texto.text() == t("rot.aviso_ok", nome="Jornal")
assert any("abra o navegador" in str(m) for m in chats[-1]["messages"])
assert falas == [], "rotina não fala em voz alta"
esperar(lambda: any(c["titulo"] == t("rot.titulo_conversa", nome="Jornal") for c in historico.listar()), o_que="título no histórico")
print("OK: rotina roda na hora, em conversa própria (↻), anota resultado, agenda a próxima, avisa e não fala")

# --- parou: precisava de permissão ---------------------------------------------------------------------------
tars.agenda.criar("Limpa", "apague a pasta velha", {"tipo": "diaria", "hora": "09:00"})
relogio[0] = dt.datetime(2026, 10, 6, 9, 0, 30)
j._tick_agenda()
assert j._rotina_em_curso["nome"] == "Limpa"
tars.ROTINA_BLOQUEOU.append("rm -rf ~/velha")       # o que o hook anotaria ao negar o comando
esperar(lambda: j._rotina_em_curso is None and not j.ponte.esta_ocupado, o_que="rotina parou")
u = tars.agenda.achar_por_nome("Limpa")["ultima"]
assert u["resultado"] == "parou" and "rm -rf" in u["detalhe"], u
assert "rm -rf" in j.faixa.texto.text() and tars.ROTINA_BLOQUEOU == []
print("OK: rotina que precisa de permissão para e avisa o comando")

# --- computador desligado: pulada, e avisa -------------------------------------------------------------------------
tars.agenda.criar("Tarde", "faça o backup", {"tipo": "diaria", "hora": "10:00"})
relogio[0] = dt.datetime(2026, 10, 6, 10, 30, 0)
j._tick_agenda()
assert j._rotina_em_curso is None
assert t("rot.aviso_perdida", nome="Tarde", hora="10:00") == j.faixa.texto.text(), j.faixa.texto.text()
assert tars.agenda.achar_por_nome("Tarde")["ultima"]["resultado"] == "perdida"
print("OK: rotina vencida há mais de 10 min é pulada e a pessoa é avisada")

# --- ocupado: espera ---------------------------------------------------------------------------------------------------
tars.agenda.criar("Espera", "abra o navegador", {"tipo": "diaria", "hora": "10:40"})
relogio[0] = dt.datetime(2026, 10, 6, 10, 41, 0)
j.compositor.entrada.setPlainText("oi")
j.compositor.b_enviar.click()
j._tick_agenda()
assert j._rotina_em_curso is None, "ocupado: não atropela a conversa"
esperar(lambda: not j.ponte.esta_ocupado, o_que="conversa normal terminou")
j._tick_agenda()
assert j._rotina_em_curso is not None and j._rotina_em_curso["nome"] == "Espera"
esperar(lambda: j._rotina_em_curso is None and not j.ponte.esta_ocupado)
print("OK: se o TARS está ocupado, a rotina espera a vez")

# --- rodar agora: não mexe no calendário ------------------------------------------------------------------------------------
antes = tars.agenda.achar_por_nome("Jornal")["proxima"]
j.abrir_config("rotinas")
j.config.rodar_rotina.emit(tars.agenda.achar_por_nome("Jornal")["id"])
assert j._rotina_em_curso is not None
esperar(lambda: j._rotina_em_curso is None and not j.ponte.esta_ocupado)
r = tars.agenda.achar_por_nome("Jornal")
assert r["proxima"] == antes and r["ultima"]["resultado"] == "ok"
print("OK: 'Rodar agora' roda sem mexer na próxima execução")

# --- criada pela IA: nasce pendente, a pessoa aprova ---------------------------------------------------------------------------
res = tars.executar_ferramenta("schedule_task", {"name": "Da IA", "request": "abra o navegador", "when_type": "daily", "time": "18:00"})
assert res["sucesso"]
j._avisar_rotinas_da_ia()
assert j.faixa.texto.text() == t("rot.aviso_ia", nome="Da IA")
j.abrir_config("rotinas")
assert any(t("rot.pendente") in x for x in textos(pr))
botao = [b for b in pr.findChildren(QPushButton) if b.text() == t("rot.aprovar")]
assert len(botao) == 1, (len(botao), [r["nome"] for r in tars.agenda.listar() if not r["aprovada"]])
botao[0].click()
r = tars.agenda.achar_por_nome("Da IA")
assert r["aprovada"] and r["ativa"] and r["proxima"]
foto(j, "rotinas_aprovada")
print("OK: rotina criada pela IA espera aprovação e só liga depois")

# --- bandeja: com rotinas ligadas, fechar esconde; 'Sair' fecha de vez -------------------------------------------------------------
class Bandeja:
    escondida = False
    def isVisible(self): return not self.escondida
    def hide(self): self.escondida = True
    def showMessage(self, *a): pass
    def setVisible(self, v): self.escondida = not v

j._tray = Bandeja()
j.close()
assert j.isHidden() and not j._saindo, "fechou a janela, o openTARS continua na bandeja"
j.show()
for r in tars.agenda.listar():
    tars.agenda.atualizar(r["id"], ativa=False)
j._saindo = False
j._relogio.stop()
j.close()
assert not j.isVisible()
print("OK: com rotinas ligadas a janela vai pra bandeja; sem nenhuma, fecha de verdade")
print("test_qt_rotinas: OK")
