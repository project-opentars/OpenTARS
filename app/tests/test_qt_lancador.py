"""5.2 (F4): a barra rápida como lançador. Vazia mostra as capacidades; "Buscar um arquivo" busca aqui mesmo e os links
dos resultados só abrem o que a busca achou (pelo número), nunca um caminho vindo de fora."""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import RAIZ  # noqa: E402,F401
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from tars_qt import barra_rapida as br  # noqa: E402

app = QApplication.instance() or QApplication([])
abertos = []
br.plataforma.abrir = abertos.append
br.busca.buscar = lambda frase: [{"caminho": "/casa/Documentos/Contrato de aluguel 2024.pdf", "nome": "Contrato de aluguel 2024.pdf",
                                  "pasta": "/casa/Documentos", "modificado": 1704000000, "trecho": "…O LOCATÁRIO obriga-se…",
                                  "sem_texto": False, "pontos": 9}] if "aluguel" in frase else []

barra = br.BarraRapida()
barra.mostrar()
app.processEvents()
assert barra.capacidades.isVisibleTo(barra) and len(barra.capacidades.findChildren(br.QPushButton)) == 6
botoes = {b.accessibleName(): b for b in barra.capacidades.findChildren(br.QPushButton)}
print("OK: vazia, a barra mostra as capacidades do mock-up e a de editar uma foto")
pedidos_foto = []
barra.editar_foto.connect(lambda: pedidos_foto.append(1))
botoes[br.t("rapido.cap.foto")].click()
assert pedidos_foto == [1] and not barra.isVisible(), "Editar uma foto fecha a barra e pede o seletor de fotos"
barra.mostrar()
print("OK: Editar uma foto fecha a barra e abre o seletor de fotos do assistente")

botoes[br.t("rapido.cap.web")].click()
assert barra.entrada.toPlainText() == br.t("rapido.pref.web") and not barra.capacidades.isVisibleTo(barra)
barra.entrada.clear()
print("OK: pesquisar na web preenche o começo do pedido e a lista some")

botoes[br.t("rapido.cap.arquivo")].click()
assert barra.modo == "arquivo"
barra.entrada.setPlainText("o contrato de aluguel de 2024")
barra._enviar()
fim = time.time() + 5
while time.time() < fim and not barra.achados:
    app.processEvents()
    time.sleep(0.02)
assert barra.achados and "Contrato de aluguel 2024.pdf" in barra._texto and "opentars-abrir:0" in barra._texto, barra._texto
barra._link(QUrl("opentars-abrir:0"))
barra._link(QUrl("opentars-pasta:0"))
barra._link(QUrl("opentars-abrir:7"))              # número que a busca não deu: nada
barra._link(QUrl("file:///etc/passwd"))            # esquema de fora: o caminho seguro ignora
assert abertos == ["/casa/Documentos/Contrato de aluguel 2024.pdf", "/casa/Documentos"], abertos
print("OK: a busca roda na barra; Abrir e Mostrar na pasta abrem só o que ela achou")

barra.entrada.setPlainText("planilha de marte")
barra._enviar()
fim = time.time() + 5
while time.time() < fim and br.t("busca.nada") not in barra._texto:
    app.processEvents()
    time.sleep(0.02)
assert br.t("busca.nada") in barra._texto
print("OK: sem resultado, diz que não achou")
print("test_qt_lancador: TUDO OK.")
