"""5.2: o painel das ações de texto (tars_qt/acoes.py) com um Ollama de mentira: o pedido segue o contrato do treino, a
tradução escolhe o sentido pelo idioma do trecho, perguntar não cola nada de volta, sem trecho só explica, e o "colar" põe o
resultado, aperta colar e devolve o que a pessoa tinha copiado."""
import os
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CASA = tempfile.mkdtemp(prefix="opentars-acoes-")
os.environ["XDG_CONFIG_HOME"] = os.path.join(CASA, ".config")
os.environ["TARS_ARQUIVO_CONFIG"] = os.path.join(CASA, "config.json")
from _util import RAIZ  # noqa: E402,F401

try:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
except ImportError:
    print("test_qt_acoes: PULADO (PySide6 não instalado)")
    sys.exit(0)

import fake_ollama  # noqa: E402
import tars_acoes_texto as acoes_lib  # noqa: E402
import tars_assistente as assistente  # noqa: E402
import tars_plataforma as plataforma  # noqa: E402
from tars_qt import fio  # noqa: E402
from tars_qt.acoes import PainelAcoes  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
fio.iniciar(app)
LITE, PRINCIPAL = "ProjectOpenTARS/Gargantua-2:lite", "ProjectOpenTARS/Gargantua-2:latest"
servidor, url = fake_ollama.subir(modelos=[LITE, PRINCIPAL], resposta="Olá, pessoal! Vocês me enviam o relatório até sexta?")


def esperar(condicao, limite=5):
    fim = time.time() + limite
    while time.time() < fim and not condicao():
        QTest.qWait(30)
    return condicao()


def ultimo_chat():
    return [c for m, p, c in servidor.pedidos if p == "/api/chat"][-1]


TEXTO = "Oi pessoal, queria saber se vcs conseguem me mandar o relatorio ate sexta"
painel = PainelAcoes(url, [LITE, PRINCIPAL], LITE, PRINCIPAL)
painel.abrir(TEXTO)
assert painel.isVisible() and painel.aba == "reescrever" and painel.opcao == "corrigir"
assert esperar(lambda: painel.resultado.startswith("Olá, pessoal")), painel.saida.toPlainText()
corpo = ultimo_chat()
assert corpo["model"] == PRINCIPAL and corpo["think"] is False and "keep_alive" not in corpo
assert corpo["messages"][0]["content"] == acoes_lib.SISTEMA_ACAO_TEXTO
assert corpo["messages"][1]["content"] == acoes_lib.pedido("corrigir", "pt_BR", TEXTO), corpo["messages"][1]["content"]
assert "Gargantua-2" in painel.modelo.text() and "ProjectOpenTARS" not in painel.modelo.text()
print("OK: reescrever corrige com o Gargantua 2, no contrato do treino (system fixo e <texto>)")

painel.escolher_aba("traduzir")
assert painel.opcao == "para_en"
esperar(lambda: len([1 for m, p, c in servidor.pedidos if p == "/api/chat"]) >= 2)
assert ultimo_chat()["messages"][1]["content"].startswith("Traduza o texto para o inglês.")
painel.abrir("The meeting was moved to Thursday at 2 p.m.")
painel.escolher_aba("traduzir")
assert painel.opcao == "para_pt"
assert esperar(lambda: painel.resultado)
QTest.qWait(300)       # o pedido do "reescrever" que o abrir() disparou também já chegou
print("OK: traduzir escolhe o sentido pelo idioma do trecho")

servidor.resposta = "Em até 30 dias."
painel.escolher_aba("perguntar")
assert not painel.botao_substituir.isVisible() and painel.linha_pergunta.isVisible()
antes = len(servidor.pedidos)
painel.rodar()
QTest.qWait(200)
assert len(servidor.pedidos) == antes, "sem pergunta não pede nada"
painel.pergunta.setText("Quando é a reunião?")     # keyClicks não aceita acento
QTest.keyClick(painel.pergunta, Qt.Key_Return)
assert esperar(lambda: painel.resultado == "Em até 30 dias.")
assert "Question: Quando é a reunião?" in ultimo_chat()["messages"][1]["content"]
print("OK: perguntar manda a pergunta junto e não oferece substituir")

assert acoes_lib.escolher_modelo([LITE, PRINCIPAL], LITE, PRINCIPAL) == PRINCIPAL
assert acoes_lib.escolher_modelo([LITE], LITE, PRINCIPAL) == LITE
assert acoes_lib.escolher_modelo([], LITE, PRINCIPAL) == PRINCIPAL
print("OK: o Gargantua 2 quando instalado (prova das ações: 71/76 contra 56/76 do Lite); sem ele, o Lite")

colados = []
painel.substituir.connect(colados.append)
painel.abrir(TEXTO)
servidor.resposta = "Texto novo."
esperar(lambda: painel.resultado == "Texto novo.")
painel.botao_substituir.click()
assert colados == ["Texto novo."] and not painel.isVisible()
painel.abrir("")
assert painel.trecho.text() and not painel.botao_substituir.isVisible() and not painel.linha_pergunta.isVisible()
QTest.keyClick(painel, Qt.Key_Escape)
assert not painel.isVisible()
print("OK: substituir entrega o resultado e fecha; sem trecho só explica; Esc fecha")

servidor.erro_no_chat = "model not found"
painel.abrir(TEXTO)
assert esperar(lambda: "model not found" in painel.saida.toPlainText()), painel.saida.toPlainText()
assert painel.resultado == ""
servidor.erro_no_chat = ""
print("OK: erro do Ollama aparece no painel e não vira resultado")

area = {"texto": "o que a pessoa tinha copiado"}
teclas = []
plataforma.ler_area_de_transferencia = lambda: area["texto"]
plataforma.escrever_area_de_transferencia = lambda texto: area.update(texto=texto)
plataforma.teclas_de_colar = lambda: ("ctrl", "v")
acoes_lib.colar("resultado", lambda *k: teclas.append(k), esperar=0, restaurar_depois=0.1)
assert teclas == [("ctrl", "v")] and area["texto"] == "resultado"
time.sleep(0.3)
assert area["texto"] == "o que a pessoa tinha copiado"
print("OK: colar põe o resultado, aperta colar e devolve a área de transferência")
# o assistente residente: ligar carrega (keep_alive -1) e guarda; as ações passam a manter o modelo; desligar descarrega
assert not assistente.ligado()
assistente.ligar(True, url, PRINCIPAL)
gerar = [c for m, p, c in servidor.pedidos if p == "/api/generate"]
assert gerar[-1] == {"model": PRINCIPAL, "keep_alive": -1} and assistente.ligado(), gerar
painel.abrir(TEXTO)
esperar(lambda: painel.resultado)
assert ultimo_chat()["keep_alive"] == -1
assistente.ligar(False, url, PRINCIPAL)
assert [c for m, p, c in servidor.pedidos if p == "/api/generate"][-1]["keep_alive"] == 0 and not assistente.ligado()
assert assistente.iniciar_com_sistema(True) and "--residente" in assistente.comando_residente()
assert "--residente" in plataforma.arquivo_autostart(assistente.NOME_AUTOSTART).read_text() and assistente.inicia_com_sistema()
assert not assistente.iniciar_com_sistema(False) and not assistente.inicia_com_sistema()
print("OK: assistente ligado mantém o modelo na memória; início com o sistema sobe com --residente")
servidor.shutdown()
print("test_qt_acoes: TUDO OK.")
