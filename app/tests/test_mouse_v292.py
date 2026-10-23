"""2.9.2: mouse preciso.

Casos reais que falharam na 2.9.1:
- "arrasta a aba do brave pro topo esquerdo": não existia ferramenta de
  arrastar, a IA só clicou lá;
- "fecha a aba clicando no X": clicou perto do X, não nele.

A "tela" aqui é uma imagem falsa que MUDA quando o clique/arrasto acerta,
e o Cooper falso enxerga de verdade (acha os pixels verdes do alvo), então o
teste confere mira, conferência e arrasto de ponta a ponta sem X nem modelo
instalado. (4.6: o Cooper é o único que olha a tela; sem grade, zoom nem OCR.)"""

import base64
import io
import types

from PIL import Image, ImageDraw

from _util import carregar_tars

tars = carregar_tars()
mouse = tars.mouse

VERDE = (0, 255, 0)


# ------------------------------------------------------------
# 1. Lugares da tela por nome, em 5 idiomas
# ------------------------------------------------------------
L, A = 1920, 1080
M = mouse.MARGEM_ANCORA
for nome in ("top-left", "top left", "upper left corner", "topo esquerdo", "canto superior esquerdo",
             "arriba a la izquierda", "en haut à gauche", "oben links"):
    assert mouse.ancora(nome, L, A) == (M, M), (nome, mouse.ancora(nome, L, A))
assert mouse.ancora("bottom-right", L, A) == (L - 1 - M, A - 1 - M)
assert mouse.ancora("direita", L, A) == (L - 1 - M, A // 2)
assert mouse.ancora("center", L, A) == mouse.ancora("centro da tela", L, A) == (L // 2, A // 2)
assert mouse.ancora("left half", L, A) == (L // 4, A // 2)
assert mouse.ancora("Trash", L, A) is None and mouse.ancora("YouTube tab", L, A) is None
assert all(v > 0 for v in mouse.ancora("top-left", L, A)), "canto exato dispara o FAILSAFE do pyautogui"
print("OK: 'top-left', 'topo esquerdo', 'oben links'... viram um ponto perto do canto (sem encostar nele)")

# ------------------------------------------------------------
# 2. Caminho do arrasto: sai devagar, chega exato
# ------------------------------------------------------------
pts = mouse.caminho(900, 30, 48, 48)
assert pts[-1] == (48, 48) and len(pts) >= 15
d3 = ((pts[2][0] - 900) ** 2 + (pts[2][1] - 30) ** 2) ** 0.5
assert d3 <= mouse.EMPURRAO_PX + 1, "os 3 primeiros passos só 'soltam' o item do lugar"
assert all(abs(a[0] - 900) <= abs(b[0] - 900) for a, b in zip(pts, pts[1:])), "sempre avança"
assert mouse.caminho(5, 5, 5, 5) == [(5, 5)]
print(f"OK: arrasto em {len(pts)} passos, os 3 primeiros em {d3:.0f} px (o app entende que é arrasto)")

# ------------------------------------------------------------
# 3. Tela falsa: barra de abas com um X pequeno
# ------------------------------------------------------------
X_ABA = (1000, 40)   # centro do X de fechar (14 px)
ABA = (760, 18, 1016, 62)


def tela_com_aba():
    img = Image.new("RGB", (L, A), (32, 33, 36))
    d = ImageDraw.Draw(img)
    d.rectangle(ABA, fill=(60, 64, 67))                             # a aba
    d.text((780, 32), "YouTube - Brave", fill=(230, 230, 230))       # título
    d.rectangle((X_ABA[0] - 7, X_ABA[1] - 7, X_ABA[0] + 7, X_ABA[1] + 7), fill=VERDE)  # o X
    d.rectangle((0, 70, L, A), fill=(255, 255, 255))                 # a página
    return img


estado = {"tela": tela_com_aba()}
eventos = []


class Fake:
    def size(self):
        return (L, A)

    def position(self):
        return (500, 500)

    def moveTo(self, x, y, duration=0, **k):
        eventos.append(("move", int(x), int(y)))

    def mouseDown(self, x=None, y=None, button="left"):
        eventos.append(("down", x, y))

    def mouseUp(self, x=None, y=None, button="left"):
        eventos.append(("up", x, y))
        inicio = next(e for e in reversed(eventos) if e[0] == "down")
        if ABA[0] <= inicio[1] <= ABA[2] and ABA[1] <= inicio[2] <= ABA[3]:
            estado["tela"] = Image.new("RGB", (L, A), (255, 255, 255))  # aba virou janela nova

    def click(self, x=None, y=None, button="left", **k):
        eventos.append(("click", x, y))
        if abs(x - X_ABA[0]) <= 7 and abs(y - X_ABA[1]) <= 7:        # acertou o X: aba fecha
            img = estado["tela"].copy()
            ImageDraw.Draw(img).rectangle(ABA, fill=(32, 33, 36))
            estado["tela"] = img

    def doubleClick(self, x=None, y=None, **k):
        eventos.append(("double", x, y))


tars.pyautogui = Fake()
tars.ERRO_PYAUTOGUI = None
tars.SESSAO_GRAFICA = "x11"
tars._escala_print.update(x=1.0, y=1.0, ox=0, oy=0, largura=L, altura=A, definido=True)
tars._capturar_tela = lambda: estado["tela"].copy()
tars._capturar_regiao = lambda bbox=None: estado["tela"].crop(bbox) if bbox else estado["tela"].copy()
tars.ESPERA_DEPOIS_CLIQUE_SEG = tars.PAUSA_HOVER_SEG = 0
tars.PAUSA_SEGURAR_SEG = tars.PAUSA_SOLTAR_SEG = tars.DURACAO_PASSO_ARRASTO_SEG = 0
tars.acess.indisponivel = lambda: "sem acessibilidade no teste"
COOPER = "ProjectOpenTARS/cooper:latest"


def chat_cooper(modelo, prompt, formato=None, imagens=None, **kw):
    """O Cooper falso: acha o verde (o alvo) e responde em milésimos da imagem, como o de verdade."""
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

# ------------------------------------------------------------
# 4. click_mouse com target: o Cooper mira, acerta e confere
# ------------------------------------------------------------
r = tars.executar_ferramenta("click_mouse", {"x": 1020, "y": 52, "target": "close X of the YouTube tab"})
clique = [e for e in eventos if e[0] == "click"][-1]
assert abs(clique[1] - X_ABA[0]) <= 3 and abs(clique[2] - X_ABA[1]) <= 3, (clique, r)
assert r["sucesso"] and "changed where it clicked" in r["mensagem"] and "located 'close X of the YouTube tab'" in r["mensagem"], r
print(f"OK: click_mouse(1020, 52, target='close X...') clicou em {clique[1:]} e a aba fechou")

# só o target, sem x/y: procura na tela toda
estado["tela"] = tela_com_aba()
r = tars.executar_ferramenta("click_mouse", {"target": "close X of the YouTube tab"})
clique = [e for e in eventos if e[0] == "click"][-1]
assert r["sucesso"] and abs(clique[1] - X_ABA[0]) <= 3 and abs(clique[2] - X_ABA[1]) <= 3, (clique, r)
print("OK: click_mouse(target=...) sem coordenada acha o X sozinho")

# ------------------------------------------------------------
# 5. Clique que erra é avisado (não vira "Pronto!")
# ------------------------------------------------------------
estado["tela"] = tela_com_aba()
r = tars.executar_ferramenta("click_mouse", {"x": 1025, "y": 50})
assert r.get("sem_efeito") and "MISSED" in r["mensagem"] and "target=" in r["mensagem"], r
print("OK: clique sem target que não muda nada na tela avisa que ERROU e ensina a mirar")

# sem Cooper: caiu no fundo liso ao lado do X -> encaixa no X
tars.visao_instalada = lambda: None
r = tars.executar_ferramenta("click_mouse", {"x": 1012, "y": 46, "target": "close X"})
clique = [e for e in eventos if e[0] == "click"][-1]
assert abs(clique[1] - X_ABA[0]) <= 2 and abs(clique[2] - X_ABA[1]) <= 2, (clique, r)
assert mouse.encaixar(tela_com_aba(), 900, 300) == (900, 300), "em cima de algo (a página): não mexe"
print("OK: sem o Cooper, um clique que caiu do lado do X encaixa nele")
tars.visao_instalada = lambda: COOPER

# ------------------------------------------------------------
# 6. drag_mouse: segura, arrasta de verdade, solta no lugar
# ------------------------------------------------------------
estado["tela"] = tela_com_aba()
eventos.clear()
r = tars.executar_ferramenta("drag_mouse", {"from_x": 850, "from_y": 40, "to": "top-left"})
tipos = [e[0] for e in eventos]
assert r["sucesso"] and "The screen changed" in r["mensagem"], r
assert tipos.index("down") < tipos.index("up") and tipos.count("down") == tipos.count("up") == 1
baixo = eventos[tipos.index("down")]
movs = [e for e in eventos[tipos.index("down") + 1:tipos.index("up")] if e[0] == "move"]
assert baixo[1:] == (850, 40) and eventos[tipos.index("up")][1:] == (M, M), eventos
assert len(movs) >= 15 and abs(movs[0][1] - 850) <= 6, "sai devagar do lugar"
print(f"OK: drag_mouse(aba -> 'top-left'): aperta em (850, 40), {len(movs)} movimentos, solta em ({M}, {M})")

# a origem pelo que é (o Cooper olha), sem coordenada
estado["tela"] = tela_com_aba()
eventos.clear()
r = tars.executar_ferramenta("drag_mouse", {"from_element": "close X of the tab", "to": "center"})
baixo = next(e for e in eventos if e[0] == "down")
assert r["sucesso"] and abs(baixo[1] - X_ABA[0]) <= 3 and eventos[-1][1:] == (L // 2, A // 2), (baixo, r)
print("OK: drag_mouse(from_element=..., to='center') acha a origem olhando a tela")

# nada mudou: arrasto não pegou o item -> a IA é avisada (e ensinada a mirar)
estado["tela"] = tela_com_aba()
r = tars.executar_ferramenta("drag_mouse", {"from_x": 1500, "from_y": 600, "to": "left"})
assert r.get("sem_efeito") and "NOTHING changed" in r["mensagem"] and "from_element=" in r["mensagem"], r
r = tars.executar_ferramenta("drag_mouse", {"from_x": 850, "from_y": 40})
assert not r["sucesso"] and "to='top-left'" in r["mensagem"], r
print("OK: arrasto que não muda nada vem com aviso (e como acertar); sem destino, pede o destino")

# ------------------------------------------------------------
# 7. Os nomes que os modelos inventam
# ------------------------------------------------------------
nome, args, _ = tars.consertar_chamada("drag_and_drop", {"x1": 1, "y1": 2, "x2": "30", "y2": 40})
assert nome == "drag_mouse" and args == {"from_x": 1, "from_y": 2, "to_x": 30, "to_y": 40}, (nome, args)
nome, args, _ = tars.consertar_chamada("drag", {"element": "YouTube tab", "destination": "top left", "window": "brave"})
assert nome == "drag_mouse" and args == {"from_element": "YouTube tab", "to": "top left", "window": "brave"}, args
nome, args, _ = tars.consertar_chamada("click", {"x": 1, "y": 2, "name": "close X"})
assert nome == "click_mouse" and args == {"x": 1, "y": 2, "target": "close X"}, args
assert tars._resumo_argumentos({"from_element": "YouTube tab", "to": "top-left"}) == "YouTube tab → top-left"
nomes_acao = {f["function"]["name"] for f in tars.ferramentas_para("acao")}
nomes_visao = {f["function"]["name"] for f in tars.ferramentas_para("visao")}
assert "drag_mouse" in nomes_acao and "drag_mouse" in nomes_visao
assert "drag_mouse" in tars.SYSTEM_PROMPT and "target=" in tars.SYSTEM_PROMPT
print("OK: 'drag_and_drop(x1..y2)', 'drag(element, destination)', 'click(name)' viram as ferramentas certas")

print("\nTUDO OK.")
