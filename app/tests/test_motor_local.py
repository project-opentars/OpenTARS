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

# o motor: sempre llama.cpp; a config não troca mais (14/11, o Ollama saiu); só a variável de desenvolvimento TARS_MOTOR=ollama
import tars_i18n  # noqa: E402
_antes_env, _antes_cfg = os.environ.pop("TARS_MOTOR", None), tars_i18n._config
try:
    tars_i18n._config = {"motor": "ollama"}
    assert m.escolhido() == "llamacpp", "a chave antiga da config não leva mais ao Ollama"
    os.environ["TARS_MOTOR"] = "ollama"
    assert m.escolhido() == "ollama", "a variável de desenvolvimento continua (baterias do Lab)"
finally:
    tars_i18n._config = _antes_cfg
    os.environ.pop("TARS_MOTOR", None)
    if _antes_env is not None:
        os.environ["TARS_MOTOR"] = _antes_env
print("OK: motor sempre llama.cpp; só TARS_MOTOR=ollama (desenvolvimento) muda")

assert not m.pronto() and m.instalados() == [] and m.garantir() is None, "sem llama-server, garantir() não sobe nada"
print("OK: sem llama-server e sem modelo, garantir() devolve None")

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
print("OK: download só entra no lugar com o SHA-256 certo")

# revisão de 13/11: o nome do GGUF não muda entre versões; um arquivo velho de mesmo nome é trocado pelo do catálogo
m._HF, _hf_antes = url.replace("x.gguf", "{arquivo}"), m._HF
destino.write_bytes(b"modelo velho")
destino.with_name("x.gguf.sha256").unlink(missing_ok=True)
assert m.sha_do_arquivo(destino) == hashlib.sha256(b"modelo velho").hexdigest()
m.obter_arquivo("r", "x.gguf", hashlib.sha256(conteudo).hexdigest())
assert destino.read_bytes() == conteudo and m.sha_do_arquivo(destino) == hashlib.sha256(conteudo).hexdigest()
m._HF = _hf_antes
servidor.shutdown()
print("OK: modelo velho com o mesmo nome é trocado; a marca guarda o SHA-256")
# 14/11: modelos da loja (Hugging Face) entram no catálogo pela loja.json; ficha ruim (caminho no nome, hash torto) não entra
sha = "a" * 64
boa = {"repo": "bartowski/Qwen3-4B-GGUF", "gguf": ["Qwen3-4B-Q4_K_M.gguf", sha, 123], "mmproj": None, "capabilities": ["completion", "tools"]}
for ruim in ({**boa, "gguf": ["../../x.gguf", sha, 1]}, {**boa, "gguf": ["a.gguf", "zz", 1]}, {**boa, "repo": "a/b/c"},
             {**boa, "mmproj": ["m.bin", sha, 1]}):
    try:
        m.adicionar_da_loja("hf.co/x:y", ruim)
        raise AssertionError(f"ficha ruim entrou: {ruim}")
    except ValueError:
        pass
try:
    m.adicionar_da_loja("ProjectOpenTARS/Gargantua-2.5:latest", boa)
    raise AssertionError("a loja não pode trocar um Gargantua")
except ValueError:
    pass
m.adicionar_da_loja("hf.co/bartowski/Qwen3-4B-GGUF:Q4_K_M", boa)
assert m.CATALOGO["hf.co/bartowski/Qwen3-4B-GGUF:Q4_K_M"]["repo"] == "bartowski/Qwen3-4B-GGUF"
assert m.CATALOGO["ProjectOpenTARS/Gargantua-2.5:latest"]["repo"] == "OpenTARS/Gargantua-2.5"
assert not m.instalado("hf.co/bartowski/Qwen3-4B-GGUF:Q4_K_M")
m.remover_da_loja("hf.co/bartowski/Qwen3-4B-GGUF:Q4_K_M")
assert "hf.co/bartowski/Qwen3-4B-GGUF:Q4_K_M" not in m.CATALOGO and "ProjectOpenTARS/Gargantua-2.5:latest" in m.CATALOGO
print("OK: loja do Hugging Face: ficha validada, entra e sai do catálogo, não troca os Gargantua")

# a variante pelo caminho, e a marca sem-gpu tira o Vulkan das opções
from pathlib import Path  # noqa: E402
assert m.variante_do(Path("/x") / m.VERSAO_LLAMA / "vulkan" / "bin" / "llama-server") == "vulkan" and m.variante_do("/x/y") == ""
m.tem_vulkan, _tv = (lambda: True), m.tem_vulkan
m.sistema_e_maquina, _sm = (lambda: ("windows", "x86_64")), m.sistema_e_maquina
assert m.variantes() == ["vulkan", "cpu"]
m._marca_sem_gpu().parent.mkdir(parents=True, exist_ok=True)
m._marca_sem_gpu().write_text("x")
assert m.variantes() == ["cpu"], "depois que a GPU falhou, só CPU"
m._marca_sem_gpu().unlink()
m.tem_vulkan, m.sistema_e_maquina = _tv, _sm
print("OK: reserva em CPU depois que a GPU falha")
print("TUDO OK.")
