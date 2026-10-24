"""5.2 (F4): o painel das ações em arquivos. Renomear mostra a prévia com os nomes sugeridos (editáveis) e só muda com o
clique; desfazer volta; a lixeira só vai com o botão de confirmação. O modelo é de mentira."""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import RAIZ  # noqa: E402,F401
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from tars_qt import arquivos as pa  # noqa: E402

app = QApplication.instance() or QApplication([])
pasta = Path(tempfile.mkdtemp(prefix="opentars-painel-"))
for nome, texto in (("scan0001.txt", "NOTA FISCAL Mercado 03/10/2026"), ("scan0002.txt", "NOTA FISCAL Farmácia 03/10/2026")):
    (pasta / nome).write_text(texto)
pa.aa.acoes.rodar = lambda acao, texto, modelo, host, pergunta=None, **k: \
    ("nota fiscal mercado 03 10 2026" if "Mercado" in texto else "nota fiscal farmacia 03 10 2026") if acao == "perguntar" else "Resumo."
lixo = []
pa.aa.plataforma.lixeira = lixo.append


def esperar(condicao, limite=5):
    fim = time.time() + limite
    while time.time() < fim and not condicao():
        app.processEvents()
        time.sleep(0.02)
    assert condicao()


painel = pa.PainelArquivos("http://x", ["ProjectOpenTARS/Gargantua-2:latest"], "ProjectOpenTARS/Gargantua-2:lite",
                           "ProjectOpenTARS/Gargantua-2:latest")
arquivos = [str(pasta / "scan0001.txt"), str(pasta / "scan0002.txt")]
painel.abrir(arquivos)
assert painel.acao == "renomear" and not painel.botao_aplicar.isEnabled()
esperar(lambda: painel.botao_aplicar.isEnabled())
assert [c.text() for _p, c in painel.campos] == ["nota-fiscal-mercado-03-10-2026.txt", "nota-fiscal-farmacia-03-10-2026.txt"]
assert (pasta / "scan0001.txt").exists(), "a prévia não muda nada"
painel.campos[1][1].setText("farmacia-outubro.txt")          # a pessoa edita um nome antes de aplicar
painel.aplicar()
assert sorted(p.name for p in pasta.iterdir()) == ["farmacia-outubro.txt", "nota-fiscal-mercado-03-10-2026.txt"]
assert painel.botao_desfazer.isVisibleTo(painel)
painel.desfazer()
assert sorted(p.name for p in pasta.iterdir()) == ["scan0001.txt", "scan0002.txt"]
print("OK: renomear mostra a prévia editável, só muda com o clique, e desfazer volta os nomes")

painel.escolher("resumir")
painel.aplicar()
esperar(lambda: "Resumo." in painel.saida.toPlainText())
print("OK: resumir mostra o resumo de cada arquivo")

painel.escolher("lixeira")
assert not lixo
painel.aplicar()
assert lixo == arquivos, lixo
print("OK: a lixeira só vai com o botão de confirmação")
print("test_qt_arquivos: TUDO OK.")
