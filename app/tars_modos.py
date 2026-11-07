"""openTARS 5.3: um modo só (Base) e a chave "dev", que acrescenta os ajustes avançados e o diagnóstico.

Até a 5.2 havia Lite, Base e Pro; em 07/11 o Enzo decidiu: Base para todo mundo e "dev" nas Configurações.
Quem usava o Pro atualiza com o dev ligado; quem usava o Lite ou o Base fica no Base.
Só biblioteca padrão: a janela pergunta aqui o que mostrar, e o núcleo pergunta os ajustes avançados.
A escolha fica em ~/.config/opentars/config.json ("dev", e o "modo" antigo só para migrar).
"""

import tars_i18n
import tars_primeiro_uso as pu

MODOS = ("base", "dev")

_BASE = {"conversa", "microfone", "anexos", "cfg.geral", "cfg.assistente", "cfg.voz", "cfg.atualizacoes", "cfg.sobre",
         "historico", "seletor_modelo", "memoria", "cfg.memoria", "cfg.rotinas", "cfg.probes", "cfg.nuvem", "cfg.modelos", "cfg.gerenciar"}
_DEV = _BASE | {"cfg.avancado", "cfg.diagnostico"}
RECURSOS = {"base": _BASE, "dev": _DEV}
_ANTIGOS = {"lite": "base", "pro": "dev"}

CONTEXTOS = (4096, 8192, 16384, 32768)
TEMPERATURA_MAXIMA = 1.5
LIMITE_INSTRUCOES = 1500


def dev_ligado():
    config = tars_i18n.ler_config()
    if isinstance(config.get("dev"), bool):
        return config["dev"]
    antigo = config.get("modo")
    if antigo in ("lite", "base"):
        return False
    if antigo == "pro":
        return True
    # sem escolha gravada: quem atualizou da 5.0 via tudo (o antigo Pro); instalação nova começa no Base
    return pu.primeiro_uso_concluido()


def definir_dev(ligado):
    tars_i18n.salvar_config(dev=bool(ligado))


def modo_atual():
    return "dev" if dev_ligado() else "base"


def definir_modo(modo):
    """Compatibilidade: "pro"/"dev" ligam o dev; "lite"/"base" desligam."""
    if modo not in MODOS and modo not in _ANTIGOS:
        raise ValueError(f"modo desconhecido: {modo}")
    definir_dev(_ANTIGOS.get(modo, modo) == "dev")


def mostra(recurso, modo=None):
    return recurso in RECURSOS[_ANTIGOS.get(modo, modo) or modo_atual()]


# ------------------------------------------------------------
# Ajustes avançados (só valem com o dev ligado; no Base tudo fica no automático)
# ------------------------------------------------------------

def _limpar(bruto):
    bruto = bruto if isinstance(bruto, dict) else {}
    a = {"temperatura": None, "contexto": None, "instrucoes": "", "ferramentas_desligadas": []}
    try:
        if bruto.get("temperatura") is not None:
            a["temperatura"] = min(TEMPERATURA_MAXIMA, max(0.0, round(float(bruto["temperatura"]), 2)))
    except (TypeError, ValueError):
        pass
    if bruto.get("contexto") in CONTEXTOS:
        a["contexto"] = bruto["contexto"]
    a["instrucoes"] = str(bruto.get("instrucoes") or "").strip()[:LIMITE_INSTRUCOES]
    desligadas = bruto.get("ferramentas_desligadas")
    if isinstance(desligadas, list):
        a["ferramentas_desligadas"] = sorted({str(x) for x in desligadas if isinstance(x, str) and x.strip()})
    return a


def avancado_gravado():
    """O que está gravado, valha ou não agora (a tela dos ajustes avançados mostra isso)."""
    return _limpar(tars_i18n.ler_config().get("avancado"))


def avancado():
    """Os ajustes que valem agora: os gravados, com o dev ligado; os padrões, no Base."""
    return avancado_gravado() if dev_ligado() else _limpar({})


def salvar_avancado(**mudancas):
    atual = avancado_gravado()
    atual.update(mudancas)
    tars_i18n.salvar_config(avancado=_limpar(atual))
