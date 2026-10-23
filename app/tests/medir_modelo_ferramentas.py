"""Medição (não entra no run_all): um modelo do Ollama chama as ferramentas do Gargantua nos pedidos do dia a dia?
Manda ao Ollama de VERDADE o prompt do Gargantua e as 19 ferramentas (como o app manda), sem executar nada, e conta:
  - pedidos de ação: chamou alguma ferramenta? a certa?
  - pergunta simples: respondeu sem ferramenta?
Mesma ideia da medição de 14/10 que achou o defeito do think=false.
Uso: TARS_TESTE_OLLAMA_REAL=1 python3 tests/medir_modelo_ferramentas.py MODELO [REPETICOES] [think|nothink|omitir]
     TARS_MEDIR_CPU=1 mede só no processador (num_gpu 0). O app manda think=false para o Gargantua 2: use nothink."""
import json
import os
import sys
import time
import urllib.request

os.environ["TARS_TESTE_OLLAMA_REAL"] = "1"
from _util import carregar_tars  # noqa: E402

tars = carregar_tars()
modelo = sys.argv[1]
repeticoes = int(sys.argv[2]) if len(sys.argv) > 2 else 3
modo_think = sys.argv[3] if len(sys.argv) > 3 else "omitir"

# (pedido, ferramentas aceitas; None = não deve chamar ferramenta)
PEDIDOS = [
    ("abre a calculadora", {"open_application"}),
    ("cria a pasta Fotos em Documentos", {"execute_terminal"}),
    ("quanto é 310 mais 506? usa a calculadora", {"open_application"}),
    ("procura receitas de lasanha no youtube", {"search_web", "open_website"}),
    ("quanta memória RAM eu estou usando?", {"execute_terminal"}),
    ("lista os arquivos da pasta Downloads", {"execute_terminal", "list_files", "list_directory"}),
    ("abre o navegador e entra no github.com", {"open_website", "open_application"}),
    ("oi, tudo bem? quem é você?", None),
    ("o que é uma pasta no linux?", None),
]
tools = tars.ferramentas_gargantua()
nomes_validos = {f["function"]["name"] for f in tools}


def chamar(pedido):
    corpo = {"model": modelo, "stream": False, "keep_alive": "5m", "tools": tools,
             "messages": [{"role": "system", "content": tars.SISTEMA_GARGANTUA}, {"role": "user", "content": pedido}],
             "options": {"temperature": 0.1, "num_ctx": 4096}}
    if os.environ.get("TARS_MEDIR_CPU") == "1":      # o tempo "só no processador": nenhuma camada na placa
        corpo["options"]["num_gpu"] = 0
    if modo_think == "think":
        corpo["think"] = True
    elif modo_think == "nothink":
        corpo["think"] = False
    r = urllib.request.Request("http://127.0.0.1:11434/api/chat", json.dumps(corpo).encode(), {"Content-Type": "application/json"})
    t0 = time.time()
    resposta = json.loads(urllib.request.urlopen(r, timeout=600).read())
    m = resposta["message"]
    return [c["function"]["name"] for c in m.get("tool_calls") or []], m.get("content", ""), m.get("thinking", ""), time.time() - t0


certos = total_acao = sem_ferr_ok = total_perg = inventadas = 0
tempos, pensou = [], 0
for pedido, aceitas in PEDIDOS:
    linha = []
    for _ in range(repeticoes):
        chamadas, texto, pensamento, s = chamar(pedido)
        tempos.append(s)
        pensou += bool(pensamento)
        inventadas += sum(1 for c in chamadas if c not in nomes_validos)
        if aceitas is None:
            total_perg += 1
            ok = not chamadas
            sem_ferr_ok += ok
        else:
            total_acao += 1
            ok = bool(chamadas) and chamadas[0] in aceitas
            certos += ok
        linha.append(("ok " if ok else "ERRO ") + (",".join(chamadas) or "sem ferramenta"))
    print(f"{pedido[:44]:44} | " + " | ".join(linha), flush=True)
print(f"\n{modelo} (think={modo_think}): ação certa {certos}/{total_acao}, pergunta sem ferramenta {sem_ferr_ok}/{total_perg}, "
      f"ferramenta inventada {inventadas}, com raciocínio {pensou}/{len(tempos)}, tempo médio {sum(tempos) / len(tempos):.1f}s")
