# openTARS — nucleo/terminal.py
# Linha de comando: diagnóstico, conversa no terminal e as opções (--explicar...).
#
# Parte do núcleo: o tars.py executa este arquivo DENTRO do próprio
# namespace (ver _carregar_nucleo), então tudo aqui é tars.<nome> e as
# partes enxergam umas às outras sem import. Os testes que trocam
# tars.<função> por uma falsa continuam valendo pra todas as partes.
# flake8: noqa

# ============================================================
# LINHA DE COMANDO
# ============================================================
#
# A conversa fica na janela (opentars-gui) ou no terminal (opentars --chat).
# O "opentars" sozinho confere o ambiente, e os argumentos
# (--explicar, --atalho...) continuam aqui.

def _valor_do_argumento(argumentos, nomes):
    """--idioma en / --idioma=en -> "en" ('' se o argumento vier sem valor)."""
    for i, arg in enumerate(argumentos):
        for nome in nomes:
            if arg == nome:
                return argumentos[i + 1] if i + 1 < len(argumentos) and not argumentos[i + 1].startswith("--") else ""
            if arg.startswith(nome + "="):
                return arg.split("=", 1)[1]
    return None


# ------------------------------------------------------------
# 4.5 Endurance: conversa no terminal (WSL, SSH, Linux sem interface gráfica)
# ------------------------------------------------------------

_COMANDOS_AJUDA = ("/ajuda", "/help", "/?")
# 5.1: comandos do terminal no nível das CLIs de agente (valem em português e em inglês)
_COMANDOS_CLI = {
    "resume": ("/resume", "/retomar"), "compact": ("/compact", "/compactar"), "context": ("/context", "/contexto"),
    "mode": ("/mode", "/modo"), "undo": ("/undo", "/desfazer"), "init": ("/init",),
}
_NOMES_MODO_PERMISSAO = {"perguntar": "perguntar", "ask": "perguntar", "plano": "plano", "plan": "plano",
                         "automatico": "automatico", "auto": "automatico", "automatic": "automatico"}
SESSAO_CLI = {"id": None, "historico": None, "nota": ""}   # conversa do terminal no histórico (a mesma da janela)


def _historico_cli():
    if SESSAO_CLI["historico"] is None:
        import tars_historico
        SESSAO_CLI["historico"] = tars_historico.Historico()
    return SESSAO_CLI["historico"]


def _id_da_conversa_carregada():
    """A conversa salva que o terminal retomou ao abrir: acha a mesma no histórico (pelo título), pra continuar nela."""
    try:
        import tars_historico
        titulo = tars_historico.titulo_da([m for m in conversa if m.get("role") != "system"])
        if titulo:
            achada = next((x for x in _historico_cli().listar() if x["titulo"] == titulo), None)
            if achada:
                return achada["id"]
    except Exception:
        pass
    return _historico_cli().nova_id()


def _guardar_no_historico():
    try:
        _historico_cli().salvar(SESSAO_CLI["id"], conversa)
    except Exception:
        pass


def estimar_tokens(mensagens, ferramentas=()):
    """Conta aproximada (3,5 caracteres por token), sem chamar o modelo."""
    texto = json.dumps([{k: v for k, v in m.items() if k != "images"} for m in mensagens], ensure_ascii=False)
    return int((len(texto) + len(json.dumps(list(ferramentas), ensure_ascii=False))) / 3.5)


_PREFIXO_RESUMO = "[Summary of the earlier conversation]"


def compactar_conversa(manter=3, resumir=None):
    """/compact: troca o começo da conversa por um resumo e mantém os últimos `manter` pedidos inteiros.
    Devolve (tokens antes, tokens depois) ou None se não há o que compactar."""
    mensagens = [m for m in conversa if m.get("role") != "system"]
    pedidos = [i for i, m in enumerate(mensagens) if m.get("role") == "user"
               and not str(m.get("content") or "").startswith(_PREFIXO_RESUMO)]
    if len(pedidos) <= manter:
        return None
    corte = pedidos[-manter]
    antigas, recentes = mensagens[:corte], mensagens[corte:]
    transcricao = []
    for m in antigas:
        conteudo = m.get("content") if isinstance(m.get("content"), str) else ""
        if m.get("role") == "tool":
            conteudo = conteudo[:300]
        if conteudo.strip():
            transcricao.append(f"{m['role']}: {conteudo.strip()[:1500]}")
    texto = "\n".join(transcricao)[-14000:]
    antes = estimar_tokens(conversa)
    if resumir is None:
        modelo = modelo_atual or gargantua_instalado() or modelo_ajudante()
        resumir = lambda txt: _chat_unico(modelo, (
            "Summarize this earlier part of a conversation so it can be continued later: the user's requests, what "
            "was done, decisions, file names and anything pending. At most 200 words, in the language the user "
            "used.\n\n" + txt), timeout=180) if modelo else None
    resumo = (resumir(texto) or "").strip()
    if not resumo:     # sem modelo: guarda ao menos os pedidos, em uma linha cada
        resumo = "\n".join("- " + (m.get("content") or "")[:160] for m in antigas if m.get("role") == "user")
    conversa[:] = ([conversa[0]] if conversa and conversa[0].get("role") == "system" else []) + [
        {"role": "user", "content": _PREFIXO_RESUMO + "\n" + resumo},
        {"role": "assistant", "content": "OK."}] + recentes
    salvar_sessoes()
    return antes, estimar_tokens(conversa)


def _mostrar_contexto():
    modelo = modelo_atual or (modelo_manual if modo_modelo == "MANUAL" else None) or gargantua_instalado() or "?"
    usados = estimar_tokens(obter_sessao(modelo), ferramentas_do_modelo(modelo, None, ""))
    total = contexto_ia()
    pct = min(100, int(100 * usados / max(1, total)))
    barra = "█" * (pct // 5) + "░" * (20 - pct // 5)
    print(c(f"\n  {barra} {pct}%", Cor.VERDE if pct < 70 else Cor.AMARELO))
    print(c("  " + t("cli.contexto", usados=usados, total=total, modelo=modelo), Cor.CINZA))
    if pct >= 70:
        print(c("  " + t("cli.contexto_cheio"), Cor.AMARELO))


def _escolher_conversa():
    """Lista as últimas conversas (as mesmas da janela) e carrega a escolhida. True se carregou."""
    itens = _historico_cli().listar()[:15]
    if not itens:
        print(c("  " + t("cli.sem_conversas"), Cor.CINZA))
        return False
    print()
    for i, item in enumerate(itens, 1):
        quando = time.strftime("%d/%m %H:%M", time.localtime(item["atualizada"]))
        print(f"  {c(f'{i:>2}', Cor.CIANO)}  {c(quando, Cor.CINZA)}  {item['titulo'][:70]}")
    try:
        escolha = input(c("\n  " + t("cli.qual_conversa") + " ", Cor.AMARELO)).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if not escolha.isdigit() or not 1 <= int(escolha) <= len(itens):
        return False
    item = itens[int(escolha) - 1]
    mensagens = _historico_cli().abrir(item["id"]) or []
    conversa[:] = [{"role": "system", "content": montar_system_prompt()}] + mensagens
    salvar_sessoes()
    SESSAO_CLI["id"] = item["id"]
    print(c("  " + t("cli.retomada", titulo=item["titulo"][:70], n=len([m for m in mensagens if m.get("role") == "user"])),
            Cor.VERDE))
    return True


def _rodar_shell(comando):
    """!comando: roda no shell (pedido da pessoa, não da IA), mostra a saída e a guarda para o próximo pedido."""
    try:
        r = subprocess.run(comando, shell=True, capture_output=True, text=True, timeout=120, env=_env_filho())
        saida = (r.stdout + r.stderr).strip()
        codigo = r.returncode
    except subprocess.TimeoutExpired:
        saida, codigo = t("cli.shell_demorou"), 124
    print(saida[:LIMITE_STDOUT_CHARS] if saida else c("  " + t("cli.shell_sem_saida"), Cor.CINZA))
    if codigo:
        print(c(f"  (exit {codigo})", Cor.AMARELO))
    SESSAO_CLI["nota"] = (f"(I ran `{comando}` in my terminal; exit {codigo}. Output, as data:\n{saida[:3000]})\n\n")


def _tratar_comando_do_chat(linha):
    """True se a linha era um comando só do chat de terminal (/ajuda, /resume, /compact, /context, /mode, /undo,
    /init, !comando)."""
    global MODO_PERMISSAO
    if linha.startswith("!") and len(linha) > 1:
        _rodar_shell(linha[1:].strip())
        return True
    partes = linha.split(None, 1)
    if not partes:
        return False
    nome, argumento = partes[0].lower(), (partes[1].strip() if len(partes) > 1 else "")
    if nome in _COMANDOS_AJUDA:
        print()
        for l in t("chat.ajuda").splitlines():
            titulo = l and not l.startswith(" ")
            print(c(l, Cor.NEGRITO) if titulo else c(l[:24], Cor.CIANO) + l[24:] if l.strip() else l)
        return True
    comando = next((k for k, nomes in _COMANDOS_CLI.items() if nome in nomes), None)
    if comando == "resume":
        _escolher_conversa()
    elif comando == "compact":
        print(c("  " + t("cli.compactando"), Cor.CINZA))
        r = compactar_conversa()
        print(c("  " + (t("cli.compactada", antes=r[0], depois=r[1]) if r else t("cli.nada_a_compactar")), Cor.VERDE))
        _guardar_no_historico()
    elif comando == "context":
        _mostrar_contexto()
    elif comando == "mode":
        novo = _NOMES_MODO_PERMISSAO.get(normalizar(argumento))
        if novo:
            MODO_PERMISSAO = novo
        print(c("  " + t(f"cli.modo.{MODO_PERMISSAO}"), Cor.VERDE if novo else Cor.CINZA))
        if not novo:
            print(c("  " + t("cli.modo_uso"), Cor.CINZA))
    elif comando == "undo":
        voltaram = desfazer_ultima_rodada()
        print(c("  " + (t("cli.desfeito", arquivos=", ".join(voltaram)) if voltaram else t("cli.nada_a_desfazer")),
                Cor.VERDE if voltaram else Cor.CINZA))
    elif comando == "init":
        criado = criar_agents_md()
        if criado:
            carregar_contexto_projeto()
        print(c("  " + (t("cli.agents_criado", arquivo=criado) if criado else t("cli.agents_existe")),
                Cor.VERDE if criado else Cor.CINZA))
    else:
        return False
    return True


def _linha_de_status():
    modelo = modelo_atual or (modelo_manual if modo_modelo == "MANUAL" else "auto")
    usados = estimar_tokens(conversa)
    partes = [str(modelo), t("cli.status_contexto", pct=min(100, int(100 * usados / max(1, contexto_ia()))))]
    if MODO_PERMISSAO != "perguntar":
        partes.append(t(f"cli.status_modo.{MODO_PERMISSAO}"))
    if CONTEXTO_PROJETO["caminho"]:
        partes.append("AGENTS.md")
    print(c("  " + " · ".join(partes), Cor.CINZA))


def _mostrar_plano():
    if PASSOS_DO_PLANO:
        print(c("\n  " + t("cli.plano_titulo"), Cor.NEGRITO + Cor.AMARELO))
        for i, passo in enumerate(PASSOS_DO_PLANO, 1):
            print(c(f"  {i:>2}. {passo}", Cor.AMARELO))
        PASSOS_DO_PLANO.clear()


def _executar_pedido_no_terminal(texto):
    iniciar_rodada()                         # 5.1: as edições deste pedido viram um ponto de retorno (/undo)
    if SESSAO_CLI["nota"]:
        texto, SESSAO_CLI["nota"] = SESSAO_CLI["nota"] + texto, ""
    try:
        with TRAVA_PEDIDO:
            return processar_mensagem(texto)
    finally:
        parar_girando()


class _SaidaComGiro:
    """Fica no lugar do sys.stdout durante o chat: apaga o símbolo de "trabalhando" antes de cada texto e troca o
    prefixo antigo "[openTARS] " pelo "⎿" dos passos. fileno/isatty continuam os do terminal (o input() usa o readline)."""

    _PREFIXOS = ("[openTARS] ", "[AUTO] ", "[IA] ")

    def __init__(self, real):
        self.real = real

    def write(self, texto):
        for p in self._PREFIXOS:
            texto = texto.replace(p, "  ⎿  ")
        with _girando.trava:
            _girando.apagar()
            return self.real.write(texto)

    def __getattr__(self, nome):
        return getattr(self.real, nome)


def _linha_visivel(texto):
    return len(re.sub(r"\033\[[0-9;]*m", "", texto))


def _painel(linhas):
    """Caixa de cantos redondos em volta das linhas (largura pelo texto visível, sem as cores)."""
    largura = max(_linha_visivel(l) for l in linhas) + 2
    print(c("╭" + "─" * largura + "╮", Cor.CINZA))
    for l in linhas:
        print(c("│", Cor.CINZA) + " " + l + " " * (largura - 1 - _linha_visivel(l)) + c("│", Cor.CINZA))
    print(c("╰" + "─" * largura + "╯", Cor.CINZA))


def _boas_vindas(pedidos):
    online = ollama_online()
    if modo_modelo == "MANUAL" and modelo_manual:
        modelo = t("term.modelo_fixo", modelo=modelo_manual)
    else:
        garg = gargantua_instalado() if online else None
        modelo = t("term.modelo_auto") + (f" · {garg.split('/')[-1]}" if garg else "")
    ollama = (c("●", Cor.VERDE) + " " + t("term.ollama_online", host=OLLAMA_HOST) if online
              else c("●", Cor.VERMELHO) + " " + t("term.ollama_offline", host=OLLAMA_HOST))
    linhas = [c("✻ ", Cor.MAGENTA) + c(t("term.bem_vindo"), Cor.NEGRITO), "",
              c("  " + t("chat.dica"), Cor.CINZA), "",
              c("  " + t("term.rotulo_ollama") + " ", Cor.CINZA) + ollama,
              c("  " + t("term.rotulo_modelo") + " ", Cor.CINZA) + modelo]
    if pedidos:
        linhas.append(c("  " + t("term.conversa_carregada", n=pedidos), Cor.CINZA))
    print()
    _painel(linhas)
    for aviso in avisos_de_ambiente():
        print(c(f"  ⚠ {aviso}", Cor.AMARELO))


TEM_READLINE = False


def _ligar_cores_do_windows():
    """O console clássico do Windows (cmd, PowerShell antigo) imprime as cores como lixo ("←[1m") até alguém ligar o modo
    de terminal virtual; o Windows Terminal já vem com ele ligado."""
    if os.name != "nt":
        return
    try:
        import ctypes
        kernel = ctypes.windll.kernel32
        for alca in (-11, -12):               # stdout e stderr
            h = kernel.GetStdHandle(alca)
            modo = ctypes.c_uint32()
            if h and kernel.GetConsoleMode(h, ctypes.byref(modo)):
                kernel.SetConsoleMode(h, modo.value | 0x0004)      # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:  # noqa: BLE001  (sem console: as cores só aparecem se a saída for um terminal)
        pass


def modo_chat_terminal(pedido_unico=None, retomar=None):
    """opentars --chat: conversa por texto no terminal. Sem pedido_unico, fica num laço (/ajuda, /sair); com ele,
    responde uma vez e sai. retomar (5.1): None = continua a última conversa (como na 5.0), "nova" = começa outra,
    "escolher" = lista as conversas salvas (--resume)."""
    global CLI_ATIVO
    global TEM_READLINE
    try:  # setas, histórico e edição da linha (ctrl+r busca nos pedidos anteriores)
        import readline  # noqa: F401
        TEM_READLINE = True
    except ImportError:       # Windows: sem readline, as marcas \001 \002 do prompt apareceriam na tela
        TEM_READLINE = False
    _ligar_cores_do_windows()
    CLI_ATIVO = True
    carregar_contexto_projeto()
    real = sys.stdout
    terminal = real.isatty() and not os.environ.get("NO_COLOR")
    if terminal:
        sys.stdout = _SaidaComGiro(real)
        _girando.ligar(real)
    try:
        return _conversar(pedido_unico, retomar)
    finally:
        _girando.desligar()
        sys.stdout = real
        CLI_ATIVO = False


def _conversar(pedido_unico, retomar=None):
    if pedido_unico is not None:
        for aviso in avisos_de_ambiente():
            print(c(f"  ⚠ {aviso}", Cor.AMARELO))
        resposta = None
        try:
            with _SessaoDescartavel():
                resposta = _executar_pedido_no_terminal(pedido_unico)
            _mostrar_plano()
        finally:
            if ollama_online():
                encerrar_todas_ias(so_do_tars=True)
        falhou = (not resposta or resposta == RESPOSTA_INTERROMPIDA
                  or resposta == t("aviso.ollama_offline", host=OLLAMA_HOST))
        return 1 if falhou else 0  # quem chama de um script usa o código de saída

    if retomar == "nova":
        limpar_sessao()
        pedidos = 0
    else:
        pedidos = iniciar_conversa()
    SESSAO_CLI["id"] = _id_da_conversa_carregada() if pedidos else _historico_cli().nova_id()
    _boas_vindas(pedidos)
    if CONTEXTO_PROJETO["caminho"]:
        print(c("  " + t("cli.agents_lido", arquivo=CONTEXTO_PROJETO["caminho"]), Cor.CINZA))
    if MODO_PERMISSAO != "perguntar":
        print(c("  " + t(f"cli.modo.{MODO_PERMISSAO}"), Cor.AMARELO))
    if retomar == "escolher":
        _escolher_conversa()
    interativo = sys.stdin.isatty()
    ctrl_c = 0
    try:
        while True:
            try:
                # \001..\002 avisam o readline que as cores não ocupam coluna (senão a edição da linha embaralha)
                ini, fim = ("\001", "\002") if TEM_READLINE else ("", "")
                linha = input("\n" + ini + Cor.NEGRITO + Cor.VERDE + fim + "❯ "
                              + ini + Cor.RESET + fim if interativo else "").strip()
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print()
                ctrl_c += 1
                if ctrl_c >= 2:
                    break
                print(c("  " + t("chat.ctrl_c"), Cor.CINZA))
                continue
            ctrl_c = 0
            if not linha:
                continue
            if _eh_comando(normalizar(linha), "cmd.sair") or normalizar(linha) in ("exit", "quit", "q"):
                break
            if _tratar_comando_do_chat(linha):
                continue
            _executar_pedido_no_terminal(linha)
            _mostrar_plano()
            _guardar_no_historico()
            if interativo:
                _linha_de_status()
    finally:
        if ollama_online():
            encerrar_todas_ias(so_do_tars=True)
        print(c("\n  " + t("term.ate_logo"), Cor.CINZA))
    return 0


LIMITE_STDIN_CHARS = 20000


def _stdin_tem_dado(espera=0.5):
    """Um pipe de verdade (echo x | opentars -p) já tem dado; um stdin aberto e mudo (agendador, outro programa) não:
    sem esta conferência o read() esperava para sempre."""
    try:
        import select
        return bool(select.select([sys.stdin], [], [], espera)[0])
    except (OSError, ValueError, TypeError):
        return True        # stdin trocado por um objeto em memória (testes): lê direto


class _SessaoDescartavel:
    """Pedido único (-p e --chat "pedido"): a conversa vai para um arquivo temporário, e a conversa salva da pessoa
    (a que a janela e o terminal retomam) não é sobrescrita."""

    def __enter__(self):
        global ARQUIVO_SESSOES
        self.arquivo, self.mensagens = ARQUIVO_SESSOES, list(conversa)
        ARQUIVO_SESSOES = Path(tempfile.mkdtemp(prefix="opentars-pedido-")) / "sessao.json"
        conversa[:] = [{"role": "system", "content": montar_system_prompt()}]
        return self

    def __exit__(self, *_):
        global ARQUIVO_SESSOES
        shutil.rmtree(ARQUIVO_SESSOES.parent, ignore_errors=True)
        ARQUIVO_SESSOES = self.arquivo
        conversa[:] = self.mensagens
        return False


def modo_print(pedido, formato="text", modelo=None):
    """opentars -p "pedido" (5.1): um pedido sem conversa interativa, para scripts. Texto: só a resposta no stdout (os
    passos vão para o stderr). JSON: um objeto com a resposta, o modelo, as ferramentas usadas e o tempo. O que vier
    pelo stdin (um pipe) entra no pedido como dado. Código de saída: 0 deu certo, 1 não."""
    global CLI_ATIVO, modo_modelo, modelo_manual
    entrada = ""
    if not sys.stdin.isatty() and _stdin_tem_dado():
        try:
            entrada = sys.stdin.read(LIMITE_STDIN_CHARS + 1)
        except (OSError, ValueError):
            entrada = ""
    if entrada.strip():
        corte = " (cut)" if len(entrada) > LIMITE_STDIN_CHARS else ""
        pedido = f"{pedido}\n\n<stdin{corte}>\n{entrada[:LIMITE_STDIN_CHARS]}\n</stdin>".strip()
    if not pedido.strip():
        print(t("cli.print_vazio"), file=sys.stderr)
        return 2
    if modelo:
        modo_modelo, modelo_manual = "MANUAL", modelo
    ferramentas = []
    usado = {"modelo": None}

    def ouvinte(tipo, dados):
        if tipo == "tarefa" and dados.get("modelo"):
            usado["modelo"] = dados["modelo"]
        elif tipo == "ferramenta":
            ferramentas.append({"nome": dados.get("nome"), "resumo": dados.get("resumo") or "", "sucesso": None})
        elif tipo == "ferramenta_fim" and ferramentas:
            ferramentas[-1]["sucesso"] = bool(dados.get("sucesso"))

    CLI_ATIVO = True
    carregar_contexto_projeto()
    inicio = time.time()
    real = sys.stdout
    definir_ouvinte_saida(ouvinte)
    resposta = None
    try:
        sys.stdout = sys.stderr             # o que o núcleo imprime (avisos, passos) não suja a saída do script
        iniciar_rodada()
        with TRAVA_PEDIDO, _SessaoDescartavel():
            resposta = processar_mensagem(pedido)
        usado["modelo"] = modelo_atual or usado["modelo"]
    finally:
        try:
            if ollama_online():
                encerrar_todas_ias(so_do_tars=True)      # ainda com o stdout no stderr: o aviso não suja a saída
        finally:
            sys.stdout = real
            definir_ouvinte_saida(None)
            CLI_ATIVO = False
    plano = list(PASSOS_DO_PLANO)
    PASSOS_DO_PLANO.clear()
    ok = bool(resposta) and resposta not in (RESPOSTA_INTERROMPIDA, t("aviso.ollama_offline", host=OLLAMA_HOST))
    if plano:     # modo plano: o que vale é a lista (a resposta do modelo pode falar como se tivesse feito)
        resposta = t("cli.plano_titulo") + "\n" + "\n".join(f"{i}. {p}" for i, p in enumerate(plano, 1))
    if formato == "json":
        print(json.dumps({"ok": ok, "resposta": resposta or "", "modelo": usado["modelo"], "ferramentas": ferramentas,
                          "plano": plano, "segundos": round(time.time() - inicio, 2)}, ensure_ascii=False))
    else:
        print(resposta or "")
    return 0 if ok else 1


def comando_cooper(instalar=True):
    """opentars --cooper: o Cooper foi descontinuado (18/10/2026); o Gargantua 2 enxerga a tela. Só avisa e diz como instalar."""
    print(c(t("cooper.descontinuado", comando=visao_lib.COMANDO_INSTALAR), Cor.AMARELO))
    return 0



# ------------------------------------------------------------
# Logo no terminal: o monólito do TARS (quatro colunas e a faixa verde, como o ícone) com o nome ao lado.
# Só aparece num terminal de verdade (não em pipe nem em script) e respeita NO_COLOR.
# ------------------------------------------------------------
_LOGO_COLUNAS = [
    "▄▄  ▄▄  ▄▄  ▄▄",
    "██  ██  ██  ██",
    None,                       # a faixa verde com os olhos
    "██  ██  ██  ██",
    "▀▀  ▀▀  ▀▀  ▀▀",
]
_LOGO_FAIXA = "\033[102;30m  ██      ██  \033[0m"
_LOGO_NOME = [
    ("┏━┓┏━┓┏━╸┏┓╻", "╺┳╸┏━┓┏━┓┏━┓"),
    ("┃ ┃┣━┛┣╸ ┃┗┫", " ┃ ┣━┫┣┳┛┗━┓"),
    ("┗━┛╹  ┗━╸╹ ╹", " ╹ ╹ ╹╹┗╸┗━┛"),
]


def _mostrar_logo():
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return
    _ligar_cores_do_windows()
    print()
    for i, coluna in enumerate(_LOGO_COLUNAS):
        linha = "   " + (_LOGO_FAIXA if coluna is None else c(coluna, Cor.NEGRITO))
        if 1 <= i <= 3:
            aberto, tars = _LOGO_NOME[i - 1]
            linha += "    " + c(aberto, Cor.NEGRITO) + c(tars, Cor.NEGRITO + Cor.VERDE)
        elif i == 4:
            linha += "    " + c(f"openTARS {VERSAO_EXIBIDA}", Cor.NEGRITO) + c(f" · {t('term.slogan')}", Cor.CINZA)
        print(linha)


def main():

    argumentos = sys.argv[1:]

    if any(a in ("--version", "-v") for a in argumentos):
        print(f"openTARS {VERSAO} ({VERSAO_EXIBIDA})")
        if murph.disponivel():
            print(f"helper Murph {murph.versao()}")
        # 4.0: a IA oficial (só consulta o Ollama, sem carregar nada)
        tag = gargantua_instalado() if ollama_online() else None
        if tag:
            print(f"Gargantua {VERSAO_GARGANTUA} ({tag})")
        else:
            print(t("gargantua.nao_instalado", modelo=MODELO_GARGANTUA))
        return

    if any(a in ("--help", "-h") for a in argumentos):
        for l in t("term.ajuda", versao=VERSAO_EXIBIDA).splitlines():
            titulo = l and not l.startswith(" ")
            print(c(l, Cor.NEGRITO) if titulo else c(l[:34], Cor.CIANO) + l[34:] if l.strip() else l)
        return

    idioma = _valor_do_argumento(argumentos, ("--idioma",))
    if idioma is not None:
        if idioma:
            codigo = i18n.definir_idioma(idioma)
            if not codigo:
                print(t("idioma.nao_encontrado", pedido=idioma, lista=", ".join(i18n.idiomas_disponiveis())))
                sys.exit(1)
        else:
            comando_idioma("")
            return

    if "--avaliar-classificador" in argumentos:
        sys.exit(avaliar_classificador())

    for flag in ("--explicar",):
        if flag in argumentos:
            pedido = " ".join(a for a in argumentos[argumentos.index(flag) + 1:] if not a.startswith("--"))
            sys.exit(explicar_escolha(pedido))

    # 5.2: prova leve e portátil (a mesma nos três sistemas), numa casa temporária
    if "--prova-dentro" in argumentos:
        import tars_prova
        sys.exit(tars_prova.rodar_dentro(sys.modules[__name__], json.loads(_valor_do_argumento(argumentos, ("--prova-dentro",)))))
    if "--prova" in argumentos:
        import tars_prova
        sys.exit(tars_prova.executar(sys.modules[__name__], argumentos))

    if any(a in ("--desinstalar", "--uninstall") for a in argumentos):
        import tars_desinstalar
        sys.exit(tars_desinstalar.executar(OLLAMA_HOST, t))

    if any(a in ("--diagnostico", "--autoteste") for a in argumentos):
        import tars_autoteste
        completo = "--autoteste" in argumentos
        sys.exit(tars_autoteste.executar(sys.modules[__name__], completo=completo))

    # 5.1: --probes é o serviço dos Probes (o atalho de início de sessão chama isto); --probes-uma-vez roda os devidos e sai
    if "--probes" in argumentos or "--probes-uma-vez" in argumentos:
        instalados = lambda: primeiro_uso.modelos_instalados(OLLAMA_HOST)
        if "--probes-uma-vez" in argumentos:
            print(t("probes.rodaram", n=probes_lib.uma_volta(probes_lib.Probes(), OLLAMA_HOST, instalados(), t=t)))
            sys.exit(0)
        # com tela, o serviço mostra o ícone com os avisos perto do relógio; sem tela (ou --sem-bandeja), só notificações
        if "--sem-bandeja" not in argumentos and os.environ.get("TARS_SEM_BANDEJA") != "1":
            try:
                from tars_qt import avisos as avisos_qt
                if avisos_qt.bandeja_possivel():
                    sys.exit(avisos_qt.rodar_bandeja(OLLAMA_HOST, instalados))
            except ImportError:
                pass
        sys.exit(probes_lib.servico(OLLAMA_HOST, instalados, t=t))

    # 5.1: --searxng prepara a pesquisa web local (Docker) e a liga
    if "--searxng" in argumentos:
        sys.exit(comando_searxng())

    # --cooper: o Cooper foi descontinuado, o comando só avisa
    if any(a in ("--cooper",) for a in argumentos):
        sys.exit(comando_cooper())

    # 5.1: modo de permissão (perguntar, plano, automático) e qual conversa retomar
    global MODO_PERMISSAO
    if any(a in ("--plan", "--plano") for a in argumentos):
        MODO_PERMISSAO = "plano"
    elif any(a in ("--auto", "--automatico") for a in argumentos):
        MODO_PERMISSAO = "automatico"
    retomar = "escolher" if any(a in ("--resume", "--retomar") for a in argumentos) else \
        "nova" if any(a in ("--new", "--nova") for a in argumentos) else None

    # 5.1: opentars -p "pedido" [--output-format json] [--model nome]: um pedido para scripts (stdin entra como dado)
    pedido_print = _valor_do_argumento(argumentos, ("-p", "--print"))
    if pedido_print is not None:
        formato = (_valor_do_argumento(argumentos, ("--output-format",)) or "text").lower()
        modelo = _valor_do_argumento(argumentos, ("--model", "--modelo")) or None
        sys.exit(modo_print(pedido_print, "json" if formato == "json" else "text", modelo))

    # Conversa no terminal (WSL, SSH, sem interface gráfica):
    #   opentars --chat                  conversa
    #   opentars --chat "que horas são"  um pedido só, e sai
    if any(a in ("--chat",) for a in argumentos):
        resto = [a for a in argumentos if a not in ("--chat",)]
        palavras, i = [], 0
        flags_com_valor = {"--idioma", "--atalho", "--atalho-acoes", "--model", "--modelo", "--output-format"}
        while i < len(resto):
            arg = resto[i]
            if arg in flags_com_valor:
                i += 2  # o valor da outra opção não é parte do pedido
                continue
            if arg.startswith("--"):
                i += 1
                continue
            palavras.append(arg)
            i += 1
        pedido = " ".join(palavras).strip()
        sys.exit(modo_chat_terminal(pedido_unico=pedido or None, retomar=retomar))

    # --voz: fica ouvindo "TARS" e responde falando (nucleo/voz.py)
    if "--voz" in argumentos:
        sys.exit(modo_voz_terminal())

    atalho_acoes = _valor_do_argumento(argumentos, ("--atalho-acoes",))
    if atalho_acoes is not None:
        import tars_atalho
        sys.exit(tars_atalho.comando_acoes(atalho_acoes))

    atalho = _valor_do_argumento(argumentos, ("--atalho",))
    if atalho is not None:
        import tars_atalho
        sys.exit(tars_atalho.comando(atalho))

    # Sem argumento: o logo e, num terminal de verdade, a conversa (opentars --chat). Em script ou pipe
    # (sem teclado ou sem tela de terminal) continua só conferindo o ambiente, como antes.
    _mostrar_logo()
    if sys.stdin.isatty() and sys.stdout.isatty():
        sys.exit(modo_chat_terminal(retomar=retomar))
    import tars_autoteste
    codigo = tars_autoteste.executar(sys.modules[__name__], completo=False)
    print()
    print(c(t("term.onde_conversar_sem_interface" if SEM_INTERFACE else "term.onde_conversar"), Cor.NEGRITO + Cor.VERDE))
    sys.exit(codigo)
