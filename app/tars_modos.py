"""openTARS 5.1: os três modos da interface (Lite, Base e Pro) e os ajustes avançados do Pro.

Só biblioteca padrão: a janela pergunta aqui o que mostrar, e o núcleo pergunta os ajustes avançados.
A escolha fica em ~/.config/opentars/config.json ("modo" e "avancado"), o mesmo arquivo do idioma.

- Lite: conversa, microfone, anexos e o básico das configurações. Tudo no automático.
- Base: Lite + histórico, escolha de modelo, memória, rotinas, Probes e nuvem.
- Pro: Base + ajustes avançados e diagnóstico.
"""

import tars_i18n
import tars_primeiro_uso as pu

MODOS = ("lite", "base", "pro")
PADRAO_INSTALACAO_NOVA = "base"
PADRAO_ATUALIZACAO = "pro"       # quem já usava a 5.0 não perde nada do que via

_LITE = {"conversa", "microfone", "anexos", "cfg.geral", "cfg.assistente", "cfg.voz", "cfg.atualizacoes", "cfg.sobre"}
_BASE = _LITE | {"historico", "seletor_modelo", "memoria", "cfg.memoria", "cfg.rotinas", "cfg.probes", "cfg.nuvem", "cfg.modelos", "cfg.gerenciar"}
_PRO = _BASE | {"cfg.avancado", "cfg.diagnostico"}
RECURSOS = {"lite": _LITE, "base": _BASE, "pro": _PRO}

CONTEXTOS = (4096, 8192, 16384, 32768)
TEMPERATURA_MAXIMA = 1.5
LIMITE_INSTRUCOES = 1500


def modo_atual():
    m = tars_i18n.ler_config().get("modo")
    if m in MODOS:
        return m
    # sem escolha gravada: quem atualizou da 5.0 (primeiro uso já feito) fica no Pro; instalação nova, Base
    return PADRAO_ATUALIZACAO if pu.primeiro_uso_concluido() else PADRAO_INSTALACAO_NOVA


def definir_modo(modo):
    if modo not in MODOS:
        raise ValueError(f"modo desconhecido: {modo}")
    tars_i18n.salvar_config(modo=modo)


def mostra(recurso, modo=None):
    return recurso in RECURSOS[modo or modo_atual()]


# ------------------------------------------------------------
# Ajustes avançados (só valem no Pro; no Lite e no Base tudo fica no automático)
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
    """O que está gravado, valha ou não agora (a tela do Pro mostra isso)."""
    return _limpar(tars_i18n.ler_config().get("avancado"))


def avancado():
    """Os ajustes que valem agora: os gravados no Pro; os padrões nos outros modos."""
    return avancado_gravado() if modo_atual() == "pro" else _limpar({})


def salvar_avancado(**mudancas):
    atual = avancado_gravado()
    atual.update(mudancas)
    tars_i18n.salvar_config(avancado=_limpar(atual))
