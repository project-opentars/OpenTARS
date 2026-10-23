"""O mascote (o monólito): anda dentro da conversa, reage ao que a IA faz, dá dicas sem repetir e se desliga pela
configuração e por TARS_SEM_MASCOTE. Janela de verdade, sem tela (offscreen) e sem Ollama."""
import json
import os
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CASA = tempfile.mkdtemp(prefix="opentars-casa-")
os.environ["HOME"] = CASA
for k in ("SESSOES", "NUVEM", "PRIMEIRO_USO"):
    os.environ[f"TARS_ARQUIVO_{k}"] = os.path.join(CASA, k.lower() + ".json")
os.environ["OLLAMA_HOST"] = "http://127.0.0.1:9"
os.environ["TARS_IDIOMA"] = "pt_BR"
os.environ.pop("TARS_SEM_MASCOTE", None)

from _util import carregar_tars, RAIZ  # noqa: E402,F401

try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    print("test_qt_mascote: PULADO (PySide6 não instalado)")
    sys.exit(0)

tars = carregar_tars()
import tars_i18n  # noqa: E402
from tars_qt import mascote as mod, principal, tema  # noqa: E402

app = QApplication.instance() or QApplication([])
tema.carregar_fontes()


def esperar(s):
    fim = time.time() + s
    while time.time() < fim:
        app.processEvents()
        time.sleep(0.01)


w = principal.JanelaPrincipal(nucleo=tars, capturar_stdout=False)
w.resize(1200, 780)
w.show()
esperar(0.5)
m = w.mascote

# 1) aparece por padrão, dentro da conversa, em cima do campo de escrever
assert m.isVisible() and m.parentWidget() is not w.lateral
chao = w.compositor.mapTo(m.parentWidget(), w.compositor.rect().topLeft()).y()
assert abs((m.y() + mod.ALTURA) - chao) <= 20, (m.y(), chao)
print("OK: aparece sozinho, em cima do campo de escrever")

# 2) anda e nunca sai dos limites (nem quando a janela encolhe)
m._parado_ate = 0
x0 = m.x()
esperar(1.0)
assert m.x() != x0, "não andou"
for largura in (1200, 900, 1500):
    w.resize(largura, 780)
    m._x = 99999
    esperar(0.2)
    assert 16 <= m.x() <= m.parentWidget().width() - mod.LARGURA - 16 + 1, (largura, m.x())
print("OK: anda e fica dentro da conversa")

# 3) reage ao que a IA faz
w.ponte.ocupado.emit(True)
esperar(0.1)
assert m.estado == "pensando"
w._ao_evento("ferramenta", {"nome": "type_text", "resumo": "x"})
assert m.estado == "trabalhando" and "…" in m.balao.text() and m.balao.isVisible(), m.balao.text()
m._ultima_fala = 0
w._ao_evento("ferramenta_fim", {"nome": "type_text", "sucesso": False, "segundos": 1})
assert m.estado == "erro" and m.balao.text() == tars_i18n.t("mascote.ops"), (m.estado, m.balao.text())
m._ultima_fala = 0
w._ao_evento("plano", {"etapas": ["a", "b", "c"]})
assert "3" in m.balao.text()
m._ultima_fala = 0
w.ponte.aprovacao.emit(type("A", (), {"comando": "rm x", "responder": lambda self, ok: None})())
assert m.estado == "espera" and m.balao.text() == tars_i18n.t("mascote.permissao")
w.ponte.ocupado.emit(False)
w.ponte.concluido.emit("pronto")
esperar(0.1)
assert m.estado == "feliz" and m.balao.text() == tars_i18n.t("mascote.pronto")
esperar(2.8)
assert m.estado == "ocioso", m.estado
# pedido cancelado não comemora
m.balao.hide(); m._ultima_fala = 0; w._cancelou = True
w.ponte.concluido.emit("parei")
assert m.estado != "feliz"
w._cancelou = False
print("OK: reage (pensando, ferramenta, erro, plano, permissão, pronto)")

# 4) não metralha balões: duas ferramentas seguidas, só a primeira fala
m.balao.hide(); m._ultima_fala = 0
w._ao_evento("ferramenta", {"nome": "type_text"}); primeiro = m.balao.text()
w._ao_evento("ferramenta", {"nome": "click_mouse"})
assert m.balao.text() == primeiro
print("OK: balões não se atropelam")

# 5) dicas: as 10 saem sem repetir antes de acabar a rodada
vistas = []
for _ in range(mod.N_DICAS):
    m._ultima_fala = 0
    m.dica()
    vistas.append(m.balao.text())
assert len(set(vistas)) == mod.N_DICAS, vistas
print("OK: 10 dicas, sem repetir na rodada")

# 6) textos: todas as chaves existem em pt_BR e en, com os mesmos {campos}
import re  # noqa: E402
chaves = [k for k in json.load(open(os.path.join(RAIZ, "idiomas", "pt_BR.json"), encoding="utf-8")) if k.startswith(("mascote.", "cfg.mascote"))]
en = json.load(open(os.path.join(RAIZ, "idiomas", "en.json"), encoding="utf-8"))
pt = json.load(open(os.path.join(RAIZ, "idiomas", "pt_BR.json"), encoding="utf-8"))
assert len(chaves) >= 20 and all(k in en for k in chaves)
assert all(re.findall(r"{\w+}", pt[k]) == re.findall(r"{\w+}", en[k]) for k in chaves)
usadas = set(re.findall(r't\("(mascote\.[a-z_]+)"', open(os.path.join(RAIZ, "tars_qt", "mascote.py"), encoding="utf-8").read()))
assert usadas <= set(chaves), usadas - set(chaves)
print("OK: textos nos dois idiomas")

# 7) liga e desliga: configuração, menu dele e variável de ambiente
tars_i18n.salvar_config(mascote=False)
w.config.mudou_mascote.emit()
assert not m.isVisible() and not m.balao.isVisible()
tars_i18n.salvar_config(mascote=True)
w.config.mudou_mascote.emit()
assert m.isVisible()
m._esconder()
assert not m.isVisible() and tars_i18n.ler_config()["mascote"] is False
tars_i18n.salvar_config(mascote=True)
os.environ["TARS_SEM_MASCOTE"] = "1"
assert not mod.ligado()
del os.environ["TARS_SEM_MASCOTE"]
assert mod.ligado()
print("OK: liga e desliga (configuração, menu, TARS_SEM_MASCOTE)")

# 8) cada humor tem um rosto próprio (fora da piscada, que é igual em todos)
def _bytes(estado):
    img = mod.desenhar_sprite(estado, 0.0, False, 1, 1.0)    # agora=1.0: longe da piscada
    return bytes(img.constBits())[:img.sizeInBytes()]
rostos = {e: _bytes(e) for e in ("ocioso", "pensando", "trabalhando", "espera", "erro", "feliz", "sono")}
assert len(set(rostos.values())) == len(rostos), [e for e in rostos if list(rostos.values()).count(rostos[e]) > 1]
print("OK: um rosto por humor")

# 9) cochila depois de muito tempo parado e acorda com qualquer coisa
m.mostrar_de_novo()                      # o passo 7 terminou com ele escondido pelo menu
m.estado = "ocioso"
m._ultima_atividade = time.monotonic() - mod.SONO_S - 1
esperar(0.1)
assert m.estado == "sono"
x0 = m.x(); esperar(0.5)
assert m.x() == x0, "anda dormindo"
w.ponte.ocupado.emit(True); esperar(0.05)
assert m.estado == "pensando"
w.ponte.ocupado.emit(False); esperar(0.05)
print("OK: cochila e acorda")

w.close()
print("\nTUDO OK.")
