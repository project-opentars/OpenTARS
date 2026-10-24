"""5.0 Tesseract: o assistente de primeiro uso em Qt, de ponta a ponta, sem
tela (QT_QPA_PLATFORM=offscreen) e contra um Ollama de mentira."""

import os
import stat
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["TARS_MODELO_GARGANTUA"] = "ProjectOpenTARS/Gargantua-2"

from _util import RAIZ  # noqa: F401  (raiz no sys.path, idioma de teste)

try:
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
except ImportError:
    print("test_qt_primeiro_uso: PULADO (PySide6 não instalado)")
    sys.exit(0)

import fake_ollama
import tars_i18n
import tars_primeiro_uso as pu

pasta = tempfile.mkdtemp(prefix="opentars-qt-")
os.environ["TARS_ARQUIVO_PRIMEIRO_USO"] = os.path.join(pasta, "primeiro_uso.json")
os.environ["TARS_ARQUIVO_NUVEM"] = os.path.join(pasta, "nuvem.json")

servidor, url = fake_ollama.subir(modelos=["qwen3:4b"], chave="boa")
os.environ["OLLAMA_HOST"] = url

from tars_qt.primeiro_uso import JanelaPrimeiroUso, criar_aplicativo  # noqa: E402

app = criar_aplicativo(["teste"])


def esperar(condicao, segundos=15, o_que=""):
    fim = time.time() + segundos
    while time.time() < fim:
        app.processEvents()
        if condicao():
            return
        QTest.qWait(20)
    raise AssertionError(f"tempo esgotado: {o_que}")


def passar_pelo_ollama(j):
    j.ir("ollama")
    p = j.paginas["ollama"]
    esperar(lambda: p.b_continuar.isEnabled(), o_que="Ollama encontrado")
    p.b_continuar.click()
    assert j.atual == "nuvem"


def ate_o_fim(j):
    esperar(lambda: j.paginas["gargantua"].b_continuar.isEnabled(), o_que="download do Gargantua")
    assert j.paginas["gargantua"].barra.value() == 1000
    j.paginas["gargantua"].b_continuar.click()
    assert j.atual == "teste"
    esperar(lambda: j.paginas["teste"].b_continuar.isEnabled(), o_que="teste rápido")
    j.paginas["teste"].b_continuar.click()
    if j.atual == "sistema":                     # Windows e macOS: o passo das permissões e do atalho
        j.paginas["sistema"].nav.itemAt(j.paginas["sistema"].nav.count() - 1).widget().click()
    assert j.atual == "pronto"


# --- 1) caminho padrão: só no computador ---------------------------------
tars_i18n.definir_idioma("pt_BR")
j = JanelaPrimeiroUso()
j.show()
assert j.atual == "idioma" and len(j.paginas) == 8 + ("sistema" in j.paginas)
assert j.windowTitle() == tars_i18n.t("pu.janela")
j.paginas["idioma"].continuar()                 # mantém português
assert j.atual == "modo"                         # 5.1: o modo vem logo depois do idioma
j.paginas["modo"].continuar()                    # Base, já marcado
assert j.atual == "ollama"
esperar(lambda: j.paginas["ollama"].b_continuar.isEnabled(), o_que="Ollama")
j.paginas["ollama"].b_continuar.click()
assert j.atual == "nuvem"
assert j.paginas["nuvem"].grupo.marcado() == 0, "o padrão é 'Não, só no meu computador'"
j.paginas["nuvem"].continuar()
assert j.atual == "gargantua"
ate_o_fim(j)
assert not pu.carregar_nuvem()["ativa"]
assert not pu.primeiro_uso_concluido()
assert j.paginas["pronto"].resumo_nuvem.texto.plano() == tars_i18n.t("pu.pronto.nuvem_nao")
j.terminar()
assert pu.primeiro_uso_concluido() and j.terminou
puxados = [c["model"] for m, p, c in servidor.pedidos if p == "/api/pull"]
assert puxados == ["ProjectOpenTARS/Gargantua-2"], puxados   # só o Gargantua 2 (que enxerga); o Cooper foi descontinuado

# --- 2) trocar de idioma reconstrói a janela -------------------------------
pu.marcar_concluido(False)
j2 = JanelaPrimeiroUso()
j2.show()
pt_titulo = j2.paginas["idioma"].h1.plano()
codigos = j2.paginas["idioma"].codigos
assert "en" in codigos
j2.paginas["idioma"].grupo.escolher(j2.paginas["idioma"].grupo.cartoes[codigos.index("en")])
j2.paginas["idioma"].continuar()
assert tars_i18n.idioma_atual() == "en"
assert j2.atual == "modo"
assert j2.paginas["modo"].h1.plano() == tars_i18n.t("pu.modo.titulo")
assert j2.paginas["ollama"].h1.plano() != pt_titulo
assert j2.paginas["ollama"].h1.plano() == tars_i18n.t("pu.ollama.titulo")
j2.close()
tars_i18n.definir_idioma("pt_BR")

# --- 3) com nuvem: chave inválida, depois válida, salva com modo 0600 -------
j3 = JanelaPrimeiroUso()
j3.show()
passar_pelo_ollama(j3)
nuvem = j3.paginas["nuvem"]
nuvem.grupo.escolher(nuvem.sim)
nuvem.continuar()
assert j3.atual == "chave"
c = j3.paginas["chave"]
assert c.prov_id == "ollama" and c.nota.isVisibleTo(c), "Ollama Cloud avisa que o endereço é a confirmar"
c.chips["groq"].click()
assert c.prov_id == "groq" and "groq" in c.endereco.text() and not c.nota.isVisibleTo(c)
c.continuar()                                   # sem chave: não avança
assert j3.atual == "chave" and pu.carregar_nuvem()["ativa"] is False
c.chips["outro"].click()
c.endereco.setText(url)
c.chave.setText("ruim")
c.b_testar.click()
esperar(lambda: c.b_testar.isEnabled(), o_que="teste da chave ruim")
assert c.resultado.plano() == tars_i18n.t("pu.chave.erro_chave"), c.resultado.plano()
assert "ruim" not in c.resultado.plano()
c.chave.setText("boa")
c.b_testar.click()
esperar(lambda: c.b_testar.isEnabled(), o_que="teste da chave boa")
assert c.resultado.plano() == tars_i18n.t("pu.chave.ok"), c.resultado.plano()
c.continuar()
assert j3.atual == "gargantua"
n = pu.carregar_nuvem()
assert n == {"ativa": True, "provedor": "outro", "endereco": url, "chave": "boa"}, n
assert os.name == "nt" or stat.S_IMODE(os.stat(pu.arquivo_nuvem()).st_mode) == 0o600
ate_o_fim(j3)
assert j3.paginas["pronto"].resumo_nuvem.texto.plano() == tars_i18n.t("pu.pronto.nuvem_sim", provedor="Outro")
j3.close()

# --- 4) Gargantua já instalado: não baixa de novo ----------------------------
servidor2, url2 = fake_ollama.subir(modelos=["ProjectOpenTARS/Gargantua:latest", "ProjectOpenTARS/cooper:latest"])
os.environ["OLLAMA_HOST"] = url2
j4 = JanelaPrimeiroUso()
j4.show()
passar_pelo_ollama(j4)
j4.paginas["nuvem"].continuar()
esperar(lambda: j4.paginas["gargantua"].b_continuar.isEnabled(), o_que="atalho 'já instalado'")
assert not [1 for m, p, _ in servidor2.pedidos if p == "/api/pull"], "não deve baixar de novo"
assert j4.paginas["gargantua"].h1.plano() == tars_i18n.t("pu.garg.titulo_ja")
j4.close()

# --- 5) Ollama fora do ar: oferece instalar, não avança ------------------------
os.environ["OLLAMA_HOST"] = "http://127.0.0.1:9"
j5 = JanelaPrimeiroUso()
j5.show()
j5.ir("ollama")
p5 = j5.paginas["ollama"]
esperar(lambda: p5.linha.texto.plano() != tars_i18n.t("pu.ollama.procurando"), o_que="busca do Ollama")
assert not p5.b_continuar.isEnabled()
j5.close()

for s in (servidor, servidor2):
    s.shutdown()
print("test_qt_primeiro_uso: OK")
