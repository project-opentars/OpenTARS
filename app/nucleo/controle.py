# openTARS — nucleo/controle.py
# Terminal, informações do PC, mouse (mira, arrasto, conferência) e teclado.
#
# Parte do núcleo: o tars.py executa este arquivo DENTRO do próprio
# namespace (ver _carregar_nucleo), então tudo aqui é tars.<nome> e as
# partes enxergam umas às outras sem import. Os testes que trocam
# tars.<função> por uma falsa continuam valendo pra todas as partes.
# flake8: noqa

# ============================================================
# OUTRAS FERRAMENTAS
# ============================================================

# Padrões de comando destrutivo o suficiente pra merecer uma
# confirmação antes de rodar — a IA (inclusive um modelo pequeno, que
# erra mais) manda qualquer comando pro terminal sem nenhuma trava
# hoje, e um comando mal interpretado nessa lista pode apagar dados ou
# derrubar o sistema sem chance de desfazer. Não é uma lista exaustiva
# de tudo que pode dar errado — é uma rede de segurança pros casos mais
# óbvios e mais caros.
_PADROES_COMANDO_PERIGOSO = [
    r"\brm\b.*\s-[a-zA-Z]*[rR]",  # rm -r/-rf/-fr/-R: apaga pastas inteiras
    r"\brm\b.*--recursive",
    r"\bfind\b.*\s-delete\b",
    r"\bfind\b.*-exec\s+(sudo\s+)?rm\b",    # find ... -exec rm
    r"\brm\b[^|;&\n]*[*?\[]",                  # rm com curinga (*.pdf): apaga vários de uma vez
    r"\bxargs\b.*\brm\b",
    r"\bshred\b",
    r"\bgit\b.*\b(reset\s+--hard|clean\s+-[a-z]*f)",
    r"\bdd\b.*\bif=",
    r"\bmkfs\b",
    r"\bwipefs\b",
    r"\bfdisk\b",
    r"\bparted\b",
    r">\s*/dev/(sd|nvme|hd)",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bpoweroff\b",
    r"\bhalt\b",
    r"\bchmod\b.*-R.*\s/(\s|$)",
    r"\bchown\b.*-R.*\s/(\s|$)",
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&?\s*\}\s*;\s*:",  # fork bomb
    r"\bmv\b[^|;&\n]*\s/dev/null\b",                      # mv algo /dev/null: some com o arquivo
    r"\bmv\b\s+(-\S+\s+)*(/|/\*|~|~/|\$HOME)\s",            # mv da raiz ou da pasta pessoal inteira pra outro lugar
]

_CONFIRMAR_COMANDOS_PERIGOSOS = (
    os.environ.get("TARS_SEM_CONFIRMACAO_PERIGOSOS", "0") != "1"
)

# Função (comando) -> bool que a interface gráfica registra pra
# perguntar numa janela. None = pergunta no terminal com input().
confirmar_comando_hook = None


# 5.0: rotina agendada em andamento (dict da agenda) ou None. Dentro de uma rotina NÃO há pergunta na tela: o comando
# arriscado só roda se a pessoa pré-aprovou essa categoria ao criar a rotina; senão a rotina PARA e avisa.
ROTINA_ATUAL = None
ROTINA_BLOQUEOU = []        # comandos que pararam a rotina atual

# 5.1: modo de permissão da conversa no terminal. "perguntar" (o padrão), "plano" (só descreve: nada que mude alguma coisa
# roda; ferramentas que só olham continuam) e "automatico" (edições de arquivo dentro da pasta do projeto sem perguntar).
# NENHUM modo dispensa a pergunta antes de apagar, enviar ou instalar.
MODOS_PERMISSAO = ("perguntar", "plano", "automatico")
MODO_PERMISSAO = "perguntar"
PASSOS_DO_PLANO = []          # o que o modo plano deixou de fazer, mostrado no fim do pedido
APROVADOS_NA_SESSAO = set()   # comandos (texto exato) liberados "sempre nesta sessão"; nunca os de apagar em massa


def _comando_e_perigoso(comando):
    comando = str(comando or "")
    if any(re.search(padrao, comando, re.IGNORECASE | re.DOTALL) for padrao in _PADROES_COMANDO_PERIGOSO):
        return True
    # 5.0: enviar/publicar e instalar/mudar o sistema também perguntam antes (apagar um arquivo nomeado, `rm a.txt`,
    # segue sem pergunta de propósito; apagar em massa já está acima/abaixo); numa rotina, qualquer ação dessas
    # categorias passa pela pré-aprovação.
    categorias = agenda_lib.categorias_do_comando(comando)
    if categorias & {"enviar", "instalar"}:
        return True
    return ROTINA_ATUAL is not None and bool(categorias)


def pode_aprovar_na_sessao(comando):
    """"Sempre nesta sessão" só vale para o que pergunta por ser envio ou instalação (git push, apt install...). O que bate
    com um padrão destrutivo (rm -rf, mkfs, dd...) pergunta toda vez."""
    comando = str(comando or "")
    return not any(re.search(p, comando, re.IGNORECASE | re.DOTALL) for p in _PADROES_COMANDO_PERIGOSO)


def _texto_visivel(comando, limite=600):
    """O comando inteiro como vai ser mostrado na confirmação: sem caracteres de controle (\\r, ESC) que escondem
    o resto, e sem cortar no meio (um ';' depois do 200º caractere ficava fora da tela)."""
    vis = "".join(ch if ch.isprintable() or ch == "\n" else f"\\x{ord(ch):02x}" for ch in str(comando))
    return vis if len(vis) <= limite else vis[:limite] + f" … (+{len(vis) - limite})"


_CLASSES_TERMINAL = ("terminal", "xterm", "konsole", "alacritty", "kitty", "tilix", "terminator", "urxvt", "rxvt",
                     "foot", "wezterm", "st-256color", "xfce4-terminal", "lxterminal", "qterminal", "guake", "yakuake",
                     "ptyxis", "console", "tmux")


def _janela_e_terminal(janela=None):
    """A janela (a pedida, ou a que está em foco) é um terminal? Texto digitado nela vira comando de shell."""
    try:
        todas = listar_janelas_x() or []
        if janela:
            alvo = encontrar_janela_por_nome(janela, todas) if "encontrar_janela_por_nome" in globals() else None
            achadas = [alvo] if alvo else []
        else:
            ativa = janela_ativa_x()
            achadas = [j for j in todas if j["id"] == ativa]
        return any(any(c in (j.get("classe", "") + " " + j.get("titulo", "")).lower() for c in _CLASSES_TERMINAL)
                   for j in achadas if j)
    except Exception:
        return False


def _barrar_texto_para_terminal(texto, janela=None):
    """Digitar `rm -rf ~` numa janela de terminal e apertar Enter é o mesmo que executar_terminal: passa pela
    mesma pergunta. Devolve um resultado de erro se a pessoa negou; None se pode seguir."""
    texto = str(texto or "")
    if not texto.strip() or not _comando_e_perigoso(texto) or not _janela_e_terminal(janela):
        return None
    if _confirmar_comando_perigoso(texto):
        return None
    return {"sucesso": False, "mensagem": "Typing cancelled: it would run a risky command in a terminal and the user did not confirm it."}


def _confirmar_comando_perigoso(comando):
    """Pede confirmação explícita no terminal antes de rodar um
    comando que bateu com um padrão destrutivo conhecido. Pode ser
    desligado (por conta e risco do usuário) com a variável de
    ambiente TARS_SEM_CONFIRMACAO_PERIGOSOS=1, útil pra rodar o TARS
    de forma não-interativa."""

    if not _CONFIRMAR_COMANDOS_PERIGOSOS:
        return True

    if ROTINA_ATUAL is not None:
        liberado = agenda_lib.autorizado(ROTINA_ATUAL, comando)
        LOG.info("rotina=%s comando_perigoso liberado=%s comando=%s", ROTINA_ATUAL.get("nome"), liberado,
                 _resumir_para_log(comando))
        if not liberado:
            ROTINA_BLOQUEOU.append(comando)
            cancelar_resposta()      # a rotina para aqui: não tenta outro jeito
        return liberado

    if comando in APROVADOS_NA_SESSAO:
        LOG.info("comando_perigoso liberado_na_sessao=True comando=%s", _resumir_para_log(comando))
        return True

    parar_girando()          # o símbolo de "trabalhando" não pode redesenhar por cima da pergunta
    imprimir_caixa(
        "⚠ " + t("perigo.titulo"),
        [_texto_visivel(comando), t("perigo.explicacao")],
        cor_titulo=Cor.VERMELHO,
    )

    if confirmar_comando_hook is not None:
        # Interface gráfica: não há terminal pra digitar "s", então ela
        # registra aqui uma função que pergunta numa caixa de diálogo.
        try:
            confirmado = bool(confirmar_comando_hook(comando))
        except Exception:
            confirmado = False
    elif threading.current_thread() is not threading.main_thread():
        # Pedido rodando fora da thread principal, sem janela: o input()
        # brigaria com o do prompt. Sem ninguém pra confirmar: não roda.
        print(c(t("perigo.sem_confirmacao_rotina"), Cor.AMARELO))
        confirmado = False
    else:
        sessao = pode_aprovar_na_sessao(comando)
        try:
            resposta = input(c(t("perigo.pergunta_sessao" if sessao else "perigo.pergunta") + " ", Cor.AMARELO)).strip()
        except (EOFError, OSError):
            resposta = ""
        confirmado = normalizar(resposta) in _vocab()["respostas_sim"]
        if sessao and normalizar(resposta) in _vocab()["respostas_sempre"]:
            APROVADOS_NA_SESSAO.add(comando)
            confirmado = True

    LOG.info(
        "comando_perigoso confirmado=%s comando=%s",
        confirmado,
        _resumir_para_log(comando),
    )

    return confirmado


def _env_filho(**extra):
    """Ambiente de um programa lançado por nós: a chave da nuvem (TARS_CHAVE_API) não vai junto, senão
    `env` no terminal a mostraria à IA — e ao que ela conversa."""
    e = {k: v for k, v in os.environ.items() if k != "TARS_CHAVE_API"}
    e.update(extra)
    return e


def executar_terminal(comando):

    if _comando_e_perigoso(comando) and not _confirmar_comando_perigoso(comando):
        return {
            "sucesso": False,
            "mensagem": (
                "Command cancelled: it matched a potentially destructive pattern "
                "and the user did not confirm it."
            ),
        }

    return _executar_terminal_de_fato(comando)


# Programas de tela cheia: precisam de um terminal de verdade. Rodando sem terminal (stdin em /dev/null, saída num
# arquivo) eles falham com "Error opening terminal" e o modelo concluía que o programa não estava instalado (16/10, htop).
_PROGRAMAS_DE_TELA = {"htop", "btop", "top", "atop", "nvtop", "iotop", "glances", "vim", "vi", "nvim", "nano", "emacs",
                      "less", "more", "man", "watch", "mc", "ranger", "nmtui", "alsamixer", "tmux", "screen", "cmatrix",
                      "ncdu", "bpytop", "nethogs", "iftop"}
_TERMINAIS = (("x-terminal-emulator", ["-e", "bash", "-c"]), ("gnome-terminal", ["--", "bash", "-c"]),
              ("kgx", ["--", "bash", "-c"]), ("konsole", ["-e", "bash", "-c"]), ("xfce4-terminal", ["-x", "bash", "-c"]),
              ("tilix", ["-e", "bash", "-c"]), ("xterm", ["-e", "bash", "-c"]))


def programa_de_tela(comando):
    """O nome do programa se o comando é um programa de tela cheia rodado sozinho (htop, vim arquivo, sudo nano x),
    ou None. Com pipe, redirecionamento, ';' ou '&&' não é: aí a saída vai para outro lugar. 'top -b' é texto."""
    if re.search(r"[|<>;&`$]", comando):
        return None
    try:
        partes = shlex.split(comando)
    except ValueError:
        return None
    while partes and (partes[0] in ("sudo", "env", "nice", "ionice") or re.match(r"^\w+=", partes[0]) or
                      (partes[0].startswith("-") and len(partes) > 1)):
        partes = partes[1:]
    if not partes:
        return None
    nome = os.path.basename(partes[0])
    if nome not in _PROGRAMAS_DE_TELA:
        return None
    if nome == "top" and any(a.startswith("-") and "b" in a for a in partes[1:]):
        return None
    return nome


def _abrir_em_janela_de_terminal(comando, nome):
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return {"sucesso": False, "mensagem": (
            f"{nome} is a full-screen terminal program and there is no graphical session to open a terminal window. "
            "Use a non-interactive command instead (for example 'top -bn1', 'free -h', 'ps aux --sort=-%mem | head').")}
    # fica aberta se der erro, para a pessoa ler; se o programa sair normalmente (q no htop), a janela fecha
    roteiro = f"{comando}; codigo=$?; [ $codigo -ne 0 ] && read -rp 'Enter: ' _; exit $codigo"
    for programa, argumentos in _TERMINAIS:
        if shutil.which(programa):
            try:
                subprocess.Popen([programa] + argumentos + [roteiro], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True, env=_env_filho())
            except OSError:
                continue
            return {"sucesso": True, "mensagem": (
                f"{nome} needs a terminal, so it was opened in a terminal window ({programa}) where the user can see and "
                "use it. Its screen is not captured here. Tell the user it is open in that window.")}
    return {"sucesso": False, "mensagem": (
        f"{nome} is a full-screen terminal program and no terminal emulator was found to open it. "
        "Use a non-interactive command instead (for example 'top -bn1' or 'free -h').")}


def _executar_terminal_de_fato(comando):

    # 5.2: fora do Linux, os comandos de bash que o Gargantua aprendeu rodam no mini-shell em Python (tars_shell), com a
    # saída no formato GNU do treino. No Windows o resto não roda; no macOS vai para o shell do sistema.
    if plataforma.sistema() != "linux":
        if shell_lib.suportado(comando):
            return shell_lib.executar(comando)
        if plataforma.sistema() == "windows":
            return {"sucesso": False, "mensagem": (
                "This command is not available on Windows in openTARS. Only these work: "
                + ", ".join(sorted(shell_lib.COMANDOS)) + " (with ~, quotes, &&, |, > and >>). "
                "Use one of them, or another tool (open_application, search_web).")}

    nome = programa_de_tela(comando)
    if nome:
        return _abrir_em_janela_de_terminal(comando, nome)

    # "firefox &" ou "nohup x &": o programa fica rodando e segurava a
    # saída aberta, e o openTARS esperava o tempo limite inteiro à toa.
    if re.search(r"&\s*$", comando.strip()) and not comando.strip().endswith("&&"):
        try:
            filho = subprocess.Popen(
                comando, shell=True, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True, env=_env_filho(),
            )
            threading.Thread(target=filho.wait, daemon=True).start()     # recolhe o filho quando ele terminar (sem zumbi)
            time.sleep(0.4)           # morreu na hora (programa que não existe)? então não foi iniciado
            codigo = filho.poll()
            if codigo not in (None, 0):
                return {"sucesso": False, "codigo": codigo,
                        "mensagem": f"The command exited right away with code {codigo}, so it was not started."}
            return {"sucesso": True, "mensagem": "Command started in the background."}
        except Exception as e:
            return {"sucesso": False, "mensagem": str(e)}

    try:
        # A saída vai pra ARQUIVOS e só o shell é esperado: um programa que o comando abriu (xdg-open, chrome,
        # code .) herda a saída e a segurava aberta até o tempo limite, que então o matava; e uma saída enorme
        # (`yes`) ficava toda na memória até o fim.
        with tempfile.TemporaryFile("w+b") as arq_saida, tempfile.TemporaryFile("w+b") as arq_erro:
            processo = subprocess.Popen(
                comando,
                shell=True,
                stdout=arq_saida,
                stderr=arq_erro,
                # Sem terminal pra digitar: sudo/apt que pedem senha ou "S/n"
                # falham na hora em vez de travar até o tempo limite.
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                env=_env_filho(DEBIAN_FRONTEND="noninteractive"),
            )
            limite = time.time() + TIMEOUT_TERMINAL_COMANDO
            while True:
                try:
                    processo.wait(timeout=0.25)
                    break
                except subprocess.TimeoutExpired:
                    if _cancelar.is_set() or time.time() > limite:
                        try:
                            os.killpg(processo.pid, 15)
                        except Exception:
                            processo.kill()
                        try:
                            processo.wait(timeout=3)
                        except subprocess.TimeoutExpired:  # ignorou o SIGTERM: SIGKILL
                            try:
                                os.killpg(processo.pid, 9)
                            except Exception:
                                processo.kill()
                            try:
                                processo.wait(timeout=3)
                            except subprocess.TimeoutExpired:
                                pass
                        if _cancelar.is_set():
                            return {"sucesso": False, "mensagem": "Command interrupted by the user."}
                        raise subprocess.TimeoutExpired(comando, TIMEOUT_TERMINAL_COMANDO)

            def _ponta(arq, limite_chars):
                tamanho = arq.seek(0, os.SEEK_END)
                arq.seek(max(0, tamanho - limite_chars * 4))     # só o final (até 4 bytes por caractere)
                return arq.read().decode("utf-8", errors="replace")[-limite_chars:]

            saida, erro_saida = _ponta(arq_saida, LIMITE_STDOUT_CHARS), _ponta(arq_erro, LIMITE_STDERR_CHARS)

        resultado = subprocess.CompletedProcess(comando, processo.returncode, saida, erro_saida)

        return {
            "sucesso": resultado.returncode == 0,
            "codigo": resultado.returncode,
            "stdout": resultado.stdout[-LIMITE_STDOUT_CHARS:],
            "stderr": resultado.stderr[-LIMITE_STDERR_CHARS:],
            "mensagem": (
                "Command finished."
                if resultado.returncode == 0
                else "Command finished with an error."
            ),
        }

    except subprocess.TimeoutExpired:

        return {
            "sucesso": False,
            "mensagem": (
                f"The command ran for more than {TIMEOUT_TERMINAL_COMANDO}s and was stopped. "
                "If it needs to run for a long time, suggest that the user runs it in a terminal."
            ),
        }

    except Exception as e:

        return {
            "sucesso": False,
            "mensagem": str(e),
        }


# O print enviado à IA é reduzido (ex: 2560x1440 -> 1280x720) e ela
# responde com coordenadas DESSA imagem. Sem converter de volta, o
# clique cairia no lugar errado (metade do caminho, numa tela 2x maior).
# Atualizado a cada take_screenshot; 1.0 enquanto não houver print.
# Com print de uma janela só, ox/oy guardam onde ela começa na tela.
_escala_print = {"x": 1.0, "y": 1.0, "ox": 0, "oy": 0, "largura": None, "altura": None, "definido": False}


def _escala_tela_inteira():
    """Quanto o print da tela inteira é reduzido (ex: 2.0 numa tela de
    2560px com prints de 1280px). Não depende de já ter tirado print."""
    try:
        largura = pyautogui.size()[0]
    except Exception:
        return 1.0
    return largura / min(largura, LARGURA_MAXIMA_SCREENSHOT) if largura else 1.0


def _usar_quadro_tela_inteira():
    """Volta as coordenadas de clique pro sistema do print de tela
    inteira. Chamado sempre que o openTARS informa posições nesse
    sistema (janelas abertas, tamanho da tela) ou quando a tela muda
    (abrir/focar janela): um recorte de janela antigo deixaria o clique
    com deslocamento errado."""
    escala = _escala_tela_inteira()
    _escala_print.update(x=escala, y=escala, ox=0, oy=0, largura=None, altura=None, definido=True)


def _para_tela(x, y):
    """Coordenadas do último print (as que a IA vê) -> pixels reais.
    Sem print nenhum ainda, vale o sistema do print de tela inteira (o
    tamanho de tela que o prompt informa à IA)."""
    if not _escala_print["definido"]:
        _usar_quadro_tela_inteira()
    return (
        int(round(_escala_print["ox"] + float(x) * _escala_print["x"])),
        int(round(_escala_print["oy"] + float(y) * _escala_print["y"])),
    )


def _para_print(x, y):
    """Pixels reais da tela -> coordenadas do último print."""
    if not _escala_print["definido"]:
        _usar_quadro_tela_inteira()
    return (
        int(round((x - _escala_print["ox"]) / _escala_print["x"])),
        int(round((y - _escala_print["oy"]) / _escala_print["y"])),
    )


# ------------------------------------------------------------
# 2.9.2: mouse preciso (mirar, conferir, arrastar) — lógica em tars_mouse.py
# ------------------------------------------------------------
PAUSA_HOVER_SEG = 0.12          # o app desenha o "hover" antes da captura de antes
ESPERA_DEPOIS_CLIQUE_SEG = 0.45
RAIO_VERIFICAR_CLIQUE = 140     # px reais em volta do clique
DURACAO_PASSO_ARRASTO_SEG = 0.018
PAUSA_SEGURAR_SEG = 0.18        # botão apertado antes de sair do lugar
PAUSA_SOLTAR_SEG = 0.3          # no destino, antes de soltar (o app mostra onde vai cair)


def _capturar_regiao(bbox=None):
    """Captura rápida pra comparar antes/depois (bbox em px reais), ou
    None se não der (Wayland, sem tela). Só serve pra conferir."""
    if SESSAO_GRAFICA == "wayland":
        return None
    try:
        from PIL import ImageGrab
        return ImageGrab.grab(bbox=bbox) if bbox else ImageGrab.grab()
    except Exception:
        return None


def _tamanho_real():
    try:
        largura, altura = pyautogui.size()
        return int(largura), int(altura)
    except Exception:
        return None


def _conferir(acao, x, y):
    """Faz a ação (clique, arrasto) e diz o que mudou na tela: "perto" do
    ponto, "longe" dele, "nada", ou None se não deu pra conferir."""
    tamanho = _tamanho_real()
    bbox = mouse.recorte_em_volta(int(x), int(y), RAIO_VERIFICAR_CLIQUE, *tamanho) if tamanho else None
    antes_perto = _capturar_regiao(bbox) if bbox else None
    antes_tudo = _capturar_regiao() if antes_perto is not None else None
    acao()
    if antes_perto is None:
        return None
    # Em vez de esperar o tempo todo, olha em 3 momentos e sai assim que a tela reagir.
    perto = None
    for fatia in (0.3, 0.3, 0.4):
        time.sleep(ESPERA_DEPOIS_CLIQUE_SEG * fatia)
        perto = mouse.mudanca(antes_perto, _capturar_regiao(bbox))
        if mouse.mudou(perto):
            break
    if mouse.mudou(perto):
        return "perto"
    if mouse.mudou(mouse.mudanca(antes_tudo, _capturar_regiao())):
        return "longe"
    return "nada" if perto is not None else None


def _ponto_por_acessibilidade(nome, janela):
    """Centro do elemento na tela pela árvore de acessibilidade (sem
    clicar), ou None. Só no X11 e com coordenadas de tela confiáveis."""
    if SESSAO_GRAFICA not in ("x11", "windows", "aqua") or acess.indisponivel():
        return None
    try:
        alvo, erro = _janela_acessivel(janela)
        if erro or not alvo or not acess.coordenadas_confiaveis(alvo):
            return None
        achado = acess.localizar(alvo, nome)
    except Exception:
        return None
    if not achado:
        return None
    rotulo, (x, y, largura, altura) = achado
    tamanho = _tamanho_real()
    cx, cy = x + largura // 2, y + altura // 2
    if tamanho and not (0 <= cx < tamanho[0] and 0 <= cy < tamanho[1]):
        return None
    return cx, cy, f"found {rotulo} through accessibility"


def _mirar_bruto(x=None, y=None, alvo=None, janela=None):
    """Onde clicar, em px REAIS da tela: (tx, ty, como) ou (None, None, erro).

    - só x/y: o ponto do último print, convertido;
    - x/y + alvo: a visão (o Gargantua 2) olha a tela e acha o alvo exato perto do ponto
      (sem ele, o ponto vai pro centro do elemento mais perto);
    - só alvo: acessibilidade e, por fim, a visão."""
    alvo = (alvo or "").strip()
    tem_ponto = x is not None and y is not None
    if tem_ponto and not alvo:
        tx, ty = _para_tela(x, y)
        return tx, ty, ""
    if not tem_ponto and not alvo:
        return None, None, "ERROR: pass x/y (pixels of the last screenshot) or 'target' (what to click)."

    if not tem_ponto:
        achado = _ponto_por_acessibilidade(alvo, janela)
        if achado:
            return achado

    try:
        if janela:
            capturada = _capturar_janela(janela)
            if not capturada:
                return None, None, f"No open window looks like '{janela}'. Use list_windows."
            imagem, ox, oy, janela_x = capturada
        else:
            imagem, ox, oy = _capturar_tela().convert("RGB"), 0, 0
    except Exception as e:
        if tem_ponto:
            tx, ty = _para_tela(x, y)
            return tx, ty, ""
        return None, None, f"ERROR capturing the screen: {e}"

    if CLIQUE_POR_VISAO:
        # A visão é a única a olhar a tela; com x/y dados pela IA, só vale perto deles
        perto = None
        if tem_ponto:
            tx0, ty0 = _para_tela(x, y)
            perto = (tx0 - ox, ty0 - oy)
        achado_cooper = mirar_com_visao(alvo, imagem, perto)
        if achado_cooper == "ausente" and not tem_ponto:
            return None, None, (f"Looked at the screen and '{alvo}' is not there. Check list_windows / "
                                "list_elements, or bring the right window to the front.")
        if achado_cooper and achado_cooper != "ausente":
            return ox + achado_cooper[0], oy + achado_cooper[1], achado_cooper[2]
        _avisar_falha_da_visao()
    if tem_ponto:
        tx, ty = _para_tela(x, y)
        lx, ly = tx - ox, ty - oy
        nx, ny = mouse.encaixar(imagem, lx, ly)
        como = "moved onto the nearest element" if (nx, ny) != (lx, ly) else ""
        return ox + nx, oy + ny, como
    if not visao_instalada():
        return None, None, (f"Could not find '{alvo}': it is not in the accessibility tree and no vision model is "
                            "installed (ollama pull ProjectOpenTARS/Gargantua-2). Pass x/y from a screenshot.")
    return None, None, (f"The vision model could not find '{alvo}' ({motivo_da_falha_da_visao()}). "
                        "Pass x/y from a screenshot.")


def _frase_conferencia(resultado):
    if resultado == "perto":
        return " The screen changed where it clicked."
    if resultado == "longe":
        return " The screen changed (not right at the click point)."
    if resultado == "nada":
        return (" WARNING: nothing changed on screen after the click, so it probably MISSED. Don't say "
                "it worked: call it again with target='<what you want to click>' (the vision model aims), "
                "or use click_element.")
    return ""


MARGEM_QUINA_PX = 3  # o pyautogui trava tudo se o ponteiro encostar numa das 4 quinas (fail-safe)


def _longe_da_quina(px, py):
    """Mantém o ponto a MARGEM_QUINA_PX da borda: coordenada inventada ou fora da tela
    mandava o ponteiro pra uma quina, e dali em diante TODO comando de mouse/teclado
    falhava com FailSafeException até alguém mexer o mouse."""
    tamanho = _tamanho_real()
    if not tamanho or px is None or py is None:
        return px, py
    m = MARGEM_QUINA_PX
    return max(m, min(tamanho[0] - 1 - m, px)), max(m, min(tamanho[1] - 1 - m, py))


def _mirar(x=None, y=None, alvo=None, janela=None):
    """_mirar_bruto com o ponto sempre dentro da tela e longe das quinas."""
    tx, ty, como = _mirar_bruto(x, y, alvo, janela)
    if tx is not None:
        tx, ty = _longe_da_quina(tx, ty)
    return tx, ty, como


def clicar_mouse(botao="left", x=None, y=None, alvo=None, janela=None, duplo=False):
    """Handler de click_mouse (clicks=2: duplo clique): mira (tars_mouse), clica
    e confere se a tela mudou."""
    botao = str(botao or "left").strip().lower().replace("-click", "").replace("_click", "")
    botao = botao if botao in ("left", "right", "middle") else "left"
    try:
        if x is None and y is None and not (alvo or "").strip():
            if duplo:
                pyautogui.doubleClick()
            else:
                pyautogui.click(button=botao)
            return {"sucesso": True, "mensagem": ("Double click done." if duplo else
                                                  f"Clicked the {botao} mouse button.")}
        tx, ty, como = _mirar(x, y, alvo, janela)
        if tx is None:
            return {"sucesso": False, "mensagem": como}
        pyautogui.moveTo(tx, ty, duration=DURACAO_MOVER_MOUSE_SEG)
        time.sleep(PAUSA_HOVER_SEG)
        if duplo:
            conferido = _conferir(lambda: pyautogui.doubleClick(x=tx, y=ty), tx, ty)
        else:
            conferido = _conferir(lambda: pyautogui.click(x=tx, y=ty, button=botao), tx, ty)
        px, py = _para_print(tx, ty)
        o_que = "Double-clicked" if duplo else f"Clicked the {botao} mouse button"
        mensagem = f"{o_que} at ({px}, {py})" + (f": {como}" if como else "") + "."
        resultado = {"sucesso": True, "mensagem": mensagem + _frase_conferencia(conferido), "x": px, "y": py}
        if conferido == "nada":
            resultado["sem_efeito"] = True
        return resultado
    except Exception as e:
        return {"sucesso": False, "mensagem": str(e)}


def _ponto_do_arrasto(x, y, elemento, janela, lugar=None):
    """(tx, ty, como) em px reais pra origem/destino de um arrasto."""
    if lugar:
        tamanho = _tamanho_real()
        ancorado = mouse.ancora(lugar, *tamanho) if tamanho else None
        if ancorado:
            return ancorado[0], ancorado[1], f"'{lugar}' of the screen"
        elemento = elemento or lugar  # não é um lugar da tela: é um elemento
    elemento = (elemento or "").strip()
    if elemento and (x is None or y is None):
        achado = _ponto_por_acessibilidade(elemento, janela)
        if achado:
            return achado
    return _mirar(x, y, elemento or None, janela)


def _arrastar_real(x0, y0, x1, y1, botao):
    pyautogui.moveTo(x0, y0, duration=DURACAO_MOVER_MOUSE_SEG)
    time.sleep(PAUSA_HOVER_SEG)
    pyautogui.mouseDown(x=x0, y=y0, button=botao)
    try:
        time.sleep(PAUSA_SEGURAR_SEG)
        for i, (px, py) in enumerate(mouse.caminho(x0, y0, x1, y1)):
            pyautogui.moveTo(px, py)
            # os 3 primeiros (o "empurrão") devagar: aí o app vê um arrasto
            time.sleep(DURACAO_PASSO_ARRASTO_SEG * (4 if i < 3 else 1))
        time.sleep(PAUSA_SOLTAR_SEG)
    finally:
        pyautogui.mouseUp(x=x1, y=y1, button=botao)


def _janela_do_arrasto(a):
    """Nome da janela, se o que se quer arrastar é a PRÓPRIA janela ("a
    janela do openTARS", a barra de título, ou só o nome de um app aberto,
    sem ponto de origem), senão None. Arrastar uma aba ou um arquivo DENTRO
    da janela continua sendo arrasto de mouse."""
    elemento = (a.get("from_element") or "").strip()
    janela = (a.get("window") or "").strip()
    if a.get("to_element"):
        return None  # soltar em cima de algo: arrasto de verdade
    if elemento and mouse.fala_de_janela(elemento):
        return mouse.sem_palavras_de_janela(elemento) or janela or None
    if a.get("from_x") is not None and a.get("from_y") is not None:
        return None
    if elemento and set(normalizar(elemento).split()) & mouse._PALAVRAS_ABA:
        return None
    if elemento and (not janela or normalizar(janela) == normalizar(elemento)):
        achada = encontrar_janela_por_nome(elemento)
        # o nome é de um app aberto (classe/binário), não só um texto do título
        if achada and _pontuar_janela(achada, _termos_para_janela(elemento)) >= 2:
            return elemento
    if not elemento and janela:
        return janela
    return None


def arrastar_mouse(a):
    """Handler de drag_mouse: segura o botão na origem, leva até o destino
    como uma pessoa faria e solta. Confere se a tela mudou."""
    if ERRO_PYAUTOGUI:
        return {"sucesso": False, "mensagem": f"Cannot control the mouse: {ERRO_PYAUTOGUI}."}
    janela_inteira = _janela_do_arrasto(a)
    if janela_inteira and (a.get("to") or (a.get("to_x") is not None and a.get("to_y") is not None)):
        # "arraste a janela do openTARS pro topo esquerdo": mover janela é com
        # o gerenciador de janelas (antes o mouse ia no TEXTO "openTARS").
        return mover_janela(janela_inteira, lugar=a.get("to"), x=a.get("to_x"), y=a.get("to_y"))
    janela = a.get("window") or None
    botao = a.get("button") if a.get("button") in ("left", "right", "middle") else "left"
    tem_origem = a.get("from_element") or (a.get("from_x") is not None and a.get("from_y") is not None)
    tem_destino = a.get("to") or a.get("to_element") or (a.get("to_x") is not None and a.get("to_y") is not None)
    if not tem_destino:
        return {"sucesso": False, "mensagem": (
            "ERROR: say where to drag it: to='top-left' (or 'right', 'center', 'bottom-right'...), "
            "to_element='<what to drop it on>', or to_x/to_y (pixels of the last screenshot).")}
    try:
        if tem_origem:
            x0, y0, como0 = _ponto_do_arrasto(a.get("from_x"), a.get("from_y"), a.get("from_element"), janela)
            if x0 is None:
                return {"sucesso": False, "mensagem": f"Could not find what to drag: {como0}"}
        else:
            x0, y0 = pyautogui.position()
            como0 = "from where the mouse is"
        # O destino fica fora da janela de origem muitas vezes ("pro topo
        # esquerdo da tela"): só procura DENTRO da janela se for um elemento.
        x1, y1, como1 = _ponto_do_arrasto(a.get("to_x"), a.get("to_y"), a.get("to_element"),
                                          janela, lugar=a.get("to"))
        if x1 is None:
            return {"sucesso": False, "mensagem": f"Could not find where to drop it: {como1}"}
        if abs(x1 - x0) + abs(y1 - y0) < 3:
            return {"sucesso": False, "mensagem": "ERROR: the start and the end of the drag are the same point."}
        conferido = _conferir(lambda: _arrastar_real(x0, y0, x1, y1, botao), x1, y1)
    except Exception as e:
        return {"sucesso": False, "mensagem": f"ERROR dragging: {e}"}
    p0, p1 = _para_print(x0, y0), _para_print(x1, y1)
    detalhes = "; ".join(x for x in (f"start: {como0}" if como0 else "", f"end: {como1}" if como1 else "") if x)
    mensagem = (f"Dragged with the {botao} button held from ({p0[0]}, {p0[1]}) to ({p1[0]}, {p1[1]})"
                + (f" ({detalhes})" if detalhes else "") + ".")
    if conferido == "nada":
        # Pode ser legítimo (a aba já era a primeira), por isso não é erro;
        # mas quase sempre quer dizer que não pegou o item: a IA é avisada.
        return {"sucesso": True, "sem_efeito": True, "mensagem": mensagem + (
            " WARNING: NOTHING changed on screen, so it probably did not grab the item. Unless it was "
            "already there, take a screenshot and call drag_mouse again with from_element='<what to "
            "drag>' (openTARS finds it) or corrected from_x/from_y. Don't say it worked without checking.")}
    return {"sucesso": True, "mensagem": "SUCCESS: " + mensagem + (
        " The screen changed." if conferido in ("perto", "longe") else "")}


def scroll_mouse(valor, x=None, y=None):
    try:
        if x is not None and y is not None:
            pyautogui.moveTo(*_para_tela(x, y), duration=DURACAO_MOVER_PARA_SCROLL_SEG)

        pyautogui.scroll(int(valor))
        return {"sucesso": True, "mensagem": f"Scrolled {valor}."}
    except Exception as e:
        return {"sucesso": False, "mensagem": str(e)}


def _definir_clipboard(texto):
    """Coloca texto na área de transferência (tars_plataforma). Usado pra digitar texto multilíngue: o
    pyautogui simula teclas físicas e não digita de forma confiável
    acentos, cedilha ou alfabetos fora do layout US (japonês, árabe,
    cirílico etc.); colar via clipboard funciona pra qualquer idioma
    independente do layout de teclado."""
    try:
        plataforma.escrever_area_de_transferencia(texto)
        return True
    except OSError:
        return False


def digitar_texto(texto, _ja_confirmado=False):
    if not _ja_confirmado:
        barrado = _barrar_texto_para_terminal(texto)
        if barrado:
            return barrado
    try:
        if texto.isascii():
            # Caminho rápido de sempre — nenhuma mudança de
            # comportamento ou desempenho pro caso comum (ASCII).
            pyautogui.write(texto, interval=INTERVALO_DIGITACAO_SEG)
            return {"sucesso": True, "mensagem": "Text typed."}

        # Texto com acentos/outros idiomas: cola via clipboard em vez
        # de tecla-a-tecla, o que também é mais rápido pra textos
        # longos além de mais confiável.
        if _definir_clipboard(texto):
            pyautogui.hotkey(plataforma.tecla_comando(), "v")
            return {"sucesso": True, "mensagem": "Text typed (pasted through the clipboard)."}

        # Sem xclip/xsel disponível: melhor esforço mesmo assim.
        pyautogui.write(texto, interval=INTERVALO_DIGITACAO_SEG)
        return {
            "sucesso": True,
            "mensagem": (
                "Text typed, but xclip/xsel is not installed: special characters "
                "may not have come out right."
            ),
        }

    except Exception as e:
        return {"sucesso": False, "mensagem": str(e)}


_APELIDOS_TECLAS = {
    "page down": "pagedown", "page up": "pageup", "windows": "win", "super": "win", "meta": "win",
    "arrowdown": "down", "arrowup": "up", "arrowleft": "left", "arrowright": "right",
    "arrow down": "down", "arrow up": "up", "arrow left": "left", "arrow right": "right",
    "control": "ctrl", "del": "delete", "return": "enter", "escape": "esc", "spacebar": "space",
}


def _tecla_valida(tecla):
    """Nome de tecla que o pyautogui conhece; ValueError se não existir (o pyautogui,
    sozinho, ignora o nome desconhecido e a ferramenta dizia que apertou)."""
    t_ = _APELIDOS_TECLAS.get(str(tecla or "").strip().lower(), str(tecla or "").strip().lower())
    ok = getattr(pyautogui, "isValidKey", None)
    if not t_ or (ok and not ok(t_)):
        raise ValueError(f"unknown key '{tecla}'. Examples: enter, esc, tab, up, down, pagedown, f5, ctrl, alt, shift, win.")
    return t_


def pressionar_tecla(tecla):
    try:
        if "+" in str(tecla) and len(str(tecla).strip()) > 1:
            return atalho_teclado(str(tecla))  # "ctrl+s" não é uma tecla: é um atalho
        pyautogui.press(_tecla_valida(tecla))
        return {"sucesso": True, "mensagem": f"Pressed '{tecla}'."}
    except Exception as e:
        return {"sucesso": False, "mensagem": str(e)}


def atalho_teclado(teclas):
    try:

        if isinstance(teclas, str):
            teclas = [x.strip() for x in teclas.split("+")]

        if not teclas:
            raise ValueError("no keys given")
        pyautogui.hotkey(*[_tecla_valida(k) for k in teclas])

        return {
            "sucesso": True,
            "mensagem": f"Pressed {'+'.join(teclas)}.",
        }

    except Exception as e:
        return {"sucesso": False, "mensagem": str(e)}
