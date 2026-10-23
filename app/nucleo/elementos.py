# openTARS — nucleo/elementos.py
# Clicar e escrever pelo nome: acessibilidade e, nos apps que não a oferecem, a visão da tela (o Gargantua 2).
#
# Parte do núcleo: o tars.py executa este arquivo DENTRO do próprio
# namespace (ver _carregar_nucleo), então tudo aqui é tars.<nome> e as
# partes enxergam umas às outras sem import. Os testes que trocam
# tars.<função> por uma falsa continuam valendo pra todas as partes.
# flake8: noqa

# ============================================================
# ELEMENTOS DA JANELA (árvore de acessibilidade)
# ============================================================
#
# Clicar num botão pelo NOME ("7", "=", "Salvar") em vez de print +
# coordenada: ver tars_acessibilidade.py. O print continua como plano B
# pra app que não expõe a árvore.

_acessibilidade_ligada = {"feito": False}

AVISO_SEM_ACESSIBILIDADE = (
    "The accessibility interface is not available ({motivo}). Use take_screenshot "
    "with window=<app> and click by coordinates. (To enable it: sudo apt install "
    "gir1.2-atspi-2.0 python3-gi at-spi2-core)"
)


def _dica_clique_por_nome():
    if acess.indisponivel():
        return ""
    return " To press its buttons, use click_element with the text shown on each button."


def _janela_x_do_pid(pid):
    if not pid:
        return None
    return next((j for j in listar_janelas_x() or [] if j["pid"] == pid), None)


TIMEOUT_JANELA_ACESSIVEL_SEG = 5
_abertos_sozinhos = {}  # app normalizado -> quando o openTARS tentou abrir


def _pode_abrir_sozinho(nome):
    """Abre no máximo uma vez a cada 30 s por app (uma fila de cliques não
    abre cinco calculadoras), nunca o próprio openTARS, e só se o nome
    for de um app instalado."""
    chave = normalizar(nome)
    if not chave or "tars" in chave:
        return False
    agora = time.time()
    if agora - _abertos_sozinhos.get(chave, 0) < 30:
        return False
    _abertos_sozinhos[chave] = agora
    return bool(encontrar_app(nome))


def _nota_aberto(alvo):
    return " (it was not open, so openTARS opened it first)" if alvo.get("aberto_agora") else ""


# Apps abertos que não expõem os botões (Electron/Chromium: Claude,
# Discord, VS Code, Slack...). Depois da primeira falha, click_element e
# list_elements respondem na hora com o caminho certo, em vez de a IA
# tentar nome por nome (log real: 14 cliques falhos seguidos no Claude).
_SEM_ARVORE = {}  # nome normalizado -> quando descobrimos
VALIDADE_SEM_ARVORE_SEG = 600


def _capturar_janela(nome):
    """(imagem, ox, oy, janela_x) da janela pedida, já na frente, ou None."""
    janela_x = encontrar_janela_por_nome(nome) if nome else None
    if not janela_x:
        return None
    try:
        if janela_x["id"] != janela_ativa_x():
            focar_janela_x(janela_x["id"])
            time.sleep(0.3)
        janela_x = next((j for j in listar_janelas_x() or [] if j["id"] == janela_x["id"]), janela_x)
    except Exception:
        pass
    captura = _capturar_tela()
    x0, y0 = max(0, janela_x["x"]), max(0, janela_x["y"])
    x1 = min(captura.width, janela_x["x"] + janela_x["largura"])
    y1 = min(captura.height, janela_x["y"] + janela_x["altura"])
    if x1 - x0 < 10 or y1 - y0 < 10:
        return None
    return captura.crop((x0, y0, x1, y1)), x0, y0, janela_x


# Clique pela visão (ícone sem texto): TARS_CLIQUE_POR_VISAO=0 desliga a visão nos cliques.
CLIQUE_POR_VISAO = os.environ.get("TARS_CLIQUE_POR_VISAO", "1") not in ("0", "off", "nao", "no")


def clicar_pela_visao(nome, janela):
    """Plano B do click_element: o modelo de visão olha a janela e aponta onde está 'nome'
    (botão, campo ou ícone); o openTARS clica ali. Funciona em app que não expõe
    seus botões (Electron...). None se não deu pra olhar (sem modelo de visão, sem janela)."""
    if not CLIQUE_POR_VISAO or ERRO_PYAUTOGUI or not janela:
        return None
    capturada = _capturar_janela(janela)
    if not capturada:
        return None
    imagem, ox, oy, janela_x = capturada
    ponto, _tag = localizar_com_visao(nome, imagem)
    if ponto == "ausente":
        return {"sucesso": False, "janela": janela_x["titulo"],
                "mensagem": f"Looked at '{janela_x['titulo']}' and '{nome}' is not there."}
    if not isinstance(ponto, tuple):
        _avisar_falha_da_visao()
        return None
    try:
        pyautogui.click(x=ox + ponto[0], y=oy + ponto[1])
    except Exception as e:
        return {"sucesso": False, "mensagem": f"Located '{nome}' but the click failed: {e}"}
    time.sleep(0.35)
    return {"sucesso": True, "janela": janela_x["titulo"], "elemento": nome, "mensagem": (
        f"SUCCESS: clicked where '{nome}' was located in '{janela_x['titulo']}' (x={ponto[0]}, y={ponto[1]} in "
        "the window). It was found by LOOKING at the screen, so it can be a little off: check the result "
        "(take_screenshot) before going on.")}


def _mensagem_sem_arvore(nome):
    return (
        f"'{nome}' is open, but it does not expose its buttons to the accessibility interface "
        "(common in Electron/Chromium apps such as Claude, Discord, VS Code, Slack). You CAN "
        "still use it. To write and send a message (its text box usually already has the "
        f"keyboard focus): type_in_element(text=<your text>, window='{nome}', submit=true). "
        f"To click something else: take_screenshot(window='{nome}') and click_mouse with x/y of "
        "that image plus target='<what it is>'. Do NOT use click_element or list_elements on it again, and don't ask the "
        "user to do it: do it yourself with those tools."
    )


def _digitar_na_janela(janela, texto, enviar=False):
    """Traz a janela pra frente e digita no campo que tem o foco (num app
    de chat, a caixa de mensagem). enviar=True aperta Enter no fim."""
    focada = focar_janela(janela)
    if not focada.get("sucesso"):
        return focada
    time.sleep(0.25)  # o app redesenha e devolve o foco à caixa de texto
    resultado = digitar_texto(texto or "")
    if not resultado.get("sucesso"):
        return resultado
    if enviar:
        tecla = pressionar_tecla("enter")
        if not tecla.get("sucesso"):
            return tecla
    titulo = (focada.get("janela") or {}).get("titulo") or janela
    return {"sucesso": True, "janela": titulo, "mensagem": (
        f"SUCCESS: typed the text into the focused box of '{titulo}'"
        + (" and pressed Enter to send it." if enviar else ". Use press_key('enter') to send it.")
        + " If it may have gone to the wrong place, check with take_screenshot.")}


def _marcar_sem_arvore(nome):
    if nome:
        _SEM_ARVORE[normalizar(nome)] = time.time()


def _sem_arvore(nome):
    quando = _SEM_ARVORE.get(normalizar(nome or ""))
    return quando is not None and time.time() - quando < VALIDADE_SEM_ARVORE_SEG


def _janela_acessivel(nome):
    """A janela (na árvore de acessibilidade) que a IA pediu, ou a ativa.
    Devolve (janela, erro)."""

    motivo = acess.indisponivel()
    if motivo:
        return None, AVISO_SEM_ACESSIBILIDADE.format(motivo=motivo)
    if nome and _sem_arvore(nome):
        return None, _mensagem_sem_arvore(nome)

    def procurar():
        janela_x, termos = None, ()
        if nome:
            termos = _termos_para_janela(nome)
            janela_x = encontrar_janela_por_nome(nome)
            # Só o título batendo (uma aba "Calculadora online" no
            # navegador) não basta pra dizer que é o app pedido.
            if janela_x and _pontuar_janela(janela_x, termos) < 2:
                janela_x = None
        else:
            ativa = janela_ativa_x()
            if ativa:
                janela_x = next((j for j in listar_janelas_x() or [] if j["id"] == ativa), None)
        return acess.achar_janela(
            pid=janela_x["pid"] if janela_x else None,
            titulo=janela_x["titulo"] if janela_x else None,
            termos=termos,
            ativa=not nome,
            ignorar_pids=_pids_protegidos(),
        )

    alvo = procurar()
    # Apps Qt/KDE (e alguns outros) só expõem a árvore com a
    # acessibilidade da sessão ligada: liga uma vez e procura de novo.
    if alvo is None and not _acessibilidade_ligada["feito"]:
        _acessibilidade_ligada["feito"] = True
        if acess.ativar():
            time.sleep(0.6)
            alvo = procurar()

    # A IA pulou o open_application ("clique no 1 da calculadora" com a
    # calculadora fechada): abre o app e espera a janela aparecer na
    # árvore, uma vez por app. Antes os cinco cliques falhavam em fila.
    aberta_no_x = bool(nome) and alvo is None and encontrar_janela_por_nome(nome) is not None
    if alvo is None and nome and not aberta_no_x and _pode_abrir_sozinho(nome):
        aberto = abrir_aplicativo(nome)
        if aberto.get("sucesso"):
            limite = time.time() + TIMEOUT_JANELA_ACESSIVEL_SEG
            while alvo is None and time.time() < limite:
                time.sleep(0.25)
                alvo = procurar()
            if alvo is not None:
                alvo = dict(alvo, aberto_agora=True)

    if alvo is None:
        if nome and (aberta_no_x or encontrar_janela_por_nome(nome) is not None):
            _marcar_sem_arvore(nome)
            return None, _mensagem_sem_arvore(nome)
        if nome:
            return None, (
                f"'{nome}' is not open, or does not expose its elements to the accessibility "
                "interface. If it is open, use take_screenshot with window=<app> and click by coordinates."
            )
        return None, (
            "No accessible window is in focus. Pass window=<app name>, or use "
            "take_screenshot and click by coordinates."
        )
    return alvo, None


def listar_elementos(janela=None, filtro=None):
    """Handler da ferramenta list_elements."""
    alvo, erro = _janela_acessivel(janela)
    if erro:
        return {"sucesso": False, "mensagem": erro}

    r = acess.listar(alvo, filtro)
    if not r["total"] and not r["textos"] and not filtro and janela:
        _marcar_sem_arvore(janela)
        return {"sucesso": False, "janela": alvo["titulo"], "mensagem": _mensagem_sem_arvore(janela)}
    if not r["total"] and not r["textos"]:
        return {
            "sucesso": False,
            "janela": alvo["titulo"],
            "mensagem": (
                f"'{alvo['titulo']}' exposes no clickable elements"
                + (f" matching '{filtro}'" if filtro else "")
                + ". Use take_screenshot with window=<app> and click by coordinates."
            ),
        }
    return {
        "sucesso": True,
        "janela": alvo["titulo"],
        "elementos": r["elementos"],
        "textos": r["textos"],
        "mensagem": (
            f"{r['total']} element(s) in '{alvo['titulo']}'{_nota_aberto(alvo)} (grouped by role) and the texts "
            "it shows. Press one with click_element(name=...)."
        ),
    }


def _clicar_pelo_retangulo(alvo, retangulo):
    """Plano B de click_element: elemento sem ação de acessibilidade, mas
    com posição conhecida. Só com X11 e só se a posição cair dentro da
    janela (GTK 4 informa posições relativas, que clicariam no lugar errado)."""
    if SESSAO_GRAFICA != "x11" or ERRO_PYAUTOGUI or not retangulo:
        return False
    if not acess.coordenadas_confiaveis(alvo):
        return False
    x, y, largura, altura = retangulo
    janela_x = _janela_x_do_pid(alvo.get("pid"))
    if largura <= 0 or altura <= 0 or not janela_x:
        return False
    cx, cy = x + largura // 2, y + altura // 2
    dentro = (janela_x["x"] <= cx < janela_x["x"] + janela_x["largura"]
              and janela_x["y"] <= cy < janela_x["y"] + janela_x["altura"])
    if not dentro:
        return False
    try:
        pyautogui.click(x=cx, y=cy)
        return True
    except Exception:
        return False


def clicar_elemento(nome, janela=None, papel=None):
    """Handler da ferramenta click_element."""
    nome = (nome or "").strip()
    if not nome:
        return {"sucesso": False, "mensagem": "ERROR: 'name' is empty: pass the text shown on the element."}

    alvo, erro = _janela_acessivel(janela)
    if erro:
        if janela and _sem_arvore(janela):
            por_texto = clicar_pela_visao(nome, janela)
            if por_texto:
                return por_texto
        return {"sucesso": False, "mensagem": erro}

    r = acess.clicar(alvo, nome, papel)
    if r["sucesso"]:
        textos = r.get("textos") or []
        mensagem = f"SUCCESS: clicked {r['elemento']} in '{alvo['titulo']}'{_nota_aberto(alvo)}."
        if textos:
            mensagem += " The window now shows: " + " | ".join(textos[:8])
        return {"sucesso": True, "janela": alvo["titulo"], "elemento": r["elemento"],
                "textos": textos[:8], "mensagem": mensagem}

    if not r["achou"]:
        parecidos = acess.parecidos(alvo, nome)
        if not parecidos and janela and not acess.listar(alvo, None)["total"]:
            _marcar_sem_arvore(janela)
            por_texto = clicar_pela_visao(nome, janela)
            if por_texto and por_texto["sucesso"]:
                return por_texto
            return {"sucesso": False, "janela": alvo["titulo"], "mensagem": _mensagem_sem_arvore(janela)}
        # A árvore existe mas não tem esse nome (botão desenhado à mão,
        # canvas...): tenta achar o texto na tela antes de desistir.
        por_texto = clicar_pela_visao(nome, janela or alvo.get("titulo"))
        if por_texto and por_texto["sucesso"]:
            return por_texto
        return {
            "sucesso": False,
            "janela": alvo["titulo"],
            "mensagem": (
                f"No element named '{nome}' in '{alvo['titulo']}'."
                + (f" Some of its elements: {', '.join(parecidos)}." if parecidos else "")
                + " Use list_elements to see them all, or take_screenshot to click by coordinates."
            ),
        }

    if _clicar_pelo_retangulo(alvo, r.get("retangulo")):
        return {"sucesso": True, "janela": alvo["titulo"], "elemento": r["elemento"],
                "mensagem": f"SUCCESS: clicked {r['elemento']} in '{alvo['titulo']}' (with the mouse)."}

    return {
        "sucesso": False,
        "janela": alvo["titulo"],
        "mensagem": (
            f"Found {r['elemento']} in '{alvo['titulo']}', but it cannot be pressed through "
            "accessibility. Use take_screenshot with window=<app> and click by coordinates."
        ),
    }


def escrever_em_elemento(nome, texto, janela=None, enviar=False):
    """Handler da ferramenta type_in_element."""
    barrado = _barrar_texto_para_terminal(texto, janela)
    if barrado:
        return barrado
    alvo, erro = _janela_acessivel(janela)
    if erro:
        # App aberto sem árvore (Electron). Com o nome do campo ("Reply to
        # Claude", "Pesquisar"), o Cooper acha o campo e o openTARS clica nele; sem nome,
        # ou se não achar, digita no campo que já tem o foco.
        if janela and _sem_arvore(janela):
            if (nome or "").strip():
                clicado = clicar_pela_visao(nome.strip(), janela)
                if clicado and clicado.get("sucesso"):
                    time.sleep(0.15)
                    resultado = digitar_texto(texto or "")
                    if resultado.get("sucesso") and enviar:
                        pressionar_tecla("enter")
                    if resultado.get("sucesso"):
                        resultado["mensagem"] = (
                            f"SUCCESS: clicked the field '{clicado['elemento']}' in '{clicado['janela']}' "
                            "(found by looking at the screen) and typed the text"
                            + (" and pressed Enter." if enviar else "."))
                    return resultado
            return _digitar_na_janela(janela, texto, enviar)
        return {"sucesso": False, "mensagem": erro}

    r = acess.preencher(alvo, (nome or "").strip(), texto or "")
    if r["sucesso"]:
        if enviar:
            janela_x = _janela_x_do_pid(alvo.get("pid"))
            if janela_x:
                try:
                    focar_janela_x(janela_x["id"])
                    time.sleep(0.15)
                except Exception:
                    pass
            pressionar_tecla("enter")
        return {"sucesso": True, "janela": alvo["titulo"],
                "mensagem": f"SUCCESS: wrote the text into {r['elemento']} in '{alvo['titulo']}'"
                            + (" and pressed Enter." if enviar else ".")}

    if r.get("precisa_digitar"):
        # O campo não aceita texto pela acessibilidade: traz a janela pra
        # frente (o foco do teclado é da janela ativa) e digita.
        janela_x = _janela_x_do_pid(alvo.get("pid"))
        if janela_x:
            try:
                focar_janela_x(janela_x["id"])
                time.sleep(0.2)
            except Exception:
                pass
        resultado = digitar_texto(texto or "")
        if resultado.get("sucesso"):
            if enviar:
                pressionar_tecla("enter")
            resultado["mensagem"] = (f"SUCCESS: focused {r['elemento']} in '{alvo['titulo']}' and typed the text"
                                     + (" and pressed Enter." if enviar else "."))
        return resultado

    campos = r.get("campos") or []
    return {
        "sucesso": False,
        "janela": alvo["titulo"],
        "mensagem": (
            f"No text field named '{nome}' in '{alvo['titulo']}'."
            + (f" Its fields: {', '.join(campos)}." if campos else " It has no text field exposed.")
            + " You can also click the field and use type_text."
        ),
    }
