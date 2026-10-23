"""4.5: "olhe a minha tela" de ponta a ponta contra um Ollama de mentira.

O Gargantua (não enxerga) tira o print; o Cooper descreve; nenhum outro modelo de visão
(gemma3, Bonsai...) é chamado; e se o Cooper falha, o plano B entra COM o motivo na tela."""

import base64
import io
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CASA = tempfile.mkdtemp(prefix="opentars-casa-")
os.environ["HOME"] = CASA
os.environ["TARS_ARQUIVO_SESSOES"] = os.path.join(CASA, "sessoes.json")

GARG = "ProjectOpenTARS/Gargantua:latest"
COOPER = "ProjectOpenTARS/cooper:latest"
MODELOS = {
    GARG: {"capabilities": ["completion", "tools"], "family": "qwen3", "size": "4.0B"},
    COOPER: {"capabilities": ["completion", "vision"], "family": "qwen3vl", "size": "2.0B"},
    "gemma3:4b": {"capabilities": ["completion", "vision", "tools"], "family": "gemma3", "size": "4.3B"},
}
chats = []
visao_quebrada = {"valor": False}


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
            return self._json({"models": [{"name": n, "model": n, "digest": "d" + n, "size": 3_000_000_000, "details": {
                "family": m["family"], "parameter_size": m["size"], "quantization_level": "Q4_K_M"}} for n, m in MODELOS.items()]})
        if self.path == "/api/ps":
            return self._json({"models": []})
        self._json({}, 404)

    def do_POST(self):
        corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path == "/api/show":
            m = MODELOS.get(corpo.get("model") or corpo.get("name"), {})
            return self._json({"capabilities": m.get("capabilities", []), "details": {
                "family": m.get("family", ""), "parameter_size": m.get("size", ""), "quantization_level": "Q4_K_M"},
                "model_info": {}, "parameters": ""})
        if self.path == "/api/generate":
            return self._json({"model": corpo.get("model"), "done": True, "response": ""})
        if self.path == "/api/chat":
            chats.append(corpo)
            quem = corpo["model"]
            if quem == COOPER:
                if visao_quebrada["valor"]:
                    return self._json({"error": "model failed to load"}, 500)
                return self._json({"model": quem, "done": True, "message": {
                    "role": "assistant", "content": 'Window "Notes". Button "Save" at (500, 500).'}})
            if quem == "gemma3:4b":
                return self._json({"model": quem, "done": True, "message": {
                    "role": "assistant", "content": "Uma janela de notas com o botão Save (gemma)."}})
            ja_chamou = sum(1 for c in chats if c["model"] == quem)
            if ja_chamou == 1:  # 1ª vez: o Gargantua pede o print
                linhas = [{"model": quem, "done": True, "message": {"role": "assistant", "content": "", "tool_calls": [
                    {"function": {"name": "take_screenshot", "arguments": {}}}]}}]
            else:
                linhas = [{"model": quem, "message": {"role": "assistant", "content": "Vejo a janela Notes."}, "done": False},
                          {"model": quem, "message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"}]
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

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from _util import carregar_tars  # noqa: E402

tars = carregar_tars()
from PIL import Image  # noqa: E402

tars.avisos_de_ambiente = lambda: []
tars.salvar_sessoes = lambda: None
tars.detectar_gpu = lambda forcar=False: None
buffer = io.BytesIO()
Image.new("RGB", (1000, 500), "white").save(buffer, format="PNG")
IMG = base64.b64encode(buffer.getvalue()).decode()
tars._DISPATCH_FERRAMENTAS["take_screenshot"] = lambda a: {"sucesso": True, "mensagem": "ok", "_imagem_b64": IMG}


def pedir():
    chats.clear()
    tars._visao_estado.update(pausado_ate=0.0, quente=False, erro="")
    tars.limpar_sessao()
    tars.interpretar_comando_modelo(f"/modelo {GARG}")
    return tars.processar_mensagem("olhe minha tela usando um print")


# 1. Cooper saudável: ele descreve, o gemma nem é chamado
resposta = pedir()
quem = [c["model"] for c in chats]
assert quem == [GARG, COOPER, GARG], quem
descricao = [m for m in chats[-1]["messages"] if m["role"] == "user"][-1]["content"]
assert 'Button "Save" at (500, 250)' in descricao and "1000x500" in descricao, descricao[:400]
assert "images" not in chats[-1]["messages"][-1], "o Gargantua recebe texto, não imagem"
assert chats[1]["messages"][-1]["images"] == [IMG] or len(chats[1]["messages"][-1]["images"]) == 1
print("OK: Gargantua tira o print, o Cooper descreve e nenhum outro modelo de visão é chamado")

# 2. Cooper com erro: sem plano B, o motivo aparece e a IA é orientada a usar list_elements
visao_quebrada["valor"] = True
import contextlib  # noqa: E402
saida = io.StringIO()
with contextlib.redirect_stdout(saida):
    resposta = pedir()
quem = [c["model"] for c in chats]
assert quem.count(COOPER) == 2 and "gemma3:4b" not in quem, quem  # erro rápido: 2 tentativas e nenhum outro modelo de visão
assert "não respondeu" in saida.getvalue() and "HTTP 500" in saida.getvalue(), saida.getvalue()[-500:]
print("OK: Cooper falhou -> 2 tentativas, sem plano B, e o motivo (HTTP 500) aparece na tela")

# 3. Cooper em pausa (estourou o prazo antes): nem é chamado
visao_quebrada["valor"] = False
chats.clear()
tars.limpar_sessao()
tars._visao_estado.update(pausado_ate=10**12, erro="Read timed out")
tars.interpretar_comando_modelo(f"/modelo {GARG}")
tars.processar_mensagem("olhe minha tela usando um print")
quem = [c["model"] for c in chats]
assert COOPER not in quem and "gemma3:4b" not in quem, quem
print("OK: Cooper em pausa não é chamado de novo (nada de esperar o prazo a cada passo)")
print("\nTUDO OK.")
