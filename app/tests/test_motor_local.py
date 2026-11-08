"""5.3 (F9): o motor llama.cpp com cara de Ollama. Sem modelo e sem rede de fora: tradução dos pedidos, keep_alive,
download conferido pelo SHA-256 (servidor local) e o que o app vê quando nada está instalado."""
import hashlib
import http.server
import os
import sys
import tempfile
import threading

casa = tempfile.mkdtemp(prefix="opentars-motor-")
os.environ["XDG_DATA_HOME"] = casa
os.environ["HOME"] = casa
os.environ["TARS_MOTOR_PORTA"] = "9"   # porta sem ninguém: um motor de verdade aberto na máquina não entra no teste
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tars_motor_local as m  # noqa: E402

L = "ProjectOpenTARS/Gargantua-2:lite"
pedido = {"model": L, "think": False, "stream": True, "logprobs": True, "options": {"temperature": 0.1, "num_predict": 50},
          "tools": [{"type": "function", "function": {"name": "execute_terminal"}}],
          "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "olha", "images": ["QUJD"]},
                       {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "execute_terminal", "arguments": {"command": "ls"}}}]},
                       {"role": "tool", "content": "a.txt", "tool_name": "execute_terminal"}]}
o = m.para_openai(pedido, L)
assert o["temperature"] == 0.1 and o["top_k"] == 20 and o["max_tokens"] == 50 and o["chat_template_kwargs"] == {"enable_thinking": False}
assert o["messages"][1]["content"][1]["image_url"]["url"] == "data:image/png;base64,QUJD"
assert o["messages"][2]["tool_calls"][0]["function"]["arguments"] == '{"command": "ls"}'
assert o["messages"][3]["tool_call_id"] == o["messages"][2]["tool_calls"][0]["id"] == "call_1"
assert "logprobs" not in o, "o llama-server recusa logprobs com ferramentas em streaming (400)"
assert m.para_openai(dict(pedido, tools=None), L)["logprobs"] is True
assert m._tem_imagem(pedido) and not m._tem_imagem({"messages": [{"role": "user", "content": "x"}]})
assert m._chamadas_ollama([{"function": {"name": "f", "arguments": '{"a": 1}'}}]) == [{"function": {"name": "f", "arguments": {"a": 1}}}]
print("OK: pedido do Ollama vira pedido do llama-server (imagem, ferramentas, opções, think)")

assert m._keep_alive(None) == 300 and m._keep_alive(-1) == -1 and m._keep_alive("10m") == 600 and m._keep_alive("0") == 0
print("OK: keep_alive no formato do Ollama")

# o motor escolhido: llama.cpp por padrão; a config de dev ("motor") troca; a variável de ambiente manda mais que a config
import tars_i18n  # noqa: E402
_antes_env, _antes_cfg = os.environ.pop("TARS_MOTOR", None), tars_i18n._config
try:
    tars_i18n._config = {}
    assert m.escolhido() == "llamacpp", "o padrão é o llama.cpp (quem vem da 5.2 é migrado)"
    tars_i18n._config = {"motor": "ollama"}
    assert m.escolhido() == "ollama"
    os.environ["TARS_MOTOR"] = "llamacpp"
    assert m.escolhido() == "llamacpp", "a variável vale mais que a config"
    os.environ["TARS_MOTOR"] = "ollama"
    tars_i18n._config = {}
    assert m.escolhido() == "ollama"
    tars_i18n._config = {"motor": "qualquer coisa"}
    os.environ.pop("TARS_MOTOR")
    assert m.escolhido() == "llamacpp", "valor desconhecido cai no padrão"
finally:
    tars_i18n._config = _antes_cfg
    if _antes_env is not None:
        os.environ["TARS_MOTOR"] = _antes_env
print("OK: motor escolhido: llama.cpp por padrão, Ollama pela config de dev, variável de ambiente manda")

assert not m.pronto() and m.instalados() == [] and m.garantir() is None, "sem motor instalado o app fica no Ollama"
print("OK: sem llama-server e sem modelo, garantir() devolve None e o app segue no Ollama")

conteudo = b"gguf de mentira" * 1000


class Arquivo(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(conteudo)))
        self.end_headers()
        self.wfile.write(conteudo)


servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Arquivo)
threading.Thread(target=servidor.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{servidor.server_port}/x.gguf"
destino = m.pasta_modelos() / "x.gguf"
try:
    m.baixar(url, destino, "0" * 64)
    raise AssertionError("hash errado passou")
except ValueError:
    pass
assert not destino.exists() and not destino.with_name("x.gguf.parcial").exists()
vistos = []
m.baixar(url, destino, hashlib.sha256(conteudo).hexdigest(), lambda f, t: vistos.append((f, t)))
assert destino.read_bytes() == conteudo and vistos[-1] == (len(conteudo), len(conteudo))
servidor.shutdown()
print("OK: download só entra no lugar com o SHA-256 certo")
print("TUDO OK.")
