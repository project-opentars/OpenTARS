"""5.0 Tesseract: a barra rápida em Qt (pergunta, resposta espelhada, Esc, continuar a conversa, abrir a janela)."""

import os
import sys
import tempfile
import threading
import time

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
    from PySide6.QtCore import Qt
except ImportError:
    print("test_qt_barra_rapida: PULADO (PySide6 não instalado)")
    sys.exit(0)

src = open(os.path.join(os.path.dirname(__file__), "test_qt_principal.py"), encoding="utf-8").read()
# reaproveita o Ollama de mentira e os ajustes do núcleo do teste da janela principal
import json  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

trecho = src[src.index("chats = []"):src.index("import tars_historico")]
exec(compile(trecho, "fake_ollama_inline", "exec"))

import tars_historico  # noqa: E402
from tars_i18n import t  # noqa: E402
from tars_qt.primeiro_uso import criar_aplicativo  # noqa: E402
from tars_qt.principal import JanelaPrincipal  # noqa: E402

app = criar_aplicativo(["teste"])


def esperar(cond, segundos=15, o_que=""):
    fim = time.time() + segundos
    while time.time() < fim:
        app.processEvents()
        if cond():
            return
        QTest.qWait(20)
    import faulthandler
    faulthandler.dump_traceback(all_threads=True)     # onde cada thread parou (no CI do Windows e do macOS, a única pista)
    raise AssertionError(f"tempo esgotado: {o_que}")


historico = tars_historico.Historico(os.path.join(CASA, "historico.json"))
j = JanelaPrincipal(tars, historico=historico, capturar_stdout=False)
esperar(lambda: j._modelos, o_que="modelos")
assert not j.isVisible() and not j.barra.isVisible()

# o atalho/--rapido: só a barra aparece, a janela não
j.pedido_externo.emit("rapido")
esperar(lambda: j.barra.isVisible())
assert not j.isVisible(), "a barra rápida não abre a janela"
assert j.barra.entrada.placeholderText() == t("rapido.dica") and not j.barra.resposta.isVisibleTo(j.barra)

# pergunta de verdade
j.barra.entrada.setPlainText("abra o navegador")
j.barra._enviar()
assert j._pedido_da_barra and j.barra.resposta.isVisibleTo(j.barra)
esperar(lambda: not j._pedido_da_barra and not j.ponte.esta_ocupado, o_que="resposta")
assert "feito" in j.barra.resposta.toPlainText() and "abra o navegador" in j.barra.resposta.toPlainText()
assert j.barra.status.text() == t("rapido.ajuda") and j.barra.isVisible()
esperar(lambda: len(historico.listar()) == 1)
if os.environ.get("TARS_CAPTURAS"):
    QTest.qWait(400)
    j.barra.grab().save(os.path.join(os.environ["TARS_CAPTURAS"], "barra_rapida.png"))
print("OK: a barra aparece sozinha, pergunta, mostra a resposta e a conversa vai pro histórico")

# segunda pergunta continua a mesma conversa
j.barra.entrada.setPlainText("e agora?")
j.barra._enviar()
esperar(lambda: not j._pedido_da_barra and not j.ponte.esta_ocupado)
assert len(chats[-1]["messages"]) > len(chats[-2]["messages"]), "continua a conversa"
assert len(historico.listar()) == 1
print("OK: perguntas seguidas continuam a mesma conversa")

# Esc fecha; reabrir começa limpo e conversa nova
QTest.keyClick(j.barra, Qt.Key_Escape)
assert not j.barra.isVisible()
j.pedido_externo.emit("rapido")
esperar(lambda: j.barra.isVisible())
assert not j.barra.resposta.isVisibleTo(j.barra) and j.barra.perguntas == 0
j.barra.entrada.setPlainText("outra coisa")
j.barra._enviar()
esperar(lambda: not j._pedido_da_barra and not j.ponte.esta_ocupado)
esperar(lambda: len(historico.listar()) == 2, o_que="conversa nova")
print("OK: Esc fecha; reabrir começa limpo, em conversa nova")

# Ctrl+Enter abre a janela
QTest.keyClick(j.barra, Qt.Key_Return, Qt.ControlModifier)
esperar(lambda: j.isVisible() and not j.barra.isVisible())
print("OK: Ctrl+Enter abre a janela principal")

# aprovação: a pergunta de segurança vem pra janela
j.hide()
j.pedido_externo.emit("rapido")
esperar(lambda: j.barra.isVisible())
j.barra.perguntas = 1
j._pedido_da_barra = True

class Ap:
    comando = "rm -rf ~/x"
    def responder(self, ok): self.ok = ok

j._ao_aprovacao(Ap())
assert j.isVisible() and not j.barra.isVisible(), "ação arriscada: a janela aparece com o cartão"
j._pedido_da_barra = False

# fica ocioso: encerra sozinho se só a barra foi usada
import tars_qt.principal as pr  # noqa: E402
j.hide()
j._ultimo_uso = time.monotonic() - 3600
saiu = []
j._sair_de_vez = lambda: saiu.append(1)
j._checar_ocioso()
assert saiu == [1], "30 min sem uso, sem janela: encerra"
j._ultimo_uso = time.monotonic()
j._checar_ocioso()
assert saiu == [1]
print("OK: aprovação traz a janela; sem uso por 30 min só com a barra, encerra")

# 5.2: o atalho das ações sem nada selecionado vira o lançador (a barra rápida); com texto, o painel das ações
import tars_acoes_texto  # noqa: E402
j.barra.hide()
tars_acoes_texto.ler_selecao = lambda: ""
j.pedido_externo.emit("acoes")
esperar(lambda: j.barra.isVisible())
assert j._painel_acoes is None
j.barra.hide()
tars_acoes_texto.ler_selecao = lambda: "Oi pessoal, tudo bem?"
j.pedido_externo.emit("acoes")
esperar(lambda: j._painel_acoes is not None and j._painel_acoes.isVisible())
assert not j.barra.isVisible() and "Oi pessoal" in j._painel_acoes.trecho.text()
j._painel_acoes.fechar()
print("OK: atalho das ações sem seleção abre a barra rápida; com seleção, o painel")

j._saindo = True
j.close()
print("test_qt_barra_rapida: OK")
