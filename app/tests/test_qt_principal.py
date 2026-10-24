"""5.0 Tesseract: a janela principal em Qt, de ponta a ponta, sem tela (offscreen), com o núcleo de verdade
contra um Ollama de mentira."""

import json
import os
import stat
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CASA = tempfile.mkdtemp(prefix="opentars-casa-")
os.environ["HOME"] = CASA
os.environ["TARS_ARQUIVO_SESSOES"] = os.path.join(CASA, "sessoes.json")
os.environ["TARS_ARQUIVO_NUVEM"] = os.path.join(CASA, "nuvem.json")
os.environ["TARS_ARQUIVO_PRIMEIRO_USO"] = os.path.join(CASA, "primeiro_uso.json")

from _util import RAIZ  # noqa: E402,F401

try:
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton
except ImportError:
    print("test_qt_principal: PULADO (PySide6 não instalado)")
    sys.exit(0)

chats = []


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
        if self.path == "/api/ps":
            return self._json({"models": []})
        self._json({}, 404)

    def do_POST(self):
        corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path == "/api/show":
            return self._json({"capabilities": ["completion", "tools"], "details": {
                "family": "qwen3", "parameter_size": "4.0B", "quantization_level": "Q4_K_M"}, "model_info": {}, "parameters": ""})
        if self.path == "/api/generate":
            return self._json({"model": corpo.get("model"), "done": True, "response": ""})
        if self.path == "/api/chat":
            chats.append(corpo)
            linhas = [{"model": "qwen3:4b", "message": {"role": "assistant", "content": "Pronto, **feito**."}, "done": False},
                      {"model": "qwen3:4b", "message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"}]
            dados = ("\n".join(json.dumps(l) for l in linhas) + "\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)
            return
        self._json({}, 404)


servidor = ThreadingHTTPServer(("127.0.0.1", 0), Falso)
threading.Thread(target=servidor.serve_forever, daemon=True).start()
os.environ["OLLAMA_HOST"] = f"127.0.0.1:{servidor.server_address[1]}"

from _util import carregar_tars  # noqa: E402

tars = carregar_tars()
tars.avisos_de_ambiente = lambda: []
tars.detectar_gpu = lambda forcar=False: None
tars.escolher_modelo = lambda texto, tarefa=None, complexa=False: tars.modelo_manual or "qwen3:4b"
tars.aquecer_ajudante = lambda: None

import tars_historico  # noqa: E402
import tars_i18n  # noqa: E402
import tars_primeiro_uso as pu  # noqa: E402
from tars_i18n import t  # noqa: E402
from tars_qt.primeiro_uso import criar_aplicativo  # noqa: E402
from tars_qt.principal import JanelaPrincipal  # noqa: E402
from tars_qt.conversa import CartaoAprovacao, MensagemIA  # noqa: E402

app = criar_aplicativo(["teste"])
SAIDA = os.environ.get("TARS_CAPTURAS")


def esperar(cond, segundos=15, o_que=""):
    fim = time.time() + segundos
    while time.time() < fim:
        app.processEvents()
        if cond():
            return
        QTest.qWait(20)
    import faulthandler
    faulthandler.dump_traceback(all_threads=True)     # onde cada thread parou (no CI do Windows e do macOS, a única pista)
    raise AssertionError(f"tempo esgotado: {o_que}")


def foto(j, nome):
    if SAIDA:
        QTest.qWait(500)
        j.grab().save(os.path.join(SAIDA, nome + ".png"))


def textos(widget):
    return [l.text() for l in widget.findChildren(QLabel)]


def mensagens_ia(j):
    return j.area.findChildren(MensagemIA)


historico = tars_historico.Historico(os.path.join(CASA, "historico.json"))
j = JanelaPrincipal(tars, historico=historico, capturar_stdout=False)
j.resize(1200, 780)
j.show()
esperar(lambda: j._modelos, o_que="modelos carregados")
assert j.pilha.currentIndex() == 0 and j.vazio is not None, "começa no estado vazio"
assert j.cabecalho.pilula.text() == t("jp.modelo_auto"), j.cabecalho.pilula.text()
assert not j.cabecalho.b_parar.isVisibleTo(j), "Parar só aparece trabalhando"
assert j.lateral.v_titulo.text() == "" and not j.lateral.cartao_versao.isVisibleTo(j)
foto(j, "principal_vazio")
print("OK: abre no estado vazio, modelo automático, sem botão Parar")

# --- enviar um pedido de verdade --------------------------------------------------------------
j.compositor.entrada.setPlainText("abra o navegador")
j.compositor.b_enviar.click()
assert j.vazio is None and j.ponte.esta_ocupado
assert j.cabecalho.b_parar.isVisibleTo(j), "Parar aparece enquanto trabalha"
esperar(lambda: not j.ponte.esta_ocupado and mensagens_ia(j) and "feito" in mensagens_ia(j)[-1].texto_completo(), o_que="resposta")
esperar(lambda: not j.cabecalho.b_parar.isVisibleTo(j))
assert j.compositor.texto() == "", "a entrada esvazia ao enviar"
assert j.cabecalho.titulo.text() == "abra o navegador", j.cabecalho.titulo.text()
assert any("abra o navegador" in x for x in textos(j.area))
esperar(lambda: len(historico.listar()) == 1, o_que="histórico gravado")
assert historico.listar()[0]["titulo"] == "abra o navegador"
esperar(lambda: j.lateral._itens, o_que="conversa na barra lateral")
foto(j, "principal_conversa")
print("OK: pedido de ponta a ponta (bolha da pessoa, resposta em streaming, título, histórico)")

# --- etapas, ferramentas e aviso (o que o núcleo emite) --------------------------------------------
j.ponte.evento.emit("plano", {"etapas": ["Abrir o editor", "Escrever o texto", "Salvar"]})
ia = mensagens_ia(j)[-1] if mensagens_ia(j) else None
j._ia = None
j._ao_evento("plano", {"etapas": ["Abrir o editor", "Escrever o texto", "Salvar"]})
ia = j._ia
assert ia.etapas is not None and ia.etapas.total() == 3 and ia.etapas.feitas == 0
j._ao_evento("ferramenta", {"nome": "open_application", "resumo": "gedit"})
j._ao_evento("ferramenta_fim", {"nome": "open_application", "sucesso": True, "segundos": 0.4})
assert ia.etapas.feitas == 1, ia.etapas.feitas
j._ao_evento("ferramenta", {"nome": "take_screenshot", "resumo": ""})
j._ao_evento("ferramenta_fim", {"nome": "take_screenshot", "sucesso": True, "segundos": 0.1})
assert ia.etapas.feitas == 1, "olhar a tela não conclui etapa"
assert t("jp.etapa_de", atual=2, total=3) == j.cabecalho.sub.text(), j.cabecalho.sub.text()
j._ao_texto("[openTARS] ✗ falhou algo\n")
assert any("falhou algo" in x for x in textos(ia))
j._ao_concluido("ok")
assert ia.etapas.feitas == 3, "ao concluir, as etapas fecham"
assert j.cabecalho.sub.text() == t("jp.pronto")
print("OK: etapas avançam por ação concluída, fecham no fim; avisos viram linhas")

# --- pergunta antes de ação arriscada ---------------------------------------------------------------
resultado = {}
j._ia = None
j.ponte.esta_ocupado = False
threading.Thread(target=lambda: resultado.setdefault("a", tars.confirmar_comando_hook("rm -rf ~/teste")), daemon=True).start()
esperar(lambda: j.area.findChildren(CartaoAprovacao), o_que="cartão de aprovação")
cartao = j.area.findChildren(CartaoAprovacao)[-1]
assert j.cabecalho.sub.text() == t("jp.espera_voce")
botoes = {b.text(): b for b in cartao.findChildren(QPushButton)}
foto(j, "principal_aprovacao")
botoes[t("jp.negar")].click()
esperar(lambda: "a" in resultado)
assert resultado["a"] is False
resultado.clear()
threading.Thread(target=lambda: resultado.setdefault("a", tars.confirmar_comando_hook("sudo apt remove x")), daemon=True).start()
esperar(lambda: len(j.area.findChildren(CartaoAprovacao)) == 2)
{b.text(): b for b in j.area.findChildren(CartaoAprovacao)[-1].findChildren(QPushButton)}[t("jp.permitir")].click()
esperar(lambda: "a" in resultado)
assert resultado["a"] is True
print("OK: ação arriscada pergunta no cartão; Negar e Permitir chegam ao núcleo")

# --- nova conversa, histórico, busca ---------------------------------------------------------------
primeiro_id = j.ponte.id_conversa
j.nova_conversa()
assert j.vazio is not None and j.ponte.id_conversa != primeiro_id
assert len(tars.conversa) == 1, "o núcleo recomeçou do zero"
j.compositor.entrada.setPlainText("segundo assunto")
j.enviar()
esperar(lambda: not j.ponte.esta_ocupado and len(historico.listar()) == 2, o_que="2 conversas")
j.abrir_conversa(primeiro_id)
assert j.cabecalho.titulo.text() == "abra o navegador"
assert any("abra o navegador" in x for x in textos(j.area)) and not any("segundo assunto" in x for x in textos(j.area))
assert any(m["role"] == "user" and "abra o navegador" in m["content"] for m in tars.conversa), "o contexto voltou pra IA"
j.lateral.busca.setText("segundo")
esperar(lambda: len(j.lateral._itens) == 1)
j.lateral.busca.setText("zzzz")
esperar(lambda: not j.lateral._itens)
assert any(t("jp.nenhum_resultado") in x for x in textos(j.lateral))
j.lateral.busca.setText("")
esperar(lambda: len(j.lateral._itens) == 2)
j._apagar_conversa(primeiro_id)
esperar(lambda: len(historico.listar()) == 1)
print("OK: nova conversa, abrir devolve o contexto, busca e apagar")

# --- modelo -----------------------------------------------------------------------------------------
j._escolher_modelo("qwen3:4b")
assert tars.modo_modelo == "MANUAL" and "qwen3:4b" in j.cabecalho.pilula.text()
j._escolher_modelo(None)
assert tars.modo_modelo == "AUTO" and j.cabecalho.pilula.text() == t("jp.modelo_auto")
print("OK: escolher o modelo na pílula e voltar ao automático")

# --- anexos ---------------------------------------------------------------------------------------------
pasta = Path(tempfile.mkdtemp(prefix="opentars-anx-"))
(pasta / "nota.txt").write_text("conteudo do arquivo de teste\n" * 5, encoding="utf-8")
novos = j.anexar_arquivos([str(pasta / "nota.txt")])
assert len(novos) == 1 and j.compositor.chips_w.isVisibleTo(j) and len(j.compositor.anexos()) == 1
chats.clear()
j.compositor.entrada.setPlainText("leia a nota")
j.enviar()
esperar(lambda: not j.ponte.esta_ocupado and chats, o_que="anexo enviado")
pedidos = [m["content"] for m in chats[0]["messages"] if m["role"] == "user"]
assert any("conteudo do arquivo de teste" in c and c.startswith("leia a nota") for c in pedidos), pedidos
assert not j.compositor.anexos() and not j.compositor.chips_w.isVisibleTo(j)
print("OK: anexo chega ao Ollama e o chip some")

# --- voz sem estar instalada abre a configuração de voz ---------------------------------------------------
j.voz.pronta = lambda: False
j.voz.faltando = lambda: ["faster-whisper"]
j._mudar_modo_voz("continua")
j._mic_clicado()
assert j.pilha.currentWidget() is j.config and j.config.nav["voz"].isChecked()
foto(j, "config_voz")
j.pilha.setCurrentIndex(0)
j._mudar_modo_voz("segurar")
print("OK: microfone sem voz instalada leva à página Voz")

# --- tela de voz --------------------------------------------------------------------------------------------
j.pilha.setCurrentIndex(1)
j.tela_voz.ao_estado("ouvindo")
foto(j, "tela_voz")
j._sair_da_voz()
assert j.pilha.currentIndex() == 0

# --- configurações --------------------------------------------------------------------------------------------
for nome in ("geral", "voz", "memoria", "nuvem", "atualizacoes", "sobre"):
    j.abrir_config(nome)
    app.processEvents()
    assert j.config.nav[nome].isChecked() and j.pilha.currentIndex() == 2
    foto(j, f"config_{nome}")
esperar(lambda: "Ollama" in j.config.paginas["geral"].estado.text() and "…" != j.config.paginas["geral"].estado.text(), o_que="estado do Ollama")
assert t("cfg.gargantua_falta") in j.config.paginas["geral"].estado.text()

# memória
tars.memoria.lembrar("meu navegador é o firefox")
j.abrir_config("memoria")
pm = j.config.paginas["memoria"]
assert any("firefox" in x for x in textos(pm))
pm._esquecer("meu navegador é o firefox")
assert tars.memoria.listar() == [] and any(t("cfg.memoria.vazia") in x for x in textos(pm))
tars.memoria.lembrar("x")
pm.b_geral.click()
assert "x" in tars.memoria.listar(), "apagar tudo pede confirmação (duas batidas)"
pm.b_geral.click()
assert tars.memoria.listar() == [] and historico.listar() == []
print("OK: memória listada, esquecida item a item; apagar tudo pede confirmação")

# nuvem: a chave fica em arquivo 0600 e nunca aparece na tela
j.abrir_config("nuvem")
pn = j.config.paginas["nuvem"]
pn.chips["groq"].click()
assert pn.endereco.text() == "https://api.groq.com/openai/v1"
pn.ativa.setChecked(True)
pn.chave.setText("SEGREDO-123")
pn._salvar()
d = pu.carregar_nuvem()
assert d["ativa"] and d["provedor"] == "groq" and d["chave"] == "SEGREDO-123"
assert os.name == "nt" or stat.S_IMODE(os.stat(pu.arquivo_nuvem()).st_mode) == 0o600
assert pn.chave.text() == "" and not any("SEGREDO" in x for x in textos(pn))
j.abrir_config("nuvem")
assert "SEGREDO" not in pn.chave.placeholderText()
print("OK: nuvem salva a chave em 0600 e nunca a mostra")

# idioma: trocar pede pra reconstruir a janela
j.abrir_config("geral")
assert not getattr(j, "reconstruir", False)
j.config.paginas["geral"]._trocar(tars_i18n.idioma_atual())
assert not getattr(j, "reconstruir", False), "o mesmo idioma não reconstrói"

j.close()
print("test_qt_principal: OK")
