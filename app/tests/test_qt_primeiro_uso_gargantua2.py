"""18/10: a tela de download do primeiro uso baixa só o Gargantua 2 (que enxerga a tela; o Cooper foi descontinuado e não
é mais oferecido). Qt offscreen, Ollama de mentira."""
import os
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["TARS_MODELO_GARGANTUA"] = "ProjectOpenTARS/Gargantua-2"
from _util import RAIZ  # noqa: F401,E402

try:
    from PySide6.QtTest import QTest
except ImportError:
    print("test_qt_primeiro_uso_gargantua2: PULADO (PySide6 não instalado)")
    sys.exit(0)

import fake_ollama  # noqa: E402
import tars_i18n  # noqa: E402
import tars_primeiro_uso as pu  # noqa: E402

pasta = tempfile.mkdtemp(prefix="opentars-qt-garg2-")
os.environ["TARS_ARQUIVO_PRIMEIRO_USO"] = os.path.join(pasta, "primeiro_uso.json")
os.environ["TARS_ARQUIVO_NUVEM"] = os.path.join(pasta, "nuvem.json")
from tars_qt.primeiro_uso import JanelaPrimeiroUso, criar_aplicativo  # noqa: E402

app = criar_aplicativo(["teste"])
tars_i18n.definir_idioma("pt_BR")
GARG2, GARG1, COOPER = "ProjectOpenTARS/Gargantua-2:latest", "ProjectOpenTARS/Gargantua:latest", "ProjectOpenTARS/cooper:1.2"


def esperar(condicao, segundos=20, o_que=""):
    fim = time.time() + segundos
    while time.time() < fim:
        app.processEvents()
        if condicao():
            return
        QTest.qWait(20)
    raise AssertionError(f"tempo esgotado: {o_que}")


def abrir(modelos, **opcoes):
    servidor, url = fake_ollama.subir(modelos=modelos, **opcoes)
    os.environ["OLLAMA_HOST"] = url
    j = JanelaPrimeiroUso()
    j.show()
    j.ir("gargantua")
    return j, j.paginas["gargantua"], servidor


def puxados(servidor):
    return [c["model"] for m, p, c in servidor.pedidos if p == "/api/pull"]


# 1) nada instalado: baixa o Gargantua 2 e o Lite obrigatório (25/10), sem opção nem fase do Cooper
j, pg, srv = abrir([])
esperar(lambda: pg.pronto and pg.b_continuar.isEnabled(), o_que="baixar o Gargantua 2")
assert puxados(srv) == [pu.MODELO_GARGANTUA, pu.MODELO_GARGANTUA_LITE] == \
    ["ProjectOpenTARS/Gargantua-2", "ProjectOpenTARS/Gargantua-2:lite"], puxados(srv)
assert not hasattr(pg, "c_cooper") and not hasattr(pg, "baixar_cooper"), "o Cooper não é mais oferecido"
j.close()
print("OK: sem nenhum modelo, baixa o Gargantua 2 e o Lite (a IA de segundo plano)")

# 2) o Gargantua 2 já está instalado: nada é baixado
j, pg, srv = abrir([GARG2, pu.MODELO_GARGANTUA_LITE])
esperar(lambda: pg.b_continuar.isEnabled(), o_que="já instalado")
assert puxados(srv) == [] and pg.h1.plano() == tars_i18n.t("pu.garg.titulo_ja")
j.close()
j, pg, srv = abrir([GARG2])
esperar(lambda: pg.pronto and pg.b_continuar.isEnabled(), o_que="só falta o Lite")
assert puxados(srv) == [pu.MODELO_GARGANTUA_LITE], puxados(srv)
j.close()
print("OK: com o Gargantua 2 e o Lite instalados, nada é baixado; sem o Lite, só ele vem")

# 3) quem já tem o Gargantua 1.x continua com ele (não é obrigado a baixar o novo)
j, pg, srv = abrir([GARG1])
esperar(lambda: pg.pronto and pg.b_continuar.isEnabled(), o_que="Gargantua antigo")
assert puxados(srv) == [pu.MODELO_GARGANTUA_LITE], puxados(srv)
j.close()
print("OK: o Gargantua 1.x instalado vale como principal; só o Lite obrigatório vem")

# 4) um Cooper instalado não conta como Gargantua e nada o baixa
j, pg, srv = abrir([COOPER])
esperar(lambda: pg.pronto and pg.b_continuar.isEnabled(), o_que="só o Cooper")
assert puxados(srv) == [pu.MODELO_GARGANTUA, pu.MODELO_GARGANTUA_LITE], puxados(srv)
j.close()
print("OK: o Cooper antigo não substitui o Gargantua, e o Gargantua 2 vem baixado")

# 4b) 25/10: os modelinhos de foto entram na fila depois dos modelos (obrigatórios); aqui de mentira
import tars_modelinhos  # noqa: E402
os.environ.pop("TARS_SEM_MODELINHOS", None)
originais = tars_modelinhos.faltando, tars_modelinhos.baixar_todos
baixados = []
tars_modelinhos.faltando = lambda: [] if baixados else ["fundo"]
tars_modelinhos.bytes_faltando = lambda: 300_000_000
tars_modelinhos.baixar_todos = lambda ao_progredir=None, cancelado=None: (ao_progredir(1, 1), baixados.append(1), (True, ""))[2]
j, pg, srv = abrir([GARG2, pu.MODELO_GARGANTUA_LITE])
esperar(lambda: pg.pronto and pg.b_continuar.isEnabled(), o_que="modelinhos")
assert baixados == [1] and puxados(srv) == [], (baixados, puxados(srv))
j.close()
tars_modelinhos.faltando, tars_modelinhos.baixar_todos = originais
os.environ["TARS_SEM_MODELINHOS"] = "1"
print("OK: os modelinhos de foto entram na fila do primeiro uso, mesmo com os modelos já instalados")

# 5) espaço: o Gargantua 2 precisa de ~1,7 GB, e o aviso aparece quando falta
real = pu.espaco_livre_gb
pu.espaco_livre_gb = lambda caminho=None: 1.0
j, pg, srv = abrir([])
esperar(lambda: pg.baixando or pg.pronto or pg.b_continuar.isEnabled(), o_que="pouco espaço")
assert "1.0" in pg.l_espaco.texto.plano(), pg.l_espaco.texto.plano()
pu.espaco_livre_gb = real
j.close()
print("OK: pouco espaço avisa")

print("\nTUDO OK.")
