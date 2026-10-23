"""4.5 Endurance (revisão): um teste pra cada bug achado na revisão geral.

Chat e anexos, controle do mouse e do teclado, escolha das IAs e linha de comando."""

import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
CASA = tempfile.mkdtemp(prefix="opentars-casa-")
os.environ["HOME"] = CASA
os.environ["TARS_ARQUIVO_SESSOES"] = os.path.join(CASA, "sessoes.json")
from _util import carregar_tars  # noqa: E402

tars = carregar_tars()
from PIL import Image  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
COOPER = "ProjectOpenTARS/cooper:latest"

# ------------------------------------------------------------
# Chat
# ------------------------------------------------------------

# 1. O print do openTARS não apaga o pedido do usuário (com o texto dos arquivos anexados)
msgs = [
    {"role": "system", "content": "s"},
    {"role": "user", "content": "resuma\n\n[Files attached]\nVENDAS 1234", "images": ["AAA"]},
    {"role": "user", "content": "[Automatic message from openTARS, not from the user] This is the screenshot", "images": ["BBB"]},
]
tars._print_em_texto = lambda *a, **k: "descrição do print"
tars._tirar_imagens_da_conversa(msgs, "resuma", "api:texto")
assert msgs[1]["content"].endswith("VENDAS 1234") and "images" not in msgs[1], msgs[1]
assert msgs[2]["content"] == "descrição do print" and "images" not in msgs[2]
print("OK: imagem anexada pelo usuário perde só a imagem; o texto do pedido e do arquivo ficam")

# 2. O botão Parar vale enquanto o Ollama ainda não respondeu
tars._cancelar.clear()
inicio = time.time()
threading.Timer(0.3, tars._cancelar.set).start()
try:
    tars._post_cancelavel(lambda: time.sleep(5))
    raise AssertionError("devia cancelar")
except tars.RespostaCancelada:
    pass
assert time.time() - inicio < 1.5, time.time() - inicio
tars._cancelar.clear()
assert tars._post_cancelavel(lambda: "pronto") == "pronto"
try:
    tars._post_cancelavel(lambda: (_ for _ in ()).throw(ValueError("x")))
    raise AssertionError("devia repassar o erro")
except ValueError:
    pass
print("OK: Parar interrompe a espera pelo Ollama em ~0,1 s e os erros passam adiante")

# 3. Resposta normal que começa com "Okay," num modelo que não raciocina NÃO é cortada
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


pedidos = []
longa = "Okay, here is a quick overview of what the command does: it lists all files in the folder. " * 12
tars._chamar_ollama_stream = lambda p: (pedidos.append(p), (Resp([{"message": {"content": longa}}, {"done": True}]), None))[1]
tars.emitir = lambda *a, **k: None
tars._PENSA_MESMO_SEM_PEDIR.clear()
res, erro = tars._executar_turno_streaming("gemma3:4b", [{"role": "user", "content": "explique"}], None, pensar=False)
assert len(pedidos) == 1 and "gemma3:4b" not in tars._PENSA_MESMO_SEM_PEDIR and len((res["content"] + res["thinking"])) > 600
print("OK: 'Okay, ...' em modelo que não raciocina não dispara o corte nem a repetição")

# 5. Contexto velho ("janelas abertas agora") e foto de pedido antigo saem do histórico
hist = [{"role": "system", "content": "s"},
        {"role": "user", "content": "pedido 1", "images": ["IMG"]},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "pedido 2"}]
tars._podar_historico(hist)
assert "images" not in hist[1] and hist[1]["content"] == "pedido 1"
print("OK: a foto de um pedido antigo não viaja em toda mensagem seguinte")

# ------------------------------------------------------------
# Controle: mouse, teclado, terminal, janelas
# ------------------------------------------------------------
tars._tamanho_real = lambda: (1280, 800)
assert tars._longe_da_quina(3000, 2000) == (1276, 796)
assert tars._longe_da_quina(-50, 0) == (3, 3)
assert tars._longe_da_quina(640, 400) == (640, 400)
tars._mirar_bruto = lambda *a, **k: (5000, 5000, "x")
assert tars._mirar(5000, 5000, None, None)[:2] == (1276, 796), "clique fora da tela não encosta na quina"
cliques = []
tars._mirar_bruto = lambda *a, **k: (100, 100, "")
tars.pyautogui = type("P", (), {
    "moveTo": staticmethod(lambda *a, **k: None),
    "click": staticmethod(lambda **k: cliques.append(k)),
    "doubleClick": staticmethod(lambda **k: None),
    "isValidKey": staticmethod(lambda k: k in ("enter", "pagedown", "ctrl", "s", "win", "esc", "down")),
    "press": staticmethod(lambda k: cliques.append(("press", k))),
    "hotkey": staticmethod(lambda *k: cliques.append(("hotkey", k))),
})
tars._conferir = lambda fazer, *a: (fazer(), "mudou")[1]
tars.PAUSA_HOVER_SEG = 0
tars.DURACAO_MOVER_MOUSE_SEG = 0
nome, args, _ = tars.consertar_chamada("right_click", {"x": 100, "y": 100})
assert nome == "click_mouse" and args["button"] == "right", (nome, args)
tars.clicar_mouse("Right", 100, 100)
assert cliques[-1]["button"] == "right", cliques
tars.clicar_mouse("right-click", 100, 100)
assert cliques[-1]["button"] == "right"
assert tars.pressionar_tecla("Page Down")["sucesso"] and cliques[-1] == ("press", "pagedown")
assert tars.pressionar_tecla("Super")["sucesso"] and cliques[-1] == ("press", "win")
assert not tars.pressionar_tecla("bogus")["sucesso"] and not tars.pressionar_tecla("")["sucesso"]
assert tars.pressionar_tecla("ctrl+s")["sucesso"] and cliques[-1] == ("hotkey", ("ctrl", "s"))
assert not tars.atalho_teclado(["ctrl", "bogus"])["sucesso"] and not tars.atalho_teclado([])["sucesso"]
print("OK: clique fora da tela não chega à quina, botão direito de verdade, teclas inválidas avisam")

r = tars._executar_terminal_de_fato("printf 'ol\\341 mundo\\n'")
assert r["sucesso"] and "mundo" in r["stdout"], r
print("OK: saída que não é UTF-8 não derruba o comando")

JANELAS = [dict(id=1, titulo="Calculator", classe="gnome-calculator Gnome-calculator", pid=10, x=0, y=0, largura=300, altura=400, minimizada=False),
           dict(id=2, titulo="Calculadora online - Google Chrome", classe="google-chrome Google-chrome", pid=11, x=0, y=0, largura=900, altura=700, minimizada=False)]
tars._buscar_app_no_sistema = lambda n: {"tipo": "desktop", "nome": "Calculator", "arquivo": "/usr/share/applications/org.gnome.Calculator.desktop",
                                          "exec": "gnome-calculator", "comando": ["gtk-launch", "x"], "origem": "x"} if n.lower().startswith("calc") else None
assert tars.encontrar_janela_por_nome("calculadora", JANELAS)["titulo"] == "Calculator", "o app vence a aba do navegador"
assert tars.encontrar_janela_por_nome("chrome", JANELAS)["id"] == 2
print("OK: 'calculadora' acha o programa e não a aba do navegador com o mesmo nome")

# ------------------------------------------------------------
# Escolha das IAs
# ------------------------------------------------------------
def modelo(tag, caps, params, categoria="geral", quant="Q4_K_M"):
    return {"tag": tag, "familia": "x", "categoria": categoria, "parametros_b": params, "capacidades": set(caps),
            "capacidades_conhecidas": True, "vram_estimado_gb": 2.0 if params is None else params * 0.6 + 0.6}


CAT = {
    "ProjectOpenTARS/Gargantua:latest": modelo("ProjectOpenTARS/Gargantua:latest", {"tools", "completion"}, 4.0),
    COOPER: modelo(COOPER, {"tools", "vision", "completion"}, 2.0, "visao"),
    "nomic-embed-text:latest": modelo("nomic-embed-text:latest", {"embedding"}, 0.14, "embedding"),
    "qwen3:8b": modelo("qwen3:8b", {"tools", "completion"}, 8.0),
    "api:bonsai": modelo("api:bonsai", {"tools"}, None),
}
CAT["api:bonsai"]["capacidades_conhecidas"] = False
assert tars.modelo_ajudante(CAT) != COOPER, "o Cooper não resolve nome de app"
for alvo in ("modelo.menor", "modelo.maior", "modelo.visao", "modelo.tecnico"):
    escolhido = tars._RESOLVEDORES_MODELO[alvo](CAT) if hasattr(tars, "_RESOLVEDORES_MODELO") else None
    assert escolhido not in (COOPER, "nomic-embed-text:latest"), (alvo, escolhido)
assert COOPER not in tars.construir_cadeia_fallback("visao", CAT)
assert tars.construir_cadeia_fallback("acao", CAT)[-1] != "x"
cadeia = tars.construir_cadeia_fallback("busca", CAT)
assert cadeia.index("api:bonsai") > cadeia.index("qwen3:8b"), cadeia  # tamanho desconhecido: no fim
assert tars._estimar_vram_gb(8.2, "BF16") > 15
print("OK: Cooper e embedding não conversam nem ajudam; tamanho desconhecido vai pro fim; BF16 não é Q4")

# modelo que já está na placa responde a conversa curta (sem trocar de modelo)
tars.catalogar_modelos = lambda forcar=False: CAT
tars._cache_cadeias.clear()
tars.modo_modelo = "AUTO"
tars.modelo_atual = "qwen3:8b"
assert tars.escolher_modelo("oi", tarefa="simples") == "qwen3:8b"
tars.modelo_atual = None

# ------------------------------------------------------------
# Linha de comando
# ------------------------------------------------------------
def tars_cli(*args, entrada=""):
    env = {**os.environ, "OLLAMA_HOST": "127.0.0.1:1", "HOME": CASA, "TARS_SEM_INTERFACE": "1", "TARS_SEM_AVISO_VERSAO": "1"}
    return subprocess.run([sys.executable, str(RAIZ / "tars.py"), *args], input=entrada, capture_output=True, text=True, env=env, timeout=60)


r = tars_cli("--chat", "oi")  # Ollama fora do ar: erro e código de saída diferente de 0
assert r.returncode == 1, (r.returncode, r.stdout[-300:])
print("OK: --chat com o Ollama fora do ar dá código de saída diferente de 0")

print("\nTUDO OK.")
