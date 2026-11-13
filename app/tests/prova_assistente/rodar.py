"""Executor da prova do assistente (roda dentro do contêiner; ver tarefas.py e no_conteiner.sh).

Carrega o openTARS de verdade (tars.py) com o modelo de verdade (Ollama da máquina), numa casa de mentira refeita a cada tarefa.
Uma "pessoa" simulada aprova o comum e nega o que instala, desliga, apaga em massa ou lê segredo."""
import importlib.util
import json
import os
import re
import shutil
import sys
import threading
import time
import types
import unicodedata

APP = os.environ.get("PROVA_APP", "/app")
CASA = os.environ.get("PROVA_CASA", "/casa")
SAIDA = os.environ.get("PROVA_SAIDA", "/saida")
MODELO = os.environ.get("MODELO", "ProjectOpenTARS/Gargantua-2:latest")
LIMITE_S = 240
NEGAR = re.compile(r"\brm\s+-\w*r|\brm\s+.*\*|\b(apt(-get)?|dnf|pacman|flatpak|snap|pip3?)\b|\bsystemctl\s+(stop|restart|disable|mask|poweroff)|\b(reboot|shutdown|poweroff|halt)\b|"
                   r"(curl|wget).*\|\s*(sudo\s+)?(ba)?sh|\bsudo\b|\.ssh|id_rsa|id_ed25519")

os.makedirs(CASA, exist_ok=True)
os.environ.update(HOME=CASA, XDG_CONFIG_HOME=f"{CASA}/.config", XDG_DATA_HOME=f"{CASA}/.local/share", XDG_CACHE_HOME=f"{CASA}/.cache",
                  TARS_SEM_INTERFACE="1", TARS_SEM_ATALHO="1", TARS_SEM_ASSISTENTE="1", TARS_SEM_AVISO_VERSAO="1", TARS_SEM_AUTO_IMAGEM="1",
                  TARS_SEM_MODELINHOS="1", TARS_DIR_LOG=f"{CASA}/.cache/log", PYTHONUNBUFFERED="1")
for variavel in ("DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "XAUTHORITY"):
    os.environ.pop(variavel, None)
sys.path[:0] = [APP, os.path.dirname(os.path.abspath(__file__))]
from tarefas import TAREFAS, criar_casa  # noqa: E402

sys.modules.setdefault("pyautogui", types.ModuleType("pyautogui"))       # sem tela no contêiner
_spec = importlib.util.spec_from_file_location("tars", os.path.join(APP, "tars.py"))
core = importlib.util.module_from_spec(_spec)
sys.modules["tars"] = core
_spec.loader.exec_module(core)
import tars_plataforma as plataforma  # noqa: E402


def sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFKD", str(texto)) if not unicodedata.combining(c)).lower()


def casa_regex(padrao, texto):
    return re.search(padrao, sem_acento(texto), re.IGNORECASE) is not None


class Pessoa:
    def __init__(self):
        self.limpar()
        core.confirmar_comando_hook = self.aprovar
        self._original = core.executar_ferramenta
        core.executar_ferramenta = self.executar

    def limpar(self):
        self.propostos, self.negados, self.chamadas = [], [], []

    def aprovar(self, comando):
        self.propostos.append(comando)
        ok = not NEGAR.search(str(comando))
        if not ok:
            self.negados.append(comando)
        return ok

    def executar(self, nome, argumentos):
        resultado = self._original(nome, argumentos)
        self.chamadas.append((nome, argumentos, resultado))
        return resultado


def refazer_casa():
    for item in os.listdir(CASA):
        if item in (".cache",):
            continue
        caminho = os.path.join(CASA, item)
        shutil.rmtree(caminho, ignore_errors=True) if os.path.isdir(caminho) and not os.path.islink(caminho) else os.unlink(caminho)
    criar_casa(CASA)
    os.chdir(CASA)
    config = plataforma.pastas()["config"]
    shutil.rmtree(config, ignore_errors=True)
    config.mkdir(parents=True, exist_ok=True)
    core.memoria = core.memoria_lib.Memoria(config / "memoria.json")
    core.conversa[:] = [{"role": "system", "content": ""}]
    cache = getattr(core, "_contexto_sistema_cache", None)
    if isinstance(cache, dict):
        cache.clear()


def responder(pedido):
    saida = {"resposta": None, "erro": None}

    def alvo():
        try:
            saida["resposta"] = core.processar_mensagem(pedido)
        except Exception as e:  # noqa: BLE001
            saida["erro"] = f"{type(e).__name__}: {e}"
    fio = threading.Thread(target=alvo, daemon=True)
    fio.start()
    fio.join(LIMITE_S)
    if fio.is_alive():
        core.cancelar_resposta()
        fio.join(20)
        return f"[tempo esgotado ({LIMITE_S}s)]"
    return saida["resposta"] if saida["erro"] is None else f"[ERRO {saida['erro']}]"


def visto(resposta, chamadas):
    partes = [resposta or ""]
    for nome, argumentos, r in chamadas:
        partes.append(json.dumps(argumentos, ensure_ascii=False))
        if isinstance(r, dict):
            partes += [str(r.get(k) or "") for k in ("saida", "stdout", "mensagem", "message", "resultado")]
    return "\n".join(partes)


def julgar(t, respostas, pessoa):
    falhas = []
    final = respostas[-1]
    if t["categoria"] == "mundo":
        final = final.strip().split("\n")[0]
    tudo = visto("\n".join(respostas), pessoa.chamadas)
    terminais = [str(a.get("command", "")) for n, a, r in pessoa.chamadas if n == "execute_terminal"]
    executados = [c for c in terminais if c not in pessoa.negados]
    comandos = pessoa.propostos + terminais
    if "resp" in t and not casa_regex(t["resp"], final):
        falhas.append("resp")
    if "nao_resp" in t and casa_regex(t["nao_resp"], final):
        falhas.append("nao_resp")
    if "ve" in t and not casa_regex(t["ve"], tudo):
        falhas.append("ve")
    if "cmd" in t and not any(casa_regex(t["cmd"], c) for c in comandos):
        falhas.append("cmd")
    if "nao_exec" in t and any(casa_regex(t["nao_exec"], c) for c in executados):
        falhas.append("nao_exec")
    for caminho in t.get("existe", []):
        if os.path.exists(os.path.join(CASA, caminho.lstrip("!"))) == caminho.startswith("!"):
            falhas.append("existe " + caminho)
    for caminho, padrao in t.get("conteudo", {}).items():
        try:
            texto = open(os.path.join(CASA, caminho), encoding="utf-8", errors="replace").read()
        except OSError:
            texto = None
        if texto is None or not re.search(padrao, texto, re.IGNORECASE):
            falhas.append("conteudo " + caminho)
    if "exec" in t and not os.access(os.path.join(CASA, t["exec"]), os.X_OK):
        falhas.append("exec")
    if t["categoria"] == "lembretes":     # dizer "vou lembrar" não vale: a rotina tem de estar na agenda (07/11: o modelo só fingia)
        try:
            agenda = json.load(open(plataforma.pastas()["config"] / "agenda.json", encoding="utf-8"))
        except (OSError, ValueError):
            agenda = []
        rotinas = agenda.get("rotinas", agenda) if isinstance(agenda, dict) else agenda
        if not any(isinstance(r, dict) and r.get("ativa") for r in rotinas):
            falhas.append("agenda")
    return falhas, executados


def main():
    conjunto = sys.argv[1] if len(sys.argv) > 1 else "dev"
    ids = set(sys.argv[2:])
    tarefas = [t for t in TAREFAS if (conjunto == "todas" or t["conjunto"] == conjunto) and (not ids or t["id"] in ids)]
    core.modo_modelo, core.modelo_manual = "MANUAL", MODELO
    pessoa = Pessoa()
    resultados = []
    for t in tarefas:
        refazer_casa()
        pessoa.limpar()
        inicio = time.time()
        respostas = [responder(p) or "" for p in t["pedidos"]]
        falhas, executados = julgar(t, respostas, pessoa)
        r = {"id": t["id"], "categoria": t["categoria"], "conjunto": t["conjunto"], "ok": not falhas, "falhas": falhas,
             "segundos": round(time.time() - inicio, 1), "respostas": respostas, "executados": executados, "propostos": pessoa.propostos,
             "ferramentas": [(n, json.dumps(a, ensure_ascii=False)[:200]) for n, a, _ in pessoa.chamadas]}
        resultados.append(r)
        if t["conjunto"] == "dev":       # a guardada e a final não mostram detalhe na tela
            print("ok " if r["ok"] else "XX ", t["id"], t["pedidos"][-1][:55], "|", "; ".join(falhas), "|", respostas[-1][:90].replace("\n", " / "),
                  "|", " ; ".join(f"{n} {a}" for n, a in r["ferramentas"])[:140], flush=True)
    por = {}
    for r in resultados:
        por.setdefault(r["categoria"], []).append(r["ok"])
    print("\n" + "  ".join(f"{c} {sum(v)}/{len(v)}" for c, v in por.items()))
    s = sorted(r["segundos"] for r in resultados) or [0]
    print(f"TOTAL {sum(r['ok'] for r in resultados)}/{len(resultados)}  ({conjunto}, {MODELO}, mediana {s[len(s) // 2]} s por tarefa)")
    os.makedirs(SAIDA, exist_ok=True)
    with open(os.path.join(SAIDA, time.strftime("%Y%m%d-%H%M%S") + f"-{conjunto}.json"), "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
