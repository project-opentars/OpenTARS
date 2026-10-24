"""Acessibilidade no macOS pela API AX (pyobjc ApplicationServices), para o tars_acessibilidade: devolve os mesmos nomes
de papel e de estado do AT-SPI, então a varredura, a busca pelo nome e o que a IA vê são os do Linux. Precisa que a pessoa
libere o openTARS em Ajustes > Privacidade e Segurança > Acessibilidade (o macOS pergunta na primeira vez)."""

PAPEIS = {
    "AXButton": "push-button", "AXMenuButton": "push-button", "AXCheckBox": "check-box", "AXRadioButton": "radio-button",
    "AXMenuItem": "menu-item", "AXMenuBarItem": "menu", "AXMenuBar": "menu-bar", "AXMenu": "panel", "AXLink": "link",
    "AXPopUpButton": "combo-box", "AXComboBox": "combo-box", "AXRow": "list-item", "AXCell": "table-cell",
    "AXIncrementor": "spin-button", "AXSlider": "slider", "AXDisclosureTriangle": "toggle-button", "AXTextField": "entry",
    "AXTextArea": "text", "AXStaticText": "label", "AXHeading": "heading", "AXWindow": "frame", "AXSheet": "dialog",
    "AXGroup": "panel", "AXScrollArea": "scroll-pane", "AXToolbar": "tool-bar", "AXWebArea": "document-web",
    "AXList": "list", "AXTable": "table", "AXOutline": "tree", "AXImage": "image", "AXTabGroup": "page-tab-list",
    "AXSplitGroup": "split-pane",
}
SUBPAPEIS = {"AXSecureTextField": "password-text", "AXSearchField": "search-box", "AXTabButton": "page-tab",
             "AXOutlineRow": "tree-item", "AXSwitch": "switch"}
ACOES = ("AXPress", "AXPick", "AXConfirm", "AXOpen", "AXShowMenu")


def _ax():
    import ApplicationServices
    return ApplicationServices


def _attr(no, nome):
    erro, valor = _ax().AXUIElementCopyAttributeValue(no, nome, None)
    return valor if erro == 0 else None


def erro():
    try:
        AX = _ax()
    except ImportError as e:
        return f"pyobjc ApplicationServices missing ({e}); reinstall openTARS"
    # na primeira vez o macOS mostra o pedido de permissão (uma vez por abertura do openTARS)
    if not AX.AXIsProcessTrustedWithOptions({AX.kAXTrustedCheckOptionPrompt: True}):
        return ("macOS has not allowed openTARS in Accessibility yet (System Settings > Privacy & Security > "
                "Accessibility: turn on openTARS, then try again)")
    return None


def janelas():
    from AppKit import NSApplicationActivationPolicyRegular, NSWorkspace
    AX = _ax()
    saida = []
    for app in NSWorkspace.sharedWorkspace().runningApplications():
        if app.activationPolicy() != NSApplicationActivationPolicyRegular or app.isHidden():
            continue
        pid = app.processIdentifier()
        elemento = AX.AXUIElementCreateApplication(pid)
        AX.AXUIElementSetMessagingTimeout(elemento, 1.0)    # app travado não trava o openTARS
        for janela in _attr(elemento, "AXWindows") or []:
            if _attr(janela, "AXMinimized"):
                continue
            saida.append({"no": janela, "app": str(app.localizedName() or ""), "pid": pid,
                          "titulo": str(_attr(janela, "AXTitle") or ""),
                          "ativa": bool(app.isActive() and _attr(janela, "AXMain"))})
    return saida


def papel(no):
    sub = _attr(no, "AXSubrole")
    if sub in SUBPAPEIS:
        return SUBPAPEIS[sub]
    if sub in ("AXDialog", "AXSystemDialog"):
        return "dialog"
    return PAPEIS.get(str(_attr(no, "AXRole") or ""), "unknown")


def nome(no):
    for atributo in ("AXTitle", "AXDescription"):
        valor = _attr(no, atributo)
        if valor:
            return str(valor)
    if _attr(no, "AXRole") == "AXStaticText":
        return str(_attr(no, "AXValue") or "")
    return ""


def descricao(no):
    return str(_attr(no, "AXHelp") or "")


def estados(no):
    saida = {"showing", "visible"}          # a AX não diz o que está fora da tela
    if _attr(no, "AXEnabled") is not False:
        saida |= {"sensitive", "enabled"}
    if _attr(no, "AXFocused"):
        saida.add("focused")
    if _attr(no, "AXRole") in ("AXTextField", "AXTextArea"):
        erro, pode = _ax().AXUIElementIsAttributeSettable(no, "AXValue", None)
        if erro == 0 and pode:
            saida.add("editable")
    return saida


def filhos(no):
    return list(_attr(no, "AXChildren") or [])


def texto(no):
    valor = _attr(no, "AXValue")
    return str(valor) if isinstance(valor, str) else ""


def acionar(no):
    AX = _ax()
    erro, nomes = AX.AXUIElementCopyActionNames(no, None)
    nomes = list(nomes or []) if erro == 0 else []
    acao = next((a for a in ACOES if a in nomes), None)
    if acao:
        return AX.AXUIElementPerformAction(no, acao) == 0
    erro, pode = AX.AXUIElementIsAttributeSettable(no, "AXSelected", None)
    if erro == 0 and pode:                  # linha de lista sem ação: selecionar é o "clique"
        return AX.AXUIElementSetAttributeValue(no, "AXSelected", True) == 0
    return False


def retangulo(no):
    AX = _ax()
    posicao, tamanho = _attr(no, "AXPosition"), _attr(no, "AXSize")
    if posicao is None or tamanho is None:
        return None
    _ok, ponto = AX.AXValueGetValue(posicao, AX.kAXValueCGPointType, None)
    _ok, caixa = AX.AXValueGetValue(tamanho, AX.kAXValueCGSizeType, None)
    return (int(ponto.x), int(ponto.y), int(caixa.width), int(caixa.height))   # pontos da tela, os mesmos do pyautogui


def escrever(no, valor):
    return _ax().AXUIElementSetAttributeValue(no, "AXValue", valor) == 0


def focar(no):
    _ax().AXUIElementSetAttributeValue(no, "AXFocused", True)
