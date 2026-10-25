"""Um Ollama de mentira pros testes do primeiro uso (biblioteca padrão).

    servidor, url = subir(modelos=[...], chave="abc")
    ... servidor.pedidos  -> lista de (método, caminho, corpo)
    servidor.shutdown()
"""

import http.server
import json
import threading
import time


class _Manipulador(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _responder(self, codigo, dados, tipo="application/json"):
        corpo = dados if isinstance(dados, bytes) else json.dumps(dados).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        s = self.server
        s.pedidos.append(("GET", self.path, None))
        if self.path == "/api/version":
            return self._responder(200, {"version": "0.99.1"})
        if self.path == "/api/tags":
            return self._responder(200, {"models": [m if isinstance(m, dict) else {"name": m} for m in s.modelos]})
        if self.path == "/models":  # a "nuvem"
            if s.chave and self.headers.get("Authorization") != f"Bearer {s.chave}":
                return self._responder(401, {"error": "chave"})
            return self._responder(200, {"data": [{"id": "x"}]})
        self._responder(404, {"error": "?"})

    def do_DELETE(self):
        s = self.server
        n = int(self.headers.get("Content-Length") or 0)
        corpo = json.loads(self.rfile.read(n) or b"{}")
        s.pedidos.append(("DELETE", self.path, corpo))
        if self.path != "/api/delete":
            return self._responder(404, {"error": "?"})
        if getattr(s, "erro_ao_apagar", ""):
            return self._responder(500, {"error": s.erro_ao_apagar})
        nome = corpo.get("model") or corpo.get("name")
        achados = [m for m in s.modelos if (m if isinstance(m, str) else m.get("name")) == nome]
        if not achados:
            return self._responder(404, {"error": f"model '{nome}' not found"})
        s.modelos.remove(achados[0])
        self._responder(200, {})

    def do_POST(self):
        s = self.server
        n = int(self.headers.get("Content-Length") or 0)
        corpo = json.loads(self.rfile.read(n) or b"{}")
        s.pedidos.append(("POST", self.path, corpo))
        if self.path == "/api/pull":
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            linhas = [{"status": "pulling manifest"}]
            for i in range(1, 5):
                linhas.append({"status": "pulling aaa", "digest": "sha256:aaa", "total": 1000, "completed": i * 250})
            linhas.append({"status": "pulling bbb", "digest": "sha256:bbb", "total": 500, "completed": 500})
            linhas.append({"status": "success"})
            if s.erro_no_download:
                linhas = [{"error": s.erro_no_download}]
            for linha in linhas:
                self.wfile.write((json.dumps(linha) + "\n").encode())
                self.wfile.flush()
                time.sleep(s.atraso)
            return
        if self.path == "/api/show":
            return self._responder(200, {"capabilities": ["completion", "tools"], "details": {"family": "qwen35"}, "model_info": {}})
        if self.path == "/api/generate":          # sem prompt: só carrega ou descarrega (keep_alive)
            return self._responder(200, {"model": corpo.get("model"), "done": True})
        if self.path == "/api/chat":
            if s.erro_no_chat:
                return self._responder(500, {"error": s.erro_no_chat})
            if corpo.get("stream") is True:          # o terminal e a janela leem em fluxo (ndjson)
                linhas = [{"message": {"role": "assistant", "content": s.resposta}, "done": False},
                          {"message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"}]
                return self._responder(200, ("\n".join(json.dumps(l) for l in linhas) + "\n").encode(), "application/x-ndjson")
            return self._responder(200, {"message": {"role": "assistant", "content": s.resposta}})
        self._responder(404, {"error": "?"})


def subir(modelos=(), chave="", resposta="4", erro_no_download="", erro_no_chat="", atraso=0.0):
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Manipulador)
    servidor.daemon_threads = True
    servidor.pedidos = []
    servidor.modelos = list(modelos)
    servidor.chave = chave
    servidor.resposta = resposta
    servidor.erro_no_download = erro_no_download
    servidor.erro_no_chat = erro_no_chat
    servidor.atraso = atraso
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor, f"http://127.0.0.1:{servidor.server_address[1]}"
