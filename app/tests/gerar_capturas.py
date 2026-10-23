"""Gera as capturas de tela do README (docs/img/*.png) a partir da janela de verdade, sem tela (offscreen).

Uso:  python3 tests/gerar_capturas.py [pasta_de_saida]     (precisa de PySide6; padrão: docs/img)

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
os.environ.setdefault("QT_SCALE_FACTOR", "1.5")
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

SAIDA = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "docs" / "img"
SAIDA.mkdir(parents=True, exist_ok=True)

from _util import carregar_tars  # noqa: E402

from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QPushButton  # noqa: E402

MODELOS = [("ProjectOpenTARS/Gargantua:latest", 2_600_000_000, "4.0B"), ("qwen3:8b", 5_200_000_000, "8.2B")]


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

tars.memoria.lembrar("my browser is Firefox")
tars.memoria.lembrar("my code lives in ~/Projects")
tars.memoria.lembrar("I like short answers")

relogio = [dt.datetime.now().replace(microsecond=0)]
tars.agenda = agenda_lib.Agenda(os.path.join(CASA, "agenda.json"), agora=lambda: relogio[0])
tars.agenda.criar("Morning news", "open the newspaper website and read me the headlines",
                  {"tipo": "diaria", "hora": "08:00"}, permitidas=(), ativa=True, aprovada=True)
tars.agenda.criar("Weekly cleanup", "move the files in Downloads older than 30 days to the trash",
                  {"tipo": "semanal", "hora": "18:30", "dias": [4]}, permitidas=("apagar",), ativa=True, aprovada=True)
tars.agenda.criar("Check free disk space", "tell me if the disk has less than 10 GB free",
                  {"tipo": "intervalo", "cada_minutos": 360}, permitidas=(), ativa=False, aprovada=False, origem="ia")


# --- o pedido encenado ---------------------------------------------------------------------------------------------------
def pedido_encenado(texto, anexos=None):
    e = tars.emitir
    tars.conversa.append({"role": "user", "content": texto})
    e("tarefa", modo="AUTO", tarefa="acao", modelo="ProjectOpenTARS/Gargantua:latest")
    e("plano", etapas=["Create the script file", "Run it to check the output"])
    time.sleep(0.15)
    e("ferramenta", nome="execute_terminal", resumo="cat > ~/hello.py")
    time.sleep(0.2)
    e("ferramenta_fim", nome="execute_terminal", sucesso=True, segundos=0.2)
    e("ferramenta", nome="execute_terminal", resumo="python3 ~/hello.py")
    time.sleep(0.2)
    e("ferramenta_fim", nome="execute_terminal", sucesso=True, segundos=0.1)
    resposta = ("Done. I created `~/hello.py`:\n\n```python\nprint(\"Hello, world!\")\n```\n\n"
                "I ran it and it printed **Hello, world!** Run it again any time with `python3 ~/hello.py`.")
    e("resposta", texto=resposta, inicio=True, apos_pensamento=False)
    e("fim_stream")
    tars.conversa.append({"role": "assistant", "content": resposta})
    return resposta


tars.processar_mensagem = pedido_encenado

j = JanelaPrincipal(tars, historico=historico, capturar_stdout=False)
j.resize(1180, 760)
j.show()
esperar(lambda: j._modelos)
foto(j, "01-home")

j.compositor.entrada.setPlainText("Write a simple hello world python script")
j.enviar()
esperar(lambda: not j.ponte.esta_ocupado and j.ponte.id_conversa)
esperar(lambda: j.lateral._itens)
foto(j, "02-conversation", 900)

# aprovação antes de uma ação arriscada
j._ia = None
resultado = {}
threading.Thread(target=lambda: resultado.setdefault("r", tars.confirmar_comando_hook("sudo apt install htop")), daemon=True).start()
esperar(lambda: j.area.findChildren(CartaoAprovacao))
foto(j, "03-approval")
for b in j.area.findChildren(CartaoAprovacao)[-1].findChildren(QPushButton):
    if b.text() == "Allow":
        b.click()
esperar(lambda: "r" in resultado)

# aviso de versão nova na barra lateral
j._nova_versao = {"versao": "5.1", "arquivos": {}}
j.lateral.mostrar_versao("5.1")
foto(j, "04-update-available", 300)

# configurações (5.1: no modo Pro, que mostra todas as páginas)
import tars_modos  # noqa: E402
import tars_probes  # noqa: E402
tars_modos.definir_modo("pro")
j.aplicar_modo()
j.config.aplicar_modo()
j.voz.pronta = lambda: False
for nome, arquivo in (("geral", "05-settings-general"), ("voz", "06-settings-voice"), ("memoria", "07-settings-memory"),
                      ("rotinas", "08-settings-routines"), ("nuvem", "09-settings-cloud"), ("atualizacoes", "10-settings-updates"),
                      ("sobre", "11-settings-about"), ("avancado", "19-settings-advanced")):
    j.abrir_config(nome)
    esperar(lambda: True)
    foto(j, arquivo, 700 if nome == "geral" else 400)

# 5.1: Probes, com dois Probes que já avisaram e o passo a passo aberto em "Uma pasta"
downloads = Path(CASA) / "Downloads"
downloads.mkdir(exist_ok=True)
tars_probes.ligar_servico = lambda ligado, iniciar=True: ligado
tars_probes.servico_ligado = lambda: True
tars_probes.servico_rodando = lambda: 1
probes = tars_probes.Probes()
for tipo, campos, aviso in (("sistema", {"condicao": "bateria", "limite": 20}, "Battery at 18% and not charging."),
                            ("feed", {"url": "https://github.com/ollama/ollama"}, "1 new item(s): v0.40.1")):
    missao, bruto, regra = tars_probes.plano_do_passo_a_passo(tipo, campos, tars.t)
    p, _ = probes.criar(missao, bruto, regra=regra)
    probes.ligar(p["id"], True)
    probes.registrar(p["id"], {"alertar": True, "mensagem": aviso, "itens": [], "estado": {}})
j.abrir_config("probes")
pg = j.config.paginas["probes"]
pg.blocos["pasta"].click()
pg.f["pasta"].setText("~/Downloads")
pg.f["filtro"].setText(".deb")
pg.ao_abrir()
esperar(lambda: True)
pg.verticalScrollBar().setValue(230)
foto(j, "18-probes", 700)
j.pilha.setCurrentIndex(0)
j.cabecalho.sino.olhar()
j.cabecalho.sino.click()
esperar(lambda: True)
foto(j.cabecalho.sino.painel, "21-probe-alerts", 400)
j.cabecalho.sino.painel.hide()

# tela de voz
j.pilha.setCurrentIndex(1)
j.tela_voz.ao_estado("ouvindo")
foto(j, "12-voice", 600)
j._sair_da_voz()

# barra rápida
j.barra.mostrar()
j.barra._texto = "**What is my local IP address?**\n\nYour local IP address is **192.168.1.20** (interface `wlp2s0`)."
j.barra.resposta.show()
j.barra._desenhar()
j.barra.status.setText("Enter sends  ·  Esc closes  ·  Ctrl+Enter opens the window")
foto(j.barra, "13-quick-bar", 700)
j.barra.esconder()

# primeira execução (assistente)
try:
    from tars_qt.primeiro_uso import JanelaPrimeiroUso
    w = JanelaPrimeiroUso()
    w.resize(900, 640)
    w.show()
    for nome, arquivo in (("idioma", "14-first-run-language"), ("modo", "20-first-run-mode"), ("gargantua", "15-first-run-model"),
                          ("pronto", "16-first-run-done")):
        try:
            w.ir(nome)
            foto(w, arquivo, 500)
        except Exception as erro:       # a página depende de rede/instalação: sem ela, segue sem a imagem
            print("sem captura de", nome, "-", erro)
    w.close()
except Exception as erro:
    print("sem assistente:", erro)

j.close()
print("\nTUDO OK.")
os._exit(0)
