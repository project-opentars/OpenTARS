#!/usr/bin/env python3
"""A página "Mais modelos" (14/11: a loja é o Hugging Face): a lista curada com SHA-256 fixo, o que é considerado instalado,
o clique que registra a ficha no motor e baixa (motor de mentira) com barra de progresso, o cancelamento, o disco cheio, a
pesquisa no Hugging Face (de mentira) e o modelo de imagem que nunca é escolhido para conversar."""
import os, sys, tempfile, types
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_casa = tempfile.mkdtemp(prefix="opentars-loja-")
os.environ["HOME"] = os.environ["XDG_DATA_HOME"] = _casa     # a loja.json do motor vai para cá, não para a pasta pessoal
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
tags = [i[0] for _, itens in mm.GRUPOS for i in itens]
assert len(tags) == len(set(tags)) and len(tags) >= 20, tags
assert [g for g, _ in mm.GRUPOS] == ["opentars", "geral", "visao", "codigo"], "14/11: sem Bonsai 2 e sem imagem (eram do Ollama)"
nossos = [i[0] for g, itens in mm.GRUPOS if g == "opentars" for i in itens]
assert nossos[0] == mm.DESTAQUE == "ProjectOpenTARS/Gargantua-2.5:lite" and "ProjectOpenTARS/Gargantua-2.5:latest" in nossos, nossos
import tars_motor_local  # noqa: E402
for _, itens in mm.GRUPOS:
    for tag, nome, gb, caps in itens:
        assert gb > 0 and nome and caps and all(c in mm.CAPACIDADES for c in caps), tag
        if not tag.startswith("ProjectOpenTARS/"):
            assert tag.startswith("hf.co/") and tars_motor_local.ficha_valida(mm.FICHAS[tag]), tag
            assert tag.endswith(":" + mm.FICHAS[tag]["quantization_level"]), tag
        else:
            assert tag in tars_motor_local.CATALOGO, tag
assert set(mm.FICHAS) == {t for t in tags if t.startswith("hf.co/")}
print("OK: lista curada do Hugging Face, cada uma com ficha válida (arquivo e SHA-256 fixos), sem repetir")

# 2. instalado, tamanho e disco
assert mm.instalado("hf.co/a/b:Q4_K_M", ["HF.CO/a/b:Q4_K_M"]) and not mm.instalado("hf.co/a/b:Q4_K_M", ["hf.co/a/b:Q8_0"])
assert mm.tamanho_texto(0.911) == "911 MB" and mm.tamanho_texto(8.3) == "8.3 GB"
assert mm.cabe(8.3, None) and mm.cabe(8.3, 10.2) and not mm.cabe(8.3, 9.0)
# escolher o GGUF de um repositório: o Q4_K_M, sem as partes de modelo dividido; o projetor F16 antes do Q8
lfs = lambda n, t: {"type": "file", "path": n, "size": t, "lfs": {"oid": "a" * 64, "size": t}}
arvore = [lfs("m-Q8_0.gguf", 8), lfs("m-Q4_K_M.gguf", 4), lfs("m-Q2_K.gguf", 2), lfs("m-BF16-00001-of-00002.gguf", 9),
          lfs("mmproj-Q8_0.gguf", 1), lfs("mmproj-F16.gguf", 2), {"type": "file", "path": "README.md", "size": 1}]
modelo, projetor = mm.escolher_arquivos(arvore)
assert modelo[0] == "m-Q4_K_M.gguf" and projetor[0] == "mmproj-F16.gguf", (modelo, projetor)
assert mm.escolher_arquivos([lfs("x-00001-of-00003.gguf", 1)]) is None, "modelo dividido em partes fica de fora"
assert mm.capacidades_do_modelo({"gguf": {"chat_template": "{% if tools %}...<think>"}}, None) == ("tools", "thinking")
print("OK: instalado, tamanho, espaço e a escolha do arquivo no repositório")

# 3. o catálogo nunca escolhe modelo de imagem para conversar
for tag, caps in (("x/flux2-klein:4b", set()), ("x/z-image-turbo:latest", {"image"}), ("outra/coisa:1", {"image"})):
    assert tars._categorizar_modelo(tag, caps, 6.0, "x") == "embedding", tag
assert tars._categorizar_modelo("hf.co/unsloth/Qwen3.5-4B-GGUF:Q4_K_M", {"completion", "vision", "tools"}, 4.0, "qwen35") != "embedding"
assert tars._categorizar_modelo("gemma3:4b", {"completion", "vision"}, 4.0, "gemma3") != "embedding"
print("OK: modelo que só gera imagem fica fora da conversa")

# 4. visível no Base e no Pro, escondido no Lite
assert not hasattr(mm, "EXTERNOS"), "o Bonsai Image saiu"
assert "cfg.modelos" in modos.RECURSOS["base"] and "cfg.modelos" in modos.RECURSOS["dev"]
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

Q2 = "hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M"
Q4 = "hf.co/unsloth/Qwen3.5-4B-GGUF:Q4_K_M"
L3 = "hf.co/bartowski/Llama-3.2-3B-Instruct-GGUF:Q4_K_M"
G12 = "hf.co/unsloth/gemma-4-12b-it-GGUF:Q4_K_M"
C30 = "hf.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q4_K_M"
P1 = "hf.co/unsloth/Phi-4-mini-instruct-GGUF:Q4_K_M"
servidor, url = fake_ollama.subir(modelos=[Q4, "ProjectOpenTARS/Gargantua-2.5:lite"])
cfg = Cfg(url)
pg = cfgmod.PModelos(cfg)
assert set(pg.cartoes) == set(tags)
pg.ao_abrir()
assert pg.cartoes[Q4].estado == "instalado" and pg.cartoes["ProjectOpenTARS/Gargantua-2.5:lite"].estado == "instalado"
assert pg.cartoes[Q2].estado == "livre" and not pg.estado.isVisible()
print("OK: o que já está no motor aparece como instalado")

# clique no cartão (não só no botão) baixa; a ficha vai para o motor; a barra chega a 100 e o app é avisado
c = pg.cartoes[Q2]
vistos = []
original = c.progresso
c.progresso = lambda pct, texto: (vistos.append((pct, texto)), original(pct, texto))
c.resize(640, 120); c.show()
QTest.mouseClick(c, Qt.LeftButton, Qt.NoModifier, c.rect().bottomLeft() + QPoint(20, -6))     # no cartão, fora do botão
assert c.estado == "instalado" and cfg.modelos_mudaram.vezes == 1
assert vistos and vistos[-1][0] == 100 and all(0 <= p <= 100 for p, _ in vistos), vistos
assert any(p[0] == "POST" and p[1] == "/api/pull" and p[2]["model"] == Q2 for p in servidor.pedidos)
assert tars_motor_local._ler_loja()[Q2]["gguf"] == mm.FICHAS[Q2]["gguf"], "a ficha com o SHA-256 fixo foi para o motor"
assert pg._baixando is None and pg.cartoes[L3].estado == "livre"
print("OK: um clique registra a ficha no motor, baixa, a barra vai a 100% e o app é avisado")

cb = pg.cartoes[P1]; cb.show()
QTest.mouseClick(cb.botao, Qt.LeftButton)
assert cb.estado == "instalado" and cfg.modelos_mudaram.vezes == 2, "o botão do cartão também baixa"

# o clique num cartão enquanto outro baixa não faz nada, e os outros ficam bloqueados
pg._baixando = L3; pg._atualizar()
assert pg.cartoes[G12].estado == "bloqueado" and not pg.cartoes[G12].botao.isEnabled()
antes = len(servidor.pedidos)
pg._clicou(G12)
assert len(servidor.pedidos) == antes
pg._clicou(L3)            # o cartão que baixa: o clique vira "cancelar"
assert pg._cancelar is True
pg._baixando = None; pg._cancelar = False; pg._atualizar()
print("OK: um download por vez e o clique no cartão que baixa cancela")

# cancelar: volta a "livre" com o aviso de retomar
original_baixar = pu.baixar_modelo
pu.baixar_modelo = lambda *a, **k: (False, "cancelado")
pg._clicou(L3)
assert pg.cartoes[L3].estado == "livre" and "retomar" in pg.cartoes[L3].info.text()
pu.baixar_modelo = original_baixar
# erro do motor aparece no cartão
servidor.erro_no_download = "Qwen.gguf: SHA256 check failed"
pg._clicou(G12)
c2 = pg.cartoes[G12]
assert c2.estado == "livre" and "SHA256" in c2.info.text(), c2.info.text()
servidor.erro_no_download = ""
# sem espaço: nem tenta baixar
pedidos = len(servidor.pedidos)
pu.espaco_livre_gb = lambda *a, **k: 0.5
pg._clicou(C30)
assert len(servidor.pedidos) == pedidos and pg.cartoes[C30].estado == "livre"
assert "espaço" in pg.cartoes[C30].info.text().lower() or "space" in pg.cartoes[C30].info.text().lower()
print("OK: cancelar, erro e disco cheio")

# motor fora do ar: aviso e botões travados
servidor.shutdown()
pg2 = cfgmod.PModelos(Cfg("http://127.0.0.1:9"))
pg2.ao_abrir()
assert pg2.estado.isHidden() is False or pg2.estado.text()
assert all(c.estado == "bloqueado" for c in pg2.cartoes.values())
# pesquisa: o filtro esconde o que não casa (e a seção vazia) e a busca no Hugging Face cria cartões da comunidade
pg2.busca.setText("gargantua pro")
vis = [t for t, c in pg2.cartoes.items() if not c.isHidden()]
assert vis == ["ProjectOpenTARS/Gargantua-Pro:pro"] and not pg2.b_web.isHidden(), vis
pg2.busca.setText("")
assert all(not c.isHidden() for c in pg2.cartoes.values()) and pg2.b_web.isHidden()
pg2.busca.setText("gemma")
pg2._mostrar_web([{"repo": "alguem/gemma-x-GGUF", "downloads": 10, "likes": 1}, {"repo": "unsloth/gemma-4-12b-it-GGUF", "downloads": 9, "likes": 1}], "gemma")
assert "hf:alguem/gemma-x-GGUF" in pg2.cartoes and pg2.cartoes["hf:alguem/gemma-x-GGUF"].gb == 0
assert "hf:unsloth/gemma-4-12b-it-GGUF" not in pg2.cartoes, "o que já está na lista curada não aparece de novo como comunidade"
pg2._mostrar_web([], "gemma")
assert "hf:alguem/gemma-x-GGUF" not in pg2.cartoes
print("OK: pesquisa na loja")
print("test_mais_modelos: TUDO OK.")
