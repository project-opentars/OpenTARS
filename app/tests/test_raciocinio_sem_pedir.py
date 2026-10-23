"""Modelo que raciocina mesmo com think=false: o turno é cortado e refeito com /no_think."""
import os as _os
import tempfile as _tmp
_os.environ["TARS_ARQUIVO_SESSOES"] = _os.path.join(_tmp.mkdtemp(prefix="opentars-"), "s.json")  # a lista de quem raciocina fica ao lado

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _util import carregar_tars  # noqa: E402

tars = carregar_tars()
payloads = []


class Resp:
    def __init__(self, linhas):
        self.linhas, self.fechada = linhas, False

    def iter_lines(self):
        for x in self.linhas:
            if self.fechada:
                return
            yield json.dumps(x).encode()

    def close(self):
        self.fechada = True


def teimoso(payload):
    payloads.append(payload)
    if payload["messages"][-1]["content"].endswith("/no_think"):
        return Resp([{"message": {"content": "feito"}}, {"done": True}]), None
    pedacos = [{"message": {"content": "<think>"}}] + [{"message": {"content": "pensando e pensando. " * 3}} for _ in range(40)]
    return Resp(pedacos + [{"done": True}]), None


tars._chamar_ollama_stream = teimoso
tars.emitir = lambda *a, **k: None
msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "olhe a tela"}]
res, erro = tars._executar_turno_streaming("ProjectOpenTARS/gargantua:1.0", msgs, None, pensar=False)
assert erro is None and res["content"] == "feito", (res, erro)
assert len(payloads) == 2 and payloads[1]["messages"][-1]["content"] == "olhe a tela\n/no_think"
assert msgs[-1]["content"] == "olhe a tela", "o histórico guardado não muda"
assert "ProjectOpenTARS/gargantua:1.0" in tars._PENSA_MESMO_SEM_PEDIR
# na vez seguinte já vai com /no_think de cara (1 chamada só)
payloads.clear()
res, erro = tars._executar_turno_streaming("ProjectOpenTARS/gargantua:1.0", msgs, None, pensar=False)
assert res["content"] == "feito" and len(payloads) == 1
# quem foi pedido pra pensar não é cortado
payloads.clear()
tars._PENSA_MESMO_SEM_PEDIR.clear()
tars._chamar_ollama_stream = lambda p: (payloads.append(p), (Resp([{"message": {"content": "<think>" + "x" * 2000}}, {"message": {"content": "</think>ok"}}, {"done": True}]), None))[1]
res, erro = tars._executar_turno_streaming("qwen3:8b", msgs, None, pensar=True)
assert len(payloads) == 1 and res["content"] == "ok"
print("OK: raciocínio sem pedido é cortado e refeito com /no_think; quem pensa por pedido não é tocado")
print("\nTUDO OK.")

# a lista sobrevive a fechar e abrir o openTARS (fica em disco)
tars._PENSA_MESMO_SEM_PEDIR.clear()
tars._lembrar_que_pensa("ProjectOpenTARS/gargantua:1.0")
tars._PENSA_MESMO_SEM_PEDIR.clear()
tars._pensa_carregado["ok"] = False
tars._carregar_pensa_sem_pedir()
assert "ProjectOpenTARS/gargantua:1.0" in tars._PENSA_MESMO_SEM_PEDIR
print("OK: quem raciocina sem pedir fica guardado em disco")
