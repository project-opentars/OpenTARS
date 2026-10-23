"""Fumaça na TELA DE VERDADE (não entra no run_all, que roda em tela falsa): abre a janela no DISPLAY da pessoa, com as
fontes e o fontconfig do sistema, e passa por todas as páginas de Configurações no modo Pro, a conversa com respostas
que têm glifos difíceis, e o painel do sino com avisos assim. Dados numa casa temporária e Ollama de mentira: nada da
pessoa é lido nem mudado.

Por que existe (16/10): a página dos Probes derrubava a janela (segfault no fontconfig) no PC do Enzo e nenhum teste
pegou, porque em tela falsa o Qt não passa pelo mesmo caminho. empacotamento/conferir.sh roda isto antes de publicar.

Uso: python3 tests/fumaca_tela_real.py     (código 0 = passou; queda nativa = 139)"""
import os
import sys
import tempfile
import time
from pathlib import Path

if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
    print("fumaça na tela real: PULADA (sem sessão gráfica)")
    sys.exit(0)
os.environ.pop("QT_QPA_PLATFORM", None)            # a plataforma de verdade (o criar_aplicativo escolhe xcb)
CASA = tempfile.mkdtemp(prefix="opentars-fumaca-")
for var, nome in (("TARS_ARQUIVO_SESSOES", "sessoes.json"), ("TARS_ARQUIVO_PRIMEIRO_USO", "primeiro_uso.json"),
                  ("TARS_ARQUIVO_CONFIG", "config.json"), ("TARS_ARQUIVO_PROBES", "probes.json")):
    os.environ[var] = os.path.join(CASA, nome)
os.environ["XDG_CONFIG_HOME"] = os.path.join(CASA, ".config")
# o cache de fontes de VERDADE (o _util dos testes põe um novo, e foi por isso que nenhum teste viu o cache corrompido)
os.environ.setdefault("XDG_CACHE_HOME", str(Path.home() / ".cache"))

from _util import carregar_tars  # noqa: E402
import fake_ollama  # noqa: E402

servidor, url = fake_ollama.subir(modelos=["ProjectOpenTARS/Gargantua:latest"])
os.environ["OLLAMA_HOST"] = url
tars = carregar_tars()
tars.avisos_de_ambiente = lambda: []
tars.aquecer_ajudante = lambda: None

import faulthandler  # noqa: E402

faulthandler.enable()
from PySide6.QtTest import QTest  # noqa: E402

import tars_historico  # noqa: E402
import tars_modos  # noqa: E402
import tars_probes as tp  # noqa: E402
from tars_qt.primeiro_uso import criar_aplicativo  # noqa: E402
from tars_qt.principal import JanelaPrincipal  # noqa: E402

DIFICEIS = "★ ● ✗ 中文 日本語 한국어 ✨ 🎉 ∑ → Ω"
app = criar_aplicativo(["opentars"])
tp.ligar_servico = lambda ligado, iniciar=True: ligado       # não mexe no início automático de verdade
tars_modos.definir_modo("pro")


def esperar(ms=250):
    fim = time.time() + ms / 1000
    while time.time() < fim:
        app.processEvents()
        QTest.qWait(20)


# o caso mínimo que derrubava o Qt com o cache de fontes corrompido (tema.preparar_fontconfig protege): texto cru,
# sem passar pelo filtro de glifos, num QLabel comum
from PySide6.QtWidgets import QLabel  # noqa: E402
cru = QLabel(f"Texto cru: {DIFICEIS}")
cru.show()
esperar()
cru.close()
print("ok: texto cru com glifos difíceis num QLabel", flush=True)

ps = tp.Probes()
_m, bruto, regra = tp.plano_do_passo_a_passo("feed", {"url": "https://github.com/a/b"})
p, _ = ps.criar(_m, bruto, regra=regra)
ps.registrar(p["id"], {"alertar": True, "mensagem": f"1 novidade: {DIFICEIS}", "itens": [f"https://x.org/{DIFICEIS}"],
                       "estado": {}})

j = JanelaPrincipal(tars, historico=tars_historico.Historico(os.path.join(CASA, "historico.json")), capturar_stdout=False)
j.resize(1200, 800)
j.show()
esperar(500)
for nome in j.config.paginas:
    j.abrir_config(nome)
    esperar()
    print("ok: página", nome, flush=True)
pg = j.config.paginas["probes"]
for tipo in pg.blocos:
    pg.blocos[tipo].click()
    esperar(100)
print("ok: passo a passo dos Probes", flush=True)
j.pilha.setCurrentIndex(0)
j._ao_evento("resposta", {"texto": f"Resposta com glifos: {DIFICEIS}"})
j._ao_evento("fim_stream", {})
esperar()
print("ok: conversa com glifos difíceis", flush=True)
j.cabecalho.sino.olhar()
j.cabecalho.sino.click()
esperar(400)
j.cabecalho.sino.painel.hide()
print("ok: sino e painel de avisos", flush=True)
j._saindo = True
j.close()
servidor.shutdown()
print("\nFUMAÇA OK: a janela de verdade abriu todas as telas sem cair.", flush=True)
os._exit(0)
