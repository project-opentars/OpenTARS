"""Acessibilidade no Windows pela UI Automation (pacote uiautomation), para o tars_acessibilidade: devolve os mesmos nomes
de papel e de estado do AT-SPI ("push-button", "showing"...), então a varredura, a busca pelo nome e o que a IA vê são os
do Linux. Cada thread que fala com a UI Automation precisa do COM iniciado: _auto() cuida disso."""
import threading

PAPEIS = {
    "ButtonControl": "push-button", "SplitButtonControl": "push-button", "CheckBoxControl": "check-box",
    "RadioButtonControl": "radio-button", "MenuItemControl": "menu-item", "MenuControl": "panel", "MenuBarControl": "menu-bar",
    "HyperlinkControl": "link", "TabItemControl": "page-tab", "ComboBoxControl": "combo-box", "ListItemControl": "list-item",
    "TreeItemControl": "tree-item", "DataItemControl": "table-cell", "SpinnerControl": "spin-button", "SliderControl": "slider",
    "EditControl": "entry", "DocumentControl": "document-text", "TextControl": "label", "HeaderControl": "heading",
    "HeaderItemControl": "heading", "StatusBarControl": "status-bar", "ToolTipControl": "tooltip", "WindowControl": "frame",
    "PaneControl": "panel", "GroupControl": "panel", "ToolBarControl": "tool-bar", "ListControl": "list", "TreeControl": "tree",
    "TableControl": "table", "DataGridControl": "table", "TabControl": "page-tab-list", "ImageControl": "image",
    "TitleBarControl": "title-bar", "ScrollBarControl": "scroll-bar", "ProgressBarControl": "progress-bar",
}
_local = threading.local()


def _auto():
    import uiautomation as auto
    if not getattr(_local, "com", False):
        import comtypes
        try:
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except OSError:
            pass                    # a thread já tinha o COM (a da janela Qt, por exemplo)
        _local.com = True
    return auto


def erro():
    try:
        _auto()
    except Exception as e:  # noqa: BLE001
        return f"UI Automation not available ({type(e).__name__}: {e}); reinstall openTARS"
    return None


def janelas():
    """As janelas da barra de tarefas (as mesmas da lista de janelas do app), com o processo de verdade do app."""
    from . import windows
    auto = _auto()
    reais = {j["id"]: j for j in windows.janelas()}
    ativa = windows.janela_ativa()
    saida = []
    for janela in auto.GetRootControl().GetChildren():
        info = reais.get(janela.NativeWindowHandle)
        if info:
            saida.append({"no": janela, "app": info["classe"].split(" ", 1)[-1], "pid": info["pid"],
                          "titulo": janela.Name or info["titulo"], "ativa": info["id"] == ativa})
    return saida


def _padrao(no, nome):
    auto = _auto()
    try:
        return no.GetPattern(getattr(auto.PatternId, nome))
    except Exception:  # noqa: BLE001
        return None


def papel(no):
    _auto()
    tipo = no.ControlTypeName
    if tipo == "EditControl" and no.IsPassword:
        return "password-text"
    if tipo == "DocumentControl":       # documento editável (Bloco de Notas, WordPad) é campo; o de uma página web, não
        valor = _padrao(no, "ValuePattern")
        if valor is not None and not valor.IsReadOnly:
            return "text"
    return PAPEIS.get(tipo, "unknown")


def nome(no):
    _auto()
    return no.Name or ""


def descricao(no):
    _auto()
    return no.HelpText or ""


def estados(no):
    _auto()
    saida = set()
    if not no.IsOffscreen:
        saida |= {"showing", "visible"}
    if no.IsEnabled:
        saida |= {"sensitive", "enabled"}
    if no.HasKeyboardFocus:
        saida.add("focused")
    if papel(no) == "text":
        saida.add("editable")
    return saida


def filhos(no):
    _auto()
    return no.GetChildren()


def texto(no):
    valor = _padrao(no, "ValuePattern")
    if valor is not None:
        return valor.Value or ""
    documento = _padrao(no, "TextPattern")
    if documento is not None:
        return documento.DocumentRange.GetText(200) or ""
    return ""


def acionar(no):
    """A ação padrão, como um leitor de tela: invocar (botão), alternar (caixa), selecionar (item), abrir (menu)."""
    tentativas = (("InvokePattern", lambda p: p.Invoke(waitTime=0)), ("TogglePattern", lambda p: p.Toggle(waitTime=0)),
                  ("SelectionItemPattern", lambda p: p.Select(waitTime=0)),
                  ("ExpandCollapsePattern", lambda p: p.Collapse(waitTime=0) if p.ExpandCollapseState == 1
                   else p.Expand(waitTime=0)),
                  ("LegacyIAccessiblePattern", lambda p: p.DoDefaultAction(waitTime=0)))
    for padrao, fazer in tentativas:
        p = _padrao(no, padrao)
        if p is not None:
            try:
                fazer(p)
                return True
            except Exception:  # noqa: BLE001
                continue
    return False


def retangulo(no):
    _auto()
    r = no.BoundingRectangle
    return (r.left, r.top, r.width(), r.height())


def escrever(no, valor_novo):
    valor = _padrao(no, "ValuePattern")
    if valor is None or valor.IsReadOnly:
        return False
    valor.SetValue(valor_novo, waitTime=0)
    return True


def focar(no):
    _auto()
    no.SetFocus()
