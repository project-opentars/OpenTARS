# openTARS — nucleo/registro.py
# Log de auditoria, estado global, utilidades de texto e a saída pro usuário (terminal ou janela).
#
# Parte do núcleo: o tars.py executa este arquivo DENTRO do próprio
# namespace (ver _carregar_nucleo), então tudo aqui é tars.<nome> e as
# partes enxergam umas às outras sem import. Os testes que trocam
# tars.<função> por uma falsa continuam valendo pra todas as partes.
# flake8: noqa

# ============================================================
# LOG DE AUDITORIA
# ============================================================

# Toda ferramenta executada (abrir app, rodar comando, fechar
# processo etc.) fica registrada aqui — nome, argumentos e resultado,
# com timestamp. É o que permite, depois de qualquer coisa inesperada
# acontecer, entender o que foi executado e por quê, em vez de
# depender só da memória de quem estava olhando o terminal na hora.
DIRETORIO_LOG = Path(os.environ.get("TARS_DIR_LOG", str(Path.home() / ".tars_log")))
ARQUIVO_LOG = DIRETORIO_LOG / "tars.log"
TAMANHO_MAX_LOG_BYTES = 2 * 1024 * 1024
BACKUPS_LOG = 3
LIMITE_LOG_CAMPO_CHARS = 300


def _configurar_log():
    logger = logging.getLogger("tars")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    try:
        DIRETORIO_LOG.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(DIRETORIO_LOG, 0o700)       # o log guarda comandos e caminhos: só o dono lê
        except OSError:
            pass

        handler = RotatingFileHandler(
            ARQUIVO_LOG,
            maxBytes=TAMANHO_MAX_LOG_BYTES,
            backupCount=BACKUPS_LOG,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        logger.addHandler(handler)

    except Exception as e:
        # Auditoria é best-effort: se não der pra escrever o log (disco
        # cheio, permissão negada etc.), o TARS continua funcionando
        # normalmente sem ela, só avisa uma vez. Print puro aqui (sem
        # o helper de cor c()) de propósito: essa função roda antes
        # dele existir na ordem de definição do módulo.
        print(f"[openTARS] {t('msg.log_desativado', erro=e)}")
        logger.addHandler(logging.NullHandler())

    return logger


LOG = _configurar_log()


def _resumir_para_log(valor):
    """Converte um valor qualquer (geralmente os argumentos de uma
    ferramenta) numa string curta o bastante pro log — sem isso, um
    texto digitado enorme ou um resultado de comando de terminal
    grande inflaria o arquivo de log rapidamente."""

    try:
        if isinstance(valor, dict) and any(k in valor for k in ("text", "texto", "password", "senha")):
            # o que a pessoa digita pode ser senha: o log guarda só o tamanho
            valor = {k: (f"<{len(str(v))} chars>" if k in ("text", "texto", "password", "senha") else v)
                     for k, v in valor.items()}
        texto = json.dumps(valor, ensure_ascii=False)
    except Exception:
        texto = str(valor)

    if len(texto) > LIMITE_LOG_CAMPO_CHARS:
        texto = texto[:LIMITE_LOG_CAMPO_CHARS] + "…"

    return texto


# ============================================================
# ESTADO
# ============================================================

modo_modelo = "AUTO"
modelo_manual = None
modelo_atual = None
modelos_do_tars = set()   # tudo que o openTARS carregou nesta sessão: ao fechar, só isso é descarregado

sessoes = {}

lock_modelo = threading.Lock()

# Sessão HTTP única e reutilizada: evita reabrir conexão TCP/TLS
# a cada chamada ao Ollama (isso importa bastante no loop de tools,
# que pode chamar o Ollama várias vezes por turno).
_SESSION = requests.Session()

# Cache de aplicativos instalados (desktop entries e flatpak).
_cache_desktop = {"dados": None, "ts": 0.0}
_cache_flatpak = {"dados": None, "ts": 0.0}


# ============================================================
# UTILIDADES
# ============================================================

def _tabela_sem_acentos():
    """Letras latinas acentuadas -> sem acento (á->a, ñ->n, ö->o, ß->ss...),
    montada uma vez só: str.translate com ela é bem mais rápido que
    decompor Unicode a cada chamada, e normalizar() roda muito (uma vez
    por processo do sistema, por app instalado, por palavra-chave...)."""
    tabela = {}
    for codigo in range(0xC0, 0x250):
        letra = chr(codigo)
        base = "".join(x for x in unicodedata.normalize("NFKD", letra) if not unicodedata.combining(x))
        if base != letra and base.isascii() and base.isalpha():
            tabela[codigo] = base.lower()
    tabela.update({ord("ß"): "ss", ord("æ"): "ae", ord("œ"): "oe", ord("ø"): "o", ord("đ"): "d", ord("ł"): "l", ord("ı"): "i"})
    return tabela


_TABELA_NORMALIZACAO = _tabela_sem_acentos()

# Separa palavras (Unicode: funciona com qualquer alfabeto).
_RE_TOKENS = re.compile(r"[\W_]+")


def normalizar(texto):
    return texto.lower().strip().translate(_TABELA_NORMALIZACAO)


_RE_SEPARADORES_NOME = re.compile(r"[-_.:/]+")


def normalizar_nome_app(texto):
    """Pra comparar nomes de apps: "Counter-Strike 2" vira "counter strike 2",
    e bate com o "counter strike" que o usuário escreveu."""
    return re.sub(r"\s+", " ", _RE_SEPARADORES_NOME.sub(" ", normalizar(texto or ""))).strip()


# ------------------------------------------------------------
# Vocabulário dos idiomas: palavras-chave, comandos, verbos de busca...
# Montado uma vez a partir dos arquivos de idioma (já normalizado e em
# conjuntos, pra busca instantânea) e refeito só quando o idioma muda.
# ------------------------------------------------------------

_CHAVES_COMANDOS = (
    "cmd.modelos", "cmd.modelo", "cmd.encerrar", "cmd.limpar", "cmd.idioma",
    "cmd.auto", "cmd.auto_argumento", "cmd.sair",
)

_vocab_atual = None


def _preparar_expressoes(expressoes):
    """(palavras soltas, trechos de várias palavras), normalizados e já
    quebrados em palavras como o pedido é: "trouve-moi" vira o trecho
    " trouve moi " e "à l'écran", " a l ecran ". Trecho é procurado com
    espaço dos dois lados (palavras inteiras): "the screen" não bate em
    "the screenshots"."""
    palavras, trechos = set(), []
    for expr in expressoes:
        partes = [x for x in _RE_TOKENS.split(normalizar(str(expr))) if x]
        if len(partes) > 1:
            trechos.append(" " + " ".join(partes) + " ")
        elif partes:
            palavras.add(partes[0])
    return frozenset(palavras), tuple(dict.fromkeys(trechos))


def _normalizados(itens):
    return tuple(dict.fromkeys(n for n in (normalizar(str(x)) for x in itens) if n))


# Palavras das listas de abrir/fechar/buscar que não são verbos ("feche a
# ABA do youtube"): não contam como uma etapa do pedido.
_NAO_SAO_VERBOS = frozenset({"aba", "abas", "tab", "tabs", "pestana", "pestanas", "onglet", "onglets",
                             "reiter", "tabs", "site", "pagina", "page", "website"})


def _montar_vocabulario():
    entrada = i18n.idiomas_de_entrada()
    v = {
        "detectar": {
            grupo: _preparar_expressoes(list(neutras) + i18n.juntar(f"detectar.{grupo}", entrada))
            for grupo, neutras in _PALAVRAS_NEUTRAS.items()
        },
        "busca_verbos": frozenset(_normalizados(i18n.juntar("busca.verbos", entrada))),
        # Verbos de ação (pra achar pedidos com várias etapas): os da lista
        # própria + os das palavras-chave de abrir/fechar/buscar.
        "verbos_acao": frozenset(
            palavra for frase in _normalizados(
                i18n.juntar("detectar.verbos", entrada) + i18n.juntar("detectar.abrir", entrada)
                + i18n.juntar("detectar.fechar", entrada) + i18n.juntar("detectar.busca", entrada)
                + i18n.juntar("busca.verbos", entrada))
            for palavra in frase.split()[:1]
            if palavra not in _NAO_SAO_VERBOS
        ),
        "busca_conectores": _normalizados(i18n.juntar("busca.conectores", entrada)),
        "busca_preposicoes": _normalizados(i18n.juntar("busca.preposicoes", entrada)),
        "navegadores": frozenset(_MARCAS_NAVEGADORES) | frozenset(_normalizados(i18n.juntar("palavras.navegador", entrada))),
        # Comandos são explícitos: valem em qualquer idioma.
        "comandos": {chave: frozenset(_normalizados(i18n.em_todos(chave))) for chave in _CHAVES_COMANDOS},
        "respostas_sim": frozenset(_normalizados(i18n.em_todos("cmd.sim"))),
        "respostas_sempre": frozenset(_normalizados(i18n.em_todos("cmd.sempre"))),     # 5.1: "sempre nesta sessão"
        "modelo_ignorar": frozenset(_normalizados(i18n.em_todos("modelo.ignorar"))),
    }
    superlativos = {}
    for chave, resolvedor in _CRITERIOS_MODELO.items():
        for frase in _normalizados(i18n.em_todos(chave)):
            superlativos.setdefault(frase, resolvedor)
    v["superlativos"] = superlativos

    # Nomes traduzidos de apps: Name[pt_BR]= no .desktop e catálogos gettext.
    grupos = [tuple(i18n.juntar("_locale", [codigo]) or [codigo]) for codigo in entrada]
    for local in i18n.locales_do_sistema():
        grupos.append((local, local.split("_")[0]) if "_" in local else (local,))
    grupos = tuple(dict.fromkeys(grupos))
    v["grupos_locale"] = grupos
    v["sufixos_desktop"] = tuple(dict.fromkeys([""] + [f"[{x}]" for grupo in grupos for x in grupo]))
    return v


def _vocab():
    global _vocab_atual
    v = _vocab_atual
    if v is None:
        v = _vocab_atual = _montar_vocabulario()
    return v


def _ao_mudar_idioma(_codigo):
    """Idioma novo: palavras-chave novas e nomes de apps relidos."""
    global _vocab_atual
    _vocab_atual = None
    _cache_arquivos_desktop.clear()
    _cache_desktop["dados"] = None


i18n.ao_mudar_idioma(_ao_mudar_idioma)


# ------------------------------------------------------------
# Interface: cores ANSI (funcionam no terminal do Zorin/qualquer
# terminal Linux moderno). Usadas só no que é impresso pro humano —
# nunca dentro do conteúdo de "mensagem" devolvido nas ferramentas,
# porque esse texto vai para o JSON que a IA lê.
# ------------------------------------------------------------

class Cor:
    RESET = "\033[0m"
    NEGRITO = "\033[1m"
    CINZA = "\033[90m"
    VERMELHO = "\033[31m"
    VERDE = "\033[32m"
    AMARELO = "\033[33m"
    AZUL = "\033[34m"
    MAGENTA = "\033[35m"
    CIANO = "\033[36m"
    ITALICO = "\033[3m"


def c(texto, cor):
    return f"{cor}{texto}{Cor.RESET}"


def imprimir_caixa(titulo, linhas, cor_titulo=Cor.CIANO):
    largura = (
        max(LARGURA_MINIMA_CAIXA, len(titulo) + 4, *(len(l) + 4 for l in linhas))
        if linhas
        else max(LARGURA_MINIMA_CAIXA, len(titulo) + 4)
    )

    print()
    print(c("╭" + "─" * largura + "╮", Cor.CINZA))
    print(c("│ ", Cor.CINZA) + c(titulo.ljust(largura - 2), cor_titulo) + c(" │", Cor.CINZA))

    for linha in linhas:
        print(c("│ ", Cor.CINZA) + linha.ljust(largura - 2)[:largura - 2] + c(" │", Cor.CINZA))

    print(c("╰" + "─" * largura + "╯", Cor.CINZA))


def executar_subprocesso(cmd, timeout=TIMEOUT_SUBPROCESSO_PADRAO):
    try:
        resultado = subprocess.run(
            cmd,
            capture_output=True,
            text=True, encoding="utf-8", errors="replace",    # nomes em latin-1 não podem virar "falhou"
            timeout=timeout,
        )

        return {
            "codigo": resultado.returncode,
            "stdout": resultado.stdout.strip(),
            "stderr": resultado.stderr.strip(),
        }

    except subprocess.TimeoutExpired:
        return {
            "codigo": -1,
            "stdout": "",
            "stderr": "timeout",
        }

    except Exception as e:
        return {
            "codigo": -1,
            "stdout": "",
            "stderr": str(e),
        }


# ============================================================
# SAÍDA PRO USUÁRIO (terminal ou janela)
# ============================================================
#
# O que o openTARS mostra enquanto trabalha (ferramenta rodando, modelo
# carregando, raciocínio e resposta chegando) sai como EVENTO. No
# terminal vira texto colorido; a janela registra um ouvinte e recebe o
# evento já estruturado, em vez de ler e interpretar o texto impresso
# (que muda com o idioma escolhido).

_ouvinte_saida = None


def definir_ouvinte_saida(funcao):
    """A interface gráfica registra aqui uma função(tipo, dados). None
    volta a imprimir no terminal."""
    global _ouvinte_saida
    _ouvinte_saida = funcao


def emitir(tipo, **dados):
    ouvinte = _ouvinte_saida
    if ouvinte is not None:
        try:
            ouvinte(tipo, dados)
        except Exception:
            pass
        return
    renderizar = _TERMINAL.get(tipo)
    if renderizar is not None:
        renderizar(dados)


def nome_ferramenta(nome):
    """"open_application" -> "abrindo app" (no idioma escolhido)."""
    chave = f"ferramenta.{nome}"
    texto = t(chave)
    return nome if texto == chave else texto


def nome_tarefa(tarefa):
    chave = f"tarefa.{tarefa}"
    texto = t(chave)
    return tarefa if texto == chave else texto


def _segundos(valor):
    return f"{valor:.1f}"


# ------------------------------------------------------------
# Terminal no estilo das CLIs de IA: "●" abre cada passo, "⎿" pendura o resultado embaixo, e um símbolo girando
# mostra que o openTARS está trabalhando. Só vale sem janela (a janela recebe os eventos, não este texto).
# ------------------------------------------------------------
_RECUO = "  "
_PENDURA = "  ⎿  "


class _Girando:
    """O símbolo de "trabalhando" na última linha do terminal. Ele só existe num terminal de verdade (ligar() chamado
    pelo chat), redesenha a linha a cada 90 ms e some antes de qualquer outro texto (_SaidaComGiro)."""

    QUADROS = "·✢✳✶✻✽✻✶✳✢"

    def __init__(self):
        self.ligado = False
        self.saida = None
        self.trava = threading.Lock()
        self.texto = ""
        self.desde = 0.0
        self.visivel = False
        self._fio = None
        self._rodando = threading.Event()

    def ligar(self, saida):
        self.saida, self.ligado = saida, True

    def desligar(self):
        self.parar()
        self.ligado, self.saida = False, None

    def girar(self, texto):
        if not self.ligado:
            return
        with self.trava:
            if texto != self.texto or not self._rodando.is_set():
                self.desde = time.time()
            self.texto = texto
        if not self._rodando.is_set():
            self._rodando.set()
            self._fio = threading.Thread(target=self._laco, daemon=True)
            self._fio.start()

    def parar(self):
        if not self._rodando.is_set():
            return
        self._rodando.clear()
        if self._fio is not None and self._fio is not threading.current_thread():
            self._fio.join(0.5)
        with self.trava:
            self.apagar()

    def apagar(self):
        """Limpa a linha do símbolo (com a trava na mão)."""
        if self.visivel and self.saida is not None:
            self.saida.write("\r\033[K")
            self.saida.flush()
            self.visivel = False

    def _laco(self):
        i = 0
        while self._rodando.is_set():
            with self.trava:
                if not self._rodando.is_set():
                    break
                quadro = self.QUADROS[i % len(self.QUADROS)]
                segundos = int(time.time() - self.desde)
                linha = (f"\r\033[K{Cor.MAGENTA}{quadro}{Cor.RESET} {self.texto}… "
                         f"{Cor.CINZA}({segundos}s · {t('term.parar')}){Cor.RESET}")
                self.saida.write(linha)
                self.saida.flush()
                self.visivel = True
            i += 1
            time.sleep(0.09)


_girando = _Girando()


def girar(texto):
    _girando.girar(texto)


def parar_girando():
    _girando.parar()


def _curto(modelo):
    """"ProjectOpenTARS/Gargantua:latest" -> "Gargantua": o nome inteiro não cabe na linha do símbolo."""
    nome = str(modelo or "").split("/")[-1]
    return nome[:-len(":latest")] if nome.endswith(":latest") else nome


def _recuar(texto):
    """Quebras de linha do texto que chega aos pedaços ficam alinhadas embaixo do "●"."""
    return texto.replace("\n", "\n" + _RECUO)


def _term_ferramenta(d):
    parar_girando()
    nome = nome_ferramenta(d["nome"])
    resumo = c(f" ({d['resumo']})", Cor.CINZA) if d.get("resumo") else ""
    print("\n" + c("● ", Cor.CIANO) + c(nome, Cor.NEGRITO) + resumo, flush=True)
    girar(nome[:1].upper() + nome[1:])


def _term_ferramenta_fim(d):
    parar_girando()
    if d.get("sucesso"):
        print(c(_PENDURA, Cor.CINZA) + c("✓", Cor.VERDE) + c(f" {_segundos(d['segundos'])}s", Cor.CINZA))
    else:
        print(c(_PENDURA, Cor.CINZA) + c(f"✗ {t('msg.falhou')}", Cor.VERMELHO) + c(f" {_segundos(d['segundos'])}s", Cor.CINZA))


def _term_tarefa(d):
    girar(f"{t('msg.pensando').capitalize()} · {_curto(d['modelo'])}")


def _term_carregando(d):
    if d.get("segundo_plano"):
        parar_girando()
        print(c(_PENDURA + t("msg.carregando_fundo", modelo=d["modelo"]).rstrip("."), Cor.CINZA))
    else:
        girar(t("msg.carregando_titulo", modelo=_curto(d["modelo"])))


def _term_carregado(d):
    if d.get("segundo_plano") or not _girando.ligado:
        parar_girando()
        print(c(_PENDURA + t("msg.carregado", modelo=d["modelo"], segundos=_segundos(d["segundos"])), Cor.CINZA))
    else:
        girar(f"{t('msg.pensando').capitalize()} · {_curto(d['modelo'])}")


def _term_descarregando(d):
    parar_girando()
    print(c(_PENDURA + t("msg.descarregando", modelo=d["modelo"]).rstrip("."), Cor.CINZA))


def _term_pensamento(d):
    if d.get("inicio"):
        parar_girando()
        print("\n" + c(f"✻ {t('msg.pensando').capitalize()}…", Cor.CINZA))
        print(_RECUO, end="")
    print(Cor.CINZA + Cor.ITALICO + _recuar(d["texto"]) + Cor.RESET, end="", flush=True)


def _term_resposta(d):
    if d.get("inicio"):
        parar_girando()
        if d.get("apos_pensamento"):
            print()
        print("\n" + c("● ", Cor.VERDE), end="")
    print(_recuar(d["texto"]), end="", flush=True)


def _term_tempo(d):
    parar_girando()
    modo = "auto" if d.get("modo") == "AUTO" else t("term.modo_fixo")
    print(c(f"{_PENDURA}{_curto(d['modelo'])} · {modo} · {_segundos(d['segundos'])}s", Cor.CINZA))


def _term_plano(d):
    parar_girando()
    print("\n" + c("● ", Cor.CIANO) + c(t("msg.plano").rstrip(":"), Cor.NEGRITO))
    for i, etapa in enumerate(d.get("etapas") or [], 1):
        print(c(_PENDURA if i == 1 else " " * len(_PENDURA), Cor.CINZA) + f"{i}. {etapa}")


def _term_folego(d):
    parar_girando()
    print(c(_PENDURA + t("msg.folego", etapas=d.get("etapas"), acoes=d.get("acoes")), Cor.CINZA))


def _term_analisando(d):
    girar(t("msg.analisando", modelo=_curto(d["modelo"])).rstrip(".").rstrip("…"))


_TERMINAL = {
    "plano": _term_plano,
    "ferramenta": _term_ferramenta,
    "ferramenta_fim": _term_ferramenta_fim,
    "tarefa": _term_tarefa,
    "carregando": _term_carregando,
    "carregado": _term_carregado,
    "descarregando": _term_descarregando,
    "pensamento": _term_pensamento,
    "resposta": _term_resposta,
    "fim_stream": lambda d: print(flush=True),
    "tempo": _term_tempo,
    "folego": _term_folego,
    "analisando": _term_analisando,
}
