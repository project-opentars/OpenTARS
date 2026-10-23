"""5.0 Tesseract: o histórico de conversas (tars_historico.py)."""

import datetime as dt
import json
import os
import stat
import tempfile

from _util import RAIZ  # noqa: F401

import tars_historico as h

pasta = tempfile.mkdtemp(prefix="opentars-hist-")
arq = os.path.join(pasta, "historico.json")
relogio = {"t": dt.datetime(2026, 10, 6, 15, 0).timestamp()}
hist = h.Historico(arq, agora=lambda: relogio["t"])

sistema = {"role": "system", "content": "regras"}
conversa = [sistema,
            {"role": "user", "content": "Organiza minha pasta Downloads: separa por tipo"},
            {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "execute_terminal", "arguments": {}}}]},
            {"role": "tool", "content": "ok"},
            {"role": "user", "content": "[Automatic message from openTARS] confira"},
            {"role": "user", "content": "e depois?", "images": ["QUJD"]},
            {"role": "assistant", "content": "Pronto."}]

assert h.titulo_da(conversa) == "Organiza minha pasta Downloads: separa por tipo", "pula o sistema e as mensagens automáticas"
assert h.titulo_da([{"role": "user", "content": "x" * 100}]).endswith("…") and len(h.titulo_da([{"role": "user", "content": "x" * 100}])) == 60
assert not hist.salvar("a", [sistema]), "sem pedido da pessoa não grava nada"
assert hist.listar() == []

assert hist.salvar("a", conversa)
assert stat.S_IMODE(os.stat(arq).st_mode) == 0o600
guardada = hist.abrir("a")
assert guardada[0]["role"] == "user" and all(m["role"] != "system" for m in guardada) and all("images" not in m for m in guardada)
assert hist.abrir("nao-existe") is None

relogio["t"] += 60
hist.salvar("b", [{"role": "user", "content": "Procurar preço de SSD"}, {"role": "assistant", "content": "R$ 300"}])
assert [c["id"] for c in hist.listar()] == ["b", "a"], "mais recente primeiro"
assert [c["id"] for c in hist.listar("ssd")] == ["b"] and [c["id"] for c in hist.listar("DOWNLOADS")] == ["a"]
assert [c["id"] for c in hist.listar("r$ 300")] == ["b"], "a busca olha as mensagens também"
assert hist.listar("zzz") == []

relogio["t"] += 60
hist.salvar("a", conversa + [{"role": "user", "content": "mais um"}])    # atualizar não duplica
assert [c["id"] for c in hist.listar()] == ["a", "b"] and len(hist.abrir("a")) == 7

assert hist.renomear("a", "  Meus   Downloads ") and hist.listar()[0]["titulo"] == "Meus Downloads"
hist.salvar("a", conversa)
assert hist.listar()[0]["titulo"] == "Meus Downloads", "o nome escolhido sobrevive a novas mensagens"

# agrupar por dia
agora = dt.datetime(2026, 10, 6, 15, 0).timestamp()
dia = 86400
itens = [{"id": i, "titulo": i, "atualizada": agora - d} for i, d in
         (("h", 3600), ("o", dia), ("s", 3 * dia), ("v", 20 * dia))]
assert [(k, [x["id"] for x in v]) for k, v in h.agrupar_por_dia(itens, agora)] == \
    [("hoje", ["h"]), ("ontem", ["o"]), ("semana", ["s"]), ("antes", ["v"])]

# exportar e apagar
saida = os.path.join(pasta, "export.json")
assert hist.exportar(saida) == 2 and len(json.load(open(saida))["conversas"]) == 2
assert hist.apagar("b") and not hist.apagar("b") and [c["id"] for c in hist.listar()] == ["a"]
assert hist.apagar_tudo() == 1 and hist.listar() == [] and not os.path.exists(arq)
assert not any(f.endswith(".tmp") for f in os.listdir(pasta))

# arquivo corrompido não derruba nada
open(arq, "w").write("{quebrado")
assert hist.listar() == [] and hist.salvar("c", conversa) and len(hist.listar()) == 1

# limite
for i in range(h.LIMITE_CONVERSAS + 5):
    relogio["t"] += 1
    hist.salvar(f"n{i}", [{"role": "user", "content": f"pedido {i}"}])
assert len(hist.listar()) == h.LIMITE_CONVERSAS

print("test_historico: OK")
