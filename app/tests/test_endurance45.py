"""4.6 Endurance: o Cooper (visão da tela), WSL e Linux sem interface gráfica.

Tudo numa pasta pessoal falsa; nenhum modelo de verdade (o Ollama é simulado)."""

import base64
import builtins
import io
import json
import os
import sys
import tempfile
from pathlib import Path

CASA = tempfile.mkdtemp(prefix="opentars-casa-")
os.environ["HOME"] = CASA
for var, sub in (("XDG_CONFIG_HOME", ".config"), ("XDG_DATA_HOME", ".local/share"), ("XDG_CACHE_HOME", ".cache")):
    os.environ[var] = os.path.join(CASA, sub)
os.environ["TARS_ARQUIVO_SESSOES"] = os.path.join(CASA, "sessoes.json")

from _util import carregar_tars  # noqa: E402

tars = carregar_tars()
amb, coo = tars.ambiente, tars.visao_lib
from PIL import Image  # noqa: E402

PASTA = Path(tempfile.mkdtemp(prefix="opentars-anexos-"))

# ------------------------------------------------------------
# 1. Versão
# ------------------------------------------------------------
assert tars.VERSAO == "5.1" and tars.CODINOME == "Tesseract" and tars.VERSAO_EXIBIDA == "5.1 Tesseract"
assert tars.REVISAO >= 2026100401
print("OK: versão 5.1 Tesseract")

# ------------------------------------------------------------
# 2. Ambiente: WSL, sem interface, caminhos do Windows
# ------------------------------------------------------------
def ler_falso(conteudos):
    return lambda caminho: conteudos.get(str(caminho), "")


wsl2 = ler_falso({"/proc/sys/kernel/osrelease": "5.15.153.1-microsoft-standard-WSL2", "/proc/version": "Linux ... microsoft"})
wsl1 = ler_falso({"/proc/sys/kernel/osrelease": "4.4.0-19041-Microsoft", "/proc/version": "Linux ... Microsoft"})
puro = ler_falso({"/proc/sys/kernel/osrelease": "6.8.0-45-generic", "/proc/version": "Linux version 6.8.0 (buildd@ubuntu)"})
assert amb.versao_wsl({}, wsl2) == 2 and amb.versao_wsl({}, wsl1) == 1 and amb.versao_wsl({}, puro) is None
assert amb.versao_wsl({"WSL_DISTRO_NAME": "Ubuntu"}, puro) == 1  # a variável basta
assert amb.e_wsl({"WSL_INTEROP": "/run/WSL/1_interop"}, puro) and not amb.e_wsl({}, puro)

d = amb.detectar({"DISPLAY": ":0"}, puro)
assert d["tela"] and not d["sem_interface"] and d["wsl"] is None and d["rotulo"] == "desktop"
d = amb.detectar({}, puro)
assert d["sem_interface"] and not d["tela"] and "no graphical session" in d["rotulo"]
d = amb.detectar({"SSH_CONNECTION": "1 2 3 4"}, puro)
assert d["sem_interface"] and d["ssh"] and "SSH" in d["rotulo"]
d = amb.detectar({}, wsl2)
assert d["sem_interface"] and d["wsl"] == 2 and d["rotulo"].startswith("WSL2")
d = amb.detectar({"DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0"}, wsl2)
assert d["wslg"] and not d["sem_interface"] and d["rotulo"] == "WSL2 with WSLg", d
d = amb.detectar({"DISPLAY": ":0", "TARS_SEM_INTERFACE": "1"}, puro)  # forçado
assert d["sem_interface"] and amb.forcado_sem_interface({"TARS_SEM_INTERFACE": "1"})

assert amb.caminho_do_windows("C:\\Users\\ana\\Meus Docs\\a b.txt") == "/mnt/c/Users/ana/Meus Docs/a b.txt"
assert amb.caminho_do_windows("d:/dados") == "/mnt/d/dados" and amb.caminho_do_windows("D:\\") == "/mnt/d"
assert amb.caminho_do_windows("\\\\wsl$\\Ubuntu\\home\\ana\\x.txt") == "/home/ana/x.txt"
assert amb.caminho_do_windows("\\\\wsl.localhost\\Ubuntu\\tmp") == "/tmp"
assert amb.caminho_do_windows("/home/ana/x") == "/home/ana/x" and not amb.parece_caminho_windows("/home/ana/x")
assert amb.parece_caminho_windows("C:\\x")

route = ("Iface\tDestination\tGateway\tFlags\nrmnet0\t00000000\t0120A8C0\t0003\nrmnet0\t0020A8C0\t00000000\t0001\n")
assert amb.gateway_padrao(route) == "192.168.32.1", amb.gateway_padrao(route)
assert amb.servidor_dns("# x\nnameserver 192.168.32.1\nnameserver 8.8.8.8\n") == "192.168.32.1"
assert amb.servidor_dns("nameserver 127.0.0.53\n") == "127.0.0.53"
cands = amb.candidatos_ollama_wsl(ler=ler_falso({"/etc/resolv.conf": "nameserver 172.20.0.1\n", "/proc/net/route": route}))
assert cands == ["http://172.20.0.1:11434", "http://192.168.32.1:11434"], cands
assert amb.candidatos_ollama_wsl(ler=ler_falso({"/etc/resolv.conf": "nameserver 127.0.0.53\n"})) == []
assert amb.abridor_de_links_do_windows(existe=lambda p: p == "explorer.exe") == ["explorer.exe"]
assert amb.abridor_de_links_do_windows(existe=lambda p: True) == ["wslview"]
assert amb.abridor_de_links_do_windows(existe=lambda p: False) is None
print("OK: ambiente: WSL1/2, WSLg, sem interface, SSH, caminhos do Windows e IP do Ollama do Windows")

# ------------------------------------------------------------
# 3. Cooper: nome, perguntas, respostas, milésimos -> pixels
# ------------------------------------------------------------
assert coo.MODELO_COOPER == "ProjectOpenTARS/cooper:1.2"       # só para reconhecer um Cooper que já esteja instalado
assert coo.COMANDO_INSTALAR == "ollama pull ProjectOpenTARS/Gargantua-2", "18/10: quem olha a tela é o Gargantua 2"
assert coo.achar_instalado(["qwen3:4b", "ProjectOpenTARS/cooper:1.2", "ProjectOpenTARS/Gargantua-2:lite", "ProjectOpenTARS/Gargantua-2:latest"]) == "ProjectOpenTARS/Gargantua-2:latest"
assert coo.achar_instalado(["ProjectOpenTARS/cooper:1.2", "ProjectOpenTARS/Gargantua-2:lite"]) == "ProjectOpenTARS/Gargantua-2:lite", "o Lite novo (com telas) vence o Cooper antigo"
assert coo.achar_instalado(["ProjectOpenTARS/Gargantua-2:lite", "ProjectOpenTARS/Gargantua-2:latest"]) == "ProjectOpenTARS/Gargantua-2:latest", "o 2B vem antes do Lite"
assert coo.achar_instalado(["ProjectOpenTARS/Gargantua:2.0-lite"]) is None, "o Lite 2.0 antigo não foi treinado com telas"
assert coo.achar_instalado(["ProjectOpenTARS/cooper:1.2", "ProjectOpenTARS/Gargantua:2.0-lite"]) == "ProjectOpenTARS/cooper:1.2"
os.environ["TARS_VISAO_NO_LITE"] = "1"
assert coo.achar_instalado(["ProjectOpenTARS/Gargantua:2.0-lite"]) == "ProjectOpenTARS/Gargantua:2.0-lite", "liberado à mão"
os.environ.pop("TARS_VISAO_NO_LITE")
assert coo.achar_instalado(["ProjectOpenTARS/Gargantua:1.2-lite", "ProjectOpenTARS/Gargantua:latest"]) is None, "o Gargantua 1.x não enxerga"
for tag in ("ProjectOpenTARS/cooper:latest", "cooper", "cooper-1.0:latest", "projectopentars/Cooper"):
    assert coo.e_cooper(tag), tag
for tag in ("gargantua:latest", "qwen3-vl:2b", "ProjectOpenTARS/Gargantua", "", None):
    assert not coo.e_cooper(tag), tag
assert coo.achar_instalado(["qwen3:4b", "cooper-1.0:latest", "ProjectOpenTARS/cooper:latest"]) == "ProjectOpenTARS/cooper:latest"
assert coo.achar_instalado(["ProjectOpenTARS/cooper:latest", "ProjectOpenTARS/cooper:1.2"]) == "ProjectOpenTARS/cooper:1.2", "o 1.2 vence o antigo"
assert coo.achar_instalado(["cooper-1.0:latest"]) == "cooper-1.0:latest" and coo.achar_instalado(["qwen3:4b"]) is None
assert coo.ligado({}) and not coo.ligado({"TARS_COOPER": "0"}) and not coo.ligado({"TARS_COOPER": "off"})

assert coo.tipo_do_alvo("the Save button") == ("button", "Save")
assert coo.tipo_do_alvo("botão Salvar") == ("button", "Salvar")
assert coo.tipo_do_alvo("Dark mode checkbox") == ("checkbox", "Dark mode")
assert coo.tipo_do_alvo("Address bar field") == ("field", "Address bar")
assert coo.tipo_do_alvo("campo Nome") == ("field", "Nome")
assert coo.tipo_do_alvo("close icon") == ("icon", "close")
assert coo.tipo_do_alvo("Settings") == ("button", "Settings")  # sem pista: botão
assert coo.tipo_do_alvo("menu Arquivo") == ("menu", "Arquivo")
assert coo.pergunta_localizar("the Save button") == (
    'Where is the button "Save" on the screen? Answer with its center as JSON {"x": 0-1000, "y": 0-1000} '
    '(thousandths of the image width and height). If it is not on the screen, answer {"found": false}.')
assert ' in the window "Notes"' in coo.pergunta_localizar("Save", janela="Notes")
assert coo.pergunta_descrever("use the Minimize icon").startswith(
    'Describe this screenshot for an assistant that must operate the computer to do: "use the Minimize icon".')

assert coo.ler_ponto('{"x": 512, "y": 340}') == ("achou", 512, 340)
assert coo.ler_ponto('```json\n{"x": 0, "y": 1000}\n```') == ("achou", 0, 1000)
assert coo.ler_ponto('Here: {"x": 12.5, "y": 99}') == ("achou", 12.5, 99)
assert coo.ler_ponto('{"found": false}') == ("ausente", None, None)
assert coo.ler_ponto("it is at (512, 340)") == ("achou", 512, 340)
for ruim in ("", None, "não sei", '{"x": 1200, "y": 5}', '{"x": "a", "y": 2}', "(5000, 40)", '{"y": 5}'):
    assert coo.ler_ponto(ruim) is None, ruim
assert coo.para_pixels(500, 500, 1920, 1080) == (960, 540)
assert coo.para_pixels(1000, 1000, 1920, 1080) == (1919, 1079) and coo.para_pixels(0, 0, 800, 600) == (0, 0)
assert coo.para_pixels(333, 666, 1280, 720) == (426, 480)
desc = 'Window "Notes". Button "Save" at (500, 500). Field "Name" at (250, 100). Odd (2000, 5).'
assert coo.descricao_em_pixels(desc, 1000, 500) == 'Window "Notes". Button "Save" at (500, 250). Field "Name" at (250, 50). Odd (2000, 5).'
assert "(960, 540)" in coo.descricao_em_pixels('Save {"x": 500, "y": 500}', 1920, 1080)
print("OK: Cooper: perguntas no formato do treino, leitura das respostas e milésimos -> pixels")

# ------------------------------------------------------------
# 4. Cooper no núcleo: clique, descrição, e nunca como IA de conversa
# ------------------------------------------------------------
COOPER = "ProjectOpenTARS/cooper:latest"
CATALOGO = {
    "qwen3:4b": {"tag": "qwen3:4b", "familia": "qwen3", "categoria": "geral", "parametros_b": 4.0, "capacidades": {"tools"},
                 "capacidades_conhecidas": True, "vram_estimado_gb": 3.0},
    COOPER: {"tag": COOPER, "familia": "qwen3vl", "categoria": "visao", "parametros_b": 2.0, "capacidades": {"vision", "completion"},
             "capacidades_conhecidas": True, "vram_estimado_gb": 2.0},
    "gemma3:4b": {"tag": "gemma3:4b", "familia": "gemma3", "categoria": "visao", "parametros_b": 4.0,
                  "capacidades": {"vision", "completion"}, "capacidades_conhecidas": True, "vram_estimado_gb": 3.0},
}
tars.catalogar_modelos = lambda forcar=False: CATALOGO
assert tars.visao_instalada() == COOPER
assert COOPER in tars.MODELOS_AJUDANTES and "cooper" in tars.MODELOS_AJUDANTES and "qwen3:4b" not in tars.MODELOS_AJUDANTES
assert "qwen2.5:0.5b" in tars.MODELOS_AJUDANTES
assert COOPER not in tars.construir_cadeia_fallback("acao"), "o Cooper não conversa"
os.environ["TARS_COOPER"] = "0"
assert tars.visao_instalada() is None
del os.environ["TARS_COOPER"]

perguntas = []
respostas = {"valor": '{"x": 250, "y": 500}'}


def chat_falso(modelo, prompt, **kw):
    perguntas.append((modelo, prompt, kw))
    return respostas["valor"]


tars._chat_unico = chat_falso
img = Image.new("RGB", (1200, 800), "white")
ponto, tag = tars.localizar_com_visao("the Save button", img)
assert ponto == (300, 400) and tag == COOPER, (ponto, tag)
modelo, prompt, kw = perguntas[-1]
assert modelo == COOPER and prompt.startswith('Where is the button "Save"') and kw["temperatura"] == 0.0 and len(kw["imagens"]) == 1
assert Image.open(io.BytesIO(base64.b64decode(kw["imagens"][0]))).size == (1200, 800)

respostas["valor"] = '{"found": false}'
assert tars.localizar_com_visao("Save", img) == ("ausente", COOPER)
respostas["valor"] = "não entendi"
assert tars.localizar_com_visao("Save", img) == (None, None)
respostas["valor"] = None
assert tars.localizar_com_visao("Save", img) == (None, None)
respostas["valor"] = '{"x": 250, "y": 500}'
assert tars.mirar_com_visao("Save", img) == (300, 400, "located 'Save' by looking at the screen")
assert tars.mirar_com_visao("Save", img, perto_de=(310, 410)) is not None
assert tars.mirar_com_visao("Save", img, perto_de=(900, 700)) is None, "longe do x/y da IA: a grade confere"

# descrição da tela: posições do Cooper já em pixels da imagem enviada
buffer = io.BytesIO()
Image.new("RGB", (1000, 500), "white").save(buffer, format="PNG")
b64 = base64.b64encode(buffer.getvalue()).decode()
respostas["valor"] = 'Window "Notes". Button "Save" at (500, 500).'
texto, quem = tars._descrever_print(b64, "salvar", "qwen3:4b")
assert quem == COOPER and "(500, 250)" in texto and "1000x500" in texto, texto
assert perguntas[-1][1].startswith("Describe this screenshot for an assistant")
respostas["valor"] = "A calm window with some buttons."  # sem posição: ainda vale, avisando
texto, quem = tars._descrever_print(b64, "salvar", "qwen3:4b")
assert quem == COOPER and "without positions" in texto
respostas["valor"] = None  # Cooper sem resposta: nada de modelo de reserva
tars._visao_estado.update(pausado_ate=0.0, quente=False, erro="")
perguntas.clear()
assert tars._descrever_print(b64, "salvar", "qwen3:4b") == (None, None) and {p[0] for p in perguntas} == {COOPER}, "só o Cooper é consultado"
print("OK: Cooper acha e descreve; sem resposta, só o motivo (nenhum outro modelo de visão); nunca conversa")

# ------------------------------------------------------------
# 5. Sem interface gráfica
# ------------------------------------------------------------
tars.SEM_INTERFACE = True
tars.AMBIENTE.update(sem_interface=True, tela=False)
nomes = {f["function"]["name"] for f in tars.ferramentas_do_pedido("acao", "abra o firefox e clique em entrar")}
assert nomes and not (nomes & tars.FERRAMENTAS_SO_COM_TELA), nomes & tars.FERRAMENTAS_SO_COM_TELA
nomes_tec = {f["function"]["name"] for f in tars.ferramentas_do_pedido("tecnico", "quanta memória livre eu tenho")}
assert "execute_terminal" in nomes_tec and "take_screenshot" not in nomes_tec
for ferramenta in ("take_screenshot", "click_mouse", "open_application", "list_windows", "type_text", "hotkey"):
    r = tars.executar_ferramenta(ferramenta, {"app": "calculadora", "text": "x", "keys": ["ctrl", "c"]})
    assert not r["sucesso"] and "no graphical session" in r["mensagem"] and ferramenta in r["mensagem"], (ferramenta, r)
r = tars.executar_ferramenta("execute_terminal", {"command": "echo ola"})
assert r["sucesso"] and "ola" in json.dumps(r), r
r = tars.executar_ferramenta("list_files", {"path": str(PASTA)})
assert r["sucesso"], r
r = tars.abrir_site("https://example.com")
assert not r["sucesso"] and "https://example.com" in r["mensagem"] and "link" in r["mensagem"], r
r = tars.pesquisar_web("gatos")
assert not r["sucesso"] and "google.com/search?q=gatos" in r["mensagem"], r
# no WSL sem tela, o link abre no navegador do Windows
chamadas = []
tars.EM_WSL = True
tars.ambiente.abridor_de_links_do_windows = lambda existe=None: ["wslview"]
tars.subprocess.Popen = lambda cmd, **kw: chamadas.append(cmd)
r = tars.abrir_site("https://example.com")
assert r["sucesso"] and chamadas == [["wslview", "https://example.com"]], (r, chamadas)
tars.EM_WSL = False
avisos = tars.avisos_de_ambiente()
assert any("tery" not in a and ("Sem sessão gráfica" in a or "Sem sess" in a) for a in avisos), avisos
assert not any("mouse" in a.lower() for a in avisos), avisos
tars._contexto_sistema_cache.clear()
assert "NO graphical session" in tars.contexto_sistema()
tars._contexto_sistema_cache.clear()
tars.EM_WSL = True
assert "Running inside WSL" in tars.contexto_sistema()
tars.EM_WSL = False
tars._contexto_sistema_cache.clear()
# com tela, tudo volta
tars.SEM_INTERFACE = False
tars.AMBIENTE.update(sem_interface=False, tela=True)
nomes = {f["function"]["name"] for f in tars.ferramentas_do_pedido("busca", "pesquise gatos")}
assert "take_screenshot" in nomes or "click_element" in nomes, nomes
assert "NO graphical session" not in tars.contexto_sistema()
print("OK: sem interface: ferramentas de tela somem e, se chamadas, explicam; links vão pro navegador do Windows no WSL")

# ------------------------------------------------------------
# 8. Conversa no terminal
# ------------------------------------------------------------
pedidos = []
tars.processar_mensagem = lambda texto: pedidos.append(texto) or "ok"
tars.iniciar_conversa = lambda: 0
tars.encerrar_todas_ias = lambda *a, **k: None
tars.avisos_de_ambiente = lambda: ["aviso de teste"]
entradas = []
builtins_input = builtins.input
builtins.input = lambda prompt="": entradas.pop(0) if entradas else (_ for _ in ()).throw(EOFError())
saida = io.StringIO()
real_stdout = sys.stdout
try:
    sys.stdout = saida
    entradas[:] = ["/ajuda", "resuma isto", "/sair", "isto não deveria ser lido"]
    assert tars.modo_chat_terminal() == 0
finally:
    sys.stdout = real_stdout
    builtins.input = builtins_input
assert pedidos == ["resuma isto"], pedidos
assert "aviso de teste" in saida.getvalue()
assert entradas == ["isto não deveria ser lido"], "o /sair encerra o laço"
entradas[:] = ["pergunta pelo pipe"]
pedidos.clear()
builtins.input = lambda prompt="": entradas.pop(0) if entradas else (_ for _ in ()).throw(EOFError())
try:
    sys.stdout = io.StringIO()
    assert tars.modo_chat_terminal() == 0
finally:
    sys.stdout = real_stdout
    builtins.input = builtins_input
assert pedidos == ["pergunta pelo pipe"]
print("OK: opentars --chat: pedido, /ajuda, /sair e entrada por pipe")

# --cooper (descontinuado em 18/10: só avisa e diz como instalar o Gargantua 2; não baixa nada)
rodou = []
tars.subprocess.run = lambda cmd, **kw: rodou.append(cmd) or type("R", (), {"returncode": 0})()
saida = io.StringIO()
try:
    sys.stdout = saida
    assert tars.comando_cooper() == 0
finally:
    sys.stdout = real_stdout
assert not rodou and "ollama pull ProjectOpenTARS/Gargantua-2" in saida.getvalue() and "descontinuado" in saida.getvalue(), saida.getvalue()
print("OK: opentars --cooper avisa que o Cooper foi descontinuado e aponta o Gargantua 2")

# ------------------------------------------------------------
# 9. Textos nos dois idiomas
# ------------------------------------------------------------
base = Path(tars.__file__).parent / "idiomas"
en, pt = json.loads((base / "en.json").read_text()), json.loads((base / "pt_BR.json").read_text())
assert set(en) == set(pt), sorted(set(en) ^ set(pt))
for chave in ("chat.ajuda", "visao.nao_instalado", "cooper.descontinuado", "diag.wsl_sem_ollama",
              "term.onde_conversar_sem_interface", "aviso.modo_sem_interface"):
    assert en[chave] and pt[chave], chave
assert "--chat" in en["term.ajuda"] and "--cooper" not in pt["term.ajuda"]
print("OK: textos novos nos dois idiomas")

print("\nTUDO OK.")

# 4.5.1: Cooper exclusivo (nada de Bonsai/LM Studio de reserva)
os.environ.pop("TARS_COOPER", None)
tars.visao_instalada = lambda: COOPER
_envio = []
tars._chat_unico = lambda modelo, prompt, **kw: (_envio.append(modelo), "A window with a Save button")[1]
img2 = Image.new("RGB", (1200, 800), "white")
buf = io.BytesIO(); img2.save(buf, format="PNG")
import base64 as _b64
b64 = _b64.b64encode(buf.getvalue()).decode()
texto, tag = tars.descrever_com_visao(b64, "salvar")
assert tag == COOPER and "Save button" in texto and set(_envio) == {COOPER}, "descrição sem posições também vale (exclusivo)"
print("OK: Cooper exclusivo: nenhum outro modelo de visão é chamado")

# 4.5.1: Cooper lento/fora do ar não trava os passos seguintes
_chamadas = []


def _lento(modelo, prompt, **kw):
    _chamadas.append(kw["timeout"])
    tars._ultimo_erro["texto"] = "Read timed out"
    return None


tars._chat_unico = _lento
tars.visao_instalada = lambda: COOPER
tars._visao_estado.update(pausado_ate=0.0, quente=False, erro="")
assert tars.perguntar_visao(COOPER, "q", imagem_b64=b64) is None
assert _chamadas == [tars.TIMEOUT_VISAO_FRIO], "prazo estourado: sem segunda tentativa"
assert tars.visao_disponivel() is None, "depois de estourar o prazo o Cooper descansa"
assert tars.motivo_da_falha_da_visao() == "Read timed out"
assert tars.descrever_com_visao(b64, "x") == (None, None) and len(_chamadas) == 1, "em pausa: nem pergunta"
tars._visao_estado.update(pausado_ate=0.0)
_chamadas.clear()


def _erro_rapido(modelo, prompt, **kw):
    _chamadas.append(kw["timeout"])
    tars._ultimo_erro["texto"] = "HTTP 500 model failed to load"
    return None


tars._chat_unico = _erro_rapido
assert tars.perguntar_visao(COOPER, "q", imagem_b64=b64) is None and len(_chamadas) == 2, "erro rápido: tenta de novo uma vez"
assert tars.visao_disponivel() == COOPER, "erro rápido não põe em pausa"
tars._visao_estado.update(pausado_ate=0.0, quente=False, erro="")
print("OK: Cooper lento ganha pausa, erro rápido tenta duas vezes, e o motivo fica registrado")
