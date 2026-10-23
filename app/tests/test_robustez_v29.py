"""2.9: IAs menos propensas a falhas."""

import os
from _util import carregar_tars

tars = carregar_tars()

# 1. Conserto de chamadas
n, a, nota = tars.consertar_chamada("open_app", {"app_name": "firefox"})
assert (n, a) == ("open_application", {"app": "firefox"}) and "open_app" in nota, (n, a, nota)
n, a, _ = tars.consertar_chamada("click_mouse", {"x": "120", "y": 80.6})
assert a == {"x": 120, "y": 81}, a
n, a, _ = tars.consertar_chamada("hotkey", {"keys": "ctrl+s"})
assert (n, a) == ("press_key", {"key": "ctrl+s"}), (n, a)  # 4.6: hotkey virou press_key
n, a, _ = tars.consertar_chamada("hotkey", {"keys": ["ctrl", "shift", "t"]})
assert (n, a) == ("press_key", {"key": "ctrl+shift+t"}), (n, a)
# 4.6: as ferramentas que saíram continuam funcionando pra quem ainda as conhece (Gargantua 1.1)
n, a, _ = tars.consertar_chamada("double_click", {"x": 10, "y": 20})
assert (n, a) == ("click_mouse", {"x": 10, "y": 20, "clicks": 2}), (n, a)
n, a, _ = tars.consertar_chamada("list_files", {"path": "~/Documentos"})
assert n == "execute_terminal" and a["command"] == "ls -la -- " + os.path.expanduser("~/Documentos"), (n, a)   # o ~ é expandido: entre aspas o ls procurava uma pasta chamada "~"
n, a, _ = tars.consertar_chamada("wait_seconds", {"seconds": 999})
assert (n, a) == ("execute_terminal", {"command": "sleep 5"}), (n, a)
n, a, _ = tars.consertar_chamada("pc_info", {})
assert n == "execute_terminal" and "free -h" in a["command"], (n, a)
n, a, _ = tars.consertar_chamada("move_to_trash", {"paths": ["a b.txt"]})
assert n == "execute_terminal" and a["command"] == "gio trash -- 'a b.txt'", (n, a)
assert not {"double_click", "hotkey", "list_files", "pc_info", "wait_seconds", "move_to_trash", "undo_last_action",
            "read_clipboard", "write_clipboard"} & {f["function"]["name"] for f in tars.TOOLS}
assert len(tars.TOOLS) == 19, len(tars.TOOLS)
n, a, _ = tars.consertar_chamada("type_in_element", {"text": "oi", "window": "Claude", "submit": "true"})
assert a["submit"] is True
n, a, _ = tars.consertar_chamada("serch_web", {"search_query": "lasanha"})
assert (n, a) == ("search_web", {"query": "lasanha"}), (n, a)
n, a, nota = tars.consertar_chamada("search_web", {"query": "x"})
assert nota is None
print("OK: nomes e argumentos inventados são corrigidos (open_app/app_name, '120', 'ctrl+s', 'true', erro de digitação)")

# 2. Ferramentas por tarefa
nomes = lambda tarefa: {f["function"]["name"] for f in tars.ferramentas_para(tarefa)}  # noqa: E731
assert nomes("simples") == {"open_website", "search_web", "open_application", "close_application"}
assert "execute_terminal" in nomes("tecnico") and "click_mouse" not in nomes("tecnico")
# 3.0: memória e agenda só entram quando o pedido fala delas (ferramentas_do_pedido)
todas = len([f for f in tars.TOOLS if f["function"]["name"] not in tars._FERRAMENTAS_SO_SE_PEDIDAS])
assert len(nomes("acao")) == todas and len(nomes(None)) == todas
print(f"OK: cada tarefa recebe só as ferramentas que fazem sentido (simples: 4, ação: {todas})")

# 3. "Pronto!" depois de uma ferramenta que falhou -> conserta ou conta a verdade
tars.carregar_modelo = lambda m, silencioso=False: True
tars.contexto_ia = lambda: 8192
tars.modo_modelo = "MANUAL"
tars.catalogar_modelos = lambda forcar=False: {}
roteiro = iter([
    ("tool", "open_application", {"app": "photoshop"}),
    ("texto", "Pronto! Abri o Photoshop pra você."),
    ("texto", "Não consegui abrir: o Photoshop não está instalado neste PC."),
])
recebidas, ofertas = [], []


def turno(modelo, msgs, tools, **kw):
    recebidas.append(msgs[-1]["content"])
    ofertas.append(len(tools or []))
    tipo, *resto = next(roteiro)
    if tipo == "texto":
        return {"content": resto[0], "tool_calls": []}, None
    return {"content": "", "tool_calls": [{"function": {"name": resto[0], "arguments": resto[1]}}]}, None


tars._executar_turno_streaming = turno
tars._DISPATCH_FERRAMENTAS["open_application"] = lambda a: {"sucesso": False, "mensagem": "APP NOT FOUND: 'photoshop'."}
tars.conversa = []
resposta = tars.perguntar_modelo("qwen3:8b", "abre o photoshop", tarefa="simples")
assert resposta.startswith("Não consegui"), resposta
assert any("LAST tool call FAILED" in r for r in recebidas)
assert ofertas[0] == 4, ofertas
print("OK: 'Pronto, abri!' logo depois de uma falha é barrado; a IA conta a verdade")
print("\nTUDO OK.")
