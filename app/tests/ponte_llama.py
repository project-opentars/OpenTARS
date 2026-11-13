"""Ponte de medida: fala a API do Ollama por fora e usa o llama-server por dentro, para rodar o app de hoje, sem mudar uma linha,
sobre o llama.cpp e comparar os dois motores (PLANO_5.3.md, F9).

    python3 ponte_llama.py --tag ProjectOpenTARS/Gargantua-2:lite --gguf X.gguf --mmproj Y.gguf --binario llama-server --porta 11601

Copia do Ollama de verdade a ficha do modelo (/api/tags, /api/show) para o app tratar o modelo igual. Pede ao llama-server pela API
compatível com OpenAI, com o molde do próprio GGUF (--jinja). A resposta sai num pedaço só: para a prova o tempo total é o mesmo.
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OLLAMA = "http://127.0.0.1:11434"


def _pedir(url, corpo=None, tempo=600):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    with urllib.request.urlopen(urllib.request.Request(url, dados, {"Content-Type": "application/json"}), timeout=tempo) as r:
        return json.loads(r.read())


def para_openai(corpo, parametros):
    """O corpo do /api/chat do Ollama no formato do /v1/chat/completions. parametros: os do Modelfile (top_k, top_p, repeat_penalty)."""
    mensagens, pendentes, numero = [], [], 0
    for m in corpo.get("messages", []):
        saida = {"role": m["role"], "content": m.get("content") or ""}
        if m.get("images"):
            saida["content"] = [{"type": "text", "text": saida["content"]}] + [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{i}"}} for i in m["images"]]
        if m.get("tool_calls"):
            saida["tool_calls"] = []
            for chamada in m["tool_calls"]:
                numero += 1
                f = chamada.get("function", {})
                argumentos = f.get("arguments")
                saida["tool_calls"].append({"id": f"call_{numero}", "type": "function", "function": {
                    "name": f.get("name"), "arguments": argumentos if isinstance(argumentos, str) else json.dumps(argumentos or {}, ensure_ascii=False)}})
                pendentes.append(f"call_{numero}")
        if m["role"] == "tool":
            saida["tool_call_id"] = pendentes.pop(0) if pendentes else "call_0"
            if m.get("tool_name") or m.get("name"):
                saida["name"] = m.get("tool_name") or m.get("name")
        mensagens.append(saida)
    opcoes = {**parametros, **corpo.get("options", {})}
    saida = {"messages": mensagens, "stream": False, "cache_prompt": True, "temperature": opcoes.get("temperature", 0.4),
             "top_p": opcoes.get("top_p", 0.8), "top_k": opcoes.get("top_k", 20), "repeat_penalty": opcoes.get("repeat_penalty", 1.05),
             "chat_template_kwargs": {"enable_thinking": bool(corpo.get("think", True))}}
    if opcoes.get("num_predict"):
        saida["max_tokens"] = opcoes["num_predict"]
    if corpo.get("tools"):
        saida["tools"] = corpo["tools"]
    if corpo.get("logprobs"):
        saida["logprobs"] = True
    if corpo.get("format") == "json":
        saida["response_format"] = {"type": "json_object"}
    elif isinstance(corpo.get("format"), dict):
        saida["response_format"] = {"type": "json_schema", "json_schema": {"schema": corpo["format"]}}
    return saida


def para_ollama(resposta, modelo, inicio):
    """A resposta do llama-server como o último pedaço do /api/chat do Ollama."""
    escolha = resposta["choices"][0]
    m = escolha["message"]
    mensagem = {"role": "assistant", "content": m.get("content") or ""}
    if m.get("reasoning_content"):
        mensagem["thinking"] = m["reasoning_content"]
    if m.get("tool_calls"):
        mensagem["tool_calls"] = []
        for chamada in m["tool_calls"]:
            f = chamada["function"]
            argumentos = f.get("arguments")
            try:
                argumentos = json.loads(argumentos) if isinstance(argumentos, str) else argumentos
            except ValueError:
                argumentos = {}
            mensagem["tool_calls"].append({"function": {"name": f["name"], "arguments": argumentos or {}}})
    saida = {"model": modelo, "message": mensagem, "done": True, "total_duration": int((time.time() - inicio) * 1e9),
             "done_reason": "length" if escolha.get("finish_reason") == "length" else "stop"}
    if (escolha.get("logprobs") or {}).get("content"):
        saida["logprobs"] = [{"token": x.get("token"), "logprob": x.get("logprob")} for x in escolha["logprobs"]["content"]]
    return saida


def servir(args):
    tags = _pedir(f"{OLLAMA}/api/tags")
    ficha = next(m for m in tags["models"] if m["name"] == args.tag)
    detalhes = _pedir(f"{OLLAMA}/api/show", {"model": args.tag})
    parametros = {}
    for linha in str(detalhes.get("parameters") or "").splitlines():
        partes = linha.split()
        if len(partes) == 2:
            try:
                parametros[partes[0]] = float(partes[1])
            except ValueError:
                pass
    comando = [args.binario, "-m", args.gguf, "--host", "127.0.0.1", "--port", str(args.porta_motor), "-c", str(args.contexto),
               "-t", str(args.threads), "--jinja", "--parallel", "1", "--no-webui"] + args.extra.split()
    if args.mmproj:
        comando += ["--mmproj", args.mmproj]
    motor = subprocess.Popen(comando, stdout=open(args.log, "ab"), stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{args.porta_motor}"
    for _ in range(600):
        try:
            if _pedir(f"{url}/health", tempo=2).get("status") == "ok":
                break
        except (OSError, ValueError):
            time.sleep(0.5)
    else:
        motor.kill()
        sys.exit("o llama-server não subiu")

    class Pedido(BaseHTTPRequestHandler):
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
                return self._json({"version": "0.40.13"})
            if self.path == "/api/tags":
                return self._json({"models": [ficha]})
            if self.path == "/api/ps":
                return self._json({"models": [{"name": args.tag, "model": args.tag, "size": ficha.get("size", 0), "size_vram": 0}]})
            self._json({"error": "not found"}, 404)

        def do_POST(self):
            corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            if self.path == "/api/show":
                return self._json(detalhes)
            if self.path == "/api/generate":
                return self._json({"model": args.tag, "response": "", "done": True})
            if self.path != "/api/chat":
                return self._json({"error": "not found"}, 404)
            inicio = time.time()
            try:
                saida = para_ollama(_pedir(f"{url}/v1/chat/completions", para_openai(corpo, parametros)), args.tag, inicio)
            except urllib.error.HTTPError as e:
                saida = {"error": e.read().decode("utf-8", "replace")[:300]}
            except OSError as e:
                saida = {"error": str(e)}
            texto = (json.dumps(saida) + "\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Content-Length", str(len(texto)))
            self.end_headers()
            self.wfile.write(texto)

    try:
        ThreadingHTTPServer(("127.0.0.1", args.porta), Pedido).serve_forever()
    finally:
        motor.terminate()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for nome in ("--tag", "--gguf", "--binario"):
        p.add_argument(nome, required=True)
    p.add_argument("--mmproj", default="")
    p.add_argument("--porta", type=int, default=11601)
    p.add_argument("--porta-motor", type=int, default=18201)
    p.add_argument("--contexto", type=int, default=8192)
    p.add_argument("--threads", type=int, default=8)
    p.add_argument("--extra", default="")
    p.add_argument("--log", default="/dev/null")
    servir(p.parse_args())
