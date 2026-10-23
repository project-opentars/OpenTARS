"""2.9.2: arrastar e clicar num X pequeno com o mouse DE VERDADE (X11).

Um app Tk faz o papel do navegador: uma "aba" que só se move com arrasto
de verdade (botão apertado + movimento) e um X de 14 px que fecha a aba.
Precisa de DISPLAY e do pyautogui de verdade; sem eles, é pulado.
O Cooper é falso mas enxerga (acha o verde do X)."""

import base64
import io
import os
import subprocess
import sys
import tempfile
import time

if os.environ.get("DISPLAY"):
    try:
        import pyautogui  # noqa: F401  (o de verdade, antes do falso do _util)
    except Exception:
        pass

from PIL import Image  # noqa: E402

from _util import carregar_tars  # noqa: E402

if not os.environ.get("DISPLAY") or not hasattr(sys.modules.get("pyautogui"), "mouseDown"):
    print("PULADO: precisa de DISPLAY e do pyautogui de verdade\n\nTUDO OK.")
    sys.exit(0)

tars = carregar_tars()
if tars.ERRO_PYAUTOGUI:
    print(f"PULADO: {tars.ERRO_PYAUTOGUI}\n\nTUDO OK.")
    sys.exit(0)
tars.SESSAO_GRAFICA = "x11"
tars.acess.indisponivel = lambda: "teste"

saida = tempfile.mktemp(prefix="opentars-mouse-")
APP = r'''
import sys, tkinter as tk
saida = sys.argv[1]
def anotar(t):
    open(saida, "a").write(t + "\n")
r = tk.Tk(); r.title("Navegadorzinho"); r.geometry("900x500+200+150"); r.configure(bg="#202124")
c = tk.Canvas(r, width=900, height=500, bg="#202124", highlightthickness=0); c.pack()
aba = c.create_rectangle(300, 10, 560, 50, fill="#3c4043", outline="", tags="aba")
c.create_text(400, 30, text="YouTube", fill="white", tags="aba")
x = c.create_rectangle(530, 23, 544, 37, fill="#00ff00", outline="", tags="fechar")
c.create_rectangle(0, 60, 900, 500, fill="white", outline="")
estado = {"arrastando": False, "moveu": 0}
def fechar(e):
    anotar("FECHOU"); c.delete("aba"); c.delete("fechar")
    return "break"
def apertar(e):
    estado.update(arrastando=True, moveu=0)
def mover(e):
    if estado["arrastando"]:
        estado["moveu"] += 1
def soltar(e):
    if estado["arrastando"] and estado["moveu"] >= 5:
        anotar(f"SOLTOU {e.x_root} {e.y_root}")
        c.itemconfigure(aba, fill="#8ab4f8")  # a aba "saiu" pra outra janela
    estado["arrastando"] = False
c.tag_bind("fechar", "<Button-1>", fechar)
c.tag_bind("aba", "<ButtonPress-1>", apertar)
r.bind_all("<B1-Motion>", mover)
r.bind_all("<ButtonRelease-1>", soltar)
r.after(60000, r.destroy); r.mainloop()
'''
proc = subprocess.Popen([sys.executable, "-c", APP, saida])


def anotado():
    try:
        return open(saida).read()
    except FileNotFoundError:
        return ""


def esperar(texto, segundos=3):
    limite = time.time() + segundos
    while texto not in anotado() and time.time() < limite:
        time.sleep(0.1)
    return texto in anotado()


COOPER = "ProjectOpenTARS/cooper:latest"


def chat_cooper(modelo, prompt, formato=None, imagens=None, **kw):
    img = Image.open(io.BytesIO(base64.b64decode(imagens[0]))).convert("RGB")
    px = img.load()
    pts = [(x, y) for y in range(img.height) for x in range(img.width)
           if px[x, y][1] > 200 and px[x, y][0] < 60 and px[x, y][2] < 60]
    if not pts:
        return '{"found": false}'
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    return '{"x": %d, "y": %d}' % (round(cx / img.width * 1000), round(cy / img.height * 1000))


tars._chat_unico = chat_cooper
tars.visao_instalada = lambda: COOPER
tars._visao_estado.update(pausado_ate=0.0, quente=True, erro="")

try:
    time.sleep(1.5)
    tela = tars.tirar_print()  # o sistema de coordenadas que a IA usa
    assert tela["sucesso"], tela
    esc = tars._escala_print["x"]

    # 1. Arrastar a aba pro topo esquerdo (antes: só clicava lá)
    ax, ay = round((200 + 360) / esc), round((150 + 30) / esc)
    r = tars.executar_ferramenta("drag_mouse", {"from_x": ax, "from_y": ay, "to": "top-left"})
    assert r["sucesso"] and esperar("SOLTOU"), (r, anotado())
    _, sx, sy = [l for l in anotado().splitlines() if l.startswith("SOLTOU")][-1].split()
    m = tars.mouse.MARGEM_ANCORA
    assert abs(int(sx) - m) <= 2 and abs(int(sy) - m) <= 2, (sx, sy)
    print(f"OK: drag_mouse arrastou a aba de verdade (botão apertado + movimento) e soltou em ({sx}, {sy})")

    # 2. Fechar a aba clicando no X, com um chute 14 px fora dele
    xx, xy = round((200 + 537 + 14) / esc), round((150 + 30 + 9) / esc)
    r = tars.executar_ferramenta("click_mouse", {"x": xx, "y": xy, "target": "close X of the YouTube tab"})
    assert esperar("FECHOU") and r["sucesso"] and "changed" in r["mensagem"], (r, anotado())
    print(f"OK: click_mouse com um chute ao lado do X mirou ({r['x']}, {r['y']}) e fechou a aba")

    # 3. Clique no nada: avisa que errou
    r = tars.executar_ferramenta("click_mouse", {"x": round((200 + 800) / esc), "y": round((150 + 300) / esc)})
    assert r.get("sem_efeito") and "MISSED" in r["mensagem"], r
    print("OK: um clique que não muda nada na tela volta com o aviso de que errou")
finally:
    proc.kill()
print("\nTUDO OK.")
