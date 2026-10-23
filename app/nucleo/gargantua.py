# openTARS — nucleo/gargantua.py
# Gargantua (4.0): a IA oficial do openTARS. É um Qwen3 4B treinado (kit
# gargantua/gargantua.py) em conversas de verdade do openTARS, então ele
# já sabe as regras e as ferramentas. Por isso recebe um formato CURTO:
#   - prompt de sistema curto (SISTEMA_GARGANTUA) + os fatos deste PC,
#   - as ferramentas todas, com descrições de uma frase,
#   - sem raciocínio (foi treinado sem).
# Este formato tem que ser IDÊNTICO ao do treino (gargantua.py, seção 2):
# qualquer mudança aqui pede um treino novo.
#
# Parte do núcleo: o tars.py executa este arquivo DENTRO do próprio
# namespace (ver _carregar_nucleo). Vem depois de "memoria" (usa
# TOOLS_MEMORIA).
# flake8: noqa

# ============================================================
# GARGANTUA
# ============================================================

# ollama pull ProjectOpenTARS/Gargantua-2   (18/10: o Gargantua 2, Qwen3.5 2B com visão, é o principal; o repositório
# antigo, ProjectOpenTARS/Gargantua, continua servindo quem já o tem e os apps antigos)
MODELO_GARGANTUA = os.environ.get("TARS_MODELO_GARGANTUA", "ProjectOpenTARS/Gargantua-2")
REPOSITORIO_ANTIGO = "ProjectOpenTARS/Gargantua"
VERSAO_GARGANTUA = "1.2"      # a do kit (gargantua/gargantua.py): 19 ferramentas

SISTEMA_GARGANTUA = (
    "You are Gargantua, a local AI assistant that controls this Linux computer with tools, inside the openTARS app.\n"
    "- Your name is Gargantua. openTARS is the app you run in, not your name.\n"
    "- When the user asks you to DO something on the computer, do it with the tools, step by step, and check the result.\n"
    "- When it is just a question or small talk, answer directly, without tools.\n"
    "- Never say something worked unless a tool result confirmed it.\n"
    "- Destructive actions (deleting many files, formatting, rm -rf) need the user's explicit confirmation.\n"
    "- Answer short, in the user's language.\n"
)

DESCRICOES_CURTAS = {
    "open_application": "Open an installed app by the name the user said.",
    "close_application": "Close an open app by the name the user said.",
    "open_website": "Open a website by name or URL in the browser.",
    "search_web": "Search the web (or a service like youtube) and open the results.",
    "click_element": "Click a button/menu/link in a window by its visible text.",
    "list_elements": "List clickable elements and texts of a window.",
    "type_in_element": "Type text into a named field of a window.",
    "execute_terminal": "Run a shell command (non-interactive).",
    "click_mouse": "Click at x/y or on a described target (clicks=2 for a double click).",
    "drag_mouse": "Drag with the mouse from one point/target to another.",
    "scroll_mouse": "Scroll the page or window.",
    "type_text": "Type text into the focused place.",
    "press_key": "Press a key or a combination (enter, esc, ctrl+s...).",
    "take_screenshot": "Take a screenshot to see the screen.",
    "list_windows": "List open windows.",
    "move_window": "Move, snap, maximize or resize a window.",
    "focus_window": "Bring a window to the front.",
    "remember": "Save a fact about the user for future conversations.",
    "forget": "Forget saved facts containing these words.",
}


def gargantua_desligado():
    """TARS_SEM_GARGANTUA=1: o AUTO deixa de preferir o Gargantua (ele
    continua usável se for escolhido na mão)."""
    return normalizar(os.environ.get("TARS_SEM_GARGANTUA") or "") in ("1", "sim", "yes", "on", "true")


def eh_gargantua(modelo):
    """'gargantua', 'gargantua:1.0', 'ProjectOpenTARS/Gargantua:latest'..."""
    return str(modelo or "").strip().lower().split("/")[-1].startswith("gargantua")


def e_gargantua_2(modelo):
    """'ProjectOpenTARS/Gargantua-2', 'Gargantua-2:lite', 'gargantua-2'... (a família nova, com visão)."""
    return str(modelo or "").strip().lower().partition(":")[0].split("/")[-1].startswith("gargantua-2")


def variante_do_gargantua(modelo):
    """'lite' ou 'code' se o nome ou a etiqueta dizem que é uma VARIANTE do Gargantua (gargantua-code,
    ProjectOpenTARS/Gargantua:code, Gargantua:1.2-lite); '' se é o oficial (ou qualquer outro Gargantua).
    A mesma regra está no kit (gargantua.py: variante_do_nome) e em tars_primeiro_uso.py."""
    base, _, tag = str(modelo or "").strip().lower().partition(":")
    segmento = base.split("/")[-1]
    partes = re.split(r"[-_. ]", segmento[len("gargantua"):] if segmento.startswith("gargantua") else segmento)
    for parte in partes + re.split(r"[-_. ]", tag):
        if parte in ("lite", "code"):
            return parte
    return ""


def ordem_do_gargantua(tag):
    """Quem vai na frente quando há vários Gargantua: o Gargantua 2, o oficial antigo, os outros, o Code e por fim o Lite."""
    variante = variante_do_gargantua(tag)
    if variante:
        return {"code": 3, "lite": 4}[variante]
    if e_gargantua_2(tag):
        return 0
    return 1 if str(tag).lower().startswith(REPOSITORIO_ANTIGO.lower()) else 2


def gargantua_instalado(catalogo=None):
    """A tag do Gargantua no Ollama (a oficial primeiro, variantes por último), ou None."""
    try:
        tags = list((catalogo if catalogo is not None else catalogar_modelos()).keys())
    except Exception:
        return None
    achados = [tag for tag in tags if eh_gargantua(tag)]
    achados.sort(key=lambda tag: (ordem_do_gargantua(tag), tag))
    return achados[0] if achados else None


def _primeira_frase_curta(texto, limite=70):
    texto = re.sub(r"\b(e\.g|i\.e|etc)\.", r"\1", (texto or "").strip())
    frase = re.split(r"(?<=[.!?])\s", texto, maxsplit=1)[0]
    return frase if len(frase) <= limite else frase[:limite - 1].rstrip() + "…"


def _compactar(ferramenta):
    f = ferramenta["function"]
    props = {}
    for nome, esquema in (f.get("parameters", {}).get("properties") or {}).items():
        p = {"type": esquema.get("type", "string")}
        if esquema.get("enum"):
            p["enum"] = esquema["enum"]
        if esquema.get("items"):
            p["items"] = {"type": esquema["items"].get("type", "string")}
        props[nome] = p
    parametros = {"type": "object", "properties": props}
    if f.get("parameters", {}).get("required"):
        parametros["required"] = f["parameters"]["required"]
    descricao = DESCRICOES_CURTAS.get(f["name"]) or _primeira_frase_curta(f.get("description"))
    return {"type": "function", "function": {"name": f["name"], "description": descricao, "parameters": parametros}}


def ferramentas_gargantua():
    """Todas as ferramentas (as do PC + memória/agenda), descrições curtas."""
    vistos, lista = set(), []
    for f in list(TOOLS) + list(TOOLS_MEMORIA):
        nome = f["function"]["name"]
        if nome in vistos:
            continue
        vistos.add(nome)
        lista.append(_compactar(f))
    return lista


def sistema_gargantua():
    """Prompt curto + os fatos deste PC + a memória + o idioma."""
    # 5.2: fora do Linux vai o prompt neutro que a "pele de sistema" dos dados da 5.2 ensina (o resto é byte a byte o mesmo)
    base = SISTEMA_GARGANTUA if plataforma.sistema() == "linux" else \
        SISTEMA_GARGANTUA.replace("controls this Linux computer", "controls this computer")
    return base + contexto_sistema() + _memoria_para_prompt() + "\n" + t("_ia") + "\n"


def prompt_do_modelo(modelo=None):
    return sistema_gargantua() if eh_gargantua(modelo) else montar_system_prompt()


def ferramentas_do_modelo(modelo, tarefa, texto):
    return ferramentas_gargantua() if eh_gargantua(modelo) else ferramentas_do_pedido(tarefa, texto)


def pensar_do_modelo(modelo, tarefa, texto, multi_etapas=False):
    return False if eh_gargantua(modelo) else deve_pensar(tarefa, texto, multi_etapas)
