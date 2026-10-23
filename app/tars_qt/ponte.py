"""A ponte entre a janela (Qt) e o núcleo do openTARS (tars.py).

O núcleo roda numa thread de trabalho e conta o que acontece por eventos (ferramenta rodando,
resposta chegando...). A ponte os transforma em sinais do Qt (que chegam na thread da janela) e
cuida de: um pedido por vez, o Parar, a confirmação de comando perigoso (a thread do núcleo espera
a resposta da pessoa), o histórico de conversas e a coleta de informações do começo (modelos, versão
nova). Não desenha nada: quem desenha é principal.py."""

import re
import sys
import threading

from PySide6.QtCore import QObject, Signal

import tars_historico
from . import fio


_ANSI = re.compile(r"\033\[[0-9;]*m")
_CAIXA = re.compile(r"^\s*[╭╰│┌└├─]")


class _Escritor:
    """No lugar do sys.stdout: o que o núcleo imprime vira o sinal `texto` (sem as cores do terminal)."""

    def __init__(self, ponte):
        self.ponte = ponte
        self._pular = False

    def write(self, texto):
        if texto.startswith("Xlib.xauth:"):      # ruído do python-xlib sem ~/.Xauthority
            self._pular = True
            return
        if self._pular and texto == "\n":
            self._pular = False
            return
        self._pular = False
        if texto:
            fio.emitir(self.ponte.texto, texto)

    def flush(self):
        pass


def limpar_saida(texto):
    """Linhas de aviso do núcleo: sem cor de terminal, sem caixas desenhadas, sem linha vazia."""
    linhas = [_ANSI.sub("", l).rstrip() for l in (texto or "").splitlines()]
    return [l for l in linhas if l.strip() and not _CAIXA.match(l)]


class Aprovacao:
    """Um pedido de confirmação em andamento: a thread do núcleo espera em `esperar`."""

    def __init__(self, comando):
        self.comando = comando
        self.ok = False
        self._pronto = threading.Event()

    def responder(self, ok):
        self.ok = bool(ok)
        self._pronto.set()

    def esperar(self):
        self._pronto.wait()
        return self.ok


class Ponte(QObject):
    evento = Signal(str, dict)          # (tipo, dados) do núcleo
    texto = Signal(str)                 # o que o núcleo imprimiu
    ocupado = Signal(bool)
    aprovacao = Signal(object)          # Aprovacao
    iniciado = Signal(dict)             # informações do começo
    modelos = Signal(list)              # lista pro seletor
    concluido = Signal(str)             # um pedido terminou (texto da resposta, ou "")
    conversa_mudou = Signal()           # o histórico (lista lateral) mudou

    def __init__(self, nucleo, historico=None, capturar_stdout=True):
        super().__init__()
        self.nucleo = nucleo
        self.historico = historico if historico is not None else tars_historico.Historico()
        self.id_conversa = self.historico.nova_id()
        self.esta_ocupado = False
        self._fechado = False
        self._aprovacao = None
        self._trabalho = None
        self._stdout_original = None
        if capturar_stdout:
            self._stdout_original = sys.stdout
            sys.stdout = _Escritor(self)
        nucleo.definir_ouvinte_saida(lambda tipo, dados: self._emitir(self.evento, tipo, dict(dados)))
        nucleo.confirmar_comando_hook = self._confirmar
        # o "ocupado" que a interface lê muda NA thread da janela, na mesma fila dos sinais do pedido: se o fim do
        # pedido limpasse a marca na thread de trabalho, um novo envio entraria antes do sinal "concluído" do
        # anterior, e esse sinal atrasado apagaria o estado do novo pedido
        self.ocupado.connect(self._marcar_ocupado)

    def _marcar_ocupado(self, ocupado):
        self.esta_ocupado = bool(ocupado)

    def _emitir(self, sinal, *args):
        """Emite de qualquer thread; depois que a janela fechou, uma thread de trabalho que termina tarde não
        mexe mais em objetos Qt que já estão sendo desmontados."""
        if self._fechado:
            return
        try:
            fio.emitir(sinal, *args)
        except RuntimeError:      # o objeto C++ já foi destruído
            pass

    def encerrar(self):
        """Devolve o terminal ao que era (a janela fechou)."""
        self._fechado = True
        if self._stdout_original is not None:
            sys.stdout = self._stdout_original
            self._stdout_original = None
        self.nucleo.definir_ouvinte_saida(None)
        self.nucleo.confirmar_comando_hook = None
        if self._aprovacao is not None:
            self._aprovacao.responder(False)

    # -- começo ----------------------------------------------------------
    def iniciar(self):
        """Coleta o que a janela mostra no começo (fora da thread da janela: consulta o Ollama)."""
        def trabalho():
            n = self.nucleo
            info = {"online": False, "avisos": [], "n_modelos": 0}
            try:
                # a janela começa numa conversa nova: o contexto da sessão anterior ficaria escondido (a IA o veria,
                # a tela não) e o primeiro envio salvaria aquelas mensagens velhas dentro da conversa nova
                n.conversa[:] = [{"role": "system", "content": n.montar_system_prompt()}]
                info["online"] = bool(n.ollama_online())
                catalogo = n.catalogar_modelos()
                info["n_modelos"] = sum(1 for m in catalogo.values()
                                        if m["categoria"] != "embedding" and m["tag"] not in n.MODELOS_AJUDANTES)
                info["avisos"] = list(n.avisos_de_ambiente())
                info["gpu"] = n.detectar_gpu()
                if info["online"] and info["n_modelos"] == 0:
                    info["avisos"].append(n.t("aviso.sem_modelo_conversa"))
                if info["online"]:
                    try:
                        n.aquecer_ajudante()
                    except Exception:
                        pass
            except Exception as e:
                info["avisos"].append(str(e))
            self._emitir(self.iniciado, info)
            self.atualizar_modelos()

        def trabalho_serializado():
            with self.nucleo.TRAVA_PEDIDO:      # não corre junto com o primeiro pedido (nem carrega o modelo duas vezes)
                trabalho()

        threading.Thread(target=trabalho_serializado, daemon=True).start()

    def atualizar_modelos(self):
        """Emite [(rotulo, tag, nuvem)] dos modelos que a pessoa pode escolher na mão."""
        def trabalho():
            n = self.nucleo
            itens = []
            try:
                catalogo = n.catalogar_modelos()
                for tag, m in sorted(catalogo.items()):
                    if m["categoria"] == "embedding" or tag in n.MODELOS_AJUDANTES or n.visao_lib.e_cooper(tag):
                        continue
                    itens.append((tag, tag, False))
            except Exception:
                pass
            try:
                for tag in sorted(n.listar_modelos_api()):
                    itens.append((tag[len(n.api.PREFIXO):], tag, True))
            except Exception:
                pass
            self._emitir(self.modelos, itens)

        threading.Thread(target=trabalho, daemon=True).start()

    # -- escolha do modelo ----------------------------------------------------
    def modo_atual(self):
        """('AUTO', None) ou ('MANUAL', tag)."""
        n = self.nucleo
        return (n.modo_modelo, n.modelo_manual if n.modo_modelo == "MANUAL" else None)

    def escolher_modelo(self, tag):
        """None = automático."""
        n = self.nucleo
        if not tag:
            n.modo_modelo, n.modelo_manual = "AUTO", None
            return
        n.modo_modelo, n.modelo_manual = "MANUAL", tag
        if not n.api.eh_modelo_api(tag):
            def carregar():
                with n.TRAVA_PEDIDO:
                    n._carregar_em_segundo_plano(tag)
            threading.Thread(target=carregar, daemon=True).start()

    # -- pedidos ---------------------------------------------------------
    def enviar(self, texto, anexos=None):
        if self.esta_ocupado or not (texto.strip() or anexos):
            return False
        self.esta_ocupado = True
        self.ocupado.emit(True)

        id_do_pedido = self.id_conversa

        def trabalho():
            resposta = ""
            try:
                with self.nucleo.TRAVA_PEDIDO:
                    resposta = self.nucleo.processar_mensagem(texto, anexos=anexos or None) or ""
            except Exception as e:
                self._emitir(self.texto, f"[openTARS] {self.nucleo.t('msg.erro_inesperado', erro=e)}\n")
            finally:
                try:
                    self.historico.salvar(id_do_pedido, self.nucleo.conversa)
                except Exception:
                    pass
                self._emitir(self.ocupado, False)
                self._emitir(self.concluido, resposta)
                self._emitir(self.conversa_mudou)

        self._trabalho = threading.Thread(target=trabalho, daemon=True)
        self._trabalho.start()
        return True

    def parar(self):
        if self.esta_ocupado:
            self.nucleo.cancelar_resposta()
        if self._aprovacao is not None:       # parar também nega o que estava esperando a pessoa
            self._aprovacao.responder(False)

    def _confirmar(self, comando):
        """Chamado na thread do núcleo: pergunta na janela e espera."""
        a = Aprovacao(comando)
        self._aprovacao = a
        self._emitir(self.aprovacao, a)
        try:
            return a.esperar()
        finally:
            self._aprovacao = None

    # -- conversas -------------------------------------------------------
    def nova_conversa(self):
        if self.esta_ocupado:
            return False
        self.nucleo.limpar_sessao()
        self.id_conversa = self.historico.nova_id()
        return True

    def abrir_conversa(self, id_):
        """Devolve as mensagens (e põe o contexto delas no núcleo), ou None."""
        if self.esta_ocupado:
            return None
        mensagens = self.historico.abrir(id_)
        if mensagens is None:
            return None
        n = self.nucleo
        n.conversa[:] = [{"role": "system", "content": n.montar_system_prompt()}] + mensagens
        n.salvar_sessoes()
        self.id_conversa = id_
        return mensagens

    def apagar_conversa(self, id_):
        ok = self.historico.apagar(id_)
        if ok and id_ == self.id_conversa and not self.esta_ocupado:
            self.nova_conversa()
        self.conversa_mudou.emit()
        return ok
