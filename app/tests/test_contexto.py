"""5.2 (F4): sugestão pelo programa em uso. Só o título e o programa decidem; desligada por padrão; "parar de sugerir
neste programa" fica guardado; o cartão não pega o foco do programa onde a pessoa escreve."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import RAIZ  # noqa: E402,F401
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tars_contexto as ctx  # noqa: E402

casos = [
    ("Escrever: (sem assunto) - Thunderbird", "Mail thunderbird", "email"),
    ("Nova mensagem - Gmail - Google Chrome", "Google-chrome google-chrome", "email"),
    ("Re: orçamento - Message (HTML)", "rctrl_renwnd32 OUTLOOK", "email"),
    ("Caixa de entrada - Gmail - Firefox", "Navigator firefox", None),       # lendo, não escrevendo
    ("relatorio.odt - LibreOffice Writer", "libreoffice-writer libreoffice", None),
    ("Untitled - Notepad", "Notepad notepad", None),
]
for titulo, classe, esperado in casos:
    assert ctx.sugestao(titulo, classe) == esperado, (titulo, classe, ctx.sugestao(titulo, classe))
assert ctx.programa("Mail thunderbird") == "thunderbird" and ctx.programa("") == ""
print("OK: e-mail sendo escrito sugere; caixa de entrada, editor e outros programas não")

assert not ctx.ligado(), "desligado por padrão"
ctx.ligar(True)
assert ctx.ligado()
ctx.silenciar("thunderbird")
ctx.silenciar("thunderbird")
assert ctx.silenciado("thunderbird") and not ctx.silenciado("outlook")
ctx.ligar(False)
print("OK: desligado por padrão; parar de sugerir num programa fica guardado")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402
from tars_qt.sugestao import CartaoSugestao  # noqa: E402
app = QApplication.instance() or QApplication([])
cartao = CartaoSugestao()
sinais = []
cartao.revisar.connect(lambda: sinais.append("revisar"))
cartao.silenciar.connect(lambda: sinais.append("silenciar"))
cartao.mostrar("email")
assert cartao.isVisible() and cartao.windowFlags() & Qt.WindowDoesNotAcceptFocus
botoes = {b.text(): b for b in cartao.findChildren(QPushButton)}
botoes[ctx.tars_i18n.t("ctx.revisar")].click()
botoes[ctx.tars_i18n.t("ctx.parar")].click()
botoes[ctx.tars_i18n.t("ctx.agora_nao")].click()
assert sinais == ["revisar", "silenciar"] and not cartao.isVisible(), sinais
print("OK: o cartão não pega o foco; Revisar e Parar avisam a janela; Agora não fecha")
print("test_contexto: TUDO OK.")
