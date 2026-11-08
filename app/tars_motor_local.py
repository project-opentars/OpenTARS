"""O motor do openTARS 5.3 (F9 do PLANO_5.3.md): llama.cpp por dentro, a API do Ollama por fora.

Decidido pelo Enzo em 07/11: llama.cpp nos três sistemas, e a parte de visão (mmproj) só quando chega uma imagem. O app continua
falando "Ollama" (13 chamadas, tars_motor.ROTAS): este processo responde nessas rotas e roda um `llama-server` por modelo em uso.

- Modelos Gargantua baixados do Hugging Face (OpenTARS/...) com SHA-256 conferido, na pasta de dados do app.
- `llama-server` da Release fixa do ggml-org (VERSAO_LLAMA), conferido pelo hash: Vulkan no Linux e no Windows (com reserva em CPU
  se a máquina não tiver Vulkan), Metal no macOS.
- Uma instância por modelo; a de visão só sobe quando o pedido traz imagem. Cada uma sai depois do keep_alive parado (padrão 5 min,
  -1 = fica, 0 = sai já). O processo do motor fica aberto (como o serviço do Ollama), só com uns MB de Python.

    python3 tars_motor_local.py --servir        (o app sobe sozinho quando precisa: garantir())
"""
import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import tars_plataforma as plataforma

PORTA = int(os.environ.get("TARS_MOTOR_PORTA") or 11435)
URL = f"http://127.0.0.1:{PORTA}"
VERSAO_LLAMA = "b12032"           # 01/11/2026: a mesma usada no Space; versão fixa, nada de "a mais nova do dia"
_GH = f"https://github.com/ggml-org/llama.cpp/releases/download/{VERSAO_LLAMA}/"
BINARIOS = {   # (sistema, máquina, aceleração): (arquivo, sha256)
    ("linux", "x86_64", "vulkan"): ("llama-b12032-bin-ubuntu-vulkan-x64.tar.gz", "f75e7107f9450034c5467492c41e9ed91816e2d815fc4b802c6bd58de7d5b126"),
    ("linux", "x86_64", "cpu"): ("llama-b12032-bin-ubuntu-x64.tar.gz", "9f10432ca3f66ef003a7a540aaffb9da0acadaefd05404521b9ab7a2436af304"),
    ("windows", "x86_64", "vulkan"): ("llama-b12032-bin-win-vulkan-x64.zip", "19a8bbf269fa683ae7bc04f886c9c2a93e0655c2606f37d2b60069bf9e8bcc32"),
    ("windows", "x86_64", "cpu"): ("llama-b12032-bin-win-cpu-x64.zip", "5296f5d18bb7d422c7c26f4bb9bc796d9d4f41e1312a8c296cff475bdc60d0d4"),
    ("macos", "arm64", "metal"): ("llama-b12032-bin-macos-arm64.tar.gz", "00468fe833eb000b78a748122f5921b6c7b07dc82331a8d0c68196c69cb26382"),
    ("macos", "x86_64", "cpu"): ("llama-b12032-bin-macos-x64.tar.gz", "291d99f3b6f45f67f73afe5381540f29928840a1a14d9c19d6595bd649a035fc"),
}
_HF = "https://huggingface.co/OpenTARS/{repo}/resolve/main/{arquivo}"
_PARAMETROS_QWEN = "top_k                          20\ntop_p                          0.8\nrepeat_penalty                 1.05\ntemperature                    0.4"
CATALOGO = {   # a ficha que o Ollama dava para cada modelo (copiada em 07/11), mais os arquivos do Hugging Face
    "ProjectOpenTARS/Gargantua-2:latest": {
        "repo": "Gargantua-2", "gguf": ("gargantua-1.2-qwen3.5-2b-Q4_0.gguf", "99b7dd093a609a06bd04b8aebeed76cb2508e0d7ce75d5b7b46083ee8a8dcb7a", 1202486848),
        "mmproj": ("mmproj-gargantua-qwen3.5-2b-Q8_0.gguf", "3156ce8710040751b6affc151eb66fe225dbe369a4ae51cd6298b1ae74087790", 364663840),
        "capabilities": ["completion", "vision", "tools", "thinking"], "family": "qwen35", "parameter_size": "1.9B", "quantization_level": "Q4_0",
        "parameters": _PARAMETROS_QWEN},
    "ProjectOpenTARS/Gargantua-2:lite": {
        "repo": "Gargantua-2-Lite", "gguf": ("gargantua-1.2-lite-qwen3.5-0.8b-Q4_0.gguf", "c519103c65de13742ed3fded28aad066d75834dada4c651ce1bbcb87747d9c27", 501452352),
        "mmproj": ("mmproj-gargantua-qwen3.5-0.8b-Q8_0.gguf", "1251de28a9e9c147e81a589d64e67470a5e8aa66a99834bb6902283a4d210519", 115923136),
        "capabilities": ["completion", "vision", "tools", "thinking"], "family": "qwen35", "parameter_size": "752.39M", "quantization_level": "Q4_0",
        "parameters": _PARAMETROS_QWEN},
    "ProjectOpenTARS/Gargantua-Code-Gen2:code": {
        "repo": "Gargantua-Code-Gen2", "gguf": ("gargantua-1.2-code-qwen2.5-coder-7b-Q4_K_M.gguf", "4c17360dcb36a3c0932f600df0eb6d7a3859e3ee7406fd4bbfb0f7c526904456", 4683073536),
        "mmproj": None, "capabilities": ["completion", "tools", "insert"], "family": "qwen2", "parameter_size": "7.6B", "quantization_level": "Q4_K_M",
        "parameters": _PARAMETROS_QWEN},
}
KEEP_ALIVE_PADRAO = 300
OLLAMA = os.environ.get("TARS_OLLAMA_REAL") or "http://127.0.0.1:11434"   # modelos que não são do catálogo ("Mais modelos") seguem para ele
CONTEXTO = 8192


# ---------------------------------------------------------------- arquivos

def pasta():
    return plataforma.pastas()["dados"] / "motor"


def pasta_modelos():
    return pasta() / "modelos"


def sistema_e_maquina():
    maquina = platform.machine().lower()
    maquina = {"amd64": "x86_64", "aarch64": "arm64"}.get(maquina, maquina)
    return plataforma.sistema(), maquina


def tem_vulkan():
    s, _ = sistema_e_maquina()
    if s == "windows":
        return Path(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "vulkan-1.dll").exists()
    if s == "linux":
        try:
            return "libvulkan.so.1" in subprocess.run(["ldconfig", "-p"], capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            return any(Path(p, "libvulkan.so.1").exists() for p in ("/usr/lib/x86_64-linux-gnu", "/usr/lib64", "/usr/lib"))
    return False


def variantes():
    """As acelerações a tentar, da melhor para a reserva."""
    s, m = sistema_e_maquina()
    if s == "macos":
        return ["metal"] if m == "arm64" else ["cpu"]
    return (["vulkan"] if tem_vulkan() else []) + ["cpu"]


def binario():
    """O llama-server instalado (o da melhor variante que já foi baixada), ou None."""
    s, m = sistema_e_maquina()
    nome = "llama-server.exe" if s == "windows" else "llama-server"
    for v in variantes():
        raiz = pasta() / VERSAO_LLAMA / v
        if raiz.exists():
            achado = next(iter(sorted(raiz.rglob(nome))), None)
            if achado:
                return achado
    return None


def _sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def baixar(url, destino, sha, ao_progresso=None, tentativas=3):
    """Baixa com retomada (.parcial), confere o SHA-256 e só então põe no lugar. Levanta ValueError se o hash não bater."""
    for tentativa in range(tentativas):        # a conexão que trava no meio retoma do .parcial (visto em 07/11 no GitHub)
        try:
            return _baixar(url, destino, sha, ao_progresso)
        except (TimeoutError, ConnectionError, urllib.error.URLError):
            if tentativa == tentativas - 1:
                raise


def _baixar(url, destino, sha, ao_progresso):
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".parcial")
    feito = parcial.stat().st_size if parcial.exists() else 0
    pedido = urllib.request.Request(url, headers={"User-Agent": "openTARS", **({"Range": f"bytes={feito}-"} if feito else {})})
    with urllib.request.urlopen(pedido, timeout=60) as r:
        if feito and r.status != 206:
            feito = 0                         # o servidor não retomou: começa de novo
        total = feito + int(r.headers.get("Content-Length") or 0)
        with open(parcial, "ab" if feito else "wb") as f:
            for bloco in iter(lambda: r.read(1 << 16), b""):
                f.write(bloco)
                feito += len(bloco)
                if ao_progresso:
                    ao_progresso(feito, total)
    if _sha256(parcial) != sha:
        parcial.unlink(missing_ok=True)
        raise ValueError(f"{destino.name}: SHA-256 check failed")
    os.replace(parcial, destino)
    return destino


def instalar_binario(ao_progresso=None):
    """Baixa e extrai o llama-server desta máquina (a melhor variante; a de CPU se a outra não existir aqui)."""
    s, m = sistema_e_maquina()
    for v in variantes():
        chave = (s, m, v)
        if chave not in BINARIOS:
            continue
        arquivo, sha = BINARIOS[chave]
        raiz = pasta() / VERSAO_LLAMA / v
        pacote = baixar(_GH + arquivo, pasta() / "baixados" / arquivo, sha, ao_progresso)
        temporario = raiz.with_name(raiz.name + ".novo")
        shutil.rmtree(temporario, ignore_errors=True)
        temporario.mkdir(parents=True)
        if arquivo.endswith(".zip"):
            with zipfile.ZipFile(pacote) as z:
                z.extractall(temporario)
        else:
            with tarfile.open(pacote) as t:
                t.extractall(temporario, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
        for executavel in temporario.rglob("llama-server*"):
            executavel.chmod(0o755)
        shutil.rmtree(raiz, ignore_errors=True)
        os.replace(temporario, raiz)
        pacote.unlink(missing_ok=True)
        return binario()
    raise ValueError(f"no llama.cpp build for {s} {m}")


def _blob_do_ollama(sha):
    """O arquivo do Ollama com esse SHA-256 (o mesmo GGUF que publicamos no Hugging Face), se esta máquina tiver."""
    pastas = [os.environ.get("OLLAMA_MODELS"), Path.home() / ".ollama" / "models", "/usr/share/ollama/.ollama/models", "/var/lib/ollama/models"]
    for raiz in filter(None, pastas):
        blob = Path(raiz) / "blobs" / f"sha256-{sha}"
        if blob.is_file() and os.access(blob, os.R_OK):
            return blob
    return None


def obter_arquivo(repo, arquivo, sha, ao_progresso=None):
    """Põe um GGUF do catálogo na pasta: copiado do Ollama se ele já tem o mesmo arquivo, senão baixado do Hugging Face."""
    destino = pasta_modelos() / arquivo
    if destino.exists():
        return destino
    blob = _blob_do_ollama(sha)
    if not blob:
        return baixar(_HF.format(repo=repo, arquivo=arquivo), destino, sha, ao_progresso)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_name(destino.name + ".parcial")
    shutil.copyfile(blob, temporario)
    if _sha256(temporario) != sha:
        temporario.unlink(missing_ok=True)
        raise ValueError(f"{arquivo}: SHA-256 check failed")
    os.replace(temporario, destino)
    return destino


def preparar(nomes, ao_progresso=None):
    """Instala o llama-server e os modelos pedidos. Levanta OSError/ValueError."""
    if binario() is None:
        instalar_binario(ao_progresso)
    for nome in nomes:
        ficha = CATALOGO[_nome(nome)]
        for arquivo, sha, _ in [ficha["gguf"]] + ([ficha["mmproj"]] if ficha.get("mmproj") else []):
            obter_arquivo(ficha["repo"], arquivo, sha, ao_progresso)


def _nome(nome):
    """"ProjectOpenTARS/Gargantua-2" é o mesmo que ":latest", como no Ollama."""
    return nome if not nome or ":" in nome.split("/")[-1] else nome + ":latest"


def instalado(nome):
    nome = _nome(nome)
    ficha = CATALOGO.get(nome)
    return bool(ficha) and (pasta_modelos() / ficha["gguf"][0]).exists()


def instalados():
    return [n for n in CATALOGO if instalado(n)]


def pronto():
    """O motor pode servir agora: tem o llama-server e ao menos um modelo."""
    return binario() is not None and bool(instalados())


# ---------------------------------------------------------------- instâncias do llama-server

def _porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _pedir(url, corpo=None, tempo=900):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    return urllib.request.urlopen(urllib.request.Request(url, dados, {"Content-Type": "application/json"}), timeout=tempo)


class Instancia:
    def __init__(self, nome, visao):
        ficha = CATALOGO[nome]
        self.nome, self.visao, self.porta = nome, visao, _porta_livre()
        self.ultimo, self.keep_alive = time.time(), KEEP_ALIVE_PADRAO
        comando = [str(binario()), "-m", str(pasta_modelos() / ficha["gguf"][0]), "--host", "127.0.0.1", "--port", str(self.porta),
                   "-c", str(CONTEXTO), "--jinja", "--parallel", "1", "--no-webui", "-ngl", "99"]
        if visao and ficha.get("mmproj"):
            comando += ["--mmproj", str(pasta_modelos() / ficha["mmproj"][0])]
        registro = open(pasta() / "llama-server.log", "ab")
        extra = {"creationflags": 0x08000000} if plataforma.sistema() == "windows" else {"start_new_session": True}   # sem janela preta no Windows
        self.processo = subprocess.Popen(comando, stdin=subprocess.DEVNULL, stdout=registro, stderr=registro, **extra)
        limite = time.time() + 300
        while time.time() < limite:
            if self.processo.poll() is not None:
                raise RuntimeError(f"llama-server stopped with code {self.processo.returncode} (see {pasta() / 'llama-server.log'})")
            try:
                with _pedir(f"http://127.0.0.1:{self.porta}/health", tempo=2) as r:
                    if json.loads(r.read()).get("status") == "ok":
                        return
            except (OSError, ValueError):
                time.sleep(0.3)
        self.parar()
        raise RuntimeError("llama-server took too long to start")

    def parar(self):
        if self.processo.poll() is None:
            self.processo.terminate()
            try:
                self.processo.wait(10)
            except subprocess.TimeoutExpired:
                self.processo.kill()


class Motor:
    def __init__(self):
        self.instancias, self.trava, self.ultimo_pedido = {}, threading.Lock(), time.time()

    def instancia(self, nome, visao=False):
        if nome not in CATALOGO or not instalado(nome):
            raise KeyError(nome)
        visao = visao and bool(CATALOGO[nome].get("mmproj"))
        with self.trava:
            chave = (nome, visao)
            atual = self.instancias.get(chave)
            if atual is None or atual.processo.poll() is not None:
                atual = self.instancias[chave] = Instancia(nome, visao)
            atual.ultimo = time.time()
            return atual

    def descarregar(self, nome):
        with self.trava:
            for chave in [c for c in self.instancias if c[0] == nome]:
                self.instancias.pop(chave).parar()

    def faxina(self):
        """Tira da memória o que ficou parado além do keep_alive."""
        agora = time.time()
        with self.trava:
            for chave, inst in list(self.instancias.items()):
                if inst.processo.poll() is not None or (inst.keep_alive >= 0 and agora - inst.ultimo > inst.keep_alive):
                    self.instancias.pop(chave).parar()

    def parar_tudo(self):
        with self.trava:
            for inst in self.instancias.values():
                inst.parar()
            self.instancias.clear()


def _keep_alive(valor):
    if valor in (None, ""):
        return KEEP_ALIVE_PADRAO
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip()
    unidade = {"s": 1, "m": 60, "h": 3600}.get(texto[-1:], 1)
    try:
        return float(texto[:-1] if texto[-1:] in "smh" else texto) * unidade
    except ValueError:
        return KEEP_ALIVE_PADRAO


# ---------------------------------------------------------------- tradução Ollama <-> OpenAI (llama-server)

def _parametros(nome):
    p = {}
    for linha in CATALOGO[nome]["parameters"].splitlines():
        partes = linha.split()
        if len(partes) == 2:
            try:
                p[partes[0]] = float(partes[1])
            except ValueError:
                pass
    return p


def para_openai(corpo, nome):
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
    opcoes = {**_parametros(nome), **(corpo.get("options") or {})}
    saida = {"messages": mensagens, "stream": bool(corpo.get("stream", True)), "cache_prompt": True,
             "temperature": opcoes.get("temperature", 0.4), "top_p": opcoes.get("top_p", 0.8), "top_k": opcoes.get("top_k", 20),
             "repeat_penalty": opcoes.get("repeat_penalty", 1.05), "chat_template_kwargs": {"enable_thinking": bool(corpo.get("think", False))}}
    if opcoes.get("num_predict"):
        saida["max_tokens"] = int(opcoes["num_predict"])
    if corpo.get("tools"):
        saida["tools"] = corpo["tools"]
    if corpo.get("logprobs") and not (corpo.get("tools") and saida["stream"]):
        saida["logprobs"] = True   # shortcut: o llama-server recusa logprobs com ferramentas em streaming; aí a conferência de confiança fica sem sinal
    if corpo.get("format") == "json":
        saida["response_format"] = {"type": "json_object"}
    elif isinstance(corpo.get("format"), dict):
        saida["response_format"] = {"type": "json_schema", "json_schema": {"schema": corpo["format"]}}
    return saida


def _chamadas_ollama(chamadas):
    saida = []
    for chamada in chamadas:
        f = chamada.get("function", {})
        argumentos = f.get("arguments")
        try:
            argumentos = json.loads(argumentos) if isinstance(argumentos, str) else argumentos
        except ValueError:
            argumentos = {}
        saida.append({"function": {"name": f.get("name"), "arguments": argumentos or {}}})
    return saida


def _final(nome, inicio, mensagem, motivo, logprobs=None):
    saida = {"model": nome, "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "message": mensagem, "done": True,
             "done_reason": "length" if motivo == "length" else "stop", "total_duration": int((time.time() - inicio) * 1e9)}
    if logprobs:
        saida["logprobs"] = logprobs
    return saida


def _tem_imagem(corpo):
    return any(m.get("images") for m in corpo.get("messages", []))


# ---------------------------------------------------------------- o servidor com cara de Ollama

def _do_ollama(caminho):
    """Os modelos do Ollama da pessoa, menos os que o motor já tem (ele serve esses). Lista vazia se não há Ollama."""
    try:
        with urllib.request.urlopen(OLLAMA + caminho, timeout=1.5) as r:
            return [m for m in json.loads(r.read()).get("models", []) if not instalado(m.get("name"))]
    except (OSError, ValueError):
        return []


def _ficha_tags(nome):
    ficha = CATALOGO[nome]
    caminho = pasta_modelos() / ficha["gguf"][0]
    tamanho = ficha["gguf"][2] + (ficha["mmproj"][2] if ficha.get("mmproj") else 0)
    detalhes = {"parent_model": ficha["gguf"][0], "format": "gguf", "family": ficha["family"], "families": [ficha["family"]],
                "parameter_size": ficha["parameter_size"], "quantization_level": ficha["quantization_level"]}
    modificado = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(caminho.stat().st_mtime)) if caminho.exists() else ""
    return {"name": nome, "model": nome, "modified_at": modificado, "size": tamanho, "digest": ficha["gguf"][1], "details": detalhes,
            "capabilities": ficha["capabilities"]}


def servir():
    motor = Motor()
    pasta().mkdir(parents=True, exist_ok=True)

    class Pedido(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _json(self, dados, codigo=200):
            corpo = json.dumps(dados, ensure_ascii=False).encode()
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def _linhas(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()

        def _linha(self, dados):
            texto = (json.dumps(dados, ensure_ascii=False) + "\n").encode()
            self.wfile.write(f"{len(texto):x}\r\n".encode() + texto + b"\r\n")
            self.wfile.flush()

        def _fim_linhas(self):
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()

        def do_GET(self):
            motor.ultimo_pedido = time.time()
            if self.path == "/api/version":
                return self._json({"version": "0.40.6"})
            if self.path == "/api/tags":
                return self._json({"models": [_ficha_tags(n) for n in instalados()] + _do_ollama("/api/tags")})
            if self.path == "/api/ps":
                with motor.trava:
                    vivos = {c[0] for c in motor.instancias}
                return self._json({"models": [dict(_ficha_tags(n), size_vram=0, expires_at="") for n in vivos] + _do_ollama("/api/ps")})
            if self.path in ("/", "/api"):
                return self._json({"status": "openTARS motor (llama.cpp)"})
            self._json({"error": "not found"}, 404)

        def do_HEAD(self):
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _repassar(self, corpo):
            """Pedido de um modelo de fora do catálogo: vai igual para o Ollama da pessoa, e a resposta volta pedaço por pedaço."""
            pedido = urllib.request.Request(OLLAMA + self.path, json.dumps(corpo).encode(), {"Content-Type": "application/json"}, method=self.command)
            try:
                r = urllib.request.urlopen(pedido, timeout=900)
            except urllib.error.HTTPError as e:
                r = e
            except OSError:
                return self._json({"error": f"model '{corpo.get('model') or corpo.get('name')}' not found"}, 404)
            with r:
                self.send_response(r.status)
                self.send_header("Content-Type", r.headers.get("Content-Type") or "application/json")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                for bloco in iter(lambda: r.read1(1 << 16), b""):
                    self.wfile.write(f"{len(bloco):x}\r\n".encode() + bloco + b"\r\n")
                    self.wfile.flush()
                self._fim_linhas()

        def do_DELETE(self):
            corpo = self._corpo()
            nome = _nome(corpo.get("model") or corpo.get("name"))
            if nome not in CATALOGO:
                return self._repassar(corpo)
            motor.descarregar(nome)
            ficha = CATALOGO[nome]
            for arquivo in [ficha["gguf"]] + ([ficha["mmproj"]] if ficha.get("mmproj") else []):
                (pasta_modelos() / arquivo[0]).unlink(missing_ok=True)
            self._json({})

        def _corpo(self):
            tamanho = int(self.headers.get("Content-Length") or 0)
            try:
                return json.loads(self.rfile.read(tamanho) or b"{}")
            except ValueError:
                return {}

        def do_POST(self):
            motor.ultimo_pedido = time.time()
            corpo = self._corpo()
            nome = _nome(corpo.get("model") or corpo.get("name"))
            if nome not in CATALOGO or (self.path != "/api/pull" and not instalado(nome) and self.path != "/api/delete"):
                return self._repassar(corpo)
            if self.path == "/api/show":
                if nome not in CATALOGO or not instalado(nome):
                    return self._json({"error": f"model '{nome}' not found"}, 404)
                ficha = _ficha_tags(nome)
                return self._json({"capabilities": ficha["capabilities"], "details": ficha["details"], "parameters": CATALOGO[nome]["parameters"],
                                   "modelfile": "", "template": "", "model_info": {"general.architecture": CATALOGO[nome]["family"]}})
            if self.path == "/api/pull":
                return self._puxar(nome, corpo.get("stream", True))
            if self.path == "/api/delete":
                return self.do_DELETE()
            if self.path == "/api/generate":
                return self._gerar(nome, corpo)
            if self.path == "/api/chat":
                return self._conversar(nome, corpo)
            self._json({"error": "not found"}, 404)

        def _gerar(self, nome, corpo):
            ka = _keep_alive(corpo.get("keep_alive"))
            if nome not in CATALOGO or not instalado(nome):
                return self._json({"error": f"model '{nome}' not found"}, 404)
            if not corpo.get("prompt"):
                if ka == 0:
                    motor.descarregar(nome)
                    return self._json({"model": nome, "response": "", "done": True, "done_reason": "unload"})
                try:
                    motor.instancia(nome).keep_alive = ka          # carregar na memória e deixar quente
                except (RuntimeError, KeyError) as e:
                    return self._json({"error": str(e)}, 500)
                return self._json({"model": nome, "response": "", "done": True, "done_reason": "load"})
            chat = {"messages": [{"role": "user", "content": corpo["prompt"], **({"images": corpo["images"]} if corpo.get("images") else {})}],
                    "stream": False, "options": corpo.get("options"), "think": corpo.get("think", False), "keep_alive": corpo.get("keep_alive")}
            if corpo.get("system"):
                chat["messages"].insert(0, {"role": "system", "content": corpo["system"]})
            resposta = self._responder(nome, chat)
            if "error" in resposta:
                return self._json(resposta, 500)
            return self._json({"model": nome, "response": resposta["message"]["content"], "done": True, "done_reason": resposta["done_reason"]})

        def _responder(self, nome, corpo):
            """Pedido sem streaming: o último pedaço do /api/chat."""
            inicio = time.time()
            try:
                inst = motor.instancia(nome, _tem_imagem(corpo))
                inst.keep_alive = _keep_alive(corpo.get("keep_alive"))
                pedido = dict(para_openai(corpo, nome), stream=False)
                with _pedir(f"http://127.0.0.1:{inst.porta}/v1/chat/completions", pedido) as r:
                    dados = json.loads(r.read())
                inst.ultimo = time.time()
            except urllib.error.HTTPError as e:
                return {"error": e.read().decode("utf-8", "replace")[:300]}
            except (OSError, RuntimeError, KeyError, ValueError) as e:
                return {"error": str(e)}
            escolha = dados["choices"][0]
            m = escolha["message"]
            mensagem = {"role": "assistant", "content": m.get("content") or ""}
            if m.get("reasoning_content"):
                mensagem["thinking"] = m["reasoning_content"]
            if m.get("tool_calls"):
                mensagem["tool_calls"] = _chamadas_ollama(m["tool_calls"])
            logprobs = [{"token": x.get("token"), "logprob": x.get("logprob")} for x in (escolha.get("logprobs") or {}).get("content") or []]
            return _final(nome, inicio, mensagem, escolha.get("finish_reason"), logprobs or None)

        def _conversar(self, nome, corpo):
            if nome not in CATALOGO or not instalado(nome):
                return self._json({"error": f"model '{nome}' not found"}, 404)
            if not corpo.get("stream", True):
                resposta = self._responder(nome, corpo)
                return self._json(resposta, 500 if "error" in resposta else 200)
            inicio = time.time()
            try:
                inst = motor.instancia(nome, _tem_imagem(corpo))
                inst.keep_alive = _keep_alive(corpo.get("keep_alive"))
                r = _pedir(f"http://127.0.0.1:{inst.porta}/v1/chat/completions", dict(para_openai(corpo, nome), stream=True))
            except urllib.error.HTTPError as e:
                return self._json({"error": e.read().decode("utf-8", "replace")[:300]}, 500)
            except (OSError, RuntimeError, KeyError) as e:
                return self._json({"error": str(e)}, 500)
            self._linhas()
            chamadas, motivo, logprobs = {}, "stop", []
            with r:
                for bruta in r:
                    linha = bruta.decode("utf-8", "replace").strip()
                    if not linha.startswith("data:"):
                        continue
                    dado = linha[5:].strip()
                    if dado == "[DONE]":
                        break
                    try:
                        pedaco = json.loads(dado)
                    except ValueError:
                        continue
                    for escolha in pedaco.get("choices") or []:
                        delta = escolha.get("delta") or {}
                        motivo = escolha.get("finish_reason") or motivo
                        for c in delta.get("tool_calls") or []:       # as chamadas chegam em pedaços: junta pelo índice
                            atual = chamadas.setdefault(c.get("index", 0), {"function": {"name": "", "arguments": ""}})
                            f = c.get("function") or {}
                            atual["function"]["name"] += f.get("name") or ""
                            atual["function"]["arguments"] += f.get("arguments") or ""
                        logprobs += [{"token": x.get("token"), "logprob": x.get("logprob")} for x in (escolha.get("logprobs") or {}).get("content") or []]
                        texto = delta.get("content") or ""
                        pensado = delta.get("reasoning_content") or ""
                        if texto or pensado:
                            mensagem = {"role": "assistant", "content": texto}
                            if pensado:
                                mensagem["thinking"] = pensado
                            self._linha({"model": nome, "message": mensagem, "done": False})
            inst.ultimo = time.time()
            final = {"role": "assistant", "content": ""}
            if chamadas:
                final["tool_calls"] = _chamadas_ollama([chamadas[i] for i in sorted(chamadas)])
            self._linha(_final(nome, inicio, final, motivo, logprobs or None))
            self._fim_linhas()

        def _puxar(self, nome, stream):
            if nome not in CATALOGO:
                return self._json({"error": f"pull model manifest: file does not exist ({nome})"}, 404)
            ficha = CATALOGO[nome]
            arquivos = [ficha["gguf"]] + ([ficha["mmproj"]] if ficha.get("mmproj") else [])
            if stream:
                self._linhas()
            avisar = (lambda d: self._linha(d)) if stream else (lambda d: None)
            try:
                avisar({"status": "pulling manifest"})
                if binario() is None:
                    avisar({"status": "downloading llama.cpp"})
                    instalar_binario(lambda f, t: None)
                for arquivo, sha, tamanho in arquivos:
                    destino = pasta_modelos() / arquivo
                    if destino.exists():
                        avisar({"status": f"pulling {sha[:12]}", "digest": f"sha256:{sha}", "total": tamanho, "completed": tamanho})
                        continue
                    ultimo = [0.0]

                    def progresso(feito, total, sha=sha, tamanho=tamanho):
                        if time.time() - ultimo[0] > 0.5 or feito >= (total or tamanho):
                            ultimo[0] = time.time()
                            avisar({"status": f"pulling {sha[:12]}", "digest": f"sha256:{sha}", "total": total or tamanho, "completed": feito})
                    obter_arquivo(ficha["repo"], arquivo, sha, progresso)
                avisar({"status": "verifying sha256 digest"})
                avisar({"status": "success"})
            except (OSError, ValueError) as e:
                if stream:
                    avisar({"error": str(e)})
                else:
                    return self._json({"error": str(e)}, 500)
            if stream:
                self._fim_linhas()
            else:
                self._json({"status": "success"})

    servidor = ThreadingHTTPServer(("127.0.0.1", PORTA), Pedido)
    servidor.daemon_threads = True
    print(f"motor escutando em {URL}", file=sys.stderr, flush=True)

    def vigiar():
        while True:
            time.sleep(15)
            motor.faxina()
    threading.Thread(target=vigiar, daemon=True).start()
    try:
        servidor.serve_forever()
    finally:
        motor.parar_tudo()


# ---------------------------------------------------------------- o lado do app

def respondendo(tempo=1.0):
    try:
        with urllib.request.urlopen(f"{URL}/api/version", timeout=tempo) as r:
            return r.status == 200
    except (OSError, ValueError):
        return False


def garantir(espera=15):
    """Deixa o motor de pé (sobe em segundo plano se não estiver) e devolve o endereço, ou None se não deu."""
    if respondendo():
        return URL
    if binario() is None:        # sem modelo também sobe: o primeiro uso baixa os modelos pelo /api/pull dele
        return None
    extra = {"creationflags": 0x08000000 | 0x00000200} if plataforma.sistema() == "windows" else {"start_new_session": True}
    pasta().mkdir(parents=True, exist_ok=True)
    with open(pasta() / "motor.log", "ab") as registro:
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--servir"], stdin=subprocess.DEVNULL, stdout=registro, stderr=registro,
                         cwd=str(Path(__file__).resolve().parent), **extra)
    limite = time.time() + espera
    while time.time() < limite:
        if respondendo(0.5):
            return URL
        time.sleep(0.2)
    return None


if __name__ == "__main__":
    if "--servir" in sys.argv:
        if os.environ.get("TARS_MOTOR_DEPURAR"):          # o CI do macOS: se travar, a pilha vai para o motor.log
            import faulthandler
            faulthandler.dump_traceback_later(20, exit=False)
        servir()
    elif "--instalar" in sys.argv:          # baixa o llama-server e os modelos pedidos (ou o 2B e o Lite)
        nomes = [a for a in sys.argv[2:] if not a.startswith("-")] or ["ProjectOpenTARS/Gargantua-2:lite", "ProjectOpenTARS/Gargantua-2:latest"]
        preparar(nomes)
        print("pronto:", instalados())
