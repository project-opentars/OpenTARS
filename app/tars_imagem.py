"""5.2 (decisão do Enzo, 25/10): gerar imagem com o Bonsai Image 4B (PrismML, Apache 2.0), instalação OPCIONAL e com
confirmação (~9 GB: Python, CUDA e o modelo), sem sudo, em `<dados>/imagem/`. Sem Qt.

- instalar(): clona o programa de demonstração deles num commit fixo e roda o setup deles (que cria o venv, baixa as
  dependências e o modelo). shortcut: o setup deles clona dois repositórios auxiliares pelo ramo, não por commit; se um
  dia quebrar, fixar os commits num fork nosso.
- gerar(): um processo próprio (tars_imagem_trabalhador.py, com o Python do venv deles) mantém o modelo carregado e
  conversa por JSON numa linha; sem portas abertas (não usamos o servidor nem o Studio deles). Antes de gerar, descarrega
  os modelos do Ollama: na RTX 3050 de 6 GB os dois não cabem juntos (medido em 21/10). Depois de alguns minutos parado,
  o processo sai e a placa volta para o Ollama.

Medido em 21/10 no PC do Enzo (RTX 3050 6 GB, placa livre): carga ~32 s, 512 px ~5 s, 576 px ~6 s, 640 px não cabe."""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import tars_plataforma as plataforma

REPOSITORIO = "https://github.com/PrismML-Eng/Bonsai-Image-Demo.git"
COMMIT = "de1e5c0323e7a0474c68c6cdd075bad4e782fb0e"
TAMANHO_GB = 9.5                 # medido em 21/10: venv 5,0 + modelo 4,3 + vendor 0,2
LADO_PADRAO = 512                # o que cabe na placa de 6 GB; múltiplo de 32
OCIOSO_S = 300                   # o processo sai depois de 5 min sem pedido (a placa volta para o Ollama)


def pasta():
    return Path(os.environ.get("TARS_PASTA_IMAGEM") or plataforma.pastas()["dados"] / "imagem")


def demo():
    return pasta() / "demo"


def python_do_venv():
    venv = demo() / ".venv"
    return venv / ("Scripts/python.exe" if plataforma.sistema() == "windows" else "bin/python3")


def instalado():
    return python_do_venv().exists() and any((demo() / "models").glob("bonsai-image-4B-*"))


def pode_instalar(vram_mb=None, livre_gb=None):
    """(sim, motivo). Linux e Windows: placa NVIDIA com 6 GB; macOS: Apple Silicon. git e curl presentes; disco."""
    so = plataforma.sistema()
    if so == "macos":
        import platform
        if platform.machine() != "arm64":
            return False, "apple_silicon"
    else:
        if vram_mb is None:
            import tars_primeiro_uso as pu
            vram_mb = pu._vram_mb()
        if vram_mb < 5500:
            return False, "placa"
    for programa in ("git", "curl") if so != "windows" else ("git",):
        if not shutil.which(programa):
            return False, "falta:" + programa
    if livre_gb is None:
        try:
            alvo = pasta()
            while not alvo.exists():
                alvo = alvo.parent
            livre_gb = shutil.disk_usage(alvo).free / 1e9
        except OSError:
            livre_gb = None
    if livre_gb is not None and livre_gb < TAMANHO_GB * 1.2:
        return False, "disco"
    return True, ""


def instalar(ao_linha=None, rodar=None):
    """Clona no commit fixo e roda o setup deles, passando cada linha para `ao_linha`. (ok, erro)."""
    ao_linha = ao_linha or (lambda linha: None)
    rodar = rodar or _rodar
    pasta().mkdir(parents=True, exist_ok=True)
    if not (demo() / ".git").exists():
        ok = rodar(["git", "clone", "--quiet", REPOSITORIO, str(demo())], pasta(), ao_linha)
        if not ok:
            return False, "git clone"
    if not rodar(["git", "-C", str(demo()), "checkout", "--quiet", COMMIT], pasta(), ao_linha):
        return False, "git checkout"
    env = dict(os.environ, BONSAI_VARIANT="ternary")
    if plataforma.sistema() == "windows":
        comando = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(demo() / "setup.ps1")]
    else:
        comando = ["bash", str(demo() / "setup.sh")]
    if not rodar(comando, demo(), ao_linha, env):
        return False, "setup"
    return (True, "") if instalado() else (False, "modelo")


def _rodar(comando, cwd, ao_linha, env=None):
    proc = subprocess.Popen(comando, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, errors="replace")
    for linha in proc.stdout:
        ao_linha(re.sub(r"\x1b\[[0-9;]*m", "", linha.rstrip()))
    return proc.wait() == 0


def remover():
    parar()
    shutil.rmtree(pasta(), ignore_errors=True)


# ------------------------------------------------------------
# Gerar
# ------------------------------------------------------------
_TRABALHADOR = {"proc": None, "ultimo": 0.0}
_TRAVA = threading.Lock()


def descarregar_ollama(host, abrir=None):
    """Tira da placa os modelos que o Ollama tem carregados (keep_alive 0). Eles voltam sozinhos no próximo pedido."""
    import urllib.request
    abrir = abrir or urllib.request.urlopen
    try:
        with abrir(f"{host}/api/ps", timeout=5) as r:
            nomes = [m.get("name") for m in json.loads(r.read()).get("models", [])]
        for nome in nomes:
            pedido = urllib.request.Request(f"{host}/api/generate", data=json.dumps({"model": nome, "keep_alive": 0}).encode(),
                                            headers={"Content-Type": "application/json"})
            with abrir(pedido, timeout=30):
                pass
        return nomes
    except Exception:  # noqa: BLE001  (Ollama fora: nada a descarregar)
        return []


MEMORIA_MINIMA_MB = 5000          # medido em 21/10: pico de ~5,0 GB em 512 px


def memoria_livre_mb():
    """Memória livre da placa NVIDIA agora (None fora dela ou sem nvidia-smi)."""
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"], capture_output=True,
                           text=True, timeout=5)
        return max(int(float(x)) for x in r.stdout.split()) if r.returncode == 0 and r.stdout.strip() else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _trabalhador():
    proc = _TRABALHADOR["proc"]
    if proc is None or proc.poll() is not None:
        script = Path(__file__).resolve().parent / "tars_imagem_trabalhador.py"
        criacao = 0x08000000 if plataforma.sistema() == "windows" else 0            # CREATE_NO_WINDOW
        registro = open(pasta() / "trabalhador.log", "a", encoding="utf-8")       # a saída das bibliotecas, para diagnóstico
        proc = subprocess.Popen([str(python_do_venv()), str(script), str(demo())], cwd=str(demo()), stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=registro, text=True, creationflags=criacao)
        _TRABALHADOR["proc"] = proc
        threading.Thread(target=_vigiar_ocioso, args=(proc,), daemon=True).start()
    return proc


def _vigiar_ocioso(proc):
    while proc.poll() is None:
        time.sleep(15)
        if time.time() - _TRABALHADOR["ultimo"] > OCIOSO_S and not _TRAVA.locked():
            proc.terminate()


def parar():
    proc = _TRABALHADOR["proc"]
    if proc is not None and proc.poll() is None:
        proc.terminate()
    _TRABALHADOR["proc"] = None


def pasta_de_saida():
    """Imagens/openTARS (a pasta de imagens do sistema, em qualquer idioma)."""
    casa = Path.home()
    for nome in ("Pictures", "Imagens", "Imágenes", "Images", "Bilder"):
        if (casa / nome).is_dir():
            return casa / nome / "openTARS"
    return casa / "Pictures" / "openTARS"


def nome_do_arquivo(pedido):
    base = re.sub(r"[^a-z0-9]+", "-", pedido.lower().encode("ascii", "ignore").decode())[:40].strip("-") or "imagem"
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{base}.png"


def gerar(pedido, host=None, lado=LADO_PADRAO, semente=None, saida=None):
    """Gera uma imagem e devolve o caminho do PNG. Levanta RuntimeError com o motivo."""
    if not instalado():
        raise RuntimeError("nao_instalado")
    lado = max(256, min(1024, lado // 32 * 32))
    saida = Path(saida or pasta_de_saida() / nome_do_arquivo(pedido))
    saida.parent.mkdir(parents=True, exist_ok=True)
    with _TRAVA:
        if host:
            descarregar_ollama(host)
        livre = memoria_livre_mb() if _TRABALHADOR["proc"] is None or _TRABALHADOR["proc"].poll() is not None else None
        if livre is not None and livre < MEMORIA_MINIMA_MB:
            # 25/10: um jogo aberto (2,4 GB) já impedia o modelo de carregar; quem usa a placa não é o openTARS
            raise RuntimeError(f"sem_memoria:{livre}")
        proc = _trabalhador()
        _TRABALHADOR["ultimo"] = time.time()
        proc.stdin.write(json.dumps({"prompt": pedido, "lado": lado, "semente": semente, "saida": str(saida)}) + "\n")
        proc.stdin.flush()
        linha = proc.stdout.readline()
        _TRABALHADOR["ultimo"] = time.time()
    if not linha:
        parar()
        raise RuntimeError("o processo do Bonsai parou (memória da placa?)")
    resposta = json.loads(linha)
    if not resposta.get("ok"):
        raise RuntimeError(resposta.get("erro") or "erro")
    return saida


# "desenhe um gato", "gera uma imagem de um farol", "draw a fox", "generate an image of a lighthouse"
_PEDIDO = re.compile(
    r"^\s*(?:(?:por favor|please)[, ]+)?(?:"
    r"(?:desenh[ae]|desenhar|pinte|pinta|ilustr[ae])(?:\s+(?:pra|para) mim)?|"
    r"(?:ger[ae]|gerar|cri[ae]|criar|fa[cç]a|faz|fazer)\s+(?:uma |um )?(?:imagem|figura|ilustra[cç][aã]o|desenho|foto)(?:\s+(?:de|do|da|com))?|"
    r"(?:draw|paint|illustrate)|"
    r"(?:generate|create|make)\s+(?:an? )?(?:image|picture|illustration|drawing)(?:\s+of)?"
    r")\s+(?P<o_que>.+)$", re.IGNORECASE | re.DOTALL)


def pedido_de_imagem(texto):
    """O que desenhar, se o texto pede uma imagem nova ("desenhe um gato na praia" -> "um gato na praia"); senão None."""
    m = _PEDIDO.match(texto or "")
    if not m:
        return None
    o_que = m.group("o_que").strip().rstrip(".!")
    return o_que if len(o_que) >= 3 else None


if __name__ == "__main__":
    # opentars --imagem [--remover]: instala pelo terminal, com as linhas do setup na tela
    if "--remover" in sys.argv:
        remover()
        print("removido")
        sys.exit(0)
    sim, motivo = pode_instalar()
    if not sim:
        print("não dá para instalar aqui:", motivo)
        sys.exit(1)
    ok, erro = instalar(print)
    print("pronto" if ok else f"falhou: {erro}")
    sys.exit(0 if ok else 1)
