"""Gera, com a janela de VERDADE do openTARS (sem tela, Ollama de mentira), as sequências de quadros do filme "Um dia com o openTARS".

Uso:  python3 tests/gerar_frames_filme.py PASTA_DE_SAIDA     (precisa de PySide6; escreve PASTA/<cena>/NNNN.jpg e PASTA/index.json)

Nada aqui conversa com um Ollama de verdade: o pedido é encenado (os mesmos eventos que o núcleo emite) para que as
imagens mostrem sempre o mesmo texto, em inglês, e não dependam de modelo, GPU ou rede.
"""

import datetime as dt
import json
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_SCALE_FACTOR", "2")
CASA = tempfile.mkdtemp(prefix="opentars-capturas-")
os.environ["HOME"] = CASA
os.environ["TARS_IDIOMA"] = "en"
os.environ["TARS_ARQUIVO_SESSOES"] = os.path.join(CASA, "sessoes.json")
os.environ["TARS_ARQUIVO_NUVEM"] = os.path.join(CASA, "nuvem.json")
os.environ["TARS_ARQUIVO_PRIMEIRO_USO"] = os.path.join(CASA, "primeiro_uso.json")
os.environ["TARS_ARQUIVO_AGENDA"] = os.path.join(CASA, "agenda.json")
os.environ["TARS_DIR_LOG"] = os.path.join(CASA, "log")
os.environ["XDG_CONFIG_HOME"] = os.path.join(CASA, "config")
os.environ["TARS_SEM_AVISO_VERSAO"] = "1"
os.environ["TARS_ARQUIVO_PROBES"] = os.path.join(CASA, "probes.json")

SAIDA = Path(sys.argv[1])
SAIDA.mkdir(parents=True, exist_ok=True)

from _util import carregar_tars  # noqa: E402

from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QPushButton  # noqa: E402

MODELOS = [("ProjectOpenTARS/Gargantua-2:latest", 1_600_000_000, "2.0B"), ("ProjectOpenTARS/Gargantua-2:lite", 617_000_000, "0.8B")]


class Falso(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, dados, codigo=200):
        corpo = json.dumps(dados).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        if self.path == "/api/version":
            return self._json({"version": "0.12.9"})
        if self.path == "/api/tags":
            return self._json({"models": [{"name": n, "model": n, "size": s, "details": {
                "family": "qwen3", "parameter_size": p, "quantization_level": "Q4_K_M"}} for n, s, p in MODELOS]})
        return self._json({"models": []} if self.path == "/api/ps" else {}, 200 if self.path == "/api/ps" else 404)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/api/show":
            return self._json({"capabilities": ["completion", "tools"], "details": {"family": "qwen3"}, "model_info": {}})
        return self._json({"done": True, "response": ""})


servidor = ThreadingHTTPServer(("127.0.0.1", 0), Falso)
threading.Thread(target=servidor.serve_forever, daemon=True).start()
os.environ["OLLAMA_HOST"] = f"127.0.0.1:{servidor.server_address[1]}"

tars = carregar_tars()
tars.avisos_de_ambiente = lambda: []
tars.detectar_gpu = lambda forcar=False: None
tars.aquecer_ajudante = lambda: None
tars.modelo_manual = None

import tars_historico  # noqa: E402
import tars_rotinas as agenda_lib  # noqa: E402
from tars_qt.primeiro_uso import criar_aplicativo  # noqa: E402
from tars_qt.principal import JanelaPrincipal  # noqa: E402
from tars_qt.conversa import CartaoAprovacao  # noqa: E402

app = criar_aplicativo(["opentars"])


def esperar(cond, segundos=15):
    fim = time.time() + segundos
    while time.time() < fim:
        app.processEvents()
        if cond():
            return True
        QTest.qWait(20)
    return False


def foto(widget, nome, espera=500):
    QTest.qWait(espera)
    app.processEvents()
    caminho = SAIDA / f"{nome}.png"
    widget.grab().save(str(caminho))
    print("captura:", caminho.name)


# --- dados de exemplo: conversas antigas, memória, rotinas -----------------------------------------------------------
agora = [time.time()]
historico = tars_historico.Historico(os.path.join(CASA, "historico.json"), agora=lambda: agora[0])
DIA = 86400
for atras, titulo in ((6 * DIA, "Rename the photos in Pictures"), (3 * DIA, "What is using port 8080?"),
                      (1 * DIA, "Summarize the PDF I just downloaded"), (1 * DIA + 3600, "Open the project folder in the editor"),
                      (3600, "Organize my Downloads by file type")):
    agora[0] = time.time() - atras
    historico.salvar(historico.nova_id(), [{"role": "user", "content": titulo}, {"role": "assistant", "content": "Done."}])
agora[0] = time.time()

tars.memoria.lembrar("my notes are in ~/Documents/Notes")
tars.memoria.lembrar("my code lives in ~/Projects")
tars.memoria.lembrar("I like short answers")

relogio = [dt.datetime.now().replace(microsecond=0)]
tars.agenda = agenda_lib.Agenda(os.path.join(CASA, "agenda.json"), agora=lambda: relogio[0])
tars.agenda.criar("Morning news", "open the newspaper website and read me the headlines",
                  {"tipo": "diaria", "hora": "08:00"}, permitidas=(), ativa=True, aprovada=True)
tars.agenda.criar("Weekly cleanup", "move the files in Downloads older than 30 days to the trash",
                  {"tipo": "semanal", "hora": "18:30", "dias": [4]}, permitidas=("apagar",), ativa=True, aprovada=True)




# ============================================================================================================================
# Cenas do filme: o MESMO app, dirigido da thread principal. Cada cena é uma lista de quadros (tempo local, imagem) e os alvos
# (botões) para o cursor do filme saber onde clicar. O texto digitado e os passos são encenados com os eventos reais do núcleo.
# ============================================================================================================================
import queue  # noqa: E402

from PySide6.QtCore import QPoint  # noqa: E402

PASTA = SAIDA
PASTA.mkdir(parents=True, exist_ok=True)
INDICE = {}


class Cena:
    def __init__(self, nome, widget):
        self.nome, self.w, self.n = nome, widget, 0
        self.frames, self.alvos = [], {}
        (PASTA / nome).mkdir(exist_ok=True)

    def foto(self, t, espera=70):
        QTest.qWait(espera)
        app.processEvents()
        arq = f"{self.n:04d}.jpg"
        self.w.grab().save(str(PASTA / self.nome / arq), "JPG", 90)
        self.frames.append([round(t, 3), arq])
        self.n += 1
        self.tam = [self.w.width(), self.w.height()]

    def alvo(self, nome, widget):
        p = widget.mapTo(self.w, QPoint(0, 0))
        self.alvos[nome] = [p.x(), p.y(), widget.width(), widget.height()]

    def fim(self):
        INDICE[self.nome] = {"tam": self.tam, "frames": self.frames, "alvos": self.alvos}
        (PASTA / "index.json").write_text(json.dumps(INDICE, indent=1), encoding="utf-8")
        print("cena", self.nome, len(self.frames), "quadros")


def digitar(cena, caixa, texto, t0, cps=26, passo=2, fim_extra=0.0):
    """Digita no campo real, um quadro a cada `passo` letras. Devolve o tempo em que terminou."""
    t = t0
    for k in range(0, len(texto) + 1, passo):
        caixa.setPlainText(texto[:k])
        caixa.moveCursor(QTextCursor.MoveOperation.End)
        cena.foto(t0 + k / cps, espera=25)
        t = t0 + k / cps
    if len(texto) % passo:
        caixa.setPlainText(texto)
        t = t0 + len(texto) / cps
        cena.foto(t, espera=25)
    return t + fim_extra


from PySide6.QtGui import QTextCursor  # noqa: E402

_liberar = threading.Event()


def _processar_travado(texto, anexos=None):
    """O pedido 'está rodando' (a janela mostra Parar) até a cena liberar; quem emite os eventos é a cena, na thread principal."""
    _liberar.wait(120)
    return None


tars.processar_mensagem = _processar_travado


def iniciar_pedido(cena, texto, t, cps=26):
    """Digita o pedido e envia (Enter): devolve o tempo depois do envio."""
    _liberar.clear()
    fim = digitar(cena, j.compositor.entrada, texto, t, cps)
    cena.foto(fim + 0.35)
    tars.conversa.append({"role": "user", "content": texto})
    j.enviar(texto)
    esperar(lambda: j.ponte.esta_ocupado)
    cena.foto(fim + 0.55)
    return fim + 0.55


def emitir(evento, **kw):
    tars.emitir(evento, **kw)
    app.processEvents()


def terminar_pedido(texto_resposta):
    tars.conversa.append({"role": "assistant", "content": texto_resposta})
    emitir("fim_stream")
    _liberar.set()
    esperar(lambda: not j.ponte.esta_ocupado)
    QTest.qWait(1600)          # o app termina as animações (KIPP volta ao normal, o campo volta a aceitar texto)
    try:
        j.mascote.balao.hide()    # o balão do KIPP some sozinho depois de uns segundos; aqui já passaram
    except AttributeError:
        pass
    app.processEvents()


def aprovar(cena, comando, t, clicar="Allow", t_clique=None):
    """Mostra o cartão de aprovação REAL para `comando`, fotografa e clica no botão pedido."""
    r = {}
    threading.Thread(target=lambda: r.setdefault("r", tars.confirmar_comando_hook(comando)), daemon=True).start()
    esperar(lambda: j.area.findChildren(CartaoAprovacao))
    cartao = j.area.findChildren(CartaoAprovacao)[-1]
    for k, dt_ in enumerate((0.0, 0.35, 0.7, 1.4)):
        cena.foto(t + dt_)
    botoes = {b.text(): b for b in cartao.findChildren(QPushButton)}
    cena.alvo(clicar.lower(), botoes[clicar])
    return r, botoes[clicar], t + 1.4


# --- 0. início: a tela de abertura de verdade --------------------------------------------------------------------------
j = JanelaPrincipal(tars, historico=historico, capturar_stdout=False)
j.resize(1180, 760)
j.show()
esperar(lambda: j._modelos)
c = Cena("inicio", j)
for k in range(8):
    c.foto(k * 0.45, espera=450 if k else 600)
c.fim()

# --- 1. tarefa: organizar o Downloads por tipo (exemplo do mockup "fazer uma tarefa") -----------------------------------------
j.nova_conversa()
c = Cena("tarefa", j)
c.foto(0.0)
t = iniciar_pedido(c, "Organize my Downloads folder by type", 0.6, cps=30)
emitir("tarefa", modo="AUTO", tarefa="acao", modelo="ProjectOpenTARS/Gargantua-2:latest")
emitir("plano", etapas=["Look at the Downloads folder (48 files)", "Plan: Images, Documents, Installers, Other", "Move the files", "Check that nothing was left behind"])
c.foto(t + 0.5)
emitir("ferramenta", nome="execute_terminal", resumo="ls ~/Downloads")
c.foto(t + 1.0)
emitir("ferramenta_fim", nome="execute_terminal", sucesso=True, segundos=0.1)
emitir("ferramenta", nome="execute_terminal", resumo="mkdir Images Documents Installers Other && mv …")
c.foto(t + 1.6)
r, botao, t = aprovar(c, "mkdir -p ~/Downloads/{Images,Documents,Installers,Other} && mv ~/Downloads/*.jpg ~/Downloads/Images/", t + 2.0)
c.foto(t + 0.5)
botao.click()
esperar(lambda: "r" in r)
c.foto(t + 1.2)
emitir("ferramenta_fim", nome="execute_terminal", sucesso=True, segundos=1.8)
emitir("ferramenta", nome="execute_terminal", resumo="ls ~/Downloads | wc -l")
emitir("ferramenta_fim", nome="execute_terminal", sucesso=True, segundos=0.1)
c.foto(t + 1.9)
resp = ("Done. I moved **48 files** into 4 new folders inside Downloads: **Images** (21), **Documents** (17), **Installers** (6) and **Other** (4). "
        "Nothing was deleted, and you can undo it from the history.")
emitir("resposta", texto=resp, inicio=True, apos_pensamento=False)
c.foto(t + 2.6)
terminar_pedido(resp)
c.foto(t + 3.4)
c.foto(t + 4.4)
c.fim()

# --- 2. busca com fonte ------------------------------------------------------------------------------------------------------
j.nova_conversa()
c = Cena("buscar", j)
c.foto(0.0)
t = iniciar_pedido(c, "How do I install Python?", 0.6, cps=30)
emitir("tarefa", modo="AUTO", tarefa="busca", modelo="ProjectOpenTARS/Gargantua-2:latest")
emitir("ferramenta", nome="search_web", resumo="how to install Python")
c.foto(t + 0.6)
emitir("ferramenta_fim", nome="search_web", sucesso=True, segundos=0.9)
c.foto(t + 1.4)
resp = ("On Ubuntu, Python 3 usually comes installed. Check it with:\n\n```bash\npython3 --version\n```\n\nIf it is missing, install it with `sudo apt install python3`. "
        "**Sources:** docs.python.org (Python Setup and Usage) and python.org. Check the current version on the official site: I may be quoting an old one.")
emitir("resposta", texto=resp, inicio=True, apos_pensamento=False)
c.foto(t + 2.2)
terminar_pedido(resp)
c.foto(t + 3.0)
c.foto(t + 4.0)
c.fim()

# --- 3. perguntar sobre a tela ---------------------------------------------------------------------------------------------
j.nova_conversa()
c = Cena("ver", j)
c.foto(0.0)
t = iniciar_pedido(c, "Where do I click to export this spreadsheet as PDF?", 0.6, cps=30)
emitir("tarefa", modo="AUTO", tarefa="visao", modelo="ProjectOpenTARS/Gargantua-2:latest")
emitir("ferramenta", nome="take_screenshot", resumo="the whole screen (kept only in memory)")
c.foto(t + 0.7)
emitir("ferramenta_fim", nome="take_screenshot", sucesso=True, segundos=0.8)
c.foto(t + 1.5)
resp = ("Open the **File** menu (I marked it in the menu bar) and choose **Export as…**, then **PDF**. "
        "Describing screens is where I make the most mistakes. Check before you click.")
emitir("resposta", texto=resp, inicio=True, apos_pensamento=False)
c.foto(t + 2.3)
terminar_pedido(resp)
c.foto(t + 3.1)
c.foto(t + 4.0)
c.fim()

# --- 4. lembrete e rotina (exemplo do mockup "criar um lembrete") ----------------------------------------------------------
j.nova_conversa()
c = Cena("lembrar", j)
c.foto(0.0)
t = iniciar_pedido(c, "Every Friday at 5 pm remind me to send the report", 0.6, cps=30)
emitir("tarefa", modo="AUTO", tarefa="simples", modelo="ProjectOpenTARS/Gargantua-2:latest")
emitir("ferramenta", nome="schedule_reminder", resumo="Every Friday at 17:00: send the report")
c.foto(t + 0.6)
tars.agenda.criar("Send the report", "remind me to send the report",
                  {"tipo": "semanal", "hora": "17:00", "dias": [4]}, permitidas=(), ativa=True, aprovada=True)
emitir("ferramenta_fim", nome="schedule_reminder", sucesso=True, segundos=0.1)
resp = ("Got it. Every **Friday at 17:00** I will remind you: *Send the report*. The first one is Friday, October 23. "
        "Reminders live in Settings > Routines, and they never delete, send or install anything without your approval.")
emitir("resposta", texto=resp, inicio=True, apos_pensamento=False)
c.foto(t + 1.4)
terminar_pedido(resp)
c.foto(t + 2.2)
import tars_modos  # noqa: E402
import tars_probes  # noqa: E402
tars_modos.definir_modo("pro")
j.aplicar_modo()
j.config.aplicar_modo()
j.voz.pronta = lambda: False
j.abrir_config("rotinas")
esperar(lambda: True)
c.foto(t + 3.4, espera=600)
pr = j.config.paginas["rotinas"]
pr.verticalScrollBar().setValue(pr.verticalScrollBar().maximum())
c.foto(t + 4.6, espera=500)
c.fim()
j.pilha.setCurrentIndex(0)

# --- 5. comando perigoso parado ---------------------------------------------------------------------------------------------
j.nova_conversa()
c = Cena("seguro", j)
c.foto(0.0)
t = iniciar_pedido(c, "Delete everything in my Documents folder", 0.6, cps=30)
emitir("tarefa", modo="AUTO", tarefa="acao", modelo="ProjectOpenTARS/Gargantua-2:latest")
emitir("ferramenta", nome="execute_terminal", resumo="rm -rf ~/Documents/*")
c.foto(t + 0.5)
r, botao, t = aprovar(c, "rm -rf ~/Documents/*", t + 1.0, clicar="Deny")
c.foto(t + 0.6)
botao.click()
esperar(lambda: "r" in r)
emitir("ferramenta_fim", nome="execute_terminal", sucesso=False, segundos=0.0)
c.foto(t + 1.3)
resp = "Okay, I did **not** run it. Nothing was deleted."
emitir("resposta", texto=resp, inicio=True, apos_pensamento=False)
c.foto(t + 2.0)
terminar_pedido(resp)
c.foto(t + 2.8)
c.foto(t + 3.6)
c.fim()

# --- 6. Probes: a página e o aviso do sino -----------------------------------------------------------------------------------
downloads = Path(CASA) / "Downloads"
downloads.mkdir(exist_ok=True)
tars_probes.ligar_servico = lambda ligado, iniciar=True: ligado
tars_probes.servico_ligado = lambda: True
tars_probes.servico_rodando = lambda: 1
probes = tars_probes.Probes()
for tipo, campos, aviso in (("pasta", {"pasta": "~/Downloads", "filtro": ".pdf"}, "1 new file in Downloads: invoice-0412.pdf"),
                            ("sistema", {"condicao": "bateria", "limite": 20}, "Battery at 18% and not charging.")):
    missao, bruto, regra = tars_probes.plano_do_passo_a_passo(tipo, campos, tars.t)
    p, _ = probes.criar(missao, bruto, regra=regra)
    probes.ligar(p["id"], True)
    probes.registrar(p["id"], {"alertar": True, "mensagem": aviso, "itens": [], "estado": {}})
j.abrir_config("probes")
pg = j.config.paginas["probes"]
pg.ao_abrir()
esperar(lambda: True)
c = Cena("probes", j)
c.foto(0.0, espera=600)
pg.verticalScrollBar().setValue(230)
c.foto(2.0, espera=400)
j.pilha.setCurrentIndex(0)
c.fim()
j.nova_conversa()
c = Cena("probes-chat", j)
c.foto(0.0, espera=500)
c.fim()
j.cabecalho.sino.olhar()
j.cabecalho.sino.click()
esperar(lambda: True)
c = Cena("probes-aviso", j.cabecalho.sino.painel)
c.foto(0.0, espera=500)
c.fim()
j.cabecalho.sino.painel.hide()

# --- 7. local por padrão: a página da nuvem (desligada) e a de modelos instalados ------------------------------------------
j.abrir_config("nuvem")
esperar(lambda: True)
c = Cena("local", j)
c.foto(0.0, espera=600)
c.foto(2.0)
c.fim()
j.abrir_config("gerenciar")
esperar(lambda: True)
c = Cena("modelos", j)
c.foto(0.0, espera=900)
pgm = j.config.paginas.get("gerenciar")
if pgm is not None:
    for pct, t_ in ((20, 2.0), (45, 3.2), (72, 4.4), (100, 5.6)):
        try:
            cartoes = getattr(pgm, "cartoes", {})
            for cartao in cartoes.values():
                cartao.progresso(pct, f"Updating… {pct}%")
                break
        except Exception as erro:
            print("sem barra:", erro)
        c.foto(t_, espera=200)
c.fim()

# --- 8. voz ---------------------------------------------------------------------------------------------------------------------
j.pilha.setCurrentIndex(1)
c = Cena("voz", j)
j.tela_voz.ao_estado("ouvindo")
c.foto(0.0, espera=500)
fala = "Every Friday at five remind me to send the report"
for k in range(0, len(fala) + 1, 3):
    j.tela_voz.definir_fala(fala[:k])
    c.foto(1.0 + k / 11.0, espera=60)
j.tela_voz.ao_estado("pensando")
c.foto(4.8, espera=300)
c.fim()
j._sair_da_voz()

# --- 9. barra rápida --------------------------------------------------------------------------------------------------------------
j.barra.mostrar()
c = Cena("barra", j.barra)
c.foto(0.0, espera=400)
digitar(c, j.barra.entrada, "What is my local IP address?", 0.6, 28, 3)
j.barra.entrada.setPlainText("")
j.barra._texto = "**What is my local IP address?**\n\nYour local IP address is **192.168.1.20** (interface `wlp2s0`)."
j.barra.resposta.show()
j.barra._desenhar()
j.barra.status.setText("Enter sends  ·  Esc closes  ·  Ctrl+Enter opens the window")
c.foto(2.4, espera=700)
c.foto(3.4)
c.fim()
j.barra.esconder()

j.close()
print("\nTUDO OK.")
os._exit(0)
