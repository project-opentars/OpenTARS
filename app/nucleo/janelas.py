# openTARS — nucleo/janelas.py
# Janelas abertas, foco, prints da tela ou de uma janela.
#
# Parte do núcleo: o tars.py executa este arquivo DENTRO do próprio
# namespace (ver _carregar_nucleo), então tudo aqui é tars.<nome> e as
# partes enxergam umas às outras sem import. Os testes que trocam
# tars.<função> por uma falsa continuam valendo pra todas as partes.
# flake8: noqa

# ============================================================
# JANELAS (X11 / XWayland)
# ============================================================
#
# Antes a IA só "via" a tela pelo print: não sabia se a calculadora
# tinha aberto, onde estava, nem se estava atrás de outra janela. Agora
# o openTARS lê a lista de janelas do gerenciador de janelas (padrão
# EWMH, o mesmo que a barra de tarefas usa), traz a janela certa pra
# frente e informa posição e tamanho. Usa o python-xlib que já vem
# junto com o pyautogui; sem X (Wayland puro, sem display), devolve
# lista vazia e as ferramentas explicam o motivo.

TIMEOUT_JANELA_APP_SEG = 10.0     # espera máxima pela janela de um app recém-aberto
INTERVALO_POLL_JANELA_SEG = 0.2


def _abrir_display_x():
    from Xlib import display as _xdisplay
    return _xdisplay.Display()


def _propriedade_x(d, janela, nome, tipo=None):
    from Xlib import X
    try:
        atom = d.intern_atom(nome)
        prop = janela.get_full_property(atom, tipo if tipo is not None else X.AnyPropertyType)
        return prop.value if prop else None
    except Exception:
        return None


def _texto_x(valor):
    if valor is None:
        return ""
    if isinstance(valor, bytes):
        return valor.decode("utf-8", errors="replace")
    return str(valor)


def _info_janela_x(d, raiz, janela):
    """Título, classe, pid e retângulo (pixels reais da tela) de uma
    janela de nível superior."""

    titulo = _texto_x(_propriedade_x(d, janela, "_NET_WM_NAME", d.intern_atom("UTF8_STRING")))
    if not titulo:
        try:
            titulo = _texto_x(janela.get_wm_name())
        except Exception:
            titulo = ""

    try:
        classe = " ".join(janela.get_wm_class() or ())
    except Exception:
        classe = ""

    pid = _propriedade_x(d, janela, "_NET_WM_PID")
    pid = int(pid[0]) if pid is not None and len(pid) else None

    estado = _propriedade_x(d, janela, "_NET_WM_STATE")
    minimizada = bool(estado is not None and d.intern_atom("_NET_WM_STATE_HIDDEN") in list(estado))

    geo = janela.get_geometry()
    origem = janela.translate_coords(raiz, 0, 0)

    return {
        "id": janela.id,
        "titulo": titulo,
        "classe": classe,
        "pid": pid,
        "x": -origem.x,
        "y": -origem.y,
        "largura": geo.width,
        "altura": geo.height,
        "minimizada": minimizada,
    }


ULTIMO_ERRO_X = None      # por que a leitura das janelas falhou da última vez (pro --diagnostico e pra prova do Lab)


def listar_janelas_x():
    """Janelas de aplicativo abertas, da mais antiga pra mais nova.
    None se não houver como ler as janelas (sem X); [] se não há nenhuma.
    Só precisa do python-xlib: um pyautogui que não carregou não impede de LER as janelas."""
    global ULTIMO_ERRO_X

    if SESSAO_GRAFICA == "nenhuma":
        return None
    if plataforma.sistema() != "linux":      # 5.2: Windows (ctypes) e macOS (Quartz); o nome "_x" ficou por compatibilidade
        try:
            ULTIMO_ERRO_X = None
            return plataforma.janelas()
        except Exception as e:  # noqa: BLE001
            ULTIMO_ERRO_X = f"{type(e).__name__}: {e}"
            return None

    try:
        d = _abrir_display_x()
    except Exception as e:
        ULTIMO_ERRO_X = f"{type(e).__name__}: {e}"
        return None
    ULTIMO_ERRO_X = None

    try:
        raiz = d.screen().root
        ids = _propriedade_x(d, raiz, "_NET_CLIENT_LIST")

        if ids is not None:
            janelas = [d.create_resource_object("window", int(i)) for i in ids]
            tipo_normal = d.intern_atom("_NET_WM_WINDOW_TYPE_NORMAL")
            tipo_dialogo = d.intern_atom("_NET_WM_WINDOW_TYPE_DIALOG")
        else:
            # Sem gerenciador de janelas compatível com EWMH: janelas
            # mapeadas direto na raiz.
            from Xlib import X
            janelas = [
                j for j in raiz.query_tree().children
                if j.get_attributes().map_state == X.IsViewable
            ]
            tipo_normal = tipo_dialogo = None

        resultado = []
        for janela in janelas:
            try:
                if tipo_normal is not None:
                    tipos = _propriedade_x(d, janela, "_NET_WM_WINDOW_TYPE")
                    # Barra de tarefas, papel de parede, menus: não são apps.
                    if tipos is not None and len(tipos) and not ({tipo_normal, tipo_dialogo} & set(tipos)):
                        continue
                info = _info_janela_x(d, raiz, janela)
                if info["titulo"] or info["classe"]:
                    resultado.append(info)
            except Exception:
                continue
        return resultado

    except Exception as e:
        ULTIMO_ERRO_X = f"{type(e).__name__}: {e}"
        return None

    finally:
        try:
            d.close()
        except Exception:
            pass


def janela_ativa_x():
    """id da janela em foco (ou None)."""
    if SESSAO_GRAFICA == "nenhuma":
        return None
    if plataforma.sistema() != "linux":
        try:
            return plataforma.janela_ativa()
        except Exception:  # noqa: BLE001
            return None
    try:
        d = _abrir_display_x()
    except Exception:
        return None
    try:
        valor = _propriedade_x(d, d.screen().root, "_NET_ACTIVE_WINDOW")
        return int(valor[0]) if valor is not None and len(valor) and valor[0] else None
    finally:
        d.close()


def focar_janela_x(id_janela):
    """Traz a janela pra frente (e restaura se estava minimizada), do
    mesmo jeito que clicar nela na barra de tarefas."""
    if plataforma.sistema() != "linux":
        return plataforma.focar_janela(id_janela)

    from Xlib import X, protocol

    d = _abrir_display_x()
    try:
        raiz = d.screen().root
        janela = d.create_resource_object("window", int(id_janela))
        atom_ativa = d.intern_atom("_NET_ACTIVE_WINDOW")

        if _propriedade_x(d, raiz, "_NET_SUPPORTED") is not None:
            evento = protocol.event.ClientMessage(
                window=janela,
                client_type=atom_ativa,
                data=(32, [2, X.CurrentTime, 0, 0, 0]),  # 2 = pedido de um "pager"
            )
            raiz.send_event(
                evento,
                event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask,
            )
        else:
            janela.map()
            janela.raise_window()
            janela.set_input_focus(X.RevertToParent, X.CurrentTime)
        d.sync()
    finally:
        d.close()


def fechar_janela_x(id_janela):
    """Pede pra janela fechar, como clicar no X dela: o app pode
    perguntar se quer salvar, em vez de ser encerrado à força."""
    if plataforma.sistema() != "linux":
        return plataforma.fechar_janela(id_janela)

    from Xlib import X, protocol

    d = _abrir_display_x()
    try:
        raiz = d.screen().root
        janela = d.create_resource_object("window", int(id_janela))
        evento = protocol.event.ClientMessage(
            window=janela,
            client_type=d.intern_atom("_NET_CLOSE_WINDOW"),
            data=(32, [X.CurrentTime, 2, 0, 0, 0]),
        )
        raiz.send_event(evento, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        d.sync()
    finally:
        d.close()


# ------------------------------------------------------------
# 3.0 Miller: mover/redimensionar janela pelo gerenciador de janelas
# ------------------------------------------------------------

def _enviar_mensagem_x(d, raiz, janela, tipo, dados):
    from Xlib import X, protocol
    evento = protocol.event.ClientMessage(window=janela, client_type=d.intern_atom(tipo), data=(32, dados))
    raiz.send_event(evento, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)


def _area_util_x(d, raiz):
    """(x, y, largura, altura) sem painéis/barras (_NET_WORKAREA)."""
    area = _propriedade_x(d, raiz, "_NET_WORKAREA")
    atual = _propriedade_x(d, raiz, "_NET_CURRENT_DESKTOP")
    i = int(atual[0]) if atual is not None and len(atual) else 0
    if area is not None and len(area) >= 4 * (i + 1):
        return tuple(int(v) for v in area[4 * i:4 * i + 4])
    geo = raiz.get_geometry()
    return (0, 0, geo.width, geo.height)


def _bordas_x(d, janela):
    """(esquerda, direita, cima, baixo) da moldura (_NET_FRAME_EXTENTS)."""
    valor = _propriedade_x(d, janela, "_NET_FRAME_EXTENTS")
    return tuple(int(v) for v in valor[:4]) if valor is not None and len(valor) >= 4 else (0, 0, 0, 0)


def geometria_para_mover_x(id_janela):
    """(área útil, bordas, tamanho externo, posição externa) da janela."""
    if plataforma.sistema() != "linux":
        info = next(j for j in plataforma.janelas() if j["id"] == int(id_janela))
        return plataforma.area_util(), (0, 0, 0, 0), (info["largura"], info["altura"]), (info["x"], info["y"])
    d = _abrir_display_x()
    try:
        raiz = d.screen().root
        janela = d.create_resource_object("window", int(id_janela))
        info = _info_janela_x(d, raiz, janela)
        e, di, c, b = _bordas_x(d, janela)
        return (_area_util_x(d, raiz), (e, di, c, b), (info["largura"] + e + di, info["altura"] + c + b),
                (info["x"] - e, info["y"] - c))
    finally:
        d.close()


def mover_janela_x(id_janela, x=None, y=None, largura=None, altura=None, maximizar=None):
    """Move/redimensiona pelo retângulo EXTERNO (com a moldura), ou
    maximiza (True) / restaura (False). Com EWMH (GNOME, KDE, XFCE,
    Cinnamon, Openbox...), pede ao gerenciador; sem ele, move direto."""
    if plataforma.sistema() != "linux":
        return plataforma.mover_janela(id_janela, x, y, largura, altura, maximizar)
    from Xlib import X

    d = _abrir_display_x()
    try:
        raiz = d.screen().root
        janela = d.create_resource_object("window", int(id_janela))
        ewmh = _propriedade_x(d, raiz, "_NET_SUPPORTED") is not None
        atomos = [d.intern_atom("_NET_WM_STATE_MAXIMIZED_VERT"), d.intern_atom("_NET_WM_STATE_MAXIMIZED_HORZ")]
        if maximizar is not None:
            if ewmh:
                _enviar_mensagem_x(d, raiz, janela, "_NET_WM_STATE", [1 if maximizar else 0, atomos[0], atomos[1], 2, 0])
            d.sync()
            return
        e, di, c, b = _bordas_x(d, janela)
        cliente_l = None if largura is None else max(50, int(largura) - e - di)
        cliente_a = None if altura is None else max(50, int(altura) - c - b)
        if ewmh:
            # maximizada não se move: tira o "maximizado" antes
            _enviar_mensagem_x(d, raiz, janela, "_NET_WM_STATE", [0, atomos[0], atomos[1], 2, 0])
            bandeiras = 1  # gravidade NorthWest: x/y = canto de cima-esquerda da moldura
            bandeiras |= (1 << 8) | (1 << 9)
            if cliente_l is not None:
                bandeiras |= 1 << 10
            if cliente_a is not None:
                bandeiras |= 1 << 11
            bandeiras |= 2 << 12  # pedido de um "pager" (o usuário pediu)
            _enviar_mensagem_x(d, raiz, janela, "_NET_MOVERESIZE_WINDOW",
                               [bandeiras, int(x), int(y), cliente_l or 0, cliente_a or 0])
        else:
            mudancas = {"x": int(x) + e, "y": int(y) + c}
            if cliente_l is not None:
                mudancas["width"] = cliente_l
            if cliente_a is not None:
                mudancas["height"] = cliente_a
            janela.configure(**mudancas)
        d.sync()
    finally:
        d.close()


def mover_janela(nome, lugar=None, x=None, y=None, largura=None, altura=None):
    """Handler de move_window: 'topo esquerdo', 'metade direita',
    'maximizar'... ou x/y (coordenadas do print da tela inteira)."""
    if SESSAO_GRAFICA == "nenhuma" or ERRO_PYAUTOGUI:
        return {"sucesso": False, "mensagem": f"Cannot move windows: {ERRO_PYAUTOGUI or 'no graphical session'}."}
    nome = (nome or "").strip()
    if not nome:
        return {"sucesso": False, "mensagem": "ERROR: pass window=<app or window title>."}
    alvo = encontrar_janela_por_nome(nome)
    if not alvo:
        return {"sucesso": False, "mensagem": f"No open window looks like '{nome}'. Use list_windows."}
    try:
        area, bordas, tamanho, posicao = geometria_para_mover_x(alvo["id"])
        if lugar:
            destino = mouse.lugar_da_janela(lugar, area, tamanho)
            if destino is None:
                return {"sucesso": False, "mensagem": (
                    f"ERROR: '{lugar}' is not a place I know. Use: top-left, top-right, bottom-left, "
                    "bottom-right, left, right, top, bottom, center, left half, right half, maximize, restore.")}
            if destino in ("maximizar", "restaurar"):
                mover_janela_x(alvo["id"], maximizar=destino == "maximizar")
                time.sleep(0.3)
                return {"sucesso": True, "janela": alvo["titulo"], "mensagem": (
                    f"SUCCESS: {'maximized' if destino == 'maximizar' else 'restored'} '{alvo['titulo']}'.")}
            nx, ny, nl, na = destino
        elif x is not None and y is not None:
            _usar_quadro_tela_inteira()
            nx, ny = _para_tela(x, y)
            nl = None if largura is None else _para_tela(largura, 0)[0]
            na = None if altura is None else _para_tela(0, altura)[1]
        else:
            return {"sucesso": False, "mensagem": "ERROR: say where: to='top-left' (or 'left half', 'maximize'...) "
                                                  "or x/y."}
        mover_janela_x(alvo["id"], nx, ny, nl, na)
        time.sleep(0.35)
        _usar_quadro_tela_inteira()
        depois = next((j for j in listar_janelas_x() or [] if j["id"] == alvo["id"]), None)
    except Exception as e:
        return {"sucesso": False, "mensagem": f"ERROR moving the window: {e}"}
    if depois:
        e, _d, c, _b = bordas
        px, py = _para_print(depois["x"] - e, depois["y"] - c)
        pl, pa = _para_print(depois["largura"], depois["altura"])
        onde = f" It is now at ({px}, {py}), {pl}x{pa}."
        mexeu = (depois["x"] - e, depois["y"] - c) != posicao or nl is not None
        if not mexeu and SESSAO_GRAFICA == "wayland":
            return {"sucesso": False, "mensagem": (
                f"The window manager did not move '{alvo['titulo']}' (on Wayland, only some apps accept "
                "it). Try the keyboard: super+left / super+right snap it to a half.")}
    else:
        onde = ""
    return {"sucesso": True, "janela": alvo["titulo"], "mensagem": f"SUCCESS: moved '{alvo['titulo']}'.{onde}"}


def _normalizar_titulo(texto):
    return re.sub(r"[^a-z0-9 ]+", " ", normalizar(texto or ""))


def _pontuar_janela(janela, termos):
    """Quanto uma janela combina com os termos (nome do app, binário,
    título pedido). 0 = não combina."""
    titulo = _normalizar_titulo(janela["titulo"])
    classe = _normalizar_titulo(janela["classe"])
    melhor = 0
    for termo in termos:
        t = _normalizar_titulo(termo).strip()
        if len(t) < 2:
            continue
        if t == titulo.strip() or t in classe.split():
            melhor = max(melhor, 3)
        elif len(t) < 3:
            continue          # "ai", "vi": como pedaço de texto bate com janela demais
        elif t in classe:
            melhor = max(melhor, 2)
        elif t in titulo:
            melhor = max(melhor, 1)
    return melhor


def _termos_para_janela(nome):
    """"calculadora" -> também "Calculator", "gnome-calculator"...: o
    título e a classe da janela costumam estar em inglês ou no nome do
    programa, não no nome que o usuário falou."""
    termos = [nome]
    try:
        encontrado = _buscar_app_no_sistema(nome)
    except Exception:
        encontrado = None
    if encontrado:
        termos += _termos_do_app(nome, encontrado)
    return list(dict.fromkeys(termos))


def encontrar_janela_por_nome(nome, janelas=None):
    janelas = (listar_janelas_x() or []) if janelas is None else janelas
    direta = encontrar_janela([nome], janelas)
    if direta and _pontuar_janela(direta, [nome]) >= 2:
        return direta  # o nome bate com a classe/programa, não só com um título qualquer
    termos = _termos_para_janela(nome)
    outra = encontrar_janela(termos, janelas)
    if direta and outra:
        # "calculadora": a aba "Calculadora online" do Chrome (só o título) perde pra gnome-calculator
        return outra if _pontuar_janela(outra, termos) > _pontuar_janela(direta, [nome]) else direta
    return outra or direta


def encontrar_janela(termos, janelas=None):
    """Melhor janela aberta para os termos; em empate, a mais recente."""
    janelas = (listar_janelas_x() or []) if janelas is None else janelas
    melhor, melhor_pontos = None, 0
    for janela in janelas:  # mais nova por último: >= deixa ela vencer
        pontos = _pontuar_janela(janela, termos)
        if pontos and pontos >= melhor_pontos:
            melhor, melhor_pontos = janela, pontos
    return melhor


def _janela_para_ia(janela):
    """Retângulo da janela nas mesmas coordenadas do print de tela
    inteira (o que a IA usa pra clicar)."""
    escala = _escala_tela_inteira()
    return {
        "titulo": janela["titulo"],
        "aplicativo": janela["classe"].split(" ")[-1] if janela["classe"] else "",
        "x": round(janela["x"] / escala),
        "y": round(janela["y"] / escala),
        "largura": round(janela["largura"] / escala),
        "altura": round(janela["altura"] / escala),
        "minimizada": janela["minimizada"],
    }


def listar_janelas():
    """Handler da ferramenta list_windows."""

    if ERRO_PYAUTOGUI:
        return {"sucesso": False, "mensagem": f"Cannot read the windows: {ERRO_PYAUTOGUI}."}

    janelas = listar_janelas_x()
    if not janelas:
        return {
            "sucesso": False,
            "mensagem": (
                "Could not read the window list"
                + (" (in a Wayland session only XWayland windows are visible)." if SESSAO_GRAFICA == "wayland" else ".")
            ),
        }

    _usar_quadro_tela_inteira()
    ativa = janela_ativa_x()
    lista = []
    for janela in reversed(janelas):  # mais recente primeiro
        item = _janela_para_ia(janela)
        item["em_foco"] = janela["id"] == ativa
        lista.append(item)

    return {
        "sucesso": True,
        "janelas": lista,
        "mensagem": (
            f"{len(lista)} open window(s). Positions are in full-screen screenshot "
            "coordinates; to click INSIDE a window, prefer click_element, or take a "
            "screenshot of that window first."
        ),
    }


def focar_janela(nome):
    """Handler da ferramenta focus_window."""

    if ERRO_PYAUTOGUI:
        return {"sucesso": False, "mensagem": f"Cannot control windows: {ERRO_PYAUTOGUI}."}

    janela = encontrar_janela_por_nome(nome)
    if not janela:
        return {
            "sucesso": False,
            "mensagem": f"No open window looks like '{nome}'. Use list_windows to see the windows.",
        }

    try:
        focar_janela_x(janela["id"])
        time.sleep(0.15)  # o gerenciador de janelas leva um instante
        _usar_quadro_tela_inteira()
    except Exception as e:
        return {"sucesso": False, "mensagem": f"Could not bring '{nome}' to the front: {e}"}

    return {
        "sucesso": True,
        "janela": _janela_para_ia(janela),
        "mensagem": f"SUCCESS: window '{janela['titulo']}' is in the foreground.",
    }


# Programas de captura que funcionam numa sessão Wayland (onde ler a
# tela pelo X devolve só preto), na ordem: GNOME, KDE, wlroots
# (Sway/Hyprland). O instalador recomenda o primeiro que couber.
_CAPTURADORES_WAYLAND = (
    ("gnome-screenshot", ["gnome-screenshot", "-f"]),
    ("spectacle", ["spectacle", "-b", "-n", "-f", "-o"]),
    ("grim", ["grim"]),
)

TIMEOUT_CAPTURA_SEG = 15


def _imagem_toda_preta(img):
    try:
        return img.convert("L").getextrema()[1] <= 5
    except Exception:
        return False


def _capturar_com_programa(cmd_base):
    import tempfile

    fd, caminho = tempfile.mkstemp(suffix=".png", prefix="opentars-print-")
    os.close(fd)

    try:
        subprocess.run(
            cmd_base + [caminho],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=TIMEOUT_CAPTURA_SEG,
            check=True,
        )
        with Image.open(caminho) as img:
            img.load()
            return img.copy()
    finally:
        try:
            os.unlink(caminho)
        except OSError:
            pass


def _capturar_tela():
    """Tira o print pelo caminho que funciona nesta sessão.

    X11: lê a tela direto pelo servidor X (Pillow/XCB). Não precisa de
    nenhum programa instalado. Antes o pyautogui exigia gnome-screenshot
    ou scrot, que o Ubuntu 24.04 e o Zorin 17 não trazem, e o print
    falhava num PC recém-instalado.

    Wayland: o X só enxerga janelas XWayland (o resto sai preto), então
    tenta os programas de captura do ambiente antes."""

    from PIL import ImageGrab

    erros = []

    if SESSAO_GRAFICA == "wayland":
        for programa, cmd in _CAPTURADORES_WAYLAND:
            if not shutil.which(programa):
                continue
            try:
                img = _capturar_com_programa(cmd)
                if not _imagem_toda_preta(img):
                    return img
                erros.append(f"{programa}: black image")
            except Exception as e:
                erros.append(f"{programa}: {e}")

    try:
        img = ImageGrab.grab()
        if SESSAO_GRAFICA == "wayland" and _imagem_toda_preta(img):
            raise RuntimeError("Wayland session and reading the screen through X returned a black image")
        return img
    except Exception as e:
        erros.append(str(e))

    # Último recurso: o caminho do pyautogui (usa gnome-screenshot/scrot
    # se existirem).
    try:
        return pyautogui.screenshot()
    except Exception as e:
        erros.append(str(e))

    dica = (
        " Install a screenshot tool: sudo apt install gnome-screenshot "
        "(GNOME/Zorin/Ubuntu), kde-spectacle (KDE) or grim (Sway/Hyprland)."
        if SESSAO_GRAFICA == "wayland"
        else ""
    )
    raise RuntimeError("; ".join(erros) + "." + dica)


def ver_imagem_arquivo(caminho):
    """take_screenshot(file=...): carrega uma imagem de um arquivo pra IA "ver" (o modelo de visão descreve, se o modelo
    não enxerga). Não mexe na escala de cliques: não é a tela."""
    try:
        texto = str(caminho).strip().strip("'\"")
        arquivo = Path(os.path.expanduser(texto)).resolve()
        if not arquivo.is_file():  # "home/pictures/x.png", "~/documentos/X.PNG", pasta em português ou inglês...
            try:
                achado = anexos_lib.resolver_caminho_citado(texto)
                arquivo = achado.resolve() if achado is not None else arquivo
            except Exception:
                pass
        if not arquivo.is_file():
            return {"sucesso": False, "acao": "take_screenshot",
                    "mensagem": f"File not found: {arquivo}. Ask the user for the image path, or look for it with execute_terminal."}
        with Image.open(arquivo) as img:
            img.load()
            imagem = img.convert("RGB")
        largura_original, altura_original = imagem.size
        if largura_original > LARGURA_MAXIMA_SCREENSHOT:
            imagem = imagem.resize((LARGURA_MAXIMA_SCREENSHOT, round(altura_original * LARGURA_MAXIMA_SCREENSHOT / largura_original)),
                                   Image.LANCZOS)
        buffer = io.BytesIO()
        imagem.save(buffer, format="PNG", compress_level=1)
        return {"sucesso": True, "acao": "take_screenshot", "arquivo": str(arquivo),
                "mensagem": (f"SUCCESS: image file '{arquivo.name}' loaded ({largura_original}x{altura_original}). "
                             "You will receive what it shows next. It is a picture, not the screen: do not click on it."),
                "_imagem_b64": base64.b64encode(buffer.getvalue()).decode("ascii")}
    except Exception as e:
        return {"sucesso": False, "acao": "take_screenshot", "mensagem": f"ERROR opening the image file: {e}"}


def tirar_print(janela=None, arquivo=None):
    """Captura a tela (ou só uma janela) e devolve a imagem em
    '_imagem_b64', que o loop anexa à conversa como mensagem de visão.

    Com 'janela', traz a janela pra frente e recorta só ela: a imagem
    fica menor (menos tokens) e sem redução, então os botões aparecem
    nítidos e o clique fica bem mais preciso que num print da tela
    inteira encolhida."""

    if arquivo:
        return ver_imagem_arquivo(arquivo)
    try:
        alvo = None
        if janela:
            alvo = encontrar_janela_por_nome(janela)
            if not alvo and _pode_abrir_sozinho(janela) and abrir_aplicativo(janela).get("sucesso"):
                alvo = encontrar_janela_por_nome(janela)
            if not alvo:
                return {
                    "sucesso": False,
                    "acao": "take_screenshot",
                    "mensagem": (
                        f"No open window looks like '{janela}'. Take a screenshot "
                        "without 'window' or use list_windows."
                    ),
                }
            try:
                if alvo["id"] != janela_ativa_x():
                    focar_janela_x(alvo["id"])
                    time.sleep(0.3)  # tempo de a janela ser redesenhada na frente
                # Posição pode ter mudado ao restaurar/focar.
                alvo = next((j for j in listar_janelas_x() or [] if j["id"] == alvo["id"]), alvo)
            except Exception:
                pass

        captura = _capturar_tela()
        if captura.mode != "RGB":  # só converte (e copia) se precisar
            captura = captura.convert("RGB")

        ox = oy = 0
        if alvo:
            tela_l, tela_a = captura.size
            x0, y0 = max(0, alvo["x"]), max(0, alvo["y"])
            x1 = min(tela_l, alvo["x"] + alvo["largura"])
            y1 = min(tela_a, alvo["y"] + alvo["altura"])
            if x1 - x0 > 10 and y1 - y0 > 10:
                captura = captura.crop((x0, y0, x1, y1))
                ox, oy = x0, y0
            else:
                alvo = None  # janela fora da tela: vai a tela inteira

        largura_original, altura_original = captura.size

        # Encolhe antes de codificar se a imagem for maior que o teto
        # configurado — ver LARGURA_MAXIMA_SCREENSHOT. Mantém a
        # proporção original; nunca AUMENTA uma imagem menor que o teto.
        if largura_original > LARGURA_MAXIMA_SCREENSHOT:
            razao = LARGURA_MAXIMA_SCREENSHOT / largura_original
            nova_altura = round(altura_original * razao)
            captura = captura.resize(
                (LARGURA_MAXIMA_SCREENSHOT, nova_altura),
                Image.LANCZOS,
            )

        buffer = io.BytesIO()
        # compress_level baixo troca um pouco de tamanho de arquivo
        # por velocidade de codificação — pra uma imagem que vai ser
        # descartada logo depois de analisada, isso vale a pena.
        captura.save(buffer, format="PNG", compress_level=1)

        imagem_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
        largura, altura = captura.size

        _escala_print.update(
            x=largura_original / largura,
            y=altura_original / altura,
            ox=ox,
            oy=oy,
            largura=largura,
            altura=altura,
            definido=True,
        )

        do_que = f"of the window '{alvo['titulo']}'" if alvo else "of the screen"

        return {
            "sucesso": True,
            "acao": "take_screenshot",
            "mensagem": (
                f"SUCCESS: screenshot {do_que} taken ({largura_original}x{altura_original}"
                + (f", scaled down to {largura}x{altura}" if largura != largura_original else "")
                + "). To click or move the mouse, use pixel coordinates of THIS "
                "image (origin at its top-left corner); openTARS converts them to "
                "the real screen position."
            ),
            "_imagem_b64": imagem_b64,
        }

    except Exception as e:
        return {
            "sucesso": False,
            "acao": "take_screenshot",
            "mensagem": f"ERROR taking the screenshot: {e}",
        }
