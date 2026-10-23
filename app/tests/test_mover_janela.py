"""3.0 Miller: "arraste a janela do openTARS pro topo esquerdo".

Bug da 3.0.2: o arrasto ia até o TEXTO "openTARS" dentro da janela, em vez
de pegar a barra de título. Agora mover janela é com o gerenciador de
janelas (EWMH): move_window, e o drag_mouse manda pra lá quando o que se
arrasta é a própria janela.

Parte 1: lógica pura. Parte 2: janela de verdade num Xvfb com o Openbox
(gerenciador de janelas com moldura e barra de título), se houver."""

import os
import shutil
import subprocess
import sys
import time

if os.environ.get("DISPLAY"):
    try:
        import pyautogui  # noqa: F401
    except Exception:
        pass

from _util import carregar_tars  # noqa: E402

tars = carregar_tars()
m = tars.mouse

# ------------------------------------------------------------
# 1. Lógica
# ------------------------------------------------------------
assert m.fala_de_janela("a janela do openTARS") and m.fala_de_janela("barra de título do Firefox")
assert m.fala_de_janela("the terminal window") and not m.fala_de_janela("aba do YouTube")
assert not m.fala_de_janela("openTARS") and m.sem_palavras_de_janela("a janela do openTARS") == "openTARS"
A = (0, 32, 1920, 1048)
assert m.lugar_da_janela("topo esquerdo", A, tamanho=(800, 600)) == (0, 32, None, None)
assert m.lugar_da_janela("bottom-right", A, tamanho=(800, 600)) == (1120, 480, None, None)
assert m.lugar_da_janela("metade direita", A) == (960, 32, 960, 1048)
assert m.lugar_da_janela("left half", A) == (0, 32, 960, 1048)
assert m.lugar_da_janela("centro", A, tamanho=(800, 600)) == (560, 256, None, None)
assert m.lugar_da_janela("maximizar", A) == "maximizar" and m.lugar_da_janela("tela cheia", A) == "maximizar"
assert m.lugar_da_janela("Lixeira", A) is None
print("OK: 'janela do X' / 'barra de título' é a janela (aba não); cantos, metades, centro e maximizar na área útil")

movidas = []
tars.mover_janela = lambda nome, lugar=None, x=None, y=None, **k: movidas.append((nome, lugar)) or {
    "sucesso": True, "mensagem": "SUCCESS: moved."}
tars.ERRO_PYAUTOGUI = None
tars.encontrar_janela_por_nome = lambda nome, janelas=None: (
    {"id": 1, "titulo": "openTARS", "classe": "opentars Opentars"} if "tars" in nome.lower() else
    {"id": 2, "titulo": "YouTube - Brave", "classe": "brave-browser Brave-browser"} if "brave" in nome.lower()
    or "youtube" in nome.lower() else None)
tars._termos_para_janela = lambda nome: [nome]
for args, esperado in [
    ({"from_element": "openTARS", "to": "top-left"}, ("openTARS", "top-left")),
    ({"from_element": "a janela do openTARS", "to": "topo esquerdo"}, ("openTARS", "topo esquerdo")),
    ({"window": "openTARS", "to": "left half"}, ("openTARS", "left half")),
    ({"from_element": "barra de título", "window": "brave", "to": "right"}, ("brave", "right")),
]:
    movidas.clear()
    r = tars.executar_ferramenta("drag_mouse", args)
    assert movidas == [esperado], (args, movidas, r)
for args in ({"from_element": "YouTube tab", "window": "brave", "to": "top-left"},
             {"from_element": "aba do YouTube", "to": "top-left"},
             {"from_element": "openTARS", "to_element": "Lixeira"}):
    assert tars._janela_do_arrasto(args) is None, args
n, a, _ = tars.consertar_chamada("drag_window", {"app": "firefox", "position": "left half"})
assert n == "move_window" and a == {"window": "firefox", "to": "left half"}, (n, a)
assert "move_window" in tars.SYSTEM_PROMPT
print("OK: 'arraste o openTARS / a janela do openTARS pro topo esquerdo' vira move_window; arrastar a ABA continua arrasto")

# ------------------------------------------------------------
# 2. De verdade: Openbox (moldura + barra de título) no Xvfb
# ------------------------------------------------------------
if not (os.environ.get("DISPLAY") and shutil.which("openbox")):
    print("PULADO (parte 2): precisa de DISPLAY e do openbox\n\nTUDO OK.")
    sys.exit(0)
tars = carregar_tars()
if tars.ERRO_PYAUTOGUI:
    print(f"PULADO (parte 2): {tars.ERRO_PYAUTOGUI}\n\nTUDO OK.")
    sys.exit(0)
tars.SESSAO_GRAFICA = "x11"
wm = subprocess.Popen(["openbox"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
APP = r'''
import tkinter as tk
r = tk.Tk(className="opentars"); r.title("openTARS"); r.geometry("700x420+600+300")
tk.Label(r, text="openTARS", font=("DejaVu Sans", 28)).pack(pady=40)
r.after(60000, r.destroy); r.mainloop()
'''
app = subprocess.Popen([sys.executable, "-c", APP])
try:
    limite = time.time() + 10
    while time.time() < limite and not tars.encontrar_janela_por_nome("openTARS"):
        time.sleep(0.2)
    time.sleep(0.6)
    antes = tars.encontrar_janela_por_nome("openTARS")
    area, bordas, _tam, _pos = tars.geometria_para_mover_x(antes["id"])
    assert bordas[2] > 0, f"o openbox desenha a barra de título: {bordas}"

    r = tars.executar_ferramenta("drag_mouse", {"from_element": "a janela do openTARS", "to": "topo esquerdo"})
    depois = tars.encontrar_janela_por_nome("openTARS")
    assert r["sucesso"], r
    e, _d, c, _b = bordas
    assert (depois["x"] - e, depois["y"] - c) == (area[0], area[1]), (area, bordas, depois)
    assert (depois["largura"], depois["altura"]) == (antes["largura"], antes["altura"])
    print(f"OK: janela de verdade com moldura foi pro topo esquerdo da área útil ({area[0]}, {area[1]}); o conteúdo "
          f"(x={depois['x']}, y={depois['y']}) fica abaixo da barra de título de {c} px")

    r = tars.executar_ferramenta("move_window", {"window": "openTARS", "to": "metade direita"})
    depois = tars.encontrar_janela_por_nome("openTARS")
    assert r["sucesso"] and abs(depois["x"] - e - (area[0] + area[2] // 2)) <= 2, (r, depois, area)
    assert abs(depois["largura"] + bordas[0] + bordas[1] - area[2] // 2) <= 2, (depois, area, bordas)
    print(f"OK: move_window(metade direita) encaixa e redimensiona ({depois['largura']}x{depois['altura']})")
finally:
    app.kill()
    wm.kill()
print("\nTUDO OK.")
