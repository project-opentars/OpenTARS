"""5.0: clicar nas sugestões da tela inicial e nas páginas de configurações não pode dar exceção em slot
(foi o que derrubou a janela: `textCursor().End` no clique de uma sugestão)."""

import json
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CASA = tempfile.mkdtemp(prefix="opentars-casa-")
os.environ["HOME"] = CASA
for nome in ("SESSOES", "NUVEM", "PRIMEIRO_USO", "AGENDA"):
    os.environ[f"TARS_ARQUIVO_{nome}"] = os.path.join(CASA, nome.lower() + ".json")
os.environ["TARS_DIR_LOG"] = os.path.join(CASA, "log")
os.environ["TARS_SEM_AVISO_VERSAO"] = "1"

from pathlib import Path  # noqa: E402

from _util import RAIZ as _RAIZ, carregar_tars  # noqa: E402

RAIZ = Path(_RAIZ)

try:
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QPushButton
except ImportError:
    print("test_qt_cliques: PULADO (PySide6 não instalado)")
    sys.exit(0)


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
            return self._json({"models": [{"name": "qwen3:4b", "model": "qwen3:4b", "size": 3_000_000_000, "details": {
                "family": "qwen3", "parameter_size": "4.0B", "quantization_level": "Q4_K_M"}}]})
        self._json({"models": []} if self.path == "/api/ps" else {}, 200 if self.path == "/api/ps" else 404)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self._json({"capabilities": ["completion", "tools"], "details": {"family": "qwen3"}, "model_info": {}}
                   if self.path == "/api/show" else {"done": True})


servidor = ThreadingHTTPServer(("127.0.0.1", 0), Falso)
threading.Thread(target=servidor.serve_forever, daemon=True).start()
os.environ["OLLAMA_HOST"] = f"127.0.0.1:{servidor.server_address[1]}"

tars = carregar_tars()
tars.avisos_de_ambiente = lambda: []
tars.detectar_gpu = lambda forcar=False: None
tars.aquecer_ajudante = lambda: None

from tars_qt.primeiro_uso import criar_aplicativo  # noqa: E402
from tars_qt.principal import JanelaPrincipal  # noqa: E402

erros = []
def _gancho(tipo, valor, tb):
    erros.append(f"{tipo.__name__}: {valor}")
    sys.__stderr__.write(f"EXCECAO: {tipo.__name__}: {valor}\n")


sys.excepthook = _gancho
app = criar_aplicativo(["opentars"])
j = JanelaPrincipal(tars, capturar_stdout=False)
j.resize(1100, 700)
j.show()
fim = time.time() + 5
while time.time() < fim:
    app.processEvents()
    QTest.qWait(20)

chips = [b for b in j.findChildren(QPushButton) if b.property("papel") == "chip" and b.isVisibleTo(j)]
assert len(chips) == 3, f"esperava as 3 sugestões da tela inicial, achei {len(chips)}"
for b in chips:
    j.compositor.limpar()
    b.click()
    app.processEvents()
    assert j.compositor.texto(), "a sugestão não foi pro campo de texto"
assert not erros, erros
print(f"OK: {len(chips)} sugestões clicadas, o texto vai pro campo e nenhum slot dá exceção")

for nome in ("geral", "voz", "memoria", "rotinas", "nuvem", "atualizacoes", "sobre"):
    j.abrir_config(nome)
    app.processEvents()
    QTest.qWait(150)
assert not erros, erros
print("OK: as 7 páginas de configurações abrem sem exceção")

# --- glifos: tudo que a janela mostra tem que existir na IBM Plex (senão o Qt chama o fontconfig do sistema, que dá
# segfault em algumas máquinas: foi o que derrubou a janela na primeira ferramenta, com o "▸" da linha da ferramenta) ---
from PySide6.QtGui import QFontDatabase, QRawFont  # noqa: E402
from PySide6.QtWidgets import QLabel  # noqa: E402

fontes = []
for arquivo in sorted((RAIZ / "tars_qt" / "fontes").glob("*.ttf")):
    fontes.append(QRawFont(str(arquivo), 15))
assert fontes, "fontes da IBM Plex não encontradas"


def faltam(texto):
    return sorted({c for c in texto if ord(c) > 0x7F and not any(f.supportsCharacter(ord(c)) for f in fontes)})


j._nova_conversa() if hasattr(j, "_nova_conversa") else None
for tipo, dados in (("tarefa", {"modo": "AUTO", "tarefa": "acao", "modelo": "qwen3:4b"}),
                    ("plano", {"etapas": ["abrir", "clicar"]}),
                    ("pensamento", {"texto": "pensando… ✓"}),
                    ("ferramenta", {"nome": "open_application", "resumo": "calculadora"}),
                    ("ferramenta_fim", {"nome": "open_application", "sucesso": True, "segundos": 0.2}),
                    ("ferramenta", {"nome": "click_element", "resumo": "7"}),
                    ("ferramenta_fim", {"nome": "click_element", "sucesso": False, "segundos": 0.1}),
                    ("resposta", {"texto": "Pronto."}), ("fim_stream", {})):
    j._ao_evento(tipo, dados)
j._ao_texto("\033[36m[openTARS] ▸ Abrindo calculadora\033[0m\n[openTARS]   ✓ 0.12s\n[openTARS]   ✗ Falhou (0.10s)\n")
app.processEvents()
QTest.qWait(200)
ruins = {}
for w in j.findChildren(QLabel) + j.findChildren(QPushButton):
    f = faltam(w.text())
    if f:
        ruins[w.text()[:50]] = f
assert not ruins, f"glifos que a IBM Plex não tem (o Qt os procuraria no fontconfig): {ruins}"
for idioma in ("pt_BR", "en"):
    dados = json.loads((RAIZ / "idiomas" / f"{idioma}.json").read_text(encoding="utf-8"))
    ruins = {k: faltam(v) for k, v in dados.items() if isinstance(v, str) and k.split(".")[0] in ("jp", "cfg", "rot", "tv", "pu", "probes", "avisos", "modo") and faltam(v)}
    assert not ruins, f"{idioma}: textos da janela com glifos fora da Plex: {ruins}"
assert not faltam(tema_seguro := __import__("tars_qt.tema", fromlist=["seguro"]).seguro("▸▾✗⏰▶▼✘✔●")), "a troca deixa glifo fora da Plex"
print("OK: nenhum texto da janela (nem as linhas da ferramenta) usa glifo fora da IBM Plex")

j.close()
print("\nTUDO OK.")
os._exit(0)
