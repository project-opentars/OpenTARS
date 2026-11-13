"""5.3 (F7): a janela da VM na página Probes. VM, modelo e downloads de mentira; a janela de verdade (offscreen).
Confere: o que falta aparece com o botão certo; a missão mostra a tela, os passos e os sites; nada da quarentena vem para o PC
sem marcar; "Trazer" copia só o marcado e apaga o resto; "Parar" cancela."""
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
casa = tempfile.mkdtemp()
os.environ["HOME"] = casa
os.environ["TARS_SEM_ATALHO"] = "1"

from PySide6.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication, QCheckBox  # noqa: E402

app = QApplication.instance() or QApplication([])
from tars_qt import fio, tema  # noqa: E402
fio.iniciar(app)
app.setStyleSheet(tema.folha_de_estilo())
from tars_qt import vm  # noqa: E402
import tars_vm_agente as agente  # noqa: E402

vm.PASTA_LIBERADA = Path(casa) / "Downloads" / "openTARS-vm"


def esperar(condicao, segundos=10):
    fim = time.time() + segundos
    while time.time() < fim:
        app.processEvents()
        if condicao():
            return True
        time.sleep(0.02)
    raise AssertionError("tempo esgotado")


def png():
    imagem = QImage(64, 40, QImage.Format_RGB32)
    imagem.fill(QColor("red"))
    dados = QByteArray()
    buf = QBuffer(dados)
    buf.open(QIODevice.WriteOnly)
    imagem.save(buf, "PNG")
    return bytes(dados)


base = Path(casa) / "base.qcow2"
estado = {"falta": ["kvm"], "modelos": []}
janela = vm.JanelaVM(lambda: "http://motor", falta=lambda: estado["falta"], base=lambda: base,
                     instalados=lambda host: estado["modelos"],
                     construir=lambda ao_progresso, avisar: (ao_progresso(5, 10), base.write_bytes(b"x")),
                     baixar=lambda nome, host, ao_progredir: (estado["modelos"].append(nome), (True, None))[1])
janela.show()
app.processEvents()
assert janela.falta.isVisible() and "kvm" in janela.falta_texto.text() and not janela.b_comecar.isEnabled()
print("OK: sem KVM a janela diz o que falta e não deixa começar")

estado["falta"] = []
janela.conferir()
assert janela.b_base.isVisible() and not janela.b_comecar.isEnabled()
janela.b_base.click()
esperar(lambda: janela.b_pro.isVisible())
assert base.exists() and not janela.b_comecar.isEnabled()
janela.b_pro.click()
esperar(lambda: janela.b_comecar.isEnabled() and not janela.falta.isVisible())
assert agente.MODELO in estado["modelos"]
print("OK: montar a imagem e baixar o Pro pelos botões; depois Começar libera")

# a missão: a tela chega pelo decisor, os passos e os sites aparecem, os arquivos ficam em quarentena
quarentena = Path(casa) / "q"
quarentena.mkdir()
(quarentena / "notas.txt").write_text("compras")
(quarentena / "lixo.sh").write_text("rm -rf ~")
tela = Path(casa) / "tela.png"
tela.write_bytes(png())
vistos = {}
agente.por_modelo = lambda pedido, perguntar=None: (lambda t, h: {"tipo": "terminar", "resultado": "feito"})


def rodar(decisor, internet, cancelar, ao_passo):
    vistos["internet"] = internet
    decisor(str(tela), [])
    ao_passo(0, "atalho ctrl+alt+t")
    return {"resultado": "criei notas.txt", "passos": ["atalho ctrl+alt+t"], "acessos": ["example.com"], "motivo": "terminou",
            "segundos": 12, "quarentena": str(quarentena),
            "arquivos": [{"nome": n, "tamanho": (quarentena / n).stat().st_size, "caminho": str(quarentena / n)} for n in ("lixo.sh", "notas.txt")]}


janela._rodar = rodar
janela.pedido.setPlainText("crie notas.txt")
janela.b_comecar.click()
esperar(lambda: janela.saida.isVisible())
assert janela.tela.pixmap() is not None and not janela.tela.pixmap().isNull()
assert janela.passos.count() == 1 and janela.sites.item(0).text() == "example.com" and vistos["internet"] is True
assert "12 s" in janela.estado.text() and "criei notas.txt" in janela.estado.text()
caixas = [c for c in janela.saida.findChildren(QCheckBox)]
assert len(caixas) == 2 and not any(c.isChecked() for c in caixas)
print("OK: a missão mostra a tela da VM, os passos, os sites e o resultado; nada vem marcado")

next(c for c in caixas if "notas.txt" in c.text()).setChecked(True)
janela.b_trazer.click()
app.processEvents()
assert (vm.PASTA_LIBERADA / "notas.txt").read_text() == "compras"
assert not (vm.PASTA_LIBERADA / "lixo.sh").exists() and not quarentena.exists()
assert not janela.saida.isVisible()
print("OK: Trazer copia só o marcado para Downloads/openTARS-vm e apaga a quarentena")

# Parar: o evento de cancelar chega ao executor
parado = threading.Event()


def rodar_lento(decisor, internet, cancelar, ao_passo):
    parado.wait(5) if not cancelar.wait(5) else None
    return {"resultado": "", "passos": [], "acessos": [], "motivo": "cancelada" if cancelar.is_set() else "terminou",
            "segundos": 1, "quarentena": None, "arquivos": []}


janela._rodar = rodar_lento
janela.b_comecar.click()
esperar(lambda: janela.b_parar.isVisible())
janela.b_parar.click()
esperar(lambda: janela.b_comecar.isVisible())
assert vm.t("vm.motivo.cancelada") in janela.estado.text(), janela.estado.text()
print("OK: Parar cancela a missão e a janela volta a aceitar outro pedido")
janela.close()
print("TUDO OK.")
