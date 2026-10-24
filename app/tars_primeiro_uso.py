#!/usr/bin/env python3
"""
openTARS 5.0 Tesseract: a lógica do primeiro uso, sem janela nenhuma.

O assistente (tars_qt/primeiro_uso.py) só desenha e chama estas funções.
Tudo aqui é biblioteca padrão, então dá pra testar sem tela e sem Ollama
(os testes sobem um Ollama de mentira).

Passos: idioma, modo (5.1: Lite, Base ou Pro), Ollama, nuvem (opcional), Gargantua, teste rápido.

Arquivos (em ~/.config/opentars/):
    primeiro_uso.json   {"concluido": true, "quando": ...}
    nuvem.json          {"ativa": false, "provedor": ..., "endereco": ..., "chave": ...}
                        (permissão 0600; a chave nunca é registrada em log)
"""

import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import tars_plataforma as plataforma

MODELO_GARGANTUA = os.environ.get("TARS_MODELO_GARGANTUA", "ProjectOpenTARS/Gargantua-2")   # 18/10: o Gargantua 2 (Qwen3.5 2B, com visão)
REPOSITORIO_ANTIGO = "ProjectOpenTARS/Gargantua"           # o Gargantua 1.x (Qwen3 4B), que quem já tem continua usando
TAMANHO_GARGANTUA_GB = 1.7          # 1,6 GB (modelo + visão); só pra checar o espaço em disco antes de baixar
# 5.1: em máquina fraca o primeiro uso e o instalador baixam o Gargantua Lite (Qwen3 1,7B). TARS_GARGANTUA=lite|completo força.
# 17/10: o Lite novo é o Qwen3.5 0.8B com visão (0,62 GB). Etiqueta própria: os apps 5.1 antigos pedem ":lite" e não têm o
# think=false do Qwen3.5, então o ":lite" continua sendo o Qwen3 1.7B para eles.
MODELO_GARGANTUA_LITE = MODELO_GARGANTUA + ":lite"            # 0,8B com visão, 0,62 GB, roda só na CPU (Gargantua-2:lite)
TAMANHO_GARGANTUA_LITE_GB = 0.7
PORTA_OLLAMA = 11434

PASSOS = ("idioma", "modo", "ollama", "nuvem", "gargantua", "teste")


# ------------------------------------------------------------
# Onde as coisas ficam
# ------------------------------------------------------------

def pasta_config():
    return plataforma.pastas()["config"]


def arquivo_estado():
    return Path(os.environ.get("TARS_ARQUIVO_PRIMEIRO_USO") or pasta_config() / "primeiro_uso.json")


def arquivo_nuvem():
    return Path(os.environ.get("TARS_ARQUIVO_NUVEM") or pasta_config() / "nuvem.json")


def _ler_json(caminho, padrao):
    try:
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
        return dados if isinstance(dados, type(padrao)) else padrao
    except (OSError, ValueError):
        return padrao


def _gravar_json(caminho, dados, modo=0o600):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_name(caminho.name + ".tmp")
    # O arquivo nasce já com a permissão certa: a chave não fica legível nem por um instante.
    fd = os.open(str(temporario), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, modo)
    if hasattr(os, "fchmod"):    # o Windows não tem (lá o arquivo já fica na pasta do usuário); sem isto o Continuar morria
        os.fchmod(fd, modo)      # se já havia um .tmp antigo (0644), o modo do os.open é ignorado: força aqui
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    os.replace(temporario, caminho)


def primeiro_uso_concluido():
    return bool(_ler_json(arquivo_estado(), {}).get("concluido"))


def marcar_concluido(valor=True):
    _gravar_json(arquivo_estado(), {"concluido": bool(valor), "quando": int(time.time())}, 0o644)


# ------------------------------------------------------------
# Ollama
# ------------------------------------------------------------

def normalizar_host(valor):
    """OLLAMA_HOST do mesmo jeito que o próprio Ollama: 'host', 'host:porta'
    ou URL completa; sem nada, o endereço local padrão."""
    valor = (valor or "").strip().rstrip("/")
    if not valor:
        return f"http://127.0.0.1:{PORTA_OLLAMA}"
    if "://" not in valor:
        valor = "http://" + valor
    sem_esquema = valor.split("://", 1)[1]
    if ":" not in sem_esquema:
        valor += f":{PORTA_OLLAMA}"
    return valor.replace("://0.0.0.0", "://127.0.0.1")


def endereco_ollama():
    return normalizar_host(os.environ.get("OLLAMA_HOST"))


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None        # o urllib repassa o cabeçalho Authorization ao endereço do redirecionamento: não segue


def _obter(url, timeout=3, cabecalhos=None):
    pedido = urllib.request.Request(url, headers=cabecalhos or {})
    abrir = urllib.request.build_opener(_SemRedirecionar).open if "Authorization" in (cabecalhos or {}) \
        else urllib.request.urlopen          # com chave: nunca segue redirecionamento (a chave iria junto)
    with abrir(pedido, timeout=timeout) as r:
        return r.status, r.read()


def versao_ollama(host, timeout=2):
    """A versão, se o servidor responde; senão None."""
    try:
        status, corpo = _obter(f"{host}/api/version", timeout)
        return str(json.loads(corpo).get("version") or "?") if status == 200 else None
    except Exception:
        return None


def candidatos_de_host():
    """O endereço configurado primeiro; no WSL2, também o Ollama do Windows."""
    achados = [endereco_ollama()]
    try:
        import tars_ambiente
        if tars_ambiente.e_wsl() and not os.environ.get("OLLAMA_HOST"):
            achados += [c for c in tars_ambiente.candidatos_ollama_wsl() if c not in achados]
    except Exception:
        pass
    return achados


def achar_ollama(candidatos=None, tem_comando=None):
    """{'instalado': bool, 'responde': bool, 'host': url, 'versao': str|None}.
    'instalado' vale também pra um Ollama que responde mas não tem o comando
    (Docker, Windows via WSL...): instalar outro por cima brigaria pela porta."""
    tem_comando = shutil.which("ollama") is not None if tem_comando is None else tem_comando
    primeiro = None
    for host in (candidatos or candidatos_de_host()):
        primeiro = primeiro or host
        versao = versao_ollama(host)
        if versao:
            return {"instalado": True, "responde": True, "host": host, "versao": versao}
    return {"instalado": bool(tem_comando), "responde": False, "host": primeiro or endereco_ollama(), "versao": None}


def comando_instalar_ollama():
    """O instalador oficial. Pede a senha por uma janela do sistema (pkexec)
    quando existe; sem ele, roda direto (quem é root, ou já tem sudo sem senha)."""
    receita = "curl -fsSL https://ollama.com/install.sh | sh"
    if os.geteuid() != 0 and shutil.which("pkexec"):
        return ["pkexec", "sh", "-c", receita]
    return ["sh", "-c", receita]


def instalar_ollama(rodar=None):
    """(ok, mensagem). `rodar` existe pros testes; no uso normal executa o instalador."""
    if plataforma.sistema() != "linux":      # no Windows e no macOS quem instala o Ollama é o instalador do openTARS
        return False, "https://ollama.com/download"
    rodar = rodar or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True, timeout=1800))
    try:
        r = rodar(comando_instalar_ollama())
    except Exception as e:
        return False, str(e)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or f"código {r.returncode}").strip()[-400:]
    return True, ""


def iniciar_ollama(esperar=12, procurar=None):
    """Instalado mas parado: sobe o servidor e espera ele responder. (ok, mensagem)"""
    procurar = procurar or (lambda: achar_ollama(tem_comando=True)["responde"])
    if procurar():
        return True, ""
    so = plataforma.sistema()
    app_windows = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Programs" / "Ollama" / "ollama app.exe"
    # no Windows e no macOS o Ollama é um app de bandeja/barra de menus: abrir o app sobe o servidor do jeito dele
    if so == "windows" and app_windows.exists():
        comando = [str(app_windows)]
    elif so == "macos" and Path("/Applications/Ollama.app").exists():
        comando = ["open", "-a", "Ollama"]
    elif shutil.which("ollama"):
        comando = ["ollama", "serve"]
    else:
        return False, "ollama: comando não encontrado"
    try:
        subprocess.Popen(comando, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError as e:
        return False, str(e)
    limite = time.time() + esperar
    while time.time() < limite:
        if procurar():
            return True, ""
        time.sleep(0.5)
    return False, "o servidor não respondeu"


def modelos_instalados(host):
    try:
        _, corpo = _obter(f"{host}/api/tags", 4)
        return [str(m.get("name") or m.get("model") or "") for m in json.loads(corpo).get("models", [])]
    except Exception:
        return []


def _sem_tag(nome):
    return nome.lower().split(":")[0]


def e_gargantua_2(modelo):
    return str(modelo or "").strip().lower().partition(":")[0].split("/")[-1].startswith("gargantua-2")


def e_variante_do_gargantua(modelo):
    """'ProjectOpenTARS/Gargantua:code', 'gargantua-lite'... são variantes: não valem como o Gargantua oficial.
    (A mesma regra de nucleo/gargantua.py: variante_do_gargantua. "Gargantua-2" é o 2B; "Gargantua-2:lite" é o 0,8B.)"""
    base, _, tag = str(modelo or "").strip().lower().partition(":")
    segmento = base.split("/")[-1]
    partes = re.split(r"[-_. ]", segmento[len("gargantua"):] if segmento.startswith("gargantua") else segmento)
    return any(parte in ("lite", "code") for parte in partes + re.split(r"[-_. ]", tag))


def tem_gargantua(modelos):
    """Algum Gargantua oficial instalado: o 2 ou o 1.x (quem já tem o antigo não é obrigado a baixar o novo)."""
    return any(_sem_tag(m) in (_sem_tag(MODELO_GARGANTUA), _sem_tag(REPOSITORIO_ANTIGO)) and not e_variante_do_gargantua(m)
               for m in modelos)


def tem_gargantua_2(modelos):
    return any(e_gargantua_2(m) and not e_variante_do_gargantua(m) for m in modelos)    # o :lite (0,8B) não conta


def _e_lite(modelo):
    base, _, tag = str(modelo or "").strip().lower().partition(":")
    segmento = base.split("/")[-1]
    if not segmento.startswith("gargantua"):
        return False
    return "lite" in re.split(r"[-_. ]", segmento[len("gargantua"):]) + re.split(r"[-_. ]", tag)


_VRAM = {}


def _vram_mb():
    """Guardado na primeira vez: o nvidia-smi leva segundos em alguns notebooks e a janela do primeiro uso pergunta várias
    vezes (no Windows, cada chamada na tela travava a janela)."""
    if "mb" not in _VRAM:
        try:
            r = subprocess.run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                               capture_output=True, text=True, timeout=5)
            _VRAM["mb"] = max((int(float(x)) for x in r.stdout.split()), default=0) if r.returncode == 0 else 0
        except (OSError, ValueError, subprocess.SubprocessError):
            _VRAM["mb"] = 0
    return _VRAM["mb"]


def _ram_mb():
    try:
        import psutil
        return psutil.virtual_memory().total // 2**20
    except (ImportError, OSError):
        pass
    return 1 << 20          # sem saber: trata como máquina boa (baixa o completo, como antes)


def maquina_fraca(vram_mb=None, ram_mb=None, threads=None):
    """Decisão de 09/10: sem placa de vídeo com pelo menos 4 GB E (até 6 GB de RAM OU menos de 4 threads).
    Qualquer outra máquina fica com o 4B, mesmo lenta."""
    escolha = (os.environ.get("TARS_GARGANTUA") or "").strip().lower()
    if escolha in ("lite", "completo"):
        return escolha == "lite"
    if (_vram_mb() if vram_mb is None else vram_mb) >= 4000:
        return False
    ram = _ram_mb() if ram_mb is None else ram_mb
    threads = (os.cpu_count() or 4) if threads is None else threads
    return ram <= 6200 or threads < 4


def gargantua_desta_maquina():
    """O que o primeiro uso baixa aqui: o Gargantua Lite em máquina fraca, o oficial nas outras."""
    return MODELO_GARGANTUA_LITE if maquina_fraca() else MODELO_GARGANTUA


def tamanho_gargantua_gb():
    return TAMANHO_GARGANTUA_LITE_GB if maquina_fraca() else TAMANHO_GARGANTUA_GB


def tem_gargantua_desta_maquina(modelos):
    """O oficial sempre serve; o Lite só conta onde ele é o escolhido (máquina fraca)."""
    return tem_gargantua(modelos) or (maquina_fraca() and any(_e_lite(m) for m in modelos))


def nome_do_gargantua(modelos):
    """O nome exato como o Ollama o conhece (com a tag), ou o padrão. O Gargantua 2 vai na frente do 1.x."""
    for repositorio in (MODELO_GARGANTUA, REPOSITORIO_ANTIGO):
        for m in modelos:
            if _sem_tag(m) == _sem_tag(repositorio) and not e_variante_do_gargantua(m):
                return m
    if maquina_fraca():                    # 5.1: na máquina fraca o Lite é o Gargantua
        return next((m for m in modelos if _e_lite(m)), MODELO_GARGANTUA_LITE)
    return MODELO_GARGANTUA


def espaco_livre_gb(caminho=None):
    """Espaço livre onde o Ollama guarda os modelos (ou no que existir mais perto)."""
    alvo = Path(caminho or os.environ.get("OLLAMA_MODELS") or Path.home() / ".ollama")
    while not alvo.exists() and alvo != alvo.parent:
        alvo = alvo.parent
    try:
        return shutil.disk_usage(alvo).free / 1e9
    except OSError:
        return None


# ------------------------------------------------------------
# Baixar o Gargantua (POST /api/pull, um JSON por linha)
# ------------------------------------------------------------

class Progresso:
    """Junta as camadas do download numa conta só: feito/total em bytes."""

    def __init__(self):
        self.camadas = {}          # digest -> [feito, total]
        self.status = ""
        self.inicio = time.time()
        self.amostras = []         # (instante, bytes feitos), pra estimar a velocidade

    def atualizar(self, linha):
        self.status = str(linha.get("status") or self.status)
        digest, total = linha.get("digest"), linha.get("total")
        if digest and total:
            self.camadas[digest] = [int(linha.get("completed") or 0), int(total)]
        agora = time.time()
        self.amostras.append((agora, self.feito))
        self.amostras = [a for a in self.amostras if agora - a[0] <= 20]

    @property
    def feito(self):
        return sum(c[0] for c in self.camadas.values())

    @property
    def total(self):
        return sum(c[1] for c in self.camadas.values())

    @property
    def fracao(self):
        return min(1.0, self.feito / self.total) if self.total else 0.0

    def segundos_restantes(self):
        """Pela velocidade dos últimos 20 s; None enquanto não dá pra estimar."""
        if len(self.amostras) < 2 or not self.total:
            return None
        (t0, b0), (t1, b1) = self.amostras[0], self.amostras[-1]
        if t1 - t0 < 2 or b1 <= b0:
            return None
        return (self.total - self.feito) / ((b1 - b0) / (t1 - t0))


def baixar_modelo(nome, host, ao_progredir=None, cancelado=None, abrir=None):
    """Baixa `nome`. Chama ao_progredir(Progresso) a cada linha. Devolve
    (ok, erro). Se cancelado() virar True, para e devolve (False, 'cancelado');
    baixar de novo retoma de onde parou (o Ollama guarda as camadas prontas)."""
    progresso = Progresso()
    corpo = json.dumps({"model": nome, "stream": True}).encode()
    pedido = urllib.request.Request(f"{host}/api/pull", data=corpo, headers={"Content-Type": "application/json"})
    try:
        with (abrir or urllib.request.urlopen)(pedido, timeout=60) as r:
            for linha in r:
                if cancelado and cancelado():
                    return False, "cancelado"
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    dados = json.loads(linha)
                except ValueError:
                    continue
                if dados.get("error"):
                    return False, _explicar_erro_de_download(str(dados["error"]))
                progresso.atualizar(dados)
                if ao_progredir:
                    ao_progredir(progresso)
                if dados.get("status") == "success":
                    return True, ""
    except urllib.error.HTTPError as e:
        try:
            detalhe = json.loads(e.read()).get("error", "")
        except Exception:  # noqa: BLE001
            detalhe = ""
        return False, _explicar_erro_de_download(detalhe or f"HTTP {e.code}", e.code)
    except Exception as e:
        return False, str(e)
    return False, "o download terminou sem confirmar"


def _explicar_erro_de_download(erro, codigo=None):
    """O Gargantua Lite em Qwen3.5 (17/10) precisa de um Ollama recente; o antigo responde 412 / "requires a newer version
    of Ollama". Em vez do erro cru, diz o que fazer."""
    if codigo == 412 or "newer version" in erro.lower():
        try:
            from tars_i18n import t
            return t("pu.ollama_antigo")
        except Exception:  # noqa: BLE001
            return "Atualize o Ollama: curl -fsSL https://ollama.com/install.sh | sh"
    return erro


# ------------------------------------------------------------
# Teste rápido
# ------------------------------------------------------------

# ------------------------------------------------------------
# 5.1: nuvem pelo login do Ollama (sem chave de API). A credencial fica com o próprio Ollama; o openTARS não guarda nada.
# ------------------------------------------------------------

MODELO_NUVEM_PADRAO = "gpt-oss:20b-cloud"      # baixar é só o manifesto (poucos KB); roda nos servidores do Ollama
_RE_URL_LOGIN = re.compile(r"https://ollama\.com/\S+")
_RE_NUVEM = re.compile(r"(^|[-:])cloud($|[-:])", re.IGNORECASE)


def conta_ollama(host, abrir=None, timeout=4):
    """O nome da conta do ollama.com em que este Ollama entrou (POST /api/me), ou None. Só o nome: o e-mail fica fora."""
    pedido = urllib.request.Request(f"{host}/api/me", data=b"{}", method="POST", headers={"Content-Type": "application/json"})
    try:
        with (abrir or urllib.request.urlopen)(pedido, timeout=timeout) as r:
            dados = json.loads(r.read() or b"{}")
        return str(dados.get("name") or "").strip() or None if isinstance(dados, dict) else None
    except Exception:
        return None


def iniciar_login(rodar=None):
    """Roda `ollama signin`. Devolve (já entrou: nome ou None, endereço da página de login ou None, erro ou None).
    O Ollama imprime o endereço; a pessoa entra (ou cria a conta) no navegador, e conta_ollama passa a responder."""
    if not shutil.which("ollama") and rodar is None:
        return None, None, "sem_ollama"
    try:
        r = (rodar or subprocess.run)(["ollama", "signin"], capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as e:
        return None, None, str(e)
    saida = (r.stdout or "") + (r.stderr or "")
    ja = re.search(r"signed in as user '([^']+)'", saida)
    if ja:
        return ja.group(1), None, None
    url = _RE_URL_LOGIN.search(saida)
    return None, (url.group(0).rstrip(".,)") if url else None), (None if url else (saida.strip()[:200] or "sem_endereco"))


def sair_da_conta(rodar=None):
    try:
        r = (rodar or subprocess.run)(["ollama", "signout"], capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def e_modelo_de_nuvem(modelo):
    return bool(_RE_NUVEM.search(str(modelo or "")))


def modelos_de_nuvem(modelos):
    return [m for m in modelos if e_modelo_de_nuvem(m)]


def testar_gargantua(host, modelo, enviar=None):
    """Um pedido simples. (ok, texto da resposta ou o erro, segundos)."""
    corpo = json.dumps({
        "model": modelo, "stream": False, "think": False,
        "messages": [{"role": "user", "content": "Quanto é 2 + 2? Responda só com o número."}],
        "options": {"num_predict": 24, "temperature": 0},
    }).encode()
    pedido = urllib.request.Request(f"{host}/api/chat", data=corpo, headers={"Content-Type": "application/json"})
    inicio = time.time()
    try:
        with (enviar or urllib.request.urlopen)(pedido, timeout=180) as r:
            dados = json.loads(r.read())
    except Exception as e:
        return False, str(e), time.time() - inicio
    texto = str((dados.get("message") or {}).get("content") or "").strip()
    if dados.get("error"):
        return False, str(dados["error"]), time.time() - inicio
    return (bool(texto), texto or "resposta vazia", time.time() - inicio)


# ------------------------------------------------------------
# Nuvem (opcional): o usuário traz a própria chave
# ------------------------------------------------------------

# O endereço de cada provedor vem do próprio provedor; 'a_confirmar' marca os
# que a documentação oficial ainda precisa confirmar (as fontes divergiram).
PROVEDORES = (
    {"id": "ollama", "nome": "Ollama Cloud", "endereco": "https://ollama.com/v1", "a_confirmar": True},
    {"id": "groq", "nome": "Groq", "endereco": "https://api.groq.com/openai/v1", "a_confirmar": False},
    {"id": "cerebras", "nome": "Cerebras", "endereco": "https://api.cerebras.ai/v1", "a_confirmar": False},
    {"id": "outro", "nome": "Outro", "endereco": "", "a_confirmar": False},
)


def provedor(id_):
    return next((p for p in PROVEDORES if p["id"] == id_), PROVEDORES[-1])


def carregar_nuvem():
    padrao = {"ativa": False, "provedor": "", "endereco": "", "chave": ""}
    dados = _ler_json(arquivo_nuvem(), {})
    padrao.update({k: dados[k] for k in padrao if k in dados})
    padrao["ativa"] = bool(padrao["ativa"])
    return padrao


def salvar_nuvem(ativa, id_provedor="", endereco="", chave=""):
    """Desligar não apaga a chave que já estava salva; só marca como desligada."""
    atual = carregar_nuvem()
    if not ativa:
        atual["ativa"] = False
        _gravar_json(arquivo_nuvem(), atual)
        return atual
    atual.update({"ativa": True, "provedor": id_provedor, "endereco": endereco.strip().rstrip("/"), "chave": chave.strip()})
    _gravar_json(arquivo_nuvem(), atual)
    return atual


def testar_nuvem(endereco, chave, obter=None):
    """Confere o endereço e a chave listando os modelos. (ok, mensagem curta).
    O texto devolvido nunca contém a chave."""
    endereco = (endereco or "").strip().rstrip("/")
    if not endereco.startswith(("http://", "https://")):
        return False, "endereço"
    cabecalhos = {"Authorization": f"Bearer {chave.strip()}"} if chave.strip() else {}
    try:
        status, corpo = (obter or _obter)(f"{endereco}/models", 12, cabecalhos)
    except urllib.error.HTTPError as e:
        return False, {401: "chave", 403: "chave", 404: "endereço", 429: "limite"}.get(e.code, f"HTTP {e.code}")
    except Exception:
        return False, "rede"
    return (True, "ok") if status == 200 else (False, f"HTTP {status}")


def formatar_tempo(segundos, t):
    """'uns 3 minutos', 'menos de 1 minuto'... com `t` (a função de textos)."""
    if segundos is None:
        return t("pu.calculando")
    if segundos < 60:
        return t("pu.menos_de_um_minuto")
    minutos = int(round(segundos / 60))
    return t("pu.um_minuto") if minutos <= 1 else t("pu.uns_minutos", n=minutos)
