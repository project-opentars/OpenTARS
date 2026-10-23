# openTARS — nucleo/ferramentas.py
# Esquemas das ferramentas que a IA vê, conserto das chamadas e o executor central.
#
# Parte do núcleo: o tars.py executa este arquivo DENTRO do próprio
# namespace (ver _carregar_nucleo), então tudo aqui é tars.<nome> e as
# partes enxergam umas às outras sem import. Os testes que trocam
# tars.<função> por uma falsa continuam valendo pra todas as partes.
# flake8: noqa

# ============================================================
# FERRAMENTAS PARA OLLAMA
# ============================================================
#
# Descrições em inglês: é a língua que os modelos entendem melhor e
# não muda com o idioma da interface (a resposta ao usuário sai no
# idioma dele — ver SYSTEM_PROMPT).

def _ferramenta(nome, descricao, propriedades=None, obrigatorios=()):
    parametros = {"type": "object", "properties": propriedades or {}}
    if obrigatorios:
        parametros["required"] = list(obrigatorios)
    return {"type": "function", "function": {"name": nome, "description": descricao, "parameters": parametros}}


_TEXTO = {"type": "string"}
_INTEIRO = {"type": "integer"}

TOOLS = [
    _ferramenta(
        "open_application",
        "Opens ANY application installed on the system, by the common name the user "
        "used, in any language (browser, text editor, calculator, terminal, file "
        "manager, a game...). The tool resolves the real name by itself, waits for "
        "the window and brings it to the front. Always use it to open apps, even if "
        "the name is not known in advance.",
        {"app": {"type": "string", "description": "Name of the application to open, as the user said it."}},
        ["app"],
    ),
    _ferramenta(
        "close_application",
        "Closes an open application by the common name the user used ('claude', "
        "'the browser', 'calculator', 'spotify'). It finds the window or process by itself.",
        {"app": {"type": "string", "description": "Name of the application, as the user said it."}},
        ["app"],
    ),
    _ferramenta(
        "open_website",
        "Opens ANY website or online service in the browser, by its common name or "
        "URL. The tool resolves the real address by itself.",
        {"site": {"type": "string", "description": "Website name or URL."}},
        ["site"],
    ),
    _ferramenta(
        "search_web",
        "Searches the web and opens the results in the browser. Use it (instead of "
        "open_website) whenever the request is a SEARCH: searching, looking up or "
        "finding something, or asking for something 'on google'/'on youtube'.",
        {
            "query": {"type": "string", "description": (
                "Only the search terms, without the verb and without the service name "
                "(for 'search rtx 5060 on google', query is just 'rtx 5060').")},
            "service": {"type": "string", "description": (
                "Where to search, only if the user names a service (e.g. 'google', "
                "'youtube'). Leave it out otherwise: the default is Google.")},
        },
        ["query"],
    ),
    _ferramenta(
        "click_element",
        "Presses a button, menu item, tab, link or checkbox in an app window BY THE "
        "TEXT SHOWN ON IT (e.g. name='7', '=', 'Save', 'Settings'). Uses the "
        "accessibility interface (or, in apps that don't expose their buttons, reads the "
        "visible text on screen): no screenshot or coordinates needed, and it works "
        "with any model. Returns what the window shows afterwards (e.g. a calculator "
        "display). Prefer it over clicking by coordinates.",
        {
            "name": {"type": "string", "description": "Text shown on the element (or its tooltip). For an icon "
                                                       "without text, describe it: 'send icon', 'gear icon'."},
            "window": {"type": "string", "description": "App or window name (e.g. 'calculator'). Recommended."},
            "role": {"type": "string", "description": "Optional: 'button', 'menu item', 'tab', 'link', 'checkbox'..."},
        },
        ["name"],
    ),
    _ferramenta(
        "list_elements",
        "Lists what can be clicked in an app window (buttons, menus, fields, tabs, "
        "links, grouped by role) and the texts it shows (e.g. a calculator display). "
        "Use it to find names for click_element or to read the window without a screenshot.",
        {
            "window": {"type": "string", "description": "App or window name. Without it, the focused window."},
            "filter": {"type": "string", "description": "Optional: only elements whose name contains this."},
        },
    ),
    _ferramenta(
        "type_in_element",
        "Writes text into a text field of an app window, found by its name or label "
        "(e.g. 'Search', 'File name'). Without a name, uses the window's only field (or, in "
        "apps that don't expose their fields, the one with the keyboard focus, like a chat "
        "box). submit=true presses Enter afterwards (to send a message or search).",
        {
            "text": {"type": "string", "description": "Text to write."},
            "name": {"type": "string", "description": "Name or label of the field."},
            "window": {"type": "string", "description": "App or window name."},
            "submit": {"type": "boolean", "description": "Press Enter after writing."},
        },
        ["text"],
    ),
    _ferramenta(
        "execute_terminal",
        "Runs a command in the Linux terminal (non-interactive: no password prompts).",
        {"command": _TEXTO},
        ["command"],
    ),
    _ferramenta(
        "click_mouse",
        "Clicks with the mouse at x/y (pixels of the last screenshot). ALWAYS also pass "
        "'target' saying what you are clicking ('close X of the YouTube tab', 'red icon at "
        "the top right'): openTARS zooms in around x/y and aims at it exactly, so small "
        "things like a tab's X are hit. With only 'target' (no x/y), it finds it on the "
        "screen by itself. Says if the screen changed (if not, the click missed).",
        {
            "button": {"type": "string", "enum": ["left", "right", "middle"]},
            "x": _INTEIRO,
            "y": _INTEIRO,
            "target": {"type": "string", "description": "What is being clicked, described (recommended)."},
            "window": {"type": "string", "description": "Optional: app/window where the target is."},
            "clicks": {"type": "integer", "description": "2 for a double click (open a file, select a word). Default 1."},
        },
    ),
    _ferramenta(
        "drag_mouse",
        "DRAGS something with the mouse: holds the button on it, moves to the destination and "
        "releases (a browser tab, a file, a window by its title bar, a slider, an icon). Use it "
        "for any 'drag'/'move with the mouse' request; clicking does NOT drag. Start: "
        "from_element (described or its text, e.g. 'YouTube tab') and/or from_x/from_y. End: "
        "'to' as a place of the screen ('top-left', 'top-right', 'bottom-left', 'bottom-right', "
        "'left', 'right', 'top', 'bottom', 'center', 'left half'), to_element (what to drop it "
        "on, e.g. 'Trash') or to_x/to_y. Coordinates are pixels of the last screenshot.",
        {
            "from_element": {"type": "string", "description": "What to drag (text shown on it, or described)."},
            "from_x": _INTEIRO,
            "from_y": _INTEIRO,
            "to": {"type": "string", "description": "Place of the screen to drop it: 'top-left', 'right', 'center'..."},
            "to_element": {"type": "string", "description": "What to drop it on (e.g. 'Trash', 'Documents folder')."},
            "to_x": _INTEIRO,
            "to_y": _INTEIRO,
            "window": {"type": "string", "description": "App/window where the dragged item is (e.g. 'brave')."},
            "button": {"type": "string", "enum": ["left", "right", "middle"]},
        },
    ),
    _ferramenta(
        "scroll_mouse",
        "Scrolls the page/window (optionally at an x/y position).",
        {"amount": _INTEIRO, "x": _INTEIRO, "y": _INTEIRO},
        ["amount"],
    ),
    _ferramenta(
        "type_text",
        "Types text with the keyboard into the focused place, in any language "
        "(accents, other alphabets and emoji included).",
        {"text": _TEXTO},
        ["text"],
    ),
    _ferramenta("press_key", "Presses a key or a key combination (e.g. 'enter', 'esc', 'tab', 'ctrl+s').",
                {"key": _TEXTO}, ["key"]),
    _ferramenta(
        "take_screenshot",
        "Takes a screenshot so you can SEE the screen. To work inside an app, pass "
        "'window' with the app name: the window comes to the front and the image shows "
        "only it, sharp. After a screenshot, click coordinates are pixels of THAT image. "
        "To look at an image FILE instead of the screen (a photo, a picture the user mentions), pass 'file' with its path.",
        {"window": {"type": "string", "description": "Optional: app/window name (e.g. 'calculator'). Without it, the whole screen."},
         "file": {"type": "string", "description": "Optional: path of an image file to look at (png, jpg...). Instead of the screen."}},
    ),
    _ferramenta("list_windows", "Lists the open windows (title, app, position, which one has focus)."),
    _ferramenta(
        "move_window",
        "Moves, snaps or resizes a WHOLE window (use it instead of dragging for any 'move/drag the X "
        "window to...'): to='top-left', 'top-right', 'bottom-left', 'bottom-right', 'left', 'right', "
        "'center', 'left half', 'right half', 'maximize', 'restore'; or x/y (and width/height) in "
        "full-screen screenshot pixels.",
        {
            "window": {"type": "string", "description": "App name or part of the window title."},
            "to": {"type": "string", "description": "Place: 'top-left', 'left half', 'maximize'..."},
            "x": _INTEIRO, "y": _INTEIRO, "width": _INTEIRO, "height": _INTEIRO,
        },
        ["window"],
    ),
    _ferramenta(
        "focus_window",
        "Brings an open window to the front (restoring it if minimized), before typing "
        "or using shortcuts in it.",
        {"window": {"type": "string", "description": "App name or part of the title."}},
        ["window"],
    ),
]


# ============================================================
# EXECUTOR CENTRAL
# ============================================================

# Dispatch table em vez de uma cadeia longa de if/elif: mais fácil de
# manter e de estender com novas ferramentas.
_DISPATCH_FERRAMENTAS = {
    "open_application": lambda a: abrir_aplicativo(a.get("app", "")),
    "close_application": lambda a: fechar_aplicativo(a.get("app", "")),
    "open_website": lambda a: abrir_site(a.get("site", "")),
    "search_web": lambda a: pesquisar_web(a.get("query", ""), a.get("service")),
    "execute_terminal": lambda a: executar_terminal(a.get("command", "")),
    "click_mouse": lambda a: clicar_mouse(a.get("button", "left"), a.get("x"), a.get("y"),
                                          a.get("target"), a.get("window") or None,
                                          duplo=_numero_de_cliques(a.get("clicks")) >= 2),
    "drag_mouse": arrastar_mouse,
    "scroll_mouse": lambda a: scroll_mouse(a.get("amount", 0), a.get("x"), a.get("y")),
    "type_text": lambda a: digitar_texto(a.get("text", "")),
    "press_key": lambda a: pressionar_tecla(a.get("key", "")),
    "take_screenshot": lambda a: tirar_print(a.get("window") or None, a.get("file") or None),
    "click_element": lambda a: clicar_elemento(a.get("name", ""), a.get("window") or None, a.get("role") or None),
    "list_elements": lambda a: listar_elementos(a.get("window") or None, a.get("filter") or None),
    "type_in_element": lambda a: escrever_em_elemento(a.get("name", ""), a.get("text", ""), a.get("window") or None,
                                                      _booleano(a.get("submit"))),
    "list_windows": lambda a: listar_janelas(),
    "move_window": lambda a: mover_janela(a.get("window", ""), a.get("to"), a.get("x"), a.get("y"),
                                          a.get("width"), a.get("height")),
    "focus_window": lambda a: focar_janela(a.get("window", "")),
}

def _numero_de_cliques(valor):
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return 1


# 5.1: o que continua rodando no modo plano (só olha, não muda nada)
FERRAMENTAS_SO_LEITURA = {"list_windows", "list_elements", "take_screenshot"}

_FERRAMENTAS_MOUSE_TECLADO = {
    "click_mouse", "scroll_mouse", "drag_mouse", "type_text", "press_key",
}

# 4.5: sem interface gráfica (servidor, SSH, WSL sem WSLg) estas não têm o que fazer.
FERRAMENTAS_SO_COM_TELA = {
    "open_application", "click_mouse", "drag_mouse", "scroll_mouse", "type_text", "press_key",
    "take_screenshot", "click_element", "list_elements", "type_in_element", "list_windows",
    "move_window", "focus_window",
}

AVISO_SEM_INTERFACE = (
    "There is no graphical session on this machine (terminal only), so '{nome}' cannot work. Use "
    "execute_terminal, search_web/open_website (they give the user the link) and the "
    "files the user attached. For command-line programs run them with execute_terminal. Tell the user "
    "plainly what you cannot do here instead of retrying."
)

AVISO_WAYLAND_FERRAMENTA = (
    "NOTE: this is a Wayland session, where simulated clicks and keys only reach "
    "some applications (the ones running through XWayland). If nothing happened "
    "on screen, prefer click_element / type_in_element (they work on Wayland), or "
    "tell the user that mouse/keyboard control needs the Xorg session (chosen on "
    "the login screen)."
)


def _resumo_argumentos(argumentos):
    """O argumento principal, curto, pra mostrar o que a ferramenta vai
    fazer ("calculadora", "ls -la", "7, 2")."""
    if not isinstance(argumentos, dict) or not argumentos:
        return ""
    if any(k in argumentos for k in ("from_element", "from_x", "to", "to_element", "to_x")):
        origem = argumentos.get("from_element") or (
            f"{argumentos['from_x']}, {argumentos.get('from_y')}" if "from_x" in argumentos else "")
        destino = argumentos.get("to") or argumentos.get("to_element") or (
            f"{argumentos['to_x']}, {argumentos.get('to_y')}" if "to_x" in argumentos else "")
        resumo = " → ".join(str(p) for p in (origem, destino) if p)
        return resumo if len(resumo) <= 60 else resumo[:57] + "..."
    for chave in ("app", "site", "query", "command", "name", "target", "window", "text", "key", "path", "filter"):
        valor = argumentos.get(chave)
        if isinstance(valor, str) and valor.strip():
            valor = " ".join(valor.split())
            return valor if len(valor) <= 60 else valor[:57] + "..."
    if "keys" in argumentos and isinstance(argumentos["keys"], list):
        return "+".join(str(k) for k in argumentos["keys"])
    if "x" in argumentos and "y" in argumentos:
        return f"{argumentos['x']}, {argumentos['y']}"
    if "seconds" in argumentos:
        return f"{argumentos['seconds']}s"
    return ""


# Ferramentas oferecidas por tarefa. Menos opções = menos erro nos
# modelos pequenos (muitas ferramentas confundem um modelo de 4B). Se a IA
# recusar ou devolver a tarefa, ela ganha todas. Uma ferramenta fora da
# lista que a IA chamar mesmo assim ainda é executada.
_FERRAMENTAS_POR_TAREFA = {
    "simples": {"open_website", "search_web", "open_application", "close_application"},
    "busca": {"search_web", "open_website", "open_application", "take_screenshot", "click_element",
              "type_in_element", "list_elements", "press_key", "type_text", "focus_window"},
    "geral": {"search_web", "open_website", "open_application", "execute_terminal"},
    "codigo": {"execute_terminal", "search_web", "open_application", "type_in_element"},
    "tecnico": {"execute_terminal", "search_web", "open_website", "open_application", "close_application"},
}


# Ferramentas que só entram quando o pedido fala delas (memória:
# ver nucleo/memoria.py, ferramentas_do_pedido).
_FERRAMENTAS_SO_SE_PEDIDAS = set()


def ferramentas_para(tarefa):
    permitidas = _FERRAMENTAS_POR_TAREFA.get(tarefa)
    if not permitidas:
        # ação, visão e desconhecida: todas
        if not _FERRAMENTAS_SO_SE_PEDIDAS:
            return TOOLS
        return [f for f in TOOLS if f["function"]["name"] not in _FERRAMENTAS_SO_SE_PEDIDAS]
    return [f for f in TOOLS if f["function"]["name"] in permitidas]


def _booleano(valor):
    """Modelos mandam true, "true", "yes", 1..."""
    if isinstance(valor, str):
        return valor.strip().lower() in ("true", "1", "yes", "sim", "y")
    return bool(valor)


# Nomes que os modelos inventam pras ferramentas -> o nome certo.
_APELIDOS_FERRAMENTAS = {
    "open_app": "open_application", "launch_app": "open_application", "launch_application": "open_application",
    "start_application": "open_application", "run_application": "open_application", "open_program": "open_application",
    "close_app": "close_application", "kill_application": "close_application", "quit_application": "close_application",
    "click": "click_mouse", "left_click": "click_mouse", "mouse_click": "click_mouse",
    "right_click": "click_mouse", "click_at": "click_mouse", "click_position": "click_mouse",
    "drag": "drag_mouse", "drag_and_drop": "drag_mouse", "drag_drop": "drag_mouse", "mouse_drag": "drag_mouse",
    "drag_to": "drag_mouse", "drag_element": "drag_mouse", "drag_file": "drag_mouse", "drag_tab": "drag_mouse",
    "move_tab": "drag_mouse", "left_click_drag": "drag_mouse",
    "drag_window": "move_window", "position_window": "move_window", "snap_window": "move_window",
    "resize_window": "move_window", "maximize_window": "move_window", "set_window_position": "move_window",
    "click_button": "click_element", "press_button": "click_element", "click_on": "click_element",
    "type": "type_text", "write_text": "type_text", "keyboard_type": "type_text", "input_text": "type_text",
    "press": "press_key", "key_press": "press_key", "keypress": "press_key",
    "look_at_image": "take_screenshot", "view_image": "take_screenshot", "see_image": "take_screenshot",
    "describe_image": "take_screenshot", "analyze_image": "take_screenshot", "use_cooper": "take_screenshot",
    "cooper": "take_screenshot", "screenshot": "take_screenshot", "capture_screen": "take_screenshot", "look_at_screen": "take_screenshot",
    "search": "search_web", "web_search": "search_web", "google_search": "search_web", "search_internet": "search_web",
    "open_url": "open_website", "open_browser": "open_website", "browse": "open_website", "visit_website": "open_website",
    "run_command": "execute_terminal", "terminal": "execute_terminal", "bash": "execute_terminal",
    "shell": "execute_terminal", "execute_command": "execute_terminal", "run_terminal": "execute_terminal",
    "wait": "wait_seconds", "sleep": "wait_seconds", "list_buttons": "list_elements", "read_window": "list_elements",
    "switch_window": "focus_window", "activate_window": "focus_window", "fill_field": "type_in_element",
}

# Nomes de argumento que os modelos trocam -> o nome certo.
_APELIDOS_ARGUMENTOS = {
    "app": ("app_name", "application", "application_name", "program", "name", "appname"),
    "url": ("website", "site", "link", "address", "uri"),
    "query": ("q", "search", "search_query", "term", "terms", "text"),
    "command": ("cmd", "shell_command", "bash"),
    "text": ("content", "message", "value", "string", "input"),
    "key": ("keys", "button", "keyname"),
    "window": ("window_name", "app", "application", "title", "window_title"),
    "name": ("element", "label", "button", "element_name", "target", "text"),
    "seconds": ("time", "duration", "secs", "s"),
    "path": ("directory", "folder", "dir"),
    "file": ("image", "image_path", "image_file", "filepath", "file_path", "filename", "picture", "photo"),
    # 2.9.2: mouse
    "target": ("element", "name", "description", "what", "label", "object", "item"),
    "from_x": ("x", "x1", "start_x", "source_x", "x_from", "from_X", "startX", "fromX"),
    "from_y": ("y", "y1", "start_y", "source_y", "y_from", "from_Y", "startY", "fromY"),
    "to_x": ("x2", "end_x", "target_x", "dest_x", "destination_x", "x_to", "toX", "endX"),
    "to_y": ("y2", "end_y", "target_y", "dest_y", "destination_y", "y_to", "toY", "endY"),
    "from_element": ("source", "from", "element", "item", "name", "what", "source_element", "drag_element",
                     "object", "tab"),
    "to": ("destination", "position", "where", "to_position", "dest", "target", "place", "location",
           "target_position", "corner"),
    "to_element": ("target_element", "destination_element", "onto", "drop_on", "drop_target", "into"),
}


def _esquemas_ferramentas():
    if not _cache_esquemas:
        for f in list(TOOLS) + _TOOLS_EXTRAS:
            fn = f["function"]
            parametros = fn.get("parameters") or {}
            _cache_esquemas[fn["name"]] = (parametros.get("properties") or {}, parametros.get("required") or [])
    return _cache_esquemas


_cache_esquemas = {}

# Ferramentas que o Gargantua NÃO vê (ele foi treinado só com TOOLS + memória): as da agenda (5.0).
_TOOLS_EXTRAS = []


def _traduzir_chamada_antiga(nome, argumentos):
    """4.6: nove ferramentas saíram (double_click, hotkey, list_files, pc_info, wait_seconds,
    move_to_trash, undo_last_action, read_clipboard, write_clipboard). Um modelo que ainda as
    conhece (o Gargantua 1.1 foi treinado com elas) continua funcionando: a chamada vira a
    ferramenta que ficou. Devolve (nome, argumentos, nota) ou None se não é uma delas."""
    a = dict(argumentos or {})
    chave = (nome or "").strip().lower().replace("-", "_").replace(" ", "_")
    if chave == "double_click":
        return "click_mouse", {**a, "clicks": 2}, "double_click -> click_mouse(clicks=2)"
    if chave == "hotkey":
        teclas = a.get("keys", a.get("key", ""))
        if isinstance(teclas, (list, tuple)):
            teclas = "+".join(str(k) for k in teclas)
        return "press_key", {"key": str(teclas)}, "hotkey -> press_key"
    if chave == "list_files":
        caminho = os.path.expanduser(str(a.get("path") or "."))
        return "execute_terminal", {"command": f"ls -la -- {shlex.quote(caminho)}"}, "list_files -> execute_terminal(ls)"
    if chave == "pc_info":
        return "execute_terminal", {"command": "uptime; free -h; df -h /"}, "pc_info -> execute_terminal"
    if chave == "wait_seconds":
        try:
            segundos = max(0.0, min(float(a.get("seconds", 1.0)), 5.0))
        except (TypeError, ValueError):
            segundos = 1.0
        return "execute_terminal", {"command": f"sleep {segundos:g}"}, "wait_seconds -> execute_terminal(sleep)"
    if chave == "move_to_trash":
        caminhos = a.get("paths") or a.get("path") or a.get("files") or []
        if isinstance(caminhos, str):
            caminhos = [caminhos]
        if caminhos:
            return ("execute_terminal", {"command": "gio trash -- " + " ".join(shlex.quote(os.path.expanduser(str(c))) for c in caminhos)},
                    "move_to_trash -> execute_terminal(gio trash)")
    return None


def consertar_chamada(nome, argumentos):
    """Corrige os erros comuns dos modelos pequenos antes de executar:
    nome de ferramenta inventado ("open_app"), argumento com outro nome
    ("app_name"), número como texto ("120"), booleano como texto.
    Devolve (nome, argumentos, nota) — nota diz o que foi corrigido."""
    if isinstance(argumentos, str):          # alguns modelos mandam os argumentos como texto JSON
        try:
            argumentos = json.loads(argumentos)
        except ValueError:
            argumentos = {}
    if not isinstance(argumentos, dict):
        argumentos = {}
    nome = nome if isinstance(nome, str) else str(nome or "")

    esquemas = _esquemas_ferramentas()
    notas = []
    original = nome
    antiga = _traduzir_chamada_antiga(nome, argumentos) if nome not in esquemas else None
    if antiga:
        nome, argumentos, nota_antiga = antiga
        notas.append(nota_antiga)
    if nome not in esquemas:
        chave = (nome or "").strip().lower().replace("-", "_").replace(" ", "_")
        novo = _APELIDOS_FERRAMENTAS.get(chave) or (chave if chave in esquemas else None)
        if not novo:
            parecidos = difflib.get_close_matches(chave, list(esquemas), n=1, cutoff=0.75)
            novo = parecidos[0] if parecidos else None
        if novo:
            nome = novo
            notas.append(f"tool '{original}' -> '{nome}'")
            if chave in ("right_click", "context_click"):
                argumentos = {**(argumentos or {}), "button": (argumentos or {}).get("button") or "right"}
    if nome not in esquemas:
        return nome, argumentos, None

    propriedades, obrigatorios = esquemas[nome]
    argumentos = dict(argumentos or {})
    for certo in list(propriedades):
        if certo in argumentos:
            continue
        for apelido in _APELIDOS_ARGUMENTOS.get(certo, ()):
            if apelido in argumentos and apelido not in propriedades:
                argumentos[certo] = argumentos.pop(apelido)
                notas.append(f"argument '{apelido}' -> '{certo}'")
                break
    # Um obrigatório faltando e um único argumento desconhecido: é ele.
    faltando = [p for p in obrigatorios if p not in argumentos]
    desconhecidos = [k for k in argumentos if k not in propriedades]
    if len(faltando) == 1 and len(desconhecidos) == 1:
        argumentos[faltando[0]] = argumentos.pop(desconhecidos[0])
        notas.append(f"argument '{desconhecidos[0]}' -> '{faltando[0]}'")

    for chave, valor in list(argumentos.items()):
        tipo = (propriedades.get(chave) or {}).get("type")
        try:
            if tipo == "integer" and not isinstance(valor, int):
                argumentos[chave] = int(round(float(str(valor).strip())))
            elif tipo == "number" and isinstance(valor, str):
                argumentos[chave] = float(valor.strip())
            elif tipo == "boolean" and not isinstance(valor, bool):
                argumentos[chave] = _booleano(valor)
            elif tipo == "string" and isinstance(valor, (int, float)) and not isinstance(valor, bool):
                argumentos[chave] = str(valor)
            elif tipo == "array" and isinstance(valor, str):
                argumentos[chave] = [x.strip() for x in re.split(r"[+,]", valor) if x.strip()]
        except (TypeError, ValueError, OverflowError):
            pass
    return nome, argumentos, ("openTARS fixed the call: " + "; ".join(notas) + ".") if notas else None


def executar_ferramenta(nome, argumentos):

    nome, argumentos, conserto = consertar_chamada(nome, argumentos)
    inicio = time.time()

    emitir("ferramenta", nome=nome, resumo=_resumo_argumentos(argumentos))

    handler = _DISPATCH_FERRAMENTAS.get(nome)

    try:

        if MODO_PERMISSAO == "plano" and nome not in FERRAMENTAS_SO_LEITURA:
            PASSOS_DO_PLANO.append(f"{nome} {_resumo_argumentos(argumentos)}".strip())
            resultado = {"sucesso": True, "mensagem": (
                "PLAN MODE: this step was recorded but NOT run. Keep planning the remaining steps the same way; then "
                "tell the user the plan, and that nothing was done yet.")}
        elif nome in modos.avancado()["ferramentas_desligadas"]:
            # 5.1: desligada no modo Pro. Bloqueada aqui, não tirada da lista: a do Gargantua é a do treino.
            resultado = {"sucesso": False, "mensagem": f"The user turned the tool '{nome}' off in Settings > Advanced. "
                                                       "Do not try it again; tell the user what you could not do."}
        elif SEM_INTERFACE and nome in FERRAMENTAS_SO_COM_TELA:
            resultado = {"sucesso": False, "mensagem": AVISO_SEM_INTERFACE.format(nome=nome)}
        elif handler is not None:
            resultado = handler(argumentos)
        else:
            resultado = {
                "sucesso": False,
                "mensagem": f"Unknown tool: {nome}",
            }

    except Exception as e:

        resultado = {
            "sucesso": False,
            "mensagem": f"Internal error in the tool '{nome}': {e}",
        }

    # Numa sessão Wayland, o pyautogui "consegue" mover/clicar/digitar
    # sem erro nenhum, mas o evento só chega a janelas XWayland. Avisa
    # a IA pra ela poder explicar ao usuário em vez de fingir sucesso.
    if SESSAO_GRAFICA == "wayland" and not ENTRADA_WAYLAND and nome in _FERRAMENTAS_MOUSE_TECLADO:
        resultado["mensagem"] = (
            f"{resultado.get('mensagem', '')} {AVISO_WAYLAND_FERRAMENTA}"
        ).strip()

    if conserto:
        resultado["mensagem"] = f"{resultado.get('mensagem', '')} ({conserto})".strip()

    tempo = time.time() - inicio

    emitir("ferramenta_fim", nome=nome, sucesso=bool(resultado.get("sucesso")), segundos=tempo)

    LOG.info(
        "ferramenta=%s args=%s sucesso=%s tempo=%.2fs mensagem=%s",
        nome,
        _resumir_para_log(argumentos),
        resultado.get("sucesso"),
        tempo,
        _resumir_para_log(resultado.get("mensagem", ""))[:LIMITE_LOG_CAMPO_CHARS],
    )

    return resultado
