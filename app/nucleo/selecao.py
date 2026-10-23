# openTARS — nucleo/selecao.py
# Escolha da tarefa (camadas) e do modelo, e os comandos /modelo.
#
# Parte do núcleo: o tars.py executa este arquivo DENTRO do próprio
# namespace (ver _carregar_nucleo), então tudo aqui é tars.<nome> e as
# partes enxergam umas às outras sem import. Os testes que trocam
# tars.<função> por uma falsa continuam valendo pra todas as partes.
# flake8: noqa

# ============================================================
# SELEÇÃO DE MODELO
# ============================================================
#
# As palavras-chave de cada categoria vêm dos arquivos de idioma
# (detectar.<categoria>) e são juntadas uma vez em _vocab(): as do idioma
# escolhido, as dos idiomas do sistema e as do inglês. Aqui ficam só as
# que não mudam com o idioma (marcas e nomes técnicos).

_PALAVRAS_NEUTRAS = {
    "visao": ("mouse",),
    "fechar": (),
    "busca": (),
    "sites": ("youtube", "chatgpt", "google", "spotify", "discord", "steam", "brave", "firefox",
              "gmail", "reddit", "instagram", "facebook", "netflix", "twitch", "github", "wikipedia"),
    "abrir": (),
    "codigo": (
        "python", "javascript", "typescript", "java", "rust", "golang", "html", "css", "sql",
        "regex", "json", "script", "debug", "bug", "stacktrace", "kotlin", "php",
    ),
    "tecnico": (
        "linux", "terminal", "bash", "shell", "ubuntu", "zorin", "kernel", "driver", "gpu",
        "cuda", "ollama", "docker", "git", "apt", "sudo", "systemd", "grub", "nvidia",
        "ext4", "btrfs", "ntfs", "exfat", "fat32", "xfs", "zfs", "lvm", "fstab", "tar.gz", "wayland", "x11",
    ),
    "acao": (),
}

# Ordem de checagem. Verbo ou alvo EXPLÍCITO ("feche", "abra", "youtube")
# vem antes de palavra-tópico solta: "abra o terminal" é uma AÇÃO (o
# "terminal" é só o alvo) e "abra o vs code" também — antes isso caía em
# "técnico" e ia pro modelo de programação, que não sabe abrir app. BUSCA
# vem antes de SITES: "pesquise X no google" precisa escolher entre
# search_web e open_website, o que o modelo minúsculo não faz direito.
# CÓDIGO (escrever/consertar programa) vem antes de TÉCNICO (Linux,
# sistema): só código vai pro especialista em programação.
_ORDEM_DETECCAO = (
    ("visao", "visao"),
    ("fechar", "acao"),
    ("busca", "busca"),
    ("sites", "simples"),
    ("abrir", "acao"),
    ("codigo", "codigo"),
    ("tecnico", "tecnico"),
    ("acao", "acao"),
)

# Limite de palavras pra considerar uma frase "conversa curta" (sem
# nenhuma das categorias acima) — bate-papo bem simples também cai no
# mesmo balde de modelo leve que abrir URL, em vez de sempre acordar o
# modelo mais pesado só pra dizer "oi".
_LIMITE_PALAVRAS_CONVERSA_SIMPLES = 6

# Até aqui, sem pista nenhuma: é cumprimento/agradecimento.
_LIMITE_PALAVRAS_SEM_CLASSIFICAR = 3

# A partir de quantas palavras um pedido que cita um site ("youtube")
# deixa de ser "abra o site" e vira uma busca nele.
_PALAVRAS_SITE_COM_BUSCA = 2  # palavras além do site, do "abrir" e de "o", "pra mim"...
# Só sites onde "X no site" é procurar algo (no Spotify/Discord/Steam o
# pedido longo costuma ser uma ação no app: "spotify pausa a música").
_SITES_DE_BUSCA = {"youtube", "google", "wikipedia", "reddit", "amazon", "github", "bing",
                   "duckduckgo", "stackoverflow", "mercadolivre", "netflix", "twitch"}

_CATEGORIAS_VALIDAS = ("visao", "codigo", "tecnico", "acao", "busca", "simples", "geral")

# Palavras que não dizem nada sobre o pedido (artigos, "pra mim"...): ficam de
# fora quando se conta o que vem além do nome de um site.
_PALAVRAS_VAZIAS = frozenset("""
a o as os um uma uns umas de da do das dos no na nos nas em pra pro pras pros para por com me mim meu minha
meus minhas te voce vc isso esse essa este esta aquele aquela que e ou se lá la aqui ai ai por favor pf pfv
the a an of to in on at for with me my i you your it this that is are be please and or can could would
el la los las un una de del en con por para mi mis yo tu que y o es lo le
le la les un une des de du en au aux pour avec moi mon ma mes je tu que et ou est ce
der die das ein eine einen dem den des mit fur mich mir mein meine ich du und oder ist bitte
""".split())


def palavras_chave(texto, t_norm=None):
    """(categoria, grupo) pelas palavras-chave (instantâneo, sem IA), ou
    (None, None). Palavra solta e trecho batem só como palavras inteiras
    ("git" não bate em "digital"; "the screen" não bate em "screenshots")."""

    if t_norm is None:
        t_norm = normalizar(texto)
    lista_tokens = [x for x in _RE_TOKENS.split(t_norm) if x]
    tokens = set(lista_tokens)
    junto = " " + " ".join(lista_tokens) + " "
    for grupo, categoria in _ORDEM_DETECCAO:
        palavras, expressoes = _vocab()["detectar"][grupo]
        if tokens & palavras or any(e in junto for e in expressoes):
            # "abra o youtube" é só abrir o site (modelo leve); "vídeos de
            # receita de lasanha no youtube" tem o que procurar lá: busca
            # (o modelo minúsculo não sabe montar a pesquisa).
            # Só contam as palavras que dizem o que fazer NO site: "entra no
            # gmail pra mim" e "open the youtube website" são só abrir.
            if grupo == "sites" and len(_palavras_alem_do_site(lista_tokens)) >= _PALAVRAS_SITE_COM_BUSCA:
                # Pedido longo citando um app/site: procurar algo nele
                # (youtube, google...) ou fazer algo nele (spotify, discord).
                return ("busca" if tokens & _SITES_DE_BUSCA else "acao"), grupo
            return categoria, grupo
    return None, None


_PALAVRAS_DE_SITE = frozenset({"site", "website", "webpage", "pagina", "page", "web", "sitio", "seite", "webseite"})


def _palavras_alem_do_site(lista_tokens):
    """As palavras do pedido tirando as vazias, o nome do site, "site" e o
    verbo de abrir/entrar."""
    v = _vocab()["detectar"]
    ignorar = v["sites"][0] | v["abrir"][0] | _PALAVRAS_DE_SITE | _VERBOS_DE_ENTRAR
    return [x for x in lista_tokens if x not in _PALAVRAS_VAZIAS and x not in ignorar]


# "entra no", "vai no", "go to": abrir um site sem ser o verbo "abrir".
_VERBOS_DE_ENTRAR = frozenset({"entra", "entre", "entrar", "vai", "va", "acessa", "acesse", "acessar", "go", "visit",
                               "take", "pull", "ve", "ir", "accede", "entra", "aller", "va", "geh", "gehe", "besuche"})


def tarefa_por_palavras(texto, t_norm=None):
    return palavras_chave(texto, t_norm)[0]


# Grupos de palavras-chave que são só um ASSUNTO ("pasta", "arquivo",
# "erro", "linux"), não um verbo ou alvo explícito: valem menos. "acha um
# tutorial de como trocar a pasta térmica" não é mexer numa pasta.
_GRUPOS_FRACOS = frozenset({"acao", "tecnico"})
# Grupos de ordem ("abra", "feche", "aba") que numa PERGUNTA ("qual aba
# está aberta?") quase nunca são uma ordem.
_GRUPOS_DE_ORDEM = frozenset({"abrir", "fechar", "acao"})


def _peso_palavra_chave(grupo, t_norm):
    if grupo in _GRUPOS_FRACOS:
        return escolha.PESO_PALAVRA_FRACA
    if grupo in _GRUPOS_DE_ORDEM and escolha.eh_pergunta(t_norm):
        return escolha.PESO_PALAVRA_FRACA
    if grupo in ("abrir", "fechar"):
        lista = [x for x in _RE_TOKENS.split(t_norm) if x]
        if lista and len(lista) <= escolha.LIMITE_PALAVRAS_ORDEM and lista[0] in _vocab()["detectar"][grupo][0]:
            return escolha.PESO_ORDEM_NO_INICIO
    return escolha.PESO_PALAVRA


# Acertos/falhas de cada modelo por tarefa neste PC (tars_escolha.Historico).
def _caminho_historico():
    if os.environ.get("TARS_ARQUIVO_HISTORICO"):
        return Path(os.environ["TARS_ARQUIVO_HISTORICO"])
    return plataforma.pastas()["cache"] / "historico_modelos.json"


historico_modelos = escolha.Historico(_caminho_historico())


def _tarefa_do_historico(tarefa):
    """'acao_complexa' é a mesma tarefa 'acao' com outro modelo na frente."""
    return "acao" if tarefa == "acao_complexa" else tarefa


# Última tarefa decidida (camada de contexto): "agora clica no =" logo
# depois de "abra a calculadora" continua sendo uma ação.
_ultima_tarefa = {"categoria": None, "ts": 0.0}
_ultima_decisao = {"d": None}

# Nomes de app instalados (camada 4): cacheados junto com a varredura dos
# .desktop. Só o nome principal, com 4+ letras ("Spotify", "GIMP").
_cache_nomes_apps = {"ts": None, "nomes": frozenset()}


def _nomes_de_apps():
    entradas = desktop_entries()
    if _cache_nomes_apps["ts"] != _cache_desktop.get("ts"):
        nomes = set()
        for e in entradas or []:
            n = normalizar(e.get("nome") or "")
            if len(n) >= 4 and n not in _NOMES_APP_GENERICOS:
                nomes.add(n)
        _cache_nomes_apps.update(ts=_cache_desktop.get("ts"), nomes=frozenset(nomes))
    return _cache_nomes_apps["nomes"]


_NOMES_APP_GENERICOS = {"files", "arquivos", "settings", "configuracoes", "help", "ajuda", "text", "texto",
                        "terminal", "videos", "music", "musica", "photos", "fotos", "maps", "mapas",
                        "weather", "clima", "clock", "relogio", "calendar", "calendario", "contacts"}


def _cita_app(t_norm, tokens):
    for nome in _nomes_de_apps():
        if (" " in nome and nome in t_norm) or nome in tokens:
            return nome
    return None


def _verbos_de_acao():
    return _vocab()["verbos_acao"]


def classificar_local(texto):
    """Camada 4 sozinha: a helper Murph (tars_murph). Devolve (resultado,
    nome); sem o arquivo dela, (None, "murph") e as outras camadas decidem."""
    try:
        r = murph.classificar(texto) if murph.disponivel() else None
    except Exception:
        LOG.exception("murph")
        r = None
    return r, "murph"


def _votos_modelo_local(texto, votos, so_duvida=False):
    """Camada 4: a Murph, treinada com os exemplos.
    Confiante (folga calibrada), vale como uma palavra-chave; em dúvida,
    as duas mais prováveis ganham um voto pequeno e seguem pras camadas
    seguintes."""
    try:
        r, _ = classificar_local(texto)
    except Exception:
        LOG.exception("classificador local")
        return None
    if not r:
        return None
    if so_duvida:
        r = dict(r, certo=False)
    notas = r["notas"]
    if r["certo"]:
        votos.dar(notas[0][1], escolha.peso_local(r["margem"], r["limite"]), "local")
    else:
        votos.dar(notas[0][1], escolha.PESO_LOCAL_DUVIDA, "local")
        if len(notas) > 1:
            votos.dar(notas[1][1], escolha.PESO_LOCAL_DUVIDA * 0.6, "local")
    return r


def decidir_tarefa(texto, anterior=None):
    """A tarefa do pedido, decidida em camadas (ver tars_escolha.py).
    Devolve uma escolha.Decisao (categoria, via, votos, finalistas,
    várias etapas e a trilha do raciocínio, mostrada no --explicar).

    anterior: a tarefa do pedido anterior (camada de contexto). Sem ela,
    usa a última lembrada por lembrar_tarefa (até 5 minutos).

    Todas as camadas são instantâneas (< 1 ms), sem IA nenhuma. (Neo: os
    embeddings e o classificador por IA saíram; a Murph cobre o que eles faziam.)"""

    t_norm = normalizar(texto)
    tokens = set(_RE_TOKENS.split(t_norm))
    palavras = len(t_norm.split())
    votos = escolha.Votos()
    trilha = []
    partes = escolha.partes_do_pedido(t_norm, _verbos_de_acao())
    multi = len(partes) >= 2

    def decisao(categoria, via):
        return escolha.Decisao(categoria, via, dict(votos.soma), votos.finalistas(_CATEGORIAS_VALIDAS),
                               multi_etapas=multi, trilha=trilha)

    # 1. Palavras-chave
    por_palavras, grupo = palavras_chave(texto, t_norm)
    votos.dar(por_palavras, _peso_palavra_chave(grupo, t_norm), "palavras")
    trilha.append(("palavras", por_palavras or "-"))

    # 2. Contexto: continuação curta do pedido anterior
    if anterior is None and time.time() - _ultima_tarefa["ts"] < escolha.VALIDADE_CONTEXTO_SEG:
        anterior = _ultima_tarefa["categoria"]
    continuacao = bool(anterior and escolha.eh_continuacao(t_norm))
    if continuacao:
        votos.dar(anterior, escolha.PESO_CONTEXTO, "contexto")
        trilha.append(("contexto", f"{anterior} (continua o pedido anterior)"))

    # 3. Estrutura (código, erro, comando, link, pergunta)
    antes = dict(votos.soma)
    escolha.votos_estruturais(texto, t_norm, votos)
    estrutura = {c: v - antes.get(c, 0.0) for c, v in votos.soma.items() if v != antes.get(c, 0.0)}
    if estrutura:
        trilha.append(("estrutura", ", ".join(f"{c}+{v:.1f}" for c, v in estrutura.items())))
    if multi:
        trilha.append(("etapas", " | ".join(partes)))
    sem_pistas = not votos.soma

    # 4. Classificador local
    # Continuação ("de novo", "agora clica no x"): o sentido vem do pedido
    # anterior, então o classificador (que só vê esta frase) vale como dúvida.
    if continuacao or escolha.so_repeticao(t_norm):
        local = _votos_modelo_local(texto, votos, so_duvida=True)
    else:
        local = _votos_modelo_local(texto, votos)
    if local:
        notas = ", ".join(f"{c} {n:.2f}" for n, c in local["notas"][:3])
        trilha.append(("murph", f"{local['notas'][0][1]} ({'decidido' if local['certo'] else 'em dúvida'}, "
                                f"folga {local['margem']:.2f} / precisa {local['limite']:.2f}; {notas})"))

    # "oi", "valeu", "bom dia": nada apontou pra outra tarefa.
    if sem_pistas and palavras <= _LIMITE_PALAVRAS_SEM_CLASSIFICAR and not (local and local["certo"]):
        trilha.append(("curto", "simples"))
        return decisao("simples", "curto")

    # As primeiras camadas concordam: decide já.
    clara = votos.decisao_clara()
    if clara:
        return decisao(*_coerente(clara[0], clara[1], t_norm, votos, trilha))

    # 5. Cita um app instalado
    app_citado = None
    try:
        app_citado = _cita_app(t_norm, tokens)
    except Exception:
        pass
    if app_citado:
        votos.dar("acao", escolha.PESO_APP, "apps")
        trilha.append(("apps", app_citado))

    clara = votos.decisao_clara()
    if clara:
        categoria, via = clara
    else:
        # Sem acordo claro: a mais votada; sem voto nenhum, pelo tamanho.
        finalistas = votos.finalistas(_CATEGORIAS_VALIDAS)
        if len(finalistas) == 1 and votos.soma[finalistas[0]] >= escolha.MINIMO_DECISAO:
            categoria, via = finalistas[0], "+".join(votos.origem[finalistas[0]])
        elif finalistas:
            categoria, via = finalistas[0], "melhor_voto"
        else:
            categoria = "simples" if palavras <= _LIMITE_PALAVRAS_CONVERSA_SIMPLES else "geral"
            via = "padrao"

    return decisao(*_coerente(categoria, via, t_norm, votos, trilha))


def _coerente(categoria, via, t_norm, votos, trilha):
    """8. Coerência: resultado sem sentido vira o mais provável que faça."""
    corrigida, motivo = escolha.coerencia(categoria, t_norm, votos)
    if motivo:
        trilha.append(("coerencia", f"{categoria} -> {corrigida}"))
        return corrigida, f"{via}+{motivo}"
    return categoria, via


def detectar_tarefa(texto):
    decisao = decidir_tarefa(texto)
    _ultima_decisao["d"] = decisao
    LOG.info("tarefa=%s", decisao.resumo())
    return decisao.categoria


def lembrar_tarefa(categoria):
    """Guarda a tarefa do pedido atual pra camada de contexto do próximo."""
    _ultima_tarefa.update(categoria=categoria, ts=time.time())


# Raciocínio ("think") do modelo: ajuda em programação e perguntas
# difíceis, mas numa ação simples ("fecha o claude") só atrasa — no log
# real, 31 s pra fechar um app, quase tudo pensando. Pedido longo em
# qualquer categoria costuma ter várias etapas: aí o raciocínio volta.
# TARS_PENSAR=sempre|nunca força um lado.
_TAREFAS_COM_RACIOCINIO = {"codigo", "tecnico", "geral"}
_PALAVRAS_PEDIDO_LONGO = 20


def deve_pensar(tarefa, texto="", multi_etapas=False):
    modo = normalizar(os.environ.get("TARS_PENSAR") or "auto")
    if modo in ("sempre", "always", "1", "on", "sim", "yes"):
        return True
    if modo in ("nunca", "never", "0", "off", "nao", "no"):
        return False
    if multi_etapas:
        # "abre X e faz Y": planejar antes evita parar na primeira etapa.
        return True
    if tarefa is None:
        tarefa = tarefa_por_palavras(texto)
    if tarefa is None or tarefa in _TAREFAS_COM_RACIOCINIO:
        return True
    return len((texto or "").split()) >= _PALAVRAS_PEDIDO_LONGO


def avaliar_classificador():
    """opentars --avaliar-classificador: mede quanto a helper Murph sozinha
    e o modo AUTO completo acertam ao decidir o tipo dos pedidos (frases do
    idioma escolhido; diferentes dos exemplos). Não precisa do Ollama."""

    frases = [tuple(par) for par in i18n.lista("avaliacao") if isinstance(par, list) and len(par) == 2]
    print(c(f"\n{t('avaliacao.titulo', modelo='Murph ' + murph.versao(), n=len(frases))}\n", Cor.CIANO))

    r = medir_classificador(frases)
    n = r["n"]

    def pct(x, total=None):
        return f"{100 * x / max(1, total if total is not None else n):.0f}"

    print(t("avaliacao.so_murph", acertos=r["acertos_local"], n=n, pct=pct(r["acertos_local"]),
            certos=r["certos_local"], pct_certos=pct(r["acertos_certos_local"], r["certos_local"])))
    print(c(t("avaliacao.com_palavras", acertos=r["acertos_total"], n=n, pct=pct(r["acertos_total"])), Cor.VERDE) + "\n")

    for cat, (ok, total) in r["por_categoria"].items():
        if total:
            print(f"  {cat:<8} {ok}/{total}")

    for chave, erros in (("avaliacao.erros_total", r["erros_total"]), ("avaliacao.erros_local", r["erros_local"])):
        if erros:
            print(c("\n" + t(chave), Cor.AMARELO))
            for frase, esperado, resposta in erros:
                print(f"  {frase} | {esperado} | {resposta}")
    print()
    return 0


def explicar_escolha(texto):
    """opentars --explicar "pedido": mostra camada por camada como a
    tarefa é decidida e qual fila de modelos atende (com o placar de cada
    um neste PC). Não manda nada pra IA de conversa."""

    if not texto.strip():
        print(t("explicar.uso"))
        return 2
    print(c(f"\n{t('explicar.titulo', pedido=texto)}\n", Cor.CIANO))

    online = ollama_online()
    if online:
        catalogar_modelos(forcar=True)
    else:
        print(c(t("aviso.ollama_offline", host=OLLAMA_HOST), Cor.AMARELO) + "\n")

    d = decidir_tarefa(texto)
    print(t("explicar.camadas"))
    for camada, conclusao in d.trilha:
        print(f"  {camada:<11} {conclusao}")
    votos = ", ".join(f"{cat}={v:.1f}" for cat, v in sorted(d.votos.items(), key=lambda x: -x[1])) or "-"
    print(t("explicar.votos", votos=votos))
    print(c(t("explicar.resultado", tarefa=f"{nome_tarefa(d.categoria)} ({d.categoria})", via=d.via), Cor.VERDE))
    if d.multi_etapas:
        partes = escolha.partes_do_pedido(normalizar(texto), _verbos_de_acao())
        print(t("explicar.multi", partes=" | ".join(partes)))

    if online:
        tarefa_hist = _tarefa_do_historico(d.categoria)
        print("\n" + t("explicar.fila"))
        fila = construir_cadeia_fallback(tarefa_da_fila(d.categoria, d.multi_etapas))[:6]
        if not fila:
            print(f"  {t('aviso.sem_modelo_conversa')}")
        for i, tag in enumerate(fila, 1):
            acertos, total = historico_modelos.placar(tag, tarefa_hist)
            if not total:
                placar = t("explicar.sem_placar")
            elif historico_modelos.ruim(tag, tarefa_hist):
                placar = t("explicar.placar_ruim", acertos=acertos, total=total)
            else:
                placar = t("explicar.placar", acertos=acertos, total=total)
            print(f"  {i}. {tag:<30} {placar}")

    pensa = deve_pensar(d.categoria, texto, d.multi_etapas)
    print("\n" + t("explicar.pensar", sim_nao=t("explicar.sim") if pensa else t("explicar.nao"),
                   n=len(ferramentas_para(d.categoria))) + "\n")
    return 0


def medir_classificador(frases):
    """Classifica as frases pela Murph sozinha e pelo caminho completo que o
    modo AUTO usa. Usado pelo --avaliar-classificador e pelo --autoteste.
    por_categoria conta o caminho completo."""

    acertos_total = acertos_local = certos_local = acertos_certos_local = 0
    por_categoria = {cat: [0, 0] for cat in _CATEGORIAS_VALIDAS}
    erros_local, erros_total = [], []
    inicio = time.time()

    for frase, esperado in frases:
        local, _ = classificar_local(frase)
        resposta_local = local["notas"][0][1] if local else None
        if resposta_local == esperado:
            acertos_local += 1
        else:
            erros_local.append((frase, esperado, resposta_local or "?"))
        if local and local["certo"]:
            certos_local += 1
            acertos_certos_local += resposta_local == esperado

    for frase, esperado in frases:
        final = detectar_tarefa(frase)
        por_categoria.setdefault(esperado, [0, 0])[1] += 1
        if final == esperado:
            acertos_total += 1
            por_categoria[esperado][0] += 1
        else:
            d = _ultima_decisao.get("d")
            erros_total.append((frase, esperado, f"{final} ({d.via})" if d else final))

    return {
        "n": len(frases),
        "acertos_total": acertos_total,
        "por_categoria": por_categoria,
        "acertos_local": acertos_local,
        "certos_local": certos_local,
        "acertos_certos_local": acertos_certos_local,
        "erros_local": erros_local,
        "erros_total": erros_total,
        "ms_medio": 1000 * (time.time() - inicio) / max(1, 2 * len(frases)),
    }


def proximo_modelo_disponivel(tarefa, excluir=()):
    """Devolve o modelo mais indicado pra essa categoria de tarefa,
    dentre os que estão de fato instalados — construindo a cadeia de
    fallback dinamicamente a partir do catálogo (ver
    construir_cadeia_fallback), não de uma lista fixa."""

    cadeia = construir_cadeia_fallback(tarefa)

    for candidato in cadeia:
        if candidato not in excluir:
            return candidato

    return MODELO_PADRAO


def tarefa_da_fila(tarefa, complexa=False):
    """A fila de modelos usada pra tarefa. Ação/busca com várias etapas
    ("abre o claude e faz uma pergunta") vai pra fila do maior modelo que
    roda bem: o menorzinho se perde no meio do caminho."""
    if complexa and tarefa in ("acao", "busca"):
        return "acao_complexa"
    return tarefa


def escolher_modelo(texto, tarefa=None, complexa=False):

    global modo_modelo
    global modelo_manual

    if modo_modelo == "MANUAL" and modelo_manual:
        return modelo_manual

    if tarefa is None:
        tarefa = detectar_tarefa(texto)

    fila = tarefa_da_fila(tarefa, complexa)
    if fila == "simples" and modelo_atual:
        # Conversa curta ("oi"): o modelo que já está na placa responde mais rápido que trocar
        # (descarregar um e carregar outro leva segundos).
        cadeia = construir_cadeia_fallback(fila)
        if modelo_atual in cadeia and cadeia.index(modelo_atual) < max(1, len(cadeia) - 1):
            return modelo_atual
    return proximo_modelo_disponivel(fila)


# ============================================================
# COMANDOS DE MODELO
# ============================================================

def mostrar_modelos():

    print()
    print(t("term.ias_disponiveis"))
    print()

    _imprimir_lista_modelos()

    print(t("term.modo_atual", modo=modo_modelo))

    if modo_modelo == "MANUAL":
        print(t("term.modelo_fixado", modelo=modelo_manual))
    else:
        print(t("term.modo_auto_explica"))


# "o menor", "the smallest", "el más grande", "o de visão"...: resolvem pra
# um modelo do catálogo por critério, em vez de nome. As frases de cada
# idioma vêm dos arquivos de idioma (modelo.menor, modelo.maior...).
_CRITERIOS_MODELO = {
    "modelo.menor": lambda cat: _extremo_por_tamanho(cat, menor=True),
    "modelo.maior": lambda cat: _extremo_por_tamanho(cat, menor=False),
    "modelo.visao": lambda cat: _melhor_por_capacidade(cat, "vision"),
    "modelo.tecnico": lambda cat: _melhor_por_categoria(cat, "codigo"),
}


def _so_de_conversa(catalogo):
    """"/modelo o menor", "o de visão"...: só entra modelo que conversa (nem embedding, nem o Cooper)."""
    return {t_: m for t_, m in catalogo.items()
            if m["categoria"] != "embedding" and not visao_lib.e_cooper(t_) and not m.get("nuvem")}


def _extremo_por_tamanho(catalogo, menor):
    catalogo = _so_de_conversa(catalogo)
    candidatos = [m for m in catalogo.values() if m["parametros_b"] is not None]

    if not candidatos:
        candidatos = list(catalogo.values())

    if not candidatos:
        return None

    candidatos.sort(
        key=lambda m: m["parametros_b"] if m["parametros_b"] is not None else 0,
        reverse=not menor,
    )

    return candidatos[0]["tag"]


def _melhor_por_capacidade(catalogo, capacidade):
    catalogo = _so_de_conversa(catalogo)
    candidatos = [m for m in catalogo.values() if capacidade in m["capacidades"]]

    if not candidatos:
        return None

    candidatos.sort(
        key=lambda m: m["parametros_b"] if m["parametros_b"] is not None else 0,
        reverse=True,
    )

    return candidatos[0]["tag"]


def _melhor_por_categoria(catalogo, categoria):
    catalogo = _so_de_conversa(catalogo)
    candidatos = [m for m in catalogo.values() if m["categoria"] == categoria]

    if not candidatos:
        return None

    candidatos.sort(
        key=lambda m: m["parametros_b"] if m["parametros_b"] is not None else 0,
        reverse=True,
    )

    return candidatos[0]["tag"]


def _tabela_resolucao_modelos(catalogo):
    """Tabela de 'texto normalizado' → tag do modelo, construída a
    partir do que está REALMENTE instalado (catalogo), não de uma
    lista fixa. Cada modelo instalado entra por: sua tag exata, a tag
    sem a versão/tamanho (ex: "qwen3" pra "qwen3:8b", quando único), e
    sua família reportada pelo Ollama."""

    tabela = {}

    contagem_prefixo = {}
    for tag in catalogo:
        prefixo = normalizar(tag.split(":")[0])
        contagem_prefixo[prefixo] = contagem_prefixo.get(prefixo, 0) + 1

    contagem_familia = {}
    for info in catalogo.values():
        fam_n = normalizar(info["familia"])
        if fam_n:
            contagem_familia[fam_n] = contagem_familia.get(fam_n, 0) + 1

    for tag, info in catalogo.items():

        tabela[normalizar(tag)] = tag

        prefixo = normalizar(tag.split(":")[0])
        if contagem_prefixo.get(prefixo) == 1:
            tabela[prefixo] = tag

        fam_n = normalizar(info["familia"])
        if fam_n and contagem_familia.get(fam_n) == 1:
            tabela[fam_n] = tag

    return tabela


def _resolver_alvo_modelo(alvo, catalogo):
    """Resolve um ALVO explícito de troca de modelo — o texto depois de
    '/modelo ', ou uma mensagem inteira que já é só o nome do modelo —
    contra o catálogo real: tag/família/prefixo exatos, ou um
    superlativo ('o menor', 'o de visão'). Retorna a tag ou None.

    IMPORTANTE: isso nunca é chamado com uma frase de tarefa qualquer
    do chat (ver interpretar_comando_modelo) — só com algo que o
    próprio usuário já indicou explicitamente ser um nome/critério de
    modelo, então não precisa (e não deve) tentar advinhar intenção a
    partir de verbos genéricos como 'usar' ou 'quero': foi exatamente
    esse tipo de heurística sobre texto livre que causava trocas de
    modelo indevidas em pedidos comuns como 'use suas ferramentas para
    abrir o youtube'."""

    if not catalogo:
        return None

    tabela = _tabela_resolucao_modelos(catalogo)

    if alvo in tabela:
        return tabela[alvo]

    for frase, resolvedor in _vocab()["superlativos"].items():
        if frase in alvo:
            resultado = resolvedor(catalogo)
            if resultado:
                return resultado

    return None


def _squash(texto):
    """Reduz um texto a só letras/números minúsculos, sem acento,
    espaço ou pontuação — pra comparar "gemma 270m" com a tag real
    "gemma3:270m" sem se importar com onde tem espaço, dois pontos ou
    um "3" que o usuário engoliu."""

    return re.sub(r"[^a-z0-9]", "", normalizar(texto))


def _resolver_modelo_por_texto_livre(texto_livre, catalogo):
    """Casamento mais tolerante que _resolver_alvo_modelo: usado
    quando o usuário já deixou explícito que quer trocar de modelo
    (comando "/modelo <algo>"), então não
    exige reconhecer a tag/família ao pé da letra — ignora pontuação e
    espaços, então "gemma 270m" casa com a tag "gemma3:270m" mesmo sem
    o "3" e sem o ":"."""

    if not catalogo or not texto_livre.strip():
        return None

    alvo = _squash(texto_livre)

    if not alvo:
        return None

    melhor_tag = None
    melhor_pontuacao = 0

    for tag, info in catalogo.items():
        for candidato in (tag, info.get("familia", "") or ""):
            squash = _squash(candidato)
            if squash and ((len(alvo) >= 3 and alvo in squash) or squash in alvo):
                if len(squash) > melhor_pontuacao:
                    melhor_pontuacao = len(squash)
                    melhor_tag = tag

    if melhor_tag:
        return melhor_tag

    # Ainda nada — tenta por partes: cada "palavra" relevante do texto
    # (2+ caracteres) precisa aparecer na tag, mesmo que fora de ordem
    # (ex: "o modelo 270m da gemma" ainda acha "gemma3:270m").
    tokens = [
        tok for tok in re.split(r"[^a-z0-9]+", normalizar(texto_livre))
        if len(tok) >= 2 and tok not in _vocab()["modelo_ignorar"]
    ]

    if not tokens:
        return None

    for tag in catalogo:
        squash = _squash(tag)
        if all(tok in squash for tok in tokens):
            return tag

    return None


def _eh_comando(t_norm, chave):
    """O texto (já normalizado) é um dos comandos da chave, em qualquer
    idioma? Ex: "/limpar", "/clear", "/limpiar"."""
    return t_norm in _vocab()["comandos"].get(chave, ())


def comando_idioma(argumento):
    """/idioma: sem argumento, lista; com um código ou nome, troca."""
    argumento = (argumento or "").strip()
    disponiveis = i18n.idiomas_disponiveis()
    if not argumento:
        print()
        print(t("idioma.lista_titulo"))
        for codigo, nome in disponiveis.items():
            marca = "●" if codigo == i18n.idioma_atual() else " "
            print(f"  {c(marca, Cor.VERDE)} {codigo:<6} {nome}")
        print(c(t("idioma.como_trocar"), Cor.CINZA))
        return
    alvo = normalizar(argumento)
    codigo = next((cod for cod, nome in disponiveis.items() if normalizar(nome).startswith(alvo)), None)
    codigo = i18n.definir_idioma(codigo or argumento)
    if codigo:
        print(c("\n✓ " + t("idioma.trocado", nome=i18n.nome_idioma(codigo)), Cor.VERDE))
    else:
        print(c("\n✗ " + t("idioma.nao_encontrado", pedido=argumento, lista=", ".join(disponiveis)), Cor.AMARELO))


def interpretar_comando_modelo(texto):
    """Comandos do chat (/modelo, /limpar, /idioma, encerrar...). Devolve
    True se o texto era um comando (e já foi tratado)."""

    global modo_modelo
    global modelo_manual

    t_norm = normalizar(texto)

    if _eh_comando(t_norm, "cmd.modelos"):
        mostrar_modelos()
        return True

    if _eh_comando(t_norm, "cmd.encerrar"):
        encerrar_todas_ias()
        return True

    if _eh_comando(t_norm, "cmd.limpar"):
        limpar_sessao()
        print(c("\n✓ " + t("msg.historico_apagado"), Cor.VERDE))
        return True

    prefixo_idioma = next((p for p in _vocab()["comandos"].get("cmd.idioma", ()) if t_norm == p or t_norm.startswith(p + " ")), None)
    if prefixo_idioma:
        comando_idioma(texto.strip()[len(prefixo_idioma):])
        return True

    if _eh_comando(t_norm, "cmd.auto"):

        modo_modelo = "AUTO"
        modelo_manual = None

        print(c("\n✓ " + t("msg.modo_auto_ativado"), Cor.VERDE))
        return True

    catalogo = catalogar_modelos()

    def _selecionar_modelo(modelo_pedido):
        global modo_modelo, modelo_manual
        modo_modelo = "MANUAL"
        modelo_manual = modelo_pedido
        print(c("\n✓ " + t("msg.modelo_manual", modelo=modelo_pedido), Cor.VERDE))
        LOG.info("troca_de_modelo modelo=%s modo=MANUAL", modelo_pedido)

        # Avisa de cara se esse modelo não suporta ferramentas: ele nunca
        # vai conseguir abrir apps/sites/executar nada, só conversar.
        info = catalogo.get(modelo_pedido)
        if info and info.get("capacidades_conhecidas") and "tools" not in info.get("capacidades", set()):
            print(c("  ⚠ " + t("msg.modelo_sem_ferramentas", modelo=modelo_pedido), Cor.AMARELO))

        # Carrega já, em segundo plano: quando o usuário mandar a próxima
        # mensagem, o modelo já pode estar pronto.
        _carregar_em_segundo_plano(modelo_pedido)

    # "/modelo <algo>" — a forma explícita de trocar de modelo por texto.
    # Tenta em ordem: correspondência exata/critério ("o menor") e
    # aproximação tolerante a pontuação/espaço. Trocar de modelo a
    # partir de uma frase qualquer do chat (sem o comando) foi removido
    # de propósito: "use suas ferramentas para abrir o youtube" chegou a
    # trocar o modelo antes.
    prefixo_modelo = next((p for p in _vocab()["comandos"].get("cmd.modelo", ()) if t_norm.startswith(p + " ")), None)
    if prefixo_modelo:
        alvo = t_norm[len(prefixo_modelo) + 1:].strip()

        if _eh_comando(alvo, "cmd.auto_argumento"):
            modo_modelo = "AUTO"
            modelo_manual = None
            print(c("\n✓ " + t("msg.modo_auto_ativado"), Cor.VERDE))
            return True

        modelo_pedido = (
            _resolver_alvo_modelo(alvo, catalogo)
            or _resolver_modelo_por_texto_livre(alvo, catalogo)
        )

        if modelo_pedido:
            _selecionar_modelo(modelo_pedido)
        else:
            instalados_fmt = ", ".join(sorted(catalogo)) if catalogo else "-"
            print(c("\n✗ " + t("msg.modelo_nao_encontrado", pedido=alvo, instalados=instalados_fmt), Cor.AMARELO))

        return True

    # Mensagem inteira IGUAL (não "contém") a uma tag/família/critério
    # também troca sem o comando: "o menor problema pode causar um erro"
    # contém "o menor", mas não É "o menor".
    tabela = _tabela_resolucao_modelos(catalogo)
    superlativos = _vocab()["superlativos"]

    if t_norm in tabela:
        modelo_pedido = tabela[t_norm]
    elif t_norm in superlativos:
        modelo_pedido = superlativos[t_norm](catalogo)
    else:
        modelo_pedido = None

    if modelo_pedido:
        _selecionar_modelo(modelo_pedido)
        return True

    # Uma tag do Ollama ("familia:tamanho") como mensagem inteira: o
    # usuário quis trocar pra um modelo que ainda não está instalado.
    # (precisa de letra na família: "12:30" ou "pt:br" não são modelo)
    if re.fullmatch(r"[a-z][a-z0-9_./-]{2,}:[a-z0-9][a-z0-9_.-]*", t_norm) and not re.fullmatch(r"[a-z]{1,3}:[a-z]{1,3}", t_norm):
        modo_modelo = "MANUAL"
        modelo_manual = t_norm
        print(c("\n✓ " + t("msg.modelo_manual", modelo=t_norm), Cor.AMARELO)
              + c(" " + t("msg.modelo_nao_instalado", modelo=t_norm), Cor.AMARELO))
        return True

    return False
