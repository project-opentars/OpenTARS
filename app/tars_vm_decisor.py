"""5.3 (F7): o decisor de uma missão na VM, que usa a visão do Gargantua 2 só para ACHAR o que clicar.
O Gargantua 2 foi treinado para localizar elementos ("onde está o botão X?"), não para planejar cliques; por isso o plano é um
roteiro de passos ({"achar": "Terminal"}, {"digitar": "..."}, {"atalho": "ctrl+l"}, {"esperar": 3}) e a visão só diz onde fica o alvo.
Se não achar o alvo depois de tentar de novo, a missão termina dizendo qual alvo faltou (nunca clica no escuro)."""
import base64
import json
import urllib.request
from pathlib import Path

import tars_visao

MODELO = "ProjectOpenTARS/Gargantua-2:latest"


def perguntar_ollama(png, pergunta, modelo=MODELO, host="http://127.0.0.1:11434", tempo=60):
    corpo = {"model": modelo, "stream": False, "think": False, "options": {"temperature": 0.0, "num_predict": 64},
             "messages": [{"role": "user", "content": pergunta, "images": [base64.b64encode(Path(png).read_bytes()).decode()]}]}
    req = urllib.request.Request(host + "/api/chat", json.dumps(corpo).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=tempo) as r:
        return json.load(r)["message"]["content"]


def por_roteiro(roteiro, perguntar=perguntar_ollama, tamanho=None, tentativas=2):
    """Devolve decisor(tela_png, historico). `tamanho(png) -> (largura, altura)` (padrão: lê o PNG)."""
    import tars_vm_controle as ctl
    tamanho = tamanho or ctl.tamanho_do_png
    fila = list(roteiro)
    pendente = {"achar": None, "falhas": 0}

    def decisor(tela, historico):
        while True:
            if not fila:
                return {"tipo": "terminar", "resultado": "roteiro concluído"}
            passo = fila[0]
            if "achar" in passo:
                lido = tars_visao.ler_ponto(perguntar(tela, tars_visao.pergunta_localizar(passo["achar"])))
                if lido and lido[0] == "achou":
                    fila.pop(0)
                    largura, altura = tamanho(tela)
                    x, y = tars_visao.para_pixels(lido[1], lido[2], largura, altura)
                    return {"tipo": passo.get("acao", "clicar"), "x": x, "y": y}
                pendente["falhas"] += 1
                if pendente["falhas"] >= tentativas:
                    return {"tipo": "terminar", "resultado": f"não achei na tela: {passo['achar']}"}
                return {"tipo": "esperar", "segundos": 3}
            pendente["falhas"] = 0
            fila.pop(0)
            if "digitar" in passo:
                return {"tipo": "digitar", "texto": passo["digitar"]}
            if "atalho" in passo:
                return {"tipo": "atalho", "teclas": passo["atalho"]}
            return {"tipo": "esperar", "segundos": passo.get("esperar", 2)}
    return decisor
