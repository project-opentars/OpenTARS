# openTARS — nucleo/ollama.py
# Conversa com o servidor do Ollama: pedidos, streaming, carregar e descarregar modelos.
#
# Parte do núcleo: o tars.py executa este arquivo DENTRO do próprio
# namespace (ver _carregar_nucleo), então tudo aqui é tars.<nome> e as
# partes enxergam umas às outras sem import. Os testes que trocam
# tars.<função> por uma falsa continuam valendo pra todas as partes.
# flake8: noqa

# ============================================================
# OLLAMA
# ============================================================

# Por que a última pergunta pontual falhou (pra mostrar ao usuário em vez de um "não respondeu" mudo).
_ultimo_erro = {"texto": ""}

# TARS_TEMPOS=0 esconde as linhas de tempo (carga / imagem / resposta) de cada chamada.
MOSTRAR_TEMPOS = os.environ.get("TARS_TEMPOS", "1") not in ("0", "off", "no", "nao")


def _resumo_de_tempos(dados, total):
    """"7.9s (carga 5.2s, leitura 1.1s, resposta 1.5s p/ 64 tokens)" a partir do que o
    Ollama devolve (durações em nanossegundos). Mostra onde o tempo foi: modelo
    sendo carregado na placa, imagem/prompt sendo lido ou texto sendo gerado."""
    ns = lambda k: float((dados or {}).get(k) or 0) / 1e9
    partes = []
    if ns("load_duration") >= 0.3:
        partes.append(f"load {ns('load_duration'):.1f}s")
    if ns("prompt_eval_duration") >= 0.3:
        partes.append(f"read {ns('prompt_eval_duration'):.1f}s")
    if ns("eval_duration") >= 0.3:
        partes.append(f"answer {ns('eval_duration'):.1f}s/{(dados or {}).get('eval_count', '?')} tok")
    return f"{total:.1f}s" + (f" ({', '.join(partes)})" if partes else "")


def _registrar_erro(texto):
    _ultimo_erro["texto"] = str(texto)[:200]


def ollama_request(payload, stream=False, timeout=TIMEOUT_HTTP_LONGO):
    return _SESSION.post(
        OLLAMA_URL,
        json=payload,
        timeout=timeout,
        stream=stream,
    )


def _chat_unico(
    modelo,
    prompt,
    temperatura=TEMPERATURA_AJUDANTE,
    timeout=TIMEOUT_HTTP_AJUDANTE,
    keep_alive=KEEP_ALIVE_AJUDANTE,
    formato=None,
    imagens=None,
    antes=None,
    opcoes=None,
):
    """Uma pergunta isolada e não-streaming a um modelo, sem tocar no
    histórico de conversa principal nem em qual modelo está 'ativo' —
    usada por toda consulta pontual e de baixo custo que o TARS faz a
    uma IA leve (resolver nome de app/site, classificar tarefa,
    resolver troca de modelo por descrição livre). Centraliza aqui o
    try/except e o parsing da resposta, que antes se repetiam em cada
    uma dessas funções com um timeout diferente (e, num caso, sem
    timeout curto nenhum). Devolve o texto de resposta já sem espaços
    nas pontas, ou None em qualquer falha (Ollama offline, timeout,
    resposta malformada etc.) — quem chamou decide o que fazer na
    ausência de resposta."""

    if api.eh_modelo_api(modelo):
        return _chat_unico_api(modelo, prompt, temperatura, timeout, formato, imagens, antes)

    corpo = {
        "model": modelo,
        # antes: mensagens fixas antes da pergunta (system, exemplos resolvidos).
        "messages": list(antes or []) + [{"role": "user", "content": prompt, **({"images": imagens} if imagens else {})}],
        "stream": False,
        "keep_alive": keep_alive,
        "options": {"temperature": temperatura},
    }
    if not visao_lib.e_cooper(modelo):
        # mesmo num_ctx do chat: senão o Ollama recarrega o modelo a cada consulta de bastidor
        corpo["options"]["num_ctx"] = contexto_ia()
    if opcoes:
        corpo["options"].update(opcoes)

    # Pergunta curta não precisa de raciocínio: num modelo que "pensa"
    # (qwen3), deixar ligado multiplica o tempo e pode vazar <think> na
    # resposta que o openTARS tenta interpretar.
    info = (_cache_catalogo.get("dados") or {}).get(modelo)
    # 18/10: o Gargantua 2 (Qwen3.5) pensa por padrão e gasta os tokens da resposta pensando (resposta VAZIA). Um modelo recém
    # exportado ainda não está no catálogo em cache: pelo NOME já se sabe, sem depender do cache.
    if (info and "thinking" in info.get("capacidades", ())) or visao_lib.e_gargantua_2(modelo):
        corpo["think"] = False

    # Resposta forçada num formato (JSON schema): um modelo pequeno não
    # consegue "responder qualquer coisa" — só um valor válido.
    if formato:
        corpo["format"] = formato

    _t0 = time.time()
    try:
        resposta = _SESSION.post(OLLAMA_URL, json=corpo, timeout=timeout)
        # Ollama antigo sem suporte a think/format: tenta sem eles.
        for extra in ("think", "format"):
            if resposta.status_code == 200 or extra not in corpo:
                continue
            corpo.pop(extra)
            resposta = _SESSION.post(OLLAMA_URL, json=corpo, timeout=timeout)
    except Exception as e:
        _registrar_erro(e)
        return None

    if resposta.status_code != 200:
        try:
            detalhe = (resposta.json() or {}).get("error") or ""
        except Exception:
            detalhe = ""
        _registrar_erro(f"HTTP {resposta.status_code} {detalhe}".strip())
        return None

    try:
        dados_resposta = resposta.json()
        texto = dados_resposta.get("message", {}).get("content") or ""
    except Exception as e:
        _registrar_erro(e)
        return None
    if MOSTRAR_TEMPOS and (time.time() - _t0) >= 1.5:
        print(c(f"[openTARS] {modelo}: {_resumo_de_tempos(dados_resposta, time.time() - _t0)}", Cor.CINZA))

    return re.sub(r"<think>.*?</think>", "", texto, flags=re.DOTALL).strip()


def _json_da_resposta(texto):
    """Lê o JSON devolvido pelo ajudante (ou o primeiro {...} no texto,
    se veio algo em volta). None se não houver JSON."""
    if not texto:
        return None
    try:
        return json.loads(texto)
    except Exception:
        pass
    m = re.search(r"\{.*\}", texto, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def aquecer_ajudante():
    """Antes carregava a Murph e o Cooper ao abrir o openTARS, ocupando RAM e VRAM
    mesmo sem ninguém usar. Agora tudo é carregado só na hora em que um pedido precisa
    (a Murph leva ~0,3 s; o Cooper, o tempo da placa). TARS_PRECARGA=1 volta ao
    comportamento antigo."""
    if not PRECARGA:
        return
    threading.Thread(target=murph.preparar, daemon=True).start()
    try:
        aquecer_visao()
    except Exception:
        pass


_ultimo_aquecimento = {"em": 0.0}


def aquecer_modelo_da_conversa():
    """Chamada quando o usuário começa a digitar: pede ao Ollama pra ter o modelo da
    conversa pronto (se ele já saiu da memória por ociosidade) enquanto a pessoa ainda
    escreve. Vazia e barata se ele já está carregado; no máximo uma vez a cada 30 s;
    não faz nada sem modelo escolhido."""
    agora = time.time()
    modelo = (modelo_manual if modo_modelo == "MANUAL" else None) or modelo_atual
    if not modelo or agora - _ultimo_aquecimento["em"] < 30:
        return
    _ultimo_aquecimento["em"] = agora

    def _pedir():
        try:
            _SESSION.post(OLLAMA_GENERATE_URL, timeout=TIMEOUT_HTTP_LONGO, json={
                "model": modelo, "prompt": "", "keep_alive": KEEP_ALIVE,
                "options": {"num_ctx": contexto_ia()}})
        except Exception:
            pass
    threading.Thread(target=_pedir, daemon=True).start()


def descarregar_modelo(modelo):
    """Pede ao Ollama para descarregar um modelo (keep_alive=0).
    Retorna True se a chamada foi aceita — isso NÃO garante que o
    modelo já saiu da memória, só que o Ollama recebeu o pedido; a
    confirmação de verdade é feita via /api/ps em encerrar_todas_ias."""

    if not modelo:
        return False
    if api.eh_modelo_api(modelo):
        return True  # nuvem: nada na memória deste computador

    try:
        r = _SESSION.post(
            OLLAMA_GENERATE_URL,
            json={
                "model": modelo,
                "prompt": "",
                "keep_alive": 0,
            },
            timeout=TIMEOUT_HTTP_DESCARREGAR,
        )
        return r.status_code == 200
    except Exception:
        return False


def ollama_online():
    """O servidor do Ollama responde no endereço configurado?"""
    try:
        return _SESSION.get(f"{OLLAMA_HOST}/api/version", timeout=TIMEOUT_HTTP_CURTO).status_code == 200
    except Exception:
        return False


def avisos_de_ambiente():
    """Problemas do ambiente que o usuário precisa saber logo ao abrir,
    em vez de descobrir quando um comando falhar."""

    avisos = []

    if not ollama_online():
        avisos.append(t("aviso.ollama_offline", host=OLLAMA_HOST))
        if EM_WSL and not os.environ.get("OLLAMA_HOST"):
            avisos.append(t("diag.wsl_sem_ollama"))

    if SEM_INTERFACE:
        # 4.5: sem tela não é defeito: é o modo terminal
        avisos.append(t("aviso.modo_sem_interface"))
    elif ERRO_PYAUTOGUI:
        motivo = t("aviso.sem_display") if SESSAO_GRAFICA == "nenhuma" else ERRO_PYAUTOGUI
        avisos.append(t("aviso.sem_mouse", motivo=motivo))
    elif SESSAO_GRAFICA == "wayland":
        if not ENTRADA_WAYLAND:
            avisos.append(t("aviso.wayland") + " " + t("aviso.wayland_ydotool", motivo=MOTIVO_SEM_YDOTOOL or "-"))

    return avisos


def listar_modelos_rodando():
    """Consulta o Ollama (endpoint /api/ps) pelos modelos que estão de
    fato carregados na memória agora — não só o que o TARS acha que
    carregou (útil se algo foi carregado fora do script, ex: via
    Open WebUI ou `ollama run` manual).

    Retorna um set com os nomes, ou None se não foi possível checar
    (Ollama offline/inacessível) — distinguir isso de "nenhum modelo
    rodando" é importante pra não confirmar um desligamento à toa."""

    try:
        r = _SESSION.get(OLLAMA_PS_URL, timeout=TIMEOUT_HTTP_CURTO)

        if r.status_code != 200:
            return None

        data = r.json()

        return {
            item.get("name")
            for item in data.get("models", [])
            if item.get("name")
        }

    except Exception:
        return None


def encerrar_todas_ias(
    max_tentativas=TENTATIVAS_ENCERRAR_IAS,
    espera_seg=ESPERA_ENTRE_TENTATIVAS_ENCERRAR_SEG,
    so_do_tars=False,
):
    """Descarrega da memória (VRAM/RAM) todo modelo Ollama em execução
    — não só o que o TARS tem marcado como atual — e CONFIRMA via
    /api/ps que cada um realmente saiu antes de declarar sucesso,
    tentando de novo algumas vezes se algum ainda aparecer rodando.
    Usado no comando manual 'encerrar todas llms' (todos os modelos) e ao
    fechar o TARS (so_do_tars=True: só os que ele mesmo carregou, pra não
    derrubar o modelo de outro programa que usa o mesmo Ollama)."""

    global modelo_atual

    with lock_modelo:

        rodando = listar_modelos_rodando()

        if rodando is None:
            print(c(f"\n[openTARS] {t('msg.ollama_sem_contato')}", Cor.AMARELO))
            modelo_atual = None
            return {"sucesso": False, "encerrados": [], "falhas": []}

        if so_do_tars:
            seus = set(modelos_do_tars)
            try:
                seus.add(visao_instalada())
            except Exception:
                pass
            alvo = rodando & seus
        else:
            alvo = set(rodando)

        if modelo_atual:
            alvo.add(modelo_atual)

        if not alvo:
            print(c(f"\n[openTARS] {t('msg.nenhuma_ia_carregada')}", Cor.CINZA))
            modelo_atual = None
            return {"sucesso": True, "encerrados": [], "falhas": []}

        print(c(f"\n[openTARS] {t('msg.encerrando_modelos', n=len(alvo), modelos=', '.join(sorted(alvo)))}", Cor.CIANO))

        pendentes = set(alvo)

        for tentativa in range(1, max_tentativas + 1):

            for modelo in list(pendentes):
                descarregar_modelo(modelo)

            time.sleep(espera_seg)

            ainda = listar_modelos_rodando()

            if ainda is None:
                print(c(f"[openTARS] {t('msg.ollama_perdido')}", Cor.AMARELO))
                break

            pendentes &= ainda

            if not pendentes:
                break

            if tentativa < max_tentativas:
                texto = t("msg.ainda_ativo", modelos=", ".join(sorted(pendentes)),
                          tentativa=tentativa, total=max_tentativas)
                print(c(f"[openTARS] {texto}", Cor.AMARELO))

        if not modelo_atual or modelo_atual not in pendentes:
            modelo_atual = None

        encerrados = alvo - pendentes

        if pendentes:
            print(c(f"[openTARS] {t('msg.encerramento_nao_confirmado', modelos=', '.join(sorted(pendentes)))}", Cor.VERMELHO))
        else:
            print(c(f"[openTARS] {t('msg.ias_descarregadas')}", Cor.VERDE))

        return {
            "sucesso": not pendentes,
            "encerrados": sorted(encerrados),
            "falhas": sorted(pendentes),
        }


def _cabem_juntos(carregados, novo):
    """Os dois modelos cabem na VRAM ao mesmo tempo? Se sim, o anterior
    fica carregado: no modo AUTO o openTARS alterna entre modelos o tempo
    todo, e descarregar à toa fazia a volta pra ele custar outro
    carregamento inteiro. Sem saber (sem GPU, sem estimativa), descarrega
    como antes, pra nunca empurrar modelo pra RAM/CPU."""

    if isinstance(carregados, str):
        carregados = [carregados]
    gpu = detectar_gpu()
    catalogo = _cache_catalogo.get("dados") or {}
    estimativas = [(catalogo.get(m) or {}).get("vram_estimado_gb") for m in list(carregados) + [novo]]
    if not gpu or None in estimativas:
        return False
    extra_contexto = len(estimativas) * contexto_ia() / 16384  # ~1GB de KV cache por 16k tokens, grosso modo
    return sum(estimativas) + extra_contexto <= gpu["vram_total_gb"] - 1.0


class OllamaOffline(Exception):
    """O Ollama não está rodando (conexão recusada)."""


def carregar_modelo(modelo, silencioso=False):
    """Carrega um modelo no Ollama (descarregando o anterior, se
    houver). Com silencioso=True, evita a caixa grande de status —
    usado no warm-up em segundo plano, pra não interromper o que o
    usuário estiver digitando com um bloco de texto grande."""

    global modelo_atual

    if api.eh_modelo_api(modelo):
        # Nuvem: não há o que carregar aqui. O modelo do Ollama que estava na placa
        # fica como está (se a pessoa voltar pra ele, já está pronto).
        return modelo in listar_modelos_api()

    with lock_modelo:

        if modelo_atual == modelo:
            # já carregado — nada a fazer (bug corrigido: antes retornava
            # None aqui, o que era interpretado como falha de carregamento)
            return True

        # Olha o que está DE FATO carregado (pode ter ficado mais de um
        # quando cabiam juntos) e descarrega tudo se o novo não couber.
        rodando = (listar_modelos_rodando() or set()) | ({modelo_atual} if modelo_atual else set())
        rodando.discard(modelo)
        if rodando and not _cabem_juntos(sorted(rodando), modelo):
            for outro in sorted(rodando):
                emitir("descarregando", modelo=outro)
                descarregar_modelo(outro)
            modelo_atual = None

        emitir("carregando", modelo=modelo, segundo_plano=silencioso)

        inicio = time.time()

        try:
            # Load-only: um prompt vazio no /api/generate faz o Ollama
            # carregar o modelo na memória sem gastar tempo gerando
            # tokens de teste (bem mais rápido que uma chamada de chat
            # completa, principalmente em modelos grandes/lentos).
            resposta = _SESSION.post(
                OLLAMA_GENERATE_URL,
                json={
                    "model": modelo,
                    "prompt": "",
                    "keep_alive": KEEP_ALIVE,
                    # Mesmo num_ctx da conversa: se for diferente, o
                    # Ollama recarrega o modelo na primeira mensagem.
                    "options": {"num_ctx": contexto_ia()},
                },
                timeout=TIMEOUT_HTTP_LONGO,
            )

            if resposta.status_code != 200:
                detalhe = resposta.text.strip() or "-"
                print(c(f"[openTARS] {t('msg.erro_carregar_http', codigo=resposta.status_code, modelo=modelo, detalhe=detalhe)}", Cor.VERMELHO))
                return False

            modelo_atual = modelo
            modelos_do_tars.add(modelo)
            emitir("carregado", modelo=modelo, segundos=time.time() - inicio)
            return True

        except requests.exceptions.ConnectionError:
            # Ollama desligado: não adianta tentar os outros modelos.
            raise OllamaOffline()
        except Exception as e:
            print(c(f"\n[openTARS] {t('msg.erro_carregar', modelo=modelo, erro=e)}", Cor.VERMELHO))
            return False


def _carregar_em_segundo_plano(modelo):
    """Dispara o carregamento de um modelo numa thread separada e
    devolve o controle na hora — usado ao trocar de IA manualmente
    (feedback imediato, sem travar o prompt) e no warm-up do modelo
    padrão ao iniciar o TARS. lock_modelo garante que, se o usuário já
    mandar a próxima mensagem antes do warm-up terminar, ela só espera
    o mesmo carregamento em vez de disparar um segundo em paralelo."""

    threading.Thread(
        target=carregar_modelo,
        args=(modelo,),
        kwargs={"silencioso": True},
        daemon=True,
    ).start()
