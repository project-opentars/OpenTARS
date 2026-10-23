"""Tudo sob demanda: nada é carregado ao abrir, e o que fica ocioso sai da memória cedo."""
import os
import sys
import tempfile
import time

CASA = tempfile.mkdtemp(prefix="opentars-casa-")
os.environ["HOME"] = CASA
os.environ["TARS_ARQUIVO_SESSOES"] = os.path.join(CASA, "sessoes.json")
for v in ("TARS_KEEP_ALIVE", "TARS_KEEP_ALIVE_VISAO", "TARS_KEEP_ALIVE_AJUDANTE", "TARS_PRECARGA"):
    os.environ.pop(v, None)

sys.path.insert(0, os.path.dirname(__file__))
from _util import carregar_tars  # noqa: E402

tars = carregar_tars()

# 1. Tempos padrão: conversa 5 min; visão e ajudante 2 min (eram 30 min pra todos)
assert tars.KEEP_ALIVE == "5m" and tars.KEEP_ALIVE_VISAO == "2m" and tars.KEEP_ALIVE_AJUDANTE == "2m"
print("OK: modelo da conversa 5 min, visão e ajudante 2 min na memória")

# 2. Abrir o openTARS não carrega nada (nem Murph em fio, nem Cooper)
import threading  # noqa: E402
THREAD_REAL = threading.Thread
fios = []
tars.threading.Thread = lambda *a, **k: fios.append(k) or type("T", (), {"start": lambda s: fios.append("start")})()
tars.aquecer_ajudante()
assert fios == [], fios
print("OK: aquecer_ajudante não dispara nada sem TARS_PRECARGA")
tars.PRECARGA = True
tars.aquecer_visao = lambda: fios.append("cooper")
tars.aquecer_ajudante()
assert "cooper" in fios and "start" in fios
tars.PRECARGA = False
print("OK: TARS_PRECARGA=1 devolve a pré-carga")

# 3. O Cooper usa o tempo curto de visão
tars.threading.Thread = THREAD_REAL
pedidos = []


class Resp:
    status_code = 200

    def json(self):
        return {"message": {"content": '{"x": 500, "y": 500}'}}


tars._SESSION.post = lambda url, json=None, timeout=None, **k: pedidos.append(json) or Resp()
tars._visao_estado.update(pausado_ate=0.0, quente=False, erro="")
tars.perguntar_visao("ProjectOpenTARS/cooper:latest", "onde?", imagem_b64="AAAA")
assert pedidos[-1]["keep_alive"] == "2m", pedidos[-1]
print("OK: o Cooper sai da memória 2 min depois do último uso")

# 4. Digitar aquece o modelo da conversa (1x a cada 30 s) e não toca em servidor externo
pedidos.clear()
tars.modo_modelo = "MANUAL"
tars.modelo_manual = "qwen3:4b"
tars._ultimo_aquecimento["em"] = 0.0
tars.aquecer_modelo_da_conversa()
tars.aquecer_modelo_da_conversa()
time.sleep(0.3)
assert len(pedidos) == 1 and pedidos[0]["model"] == "qwen3:4b" and pedidos[0]["prompt"] == "" and pedidos[0]["keep_alive"] == "5m", pedidos
print("OK: ao digitar, o modelo da conversa é aquecido uma única vez (a cada 30 s)")
print("\nTUDO OK.")
