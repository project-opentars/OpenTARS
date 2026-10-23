# openTARS — nucleo/anexos.py
# 4.5 Endurance: arquivos anexados ao pedido (botão 📎 da janela, /anexar e
# @arquivo no terminal). A leitura de cada arquivo está em tars_anexos.py; aqui
# fica o encaixe no pedido: o conteúdo entra na mensagem, a imagem vai pra um
# modelo que enxerga (ou é descrita por um modelo de visão se o escolhido não
# enxerga) e o contexto da IA sobe se os anexos forem grandes.
#
# Parte do núcleo: o tars.py executa este arquivo DENTRO do próprio
# namespace (ver _carregar_nucleo). Vem depois de "chat".
# flake8: noqa

# ============================================================
# ANEXOS
# ============================================================

TEXTO_PEDIDO_SO_ANEXOS = "Look at the attached file(s) and tell me what they contain."
TOKENS_PROMPT_BASE = 5500           # prompt do openTARS + ferramentas + folga pra resposta e histórico
TOKENS_POR_IMAGEM = 1500
CHARS_POR_TOKEN = 3
CONTEXTO_MAXIMO_ANEXOS = int(os.environ.get("TARS_CONTEXTO_MAXIMO", "0") or 0)
_DEGRAUS_CONTEXTO = (8192, 12288, 16384, 24576, 32768, 49152, 65536)


def contexto_maximo_para_anexos():
    """Até onde o contexto pode subir por causa dos anexos: 16 mil tokens
    (32 mil com GPU de 16 GB ou mais), ou TARS_CONTEXTO_MAXIMO."""
    if CONTEXTO_MAXIMO_ANEXOS:
        return CONTEXTO_MAXIMO_ANEXOS
    try:
        gpu = detectar_gpu()
    except Exception:
        gpu = None
    return 32768 if gpu and gpu["vram_total_gb"] >= 16 else 16384


def orcamento_de_texto_dos_anexos():
    """Quantos caracteres de anexos cabem num pedido (o que o contexto máximo deixa livre)."""
    sobra = contexto_maximo_para_anexos() - TOKENS_PROMPT_BASE
    return max(6000, min(80000, sobra * CHARS_POR_TOKEN))


def _garantir_contexto(tokens):
    """Sobe o num_ctx (até o máximo) pra caber 'tokens' de anexos; não desce."""
    precisa = TOKENS_PROMPT_BASE + int(tokens)
    teto = contexto_maximo_para_anexos()
    alvo = next((d for d in _DEGRAUS_CONTEXTO if d >= precisa), _DEGRAUS_CONTEXTO[-1])
    alvo = min(alvo, teto)
    if alvo > _contexto_minimo["n"] and alvo > 8192:
        _contexto_minimo["n"] = alvo


def _descrever_imagem_anexada(anexo, pedido, modelo_atual):
    """Um modelo que não enxerga: o modelo de visão (se instalado) descreve a imagem em texto. Sem ele, só o aviso."""
    try:
        descricao, _tag = descrever_com_visao(anexo.imagem_b64, pedido)
    except Exception:
        descricao = None
    if descricao:
        print(c(f"[openTARS] {t('msg.descrevendo_tela', modelo=modelo_atual, visao=_tag)}", Cor.AMARELO))
    return descricao


def montar_mensagem_com_anexos(texto, anexos, modelo):
    """(conteúdo, imagens) da mensagem do usuário com os anexos. Imagens vão
    como imagem se o modelo enxerga; senão viram texto (descritas por um
    modelo de visão) ou, sem nenhum, só o nome."""
    texto = (texto or "").strip() or TEXTO_PEDIDO_SO_ANEXOS
    imagens, descricoes = [], {}
    enxerga = modelo_enxerga(modelo)
    for a in anexos:
        if a.tipo != "imagem":
            continue
        if enxerga:
            imagens.append(a.imagem_b64)
            continue
        descricao = _descrever_imagem_anexada(a, texto, modelo)
        if descricao:
            descricoes[a.caminho] = descricao
        else:
            a.avisos.append("you cannot see images and no vision model is installed (ollama pull gemma3:4b "
                            "or qwen3-vl:2b), so tell the user you can't see this image")
    limite = orcamento_de_texto_dos_anexos()
    bloco = anexos_lib.montar_bloco(anexos, descricoes, limite_total=limite)
    _garantir_contexto(len(bloco) / CHARS_POR_TOKEN + TOKENS_POR_IMAGEM * len(imagens))
    return f"{texto}\n\n{bloco}", imagens


def anexar_arquivos(entradas, ja_anexados=()):
    """([Anexo], [erros]) — pro terminal e pra janela."""
    return anexos_lib.carregar_varios(entradas, ja_anexados=ja_anexados)
