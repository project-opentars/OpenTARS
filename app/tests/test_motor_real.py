"""5.3 (F9): o motor llama.cpp de verdade neste sistema (llama-server da Release, Gargantua 2 Lite do Hugging Face).
Baixa ~650 MB: só roda com TARS_MOTOR_REAL=1 (o CI do Windows e do macOS liga). Confere o que o app precisa: lista,
uma conversa, uma chamada de ferramenta e descarregar."""
import json
import os
import sys
import tempfile
import urllib.request

if os.environ.get("TARS_MOTOR_REAL") != "1":
    print("PULADO (TARS_MOTOR_REAL=1 liga; baixa o llama-server e o Lite)")
    sys.exit(0)

pasta = tempfile.mkdtemp(prefix="opentars-motor-real-")
os.environ.update(XDG_DATA_HOME=pasta, LOCALAPPDATA=pasta, TARS_MOTOR_PORTA="11496")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tars_motor_local as m  # noqa: E402

L = "ProjectOpenTARS/Gargantua-2:lite"
print("variantes:", m.variantes())
m.preparar([L])
print("llama-server:", m.binario())
url = m.garantir(espera=30)
if not url:
    for nome in ("motor.log", "llama-server.log"):
        arquivo = m.pasta() / nome
        print(f"--- {arquivo}\n" + (arquivo.read_text(errors="replace")[-3000:] if arquivo.exists() else "(não existe)"))
assert url, "o motor não subiu"


def pedir(caminho, corpo=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    with urllib.request.urlopen(urllib.request.Request(url + caminho, dados, {"Content-Type": "application/json"}), timeout=600) as r:
        return [json.loads(x) for x in r.read().decode().splitlines() if x.strip()]


assert L in [x["name"] for x in pedir("/api/tags")[0]["models"]]
r = pedir("/api/chat", {"model": L, "stream": False, "think": False, "messages": [{"role": "user", "content": "Say hi in three words."}]})[0]
assert r["done"] and r["message"]["content"].strip(), r
print("conversa:", r["message"]["content"][:60])
ferramenta = {"type": "function", "function": {"name": "execute_terminal", "description": "Run a shell command",
              "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}}
linhas = pedir("/api/chat", {"model": L, "stream": True, "think": False, "logprobs": True, "tools": [ferramenta],
                             "messages": [{"role": "user", "content": "create a folder named reports in my home"}]})
chamadas = linhas[-1]["message"].get("tool_calls")
assert linhas[-1]["done"] and chamadas and chamadas[0]["function"]["name"] == "execute_terminal", linhas[-1]
print("ferramenta:", chamadas[0]["function"]["arguments"])
assert pedir("/api/generate", {"model": L, "keep_alive": 0})[0]["done_reason"] == "unload"
assert pedir("/api/ps")[0]["models"] == []
print("TUDO OK.")
