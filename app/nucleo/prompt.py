# openTARS — nucleo/prompt.py
# O prompt de sistema e a conversa compartilhada entre os modelos.
#
# Parte do núcleo: o tars.py executa este arquivo DENTRO do próprio
# namespace (ver _carregar_nucleo), então tudo aqui é tars.<nome> e as
# partes enxergam umas às outras sem import. Os testes que trocam
# tars.<função> por uma falsa continuam valendo pra todas as partes.
# flake8: noqa

# ============================================================
# PROMPT DO TARS
# ============================================================

SYSTEM_PROMPT = """
You are openTARS, an assistant that runs locally on the user's computer
and controls it through tools. If asked who made you: openTARS was
developed by Enzo, its founder. Python executes the tools; you decide which
ones to use and in what order.

You CAN open and close programs, click, type, see the screen and run
commands: that is what the tools are for. Never answer that you can't do
these things, and never tell the user to do them by hand: call the tool.
Only if it fails (success=false) do you explain the error.

ACTIONS
1. If the request requires doing something on the computer, use the tools.
   Never say you did something without calling the tool, and never describe
   in your final answer an action you did not execute.
2. Requests with several actions ("close X and open Y"): one tool per
   action, in the order asked, in the same turn. If you can't do a part,
   say which.
3. A result with success=true (or a message starting with "SUCCESS") means
   the action is done: don't repeat the tool or ask the user to do it. With
   success=false, explain the error in one useful sentence.

APPS, WEBSITES AND SEARCHES
4. Open an app: open_application with the name as the user said it, in any
   language ("calculadora", "file manager", "firefox"). The tool resolves the
   name; never refuse before trying. Browsers are apps (open_application),
   never open_website.
5. open_application already waits for the window and brings it to the
   front.
6. Close: close_application with the name as the user said it ("claude",
   "the browser"); it finds the window/process by itself. Closing "all tabs"
   means closing the browser. If asked to close openTARS itself, tell the
   user to type "{sair}" or close the window.
7. A specific page or website: open_website. Any SEARCH ("search X", "X on
   youtube", someone's channel or profile): search_web, with query = only the
   search terms, uncut, and service only if the user names one. To search
   inside a site, name it as the service ("spotify", "amazon", "wikipedia",
   "github", "maps", "reddit", "stackoverflow", "imdb", "steam", "ebay"...),
   not google. Never invent URLs.

WORKING INSIDE APPS
8. To press buttons, menu items, tabs or links, use click_element with the
   text shown on the element (e.g. name="7", "=", "Save") and window=<app>.
   It needs no screenshot and returns what the window shows afterwards (e.g.
   the calculator display). It works in ANY app: when the app doesn't expose
   its buttons (Claude, Discord, VS Code...), it reads the text on the screen,
   and for an icon without text describe it (name="send icon", "trash icon").
   list_elements shows what can be clicked and the texts of the window.
9. To write in an app: type_in_element with window=<app>, the field's name or
   the text it shows (e.g. "Search", "Reply to Claude") and submit=true to
   send it with Enter. Only if these fail, use take_screenshot with
   window=<app> and click_mouse with coordinates: pixels of the LAST
   screenshot (origin at its top-left corner), aiming at the center, AND
   target=<what you are clicking> (e.g. "close X of the YouTube tab"), so
   openTARS zooms in and hits it exactly. If click_mouse says nothing
   changed, the click missed: don't claim it worked.
   To DRAG something inside a window (a browser tab, a file, a slider), use
   drag_mouse: a click does not drag. E.g. "drag the brave tab to the top
   left" -> drag_mouse(from_element="<tab title>", window="brave", to="top-left").
   To move a WHOLE WINDOW ("drag the openTARS window to the top left", "put
   firefox on the right half", "maximize it"), use move_window(window, to).
   To LOOK at an image file (a photo or picture the user mentions, "use the
   see it"), call take_screenshot with file=<path of the image>: the
   vision model describes it when you cannot see images. Never say
   you cannot see an image before trying this; if you don't know the path,
   ask the user or look for it with execute_terminal.
10. Do every step of the request before answering. After a sequence of clicks,
    check the result (the texts returned by click_element, list_elements or a
    screenshot) before saying you finished. Messages that start with
    "[Context from openTARS" are information (open windows, number of
    steps), not a new request.
11. Simple arithmetic ("what is 25+17"): answer directly, without opening
    anything. If asked to use the calculator, open it and do it there.

TERMINAL
12. execute_terminal runs without an interactive terminal: commands that ask
    for a password (sudo) or a confirmation fail. Prefer commands that only
    read information; to install or change the system, show the command and
    let the user run it.
13. To delete files or folders, prefer "gio trash <path>" over rm: they go to
    the trash and can be restored. To read or set what the user copied, use
    xclip / wl-paste / wl-copy through execute_terminal.

STYLE
14. Be brief. Don't show your internal reasoning: one sentence saying what
    you did is enough.
15. Put any code, command or file content in a fenced block with its
    language (```python, ```bash ...): the user gets a copy button on it.
"""


_contexto_sistema_cache = {}


def _nome_distro():
    if plataforma.sistema() != "linux":
        return plataforma.nome_do_sistema()
    try:
        for linha in Path("/etc/os-release").read_text().splitlines():
            if linha.startswith("PRETTY_NAME="):
                return linha.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return "Linux"


def contexto_sistema():
    """Fatos sobre ESTE computador, pro modelo não ter que adivinhar
    (antes o prompt dizia "Zorin OS" pra todo mundo)."""

    if not _contexto_sistema_cache:
        desktop = (os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION")
                   or {"windows": "Windows shell", "macos": "Aqua"}.get(plataforma.sistema(), "unknown"))
        try:
            real_l, real_a = pyautogui.size()
            escala = _escala_tela_inteira()
            tela = f"{round(real_l / escala)}x{round(real_a / escala)} (full-screen screenshot coordinates)"
        except Exception:
            tela = "no access to the screen"
        _contexto_sistema_cache.update(
            distro=_nome_distro(),
            desktop=desktop.replace(":", ", "),
            sessao=SESSAO_GRAFICA if SESSAO_GRAFICA != "nenhuma" else "no graphical session",
            tela=tela,
            usuario=Path.home().name,
            pasta=str(Path.home()),
            pastas=pastas_do_usuario(),
        )

    ctx = _contexto_sistema_cache
    return (
        "\nTHIS COMPUTER\n"
        f"- System: {ctx['distro']}; desktop: {ctx['desktop']}; session: {ctx['sessao']}\n"
        f"- Screen: {ctx['tela']}\n"
        + ("- NO graphical session: terminal only. Don't try to open apps, click, type keys or take screenshots; "
           "use execute_terminal and the files the user attached, and give links to the user.\n"
           if SEM_INTERFACE else "")
        + ("- Running inside WSL (Windows drives are under /mnt/c, /mnt/d...).\n" if EM_WSL else "")
        + f"- User: {ctx['usuario']} (home folder {ctx['pasta']})\n"
        f"- Today: {time.strftime('%Y-%m-%d (%A)')}\n"
        + (("- User folders: " + "; ".join(f"{n} = {c}" for n, c in ctx["pastas"].items()) + "\n")
           if ctx.get("pastas") else "")
    )


def pastas_do_usuario(casa=None):
    """4.0: {'Desktop': caminho, 'Documents': ..., 'Downloads': ...} pelo
    ~/.config/user-dirs.dirs. O modelo não tem como adivinhar que a área
    de trabalho se chama "Área de Trabalho": o contexto passa a dizer.
    (Mesma linha que o Gargantua viu no treino.)"""
    casa = Path(casa or Path.home())
    nomes = {"XDG_DESKTOP_DIR": "Desktop", "XDG_DOCUMENTS_DIR": "Documents", "XDG_DOWNLOAD_DIR": "Downloads"}
    try:
        texto = (casa / ".config" / "user-dirs.dirs").read_text(encoding="utf-8")
    except OSError:
        return {}
    achadas = {}
    for chave, nome in nomes.items():
        m = re.search(rf'^{chave}="(.+)"', texto, re.M)
        if m:
            achadas[nome] = m.group(1).replace("$HOME", str(casa))
    return achadas


def _memoria_para_prompt():
    """O que a pessoa pediu pra lembrar (nucleo/memoria.py) e, no modo Pro, as instruções extras dela."""
    try:
        texto = memoria.para_prompt()
    except Exception:
        texto = ""
    texto += contexto_projeto_para_prompt()        # 5.1: AGENTS.md, só na conversa do terminal
    extras = modos.avancado()["instrucoes"]
    if extras:
        texto += "\nEXTRA INSTRUCTIONS FROM THE USER (they never allow destructive actions without confirmation):\n" + extras + "\n"
    return texto


def montar_system_prompt():
    """Regras (em inglês, que todo modelo entende melhor) + este PC + o
    idioma da resposta, escrito NO idioma escolhido: uma instrução na
    própria língua puxa o modelo pra responder nela."""
    return (
        SYSTEM_PROMPT.replace("{sair}", t("cmd.sair_principal"))
        + contexto_sistema()
        + _memoria_para_prompt()
        + "\n" + t("_ia") + "\n"
    )


# ============================================================
# CONVERSA
# ============================================================

# Uma conversa só, compartilhada por todos os modelos. Antes cada modelo
# tinha o seu histórico: no modo AUTO, "abra o firefox" ia pra um modelo
# e "agora feche ele" pra outro, que não sabia do que se tratava.
ARQUIVO_SESSOES = Path(
    os.environ.get("TARS_ARQUIVO_SESSOES", str(Path.home() / ".tars_sessoes.json"))
)

conversa = [{"role": "system", "content": SYSTEM_PROMPT}]

# Compatibilidade: código/testes antigos olham "sessoes".
sessoes = {}


def carregar_sessoes():
    """Lê a conversa salva. Aceita o formato antigo (um histórico por
    modelo): usa o maior deles. Devolve a lista de mensagens, já com o
    prompt de sistema atual na frente."""

    if not ARQUIVO_SESSOES.exists():
        return []

    try:
        dados = json.loads(ARQUIVO_SESSOES.read_text(encoding="utf-8"))
    except Exception as e:
        print(c(f"[openTARS] {t('msg.historico_ilegivel', arquivo=ARQUIVO_SESSOES, erro=e)}", Cor.AMARELO))
        return []

    if isinstance(dados, dict) and isinstance(dados.get("conversa"), list):
        mensagens = dados["conversa"]
    elif isinstance(dados, dict):
        listas = [v for v in dados.values() if isinstance(v, list)]
        mensagens = max(listas, key=len) if listas else []
    else:
        mensagens = []

    mensagens = [m for m in mensagens if isinstance(m, dict) and m.get("role") != "system"]
    if not mensagens:
        return []
    mensagens = [{"role": "system", "content": montar_system_prompt()}] + mensagens
    _remover_turnos_recusados(mensagens)
    return mensagens if len(mensagens) > 1 else []


def iniciar_conversa():
    """Carrega a conversa salva (terminal e interface usam isto)."""
    carregada = carregar_sessoes()
    if carregada:
        conversa[:] = carregada
    return len([m for m in conversa if m.get("role") == "user"])


_TRAVA_SESSOES = threading.Lock()


def salvar_sessoes():
    """Grava a conversa sem imagens, de forma atômica (arquivo temporário
    + rename): um travamento no meio da escrita não corrompe o histórico."""

    try:
        limpas = [
            {k: v for k, v in m.items() if k != "images"}
            for m in conversa
            if isinstance(m, dict) and m.get("role") != "system"
        ]
        with _TRAVA_SESSOES:
            memoria_lib.gravar_texto_atomico(
                ARQUIVO_SESSOES, json.dumps({"versao": 2, "conversa": limpas}, ensure_ascii=False, indent=1))
    except Exception as e:
        print(c(f"[openTARS] {t('msg.historico_nao_salvo', erro=e)}", Cor.AMARELO))


def limpar_sessao(modelo=None):
    """Apaga a conversa (comando /limpar)."""
    conversa[:] = [{"role": "system", "content": montar_system_prompt()}]
    _contexto_minimo["n"] = 0  # 5.0: o contexto que os anexos tinham subido volta ao normal
    salvar_sessoes()


def obter_sessao(modelo=None):
    """A conversa (a mesma pra qualquer modelo), com o prompt de sistema
    atualizado."""
    if not conversa or conversa[0].get("role") != "system":
        conversa.insert(0, {"role": "system", "content": ""})
    # 4.0: o Gargantua recebe o prompt curto com que foi treinado
    conversa[0]["content"] = sistema_gargantua() if eh_gargantua(modelo) else montar_system_prompt()
    return conversa


LIMITE_CHARS_RESULTADO_ANTIGO = 600

# "Não consigo abrir aplicativos", "I can't close programs", "no puedo"...
# Modelo pequeno às vezes esquece que tem ferramentas e recusa. (Texto já
# normalizado: minúsculo e sem acento.)
_PADROES_RECUSA = [re.compile(p) for p in (
    r"\bnao (consigo|posso|sou capaz|tenho como|tenho a capacidade|tenho acesso|e possivel para mim)\b",
    r"\bnao (tenho|possuo) (ferramenta|funcao|permissao|essa capacidade)",
    r"\b(i can'?t|i cannot|i am unable|i'?m unable|i don'?t have (the ability|access|a tool))\b",
    r"\bno (puedo|soy capaz|tengo (acceso|la capacidad|herramientas|forma))\b",
    r"\b(je ne (peux|suis) pas|je n'ai pas (acces|la possibilite|la capacite))\b",
    r"\b(ich kann (das |dies |es )?nicht|ich bin nicht in der lage|ich habe keinen zugriff)\b",
)]


# "Clique você na caixa e digite": a IA devolve a tarefa pro usuário
# depois de uma ferramenta falhar, em vez de usar as outras.
_PADROES_DEVOLVE = [re.compile(p) for p in (
    r"\b(you can|you could|you'?ll need to|you need to|please)\b[^.]{0,60}\b(type|click|press|focus|enter)\b",
    r"\b(voce pode|voce precisa|voce tera que|por favor)\b[^.]{0,60}\b(digit|clic|escrev|apert|foc)",
    r"\b(puedes|tendras que|necesitas)\b[^.]{0,60}\b(escrib|haz clic|puls|pulsa)",
    r"\b(vous pouvez|vous devez)\b[^.]{0,60}\b(tap|clique|saisi|appuy)",
    r"\b(sie konnen|du kannst|sie mussen)\b[^.]{0,60}\b(tipp|klick|drück|druck|eingeb)",
    r"\b(cannot|can'?t|unable to) (directly )?(interact|click|access)",
)]


def _devolveu_pro_usuario(texto):
    t = normalizar(texto or "")
    return bool(t) and len(t) < 1500 and (_parece_recusa(texto) or any(p.search(t) for p in _PADROES_DEVOLVE))


def _parece_recusa(texto):
    t = normalizar(texto or "")
    return bool(t) and len(t) < 1500 and any(p.search(t) for p in _PADROES_RECUSA)


def _remover_turnos_recusados(mensagens):
    """Tira do histórico os pedidos que terminaram em "não consigo" sem a
    IA ter tentado nenhuma ferramenta. Uma recusa dessas na conversa
    ensina o próximo modelo a recusar também (foi o que fez o qwen3:8b
    dizer que não conseguia fechar um app depois do qwen2.5-coder)."""

    sistema, resto = mensagens[:1], mensagens[1:]
    turnos, atual = [], []
    for m in resto:
        if _e_pedido_do_usuario(m) and atual:
            turnos.append(atual)
            atual = []
        atual.append(m)
    if atual:
        turnos.append(atual)

    def recusado(turno):
        if any(m.get("tool_calls") for m in turno):
            return False
        respostas = [m for m in turno if m.get("role") == "assistant"]
        return bool(respostas) and _parece_recusa(respostas[-1].get("content"))

    limpos = [m for turno in turnos if not recusado(turno) for m in turno]
    removidos = len(resto) - len(limpos)
    mensagens[:] = sistema + limpos
    return removidos


def _e_pedido_do_usuario(m):
    """Mensagem 'user' escrita pela pessoa (não as automáticas do
    openTARS, que também vão com role=user)."""
    conteudo = m.get("content") or ""
    return m.get("role") == "user" and not conteudo.startswith("[")


def _podar_historico(mensagens):
    """Mantém o histórico dentro do limite sem cortar uma tarefa no meio.

    - Corta sempre no começo de um pedido do usuário: antes o corte podia
      deixar um resultado de ferramenta "órfão" no início, sem a chamada
      que o gerou, e alguns modelos se perdiam com isso.
    - Resultados de ferramentas de pedidos antigos (saída de comando,
      listas de arquivos) são encurtados: ocupavam contexto à toa."""

    sistema, resto = mensagens[:1], mensagens[1:]

    inicios = [i for i, m in enumerate(resto) if _e_pedido_do_usuario(m)]
    if len(resto) > LIMITE_HISTORICO_MENSAGENS and inicios:
        corte = next((i for i in inicios if len(resto) - i <= LIMITE_HISTORICO_MENSAGENS), inicios[-1])
        resto = resto[corte:]
        inicios = [i - corte for i in inicios if i >= corte]

    ultimo_pedido = inicios[-1] if inicios else 0
    for i, m in enumerate(resto):
        if i < ultimo_pedido and m.get("images"):
            m.pop("images", None)  # foto de um pedido antigo: só o texto continua na conversa
        if i < ultimo_pedido and m.get("role") == "tool" and len(m.get("content", "")) > LIMITE_CHARS_RESULTADO_ANTIGO:
            m["content"] = m["content"][:LIMITE_CHARS_RESULTADO_ANTIGO] + "…(old result shortened)"

    mensagens[:] = sistema + resto
