#!/usr/bin/env python3
"""A página "Mais modelos": a lista, o que é considerado instalado, o clique que baixa pelo Ollama (de mentira) com
barra de progresso, o cancelamento, o disco cheio, e o modelo de imagem que nunca é escolhido para conversar."""
import os, sys, types
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
except ImportError:
    print("test_mais_modelos: PULADO (PySide6 não instalado)")
    sys.exit(0)
from _util import carregar_tars
import fake_ollama
import tars_mais_modelos as mm
import tars_modos as modos
import tars_primeiro_uso as pu

tars = carregar_tars()
app = QApplication.instance() or QApplication([])
from tars_qt import configuracoes as cfgmod, tema
app.setStyleSheet(tema.folha_principal() if hasattr(tema, "folha_principal") else "")

# 1. a lista em si
tags = mm.todas_as_tags()
assert len(tags) == len(set(tags)) and len(tags) >= 55, tags
assert [g for g, _ in mm.GRUPOS] == ["bonsai", "imagem", "geral", "visao", "codigo", "grandes"]
bonsai = [i for g, itens in mm.GRUPOS if g == "bonsai" for i in itens]
assert [i[0] for i in bonsai] == ["bonsai-2:2b", "bonsai-2:4b", "bonsai-2:9b", "bonsai-2:27b"], "todos os tamanhos do Bonsai 2"
imagens = {i[0] for g, itens in mm.GRUPOS if g == "imagem" for i in itens}
assert imagens >= {"x/flux2-klein:4b", "x/flux2-klein:9b-bf16", "x/z-image-turbo", "x/z-image-turbo:bf16"} and len(imagens) == 8
for _, itens in mm.GRUPOS:
    for tag, nome, gb, caps in itens:
        assert gb > 0 and nome and caps and all(c in mm.CAPACIDADES for c in caps), tag
# (as chaves de texto de cada grupo e de cada capacidade são conferidas pelo test_textos.py)
print("OK: lista com os 4 Bonsai 2, modelos de imagem e outros, sem repetir tag")

# 2. instalado, apelidos, tamanho e disco
assert mm.instalado("bonsai-2:4b", ["Bonsai-2:4b"]) and not mm.instalado("bonsai-2:4b", ["bonsai-2:2b"])
assert mm.instalado("bonsai-2:9b", ["bonsai-2:latest"]), "o Ollama chama o 9b de latest"
assert mm.instalado("mistral:7b", ["mistral:latest"]) and not mm.instalado("qwen2.5:14b", ["qwen2.5:latest"])
assert mm.instalado("x/z-image-turbo", ["x/z-image-turbo:latest"]) and mm.instalado("qwen3:8b", ["qwen3:latest"]) and mm.instalado("deepseek-r1:8b", ["deepseek-r1:latest"])
assert not mm.instalado("qwen3:14b", ["qwen3:latest"]) and not mm.instalado("qwen3:14b", ["qwen3:8b"])
assert mm.tamanho_texto(0.911) == "911 MB" and mm.tamanho_texto(8.3) == "8.3 GB"
assert mm.cabe(8.3, None) and mm.cabe(8.3, 10.2) and not mm.cabe(8.3, 9.0)
print("OK: instalado, apelidos, tamanho e espaço")

# 3. o catálogo nunca escolhe modelo de imagem para conversar
for tag, caps in (("x/flux2-klein:4b", set()), ("x/z-image-turbo:latest", {"image"}), ("outra/coisa:1", {"image"})):
    assert tars._categorizar_modelo(tag, caps, 6.0, "x") == "embedding", tag
assert tars._categorizar_modelo("bonsai-2:4b", {"completion", "vision", "tools"}, 4.0, "qwen35") != "embedding"
assert tars._categorizar_modelo("gemma3:4b", {"completion", "vision"}, 4.0, "gemma3") != "embedding"
print("OK: modelo que só gera imagem fica fora da conversa")

# 4. visível no Base e no Pro, escondido no Lite
assert not hasattr(mm, "EXTERNOS"), "o Bonsai Image saiu"
assert "cfg.modelos" in modos.RECURSOS["base"] and "cfg.modelos" in modos.RECURSOS["pro"] and "cfg.modelos" not in modos.RECURSOS["lite"]
assert "modelos" in cfgmod.PAGINAS
print("OK: página no Base e no Pro")

# 5. a página, com um Ollama de mentira
class Emite:
    def __init__(self): self.vezes = 0
    def emit(self): self.vezes += 1

class Cfg:                              # o suficiente do PaginaConfiguracoes para a página
    def __init__(self, url):
        self.nucleo = types.SimpleNamespace(OLLAMA_HOST=url)
        self.modelos_mudaram = Emite()
    def em_segundo_plano(self, trabalho, ao_fim):
        try:
            r = trabalho()
        except Exception as e:
            r = e
        ao_fim(r)
    def depois(self, f): f()

servidor, url = fake_ollama.subir(modelos=["bonsai-2:4b", "qwen3:8b"])
cfg = Cfg(url)
pg = cfgmod.PModelos(cfg)
assert set(pg.cartoes) == set(tags)
pg.ao_abrir()
assert pg.cartoes["bonsai-2:4b"].estado == "instalado" and pg.cartoes["qwen3:8b"].estado == "instalado"
assert pg.cartoes["bonsai-2:2b"].estado == "livre" and not pg.estado.isVisible()
assert "911 MB" in pg.cartoes["bonsai-2:2b"].botao.text()
print("OK: o que já está no Ollama aparece como instalado")

# clique no cartão (não só no botão) baixa; a barra chega a 100 e o app é avisado
c = pg.cartoes["gemma3:1b"]
vistos = []
original = c.progresso
c.progresso = lambda pct, texto: (vistos.append((pct, texto)), original(pct, texto))
c.resize(640, 120); c.show()
QTest.mouseClick(c, Qt.LeftButton, Qt.NoModifier, c.rect().bottomLeft() + QPoint(20, -6))     # no cartão, fora do botão
assert c.estado == "instalado" and cfg.modelos_mudaram.vezes == 1
assert vistos and vistos[-1][0] == 100 and all(0 <= p <= 100 for p, _ in vistos), vistos
assert any(p[0] == "POST" and p[1] == "/api/pull" and p[2]["model"] == "gemma3:1b" for p in servidor.pedidos)
assert pg._baixando is None and pg.cartoes["bonsai-2:2b"].estado == "livre"
assert "%" in vistos[-1][1] and "GB" in vistos[-1][1] or "MB" in vistos[-1][1]
print("OK: um clique baixa pelo Ollama, a barra vai a 100% e o app é avisado")

cb = pg.cartoes["gemma3:4b"]; cb.show()
QTest.mouseClick(cb.botao, Qt.LeftButton)
assert cb.estado == "instalado" and cfg.modelos_mudaram.vezes == 2, "o botão do cartão também baixa"

# o clique num cartão enquanto outro baixa não faz nada, e os outros ficam bloqueados
pg._baixando = "bonsai-2:2b"; pg._atualizar()
assert pg.cartoes["bonsai-2:9b"].estado == "bloqueado" and not pg.cartoes["bonsai-2:9b"].botao.isEnabled()
antes = len(servidor.pedidos)
pg._clicou("bonsai-2:9b")
assert len(servidor.pedidos) == antes
pg._clicou("bonsai-2:2b")            # o cartão que baixa: o clique vira "cancelar"
assert pg._cancelar is True
pg._baixando = None; pg._cancelar = False; pg._atualizar()
print("OK: um download por vez e o clique no cartão que baixa cancela")

# cancelar: volta a "livre" com o aviso de retomar
original_baixar = pu.baixar_modelo
pu.baixar_modelo = lambda *a, **k: (False, "cancelado")
pg._clicou("bonsai-2:2b")
assert pg.cartoes["bonsai-2:2b"].estado == "livre" and "retomar" in pg.cartoes["bonsai-2:2b"].info.text()
pu.baixar_modelo = original_baixar
# erro do Ollama aparece no cartão
servidor.erro_no_download = "pull model manifest: file does not exist"
pg._clicou("llama3.2:3b")
c2 = pg.cartoes["llama3.2:3b"]
assert c2.estado == "livre" and "manifest" in c2.info.text(), c2.info.text()
servidor.erro_no_download = ""
# sem espaço: nem tenta baixar
pedidos = len(servidor.pedidos)
pu.espaco_livre_gb = lambda *a, **k: 0.5
pg._clicou("bonsai-2:27b")
assert len(servidor.pedidos) == pedidos and pg.cartoes["bonsai-2:27b"].estado == "livre"
assert "espaço" in pg.cartoes["bonsai-2:27b"].info.text().lower() or "space" in pg.cartoes["bonsai-2:27b"].info.text().lower()
print("OK: cancelar, erro e disco cheio")

# Ollama fora do ar: aviso e botões travados
servidor.shutdown()
pg2 = cfgmod.PModelos(Cfg("http://127.0.0.1:9"))
pg2.ao_abrir()
assert pg2.estado.isHidden() is False or pg2.estado.text()
assert all(c.estado == "bloqueado" for c in pg2.cartoes.values())
print("test_mais_modelos: TUDO OK.")
