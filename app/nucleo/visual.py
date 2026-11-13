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
    try:
        pasta = os.path.realpath(os.getcwd())          # realpath dos dois lados: no macOS /var é /private/var e o ~ não casava
    except OSError:                                    # a pasta atual foi apagada: o enfeite não derruba o chat
        return ""
    casa = os.path.realpath(os.path.expanduser("~"))
    if pasta == casa or pasta.startswith(casa + os.sep):
        pasta = "~" + pasta[len(casa):]
    return pasta if len(pasta) <= 40 else "…" + pasta[-39:]


def _ramo_git():
    """O ramo do git da pasta atual, ou "" (sem git, fora de repositório, ou demorou)."""
    try:
        r = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=1.0,
                           cwd=os.getcwd(), env=_env_filho() if "_env_filho" in globals() else None)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:  # noqa: BLE001  (sem git, ou um teste que troca o subprocess: o enfeite nunca derruba o chat)
        return ""


def _regua(modo):
    """A linha que separa um pedido do outro, com o modo da conversa à direita (como a barra do opencode)."""
    rotulo = " " + t(f"cli.regua.{modo}") + " "
    largura = _largura_do_terminal()
    return c("─" * max(4, largura - len(rotulo) - 2), Cor.CINZA) + c(rotulo, Cor.CINZA) + c("──", Cor.CINZA)


def _partes_do_status():
    """Modelo, contexto usado, pasta com o ramo, modo (quando não é o padrão) e AGENTS.md: a mesma conta da linha de status."""
    modelo = modelo_atual or (modelo_manual if modo_modelo == "MANUAL" else "auto")
    usados = estimar_tokens(conversa)
    partes = [str(modelo).split("/")[-1], t("cli.status_contexto", pct=min(100, int(100 * usados / max(1, contexto_ia()))))]
    ramo = _ramo_git()
    partes.append(_pasta_curta() + (f" ⎇ {ramo}" if ramo else ""))
    if MODO_PERMISSAO != "perguntar":
        partes.append(t(f"cli.status_modo.{MODO_PERMISSAO}"))
    if CONTEXTO_PROJETO["caminho"]:
        partes.append("AGENTS.md")
    return partes


_SELO = "\033[1;38;5;16;48;5;78m"   # preto em negrito sobre verde (256 cores): o selo do openTARS na barra (como o do modo no opencode)


def _barra_de_estado(largura):
    """A barra do opencode embaixo da caixa: selo "openTARS", modelo · motor · contexto · pasta ⎇ ramo, e a dica à direita."""
    partes = _partes_do_status()
    partes.insert(1, _nome_do_motor())
    esquerda = " openTARS "
    meio = "  " + "  ·  ".join(partes)
    dica = t("cli.barra_dica")
    sobra = largura - len(esquerda) - len(meio) - len(dica) - 1
    if sobra < 1:
        meio, sobra = meio[:max(0, largura - len(esquerda) - 2)], 0
        dica = ""
    return _SELO + esquerda + Cor.RESET + c(meio, Cor.CINZA) + " " * sobra + c(dica, Cor.CINZA)


def _pedir_na_caixa(ini, fim):
    """Claude Code: o pedido é digitado dentro de uma caixa de cantos redondos, com a barra de estado logo abaixo. A caixa e a
    barra são desenhadas antes e o cursor sobe para dentro; depois do Enter a linha ganha a borda da direita e o cursor desce
    além da barra. Só num terminal de verdade com readline (as marcas \\001 e \\002 mantêm a edição da linha certa)."""
    largura = _largura_do_terminal() - 1
    borda = lambda s: c(s, Cor.CINZA)
    sys.stdout.write("\n" + borda("╭" + "─" * (largura - 2) + "╮") + "\n" + borda("│") + " " * (largura - 2) + borda("│") + "\n"
                     + borda("╰" + "─" * (largura - 2) + "╯") + "\n" + _barra_de_estado(largura) + "\033[2A\r")
    sys.stdout.flush()
    try:
        linha = input(ini + Cor.CINZA + fim + "│ " + ini + Cor.NEGRITO + Cor.VERDE + fim + "❯ " + ini + Cor.RESET + fim)
    except BaseException:
        sys.stdout.write("\r\n\033[J")      # Ctrl+C ou Ctrl+D: some a caixa de baixo e a barra, a mensagem sai limpa
        sys.stdout.flush()
        raise
    visivel = "│ ❯ " + linha
    if len(visivel) <= largura - 2:          # coube numa linha: fecha a borda da direita e pula a borda de baixo e a barra
        sys.stdout.write("\033[1A\r" + borda("│") + " " + c("❯ ", Cor.NEGRITO + Cor.VERDE) + linha
                         + " " * (largura - 1 - len(visivel)) + borda("│") + "\n\033[1B\n")
    else:                                     # quebrou em várias linhas: a caixa já se desfez; só limpa o que sobrou embaixo
        sys.stdout.write("\033[J")
    sys.stdout.flush()
    return linha


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
