"""5.0 Tesseract: a nuvem opcional (servidor compatível com a API da OpenAI).

Um servidor HTTP de verdade (em thread) fala /models e /chat/completions com streaming
SSE, mandando a chamada de ferramenta em pedaços. Confere: conversa e ferramenta de ponta
a ponta, chave no cabeçalho, nuvem desligada = nada sai, chave recusada e limite viram
mensagem clara, e o modelo da nuvem NUNCA entra no automático."""

import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ["TARS_IDIOMA"] = "pt_BR"
os.environ["TARS_ARQUIVO_NUVEM"] = os.path.join(tempfile.mkdtemp(prefix="opentars-nuvem-"), "nuvem.json")
from _util import carregar_tars  # noqa: E402

tars = carregar_tars()
api = tars.api
pu = tars.primeiro_uso

# ------------------------------------------------------------
# 1. Conversão da conversa (Ollama -> OpenAI)
# ------------------------------------------------------------
conversa = [
    {"role": "system", "content": "regras"},
    {"role": "user", "content": "abre a calculadora e tira um print"},
    {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "open_application", "arguments": {"app": "calculadora"}}},
        {"function": {"name": "take_screenshot", "arguments": {}}}]},
    {"role": "tool", "tool_name": "open_application", "content": "{\"success\": true}"},
    {"role": "tool", "tool_name": "take_screenshot", "content": "{\"success\": true}"},
    {"role": "user", "content": "[print]", "images": ["QUJD"]},
    {"role": "tool", "content": "órfão"},
]
o = api.para_openai(conversa)
assert o[2]["tool_calls"][0]["id"] == "call_1" and o[2]["tool_calls"][1]["id"] == "call_2"
assert o[2]["tool_calls"][0]["function"]["arguments"] == '{"app": "calculadora"}'
assert o[3] == {"role": "tool", "tool_call_id": "call_1", "content": "{\"success\": true}"}
assert o[4]["tool_call_id"] == "call_2"
assert o[5]["content"][1] == {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}}
assert o[6]["role"] == "user" and "órfão" in o[6]["content"]
assert api.normalizar_url("localhost:1234") == "http://localhost:1234/v1"
assert api.normalizar_url("http://x:8000/v1/") == "http://x:8000/v1"
print("OK: conversa do Ollama vira formato OpenAI (ids das chamadas, argumentos em texto, imagens)")

# ------------------------------------------------------------
# 2. Servidor falso de verdade
# ------------------------------------------------------------
recebidos = []
LIMITE = {"ligado": False}


def sse(obj):
    return f"data: {json.dumps(obj)}\n\n".encode()


class Servidor(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.headers.get("Authorization") != "Bearer segredo":
            self.send_response(401)
            self.end_headers()
            return
        if self.path == "/v1/models":
            corpo = json.dumps({"data": [{"id": "Qwen/Qwen2.5-7B-Instruct"}, {"id": "nomic-embed-text"},
                                         {"id": "qwen2.5-vl-3b"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(corpo)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        recebidos.append((corpo, self.headers.get("Authorization")))
        if LIMITE["ligado"]:
            self.send_response(429)
            self.end_headers()
            return
        if self.headers.get("Authorization") != "Bearer segredo":
            self.send_response(401)
            self.end_headers()
            return
        if not corpo.get("stream"):
            texto = '{"categoria": "acao"}' if corpo.get("response_format") else "ok"
            dados = json.dumps({"choices": [{"message": {"role": "assistant", "content": texto}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(dados)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        ultima = corpo["messages"][-1]
        if ultima["role"] == "tool":
            partes = [sse({"choices": [{"delta": {"reasoning_content": "já abriu"}}]}),
                      sse({"choices": [{"delta": {"content": "Abri a "}}]}),
                      sse({"choices": [{"delta": {"content": "calculadora."}, "finish_reason": "stop"}]})]
        else:
            partes = [
                sse({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "x1", "type": "function",
                                                            "function": {"name": "open_", "arguments": ""}}]}}]}),
                sse({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"name": "application",
                                                                                     "arguments": "{\"app\": "}}]}}]}),
                sse({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "\"calculadora\"}"}}]},
                                  "finish_reason": "tool_calls"}]}),
            ]
        for p in partes + [b"data: [DONE]\n\n"]:
            self.wfile.write(p)
            self.wfile.flush()


http = HTTPServer(("127.0.0.1", 0), Servidor)
threading.Thread(target=http.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{http.server_port}"

# Desligada (o padrão): nada vai pra rede
assert tars.servidor_api() == "" and tars.listar_modelos_api(forcar=True) == set()
pu.salvar_nuvem(True, "outro", url + "/v1", "segredo")
assert tars.servidor_api() == url + "/v1"
pu.salvar_nuvem(False)
assert tars.servidor_api() == "" and tars.listar_modelos_api(forcar=True) == set()
n_antes = len(recebidos)
r, erro = tars._turno_api("api:x", [{"role": "user", "content": "oi"}], None)
assert r is None and erro == tars.t("msg.nuvem_desligada") and len(recebidos) == n_antes, "desligada: nada sai do computador"
pu.salvar_nuvem(True, "outro", url + "/v1", "segredo")

assert tars.listar_modelos_api(forcar=True) == {"api:Qwen/Qwen2.5-7B-Instruct", "api:qwen2.5-vl-3b"}
tars.listar_modelos_instalados = lambda forcar=False: {"llama3:8b"}
tars.catalogar_modelos(forcar=True)
assert not any(k.startswith("api:") for k in (tars._cache_catalogo["dados"] or {})), "modelo da nuvem nunca entra no catálogo/automático"
assert tars.carregar_modelo("api:Qwen/Qwen2.5-7B-Instruct") is True
assert tars.carregar_modelo("api:nao-existe") is False
assert tars.descarregar_modelo("api:qwen2.5-vl-3b") is True
print(f"OK: {url}/v1/models lista a nuvem; ela fica fora do catálogo local")

# ------------------------------------------------------------
# 3. Conversa com ferramenta, de ponta a ponta
# ------------------------------------------------------------
eventos = []
tars.definir_ouvinte_saida(lambda tipo, dados: eventos.append((tipo, dados)))
tars.contexto_ia = lambda: 8192
tars.modo_modelo = "MANUAL"
tars.listar_janelas_x = lambda: None
abertos = []
tars._DISPATCH_FERRAMENTAS["open_application"] = lambda a: abertos.append(a["app"]) or {
    "sucesso": True, "mensagem": "SUCCESS: opened."}
tars.conversa = []
resposta = tars.perguntar_modelo("api:Qwen/Qwen2.5-7B-Instruct", "abre a calculadora", tarefa="acao")
assert resposta == "Abri a calculadora." and abertos == ["calculadora"], (resposta, abertos)
corpo, chave = recebidos[-1]
assert chave == "Bearer segredo" and corpo["model"] == "Qwen/Qwen2.5-7B-Instruct"
assert corpo["messages"][-2]["tool_calls"][0]["function"]["name"] == "open_application"
assert corpo["messages"][-1]["role"] == "tool" and corpo["messages"][-1]["tool_call_id"] == "call_1"
assert any(tipo == "resposta" for tipo, _ in eventos)
assert not any(tipo == "pensamento" for tipo, _ in eventos), "pedido simples: o raciocínio não aparece (pensar=False)"
print("OK: chamada de ferramenta em pedaços (streaming) vira open_application(calculadora); a resposta aparece na hora")

texto = tars._chat_unico("api:Qwen/Qwen2.5-7B-Instruct", "classifique", formato={"type": "object"})
assert texto == '{"categoria": "acao"}' and recebidos[-1][0]["response_format"]["type"] == "json_schema"
print("OK: pergunta curta com formato JSON usa response_format do servidor")

# Chave recusada e limite viram mensagens claras (sem vazar a chave)
pu.salvar_nuvem(True, "outro", url + "/v1", "errada")
r, erro = tars._turno_api("api:x", [{"role": "user", "content": "oi"}], None)
assert r is None and erro == tars.t("msg.nuvem_chave") and "errada" not in erro
pu.salvar_nuvem(True, "outro", url + "/v1", "segredo")
LIMITE["ligado"] = True
r, erro = tars._turno_api("api:x", [{"role": "user", "content": "oi"}], None)
assert r is None and erro == tars.t("msg.nuvem_limite")
LIMITE["ligado"] = False
print("OK: chave recusada (401) e limite (429) viram avisos claros")

# A variável TARS_CHAVE_API vale mais que o arquivo
os.environ["TARS_CHAVE_API"] = "segredo"
pu.salvar_nuvem(True, "outro", url + "/v1", "qualquer")
assert tars.nuvem_config()["chave"] == "segredo"
del os.environ["TARS_CHAVE_API"]
http.shutdown()
print("\nTUDO OK.")
