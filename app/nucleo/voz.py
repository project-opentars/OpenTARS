# openTARS — nucleo/voz.py
# Voz (3.0): falar as respostas, ouvir "TARS", instalar o que falta.
# A parte pesada (microfone, Whisper, Piper) fica em tars_voz.py.
#
# Parte do núcleo: o tars.py executa este arquivo DENTRO do próprio
# namespace (ver _carregar_nucleo), então tudo aqui é tars.<nome> e as
# partes enxergam umas às outras sem import. Os testes que trocam
# tars.<função> por uma falsa continuam valendo pra todas as partes.
# flake8: noqa

# ============================================================
# VOZ
# ============================================================

_falador_voz = {"f": None}


def config_voz():
    """{'falar': bool, 'ativacao': bool} salvos no config.json."""
    dados = i18n.ler_config()
    return {"falar": bool(dados.get("voz_falar")), "ativacao": bool(dados.get("voz_ativacao"))}


def salvar_config_voz(**mudancas):
    i18n.salvar_config(**{f"voz_{k}": bool(v) for k, v in mudancas.items()})


def voz_no_idioma():
    """5.0: a voz existe em inglês e em português."""
    return voz_lib.tem_voz(i18n.idioma_atual())


def o_que_falta_voz():
    if not voz_no_idioma():
        return ["idioma"]
    return voz_lib.o_que_falta(i18n.idioma_atual())


def descrever_falta_voz(falta):
    """['piper-tts', 'gravador'] -> texto no idioma da pessoa."""
    return plataforma.dica_instalar(", ".join(t(f"voz.falta_{item.replace('-', '_')}") for item in falta))


def falador():
    if _falador_voz["f"] is None:
        _falador_voz["f"] = voz_lib.Falador()
    aplicar_preferencias_voz()
    return _falador_voz["f"]


# ------------------------------------------------------------
# 4.1: voz escolhida e velocidade
# ------------------------------------------------------------

def preferencias_voz():
    """{'vozes': {'pt_BR': 'cadu'}, 'velocidade': 1.0} salvos no config.json."""
    dados = i18n.ler_config()
    vozes = {idioma: dados.get(f"voz_nome_{idioma}") for idioma in voz_lib.VOZES_DISPONIVEIS
             if dados.get(f"voz_nome_{idioma}")}
    try:
        velocidade = float(dados.get("voz_velocidade") or 1.0)
    except (TypeError, ValueError):
        velocidade = 1.0
    return {"vozes": vozes, "velocidade": velocidade}


def aplicar_preferencias_voz():
    p = preferencias_voz()
    voz_lib.configurar(vozes=p["vozes"], velocidade=p["velocidade"], idioma=i18n.idioma_atual())


def voz_atual(idioma=None):
    return voz_lib.nome_da_voz(idioma or i18n.idioma_atual())


def vocabulario_voz():
    """Nomes dos apps instalados: o Whisper erra menos neles ("abre o Steam",
    "fecha o Discord")."""
    try:
        nomes = [e.get("nome") or "" for e in desktop_entries()]
    except Exception:
        nomes = []
    curtos = {n.strip() for n in nomes if 2 <= len(n.strip()) <= 24 and len(n.split()) <= 3}
    return sorted(curtos, key=lambda n: (len(n), n.lower()))[:40]


def escolher_voz(nome, avisar=None):
    """Troca a voz do idioma atual (baixa se ainda não tiver). (ok, mensagem)"""
    idioma = i18n.idioma_atual() if i18n.idioma_atual() in voz_lib.VOZES_DISPONIVEIS else "en"
    disponiveis = voz_lib.VOZES_DISPONIVEIS.get(idioma, {})
    nome = (nome or "").strip().lower()
    if nome not in disponiveis:
        return False, t("voz.nome_invalido", nome=nome, lista=", ".join(disponiveis))
    if not voz_lib.kokoro_baixado():
        ok, erro = voz_lib.baixar_voz(idioma, avisar or (lambda msg: None), nome=nome)
        if not ok:
            return False, t("voz.erro_instalar", erro=erro)
    i18n.salvar_config(**{f"voz_nome_{idioma}": nome})
    aplicar_preferencias_voz()
    return True, t("voz.escolhida", nome=nome.capitalize())


def definir_velocidade_voz(valor):
    try:
        v = float(str(valor).replace(",", "."))
    except ValueError:
        return False, t("voz.velocidade_invalida", valor=valor)
    v = min(voz_lib.VELOCIDADE_MAX, max(voz_lib.VELOCIDADE_MIN, v))
    i18n.salvar_config(voz_velocidade=round(v, 2))
    aplicar_preferencias_voz()
    return True, t("voz.velocidade_ok", valor=f"{v:.2f}")


def frase_de_teste_voz():
    return t("voz.frase_teste", nome=voz_atual().capitalize())


def falar_resposta(texto, forcar=False, ao_terminar=None):
    """Lê a resposta em voz alta se a pessoa ligou "responder falando".
    ao_terminar: chamado quando a fala acaba (pra ouvir a continuação)."""
    if not texto or texto == RESPOSTA_INTERROMPIDA:
        return False
    if not (forcar or config_voz()["falar"]) or o_que_falta_voz():
        return False
    return falador().falar(texto, i18n.idioma_atual(), ao_terminar=ao_terminar)


def instalar_voz(avisar=None):
    avisar = avisar or (lambda msg: print(c(f"[openTARS] {msg}", Cor.CINZA)))
    faltava = o_que_falta_voz()
    duras = [x for x in faltava if x in ("gravador", "tocador")]
    if duras:
        return False, t("voz.precisa_sistema", itens=descrever_falta_voz(duras))
    ok, erro = voz_lib.instalar(i18n.idioma_atual(), avisar)
    return ok, ("" if ok else erro)


def modo_voz_terminal():
    """opentars --voz: fica ouvindo "TARS" e responde falando."""
    falta = o_que_falta_voz()
    if falta:
        print(c(t("voz.falta", itens=descrever_falta_voz(falta)), Cor.AMARELO))
        return 1
    pedidos = []
    trava = threading.Event()

    def ao_pedido(texto):
        pedidos.append(texto)
        trava.set()

    def ao_estado(estado):
        if estado == "chamado":
            print(c(f"[openTARS] {t('voz.chamado')}", Cor.CIANO))
        elif estado == "conversa":
            print(c(f"[openTARS] {t('gui.voz_conversa')}", Cor.CINZA))
        elif estado == "carregando":
            print(c(f"[openTARS] {t('gui.voz_carregando')}", Cor.CINZA))
        elif estado.startswith("erro:"):
            print(c(f"[openTARS] {t('voz.erro_microfone', erro=estado[5:])}", Cor.VERMELHO))
            trava.set()

    ouvinte = voz_lib.Ouvinte(ao_pedido, i18n.idioma_atual, modo="ativacao", ao_estado=ao_estado,
                              falador=falador(), vocabulario=vocabulario_voz)
    ouvinte.iniciar()
    print(c(t("voz.ouvindo"), Cor.CIANO))
    try:
        while ouvinte.ativo:
            if not trava.wait(0.5):
                continue
            trava.clear()
            while pedidos:
                texto = pedidos.pop(0)
                print(c(t("term.voce"), Cor.NEGRITO + Cor.VERDE) + f" ({t('voz.por_voz')}) {texto}")
                with TRAVA_PEDIDO:
                    resposta = processar_mensagem(texto)
                if not falar_resposta(resposta, forcar=True, ao_terminar=ouvinte.abrir_conversa):
                    ouvinte.abrir_conversa()
    except KeyboardInterrupt:
        print()
    finally:
        ouvinte.parar()
        falador().parar()
    return 0
