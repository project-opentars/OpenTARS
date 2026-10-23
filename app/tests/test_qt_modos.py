"""5.1: os modos na janela de verdade (offscreen, Ollama de mentira). O Lite esconde histórico, memória, escolha de
modelo e as páginas avançadas; o Pro mostra tudo; trocar o modo em Configurações > Geral muda a janela na hora; as
páginas Ajustes avançados e Diagnóstico gravam e leem o que devem."""
import os
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CASA = tempfile.mkdtemp(prefix="opentars-modos-qt-")
os.environ["HOME"] = CASA
os.environ["TARS_ARQUIVO_SESSOES"] = os.path.join(CASA, "sessoes.json")
os.environ["TARS_ARQUIVO_NUVEM"] = os.path.join(CASA, "nuvem.json")
os.environ["TARS_ARQUIVO_PRIMEIRO_USO"] = os.path.join(CASA, "primeiro_uso.json")
os.environ["TARS_ARQUIVO_CONFIG"] = os.path.join(CASA, "config.json")

from _util import RAIZ  # noqa: E402,F401

try:
    from PySide6.QtTest import QTest
except ImportError:
    print("test_qt_modos: PULADO (PySide6 não instalado)")
    sys.exit(0)

import fake_ollama  # noqa: E402

servidor, url = fake_ollama.subir(modelos=["qwen3:4b"])
os.environ["OLLAMA_HOST"] = url

from _util import carregar_tars  # noqa: E402

tars = carregar_tars()
tars.avisos_de_ambiente = lambda: []
tars.detectar_gpu = lambda forcar=False: None
tars.aquecer_ajudante = lambda: None

import tars_historico  # noqa: E402
import tars_modos as modos  # noqa: E402
from tars_qt.configuracoes import ultimas_ferramentas  # noqa: E402
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


modos.definir_modo("lite")
j = JanelaPrincipal(tars, historico=tars_historico.Historico(os.path.join(CASA, "historico.json")), capturar_stdout=False)
j.resize(1200, 780)
j.show()
esperar(lambda: j._modelos, o_que="modelos")
cfg = j.config
assert not j.lateral.lista_w.isVisibleTo(j) and not j.lateral.caixa_busca.isVisibleTo(j), "Lite: sem histórico"
assert not j.lateral.b_memoria.isVisibleTo(j) and not j.cabecalho.pilula.isVisibleTo(j), "Lite: sem memória e seletor"
assert j.lateral.versao.text() == tars.VERSAO_EXIBIDA
j.abrir_config("avancado")                        # página escondida no Lite: cai na Geral
assert cfg.pilha.currentWidget() is cfg.paginas["geral"]
visiveis = {n for n, b in cfg.nav.items() if b.isVisibleTo(cfg)}
assert visiveis == {"geral", "assistente", "voz", "atualizacoes", "sobre"}, visiveis   # 5.2: o assistente vale em todo modo
print("OK: o Lite esconde histórico, memória, seletor de modelo e as páginas que não são dele")

# trocar para Pro pela própria tela
cfg.paginas["geral"].chips_modo["pro"].click()
assert modos.modo_atual() == "pro"
assert not j.lateral.lista_w.isHidden() and not j.lateral.b_memoria.isHidden() and not j.cabecalho.pilula.isHidden()
visiveis = {n for n, b in cfg.nav.items() if b.isVisibleTo(cfg)}
assert {"avancado", "diagnostico", "memoria", "rotinas", "nuvem"} <= visiveis, visiveis
print("OK: trocar para o Pro em Configurações > Geral mostra tudo na hora")

# Ajustes avançados: grava o que está na tela
cfg.ir("avancado")
av = cfg.paginas["avancado"]
av.temperatura.setCurrentIndex(av.temperatura.findData(0.7))
av.contexto.setCurrentIndex(av.contexto.findData(16384))
av.instrucoes.setPlainText("seja breve")
av.caixas["execute_terminal"].setChecked(False)
av._salvar()
a = modos.avancado()
assert a == {"temperatura": 0.7, "contexto": 16384, "instrucoes": "seja breve",
             "ferramentas_desligadas": ["execute_terminal"]}, a
assert av.msg.text() and not av.aviso.isVisibleTo(cfg)
cfg.paginas["geral"].chips_modo["base"].click()
cfg.ir("geral")
assert not cfg.nav["avancado"].isVisibleTo(cfg) and modos.avancado()["temperatura"] is None
cfg.paginas["geral"].chips_modo["pro"].click()
print("OK: Ajustes avançados gravam e só valem no Pro")

# Diagnóstico: lê as ferramentas do log
log = os.path.join(CASA, "tars.log")
with open(log, "w", encoding="utf-8") as f:
    f.write('2026-10-16 10:00:01,000 INFO ferramenta=open_application args={"app": "calc"} sucesso=True tempo=0.1s mensagem="ok"\n')
    f.write("2026-10-16 10:00:02,000 INFO outra coisa\n")
    f.write('2026-10-16 10:00:03,000 INFO ferramenta=execute_terminal args={"command": "ls"} sucesso=False tempo=0s mensagem="x"\n')
assert ultimas_ferramentas(log) == ['10:00:01 ✓ open_application {"app": "calc"}', '10:00:03 × execute_terminal {"command": "ls"}']
assert ultimas_ferramentas(os.path.join(CASA, "nao-existe.log")) == []
tars.ARQUIVO_LOG = log
cfg.ir("diagnostico")
assert "open_application" in cfg.paginas["diagnostico"].log.toPlainText()
print("OK: o Diagnóstico mostra as últimas ferramentas do log")

# 5.1: modelo da nuvem do Ollama escolhido à mão: o rodapé avisa que sai do computador
tars.modo_modelo, tars.modelo_manual = "MANUAL", "gpt-oss:20b-cloud"
j._mostrar_modelo_em_uso()
assert "Ollama Cloud" in j.compositor.rodape.text(), j.compositor.rodape.text()
tars.modo_modelo, tars.modelo_manual = "MANUAL", "qwen3:4b"
j._mostrar_modelo_em_uso()
assert "Ollama Cloud" not in j.compositor.rodape.text()
print("OK: o rodapé avisa quando o modelo escolhido é da nuvem do Ollama")

j._saindo = True
j.close()
print("\nTUDO OK.")
