# openTARS — nucleo/visual.py
# Aparência do terminal novo da 5.3 (F8): um híbrido do CLI do Claude Code (● passo, ⎿ resultado, resposta formatada, aviso
# de contexto) com o do opencode (régua com o modo da conversa e barra de estado com pasta e ramo). Só desenho: nada aqui
# decide o que a IA faz. Parte do núcleo: roda dentro do namespace do tars.py, como as outras (ver _carregar_nucleo).
# flake8: noqa

import re as _re
import shutil as _shutil


def _largura_do_terminal(maximo=100):
    return max(40, min(maximo, _shutil.get_terminal_size((80, 20)).columns))


def _tempo_curto(segundos):
    """12 -> "12s"; 65 -> "1m 05s"."""
    segundos = int(segundos)
    return f"{segundos}s" if segundos < 60 else f"{segundos // 60}m {segundos % 60:02d}s"


def _nome_do_motor():
    """"llama.cpp" se o app fala com o motor próprio (porta 11435); senão "Ollama"."""
    try:
        import tars_motor_local
        if str(OLLAMA_HOST).rstrip("/") == tars_motor_local.URL:
            return "llama.cpp"
    except Exception:  # noqa: BLE001
        pass
    return "Ollama"


def _pasta_curta():
    """A pasta atual, com ~ no lugar da pasta pessoal."""
    pasta = os.getcwd()
    casa = os.path.expanduser("~")
    if pasta == casa or pasta.startswith(casa + os.sep):
        pasta = "~" + pasta[len(casa):]
    return pasta if len(pasta) <= 40 else "…" + pasta[-39:]


def _ramo_git():
    """O ramo do git da pasta atual, ou "" (sem git, fora de repositório, ou demorou)."""
    try:
        r = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=1.0,
                           cwd=os.getcwd(), env=_env_filho() if "_env_filho" in globals() else None)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _regua(modo):
    """A linha que separa um pedido do outro, com o modo da conversa à direita (como a barra do opencode)."""
    rotulo = " " + t(f"cli.regua.{modo}") + " "
    largura = _largura_do_terminal()
    return c("─" * max(4, largura - len(rotulo) - 2), Cor.CINZA) + c(rotulo, Cor.CINZA) + c("──", Cor.CINZA)


class _MarkdownTerminal:
    """Formata a resposta, que chega aos pedaços, linha por linha: títulos em negrito, listas com •, **negrito**, `código` em
    ciano e blocos de código com uma barra. Só vale num terminal de verdade (a janela e os pipes recebem o texto puro)."""

    def __init__(self):
        self.buf = ""
        self.em_codigo = False

    def reiniciar(self):
        self.buf, self.em_codigo = "", False

    def alimentar(self, texto):
        """Devolve o que já pode ser impresso (as linhas completas); o resto espera a próxima quebra de linha."""
        self.buf += texto
        if "\n" not in self.buf:
            return ""
        *linhas, self.buf = self.buf.split("\n")
        return "".join(self._linha(l) + "\n" for l in linhas)

    def terminar(self):
        resto, self.buf = self.buf, ""
        saida = self._linha(resto) if resto else ""
        self.em_codigo = False
        return saida

    @staticmethod
    def _inline(linha):
        linha = _re.sub(r"\*\*(.+?)\*\*", lambda m: Cor.NEGRITO + m.group(1) + Cor.RESET, linha)
        return _re.sub(r"`([^`\n]+)`", lambda m: Cor.CIANO + m.group(1) + Cor.RESET, linha)

    def _linha(self, linha):
        if linha.lstrip().startswith("```"):
            self.em_codigo = not self.em_codigo
            rotulo = linha.strip().strip("`").strip()
            return c("╭─ " + rotulo if self.em_codigo and rotulo else "╭─" if self.em_codigo else "╰─", Cor.CINZA)
        if self.em_codigo:
            return c("│ ", Cor.CINZA) + linha
        m = _re.match(r"^(#{1,6})\s+(.*)$", linha)
        if m:
            return Cor.NEGRITO + (Cor.CIANO if len(m.group(1)) == 1 else "") + self._inline(m.group(2)) + Cor.RESET
        m = _re.match(r"^(\s*)[-*]\s+(.*)$", linha)
        if m:
            return m.group(1) + c("•", Cor.CINZA) + " " + self._inline(m.group(2))
        if linha.startswith("> "):
            return c("│ ", Cor.CINZA) + c(self._inline(linha[2:]), Cor.ITALICO)
        return self._inline(linha)


_MD = _MarkdownTerminal()
