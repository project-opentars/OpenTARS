"""5.3 (F7, passo 2): controlar a VM dos Probes DE FORA, pelo canal QMP do QEMU (decisão do Enzo em 08/11: "de fora"). Não existe
agente dentro da VM: a tela vem do `screendump` do QEMU e o mouse e o teclado são eventos de entrada virtuais (tablet e teclado
virtio, sem USB). O socket é um arquivo unix do próprio usuário (nada escuta em porta de rede).

Consequência que o Enzo precisa saber: de fora só dá para ver a tela e usar mouse e teclado. Não há `execute_terminal`, nem os
elementos pela acessibilidade (list_elements, click_element), nem ler arquivo da VM: o Probe lê a tela (imagem) e escreve no
teclado, como uma pessoa. Teclado: letras, números e pontuação do teclado americano; acentos e outros alfabetos não saem (a função
diz quais caracteres foram ignorados). O que acontece dentro da VM não passa pelas regras do app (comandos perigosos): a proteção é
a própria VM (rede fechada, sem arquivos do PC, reset no fim)."""
import json
import socket
import struct
import time
from pathlib import Path

TECLAS_SHIFT = {c: q for c, q in zip('~!@#$%^&*()_+{}|:"<>?', ["grave_accent", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "minus", "equal",
                                                                    "bracket_left", "bracket_right", "backslash", "semicolon", "apostrophe", "comma", "dot", "slash"])}
TECLAS_SEM_SHIFT = {" ": "spc", "\n": "ret", "\t": "tab", "-": "minus", "=": "equal", "[": "bracket_left", "]": "bracket_right", "\\": "backslash",
                    ";": "semicolon", "'": "apostrophe", ",": "comma", ".": "dot", "/": "slash", "`": "grave_accent"}
BOTOES = {"esquerdo": "left", "direito": "right", "meio": "middle", "left": "left", "right": "right", "middle": "middle"}
EIXO_MAX = 32767
NOMES_TECLAS = {"enter": "ret", "return": "ret", "esc": "esc", "escape": "esc", "tab": "tab", "backspace": "backspace", "delete": "delete",
                "space": "spc", "up": "up", "down": "down", "left": "left", "right": "right", "home": "home", "end": "end",
                "pageup": "pgup", "pagedown": "pgdn", "ctrl": "ctrl", "alt": "alt", "shift": "shift", "super": "meta_l", "win": "meta_l", "cmd": "meta_l"}


def qcode_do_caractere(c):
    """(qcode, com_shift) para um caractere do teclado americano, ou None se não dá para digitar."""
    if c.isascii() and c.isalpha():
        return c.lower(), c.isupper()
    if c.isascii() and c.isdigit():
        return c, False
    if c in TECLAS_SEM_SHIFT:
        return TECLAS_SEM_SHIFT[c], False
    if c in TECLAS_SHIFT:
        return TECLAS_SHIFT[c], True
    return None


def tamanho_do_png(caminho):
    """(largura, altura) lidas do cabeçalho do PNG."""
    with open(caminho, "rb") as f:
        cab = f.read(24)
    if cab[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("não é PNG")
    return struct.unpack(">II", cab[16:24])


class ControleVM:
    """Fala QMP (JSON por linha) com o QEMU pelo socket unix. Uma tela por vez: `tela()` devolve o caminho do PNG."""

    def __init__(self, socket_path, tela_padrao=(1280, 800), tempo=10):
        self.caminho, self.tela_tam, self.tempo = str(socket_path), tela_padrao, tempo
        self._sock = None
        self._buf = b""

    def conectar(self, espera=30):
        limite = time.monotonic() + espera
        while True:
            try:
                s = socket.socket(socket.AF_UNIX)
                s.settimeout(self.tempo)
                s.connect(self.caminho)
                break
            except OSError:
                s.close()
                if time.monotonic() > limite:
                    raise
                time.sleep(0.3)
        self._sock = s
        self._ler()                                   # a saudação
        self.comando("qmp_capabilities")
        return self

    def fechar(self):
        if self._sock:
            self._sock.close()
            self._sock = None

    def _ler(self):
        while b"\n" not in self._buf:
            dados = self._sock.recv(65536)
            if not dados:
                raise ConnectionError("o QEMU fechou o canal")
            self._buf += dados
        linha, _, self._buf = self._buf.partition(b"\n")
        return json.loads(linha)

    def comando(self, nome, **argumentos):
        self._sock.sendall((json.dumps({"execute": nome, **({"arguments": argumentos} if argumentos else {})}) + "\n").encode())
        while True:
            r = self._ler()
            if "event" in r:
                continue                               # eventos assíncronos do QEMU: não são a resposta
            if "error" in r:
                raise RuntimeError(f"{nome}: {r['error'].get('desc', r['error'])}")
            return r.get("return")

    # ---- ver
    def tela(self, destino):
        """Foto da tela em PNG (o formato de que o modelo de visão precisa). Atualiza o tamanho da tela."""
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        self.comando("screendump", filename=str(destino), format="png")
        self.tela_tam = tamanho_do_png(destino)
        return destino

    # ---- mouse
    def _eventos(self, eventos):
        self.comando("input-send-event", events=eventos)

    def mover(self, x, y):
        l, a = self.tela_tam
        x, y = min(max(0, int(x)), l - 1), min(max(0, int(y)), a - 1)
        self._eventos([{"type": "abs", "data": {"axis": "x", "value": round(x / max(1, l - 1) * EIXO_MAX)}},
                       {"type": "abs", "data": {"axis": "y", "value": round(y / max(1, a - 1) * EIXO_MAX)}}])

    def clicar(self, x, y, botao="esquerdo", duplo=False):
        b = BOTOES[botao]
        self.mover(x, y)
        time.sleep(0.05)
        for _ in range(2 if duplo else 1):
            self._eventos([{"type": "btn", "data": {"down": True, "button": b}}])
            self._eventos([{"type": "btn", "data": {"down": False, "button": b}}])
            time.sleep(0.05)

    def rolar(self, passos):
        """Positivo desce, negativo sobe."""
        botao = "wheel-down" if passos > 0 else "wheel-up"
        for _ in range(abs(int(passos))):
            self._eventos([{"type": "btn", "data": {"down": True, "button": botao}}])
            self._eventos([{"type": "btn", "data": {"down": False, "button": botao}}])

    # ---- teclado
    def _tecla(self, qcodes, apertar):
        self._eventos([{"type": "key", "data": {"down": apertar, "key": {"type": "qcode", "data": q}}} for q in qcodes])

    def digitar(self, texto, pausa=0.02):
        """Digita o texto como no teclado americano. Devolve os caracteres que NÃO deu para digitar (acentos, emoji...)."""
        ignorados = []
        for c in texto:
            achado = qcode_do_caractere(c)
            if achado is None:
                ignorados.append(c)
                continue
            q, shift = achado
            teclas = (["shift", q] if shift else [q])
            self._tecla(teclas, True)
            self._tecla(list(reversed(teclas)), False)
            time.sleep(pausa)
        return ignorados

    def atalho(self, combinacao):
        """"ctrl+alt+t", "enter", "alt+f4": as teclas apertadas juntas e soltas na ordem contrária."""
        qcodes = [NOMES_TECLAS.get(p.strip().lower(), p.strip().lower()) for p in combinacao.split("+")]
        self._tecla(qcodes, True)
        self._tecla(list(reversed(qcodes)), False)

    # ---- ligar e desligar
    def desligar_suave(self):
        self.comando("system_powerdown")

    def encerrar(self):
        """Mata a VM na hora (o reset apaga o overlay logo depois)."""
        try:
            self.comando("quit")
        except (ConnectionError, OSError):
            pass
        self.fechar()
