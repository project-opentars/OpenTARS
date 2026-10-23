# openTARS — nucleo/hardware.py
# GPU/VRAM, catálogo dos modelos instalados e se cada um cabe nesta máquina.
#
# Parte do núcleo: o tars.py executa este arquivo DENTRO do próprio
# namespace (ver _carregar_nucleo), então tudo aqui é tars.<nome> e as
# partes enxergam umas às outras sem import. Os testes que trocam
# tars.<função> por uma falsa continuam valendo pra todas as partes.
# flake8: noqa

# ============================================================
# HARDWARE E DISPONIBILIDADE DE MODELOS
# ============================================================

_cache_modelos_instalados = {"dados": None, "ts": 0.0}
CACHE_MODELOS_TTL = 60


CACHE_GPU_TTL = 300
_cache_gpu = {"dados": None, "ts": -CACHE_GPU_TTL}


def contexto_ia():
    """Tamanho do contexto (num_ctx) pedido ao Ollama pro modelo da
    conversa. O padrão do Ollama (4096 tokens) não cabe o prompt do
    openTARS + ferramentas (~4 mil tokens) + um print de tela: o Ollama
    cortava o começo da conversa e a IA esquecia o pedido no meio da
    tarefa. Mais contexto usa mais VRAM, então depende da GPU."""

    fixo = os.environ.get("TARS_CONTEXTO")
    if fixo and fixo.isdigit():
        return int(fixo)
    escolhido = modos.avancado()["contexto"]       # 5.1: modo Pro, Ajustes avançados
    if escolhido:
        return max(escolhido, _contexto_minimo["n"])

    gpu = detectar_gpu()
    base = 16384 if gpu and gpu["vram_total_gb"] >= 16 else 8192
    # 5.0: anexos grandes pedem mais contexto (nucleo/anexos.py); fica assim até /limpar
    return max(base, _contexto_minimo["n"])


_contexto_minimo = {"n": 0}


def detectar_gpu(forcar=False):
    """Consulta a GPU NVIDIA local via nvidia-smi. Retorna None se não
    houver nvidia-smi disponível (sem GPU dedicada ou driver ausente).
    Cacheado: essa função é consultada a cada mensagem em modo AUTO
    (pra ordenar a cadeia de fallback pelo que cabe no hardware), e
    rodar um subprocesso a cada turno seria desperdício — a VRAM total
    nunca muda, e a livre não precisa de uma leitura por mensagem pra
    essa heurística."""

    agora = time.time()

    if (
        not forcar
        and (agora - _cache_gpu["ts"]) < CACHE_GPU_TTL
    ):
        return _cache_gpu["dados"]

    resultado = _detectar_gpu_sem_cache()

    _cache_gpu["dados"] = resultado
    _cache_gpu["ts"] = agora

    return resultado


# Menos que isso é memória "emprestada" da RAM por um vídeo integrado
# (APU), não uma GPU onde o Ollama vá rodar modelo de verdade.
VRAM_MINIMA_GPU_DEDICADA_GB = 2.0

# Maior modelo (memória estimada) que ainda responde num tempo usável
# rodando só na CPU — por volta de um 8B quantizado em Q4.
LIMITE_MODELO_PRATICO_CPU_GB = 7.0


def _detectar_gpu_nvidia():
    if not shutil.which("nvidia-smi"):
        return None

    r = executar_subprocesso(
        [
            "nvidia-smi",
            "--query-gpu=memory.total,memory.free",
            "--format=csv,noheader,nounits",
        ],
        timeout=TIMEOUT_GPU,
    )

    if r["codigo"] != 0 or not r["stdout"]:
        return None

    try:
        # Várias placas: o Ollama divide o modelo entre elas, então o
        # que importa é a soma.
        total_mb = livre_mb = 0
        for linha in r["stdout"].splitlines():
            t, l = linha.split(",")
            total_mb += int(t.strip())
            livre_mb += int(l.strip())

        return {
            "vram_total_gb": round(total_mb / 1024, 1),
            "vram_livre_gb": round(livre_mb / 1024, 1),
            "fabricante": "NVIDIA",
        }

    except Exception:
        return None


def _detectar_gpu_amd(raiz_drm="/sys/class/drm"):
    """Placas AMD (driver amdgpu) informam a VRAM em arquivos do
    sistema — não precisa de ROCm nem de programa nenhum instalado."""

    total = usado = 0

    for dispositivo in sorted(Path(raiz_drm).glob("card[0-9]*/device")):
        try:
            if (dispositivo / "vendor").read_text().strip().lower() != "0x1002":
                continue
            t = int((dispositivo / "mem_info_vram_total").read_text().strip())
            u = int((dispositivo / "mem_info_vram_used").read_text().strip())
        except (OSError, ValueError):
            continue

        if t / 1024**3 < VRAM_MINIMA_GPU_DEDICADA_GB:
            continue  # vídeo integrado (ex: Ryzen 5700G)

        total += t
        usado += u

    if not total:
        return None

    return {
        "vram_total_gb": round(total / 1024**3, 1),
        "vram_livre_gb": round((total - usado) / 1024**3, 1),
        "fabricante": "AMD",
    }


def _detectar_gpu_sem_cache():
    return _detectar_gpu_nvidia() or _detectar_gpu_amd()


def ram_total_gb():
    try:
        return psutil.virtual_memory().total / 1024**3
    except Exception:
        return None  # psutil ausente/limitado: não dá pra saber


def listar_modelos_instalados(forcar=False):
    """Conjunto de modelos que o Ollama realmente tem baixados. Um
    conjunto vazio significa 'não deu pra checar' (Ollama offline) —
    nesse caso o resto do código assume modo aberto (não bloqueia a
    seleção automática por falta de informação)."""

    agora = time.time()

    if (
        not forcar
        and _cache_modelos_instalados["dados"] is not None
        and (agora - _cache_modelos_instalados["ts"]) < CACHE_MODELOS_TTL
    ):
        return _cache_modelos_instalados["dados"]

    try:
        r = _SESSION.get(OLLAMA_TAGS_URL, timeout=TIMEOUT_HTTP_CURTO)

        if r.status_code != 200:
            _cache_modelos_instalados["ts"] = agora  # falhou: não tenta de novo a cada chamada
            if _cache_modelos_instalados["dados"] is None:
                _cache_modelos_instalados["dados"] = set()
            return _cache_modelos_instalados["dados"] or set()

        data = r.json()

        nomes = {
            item.get("name")
            for item in data.get("models", [])
            if item.get("name")
        }
        # impressão digital de cada modelo: o /api/show só precisa ser refeito se ela mudar
        _digests_modelos.clear()
        for item in data.get("models", []):
            if item.get("name"):
                _digests_modelos[item["name"]] = str(item.get("digest") or item.get("modified_at") or "")

        _cache_modelos_instalados["dados"] = nomes
        _cache_modelos_instalados["ts"] = agora

        return nomes

    except Exception:
        # Ollama fora/lento: guarda o que tinha por 10 s (sem isso a janela esperava 5 s a cada chamada)
        if _cache_modelos_instalados["dados"] is None:
            _cache_modelos_instalados["dados"] = set()      # nunca respondeu: também não espera 5 s a cada chamada
        _cache_modelos_instalados["ts"] = agora - CACHE_MODELOS_TTL + 10
        return _cache_modelos_instalados["dados"] or set()


def classificar_encaixe(vram_estimado_gb, gpu_info):
    """Classifica se um modelo (dado seu consumo estimado de VRAM) cabe
    confortavelmente na GPU, precisa de offload parcial pra CPU, ou vai
    rodar majoritariamente na CPU (bem mais lento). Só para exibição —
    quem decide o offload de fato é o próprio Ollama."""

    if vram_estimado_gb is None or not gpu_info:
        return "desconhecido"

    vram_total = gpu_info["vram_total_gb"]

    if vram_estimado_gb <= vram_total - 0.5:
        return "gpu"

    if vram_estimado_gb <= vram_total * 1.5:
        return "misto"

    return "cpu"


_EMOJI_CATEGORIA = {
    "visao": "👁",
    "codigo": "💻",
    "simples": "⚡",
    "geral": "🧠",
}

# Modelos ESPECIALISTAS em programação (qwen2.5-coder, codestral,
# deepseek-coder, codellama...). São ótimos pra escrever código e péssimos
# pra controlar o desktop: recusam abrir apps ou escrevem a chamada da
# ferramenta como texto. Por isso só atendem pedidos de código.
_RE_MODELO_CODIGO = re.compile(r"coder|codestral|starcoder|devstral|codellama|codegemma|codeqwen|(^|[^a-z])code([^a-z]|$)")


_RE_TAG_NUVEM = re.compile(r"[:\-]cloud$", re.I)


def eh_modelo_de_nuvem(tag, info_show=None):
    """Modelo que roda nos servidores do Ollama (gemma4:cloud, gpt-oss:120b-cloud...): o que a pessoa escreve (e os
    prints da tela) SAI do computador. Fica de fora de toda escolha automática (AUTO, ajudante, "/modelo o maior"):
    só vale se a pessoa o escolher pelo nome."""
    info_show = info_show if isinstance(info_show, dict) else {}
    return bool(_RE_TAG_NUVEM.search(str(tag or ""))) or bool(info_show.get("remote_host") or info_show.get("remote_model"))


def eh_modelo_de_codigo(m):
    """O modelo do catálogo é um especialista em código?"""
    if m.get("categoria") == "codigo":
        return True
    return bool(_RE_MODELO_CODIGO.search(f"{m.get('tag', '')} {m.get('familia', '')}".lower()))

# bytes por parâmetro conforme o nível de quantização reportado pelo
# Ollama (details.quantization_level) — usado só pra estimar VRAM;
# aproximado de propósito, o Ollama é quem decide o offload de fato.
_BYTES_POR_PARAM_QUANT = {
    "Q2": 0.4, "Q3": 0.45, "Q4": 0.6, "Q5": 0.7,
    "Q6": 0.8, "Q8": 1.05, "BF16": 2.1, "F16": 2.1, "FP16": 2.1, "F32": 4.2,
}


# /api/show de um modelo só muda se o modelo for baixado de novo (digest novo):
# o resultado fica guardado, e o catálogo (a cada 60 s) deixa de repetir N pedidos.
_digests_modelos = {}
_cache_show = {}


def _show_com_cache(tag):
    digest = _digests_modelos.get(tag)
    guardado = _cache_show.get(tag)
    if digest and guardado and guardado[0] == digest:
        return guardado[1]
    info = _show_modelo(tag)
    if info is not None and digest:
        _cache_show[tag] = (digest, info)
    return info


def _show_modelo(tag):
    """Consulta /api/show pro modelo — parâmetros reais, quantização e
    a lista de capacidades que o próprio Ollama reporta (completion,
    tools, vision, thinking, embedding...). É isso que permite ao TARS
    se adaptar a QUALQUER modelo instalado, em vez de conhecer só uma
    lista fixa de nomes."""

    try:
        r = _SESSION.post(OLLAMA_SHOW_URL, json={"model": tag}, timeout=TIMEOUT_HTTP_MODELO_INFO)

        if r.status_code != 200:
            return None

        return r.json()

    except Exception:
        return None


def _parametros_em_bilhoes(texto):
    """Converte 'parameter_size' (ex: '8.2B', '600M') pra float em
    bilhões de parâmetros. None se não der pra entender."""

    if not texto:
        return None

    m = re.match(r"([\d.]+)\s*([BMK])", texto.strip(), re.IGNORECASE)

    if not m:
        return None

    valor = float(m.group(1))
    unidade = m.group(2).upper()

    if unidade == "B":
        return valor
    if unidade == "M":
        return valor / 1000
    if unidade == "K":
        return valor / 1_000_000

    return None


def _estimar_vram_gb(parametros_b, quantizacao):
    if parametros_b is None:
        return None

    chave = None

    if quantizacao:
        q = quantizacao.upper()
        # Usa as próprias chaves de _BYTES_POR_PARAM_QUANT como lista de
        # prefixos reconhecidos, em vez de repetir os mesmos nomes numa
        # segunda lista solta que precisaria ser mantida em sincronia.
        for prefixo in _BYTES_POR_PARAM_QUANT:
            if q.startswith(prefixo):
                chave = prefixo
                break

    bytes_por_param = _BYTES_POR_PARAM_QUANT.get(chave, 0.6)

    # +0.6GB de folga pra contexto/KV-cache, que não entra no peso
    # bruto dos parâmetros mas ocupa VRAM de verdade.
    return round(parametros_b * bytes_por_param + 0.6, 1)


def _categorizar_modelo(tag, capacidades, parametros_b, familia):
    """Decide pra que tipo de tarefa esse modelo é mais indicado, só
    com base no que o Ollama reporta sobre ele — sem precisar que
    alguém tenha cadastrado esse modelo específico antes.

    Isso é o que permite ao TARS considerar QUALQUER modelo baixado
    (não só uma lista fixa de nomes conhecidos) na hora de escolher
    automaticamente uma IA pra tarefa — qualquer coisa que o usuário
    baixar com 'ollama pull' entra no catálogo e participa da escolha
    a partir da próxima consulta ao catálogo (até CACHE_CATALOGO_TTL
    segundos depois), sem precisar mexer em nenhum código."""

    fam = (familia or "").lower()
    nome = tag.lower()

    # Modelo puramente de embedding (sem 'completion') não consegue
    # participar de uma conversa/tool-calling de jeito nenhum — incluí-
    # lo na cadeia de fallback quebraria o chat se ele fosse escolhido.
    # capacidades vazio (desconhecido) NÃO cai aqui — só quando o
    # Ollama afirma explicitamente que só sabe fazer embedding.
    if capacidades and "embedding" in capacidades and "completion" not in capacidades:
        return "embedding"
    # 21/10: modelo que só gera imagem (x/flux2-klein, x/z-image-turbo...) também não conversa. shortcut: entra na mesma
    # categoria "embedding" (= "não conversa") em vez de uma categoria nova, que pediria mexer em mais de dez filtros.
    if capacidades and "image" in capacidades and "completion" not in capacidades:
        return "embedding"
    if re.search(r"(^|/)(flux|z-image)", nome):
        return "embedding"
    # Ollama antigo não informa capacidades: reconhece pelo nome os modelos
    # de embeddings conhecidos (granite-embedding, nomic-embed-text...).
    if not capacidades and re.search(r"embed|minilm|bge-|paraphrase-multilingual|snowflake-arctic|e5-", nome):
        return "embedding"

    if "vision" in capacidades:
        return "visao"

    if parametros_b is not None and parametros_b <= 1.5:
        return "simples"

    if _RE_MODELO_CODIGO.search(f"{nome} {fam}"):
        return "codigo"

    return "geral"


CACHE_CATALOGO_TTL = 60
_cache_catalogo = {"dados": None, "ts": 0.0}


def catalogar_modelos(forcar=False):
    """Monta um catálogo com TODOS os modelos que o usuário realmente
    tem instalados no Ollama — consultando /api/show de cada um pra
    descobrir parâmetros, quantização e capacidades reais (tools,
    vision, thinking...), em vez de depender de uma lista fixa de
    modelos conhecidos. É isso que faz o TARS se adaptar a qualquer
    conjunto de IAs que o usuário tenha baixado.

    Cacheado (TTL) porque bate um /api/show por modelo instalado —
    rápido (é tudo local), mas não precisa refazer isso a cada
    mensagem."""

    global _cache_catalogo

    agora = time.time()

    if (
        not forcar
        and _cache_catalogo["dados"] is not None
        and (agora - _cache_catalogo["ts"]) < CACHE_CATALOGO_TTL
    ):
        return _cache_catalogo["dados"]

    nomes = listar_modelos_instalados(forcar=forcar)

    if not nomes:
        # Ollama offline ou nada instalado — mantém o catálogo anterior
        # (se houver) em vez de apagar tudo por uma falha passageira.
        return _cache_catalogo["dados"] or {}

    tags_ordenadas = sorted(nomes)

    # Um /api/show por modelo instalado — todos independentes entre si
    # (só leem dados, não mudam estado no Ollama), então rodam em
    # paralelo em vez de sequencialmente. Com poucos modelos o ganho é
    # pequeno, mas cresce direto com quantos o usuário tiver instalado,
    # e o custo de criar as threads é desprezível perto de uma chamada
    # de rede (mesmo local).
    with ThreadPoolExecutor(max_workers=min(8, len(tags_ordenadas)) or 1) as pool:
        infos_show = list(pool.map(_show_com_cache, tags_ordenadas)) if tags_ordenadas else []

    catalogo = {}

    for tag, info_show in zip(tags_ordenadas, infos_show):

        info_show = info_show or {}
        detalhes = info_show.get("details", {}) or {}

        capacidades = set(info_show.get("capabilities") or [])
        parametros_b = _parametros_em_bilhoes(detalhes.get("parameter_size"))
        familia = detalhes.get("family", "") or ""
        quantizacao = detalhes.get("quantization_level", "")

        vram_estimado = _estimar_vram_gb(parametros_b, quantizacao)
        categoria = _categorizar_modelo(tag, capacidades, parametros_b, familia)

        catalogo[tag] = {
            "tag": tag,
            "familia": familia,
            "parametros_b": parametros_b,
            "quantizacao": quantizacao,
            "vram_estimado_gb": vram_estimado,
            "capacidades": capacidades,
            # Se /api/show não respondeu (Ollama antigo sem o campo
            # 'capabilities', por exemplo), não sabemos as capacidades
            # reais — nesse caso o TARS não filtra por elas (modo
            # aberto), em vez de excluir o modelo por falta de dado.
            "capacidades_conhecidas": bool(info_show),
            "categoria": categoria,
            "emoji": _EMOJI_CATEGORIA.get(categoria, "🤖"),
            "nuvem": eh_modelo_de_nuvem(tag, info_show),
        }

    _cache_catalogo = {"dados": catalogo, "ts": agora}

    return catalogo


def modelos_com_capacidade(catalogo, capacidade):
    """Modelos do catálogo que suportam uma capacidade (ex: 'tools',
    'vision'), ou cuja capacidade é desconhecida (não filtra por falta
    de informação) — sempre excluindo modelos de embedding puro, que
    não conseguem participar de chat/tool-calling de jeito nenhum."""

    return [
        m for m in catalogo.values()
        if m["categoria"] != "embedding"
        and (not m["capacidades_conhecidas"] or capacidade in m["capacidades"])
    ]


def modelo_ajudante(catalogo=None):
    """O modelo mais leve disponível com suporte a 'tools' — usado como
    'ajudante' de baixo custo pra resolver nomes de app/site (ver
    perguntar_candidatos_app/perguntar_url_site), em vez de depender de
    um nome fixo que pode nem estar instalado nesta máquina."""

    catalogo = catalogo if catalogo is not None else catalogar_modelos()
    # O Cooper só olha a tela e embedding não conversa: nenhum dos dois resolve nome de app.
    catalogo = {t_: m for t_, m in catalogo.items()
                if m["categoria"] != "embedding" and not visao_lib.e_cooper(t_) and not m.get("nuvem")}

    candidatos = modelos_com_capacidade(catalogo, "tools") or [
        m for m in catalogo.values() if m["categoria"] != "embedding"
    ]

    if not candidatos:
        return MODELO_PADRAO

    candidatos.sort(key=lambda m: m["parametros_b"] if m["parametros_b"] is not None else 999)

    return candidatos[0]["tag"]


_cache_cadeias = {}


_TAREFAS_DO_GARGANTUA = ("acao", "busca", "acao_complexa")


def construir_cadeia_fallback(tarefa, catalogo=None):
    """Ordena os modelos instalados do mais ao menos indicado pra uma
    categoria de tarefa, pelas capacidades e pelo tamanho reais de cada um
    (não por uma lista fixa). O modo AUTO usa a ordem pra escolher e pra
    descer pro próximo se um modelo falhar.

    Regras:
    - especialista em código (qwen2.5-coder...) SÓ atende pedido de código;
      nas outras tarefas só entra se não houver mais nada instalado;
    - quem controla o PC (ação, busca, visão, técnico) precisa de 'tools';
    - modelo que roda devagar demais pra máquina (não cabe na GPU, ou
      grande demais pra CPU) vai pro fim da fila;
    - ação/busca: o menor modelo geral capaz (o suficiente pra acertar a
      ferramenta, sem gastar o mais pesado); código, técnico e geral: o
      maior prático; simples: o menor.

    Cacheado por catálogo: roda a cada mensagem."""

    usar_cache = catalogo is None
    catalogo = catalogo if catalogo is not None else catalogar_modelos()
    chave = (tarefa, _cache_catalogo.get("ts"), _cache_gpu.get("ts"), historico_modelos.versao)
    if usar_cache and chave in _cache_cadeias:
        return list(_cache_cadeias[chave])

    # Modelo de nuvem nunca entra na fila automática (nem como último recurso): o pedido sairia do computador.
    candidatos = [m for m in catalogo.values() if m["categoria"] != "embedding" and not m.get("nuvem")]
    # Os ajudantes não conversam: só entram se não houver mais nada.
    candidatos = [m for m in candidatos if m["tag"] not in MODELOS_AJUDANTES] or candidatos
    # O Cooper nunca conversa, nem como último recurso (ele só responde sobre prints).
    candidatos = [m for m in candidatos if not visao_lib.e_cooper(m["tag"])]
    if not candidatos:
        return []

    def tools(m):
        return (not m["capacidades_conhecidas"]) or ("tools" in m["capacidades"])

    def params(m):
        return m["parametros_b"] if m["parametros_b"] is not None else 0

    gpu_info = detectar_gpu()
    ram_gb = ram_total_gb() if gpu_info is None else None

    def pratico(m):
        """Responde em segundos nesta máquina?"""
        if m.get("vram_estimado_gb") is None:
            return True
        if gpu_info is None:
            if ram_gb is None:
                return True
            return m["vram_estimado_gb"] <= min(LIMITE_MODELO_PRATICO_CPU_GB, ram_gb * 0.6)
        return classificar_encaixe(m["vram_estimado_gb"], gpu_info) in ("gpu", "misto")

    codigo = [m for m in candidatos if eh_modelo_de_codigo(m)]
    outros = [m for m in candidatos if m not in codigo]

    if tarefa == "codigo":
        # Especialista primeiro (o maior que roda bem), depois os gerais.
        ordenados = sorted(codigo, key=lambda m: (pratico(m), params(m)), reverse=True) \
            + sorted(outros, key=lambda m: (pratico(m), tools(m), params(m)), reverse=True)
    else:
        base = outros or candidatos
        if tarefa == "visao":
            # "Veja E clique": modelo que enxerga mas não chama ferramentas
            # só consegue descrever a tela.
            ordenados = sorted(base, key=lambda m: (
                "vision" in m["capacidades"], tools(m), pratico(m), params(m)), reverse=True)
        elif tarefa == "simples":
            ordenados = sorted(base, key=lambda m: (not tools(m), params(m) if m["parametros_b"] is not None else 999))
        elif tarefa in ("acao", "busca"):
            # O menorzinho ("simples") recusa, inventa ou erra a ferramenta:
            # não entra, se houver outro. Modelo com visão costuma ser maior
            # e mais lento sem precisar enxergar: depois dos gerais.
            base = [m for m in base if m["categoria"] != "simples"] or base
            ordenados = sorted(base, key=lambda m: (
                not tools(m), not pratico(m), "vision" in m["capacidades"],
                m["parametros_b"] if m["parametros_b"] is not None else 999))  # tamanho desconhecido: no fim, não no topo
        else:  # "tecnico" (Linux, sistema) e "geral": o maior que roda bem
            ordenados = sorted(base, key=lambda m: (
                tools(m) or tarefa == "geral", pratico(m), params(m)), reverse=True)
        if outros:
            ordenados += sorted(codigo, key=params)  # só se o resto falhar ao carregar

    tags = [m["tag"] for m in ordenados]
    # 4.0: o Gargantua foi treinado pra controlar o PC pelo openTARS: nas
    # ações e buscas ele vai pra frente da fila (se roda bem aqui). Se ele
    # falhar muito neste PC, o histórico abaixo o manda pro fim de novo.
    # TARS_SEM_GARGANTUA=1 desliga a preferência.
    if tarefa in _TAREFAS_DO_GARGANTUA and not gargantua_desligado():
        preferidos = [m["tag"] for m in ordenados if eh_gargantua(m["tag"]) and tools(m) and pratico(m)]
        preferidos.sort(key=ordem_do_gargantua)      # oficial, outros, Code, Lite
        tags = preferidos + [tag for tag in tags if tag not in preferidos]
    elif tarefa == "codigo" and not gargantua_desligado():
        # O Gargantua Code (variante treinada pra programar COM as ferramentas do openTARS) vai na frente nos pedidos de código;
        # o nome dele tem "code", então o catálogo já o conta como especialista em código, e nas outras tarefas ele fica no fim.
        do_code = [m["tag"] for m in ordenados if variante_do_gargantua(m["tag"]) == "code" and tools(m) and pratico(m)]
        tags = do_code + [tag for tag in tags if tag not in do_code]
    # Quem falhou a maioria das últimas vezes NESTA tarefa, neste PC, vai
    # pro fim da fila dela (os de programação continuam por último fora
    # de código).
    tags = historico_modelos.reordenar(
        tags, _tarefa_do_historico(tarefa),
        fixos_no_fim={m["tag"] for m in codigo} if tarefa != "codigo" and outros else (),
    )
    if usar_cache:
        if len(_cache_cadeias) > 64:
            _cache_cadeias.clear()
        _cache_cadeias[chave] = tags
    return list(tags)


def formatar_parametros(bilhoes):
    """0.75163 → '752M', 8.19 → '8.2B', 24.0 → '24B'."""
    if bilhoes < 1:
        return f"{round(bilhoes * 1000)}M"
    texto = f"{bilhoes:.1f}".rstrip("0").rstrip(".")
    return f"{texto}B"


def _imprimir_lista_modelos():
    """Fonte única usada tanto na tela inicial quanto no comando
    /modelo — lista dinamicamente o que está de fato instalado no
    Ollama, com as capacidades e estimativas de cada modelo."""

    gpu_info = detectar_gpu(forcar=True)
    catalogo = catalogar_modelos()

    if gpu_info:
        print(t(
            "lista.gpu", fabricante=gpu_info.get("fabricante") or "GPU",
            total=gpu_info["vram_total_gb"], livre=gpu_info["vram_livre_gb"],
        ))
    else:
        print(t("lista.sem_gpu"))

    print()

    if not catalogo:
        print(c(t("lista.nenhum_modelo"), Cor.AMARELO))
        print()
        return

    # Agrupa por categoria só pra exibição ficar organizada (visão,
    # técnico, simples, geral) — cada IA aparece do maior pro menor
    # dentro da própria categoria.
    ordem_categorias = ["visao", "codigo", "geral", "simples"]

    for categoria in ordem_categorias:

        modelos_cat = [
            m for m in catalogo.values()
            if m["categoria"] == categoria and m["tag"] not in MODELOS_AJUDANTES
        ]

        if not modelos_cat:
            continue

        modelos_cat.sort(
            key=lambda m: m["parametros_b"] if m["parametros_b"] is not None else 0,
            reverse=True,
        )

        for info in modelos_cat:

            encaixe = classificar_encaixe(info["vram_estimado_gb"], gpu_info)
            marcador = t(f"encaixe.{encaixe}") if encaixe != "desconhecido" else ""

            capacidades_visiveis = sorted(
                info["capacidades"] & _CAPACIDADES_RELEVANTES
            )

            print(f"  {info['emoji']} {info['tag']}")

            detalhe_linha = t(f"categoria.{categoria}")
            if info["familia"]:
                detalhe_linha = f"{info['familia']} — {detalhe_linha}"
            print(f"     {detalhe_linha}")

            if info["parametros_b"] is not None:
                linha = f"     ~{formatar_parametros(info['parametros_b'])} params"
                if info["vram_estimado_gb"] is not None:
                    linha += f", ~{info['vram_estimado_gb']}GB VRAM"
                if marcador:
                    linha += f" — {marcador}"
                print(linha)

            if capacidades_visiveis:
                print(f"     {t('lista.capacidades')}: {', '.join(capacidades_visiveis)}")

            print()

    n_embedding = sum(1 for m in catalogo.values() if m["categoria"] == "embedding")

    if n_embedding:
        print(c(f"  ({t('lista.embeddings', n=n_embedding)})", Cor.CINZA))
        print()
