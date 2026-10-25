# openTARS — nucleo/chat.py
# O laço de conversa com ferramentas: turnos, falhas, troca de modelo, visão.
#
# Parte do núcleo: o tars.py executa este arquivo DENTRO do próprio
# namespace (ver _carregar_nucleo), então tudo aqui é tars.<nome> e as
# partes enxergam umas às outras sem import. Os testes que trocam
# tars.<função> por uma falsa continuam valendo pra todas as partes.
# flake8: noqa

# ============================================================
# CHAT COM OLLAMA
# ============================================================

_MODELOS_SEM_THINKING = set()

# Modelos que confirmadamente não aceitam o parâmetro 'tools' (ex:
# gemma3:270m). Sem isso, escolher um modelo assim quebrava TODA
# mensagem com um 400 do Ollama — o openTARS sempre manda 'tools'.
_MODELOS_SEM_TOOLS = set()

# Modelos que não enxergam imagem (sem 'vision' no catálogo, ou o Ollama
# respondeu "does not support multimodal"). O print de tela não vai pra
# eles: o modelo de visão (o Gargantua 2) descreve a tela em texto.
_MODELOS_SEM_VISAO = set()


def modelo_enxerga(modelo):
    if modelo in _MODELOS_SEM_VISAO:
        return False
    try:
        info = catalogar_modelos().get(modelo)
    except Exception:
        info = None
    if info and info.get("capacidades_conhecidas"):
        return "vision" in info["capacidades"]
    return True  # não sabemos: tenta (e aprende com o erro)


def _erro_de_imagem(erro):
    """O modelo não aceita imagem nenhuma. Diferente de "tools not supported
    with images" (Ollama antigo): aí a imagem serve, as ferramentas não."""
    e = (erro or "").lower()
    if "tool" in e:
        return "multimodal" in e
    return "multimodal" in e or (("image" in e or "vision" in e) and "support" in e)


_visao_avisado = {"em": 0.0}


def _avisar_falha_da_visao():
    """Se o Cooper está instalado mas não respondeu, o usuário vê o motivo
    (e que outro modelo assume), em vez de um fallback silencioso."""
    if not _visao_estado["erro"] or not visao_instalada():
        return
    agora = time.time()
    if agora - _visao_avisado["em"] < 20:
        return
    _visao_avisado["em"] = agora
    print(c(f"[openTARS] {t('visao.sem_resposta', motivo=motivo_da_falha_da_visao())}", Cor.AMARELO))


def _descrever_print(imagem_b64, pedido, modelo_atual):
    """Texto descrevendo o print (janelas, botões, textos e posições em
    pixels DESTA imagem), feito pelo modelo de visão (o Gargantua 2). None se ele não estiver
    instalado ou não responder."""
    texto_cooper, visao_tag = descrever_com_visao(imagem_b64, pedido)
    if texto_cooper:
        print(c(f"[openTARS] {t('msg.descrevendo_tela', modelo=modelo_atual, visao=visao_tag)}", Cor.AMARELO))
        return texto_cooper, visao_tag
    _avisar_falha_da_visao()
    return None, None


def _print_em_texto(imagem_b64, pedido, modelo, janela=None, arquivo=None):
    """Mensagem (sem imagem) que substitui o print pra um modelo que não
    enxerga."""
    descricao, visao = _descrever_print(imagem_b64, pedido, modelo)
    if descricao and arquivo:
        return (
            "[Automatic message from openTARS, not from the user] You cannot see images, so "
            f"the vision model ({visao}) looked at the image file '{arquivo}' for you:\n{descricao}\n\n"
            f"This is a picture, not the screen: don't click on it. Answer the user's request: \"{pedido}\"."
        )
    if descricao:
        if janela and _sem_arvore(janela):
            # Os nomes da descrição NÃO servem pro click_element nesse app.
            como = ("This app does not expose its buttons: click with click_mouse(x, y, target=<what it is>) "
                    "using the coordinates above (they are approximate: 'target' makes openTARS aim exactly), "
                    "and write with type_in_element(text=..., window=..., submit=true).")
        else:
            como = ("To click, use click_element(name) if the app exposes its buttons; if it fails, "
                    "use click_mouse(x, y, target=<what it is>) with the coordinates above (approximate: "
                    "'target' makes openTARS aim exactly). To drag, use drag_mouse. To write, use type_text.")
        return (
            "[Automatic message from openTARS, not from the user] You cannot see images, so "
            f"the vision model ({visao}) described the screenshot you took:\n{descricao}\n\n"
            f"Continue the user's request: \"{pedido}\". {como}"
        )
    if arquivo:
        return (
            "[Automatic message from openTARS, not from the user] The image file "
            f"'{arquivo}' was loaded, but you cannot see images and the vision model "
            + ("did not answer this time" if visao_instalada() else "is not installed")
            + ". Don't retry. Tell the user plainly that you could not look at the image, and that Gargantua 2 "
            "is the model that lets you see it (ollama pull ProjectOpenTARS/Gargantua-2). "
            f"The user's request was: \"{pedido}\"."
        )
    return (
        "[Automatic message from openTARS, not from the user] The screenshot was taken, but "
        "you cannot see images and the vision model "
        + ("did not answer this time" if visao_instalada() else "is not installed")
        + ". Don't retry the screenshot: "
        "use list_elements(window=<app>) to read a window's buttons and texts, and "
        f"click_element to press them. Continue the user's request: \"{pedido}\"."
    )


def _e_mensagem_de_print(m):
    """Mensagem com o print que o openTARS tirou (e não imagem anexada pelo usuário)."""
    return (m.get("content") or "").startswith("[Automatic message from openTARS")


def _tirar_imagens_da_conversa(mensagens, pedido, modelo):
    """Troca toda imagem da conversa por texto (o modelo recusou imagem)."""
    for m in mensagens:
        imagens = m.pop("images", None)
        if imagens and _e_mensagem_de_print(m):
            m["content"] = _print_em_texto(imagens[-1], pedido, modelo)
        # (imagem anexada pelo usuário: só some a imagem; o texto do pedido e do arquivo ficam)


# Pedido de parar a resposta atual (botão "Parar" da janela, Ctrl+C).
_cancelar = threading.Event()


class RespostaCancelada(Exception):
    pass


# O que perguntar_modelo devolve quando o usuário para a resposta.
RESPOSTA_INTERROMPIDA = "(interrompido)"


_resposta_ativa = {"r": None}


def cancelar_resposta():
    """Interrompe a resposta/tarefa em andamento assim que possível: no
    meio do texto, enquanto o Ollama ainda lê a conversa (fecha a
    conexão), ou entre uma ferramenta e outra."""
    _cancelar.set()
    resposta = _resposta_ativa["r"]
    if resposta is not None:
        try:
            resposta.close()
        except Exception:
            pass


def _verificar_cancelamento():
    if _cancelar.is_set():
        raise RespostaCancelada()


def _preparar_payload_ollama(payload):
    """Remove de antemão os parâmetros que a gente já sabe (pelo
    catálogo, via /api/show, ou por uma falha anterior nesta sessão)
    que esse modelo não aceita."""

    modelo = payload.get("model")
    payload = dict(payload)

    try:
        info = catalogar_modelos().get(modelo)
    except Exception:
        info = None

    if info and info.get("capacidades_conhecidas"):
        capacidades = info["capacidades"]
        if "tools" not in capacidades:
            _MODELOS_SEM_TOOLS.add(modelo)
        if "thinking" not in capacidades:
            _MODELOS_SEM_THINKING.add(modelo)

    if modelo in _MODELOS_SEM_THINKING:
        payload.pop("think", None)

    if modelo in _MODELOS_SEM_TOOLS:
        payload.pop("tools", None)

    return payload


def _erro_de_recurso_nao_suportado(texto, recurso):
    t = (texto or "").lower()
    return recurso in t and ("support" in t or "suport" in t)


def _post_cancelavel(fazer):
    """Roda o POST (que só volta quando o Ollama manda os primeiros bytes:
    carregando o modelo, lendo o prompt) numa thread e confere o botão
    Parar a cada 0,1 s. Sem isso o Parar não valia até o Ollama responder."""
    caixa = {}

    def alvo():
        try:
            caixa["r"] = fazer()
        except Exception as e:  # noqa: BLE001
            caixa["e"] = e

    fio = threading.Thread(target=alvo, daemon=True)
    fio.start()
    while fio.is_alive():
        fio.join(0.1)
        if _cancelar.is_set():
            def fechar_depois():
                fio.join()
                r = caixa.get("r")
                if r is not None:
                    try:
                        r.close()
                    except Exception:
                        pass
            threading.Thread(target=fechar_depois, daemon=True).start()
            raise RespostaCancelada()
    if "e" in caixa:
        raise caixa["e"]
    return caixa["r"]


def _chamar_ollama_stream(payload):
    """Chamada de streaming ao Ollama. Se o Ollama disser que o modelo
    não suporta 'think' ou 'tools', tenta de novo sem isso e lembra pro
    resto da sessão.

    Antes qualquer erro (falta de memória, Ollama reiniciando) disparava
    as tentativas sem think/tools, e um sucesso depois de uma falha
    passageira marcava o modelo como "sem ferramentas" pra sempre."""

    modelo = payload.get("model")
    tentativa = _preparar_payload_ollama(payload)

    for _ in range(3):
        try:
            resposta = _post_cancelavel(lambda: ollama_request(tentativa, stream=True))
        except RespostaCancelada:
            raise
        except Exception as e:
            return None, t("msg.erro_comunicar_ollama", erro=e)

        if resposta.status_code == 200:
            return resposta, None

        try:
            detalhe = resposta.text
        except Exception:
            detalhe = ""

        if "think" in tentativa and _erro_de_recurso_nao_suportado(detalhe, "think"):
            _MODELOS_SEM_THINKING.add(modelo)
            tentativa = {k: v for k, v in tentativa.items() if k != "think"}
            continue

        if "tools" in tentativa and _erro_de_recurso_nao_suportado(detalhe, "tool"):
            _MODELOS_SEM_TOOLS.add(modelo)
            tentativa = {k: v for k, v in tentativa.items() if k != "tools"}
            continue

        return None, t("msg.erro_ollama_http", codigo=resposta.status_code, detalhe=detalhe.strip() or "-")

    return None, t("msg.ollama_recusou")


# ------------------------------------------------------------
# 4.0: raciocínio que vaza no texto da resposta
# ------------------------------------------------------------
# Quando o Ollama não separa o raciocínio (modelo importado de um .gguf,
# formato de chat que ele não reconhece), o "pensamento" vem misturado na
# resposta: "<think>...</think>", ou só o texto em inglês terminando num
# "</think>" solto (a tag de abertura some). O filtro separa de novo: o
# raciocínio vai cinza, a resposta fica limpa e nenhuma tag aparece.

_ABRE_THINK, _FECHA_THINK = "<think>", "</think>"
# Começos típicos de raciocínio (qwen3, deepseek-r1...) quando a tag de abertura sumiu.
_PARECE_RACIOCINIO = re.compile(
    r"^\s*(okay|ok|alright|all right|hmm+|let me|let's see|so,? the user|the user|first,? i|"
    r"i need to|i should|wait,|we need to)\b", re.I)
_DECIDIR_COM = 60   # caracteres guardados antes de decidir se é raciocínio


class FiltroPensamento:
    """Recebe os pedaços de 'content' e devolve [(tipo, texto)], com tipo
    'pensamento', 'resposta' ou 'era_pensamento' (o que já foi mostrado como
    resposta era raciocínio: a janela pinta de cinza)."""

    def __init__(self):
        self.estado = "decidindo"      # decidindo | pensando | respondendo
        self.buffer = ""
        self.pensamento = []
        self.resposta = []
        self.chutou_pensamento = False  # entrou em 'pensando' sem ver <think>

    @staticmethod
    def _sem_tags(texto):
        return texto.replace(_ABRE_THINK, "").replace(_FECHA_THINK, "")

    def _cauda_segura(self, texto):
        """Parte que dá pra mostrar sem cortar uma tag no meio ('</thi' + 'nk>')."""
        for n in range(min(len(texto), len(_FECHA_THINK) - 1), 0, -1):
            if (_FECHA_THINK.startswith(texto[-n:]) or _ABRE_THINK.startswith(texto[-n:])):
                return texto[:-n], texto[-n:]
        return texto, ""

    def _pensar(self, texto):
        texto = self._sem_tags(texto)
        if texto:
            self.pensamento.append(texto)
            return [("pensamento", texto)]
        return []

    def _responder(self, texto):
        texto = self._sem_tags(texto)
        if not self.resposta:
            texto = texto.lstrip()  # "</think>\n\n" deixa quebras de linha antes da resposta
        if texto:
            self.resposta.append(texto)
            return [("resposta", texto)]
        return []

    def alimentar(self, pedaco):
        self.buffer += pedaco
        saida = []
        while True:
            if self.estado == "decidindo":
                b = self.buffer
                if _FECHA_THINK in b:
                    antes, _, depois = b.partition(_FECHA_THINK)
                    saida += self._pensar(antes)
                    self.estado, self.buffer = "respondendo", depois.lstrip()
                    continue
                if b.lstrip().startswith(_ABRE_THINK):
                    self.estado, self.buffer = "pensando", b.lstrip()[len(_ABRE_THINK):]
                    continue
                if len(b) < _DECIDIR_COM and not (_ABRE_THINK.startswith(b.lstrip()) and b.strip()) and "\n" not in b.strip():
                    return saida  # ainda pouco texto pra saber
                if _ABRE_THINK.startswith(b.lstrip()) and b.strip():
                    return saida  # pode ser o começo de "<think>"
                if _PARECE_RACIOCINIO.match(b):
                    self.estado, self.chutou_pensamento = "pensando", True
                else:
                    self.estado = "respondendo"
                continue
            if self.estado == "pensando":
                if _FECHA_THINK in self.buffer:
                    antes, _, depois = self.buffer.partition(_FECHA_THINK)
                    saida += self._pensar(antes)
                    self.estado, self.buffer, self.chutou_pensamento = "respondendo", depois.lstrip(), False
                    continue
                mostrar, self.buffer = self._cauda_segura(self.buffer)
                return saida + self._pensar(mostrar)
            # respondendo
            if _FECHA_THINK in self.buffer:
                # O que foi mostrado como resposta era raciocínio (a tag de abertura sumiu).
                antes, _, depois = self.buffer.partition(_FECHA_THINK)
                ja = "".join(self.resposta) + self._sem_tags(antes)
                self.resposta = []
                if ja.strip():
                    self.pensamento.append(ja)
                    saida.append(("era_pensamento", ja))
                self.buffer = depois.lstrip()
                continue
            if _ABRE_THINK in self.buffer:
                antes, _, depois = self.buffer.partition(_ABRE_THINK)
                saida += self._responder(antes)
                self.estado, self.buffer = "pensando", depois
                continue
            mostrar, self.buffer = self._cauda_segura(self.buffer)
            return saida + self._responder(mostrar)

    def terminar(self):
        """Fim do stream: solta o que sobrou. Se chutou 'raciocínio' e ele
        nunca fechou, era a resposta mesmo."""
        saida = []
        if self.estado == "decidindo":
            saida += self._responder(self.buffer)
        elif self.estado == "pensando":
            saida += self._pensar(self.buffer)
            if self.chutou_pensamento and not self.resposta:
                texto = "".join(self.pensamento)
                self.pensamento = []
                saida += self._responder(texto)
        else:
            saida += self._responder(self.buffer)
        self.buffer = ""
        return saida

    @property
    def conteudo(self):
        return "".join(self.resposta).strip()

    @property
    def texto_pensado(self):
        return "".join(self.pensamento).strip()


# Modelos que raciocinam MESMO com think=false (um fine-tune cujo molde não
# conhece o parâmetro): pra eles o pedido já vai com o interruptor /no_think
# do Qwen3. O openTARS aprende isso sozinho: se um turno sem pensar começa a
# raciocinar por mais que ORCAMENTO_PENSAMENTO_SEM_PEDIR, o turno é cortado
# e refeito com o interruptor (uma vez), e o modelo fica na lista.
_PENSA_MESMO_SEM_PEDIR = set()
# A lista fica em disco: sem isso cada abertura do openTARS pagava de novo um
# turno cortado e refeito (segundos jogados fora) até reaprender.
_pensa_carregado = {"ok": False}


def _arquivo_pensa():
    return os.path.join(os.path.dirname(os.path.abspath(str(ARQUIVO_SESSOES))), ".tars_pensa_sem_pedir.json")


def _carregar_pensa_sem_pedir():
    if _pensa_carregado["ok"]:
        return
    _pensa_carregado["ok"] = True
    try:
        with open(_arquivo_pensa(), encoding="utf-8") as f:
            _PENSA_MESMO_SEM_PEDIR.update(x for x in json.load(f) if isinstance(x, str))
    except Exception:
        pass


def _lembrar_que_pensa(modelo):
    _PENSA_MESMO_SEM_PEDIR.add(modelo)
    try:
        with open(_arquivo_pensa(), "w", encoding="utf-8") as f:
            json.dump(sorted(_PENSA_MESMO_SEM_PEDIR), f)
    except Exception:
        pass
ORCAMENTO_PENSAMENTO_SEM_PEDIR = 500   # caracteres de raciocínio tolerados num turno sem pensar
_NO_THINK = "\n/no_think"


def _modelo_pensa_de_verdade(modelo):
    """Modelo da família que raciocina (Qwen3, Gargantua, ou o Ollama diz 'thinking'):
    só nele um "Okay, the user wants..." sem <think> é raciocínio de verdade, e não
    uma resposta normal que começa assim (gemma, llama...)."""
    if eh_gargantua(modelo) or "qwen3" in str(modelo).lower() or "deepseek-r1" in str(modelo).lower():
        return True
    info = (_cache_catalogo.get("dados") or {}).get(modelo) or {}
    return "thinking" in info.get("capacidades", ())


def _mensagens_sem_pensar(mensagens):
    """Cópia da conversa com /no_think na última mensagem do usuário (só pro
    pedido; o histórico guardado não muda)."""
    copia = [dict(m) for m in mensagens]
    for m in reversed(copia):
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            if not m["content"].rstrip().endswith("/no_think"):
                m["content"] = m["content"].rstrip() + _NO_THINK
            break
    return copia


def _familia_do_modelo(modelo):
    """A família que o Ollama informa ('qwen3', 'qwen35', ...). Lê o catálogo se ainda não foi lido: no modo de modelo fixo
    (o da prova do Lab) ele não era, a família vinha vazia, o Gargantua em Qwen3.5 ia sem think=false, pensava em vez de
    agir e devolvia resposta vazia (5 das 84 tarefas em 17/10). '' se não souber."""
    nomes = (modelo, modelo if ":" in str(modelo) else f"{modelo}:latest")
    dados = _cache_catalogo.get("dados")
    if not dados or not any(n in dados for n in nomes):
        try:
            dados = catalogar_modelos() or {}
        except Exception:  # noqa: BLE001  (Ollama fora do ar: o pedido falha depois, com a mensagem de sempre)
            dados = dados or {}
    info = next((dados[n] for n in nomes if n in dados), {})
    return str(info.get("familia") or "").lower()


def _executar_turno_streaming(modelo, mensagens, tools, pensar=True):
    """Envia a conversa ao Ollama em modo streaming e vai mostrando o
    pensamento e a resposta em tempo real. Devolve conteúdo, pensamento
    e as tool_calls. pensar=False desliga o raciocínio dos modelos que
    pensam (qwen3...): ver deve_pensar()."""

    if api.eh_modelo_api(modelo):
        return _turno_api(modelo, mensagens, tools, pensar)

    _carregar_pensa_sem_pedir()
    # o "/no_think" é truque do Qwen3; o Qwen3.5 não conhece e o lê como parte do pedido (17/10: abriu o site "/no_think" e
    # tentou "apt install no_think"). Ele obedece ao think=false.
    forcar_nothink = (not pensar) and modelo in _PENSA_MESMO_SEM_PEDIR and _familia_do_modelo(modelo) != "qwen35"
    payload = {
        "model": modelo,
        "messages": _mensagens_sem_pensar(mensagens) if forcar_nothink else mensagens,
        "stream": True,
        "keep_alive": KEEP_ALIVE,
        "think": bool(pensar),
        "options": {"temperature": temperatura_conversa(), "num_ctx": contexto_ia()},
    }
    if eh_gargantua(modelo) and not pensar and _familia_do_modelo(modelo) != "qwen35":
        # Treinado sem raciocínio: com think=false o molde do .gguf abre a resposta com "<think></think>", que no treino só
        # vinha antes da resposta final em texto, e o modelo respondia sem chamar ferramenta (prova de 14/10/2026).
        # 17/10: o Gargantua em Qwen3.5 é o contrário: o molde dele põe o <think> vazio também antes das ferramentas e o
        # renderer do Ollama PENSA quando o campo não vem (12/21 sem o campo, 15/21 com think=false no ensaio).
        payload.pop("think")

    if tools:
        payload["tools"] = tools
    if eh_gargantua(modelo) and confianca_lib.ligado():
        payload["logprobs"] = True      # anti-alucinação (5.2): a confiança do modelo na própria resposta, sem custo extra

    resposta, erro = _chamar_ollama_stream(payload)

    if erro:
        return None, erro

    partes_pensamento = []
    tool_calls = []
    logprobs = []

    pensando_ativo = False
    escrevendo_ativo = False
    filtro = FiltroPensamento()

    concluido = False
    _resposta_ativa["r"] = resposta
    try:
        if _cancelar.is_set():
            raise RespostaCancelada()

        for linha in resposta.iter_lines():

            if _cancelar.is_set():
                resposta.close()
                if pensando_ativo or escrevendo_ativo:
                    emitir("fim_stream")
                raise RespostaCancelada()

            if not linha:
                continue

            try:
                chunk = json.loads(linha)
            except Exception:
                continue

            if not isinstance(chunk, dict):
                continue

            if chunk.get("error"):
                if pensando_ativo or escrevendo_ativo:
                    emitir("fim_stream")
                return None, t("msg.erro_ollama", detalhe=chunk["error"])

            msg = chunk.get("message", {})
            msg = msg if isinstance(msg, dict) else {}

            pensamento = msg.get("thinking")

            if pensamento:
                emitir("pensamento", texto=pensamento, inicio=not pensando_ativo)
                pensando_ativo = True
                partes_pensamento.append(pensamento)

            if (not pensar and not forcar_nothink and not tool_calls
                    and sum(len(x) for x in partes_pensamento) > ORCAMENTO_PENSAMENTO_SEM_PEDIR):  # campo 'thinking' de verdade
                # raciocinando sem ninguém pedir: corta e refaz com /no_think
                _lembrar_que_pensa(modelo)
                resposta.close()
                if pensando_ativo or escrevendo_ativo:
                    emitir("fim_stream")
                print(c(f"[openTARS] {t('msg.cortando_raciocinio', modelo=modelo)}", Cor.CINZA))
                return _executar_turno_streaming(modelo, mensagens, tools, pensar)

            if chunk.get("logprobs") and len(logprobs) < confianca_lib.JANELA:
                logprobs.extend(confianca_lib.logprobs_do_pedaco(chunk["logprobs"]))

            pedaco = msg.get("content")

            if pedaco:
                for tipo, texto in filtro.alimentar(pedaco):
                    pensando_ativo, escrevendo_ativo = _mostrar_trecho(tipo, texto, pensando_ativo, escrevendo_ativo)
                if (not pensar and not forcar_nothink and not tool_calls and filtro.estado == "pensando"
                        and (not filtro.chutou_pensamento or _modelo_pensa_de_verdade(modelo))
                        and sum(len(x) for x in filtro.pensamento) > ORCAMENTO_PENSAMENTO_SEM_PEDIR):
                    _lembrar_que_pensa(modelo)
                    resposta.close()
                    if pensando_ativo or escrevendo_ativo:
                        emitir("fim_stream")
                    print(c(f"[openTARS] {t('msg.cortando_raciocinio', modelo=modelo)}", Cor.CINZA))
                    return _executar_turno_streaming(modelo, mensagens, tools, pensar)

            # Versões novas do Ollama podem mandar as chamadas de
            # ferramenta em mais de um pedaço: junta todas.
            if msg.get("tool_calls"):
                tool_calls.extend(msg["tool_calls"])

            if chunk.get("done"):
                if MOSTRAR_TEMPOS and chunk.get("total_duration"):
                    total_s = float(chunk["total_duration"]) / 1e9
                    if total_s >= 1.5:
                        print(c(f"\n[openTARS] {modelo}: {_resumo_de_tempos(chunk, total_s)}", Cor.CINZA))
                if chunk.get("done_reason") == "length":
                    print(c(f"\n[openTARS] {t('msg.limite_contexto', tokens=contexto_ia())}", Cor.AMARELO))
                concluido = True
                break

    except RespostaCancelada:
        raise
    except Exception as e:
        if _cancelar.is_set():  # conexão fechada pelo botão Parar
            if pensando_ativo or escrevendo_ativo:
                emitir("fim_stream")
            raise RespostaCancelada()
        if pensando_ativo or escrevendo_ativo:
            emitir("fim_stream")
        return None, t("msg.erro_streaming", erro=e)
    finally:
        _resposta_ativa["r"] = None
        try:
            resposta.close()          # solta a conexão em qualquer saída (erro, cancelamento, fim)
        except Exception:
            pass

    if not concluido:
        # o Ollama fechou a conexão sem mandar "done" (reiniciou, caiu): o texto parcial NÃO é uma resposta completa
        if pensando_ativo or escrevendo_ativo:
            emitir("fim_stream")
        return None, t("msg.erro_streaming", erro="connection closed before the answer was complete")

    for tipo, texto in filtro.terminar():
        pensando_ativo, escrevendo_ativo = _mostrar_trecho(tipo, texto, pensando_ativo, escrevendo_ativo)

    if pensando_ativo or escrevendo_ativo:
        emitir("fim_stream")

    pensado = "".join(partes_pensamento).strip()
    if filtro.texto_pensado:
        pensado = (pensado + "\n" + filtro.texto_pensado).strip()
    return {
        "content": filtro.conteudo,
        "thinking": pensado,
        "tool_calls": tool_calls,
        "logprobs": logprobs,
    }, None


def _mostrar_trecho(tipo, texto, pensando_ativo, escrevendo_ativo):
    """Manda um trecho separado pelo FiltroPensamento pra tela."""
    if tipo == "pensamento":
        emitir("pensamento", texto=texto, inicio=not pensando_ativo)
        return True, escrevendo_ativo
    if tipo == "era_pensamento":
        emitir("resposta_era_pensamento", texto=texto)
        return True, False
    emitir("resposta", texto=texto, inicio=not escrevendo_ativo, apos_pensamento=pensando_ativo)
    return pensando_ativo, True


LIMITE_CUTUCADAS_RESPOSTA_VAZIA = 2

# Falhas seguidas: a partir de 3 da MESMA ferramenta, a IA é mandada
# mudar de estratégia; com 8 de qualquer uma, para e explica ao usuário.
LIMITE_FALHAS_MESMA_FERRAMENTA = 3
LIMITE_FALHAS_SEGUIDAS = 8


# Mensagens automáticas (vão pra IA, com role=user): começam com "[" —
# é assim que _e_pedido_do_usuario sabe que não foi a pessoa que escreveu.

def _mensagem_do_print(pedido, arquivo=None):
    if arquivo:
        return (
            "[Automatic message from openTARS, not from the user] This is the image file "
            f"'{arquivo}' you asked to look at. It is a picture, not the screen: don't click on it. "
            f"Answer the user's request: \"{pedido}\"."
        )
    return (
        "[Automatic message from openTARS, not from the user] This is the "
        "screenshot you took with take_screenshot. Use it to continue the "
        f"user's request: \"{pedido}\". To click, use pixel coordinates of this "
        "image. Don't describe the image: go on with the next action (or answer, "
        "if the task is done)."
    )


def _mensagem_use_ferramentas(pedido):
    return (
        "[Automatic message from openTARS] You DO have tools for this "
        "(open_application, close_application, click_element, take_screenshot, "
        "execute_terminal and others). Don't say you can't: call the right tool "
        f"now for the user's request: \"{pedido}\"."
    )


_PADROES_SUCESSO = [re.compile(p) for p in (
    r"^(pronto|feito|prontinho|done|all set|finished|listo|hecho|c'?est fait|voila|fertig|erledigt)\b",
    r"\b(abri|fechei|cliquei|enviei|digitei|pesquisei|criei|apaguei|movi|executei|consegui)\b",
    r"\b(i (have )?(opened|closed|clicked|sent|typed|searched|created|deleted|moved|ran))\b",
    r"\b(successfully|com sucesso|con exito|avec succes|erfolgreich)\b",
)]


def _diz_que_conseguiu(texto):
    t = normalizar(texto or "")
    return bool(t) and len(t) < 1200 and any(p.search(t) for p in _PADROES_SUCESSO) \
        and not _parece_recusa(texto)


def _mensagem_sucesso_falso(pedido):
    return (
        "[Automatic message from openTARS] Careful: your LAST tool call FAILED (see its result), "
        "so the task is not done yet. Either fix it now with another approach, or tell the user "
        f"honestly what did not work. Don't say it worked. Request: \"{pedido}\"."
    )


LIMITE_REESCALAR = 2          # trocas de modelo por pedido (erro, recusa, nada funcionou)
MENOR_TROCA_ACEITA = 0.75     # 5.1: na troca, o próximo modelo tem ao menos 3/4 do tamanho do que falhou
LIMITE_JANELAS_CONTEXTO = 8
CONTEXTO_JANELAS = os.environ.get("TARS_CONTEXTO_JANELAS", "1") not in ("0", "off", "nao", "no")


def _pode_cobrar_ferramenta(mensagens, inicio_do_pedido):
    """False quando o pedido parece só a continuação de uma CONVERSA: a Murph apenas palpitou o tipo (via melhor_voto ou padrao,
    "em dúvida") e a última resposta da IA, antes deste pedido, foi texto sem ferramenta. 17/10: "but i need to wash the car",
    resposta a uma pergunta de conversa, foi palpitada como visao, o app mandou o modelo "fazer de verdade" e ele FECHOU o Claude
    do Enzo e abriu o Brave. O primeiro pedido de uma conversa continua sendo cobrado mesmo em palpite, e tarefa decidida com
    certeza também (cobrar de menos é inofensivo; mandar agir sem ter pedido, não)."""
    d = _ultima_decisao.get("d")
    if d is None or not str(getattr(d, "via", "")).startswith(("melhor_voto", "padrao")):
        return True
    respondeu_texto = False
    for m in reversed(mensagens[:inicio_do_pedido]):          # a troca anterior: do fim até a última fala de verdade da pessoa
        if m.get("role") == "tool" or m.get("tool_calls"):
            return True                                        # houve trabalho com ferramenta: é sequência de ação
        if m.get("role") == "assistant" and (m.get("content") or "").strip():
            respondeu_texto = True
        if m.get("role") == "user" and not str(m.get("content") or "").startswith("["):
            return not respondeu_texto
    return True


# A resposta já diz que os resultados ficaram abertos no navegador (então não é resposta de memória disfarçada de busca).
_RE_FALA_DO_NAVEGADOR = re.compile(r"navegador|browser|abert[oa]s?\b|\babri\b|opened|\bopen (?:in|on)\b|on (?:the|your) screen|"
                                   r"na tela|\blink\b|resultados? (?:da busca|esta|estao)|results? (?:are|is)\b")


# A resposta diz que ABRIU algo na tela (falso quando a busca só consultou o SearXNG)
_RE_DIZ_QUE_ABRIU = re.compile(r"(?:abert[oa]s?|abri|abrimos|abrindo)\b.{0,50}\b(?:navegador|browser|google|tela|aba)\b|"
                               r"\b(?:opened|opening|open)\b.{0,40}\b(?:browser|google|tab|screen)\b|"
                               r"\b(?:no|in the|in your|on your) (?:navegador|browser)\b|encontrad[oa]s? no google|found (?:it )?on google")


def _mensagem_sem_ferramenta(pedido):
    return (
        "[Automatic message from openTARS] You answered without doing it (or as if it were done), but you did NOT call "
        "any tool, so nothing happened on the computer. Call the right tool(s) now to actually do "
        f"it: \"{pedido}\". Only after a tool result confirms it, say it's done."
    )


def _mensagem_verificar_fato(pedido):
    return (
        "[Automatic message from openTARS] You answered from memory and your confidence in that answer was low, so it may "
        "be wrong or invented. Do not repeat it. Call search_web for it now, then answer ONLY from the results (say which "
        "site), or say you could not confirm it. Question: "
        f"\"{pedido}\"."
    )


def _mensagem_outro_modelo(pedido):
    return (
        "[Automatic message from openTARS] The attempts above (by another model) all failed. You "
        "are taking over: use a DIFFERENT approach from the ones that failed (another tool, "
        "another window name, typing instead of clicking...). If there is really no way, tell the "
        f"user what blocks it. Request: \"{pedido}\"."
    )


def _desfecho(tarefa, conteudo, usou_ferramenta, algum_sucesso, mentiu):
    """Pro histórico do modelo: deu certo (True), falhou (False) ou não dá
    pra dizer (None: ex. todas as ferramentas falharam por causa do
    computador e a IA explicou direito)."""
    if not conteudo or mentiu:
        return False
    if _parece_recusa(conteudo) and not usou_ferramenta:
        return False
    if tarefa in ("acao", "visao", "busca"):
        return True if algum_sucesso else None
    return True


def _janelas_para_contexto():
    if not plataforma.janelas_prontas():       # macOS: o Quartz ainda carregando; o pedido não espera por ele
        return []
    try:
        janelas = listar_janelas_x()
        ativa = janela_ativa_x() if janelas else None
    except Exception:
        return []
    if not janelas:
        return []
    protegidos = _pids_protegidos()
    saida = []
    for j in janelas:
        titulo = (j.get("titulo") or "").strip()
        if not titulo or j.get("pid") in protegidos:
            continue
        titulo = titulo if len(titulo) <= 50 else titulo[:47] + "..."
        saida.append(f"'{titulo}'" + (" (focused)" if j.get("id") == ativa else ""))
        if len(saida) >= LIMITE_JANELAS_CONTEXTO:
            break
    return saida


def _ultimo_pedido_real(mensagens=None):
    """A última fala de verdade da pessoa na conversa (não as mensagens automáticas, que começam com "[")."""
    for m in reversed(mensagens if mensagens is not None else conversa):
        if m.get("role") == "user" and not str(m.get("content") or "").startswith("["):
            return str(m["content"]).split("\n\n[", 1)[0].strip() or None
    return None


_PERGUNTA_DE_IDENTIDADE = re.compile(
    r"\b(?:quem (?:e|eh) (?:voce|vc|tu)|quem (?:te |lhe )?(?:criou|fez|desenvolveu|programou|inventou|treinou)|"
    r"quem (?:e|eh) (?:o )?(?:seu )?(?:criador|dono|fundador|desenvolvedor)|qual (?:e )?(?:o )?seu nome|como (?:voce )?se chama|"
    r"seu nome|voce (?:e|eh) (?:o )?(?:chatgpt|gpt|gemini|claude|llama|qwen|alexa|siri)|"
    r"who (?:are you|made you|created you|built you|developed you|trained you|is your (?:creator|developer|founder|maker))|"
    r"what(?:'s| is) your name|your (?:name|creator|developer|founder)|who (?:is|are) (?:the )?(?:founder|creator) of opentars|"
    r"(?:fundador|criador|dono|founder|creator) (?:do |da |of )?opentars)\b")
_VERBOS_DE_BUSCA = re.compile(r"\b(?:pesquis\w*|busc\w*|procur\w*|search\w*|find|look up|look for|ache|achar)\b")


def _sites_citados_na_busca(texto_n):
    """Os sites com busca própria que o pedido cita ("pesquisa X no spotify"), fora google e youtube (que a IA já conhece)."""
    if not _VERBOS_DE_BUSCA.search(texto_n):
        return []
    nomes = set(_BUSCAS_POR_SERVICO) | set(_APELIDOS_DE_SERVICO)
    achados = [n for n in sorted(nomes, key=len, reverse=True)
               if n not in ("google", "youtube", "yt", "x", "mapa", "mapas", "prime") and re.search(rf"\b{re.escape(n)}\b", texto_n)]
    return [_APELIDOS_DE_SERVICO.get(n, n) for n in achados]


def _contexto_do_pedido(texto, tarefa, multi_etapas, retoma=None):
    """O que a IA precisa saber antes de agir: as janelas abertas (não
    precisa abrir o que já está aberto, sabe o nome certo da janela) e, se
    o pedido tem várias etapas, que é pra fazer TODAS."""
    linhas = []
    if escolha.pedido_em_ingles(normalizar(retoma or texto)):
        linhas.append("The user writes in English: answer in English.")
    if retoma:
        # 18/10: "use the built-in tool" sozinho não diz o quê; o modelo pequeno inventava (abriu o "app" google)
        linhas.append(f"The user's message refers to the previous request: \"{retoma}\". Do that request now with the "
                      "right tool, and say only what the tool results confirm.")
    texto_n = normalizar(retoma or texto)
    if _PERGUNTA_DE_IDENTIDADE.search(texto_n):
        linhas.append("About you: your name is Gargantua. You were developed by Enzo, the founder of openTARS, and you run "
                      "inside the openTARS app (openTARS is the app, Gargantua is you). Say so in your own words; never "
                      "name another company or model as your maker.")
    sites = _sites_citados_na_busca(texto_n)
    if sites:
        linhas.append("To search INSIDE a site, call search_web with query = only the search terms and service = the site "
                      f"name, here: service=\"{sites[0]}\". Do not use google as the service and do not open_website "
                      "for a search.")
    if CONTEXTO_JANELAS and tarefa in ("acao", "visao"):
        janelas = _janelas_para_contexto()
        if janelas:
            linhas.append("Open windows right now: " + "; ".join(janelas) + ".")
    if multi_etapas:
        partes = _etapas_do_pedido(texto)
        if len(partes) >= 2:
            plano = " ".join(f"{i}. {p}" for i, p in enumerate(partes, 1))
            linhas.append(f"This request has {len(partes)} steps. Plan: {plano}. Do ALL of them, in order, "
                          "checking each one worked (its tool result) before the next, and only then give "
                          "your final answer (don't stop after the first one).")
    if not linhas:
        return None
    return "[Context from openTARS, not a new request] " + " ".join(linhas)


# ------------------------------------------------------------
# 3.0: planejar e conferir
# ------------------------------------------------------------
# Ferramentas que só OLHAM (não contam como etapa feita).
_FERRAMENTAS_SO_OLHAM = {
    "take_screenshot", "list_elements", "list_windows",
}


def _etapas_do_pedido(texto):
    return escolha.partes_do_pedido(normalizar(texto), _verbos_de_acao())


def _mensagem_plano_incompleto(pedido, etapas, feitas):
    lista = " ".join(f"{i}. {p}" for i, p in enumerate(etapas, 1))
    return (
        f"[Automatic message from openTARS] Plan check: this request has {len(etapas)} steps ({lista}), "
        f"but only {feitas} action(s) worked so far. Do the missing step(s) now. If one really cannot "
        f"be done, tell the user which one and why. Don't say everything is done. Request: \"{pedido}\"."
    )


def _mensagem_conferir_conclusao(pedido, feitas, resposta):
    lista = "; ".join(feitas[-12:]) or "none"
    return (
        "[Automatic message from openTARS] Completion check before you finish. "
        f"The user asked: \"{pedido}\". Actions that worked so far: {lista}. "
        f"Your last answer was: \"{str(resposta or '').strip()[:400]}\". "
        "Compare them: is EVERY part of the request really done, with its final result on screen, and "
        "nothing left for the user to do? If anything is missing (including something you told the "
        "user to do), call the tool(s) now to finish it. If everything is done, answer briefly."
    )


def _mensagem_sem_efeito(pedido):
    return (
        "[Automatic message from openTARS] Your last click/drag changed NOTHING on screen, so it "
        "probably missed. Check (take_screenshot or list_elements) and retry with target=<what to "
        "click> before saying it's done; if it really can't be done, tell the user honestly. "
        f"Request: \"{pedido}\"."
    )


def _mensagem_faca_voce(pedido):
    return (
        "[Automatic message from openTARS] Don't hand the task back to the user: you have the "
        "tools to do it yourself. Read the last tool result again and follow the way it gives "
        "(e.g. type_in_element with window and submit=true to write in an app that doesn't expose "
        "its buttons, or take_screenshot + click_mouse). If you must invent content (a question, a "
        f"message), invent it. Do it now for: \"{pedido}\"."
    )


def _mensagem_continuar(pedido):
    return (
        "[Automatic message from openTARS] You neither called a tool nor "
        f"answered. Continue the user's request: \"{pedido}\" — call the next "
        "tool or, if you are done, say in one sentence what was done."
    )


_NOMES_FERRAMENTAS = None


def _ferramentas_no_texto(texto):
    """Chamadas de ferramenta escritas no texto da resposta, no formato
    [{"function": {"name", "arguments"}}], ou [] se não houver."""
    global _NOMES_FERRAMENTAS
    if _NOMES_FERRAMENTAS is None:
        _NOMES_FERRAMENTAS = {f["function"]["name"] for f in TOOLS}
    if '"name"' not in texto or not any(nome in texto for nome in _NOMES_FERRAMENTAS):
        return []
    decodificador = json.JSONDecoder()
    chamadas, pos = [], 0
    while True:
        pos = texto.find("{", pos)
        if pos < 0:
            break
        try:
            obj, fim = decodificador.raw_decode(texto, pos)
        except ValueError:
            pos += 1
            continue
        pos = fim
        if isinstance(obj, dict) and isinstance(obj.get("function"), dict):
            obj = obj["function"]
        argumentos = obj.get("arguments", obj.get("parameters")) if isinstance(obj, dict) else None
        if isinstance(argumentos, str):
            try:
                argumentos = json.loads(argumentos)
            except ValueError:
                argumentos = None
        if isinstance(obj, dict) and isinstance(obj.get("name"), str) and obj["name"] in _NOMES_FERRAMENTAS and isinstance(argumentos, dict):
            chamadas.append({"function": {"name": obj["name"], "arguments": argumentos}})
    return chamadas


def _argumentos_da_chamada(funcao):
    argumentos = funcao.get("arguments", {})
    if isinstance(argumentos, str):
        try:
            argumentos = json.loads(argumentos)
        except Exception:
            argumentos = {}
    return argumentos if isinstance(argumentos, dict) else {}


def _carregar_com_fallback(modelo, tarefa):
    """Carrega o modelo pedido; no modo AUTO, se falhar, desce a cadeia
    de alternativas da tarefa."""

    candidatos = [modelo]
    if modo_modelo == "AUTO" and tarefa:
        candidatos += [m for m in construir_cadeia_fallback(tarefa) if m != modelo]

    for candidato in candidatos:
        if carregar_modelo(candidato):
            return candidato, candidatos
        print(c(f"[AUTO] {t('msg.falha_carregar_alternativa', modelo=candidato)}", Cor.AMARELO))
    return None, candidatos


# Resultados de ferramenta vão pra IA com chaves em inglês (o código usa
# as chaves em português; a IA entende melhor um JSON todo em inglês).
_CHAVES_PARA_IA = {
    "sucesso": "success", "mensagem": "message", "acao": "action", "aplicativo": "app",
    "encontrado_como": "found_as", "janela": "window", "janelas": "windows",
    "janelas_fechadas": "closed_windows", "janelas_abertas": "open_windows",
    "titulo": "title", "largura": "width", "altura": "height", "minimizada": "minimized",
    "em_foco": "focused", "diretorio": "directory", "caminho": "path", "arquivos": "files",
    "codigo": "exit_code", "entrada": "input", "servico": "service",
    "ram_percentual": "ram_percent", "ram_disponivel_gb": "ram_available_gb",
    "disco_percentual": "disk_percent", "disco_livre_gb": "disk_free_gb",
    "elementos": "elements", "elemento": "element", "textos": "texts",
}


def _para_ia(valor):
    if isinstance(valor, dict):
        return {_CHAVES_PARA_IA.get(k, k): _para_ia(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_para_ia(v) for v in valor]
    return valor


# ------------------------------------------------------------
# 4.1: tarefas longas
# ------------------------------------------------------------
LIMITE_CICLOS_MAX = int(os.environ.get("TARS_LIMITE_ETAPAS", "120"))  # teto absoluto por pedido
FOLEGO_CICLOS = 20             # quanto cada fôlego extra dá
ETAPAS_POR_PASSO_DO_PLANO = 6  # pedido com plano: cada etapa a mais do plano já começa com isso
CICLOS_ANTES_DE_COMPACTAR = 10
RESULTADOS_INTEIROS = 6        # os últimos resultados de ferramenta ficam inteiros
LIMITE_CHARS_RESULTADO_NO_PEDIDO = 500


def limite_de_ciclos(etapas=()):
    """Limite inicial de idas-e-voltas: 20, mais 6 por etapa do plano além
    da segunda (até 50)."""
    extra = ETAPAS_POR_PASSO_DO_PLANO * max(0, len(etapas or ()) - 2)
    return min(max(LIMITE_CICLOS_FERRAMENTAS, 50), LIMITE_CICLOS_FERRAMENTAS + extra)


def _merece_folego(ciclo, acoes_feitas, acoes_no_inicio_do_folego):
    """Mais fôlego só se o último trecho teve ação que deu certo de verdade
    (olhar a tela ou listar janelas não conta) e se ainda cabe no teto."""
    return ciclo < LIMITE_CICLOS_MAX and acoes_feitas > acoes_no_inicio_do_folego


def _mensagem_folego(pedido, etapas, acoes_feitas):
    plano = ""
    if etapas:
        plano = " The plan was: " + "; ".join(f"{i}. {e}" for i, e in enumerate(etapas, 1)) + "."
    return (f"[Automatic message from openTARS] Long task in progress: {acoes_feitas} actions done so far. "
            f"Keep going with what is left of the user's request (\"{pedido}\").{plano} Don't redo what already "
            "worked. When everything is done, check it and tell the user the result in a few sentences.")


def _compactar_pedido_atual(mensagens, inicio):
    """Num pedido longo, os resultados de ferramenta mais antigos (listas de
    arquivos, saída de comando) são encurtados: os últimos ficam inteiros.
    Sem isso, a conversa passa do contexto da IA no meio da tarefa."""
    indices = [i for i in range(max(inicio, 1), len(mensagens)) if mensagens[i].get("role") == "tool"]
    for i in indices[:-RESULTADOS_INTEIROS]:
        conteudo = mensagens[i].get("content") or ""
        if len(conteudo) > LIMITE_CHARS_RESULTADO_NO_PEDIDO:
            mensagens[i]["content"] = conteudo[:LIMITE_CHARS_RESULTADO_NO_PEDIDO] + "…(earlier result shortened)"
    # Orçamento: os resultados "inteiros" também têm teto, senão 6 saídas de 8000 caracteres estouram um contexto de
    # 8k tokens e o Ollama corta o COMEÇO da conversa (o pedido da pessoa). Encurta do mais antigo ao mais novo.
    try:
        orcamento = int(contexto_ia() * 3 * 0.4)
    except Exception:
        orcamento = 9000
    inteiros = indices[-RESULTADOS_INTEIROS:]
    total = sum(len(mensagens[i].get("content") or "") for i in inteiros)
    for i in inteiros[:-1]:           # o mais recente fica inteiro
        if total <= orcamento:
            break
        conteudo = mensagens[i].get("content") or ""
        if len(conteudo) > LIMITE_CHARS_RESULTADO_NO_PEDIDO:
            mensagens[i]["content"] = conteudo[:LIMITE_CHARS_RESULTADO_NO_PEDIDO] + "…(earlier result shortened)"
            total -= len(conteudo) - len(mensagens[i]["content"])


def perguntar_modelo(modelo, texto, tarefa=None, multi_etapas=False, anexos=None, retoma=None):

    pendentes = []  # ferramentas pedidas e ainda não executadas neste ciclo

    try:
        modelo_carregado, tentados = _carregar_com_fallback(modelo, tarefa)
    except OllamaOffline:
        modelo_carregado, tentados = None, [modelo]

    if not modelo_carregado and not ollama_online():
        # "Não consegui carregar o modelo" escondia a causa: o Ollama
        # está desligado (ex: parado pra usar o vLLM).
        mensagem_erro = t("aviso.ollama_offline", host=OLLAMA_HOST)
        print(c(f"\n[openTARS] {mensagem_erro}", Cor.VERMELHO))
        return mensagem_erro

    if not modelo_carregado:
        mensagem_erro = t("msg.nenhum_modelo_carregou", tentados=", ".join(tentados))
        print(c(f"\n[openTARS] {mensagem_erro}", Cor.VERMELHO))
        return mensagem_erro

    modelo = modelo_carregado
    usados = [modelo]
    mensagens = obter_sessao(modelo)
    _remover_turnos_recusados(mensagens)
    # a lista de janelas abertas de pedidos anteriores é velha: só a de agora vale
    mensagens[:] = [m for m in mensagens
                    if not (m.get("role") == "user" and str(m.get("content") or "").startswith("[Context from openTARS"))]
    if anexos:
        # arquivos anexados: o conteúdo vai junto com o pedido (a imagem, pra quem enxerga)
        conteudo_usuario, imagens_anexadas = montar_mensagem_com_anexos(texto, anexos, modelo)
        mensagens.append({"role": "user", "content": conteudo_usuario,
                          **({"images": imagens_anexadas} if imagens_anexadas else {})})
    else:
        mensagens.append({"role": "user", "content": texto})
    inicio_do_pedido = len(mensagens) - 1
    contexto = _contexto_do_pedido(texto, tarefa, multi_etapas, retoma)
    if contexto:
        mensagens.append({"role": "user", "content": contexto})

    inicio_total = time.time()
    cutucadas = 0
    usou_ferramenta = False
    lembrou_ferramentas = False
    pensar = pensar_do_modelo(modelo, tarefa, texto, multi_etapas)
    janela_do_print = None
    arquivo_do_print = None
    ultima_falhou = insistiu = conferiu_sucesso = cobrou_acao = False
    algum_sucesso = mentiu = False
    desfecho = None               # pro histórico: True deu certo, False falhou, None não conta
    reescaladas = 0
    ferramentas = ferramentas_do_modelo(modelo, tarefa, texto)
    # 5.1: "keep in memory i use brave" MANDA salvar. Se o modelo não chamar a ferramenta (responde "anotado!" ou vai
    # de shell escrever num arquivo), o openTARS salva o fato sozinho. Só quando o pedido é só isso (sem outra etapa).
    fato_a_lembrar = None if multi_etapas else memoria_lib.intencao_de_lembrar(texto)
    falhas_seguidas = {}          # ferramenta -> falhas desde o último sucesso
    chamadas_que_falharam = {}    # (ferramenta, argumentos) -> motivo
    # 3.0: planejar e conferir
    etapas = _etapas_do_pedido(texto) if multi_etapas else []
    acoes_feitas = 0              # ações (não só olhar) que deram certo DE VERDADE
    feitas_resumo = []            # "nome(argumentos)" de cada uma, pra conferir no fim
    busca_sem_leitura = False     # search_web abriu resultados que ninguém leu (nem print nem read_page depois)
    busca_sem_abrir = False       # search_web leu pelo SearXNG e NÃO abriu nada na tela (decisão de 18/10)
    revisou = False
    verificou_fato = False        # anti-alucinação: já tentou conferir uma resposta de pouca confiança
    pouca_confianca = False
    sem_efeito_seguidos = 0       # cliques/arrastos "certos" que não mudaram a tela
    ultima_sem_efeito = cobrou_plano = cobrou_efeito = False
    if len(etapas) >= 2:
        emitir("plano", etapas=etapas)

    def aplicar_formato():
        """4.0: entrar ou sair do Gargantua no meio do pedido troca o
        formato junto (prompt de sistema, ferramentas, raciocínio)."""
        nonlocal ferramentas, pensar
        if mensagens and mensagens[0].get("role") == "system":
            mensagens[0]["content"] = prompt_do_modelo(modelo)
        ferramentas = ferramentas_do_modelo(modelo, tarefa, texto)
        pensar = pensar_do_modelo(modelo, tarefa, texto, multi_etapas)

    def trocar_de_modelo(chave_mensagem):
        """Passa o pedido pro próximo modelo da fila (no modo AUTO, até
        LIMITE_REESCALAR vezes por pedido). O que falhou fica no placar."""
        nonlocal modelo, reescaladas
        if modo_modelo != "AUTO" or reescaladas >= LIMITE_REESCALAR:
            return False
        fila = construir_cadeia_fallback(tarefa_da_fila(tarefa or "acao", multi_etapas))
        # 5.1 (item 7 do plano): depois de uma falha a troca é para cima ou para o lado, nunca para um modelo bem menor
        # (no print do Enzo, o Gargantua falhou e quem respondeu foi o qwen3:0.6b, sem dar conta do pedido)
        catalogo = catalogar_modelos()
        atual_b = (catalogo.get(modelo) or {}).get("parametros_b")

        def nao_desce(m):
            b = (catalogo.get(m) or {}).get("parametros_b")
            return atual_b is None or b is None or b >= atual_b * MENOR_TROCA_ACEITA

        proximo = next((m for m in fila if m not in usados and nao_desce(m)), None)
        if not proximo:
            return False
        try:
            if not carregar_modelo(proximo):
                return False
        except OllamaOffline:
            return False
        historico_modelos.registrar(modelo, _tarefa_do_historico(tarefa), False)
        print(c(f"[AUTO] {t(chave_mensagem, modelo=modelo, novo=proximo)}", Cor.AMARELO))
        usados.append(proximo)
        modelo = proximo
        reescaladas += 1
        aplicar_formato()
        return True

    # 4.1: tarefas longas. O limite começa maior quando o pedido tem várias
    # etapas e, enquanto a IA estiver fazendo progresso de verdade (ações que
    # deram certo), ganha mais fôlego, até LIMITE_CICLOS_MAX.
    limite_ciclos = limite_de_ciclos(etapas)
    ciclo = 0
    acoes_no_inicio_do_folego = 0
    folegos = 0

    try:
        while True:
            if ciclo >= limite_ciclos:
                if not _merece_folego(ciclo, acoes_feitas, acoes_no_inicio_do_folego):
                    break
                folegos += 1
                limite_ciclos = min(LIMITE_CICLOS_MAX, limite_ciclos + FOLEGO_CICLOS)
                acoes_no_inicio_do_folego = acoes_feitas
                emitir("folego", etapas=ciclo, acoes=acoes_feitas, limite=limite_ciclos)
                print(c(f"[openTARS] {t('msg.folego', etapas=ciclo, acoes=acoes_feitas)}", Cor.CINZA))
                mensagens.append({"role": "user", "content": _mensagem_folego(texto, etapas, acoes_feitas)})
            ciclo += 1  # conta a partir de 1: "ciclo > 1" = já houve uma volta antes desta
            if ciclo > CICLOS_ANTES_DE_COMPACTAR:
                _compactar_pedido_atual(mensagens, inicio_do_pedido)

            _verificar_cancelamento()

            imagem_no_turno = any(m.get("images") for m in mensagens)

            resultado, erro = _executar_turno_streaming(modelo, mensagens, ferramentas, pensar=pensar)

            if erro and imagem_no_turno and _erro_de_imagem(erro):
                # "Model does not support multimodal": esse modelo não
                # enxerga. Toda imagem da conversa vira texto (descrita
                # por um modelo com visão) e as ferramentas continuam.
                _MODELOS_SEM_VISAO.add(modelo)
                _tirar_imagens_da_conversa(mensagens, texto, modelo)
                resultado, erro = _executar_turno_streaming(modelo, mensagens, ferramentas, pensar=pensar)
            elif erro and imagem_no_turno:
                # Alguns Ollama antigos não aceitam 'tools' junto com
                # imagem: tenta de novo sem as ferramentas.
                print(c(f"[openTARS] {t('msg.imagem_sem_ferramentas', erro=erro)}", Cor.AMARELO))
                resultado, erro = _executar_turno_streaming(modelo, mensagens, None, pensar=pensar)

            if erro:
                # Modelo que quebrou (sem memória, chamada de ferramenta que
                # o Ollama não entendeu...): o próximo da fila continua a
                # MESMA conversa, com o que já foi feito.
                if not _erro_de_imagem(erro) and trocar_de_modelo("msg.tentando_outro_modelo"):
                    continue
                desfecho = False
                print(c(f"\n[openTARS] {erro}", Cor.VERMELHO))
                return erro

            conteudo = resultado["content"]
            tool_calls = resultado["tool_calls"]

            # Modelo que escreve a chamada da ferramenta como TEXTO
            # (<tool_call>{...}</tool_call>, um JSON solto): vira chamada
            # de verdade, em vez de aparecer pro usuário como resposta.
            if not tool_calls and conteudo:
                no_texto = _ferramentas_no_texto(conteudo)
                if no_texto:
                    tool_calls, conteudo = no_texto, ""

            if fato_a_lembrar:
                if any((ch.get("function") or {}).get("name") in ("remember", "forget") for ch in tool_calls):
                    fato_a_lembrar = None          # o modelo mesmo chamou: nada a fazer
                elif ciclo == 1:
                    # nada de remember: a chamada certa entra no lugar do que o modelo fez (resposta solta, shell...)
                    print(c(f"[openTARS] {t('msg.memoria_sozinho', fato=fato_a_lembrar)}", Cor.CINZA))
                    tool_calls = [{"function": {"name": "remember", "arguments": {"fact": fato_a_lembrar}}}]
                    conteudo = ""
                    fato_a_lembrar = None

            if not tool_calls and not conteudo and ciclo > 1 and cutucadas < LIMITE_CUTUCADAS_RESPOSTA_VAZIA:
                # Modelo "pensou" mas não respondeu nem chamou ferramenta
                # no meio de uma tarefa: pede pra continuar em vez de
                # encerrar pela metade.
                cutucadas += 1
                print(c(f"[openTARS] {t('msg.ia_parou')}", Cor.AMARELO))
                mensagens.append({"role": "user", "content": _mensagem_continuar(texto)})
                continue

            if (
                not tool_calls and not usou_ferramenta and not lembrou_ferramentas
                and modelo not in _MODELOS_SEM_TOOLS and _parece_recusa(conteudo)
            ):
                # "Não consigo abrir aplicativos": lembra que consegue, uma
                # vez. A recusa não entra no histórico.
                lembrou_ferramentas = True
                ferramentas = ferramentas_do_modelo(modelo, None, texto)  # talvez faltasse a ferramenta certa
                print(c(f"[openTARS] {t('msg.ia_recusou')}", Cor.AMARELO))
                mensagens.append({"role": "user", "content": _mensagem_use_ferramentas(texto)})
                continue

            if (
                not tool_calls and not usou_ferramenta and lembrou_ferramentas
                and modo_modelo == "AUTO" and _parece_recusa(conteudo)
            ):
                # Recusou de novo mesmo lembrado: esse modelo não serve pra
                # esse pedido. Passa pro próximo da fila (uma vez).
                proximo = next((m for m in construir_cadeia_fallback(tarefa or "acao")
                                if m not in usados), None)
                try:
                    carregou = bool(proximo) and carregar_modelo(proximo)
                except OllamaOffline:
                    carregou = False
                if carregou:
                    historico_modelos.registrar(modelo, _tarefa_do_historico(tarefa), False)
                    print(c(f"[AUTO] {t('msg.trocando_modelo', modelo=modelo, novo=proximo)}", Cor.AMARELO))
                    usados.append(proximo)
                    modelo = proximo
                    aplicar_formato()
                    lembrou_ferramentas = False
                    while mensagens and mensagens[-1].get("role") == "user" and mensagens[-1].get("content", "").startswith("["):
                        mensagens.pop()
                    continue

            if (
                not tool_calls and usou_ferramenta and ultima_falhou and not insistiu
                and tarefa in ("acao", "visao", None) and _devolveu_pro_usuario(conteudo)
            ):
                # Uma ferramenta falhou e a IA mandou o usuário fazer na mão
                # ("clique na caixa e digite"), com as ferramentas certas
                # disponíveis. Uma vez: manda ela mesma fazer.
                insistiu = True
                ferramentas = ferramentas_do_modelo(modelo, None, texto)
                print(c(f"[openTARS] {t('msg.ia_recusou')}", Cor.AMARELO))
                mensagens.append({"role": "user", "content": _mensagem_faca_voce(texto)})
                continue

            if (
                not tool_calls and usou_ferramenta and ultima_falhou and not conferiu_sucesso
                and _diz_que_conseguiu(conteudo)
            ):
                # "Pronto, abri!" logo depois de uma ferramenta que FALHOU:
                # a IA está inventando. Uma vez: conserta ou conta a verdade.
                conferiu_sucesso = mentiu = True
                mensagens.append({"role": "user", "content": _mensagem_sucesso_falso(texto)})
                continue

            if (
                not tool_calls and not usou_ferramenta and not cobrou_acao
                # "use a ferramenta"/"faz de verdade" (retoma): a pessoa pediu ferramenta com todas as letras, em qualquer modo
                and (tarefa in ("acao", "visao") or retoma) and modelo not in _MODELOS_SEM_TOOLS
                and (retoma or _pode_cobrar_ferramenta(mensagens, inicio_do_pedido))
                and (conteudo or "").strip()
            ):
                # Pedido de ação respondido sem ferramenta nenhuma: "Pronto,
                # abri o Firefox!" ou só o resultado ("12 x 8 = 96", sem
                # apertar os botões). Nada aconteceu no computador. Uma vez: faça.
                cobrou_acao = mentiu = True
                ferramentas = ferramentas_do_modelo(modelo, None, retoma or texto)
                mensagens.append({"role": "user", "content": _mensagem_sem_ferramenta(retoma or texto)})
                continue

            if (
                not tool_calls and usou_ferramenta and ultima_sem_efeito and not cobrou_efeito
                and _diz_que_conseguiu(conteudo)
            ):
                # "Pronto!" logo depois de um clique que não mudou nada na
                # tela: confere antes. Uma vez.
                cobrou_efeito = mentiu = True
                mensagens.append({"role": "user", "content": _mensagem_sem_efeito(texto)})
                continue

            if (
                not tool_calls and len(etapas) >= 2 and acoes_feitas < len(etapas) and not cobrou_plano
                and tarefa in ("acao", "visao", None) and modelo not in _MODELOS_SEM_TOOLS
            ):
                # Pedido de várias etapas encerrado antes de fazer todas:
                # mostra o plano e o que falta. Uma vez.
                cobrou_plano = True
                print(c(f"[openTARS] {t('msg.plano_incompleto', feitas=acoes_feitas, total=len(etapas))}",
                        Cor.AMARELO))
                mensagens.append({"role": "user", "content": _mensagem_plano_incompleto(texto, etapas,
                                                                                          acoes_feitas)})
                continue

            if (
                not tool_calls and not revisou and usou_ferramenta
                and (len(etapas) >= 2 or acoes_feitas >= 2)
                and tarefa in ("acao", "visao", None) and modelo not in _MODELOS_SEM_TOOLS
            ):
                # Antes de aceitar "terminei" num pedido de várias ações, a IA
                # confere o pedido inteiro contra o que fez (sem olhar o que ela
                # escreveu: só o pedido e as ações). Uma vez.
                revisou = True
                print(c(f"[openTARS] {t('msg.conferindo_conclusao')}", Cor.CINZA))
                mensagens.append({"role": "assistant", "content": conteudo})
                mensagens.append({"role": "user", "content": _mensagem_conferir_conclusao(texto, feitas_resumo, conteudo)})
                continue

            if (
                not tool_calls and not usou_ferramenta and not verificou_fato and confianca_lib.ligado()
                and confianca_lib.vale_conferir(tarefa, texto, conteudo)
                and confianca_lib.pouca_confianca(resultado.get("logprobs"))
            ):
                # Anti-alucinação: o modelo respondeu um fato com pouca confiança nos próprios tokens. Com a pesquisa web
                # ligada, uma vez, ele confere pela busca; sem ela, o app avisa embaixo da resposta.
                verificou_fato = True
                if _pesquisa_ligada():
                    print(c(f"[openTARS] {t('msg.verificando_fato')}", Cor.AMARELO))
                    mensagens.append({"role": "assistant", "content": conteudo})
                    mensagens.append({"role": "user", "content": _mensagem_verificar_fato(texto)})
                    ferramentas = ferramentas_do_modelo(modelo, "busca", texto)
                    continue
                pouca_confianca = True

            if not tool_calls:
                mensagens.append({"role": "assistant", "content": conteudo})
                if pouca_confianca and conteudo:
                    print(c(f"[openTARS] {t('msg.pouca_confianca')}", Cor.AMARELO))
                if not conteudo:
                    print(c(f"[openTARS] {t('msg.sem_texto', modelo=modelo)}", Cor.AMARELO))
                elif busca_sem_abrir and _RE_DIZ_QUE_ABRIU.search(normalizar(conteudo)):
                    # 18/10: o Lite escreve "o resultado foi aberto no navegador" por hábito do treino; com o SearXNG nada abriu
                    print(c(f"[openTARS] {t('msg.busca_nada_aberto')}", Cor.AMARELO))
                elif busca_sem_leitura and not _RE_FALA_DO_NAVEGADOR.search(normalizar(conteudo)):
                    # 18/10: o Lite abria a busca e respondia de memória como se tivesse lido. Quem avisa é o app, não o modelo.
                    print(c(f"[openTARS] {t('msg.busca_nao_lida')}", Cor.AMARELO))
                desfecho = _desfecho(tarefa, conteudo, usou_ferramenta, algum_sucesso, mentiu)
                emitir("tempo", modo=modo_modelo, modelo=modelo, segundos=time.time() - inicio_total)
                return conteudo

            mensagens.append({"role": "assistant", "content": conteudo, "tool_calls": tool_calls})
            usou_ferramenta = True
            desistiu = False
            pendentes[:] = [ch.get("function", {}).get("name", "") for ch in tool_calls]
            ultima_imagem = None

            for chamada in tool_calls:

                _verificar_cancelamento()

                funcao = chamada.get("function", {})
                nome = funcao.get("name", "")
                argumentos = _argumentos_da_chamada(funcao)
                chave_chamada = (nome, json.dumps(argumentos, sort_keys=True, ensure_ascii=False))
                oferecidas = {f["function"]["name"] for f in ferramentas}
                if nome in _FERRAMENTAS_SO_SE_PEDIDAS and nome not in oferecidas:
                    # Memória/agenda só quando o PEDIDO fala disso: uma página
                    # lida ou um modelo confuso não apaga a memória nem agenda nada.
                    resultado_ferramenta = {"sucesso": False, "mensagem": (
                        f"{nome} is not available for this request (the user did not ask to remember, "
                        "forget or schedule anything). Don't use it.")}
                elif chave_chamada in chamadas_que_falharam:
                    # Mesma chamada, mesmos argumentos, já falhou neste pedido.
                    resultado_ferramenta = {"sucesso": False, "mensagem": (
                        f"You already tried exactly this {nome} call and it failed: "
                        f"{chamadas_que_falharam[chave_chamada]} Do something different.")}
                else:
                    resultado_ferramenta = executar_ferramenta(nome, argumentos)
                pendentes.pop(0)
                if nome == "take_screenshot":
                    janela_do_print = argumentos.get("window") or None
                    arquivo_do_print = resultado_ferramenta.get("arquivo")

                ultima_falhou = not resultado_ferramenta.get("sucesso")
                sem_efeito = bool(resultado_ferramenta.get("sem_efeito"))
                if nome not in _FERRAMENTAS_SO_OLHAM:
                    ultima_sem_efeito = sem_efeito
                if resultado_ferramenta.get("sucesso") and sem_efeito:
                    # "Clicou", mas a tela não mudou: não é progresso. Conta
                    # pra desistir (andar em círculos clicando no nada).
                    sem_efeito_seguidos += 1
                    if sum(falhas_seguidas.values()) + sem_efeito_seguidos >= LIMITE_FALHAS_SEGUIDAS:
                        desistiu = True
                elif resultado_ferramenta.get("sucesso"):
                    algum_sucesso = True
                    if nome == "search_web":
                        busca_sem_leitura = not resultado_ferramenta.get("leu_resultados")
                        busca_sem_abrir = bool(resultado_ferramenta.get("leu_resultados")) and not resultado_ferramenta.get("url")
                    elif nome in ("take_screenshot", "read_page", "web_search"):
                        busca_sem_leitura = False
                    falhas_seguidas.clear()
                    sem_efeito_seguidos = 0
                    if nome not in _FERRAMENTAS_SO_OLHAM:
                        acoes_feitas += 1
                        feitas_resumo.append(f"{nome}({json.dumps(argumentos, ensure_ascii=False)[:80]})")
                else:
                    chamadas_que_falharam[chave_chamada] = str(resultado_ferramenta.get("mensagem", ""))[:300]
                    falhas_seguidas[nome] = falhas_seguidas.get(nome, 0) + 1
                    total_falhas = sum(falhas_seguidas.values()) + sem_efeito_seguidos
                    if falhas_seguidas[nome] >= LIMITE_FALHAS_MESMA_FERRAMENTA:
                        resultado_ferramenta["mensagem"] = (
                            f"{resultado_ferramenta.get('mensagem', '')} STOP: {nome} failed "
                            f"{falhas_seguidas[nome]} times in a row. Don't call it again for this; "
                            "change approach (another tool) or tell the user what is blocking you."
                        )
                    if total_falhas >= LIMITE_FALHAS_SEGUIDAS:
                        desistiu = True

                # A imagem do print nunca entra no JSON de texto (custaria
                # uma fortuna de tokens): vai como mensagem de visão.
                imagem_b64 = resultado_ferramenta.pop("_imagem_b64", None)
                if imagem_b64:
                    ultima_imagem = imagem_b64

                mensagens.append({
                    "role": "tool",
                    "tool_name": nome,  # ajuda o modelo a ligar resultado e chamada
                    "content": json.dumps(_para_ia(resultado_ferramenta), ensure_ascii=False),
                })

            # A imagem vai DEPOIS de todos os resultados: cada resultado
            # tem que vir logo após as chamadas que o geraram.
            if ultima_imagem and (not modelo_enxerga(modelo) or eh_gargantua(modelo)):
                # Modelo sem visão: o print não vai (o Ollama recusaria o
                # pedido inteiro); vai a descrição em texto. O Gargantua 2 enxerga, mas o treino dele com ferramentas não
                # tem imagem no meio da conversa: ele olha o print numa pergunta à parte (o formato em que foi treinado)
                # e o laço de ferramentas recebe o texto com as posições.
                mensagens.append({"role": "user", "content": _print_em_texto(ultima_imagem, texto, modelo, janela_do_print, arquivo_do_print)})
            elif ultima_imagem:
                # Prints antigos saem da conversa: cada um ocupa ~1 mil
                # tokens de contexto e só a tela atual importa.
                for anterior in mensagens:
                    if anterior.get("images"):
                        anterior.pop("images")
                        if _e_mensagem_de_print(anterior):  # o pedido do usuário (com arquivos anexados) não se apaga
                            anterior["content"] = "[previous screenshot removed: see the latest one]"

                # Vai como "user" (é onde o Ollama aceita imagem), mas
                # sem parecer um pedido novo: antes o modelo lia
                # "usuário mandou um print" e esquecia a tarefa.
                mensagens.append({
                    "role": "user",
                    "content": _mensagem_do_print(texto, arquivo_do_print),
                    "images": [ultima_imagem],
                })

            if desistiu and not algum_sucesso and trocar_de_modelo("msg.tentando_outro_modelo"):
                # Nada funcionou (e nada mudou no computador): outro modelo
                # tenta, vendo o que já falhou (e sem poder repetir igual).
                falhas_seguidas.clear()
                sem_efeito_seguidos = 0
                desistiu = False
                mensagens.append({"role": "user", "content": _mensagem_outro_modelo(texto)})
                continue

            if desistiu:
                desfecho = False
                # Muitas falhas seguidas: a IA está andando em círculos.
                # Uma última rodada SEM ferramentas pra ela explicar ao
                # usuário o que travou, em vez de gastar as 20 etapas.
                print(c(f"[openTARS] {t('msg.muitas_falhas', n=LIMITE_FALHAS_SEGUIDAS)}", Cor.AMARELO))
                mensagens.append({"role": "user", "content": (
                    "[Automatic message from openTARS] Too many tool calls failed in a row. Stop "
                    "using tools: in 2-3 sentences, tell the user what you tried, what blocked you, "
                    "and what they can do (e.g. click it themselves, or another way to ask).")})
                resultado, erro = _executar_turno_streaming(modelo, mensagens, None, pensar=False)
                conteudo = (resultado or {}).get("content") or t("msg.muitas_falhas", n=LIMITE_FALHAS_SEGUIDAS)
                mensagens.append({"role": "assistant", "content": conteudo})
                emitir("tempo", modo=modo_modelo, modelo=modelo, segundos=time.time() - inicio_total)
                return conteudo

            emitir("analisando", modelo=modelo)

        desfecho = False
        mensagem_limite = t("msg.limite_etapas", n=ciclo)
        print(c(f"\n[openTARS] {mensagem_limite}", Cor.VERMELHO))
        return mensagem_limite

    except (RespostaCancelada, KeyboardInterrupt):
        _cancelar.clear()
        # Toda chamada de ferramenta precisa de um resultado, senão o
        # próximo pedido vai com a conversa quebrada.
        for nome in pendentes:
            mensagens.append({
                "role": "tool",
                "tool_name": nome,
                "content": json.dumps({"success": False, "message": "Cancelled by the user."}),
            })
        mensagens.append({"role": "assistant", "content": "(interrupted by the user)"})
        print(c(f"\n[openTARS] {t('msg.interrompido')}", Cor.AMARELO))
        return RESPOSTA_INTERROMPIDA

    finally:
        _podar_historico(mensagens)
        if tarefa and modo_modelo == "AUTO":
            historico_modelos.registrar(modelo, _tarefa_do_historico(tarefa), desfecho)


def processar_mensagem(texto, anexos=None):
    """Um pedido do usuário do começo ao fim: comandos (/modelo,
    /limpar...), escolha do modelo, resposta e salvamento. Usado pelo
    terminal e pela janela, que antes repetiam essa lógica cada um."""

    # Limpa aqui (e não no meio do caminho): um Parar apertado enquanto
    # o openTARS ainda escolhe o modelo continua valendo.
    _cancelar.clear()

    if interpretar_comando_modelo(texto):
        return None

    if not anexos and not os.environ.get("TARS_SEM_AUTO_IMAGEM"):
        # o pedido cita uma imagem ("veja home/pictures/foto.png"): anexa sozinho, sem depender de
        # o modelo saber chamar uma ferramenta (o modelo de visão descreve se ele não enxerga)
        try:
            citadas = anexos_lib.achar_imagens_no_texto(texto)
            if citadas:
                anexos, _erros = anexos_lib.carregar_varios([str(x) for x in citadas])
                for a in anexos or []:
                    print(c(f"[openTARS] {t('msg.imagem_citada', nome=a.nome)}", Cor.CINZA))
        except Exception:
            anexos = None

    if anexos and not (texto or "").strip():
        texto = TEXTO_PEDIDO_SO_ANEXOS

    # "use a ferramenta", "faz de verdade", "try again": a tarefa e o modelo saem do pedido anterior, que é o que vai ser feito
    retoma = _ultimo_pedido_real() if not anexos and escolha.eh_retomada(normalizar(texto)) else None
    base = retoma or texto
    _pedido_atual["texto"] = base       # o search_web vê se a pessoa pediu para abrir a busca no navegador
    tarefa = detectar_tarefa(base) if modo_modelo == "AUTO" else None
    decisao = _ultima_decisao["d"] if tarefa else None
    if tarefa:
        lembrar_tarefa(tarefa)
    # Várias etapas também contam no modo MANUAL (pensar + lembrete).
    multi = decisao.multi_etapas if decisao else escolha.eh_multi_etapas(normalizar(base), _verbos_de_acao())
    modelo = escolher_modelo(base, tarefa=tarefa, complexa=multi)

    emitir("tarefa", modo=modo_modelo, tarefa=tarefa, modelo=modelo, via=decisao.via if decisao else None)

    try:
        return perguntar_modelo(modelo, texto, tarefa=tarefa, multi_etapas=multi, anexos=anexos or None, retoma=retoma)
    finally:
        salvar_sessoes()
