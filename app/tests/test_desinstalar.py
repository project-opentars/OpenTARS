"""5.2: opentars --desinstalar. Pergunta antes de apagar dados e, à parte, os modelos oficiais; sem resposta não apaga
nada; o .deb só mostra o comando do apt; a instalação por script chama o --remover do próprio instalador."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import RAIZ  # noqa: E402,F401
import fake_ollama  # noqa: E402
import tars_desinstalar as d  # noqa: E402
import tars_gerenciar_modelos as gm  # noqa: E402

casa = Path(tempfile.mkdtemp(prefix="opentars-desinst-"))
os.environ.update(HOME=str(casa), XDG_CONFIG_HOME=str(casa / "cfg"), XDG_DATA_HOME=str(casa / "dados"),
                  XDG_CACHE_HOME=str(casa / "cache"), TARS_DIR_LOG=str(casa / ".tars_log"))
for pasta in ("cfg/opentars", "dados/opentars", ".tars_log"):
    (casa / pasta).mkdir(parents=True)
(casa / ".tars_sessoes.json").write_text("{}")
(casa / "opentars-autoteste.txt").write_text("relatório")
servidor, url = fake_ollama.subir(modelos=["ProjectOpenTARS/Gargantua-2:latest", "qwen3:4b"])
t = lambda chave, **k: chave  # noqa: E731
apagados, rodados, soltos = [], [], []
original_apagar = gm.apagar
gm.apagar = lambda nome, host: apagados.append(nome) or (True, "")
original_pelo_script = d.tars_atualizacao.pelo_script
try:
    # sem terminal para responder: nada sai
    def sem_resposta(_pergunta):
        raise EOFError
    d.tars_atualizacao.pelo_script = lambda: False
    assert d.executar(url, t, entrada=sem_resposta) == 0
    assert (casa / ".tars_sessoes.json").exists() and (casa / "cfg/opentars").exists() and not apagados
    print("OK: sem resposta, não apaga dados nem modelos")

    # "não" para os dados, "sim" para os modelos: só os oficiais saem, os outros modelos do Ollama ficam
    respostas = iter(["n", "s"])
    d.executar(url, t, entrada=lambda _p: next(respostas))
    assert (casa / "dados/opentars").exists() and apagados == ["ProjectOpenTARS/Gargantua-2:latest"], apagados
    print("OK: os modelos oficiais saem só com o sim; o qwen3 da pessoa fica")

    # instalado pelo script no Linux: "sim" para os dados, chama o --remover do instalador; o relatório fica
    d.tars_atualizacao.pelo_script = lambda: True
    respostas = iter(["s", "n"])
    codigo = d.executar(url, t, entrada=lambda _p: next(respostas),
                        rodar=lambda cmd: rodados.append(cmd) or type("R", (), {"returncode": 0})())
    assert codigo == 0 and rodados and rodados[0][-1] == "--remover" and rodados[0][1].endswith("linux/instalar.sh"), rodados
    assert not any(x.exists() for x in (casa / ".tars_sessoes.json", casa / "cfg/opentars", casa / "dados/opentars", casa / ".tars_log"))
    assert (casa / "opentars-autoteste.txt").exists()
    print("OK: com o sim, conversas, configurações e registros saem; o removedor do script roda; o relatório fica")
finally:
    gm.apagar = original_apagar
    d.tars_atualizacao.pelo_script = original_pelo_script
    servidor.shutdown()
print("test_desinstalar: TUDO OK.")
