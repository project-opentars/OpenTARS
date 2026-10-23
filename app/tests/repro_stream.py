"""5.0 Tesseract: a janela principal em Qt, de ponta a ponta, sem tela (offscreen), com o núcleo de verdade
contra um Ollama de mentira."""

import json
import os
import stat
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ["QT_QPA_PLATFORM"]="xcb"
CASA = tempfile.mkdtemp(prefix="opentars-casa-")
os.environ["HOME"] = CASA
os.environ["TARS_ARQUIVO_SESSOES"] = os.path.join(CASA, "sessoes.json")
os.environ["TARS_ARQUIVO_NUVEM"] = os.path.join(CASA, "nuvem.json")
os.environ["TARS_ARQUIVO_PRIMEIRO_USO"] = os.path.join(CASA, "primeiro_uso.json")

from _util import RAIZ  # noqa: E402,F401

try:
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton
except ImportError:
    print("test_qt_principal: PULADO (PySide6 não instalado)")
    sys.exit(0)

chats = []
FERRAMENTAS=[('open_application',{'app':'calculator'}),('list_windows',{}),('execute_terminal',{'command':'echo oi'}),('take_screenshot',{}),('close_application',{'app':'calculator'})]
FERRAMENTAS_X=[('open_application',{'app':'calculator'}),('list_elements',{'app':'calculator'}),('click_element',{'name':'7','app':'calculator'}),('type_in_element',{'name':'x','text':'1'}),('click_mouse',{'x':500,'y':500}),('drag_mouse',{'from_x':1,'from_y':1,'to':'center'}),('scroll_mouse',{'amount':3}),('type_text',{'text':'oi'}),('press_key',{'key':'escape'}),('take_screenshot',{}),('focus_window',{'title':'Calculator'}),('move_window',{'title':'Calculator','where':'left'}),('remember',{'fact':'x'}),('forget',{'fact':'x'}),('open_website',{'url':'https://example.com'}),('search_web',{'query':'tars'}),('close_application',{'app':'calculator'})]


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
            ultima = corpo["messages"][-1]["role"]
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            def env(o):
                d = (json.dumps(o) + "\n").encode()
                self.wfile.write(("%x\r\n" % len(d)).encode() + d + b"\r\n"); self.wfile.flush()
            if ultima != "tool" and len(chats) % 2 == 1:
                env({"message": {"role": "assistant", "content": "", "thinking": "Vou pensar um pouco sobre isso. " * 3}, "done": False})
                env({"message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": FERRAMENTAS[(len(chats)//2) % len(FERRAMENTAS)][0], "arguments": FERRAMENTAS[(len(chats)//2) % len(FERRAMENTAS)][1]}}]}, "done": False})
                env({"message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"})
            else:
                texto = ("## Resultado\n\nAqui vai uma resposta **longa** com `codigo`, listas e emoji 😀 ✓:\n\n- item um\n- item dois\n\n```python\nprint('oi')\nfor i in range(3):\n    print(i)\n```\n\n" * 6)
                for i in range(0, len(texto), 4):
                    env({"message": {"role": "assistant", "content": texto[i:i+4]}, "done": False}); time.sleep(0.004)
                env({"message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"})
            self.wfile.write(b"0\r\n\r\n"); return
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



historico = tars_historico.Historico(os.path.join(CASA, "historico.json"))
j = JanelaPrincipal(tars, historico=historico, capturar_stdout=True)
j.resize(1200, 780); j.show()
esperar(lambda: j._modelos, o_que="modelos")
for i,f in enumerate(FERRAMENTAS*2):
    sys.__stdout__.write(f"pedido {i} {f[0]}\n"); sys.__stdout__.flush()
    j.compositor.entrada.setPlainText("faça "+f[0])
    j.enviar()
    esperar(lambda: not j.ponte.esta_ocupado, 40, "fim")
    QTest.qWait(500)
    sys.__stdout__.write("  vivo\n"); sys.__stdout__.flush()
print("FIM")
