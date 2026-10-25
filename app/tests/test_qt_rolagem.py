"""5.2: a rolagem da conversa termina na última mensagem (antes sobravam centenas de pixels de vazio, porque o miolo
usava o sizeHint dos textos com quebra de linha, que passa da altura real)."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from _util import RAIZ  # noqa: E402,F401

from PySide6.QtTest import QTest  # noqa: E402

from tars_qt import conversa as c  # noqa: E402
from tars_qt.primeiro_uso import criar_aplicativo  # noqa: E402

app = criar_aplicativo(["teste"])
area = c.AreaConversa()
area.resize(900, 600)
area.show()
for i in range(6):
    area.adicionar_pessoa(f"pergunta {i}")
    m = area.adicionar_ia()
    m.acrescentar_texto("resposta **x** " * 80)
    m.fim_do_trecho()
QTest.qWait(500)
ultimo = area.itens[-1]
fundo = ultimo.mapTo(area.widget(), ultimo.rect().bottomLeft()).y()
sobra = area.widget().height() - fundo
assert area.verticalScrollBar().maximum() > 0 and sobra <= 40, sobra
area.resize(700, 400)
QTest.qWait(500)
fundo = ultimo.mapTo(area.widget(), ultimo.rect().bottomLeft()).y()
assert area.widget().height() - fundo <= 40, area.widget().height() - fundo
print("OK: a rolagem termina na última mensagem, também depois de mudar o tamanho da janela")
