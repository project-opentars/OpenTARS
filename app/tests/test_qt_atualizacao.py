"""Aviso de atualização na janela Qt: o resultado vindo de outra thread tem que chegar na janela (bug do QTimer.singleShot)."""

import os
import sys
import tempfile
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CASA = tempfile.mkdtemp(prefix="opentars-casa-")
os.environ["HOME"] = CASA
os.environ["TARS_ARQUIVO_SESSOES"] = os.path.join(CASA, "sessoes.json")
os.environ["TARS_ARQUIVO_AGENDA"] = os.path.join(CASA, "agenda.json")
os.environ["TARS_ARQUIVO_NUVEM"] = os.path.join(CASA, "nuvem.json")
os.environ["TARS_ARQUIVO_PRIMEIRO_USO"] = os.path.join(CASA, "primeiro_uso.json")

from _util import RAIZ  # noqa: E402,F401

try:
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
except ImportError:
    print("test_qt_barra_rapida: PULADO (PySide6 não instalado)")
    sys.exit(0)

src = open(os.path.join(os.path.dirname(__file__), "test_qt_principal.py"), encoding="utf-8").read()
# reaproveita o Ollama de mentira e os ajustes do núcleo do teste da janela principal
import json  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

trecho = src[src.index("chats = []"):src.index("import tars_historico")]
exec(compile(trecho, "fake_ollama_inline", "exec"))

import tars_historico  # noqa: E402
from tars_i18n import t  # noqa: E402
from tars_qt.primeiro_uso import criar_aplicativo  # noqa: E402
from tars_qt.principal import JanelaPrincipal  # noqa: E402

app = criar_aplicativo(["teste"])


def esperar(cond, segundos=15, o_que=""):
    fim = time.time() + segundos
    while time.time() < fim:
        app.processEvents()
        if cond():
            return
        QTest.qWait(20)
    raise AssertionError(f"tempo esgotado: {o_que}")


historico = tars_historico.Historico(os.path.join(CASA, "historico.json"))
historico = tars_historico.Historico(os.path.join(CASA, "historico.json"))
j = JanelaPrincipal(tars, historico=historico, capturar_stdout=False)
esperar(lambda: j._modelos, o_que="modelos")
import tars_atualizacao  # noqa: E402

nova = {"versao": "06/10 19:10", "notas": "", "arquivos": {"deb": {"nome": "opentars_all.deb", "url": "https://raw.githubusercontent.com/x/y/HEAD/opentars_all.deb",
                                                              "sha256": "", "git_sha": "a" * 40, "id": "a" * 40}}}
tars_atualizacao.procurar_atualizacao = lambda *a, **k: nova
assert not j.lateral.cartao_versao.isVisibleTo(j.lateral)
j.show()
j._procurar_atualizacao()      # a busca roda em outra thread: o aviso tem que aparecer mesmo assim
esperar(lambda: j.lateral.cartao_versao.isVisibleTo(j.lateral), o_que="aviso de versão nova na barra lateral")
assert j._nova_versao is nova
print("OK: o aviso de atualização aparece vindo de outra thread")

# 25/10 (pedido do Enzo): a barra lateral só avisa e leva às Configurações; é lá que se instala
assert j.lateral.v_sub.text() == t("jp.instale_nas_config") and j.lateral.b_atualizar.text() == t("jp.ver_atualizacao")
j.lateral.atualizar.emit()
assert j.pilha.currentIndex() == 2 and j.config.pilha.currentWidget() is j.config.paginas["atualizacoes"]
pagina = j.config.paginas["atualizacoes"]
assert pagina.b_instalar.isVisibleTo(pagina) and pagina.b_instalar.text() == t("jp.atualizar")
assert "06/10 19:10" in pagina.msg.text()
print("OK: o cartão da barra lateral avisa e leva à página Atualizações, que mostra o botão de instalar")

# o clique em Atualizar da página: baixa, confere, instala e avisa (tudo falso): o andamento aparece na página
registro = []
tars_atualizacao.baixar_verificado = lambda url, destino, sha, ao_progredir=None, **k: (ao_progredir and ao_progredir(5, 10), (True, ""))[1]
tars_atualizacao.instalar_arquivo = lambda destino, **k: (True, "")
tars_atualizacao.marcar_instalada = lambda x: registro.append(x)
pagina.b_instalar.click()
esperar(lambda: registro == ["a" * 40], o_que="instalação concluída")
esperar(lambda: pagina.msg.text() == t("jp.atualizado"), o_que="texto de atualizado na página")
assert not pagina.b_instalar.isEnabled() and j.lateral.v_sub.text() == t("jp.atualizado")
print("OK: baixar e instalar mostram o andamento e o fim na página Atualizações")

# "Procurar agora" na página: acha, avisa na barra lateral e deixa instalar de lá
j.lateral.cartao_versao.hide()
j._nova_versao = None
pagina.b_instalar.hide()
pagina._procurar()
esperar(lambda: j.lateral.cartao_versao.isVisibleTo(j.lateral) and pagina.b_instalar.isVisibleTo(pagina), o_que="procurar nas Configurações")
assert j._nova_versao is nova and pagina.b_instalar.isEnabled()
print("OK: procurar nas Configurações avisa na barra lateral e instala de lá")
# 26/10: com o assistente ligado o app fica no ícone ao fechar; atualizado, ele recomeça sozinho (ou avisa, se há trabalho)
reinicios = []
j._reiniciar = lambda: reinicios.append(1)
j._atualizado_em_disco = lambda: True
os.environ.pop("TARS_SEM_ATALHO")
j.hide()
j._checar_ocioso()
assert reinicios == [1], "atualizado por fora e parado: reinicia sozinho"
j._reinicio_avisado = False
j.show()
j.pilha.setCurrentIndex(0)
j._checar_ocioso()
assert reinicios == [1] and j.faixa.destino == "reiniciar" and j.faixa.isVisibleTo(j), "com a janela aberta: só avisa, com o botão"
os.environ["TARS_SEM_ATALHO"] = "1"
print("OK: atualizado por fora, o app reinicia sozinho quando parado e avisa (com o botão) quando está em uso")
j.close()
