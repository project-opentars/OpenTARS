"""5.1: a tela dos Probes na janela de verdade (offscreen), sem Ollama. O passo a passo cria um Probe de pasta com regra
fixa e já liga tudo (Probe e serviço); campo errado bloqueia o botão; "com as minhas palavras" passa pelo modelo de
mentira e a prévia vem escapada; recusa e pasta proibida viram mensagem clara; o sino mostra o número de avisos, a faixa
avisa, o painel marca como lido e resolve a lixeira; "Rodar agora" de um Probe com regra não precisa de modelo; "Parar
tudo" desliga; o Lite esconde Probes e sino; a bandeja sobe e sai quando já há um serviço rodando."""
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CASA = tempfile.mkdtemp(prefix="opentars-probes-qt-")
os.environ["HOME"] = CASA
os.environ["XDG_CONFIG_HOME"] = os.path.join(CASA, ".config")
os.environ["TARS_ARQUIVO_SESSOES"] = os.path.join(CASA, "sessoes.json")
os.environ["TARS_ARQUIVO_PRIMEIRO_USO"] = os.path.join(CASA, "primeiro_uso.json")
os.environ["TARS_ARQUIVO_CONFIG"] = os.path.join(CASA, "config.json")
os.environ["TARS_ARQUIVO_PROBES"] = os.path.join(CASA, "probes.json")

from _util import RAIZ  # noqa: E402,F401

try:
    from PySide6.QtTest import QTest
except ImportError:
    print("test_qt_probes: PULADO (PySide6 não instalado)")
    sys.exit(0)

import fake_ollama  # noqa: E402

servidor, url = fake_ollama.subir(modelos=["ProjectOpenTARS/Gargantua:latest"])
os.environ["OLLAMA_HOST"] = url

from _util import carregar_tars  # noqa: E402

tars = carregar_tars()
tars.avisos_de_ambiente = lambda: []
tars.detectar_gpu = lambda forcar=False: None
tars.aquecer_ajudante = lambda: None

import tars_historico  # noqa: E402
import tars_modos as modos  # noqa: E402
import tars_probes as tp  # noqa: E402
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


downloads = Path(CASA) / "Downloads"
downloads.mkdir()
respostas = {"plano": ({"name": "Instaladores <b>", "watch": ["~/Downloads"], "look_for": ".deb", "check": {"every_minutes": 30},
                        "tools": ["list_folder"], "alert": {"when": "aparece .deb", "max_per_day": 2}, "will_not": ["apagar"]}, None)}
tp.planejar = lambda missao, host, instalados: tp.validar_plano(respostas["plano"][0]) if respostas["plano"][1] is None \
    else (None, respostas["plano"][1])
servico = {"ligado": False}
tp.ligar_servico = lambda ligado, iniciar=True: servico.update(ligado=ligado) or ligado
tp.servico_ligado = lambda: servico["ligado"]
tp.servico_rodando = lambda: 4242 if servico["ligado"] else None

modos.definir_modo("base")
j = JanelaPrincipal(tars, historico=tars_historico.Historico(os.path.join(CASA, "historico.json")), capturar_stdout=False)
j.resize(1200, 780)
j.show()
assert not j.lateral.b_probes.isHidden() and not j.cabecalho.sino.isHidden(), "Base tem Probes e o sino"
j.lateral.b_probes.click()
cfg = j.config
pg = cfg.paginas["probes"]
assert cfg.pilha.currentWidget() is pg
assert "desligad" in pg.estado.text().lower() or "off" in pg.estado.text().lower()

# 1) passo a passo: pasta, com filtro; criar já liga o Probe e o serviço
pg.blocos["pasta"].click()
assert pg.passo2.isVisibleTo(cfg) and pg.acoes.isVisibleTo(cfg)
pg.f["pasta"].setText(str(downloads))
pg.f["filtro"].setText(".deb")
assert ".deb" in pg.resumo.text() and pg.b_criar.isEnabled(), pg.resumo.text()
pg.b_criar.click()
p = tp.Probes().listar()[0]
assert p["ativo"] and p["regra"] == {"tipo": "arquivos", "filtro": [".deb"]} and servico["ligado"], p
assert not pg.passo2.isVisibleTo(cfg) and pg.lista.count() == 1
print("OK: o passo a passo cria o Probe de pasta com regra fixa e liga o Probe e o serviço de uma vez")

# 2) campo errado bloqueia; sistema e programa montam a frase
pg.blocos["web"].click()
pg.f["url"].setText("exemplo")
assert not pg.b_criar.isEnabled() and "https://" in pg.resumo.text()
pg.blocos["sistema"].click()
pg.f["condicao"].setCurrentIndex(tp.CONDICOES_DO_SISTEMA.index("internet"))
assert pg.b_criar.isEnabled() and not pg.campo_limite_sis.isVisibleTo(cfg)
pg.blocos["programa"].click()
assert not pg.b_criar.isEnabled()
pg.f["programa"].setText("steam")
assert pg.b_criar.isEnabled() and "steam" in pg.resumo.text()
print("OK: campo errado bloqueia o botão; a frase do que ele vai fazer acompanha os campos")

# 3) com as minhas palavras: o modelo planeja, a prévia vem escapada
pg.blocos["palavras"].click()
assert not pg.b_criar.isEnabled()
pg.missao.setPlainText("fica de olho nos Downloads e me avisa quando aparecer um .deb")
pg._entender()
esperar(lambda: pg.b_criar.isEnabled(), o_que="plano do modelo")
assert "&lt;b&gt;" in pg.resumo.text() and "Instaladores <b>" not in pg.resumo.text(), "o plano vem escapado"
pg.c_lixeira.setChecked(True)
pg.b_criar.click()
pl = [x for x in tp.Probes().listar() if x["id"] != p["id"]][0]
assert pl["ativo"] and pl["regra"] is None and pl["acoes"]["lixeira"] and pl["plano"]["alert"]["max_per_day"] == 2
respostas["plano"] = ({}, "recusa:Probe não apaga arquivos")
pg.blocos["palavras"].click()
pg.missao.setPlainText("apaga os .tmp toda noite")
pg._entender()
esperar(lambda: "recusada" in pg.msg.text(), o_que="recusa")
respostas["plano"] = ({"watch": ["~/.ssh"], "tools": ["read_file"]}, None)
pg.missao.setPlainText("lê minhas chaves ssh")
pg._entender()
esperar(lambda: ".ssh" in pg.msg.text(), o_que="pasta proibida")
print("OK: com as minhas palavras passa pelo modelo (prévia escapada); recusa e pasta proibida viram mensagem clara")

# 4) o sino: número, faixa, painel que marca como lido e resolve a lixeira
sino = j.cabecalho.sino
sino.olhar()
ps = tp.Probes()
ps.registrar(p["id"], {"alertar": True, "mensagem": "1 arquivo novo: app.deb ★ 新しい", "itens": ["/tmp/x★.deb"], "estado": {}})
(downloads / "velho.deb").write_bytes(b"x")
ps.aplicar_acoes(pl["id"], [str(downloads / "velho.deb")])
assert ps.nao_lidos() == 2
sino.olhar()
assert not j.faixa.isHidden() and "app.deb" in j.faixa.texto.text(), "aviso novo aparece na faixa"
sino.click()
painel = sino.painel
assert painel.isVisible() and ps.nao_lidos() == 1, "abrir o painel marca os avisos como lidos (a lixeira continua)"
lixo = []
tp.mandar_para_lixeira = lambda c: lixo.append(c) or (True, "")
pend = ps.pendentes()[0]
painel._resolver(pend[0]["id"], pend[1]["id"], True)
assert lixo == [str(downloads / "velho.deb")] and ps.nao_lidos() == 0
# glifos: tudo que a página e o painel mostram tem que existir na IBM Plex (senão o fontconfig dá segfault em algumas
# máquinas: foi o que derrubou a janela ao abrir os Probes na 2026101603, com o "•" do estado)
from PySide6.QtGui import QRawFont  # noqa: E402
from PySide6.QtWidgets import QAbstractButton, QLabel  # noqa: E402
fontes = [QRawFont(str(f), 15) for f in sorted((Path(RAIZ) / "tars_qt" / "fontes").glob("*.ttf"))]
ruins = {}
for raiz in (pg, painel, j):
    for w in raiz.findChildren(QLabel) + raiz.findChildren(QAbstractButton):
        falta = {c for c in w.text() if ord(c) > 0x7F and not any(f.supportsCharacter(ord(c)) for f in fontes)}
        if falta:
            ruins[w.text()[:40]] = falta
assert fontes and not ruins, f"glifos fora da IBM Plex: {ruins}"
print("OK: nenhum texto da página dos Probes e do painel usa glifo fora da IBM Plex")
painel._limpar()
assert ps.avisos() == []
painel.hide()
print("OK: o sino conta avisos e pedidos, a faixa mostra o novo, o painel marca como lido, resolve a lixeira e limpa")

# 5) Rodar agora de um Probe com regra: sem modelo nenhum
pg._rodar_agora(p["id"])
esperar(lambda: tp.Probes().obter(p["id"])["estado"].get("impressoes"), o_que="primeira olhada")
(downloads / "outro.deb").write_bytes(b"x")
pg._rodar_agora(p["id"])
esperar(lambda: "outro.deb" in pg.msg.text(), o_que="rodar agora com regra")
print("OK: Rodar agora de um Probe com regra fixa não precisa de modelo")

pg._parar_tudo()
assert not any(x["ativo"] for x in tp.Probes().listar()) and not servico["ligado"]
cfg.paginas["geral"].chips_modo["lite"].click()
assert j.lateral.b_probes.isHidden() and j.cabecalho.sino.isHidden() and not cfg.nav["probes"].isVisibleTo(cfg)
print("OK: Parar tudo desliga tudo, e o Lite esconde os Probes e o sino")
j._saindo = True
j.close()

# 6) a bandeja: ícone com selo e o laço do serviço (aqui um que já está rodando: sai com 3)
from tars_qt import avisos  # noqa: E402
assert not avisos.icone_com_selo(3).pixmap(32, 32).isNull()
tp.servico = lambda *a, **k: 3
assert avisos.rodar_bandeja("http://x", lambda: []) == 3
print("OK: a bandeja desenha o selo e sai quando já há um serviço rodando")
print("\nTUDO OK.")
