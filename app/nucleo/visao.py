# openTARS — nucleo/visao.py
# A visão da tela. Era o Cooper (descontinuado em 18/10/2026); agora é o próprio Gargantua 2
# (ollama pull ProjectOpenTARS/Gargantua-2), que responde no mesmo formato. As perguntas e a leitura das
# respostas ficam em tars_visao.py; aqui está a conversa com o Ollama e o
# encaixe no clique (por nome ou ícone) e na descrição da tela.
#
# Parte do núcleo: o tars.py executa este arquivo DENTRO do próprio
# namespace (ver _carregar_nucleo). Usa _chat_unico e _ultimo_erro (ollama),
# catalogar_modelos (hardware) e time/io/base64/re em tempo de execução.
# flake8: noqa

# ============================================================
# COOPER
# ============================================================

# Num clique com x/y já dados pela IA, o ponto do Cooper só vale se cair a
# esta distância (px) do que ela indicou; senão, vale o x/y da IA.
DISTANCIA_MAXIMA_VISAO_PX = 220

# 1ª pergunta (modelo ainda carregando, às vezes trocando de lugar com outro
# na placa de vídeo) tem mais prazo que as seguintes.
# O prazo era 90 s e a resposta não tinha limite de tamanho: numa descrição de
# tela o Cooper (2B, treinado pra respostas curtas) podia escrever sem parar
# até estourar. Agora a resposta tem teto de tokens e o prazo é folgado, como
# o do modelo de visão geral sempre foi.
TIMEOUT_VISAO_FRIO = 300
TIMEOUT_VISAO_QUENTE = 120
# Contexto fixo e pequeno: cabe o print + a resposta, gasta pouca VRAM (o
# Cooper fica na placa junto do modelo da conversa) e não recarrega.
CONTEXTO_VISAO = 4096
TOKENS_VISAO_PONTO = 64
TOKENS_VISAO_DESCRICAO = 400
# Se o Cooper estourou o prazo, ele descansa este tempo (s): sem isso cada
# passo da tarefa esperaria o prazo inteiro de novo.
PAUSA_VISAO_LENTO = 240

_visao_estado = {"quente": False, "pausado_ate": 0.0, "erro": ""}


def visao_instalada():
    """A tag do Cooper no Ollama (ou None se não está instalado ou está desligado)."""
    if not visao_lib.ligado():
        return None
    try:
        return visao_lib.achar_instalado(list(catalogar_modelos().keys()))
    except Exception:
        return None


def visao_disponivel():
    """A tag do Cooper pronta pra uso agora: instalado, ligado e fora da
    pausa que ele leva depois de estourar o prazo."""
    if time.time() < _visao_estado["pausado_ate"]:
        return None
    return visao_instalada()


def motivo_da_falha_da_visao():
    return _visao_estado["erro"] or "no answer"


def _opcoes_visao(max_tokens, tag=None):
    if visao_lib.e_gargantua_2(tag):
        # O Gargantua 2 é o mesmo modelo da conversa: o MESMO num_ctx (o _chat_unico já usa contexto_ia(); outro valor faria o
        # Ollama recarregar o modelo a cada olhada) e as opções do Modelfile (a prova de visão foi medida com elas).
        return {"num_predict": max_tokens}
    return {"num_ctx": CONTEXTO_VISAO, "num_predict": max_tokens, "repeat_penalty": 1.15}


def _visao_cabe_junto(tag):
    """O Cooper cabe na placa AO LADO do maior modelo de conversa instalado?
    Se não cabe, carregar ele ao abrir só expulsa o modelo da conversa (ou é
    expulso por ele): o 1º pedido ficava esperando uma recarga à toa."""
    try:
        gpu = detectar_gpu()
        catalogo = catalogar_modelos()
        meu = (catalogo.get(tag) or {}).get("vram_estimado_gb")
        outros = [m.get("vram_estimado_gb") for m in catalogo.values()
                  if not visao_lib.e_cooper(m["tag"]) and m.get("categoria") != "embedding"
                  and m.get("vram_estimado_gb") is not None]
        if not gpu or meu is None or not outros:
            return False
        return meu + max(outros) + 0.7 <= gpu["vram_total_gb"]
    except Exception:
        return False


def aquecer_visao():
    """Carrega o Cooper em segundo plano ao abrir o openTARS, pra a 1ª
    olhada na tela não pagar a carga do modelo."""
    def _carregar():
        try:
            tag = visao_instalada()
            if not tag or visao_lib.e_gargantua_2(tag) or not _visao_cabe_junto(tag):
                return          # o Gargantua 2 já é o modelo da conversa: aquecer_modelo_da_conversa cuida dele
            r = _SESSION.post(OLLAMA_GENERATE_URL, timeout=TIMEOUT_VISAO_FRIO, json={
                "model": tag, "prompt": "", "keep_alive": KEEP_ALIVE_VISAO,
                "options": {"num_ctx": CONTEXTO_VISAO}})
            if r.status_code == 200:
                _visao_estado["quente"] = True
        except Exception:
            pass
    threading.Thread(target=_carregar, daemon=True).start()


def _imagem_em_b64(imagem):
    # Tela 4K inteira é lenta no Cooper (e estoura o prazo na placa de 6 GB). A resposta vem em
    # milésimos da imagem, então reduzir não muda a posição.
    try:
        if imagem.width > LARGURA_MAXIMA_SCREENSHOT:
            imagem = imagem.resize((LARGURA_MAXIMA_SCREENSHOT, max(1, round(imagem.height * LARGURA_MAXIMA_SCREENSHOT / imagem.width))))
    except Exception:
        pass
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG", compress_level=1)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def perguntar_visao(tag, pergunta, imagem=None, imagem_b64=None, max_tokens=TOKENS_VISAO_PONTO):
    """Resposta do Cooper (texto) ou None se o Ollama não respondeu (o
    motivo fica em motivo_da_falha_da_visao). Falha rápida (erro, não prazo
    estourado) ganha uma segunda tentativa; prazo estourado põe o Cooper em
    pausa pra não travar os passos seguintes."""
    b64 = imagem_b64 or _imagem_em_b64(imagem)
    prazo = TIMEOUT_VISAO_QUENTE if _visao_estado["quente"] else TIMEOUT_VISAO_FRIO
    for tentativa in range(2):
        _ultimo_erro["texto"] = ""
        inicio = time.time()
        resposta = _chat_unico(tag, pergunta, temperatura=0.0, timeout=prazo,
                               keep_alive=KEEP_ALIVE if visao_lib.e_gargantua_2(tag) else KEEP_ALIVE_VISAO, imagens=[b64],
                               opcoes=_opcoes_visao(max_tokens, tag))
        if resposta:
            _visao_estado["quente"] = True
            _visao_estado["erro"] = ""
            return resposta
        gasto = time.time() - inicio
        _visao_estado["erro"] = _ultimo_erro["texto"] or "empty answer"
        if gasto >= prazo * 0.9 or "timed out" in _visao_estado["erro"].lower():
            _visao_estado["quente"] = False
            _visao_estado["pausado_ate"] = time.time() + PAUSA_VISAO_LENTO
            break  # estourou o prazo: não adianta repetir
        if gasto > 8:
            break
    return None


def localizar_com_visao(nome, imagem, tag=None):
    """O centro do elemento 'nome' na imagem, em pixels DELA: ((x, y), tag),
    ("ausente", tag) se o Cooper diz que não está na tela, ou (None, None)."""
    tag = tag or visao_disponivel()
    if not tag:
        return None, None
    try:
        resposta = perguntar_visao(tag, visao_lib.pergunta_localizar(nome), imagem=imagem)
    except Exception as e:
        _visao_estado["erro"] = str(e)[:200]
        return None, None
    lido = visao_lib.ler_ponto(resposta)
    if lido is None:
        if resposta:
            _visao_estado["erro"] = "unreadable answer"
        return None, None
    if lido[0] == "ausente":
        return "ausente", tag
    largura, altura = imagem.size
    return visao_lib.para_pixels(lido[1], lido[2], largura, altura), tag


def mirar_com_visao(alvo, imagem, perto_de=None):
    """(x, y, como) em pixels da imagem; "ausente" se o Cooper olhou e o
    alvo não está na tela; ou None (sem Cooper, falhou ou ficou longe do
    ponto que a IA tinha indicado)."""
    ponto, tag = localizar_com_visao(alvo, imagem)
    if ponto == "ausente":
        return "ausente"
    if not isinstance(ponto, tuple):
        return None
    if perto_de is not None:
        distancia = ((ponto[0] - perto_de[0]) ** 2 + (ponto[1] - perto_de[1]) ** 2) ** 0.5
        if distancia > DISTANCIA_MAXIMA_VISAO_PX:
            return None
    return ponto[0], ponto[1], f"located '{alvo}' by looking at the screen"


def descrever_com_visao(imagem_b64, pedido):
    """(texto com posições em pixels, tag) feito pelo Cooper, ou (None, None)
    se não há Cooper ou ele não respondeu."""
    tag = visao_disponivel()
    if not tag:
        return None, None
    try:
        from PIL import Image
        with Image.open(io.BytesIO(base64.b64decode(imagem_b64))) as img:
            largura, altura = img.size
        bruto = perguntar_visao(tag, visao_lib.pergunta_descrever(pedido), imagem_b64=imagem_b64,
                                 max_tokens=TOKENS_VISAO_DESCRICAO)
    except Exception as e:
        _visao_estado["erro"] = str(e)[:200]
        return None, None
    if not bruto:
        return None, None
    if not re.search(r"\(\s*\d+(?:\.\d+)?\s*,\s*\d+(?:\.\d+)?\s*\)|\"x\"\s*:", bruto):
        return (f"[The {largura}x{altura} screenshot, described without positions. To click, use click_element(name) "
                f"or click_mouse(x, y, target=<what it is>).]\n{bruto.strip()}"), tag
    texto = visao_lib.descricao_em_pixels(bruto, largura, altura)
    return (f"[Positions are pixel coordinates of this {largura}x{altura} image, origin at the top-left.]\n{texto}"), tag
