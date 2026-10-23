#!/usr/bin/env python3
"""Imagem que o modelo manda no Markdown (`![](caminho)`): só arquivo local vira figura; o resto nunca é carregado."""
import os, sys, tempfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from PySide6.QtGui import QImage, QColor
    from PySide6.QtWidgets import QApplication
except ImportError:
    print("test_qt_imagem: PULADO (PySide6 não instalado)")
    sys.exit(0)
app = QApplication.instance() or QApplication([])
from tars_qt import conversa, tema
app.setStyleSheet(tema.folha_principal() if hasattr(tema, "folha_principal") else "")

pasta = tempfile.mkdtemp(prefix="opentars-img-")
grande = os.path.join(pasta, "foto grande.png")
pequena = os.path.join(pasta, "icone.png")
for caminho, w, h in ((grande, 1600, 1200), (pequena, 64, 48)):
    im = QImage(w, h, QImage.Format_RGB32); im.fill(QColor("#5FD97A")); assert im.save(caminho)
texto_falso = os.path.join(pasta, "nota.txt"); open(texto_falso, "w").write("x")
quebrada = os.path.join(pasta, "quebrada.png"); open(quebrada, "w").write("não sou uma imagem")

# 1. o que vira figura e o que não vira
assert conversa.caminho_de_imagem(grande) and conversa.caminho_de_imagem(pequena)
assert conversa.caminho_de_imagem(f"<{grande}>"), "com sinais < >"
assert conversa.caminho_de_imagem("file://" + pequena.replace(" ", "%20")), "file:// e %20"
for ruim in ("https://exemplo.com/a.png", "http://127.0.0.1/a.png", "data:image/png;base64,AAAA", "foto.png",
             "../foto.png", os.path.join(pasta, "nao-existe.png"), texto_falso, pasta, "ftp://x/a.png"):
    assert conversa.caminho_de_imagem(ruim) is None, ruim
print("OK: só arquivo local de imagem existente passa")

# 2. partir em blocos
p = conversa.partir_em_blocos(f"Olha:\n![minha foto]({pequena})\nE pronto.")
assert [x[0] for x in p] == ["texto", "imagem", "texto"], p
assert str(p[1][1]) == pequena and p[1][2] == "minha foto"
p = conversa.partir_em_blocos(f"```\n![nao]({pequena})\n```\n![a]({pequena}) e ![b]({grande} \"título\")")
assert [x[0] for x in p] == ["codigo", "imagem", "texto", "imagem"], [x[0] for x in p]
assert "![nao]" in p[0][1], "dentro de cerca de código não vira figura"
r = conversa.partir_em_blocos("![remota](https://exemplo.com/rastreio.png) fim")
assert [x[0] for x in r] == ["texto"] and "![" not in r[0][1] and "[remota](https://exemplo.com/rastreio.png)" in r[0][1], r
print("OK: texto, imagem e código na ordem; remota vira link comum")

# 3. o widget: reduzida para caber, sem carregar a imagem inteira
b = conversa.BlocoTexto()
b.acrescentar(f"Aqui:\n\n![grande]({grande})\n\n![pequena]({pequena})\n\n![quebrada]({quebrada})")
b.concluir()
figs = [w for w in b._pecas if isinstance(w, conversa.ImagemIA)]
assert len(figs) == 3, len(figs)
g, pq, q = figs
assert g.pixmap().width() <= 640 and g.pixmap().height() <= 480 and g.pixmap().width() * 3 == g.pixmap().height() * 4 or abs(g.pixmap().width() / g.pixmap().height() - 4 / 3) < 0.02
assert (pq.pixmap().width(), pq.pixmap().height()) == (64, 48), "pequena não é ampliada"
assert q.pixmap() is None or q.pixmap().isNull()
assert q.text() == "quebrada" and q.property("papel") == "aviso-linha", "arquivo que não abre mostra o texto"
assert g.toolTip() == "foto grande.png" and g.accessibleName() == "grande"
print("OK: figura reduzida, pequena intacta, arquivo quebrado vira texto")

# 4. resposta só com texto continua igual; imagem remota sozinha não gera figura
b2 = conversa.BlocoTexto(); b2.acrescentar("oi **tudo**"); b2.concluir()
assert not b2._pecas and b2.rotulo.text() == "oi **tudo**"
b3 = conversa.BlocoTexto(); b3.acrescentar("![x](https://exemplo.com/a.png)"); b3.concluir()
assert not b3._pecas and "![" not in b3.rotulo.text()
print("test_qt_imagem: TUDO OK.")
