"""4.5 Endurance: os anexos chegam de verdade no pedido HTTP ao Ollama.

Sobe um Ollama de mentira (servidor HTTP local) e confere, no corpo do
/api/chat, o texto do arquivo, a imagem (só pra quem enxerga), o num_ctx e o
modelo de visão descrevendo a imagem pra quem não enxerga."""

import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CASA = tempfile.mkdtemp(prefix="opentars-casa-")
os.environ["HOME"] = CASA
os.environ["TARS_ARQUIVO_SESSOES"] = os.path.join(CASA, "sessoes.json")

MODELOS = {
    "qwen3:4b": {"capabilities": ["completion", "tools"], "family": "qwen3", "size": "4.0B"},
    "gemma3:4b": {"capabilities": ["completion", "vision", "tools"], "family": "gemma3", "size": "4.3B"},
}
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
            return self._json({"models": [{"name": n, "model": n, "size": 3_000_000_000, "details": {
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
            if corpo.get("stream", True):
                linhas = [{"model": quem, "message": {"role": "assistant", "content": f"resposta de {quem}"}, "done": False},
                          {"model": quem, "message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"}]
                dados = ("\n".join(json.dumps(l) for l in linhas) + "\n").encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)
                return
            return self._json({"model": quem, "message": {"role": "assistant", "content": "um quadrado verde"}, "done": True})
        self._json({}, 404)


servidor = ThreadingHTTPServer(("127.0.0.1", 0), Falso)
threading.Thread(target=servidor.serve_forever, daemon=True).start()
os.environ["OLLAMA_HOST"] = f"127.0.0.1:{servidor.server_address[1]}"

from _util import carregar_tars  # noqa: E402

tars = carregar_tars()
from PIL import Image  # noqa: E402

assert tars.OLLAMA_HOST == f"http://127.0.0.1:{servidor.server_address[1]}"
tars.avisos_de_ambiente = lambda: []
tars.salvar_sessoes = lambda: None
tars.detectar_gpu = lambda forcar=False: None
tars.escolher_modelo = lambda texto, tarefa=None, complexa=False: tars.modelo_manual or "qwen3:4b"

PASTA = Path(tempfile.mkdtemp(prefix="opentars-anexos-"))
(PASTA / "relatorio.txt").write_text("VENDAS DO MÊS: 1234 unidades\n" * 40, encoding="utf-8")
Image.new("RGB", (80, 60), "green").save(PASTA / "verde.png")
anexos = tars.anexos_lib.carregar_varios([PASTA / "relatorio.txt", PASTA / "verde.png"])[0]
assert [a.tipo for a in anexos] == ["texto", "imagem"]


def ultimo_chat_de(modelo, streaming=True):
    return [c for c in chats if c["model"] == modelo and bool(c.get("stream", True)) == streaming][-1]


# 1. modelo que enxerga: texto E imagem no mesmo pedido
tars.limpar_sessao()
tars.interpretar_comando_modelo("/modelo gemma3:4b")
resposta = tars.processar_mensagem("resuma o relatório e diga a cor da imagem", anexos=anexos)
assert resposta and "gemma3:4b" in resposta, resposta
corpo = ultimo_chat_de("gemma3:4b")
usuario = [m for m in corpo["messages"] if m["role"] == "user"][-1]
assert usuario["content"].startswith("resuma o relatório e diga a cor da imagem\n\n[Files attached")
assert "VENDAS DO MÊS: 1234 unidades" in usuario["content"] and "relatorio.txt" in usuario["content"]
assert len(usuario.get("images", [])) == 1 and usuario["images"][0] == anexos[1].imagem_b64
assert corpo["tools"], "as ferramentas continuam sendo oferecidas"
assert corpo["options"]["num_ctx"] == 8192, corpo["options"]
print("OK: modelo com visão recebe o texto do arquivo e a imagem")

# 2. modelo que não enxerga: sem imagem no pedido; o texto vai e a IA é avisada que não vê a imagem
chats.clear()
tars.limpar_sessao()
tars.interpretar_comando_modelo("/modelo qwen3:4b")
resposta = tars.processar_mensagem("o que tem nesses arquivos?", anexos=anexos)
assert resposta and "qwen3:4b" in resposta, resposta
corpo = ultimo_chat_de("qwen3:4b")
usuario = [m for m in corpo["messages"] if m["role"] == "user"][-1]
assert "images" not in usuario and "VENDAS DO MÊS" in usuario["content"] and "cannot see images" in usuario["content"]
assert not [c for c in chats if c["model"] == "gemma3:4b"], "o modelo de visão de reserva saiu na 4.6: nada é descrito por outro modelo"
print("OK: modelo sem visão recebe o texto e o aviso de que não vê a imagem")

# 3. arquivo grande sobe o num_ctx; /limpar volta
chats.clear()
(PASTA / "enorme.txt").write_text("dado importante numero 7. " * 6000)
enorme = tars.anexos_lib.carregar_varios([PASTA / "enorme.txt"])[0]
tars.limpar_sessao()
tars.interpretar_comando_modelo("/modelo qwen3:4b")
tars.processar_mensagem("resuma", anexos=enorme)
assert ultimo_chat_de("qwen3:4b")["options"]["num_ctx"] == 12288, ultimo_chat_de("qwen3:4b")["options"]
chats.clear()
tars.processar_mensagem("e agora?")
assert ultimo_chat_de("qwen3:4b")["options"]["num_ctx"] == 12288, "continua alto na mesma conversa (o Ollama não recarrega à toa)"
tars.limpar_sessao()
chats.clear()
tars.processar_mensagem("oi")
assert ultimo_chat_de("qwen3:4b")["options"]["num_ctx"] == 8192
print("OK: anexo grande sobe o num_ctx (o menor degrau que cabe, no máximo 16384 sem GPU grande); /limpar volta a 8192")

# 4. a conversa seguinte ainda enxerga o arquivo anexado (está no histórico)
chats.clear()
tars.limpar_sessao()
tars.processar_mensagem("leia", anexos=[anexos[0]])
tars.processar_mensagem("qual era mesmo o número de unidades?")
historico = [m["content"] for m in ultimo_chat_de("qwen3:4b")["messages"] if m["role"] == "user"]
assert any("1234 unidades" in h for h in historico), historico
print("OK: o arquivo anexado fica na conversa para as perguntas seguintes")

print("\nTUDO OK.")
