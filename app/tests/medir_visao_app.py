"""Medição (não entra no run_all): achar o botão pelo caminho do app. Usa as telas desenhadas da prova de visão do Lab
(~/opentars-lab/cooper/dados/prova.jsonl, resposta conhecida) e pergunta do jeito que o openTARS pergunta quando vai clicar
(`localizar_com_visao`, com a pergunta do app, não a do Lab). Acerto = o ponto cai dentro da caixa do elemento.
É a medida "achar botão 34/40" do site e da página do ollama.com (o script de 18/10 não tinha sido guardado).

Uso: python3 tests/medir_visao_app.py MODELO [QUANTOS=40]"""
import json
import os
import re
import sys
from pathlib import Path

os.environ["TARS_TESTE_OLLAMA_REAL"] = "1"
from _util import carregar_tars  # noqa: E402

from PIL import Image  # noqa: E402

tars = carregar_tars()
modelo = sys.argv[1]
quantos = int(sys.argv[2]) if len(sys.argv) > 2 else 40
pasta = Path(os.environ.get("OPENTARS_LAB_DIR") or Path.home() / "opentars-lab") / "cooper" / "dados"
itens = [json.loads(l) for l in (pasta / "prova.jsonl").read_text(encoding="utf-8").splitlines()]
itens = [i for i in itens if i["tarefa"] == "localizar" and not i["ausente"] and i.get("alvo")][:quantos]

acertos, saida = 0, []
for i, item in enumerate(itens, 1):
    nome = re.search(r'"([^"]+)"', item["pergunta"]).group(1)
    imagem = Image.open(pasta / item["imagem"]).convert("RGB")
    ponto, _tag = tars.localizar_com_visao(nome, imagem, tag=modelo)
    x0, y0, x1, y1 = item["alvo"]
    w, h = imagem.size
    caixa = (x0 * w / 1000, y0 * h / 1000, x1 * w / 1000, y1 * h / 1000)
    ok = isinstance(ponto, tuple) and caixa[0] <= ponto[0] <= caixa[2] and caixa[1] <= ponto[1] <= caixa[3]
    acertos += ok
    saida.append({"id": item["id"], "nome": nome, "ponto": ponto, "caixa": caixa, "ok": ok})
    print(f"\r  {i}/{len(itens)}  acertos {acertos}", end="", flush=True)
print(f"\nAchar o elemento pelo caminho do app: {acertos}/{len(itens)} ({modelo})")
if len(sys.argv) > 3:
    Path(sys.argv[3]).write_text(json.dumps(saida, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
