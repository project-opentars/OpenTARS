#!/usr/bin/env python3
"""A página "Gerenciar modelos": lista o que o Ollama tem (maior primeiro), apaga só depois de confirmar, atualiza com
barra de progresso, avisa o app e trata erro e Ollama fora do ar."""
import os, sys, types
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
except ImportError:
    print("test_gerenciar_modelos: PULADO (PySide6 não instalado)")
    sys.exit(0)
import fake_ollama
import tars_gerenciar_modelos as gm
import tars_modos as modos
import tars_primeiro_uso as pu

app = QApplication.instance() or QApplication([])
from tars_qt import configuracoes as cfgmod, tema
app.setStyleSheet(tema.folha_de_estilo())

MODELOS = [
    {"name": "qwen3:4b", "size": 2_500_000_000, "modified_at": "2026-10-08T12:00:00-03:00",
     "details": {"family": "qwen3", "parameter_size": "4.0B", "quantization_level": "Q4_K_M"}},
    {"name": "ProjectOpenTARS/Gargantua-2:latest", "size": 1_600_000_000, "modified_at": "2026-10-18T09:00:00-03:00",
     "details": {"family": "qwen35", "parameter_size": "2B", "quantization_level": "Q4_0"}},
    {"name": "gpt-oss:20b-cloud", "size": 0, "modified_at": "2026-10-12T10:00:00-03:00", "details": {}},
    {"name": "qwen3:8b", "size": 5_200_000_000, "modified_at": "2026-10-01T12:00:00-03:00",
     "details": {"family": "qwen3", "parameter_size": "8.2B", "quantization_level": "Q4_K_M"}},
]
servidor, url = fake_ollama.subir(modelos=MODELOS)

# 1. listar: maior primeiro, detalhes, selos
lista = gm.listar(url)
assert [m["nome"] for m in lista] == ["qwen3:8b", "qwen3:4b", "ProjectOpenTARS/Gargantua-2:latest", "gpt-oss:20b-cloud"], lista
assert lista[0]["gb"] == 5.2 and lista[0]["parametros"] == "8.2B" and lista[0]["quantizacao"] == "Q4_K_M" and lista[0]["data"] == "2026-10-01"
assert lista[2]["oficial"] and not lista[0]["oficial"] and lista[3]["nuvem"] and not lista[0]["nuvem"]
assert abs(gm.total_gb(lista) - 9.3) < 1e-6
assert gm.detalhe(lista[0], lambda gb: f"{gb:.1f} GB") == "8.2B · Q4_K_M · 5.2 GB · 2026-10-01"
assert gm.detalhe(lista[3], lambda gb: "x") == "2026-10-12", "sem tamanho nem detalhes inventados"
try:
    gm.listar("http://127.0.0.1:9"); assert False
except OSError:
    pass
print("OK: lista do maior para o menor, com detalhes, selos e total")

# 2. apagar e erro
ok, erro = gm.apagar("qwen3:8b", url)
assert ok and not erro
assert ("DELETE", "/api/delete", {"model": "qwen3:8b", "name": "qwen3:8b"}) in servidor.pedidos
assert [m["nome"] for m in gm.listar(url)][0] == "qwen3:4b"
ok, erro = gm.apagar("nao-existe:1", url)
assert not ok and "not found" in erro, erro
print("OK: apagar chama o DELETE do Ollama e mostra o erro dele")

# 3. a página
class Emite:
    def __init__(self): self.vezes = 0
    def emit(self): self.vezes += 1

class Cfg:
    def __init__(self, u):
        self.nucleo = types.SimpleNamespace(OLLAMA_HOST=u)
        self.modelos_mudaram = Emite()
    def em_segundo_plano(self, trabalho, ao_fim):
        try:
            r = trabalho()
        except Exception as e:
            r = e
        ao_fim(r)
    def depois(self, f): f()

assert "cfg.gerenciar" in modos.RECURSOS["base"] and "cfg.gerenciar" in modos.RECURSOS["pro"] and "cfg.gerenciar" not in modos.RECURSOS["lite"]
assert "gerenciar" in cfgmod.PAGINAS and cfgmod.PAGINAS.index("gerenciar") == cfgmod.PAGINAS.index("modelos") + 1
cfg = Cfg(url)
pg = cfgmod.PGerenciar(cfg)
pg.ao_abrir()
assert list(pg.cartoes) == ["qwen3:4b", "ProjectOpenTARS/Gargantua-2:latest", "gpt-oss:20b-cloud"], list(pg.cartoes)
assert "3 " in pg.resumo.text() and "4.1 GB" in pg.resumo.text(), pg.resumo.text()
nuvem = pg.cartoes["gpt-oss:20b-cloud"]
assert nuvem.b_atualizar.isHidden() and not nuvem.b_apagar.isHidden(), "nuvem não atualiza (não há arquivos)"
print("OK: a página lista os modelos e o resumo")

# apagar pede confirmação; "Manter" desiste; "Sim" apaga e avisa o app
c = pg.cartoes["qwen3:4b"]
c.b_apagar.click()
assert not c.confirmacao.isHidden() and not c.b_apagar.isEnabled()
pedidos = len(servidor.pedidos)
c.b_manter.click()
assert c.confirmacao.isHidden() and c.b_apagar.isEnabled() and len(servidor.pedidos) == pedidos, "nada foi apagado"
c.b_apagar.click()
c.b_confirmar.click()
assert "qwen3:4b" not in pg.cartoes and cfg.modelos_mudaram.vezes == 1
assert [p for p in servidor.pedidos if p[0] == "DELETE" and p[2]["model"] == "qwen3:4b"]
print("OK: apagar só depois de confirmar, e o app é avisado")

# o modelo oficial tem a pergunta mais forte
o = pg.cartoes["ProjectOpenTARS/Gargantua-2:latest"]
textos = " ".join(w.text() for w in o.confirmacao.findChildren(type(pg.resumo)))
assert "openTARS" in textos and "Gargantua-2" in textos, textos
print("OK: o modelo oficial avisa que o assistente o usa")

# erro ao apagar: o cartão fica e mostra o erro
servidor.erro_ao_apagar = "permission denied"
o.b_apagar.click(); o.b_confirmar.click()
assert "ProjectOpenTARS/Gargantua-2:latest" in pg.cartoes and "permission denied" in o.info.text()
assert o.confirmacao.isHidden() and o.b_apagar.isEnabled()
servidor.erro_ao_apagar = ""
print("OK: erro ao apagar aparece no cartão")

# atualizar: baixa de novo com a barra; sem camadas novas diz "já está"
vistos = []
orig = o.progresso
o.progresso = lambda pct, texto: (vistos.append(pct), orig(pct, texto))
o.b_atualizar.click()
assert vistos and vistos[-1] == 100 and any(p[0] == "POST" and p[1] == "/api/pull" and p[2]["model"] == "ProjectOpenTARS/Gargantua-2:latest" for p in servidor.pedidos)
assert "Updated" in o.info.text() or "Atualizado" in o.info.text()
assert cfg.modelos_mudaram.vezes == 2 and pg._ocupado is False and o.barra.isHidden()
real = pu.baixar_modelo
pu.baixar_modelo = lambda nome, host, ao_progredir=None, **k: (True, "")      # o Ollama não trouxe camada nova
o.b_atualizar.click()
assert "up to date" in o.info.text() or "mais nova" in o.info.text(), o.info.text()
pu.baixar_modelo = lambda *a, **k: (False, "sem rede")
o.b_atualizar.click()
assert "sem rede" in o.info.text()
pu.baixar_modelo = real
print("OK: atualizar mostra a barra, 'já está atualizado' e o erro")

# Ollama fora do ar e lista vazia
servidor.shutdown()
pg2 = cfgmod.PGerenciar(Cfg("http://127.0.0.1:9"))
pg2.ao_abrir()
assert pg2.cartoes == {} and ("Ollama" in pg2.resumo.text() or "ollama" in pg2.resumo.text().lower())
servidor2, url2 = fake_ollama.subir(modelos=[])
pg3 = cfgmod.PGerenciar(Cfg(url2)); pg3.ao_abrir()
assert pg3.cartoes == {} and ("Add some" in pg3.resumo.text() or "Adicione" in pg3.resumo.text())
servidor2.shutdown()
print("test_gerenciar_modelos: TUDO OK.")
