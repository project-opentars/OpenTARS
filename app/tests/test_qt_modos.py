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


modos.definir_dev(False)
j = JanelaPrincipal(tars, historico=tars_historico.Historico(os.path.join(CASA, "historico.json")), capturar_stdout=False)
j.resize(1200, 780)
j.show()
esperar(lambda: j._modelos, o_que="modelos")
cfg = j.config
assert j.lateral.lista_w.isVisibleTo(j) and j.lateral.b_memoria.isVisibleTo(j) and j.cabecalho.pilula.isVisibleTo(j), "Base: histórico, memória e seletor"
assert j.lateral.versao.text() == tars.VERSAO_EXIBIDA
j.abrir_config("avancado")                        # página do dev, com ele desligado: cai na Geral
assert cfg.pilha.currentWidget() is cfg.paginas["geral"]
visiveis = {n for n, b in cfg.nav.items() if b.isVisibleTo(cfg)}
assert {"memoria", "rotinas", "probes", "nuvem"} <= visiveis and not {"avancado", "diagnostico"} & visiveis, visiveis
print("OK: o Base mostra tudo do dia a dia e esconde ajustes avançados e diagnóstico")

# ligar o dev pela própria tela
cfg.paginas["geral"].dev.setChecked(True)
assert modos.modo_atual() == "dev"
assert not j.lateral.lista_w.isHidden() and not j.lateral.b_memoria.isHidden() and not j.cabecalho.pilula.isHidden()
visiveis = {n for n, b in cfg.nav.items() if b.isVisibleTo(cfg)}
assert {"avancado", "diagnostico", "memoria", "rotinas", "nuvem"} <= visiveis, visiveis
print("OK: ligar o dev em Configurações > Geral mostra tudo na hora")

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
cfg.paginas["geral"].dev.setChecked(False)
cfg.ir("geral")
assert not cfg.nav["avancado"].isVisibleTo(cfg) and modos.avancado()["temperatura"] is None
cfg.paginas["geral"].dev.setChecked(True)
print("OK: Ajustes avançados gravam e só valem com o dev ligado")

# Motor de IA (5.3): llama.cpp por padrão; a chave de dev troca para o Ollama e avisa que vale ao reabrir
import tars_i18n  # noqa: E402
import tars_motor_local  # noqa: E402
os.environ.pop("TARS_MOTOR", None)
av.ao_abrir()
assert av.motor.currentData() == "llamacpp" and av.motor.isEnabled(), av.motor.currentData()
av.motor.setCurrentIndex(av.motor.findData("ollama"))
av._salvar()
assert tars_i18n.ler_config().get("motor") == "ollama" and tars_motor_local.escolhido() == "ollama"
assert av.msg.text() == tars_i18n.t("cfg.av.motor_reiniciar")
av.motor.setCurrentIndex(av.motor.findData("llamacpp"))
av._salvar()
assert tars_motor_local.escolhido() == "llamacpp"
print("OK: a chave de dev troca o motor entre llama.cpp (padrão) e Ollama")

# Busca de arquivos (5.3): o índice local é opcional e desligado por padrão; ligar monta em segundo plano, desligar apaga
import tars_busca_arquivos  # noqa: E402
montagens = []
tars_busca_arquivos.atualizar_indice = lambda *a, **k: montagens.append(1) or {"arquivos": 7, "lidos": 7, "removidos": 0}
cfg.ir("assistente")
ass = cfg.paginas["assistente"]
assert not ass.indice.isChecked() and not tars_busca_arquivos.indice_ligado()
ass.indice.setChecked(True)
assert tars_busca_arquivos.indice_ligado()
for _ in range(100):
    app.processEvents()
    if montagens and "7" in ass.indice_nota.text():
        break
    time.sleep(0.03)
assert montagens == [1] and "7" in ass.indice_nota.text(), (montagens, ass.indice_nota.text())
ass.indice.setChecked(False)
assert not tars_busca_arquivos.indice_ligado()
print("OK: o índice de arquivos liga montando em segundo plano e desliga apagando")

# Agenda e notas (5.3): desligadas por padrão; só aceitam arquivo que existe ou link https; vazio desliga
import tars_integracoes  # noqa: E402
ics = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_qt_modos.py")        # qualquer arquivo que exista
assert tars_integracoes.agendas() == [] and tars_integracoes.pasta_de_notas() is None
ass.agenda.setText("/nao/existe.ics")
ass._salvar_agenda()
assert tars_integracoes.agendas() == [] and "/nao/existe.ics" in ass.agenda_nota.text()
ass.agenda.setText(ics + "; https://example.com/agenda.ics")
ass._salvar_agenda()
assert tars_integracoes.agendas() == [ics, "https://example.com/agenda.ics"] and "2" in ass.agenda_nota.text()
ass.notas.setText("/tmp/minhas-notas")
ass._salvar_notas()
assert str(tars_integracoes.pasta_de_notas()) == "/tmp/minhas-notas"
ass.agenda.setText("")
ass._salvar_agenda()
ass.notas.setText("")
ass._salvar_notas()
assert tars_integracoes.agendas() == [] and tars_integracoes.pasta_de_notas() is None
print("OK: agenda e notas: só arquivo que existe ou link https, e vazio desliga")

# E-mail (5.3): a senha só vai para o cofre (aqui um cofre falso), o config guarda só o endereço e os servidores
import tars_email  # noqa: E402
cofre_falso = {}


class _Cofre:
    set_password = staticmethod(lambda servico, usuario, senha: cofre_falso.__setitem__((servico, usuario), senha))
    get_password = staticmethod(lambda servico, usuario: cofre_falso.get((servico, usuario)))
    delete_password = staticmethod(lambda servico, usuario: cofre_falso.pop((servico, usuario), None))


tars_email._cofre = lambda: _Cofre
assert tars_email.conta() is None
ass.email_usuario.setText("pessoa@provedor-desconhecido.org")
ass.email_senha.setText("segredo-123")
ass._salvar_email()
assert tars_email.conta() is None and not cofre_falso and "IMAP" in ass.email_nota.text(), "provedor desconhecido pede os servidores e não guarda nada"
ass.email_usuario.setText("pessoa@gmail.com")
ass.email_senha.setText("")
ass._salvar_email()
assert tars_email.conta() is None and not cofre_falso, "sem senha não liga"
ass.email_senha.setText("segredo-123")
ass._salvar_email()
assert tars_email.conta()["usuario"] == "pessoa@gmail.com" and tars_email.conta()["imap"] == "imap.gmail.com"
assert cofre_falso == {("openTARS-email", "pessoa@gmail.com"): "segredo-123"} and ass.email_senha.text() == ""
assert "segredo-123" not in open(os.environ["TARS_ARQUIVO_CONFIG"]).read(), "a senha nunca vai para o config"
tars_email.testar = lambda *a, **k: "Connection refused"
ass._testar_email()
for _ in range(100):
    app.processEvents()
    if "refused" in ass.email_nota.text():
        break
    time.sleep(0.03)
assert "Connection refused" in ass.email_nota.text()
def sem_cofre():
    raise tars_email.SemCofre("keyring não instalado")
tars_email._cofre = sem_cofre
ass.email_usuario.setText("outra@gmail.com")
ass.email_senha.setText("x")
ass._salvar_email()
assert tars_email.conta()["usuario"] == "pessoa@gmail.com" and "keyring" in ass.email_nota.text(), "sem cofre: a conta antiga fica e a tela explica"
tars_email._cofre = lambda: _Cofre
ass._desligar_email()
assert tars_email.conta() is None and not cofre_falso, "desligar esquece a conta e apaga a senha"
print("OK: e-mail: senha só no cofre, provedor desconhecido pede servidores, sem cofre não guarda, desligar apaga")

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
