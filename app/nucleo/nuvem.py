# openTARS — nucleo/nuvem.py
# 5.0 Tesseract: nuvem opcional (qualquer servidor compatível com a API da OpenAI:
# Ollama Cloud, Groq, Cerebras, outro). A parte da API (formato da conversa, streaming)
# fica em tars_openai.py; o endereço e a chave, em tars_primeiro_uso.py (nuvem.json, 0600).
#
# Regras de privacidade:
#  - desligada por padrão; só vale se a pessoa ligou e pôs a própria chave;
#  - modelo da nuvem NUNCA entra na escolha automática (nem no catálogo): só quando a
#    pessoa o escolhe na mão ("api:<nome>"). O que ela escreve só sai do computador
#    se ela escolheu isso.
# Parte do núcleo: executada dentro do namespace do tars.py (ver _carregar_nucleo).
# flake8: noqa

_cache_modelos_nuvem = {"dados": None, "ts": 0.0, "url": None}


def nuvem_config():
    """{'ativa', 'provedor', 'endereco', 'chave'}; a variável TARS_CHAVE_API vale mais que o arquivo."""
    dados = primeiro_uso.carregar_nuvem()
    chave_ambiente = os.environ.get("TARS_CHAVE_API")
    if chave_ambiente:
        dados = dict(dados, chave=chave_ambiente)
    return dados


def servidor_api():
    """Endereço da nuvem em uso, ou '' (desligada ou sem endereço/chave)."""
    dados = nuvem_config()
    if not (dados["ativa"] and dados["endereco"] and dados["chave"]):
        return ""
    return dados["endereco"].rstrip("/")


def _cabecalhos_api():
    chave = nuvem_config()["chave"]
    return {"Authorization": f"Bearer {chave}"} if chave else {}


def listar_modelos_api(forcar=False):
    """{'api:<nome>', ...} da nuvem (vazio se desligada ou fora do ar)."""
    url = servidor_api()
    if not url:
        return set()
    agora = time.time()
    cache = _cache_modelos_nuvem
    if not forcar and cache["url"] == url and cache["dados"] is not None and agora - cache["ts"] < CACHE_MODELOS_TTL:
        return cache["dados"]
    try:
        r = _SESSION.get(f"{url}/models", headers=_cabecalhos_api(), timeout=TIMEOUT_HTTP_CURTO)
        dados = {api.PREFIXO + i for i in api.ler_modelos(r.json())} if r.status_code == 200 else set()
    except Exception:
        dados = set()
    cache.update(dados=dados, ts=agora, url=url)
    return dados


def _post_api(corpo, stream=False, timeout=TIMEOUT_HTTP_LONGO):
    return _SESSION.post(f"{servidor_api()}/chat/completions", json=corpo, headers=_cabecalhos_api(),
                         timeout=timeout, stream=stream)


def _chat_unico_api(modelo, prompt, temperatura, timeout, formato, imagens, antes):
    mensagens = list(antes or []) + [{"role": "user", "content": prompt, **({"images": imagens} if imagens else {})}]
    corpo = api.corpo_chat(modelo, mensagens, stream=False, temperatura=temperatura, formato=formato)
    try:
        r = _post_api(corpo, timeout=timeout)
        if r.status_code != 200 and "response_format" in corpo:  # servidor sem JSON schema
            corpo.pop("response_format")
            r = _post_api(corpo, timeout=timeout)
        if r.status_code != 200:
            return None
        texto = api.resposta_unica(r.json())
    except Exception:
        return None
    return re.sub(r"<think>.*?</think>", "", texto or "", flags=re.DOTALL).strip() if texto is not None else None


def _turno_api(modelo, mensagens, tools, pensar=True):
    """Igual a _executar_turno_streaming, na nuvem: mesmos eventos na tela, mesma resposta
    (conteúdo, pensamento, chamadas no formato do Ollama)."""
    if not servidor_api():
        return None, t("msg.nuvem_desligada")
    corpo = api.corpo_chat(modelo, mensagens, tools=tools, stream=True, temperatura=temperatura_conversa())
    try:
        resposta = _post_api(corpo, stream=True)
        if resposta.status_code != 200 and tools and resposta.status_code in (400, 422):
            detalhe = resposta.text[:300]
            if "tool" in detalhe.lower():
                resposta.close()
                _MODELOS_SEM_TOOLS.add(modelo)
                corpo.pop("tools", None)
                resposta = _post_api(corpo, stream=True)
        if resposta.status_code != 200:
            detalhe = resposta.text[:300].strip()
            codigo = resposta.status_code
            resposta.close()
            if codigo in (401, 403):
                return None, t("msg.nuvem_chave")
            if codigo == 429:
                return None, t("msg.nuvem_limite")
            return None, t("msg.erro_servidor_api", codigo=codigo, detalhe=detalhe)
    except requests.exceptions.ConnectionError:
        return None, t("msg.servidor_api_offline", url=servidor_api())
    except Exception as e:
        return None, t("msg.erro_streaming", erro=e)

    leitor = api.LeitorStream()
    pensando_ativo = escrevendo_ativo = False
    _resposta_ativa["r"] = resposta
    try:
        for linha in resposta.iter_lines():
            if _cancelar.is_set():
                resposta.close()
                if pensando_ativo or escrevendo_ativo:
                    emitir("fim_stream")
                raise RespostaCancelada()
            for tipo, valor in leitor.alimentar(linha):
                if tipo == "pensamento" and pensar:
                    emitir("pensamento", texto=valor, inicio=not pensando_ativo)
                    pensando_ativo = True
                elif tipo == "resposta":
                    emitir("resposta", texto=valor, inicio=not escrevendo_ativo, apos_pensamento=pensando_ativo)
                    escrevendo_ativo = True
                elif tipo == "erro":
                    return None, t("msg.erro_servidor_api", codigo="stream", detalhe=valor)
            if leitor.terminou:
                break
    except RespostaCancelada:
        raise
    except Exception as e:
        if _cancelar.is_set():
            if pensando_ativo or escrevendo_ativo:
                emitir("fim_stream")
            raise RespostaCancelada()
        return None, t("msg.erro_streaming", erro=e)
    finally:
        _resposta_ativa["r"] = None
        resposta.close()

    if pensando_ativo or escrevendo_ativo:
        emitir("fim_stream")
    if not (leitor.terminou or leitor.motivo):
        # a conexão acabou no meio: uma chamada de ferramenta cortada ({"app":"fir) viraria execução com argumentos vazios
        return None, t("msg.erro_streaming", erro="connection closed before the answer was complete")
    if leitor.motivo == "length":
        print(c(f"\n[openTARS] {t('msg.limite_contexto', tokens=contexto_ia())}", Cor.AMARELO))
    conteudo = re.sub(r"<think>.*?</think>", "", "".join(leitor.conteudo), flags=re.DOTALL).strip()
    return {"content": conteudo, "thinking": "".join(leitor.pensamento).strip(),
            "tool_calls": leitor.chamadas}, None
