"""Lembretes e timers por frase (F4++ do PLANO_5.3.md, 07/11), sem o modelo.

Medido antes: "me lembra de tomar água daqui a 30 minutos" virava uma memória ("Vou lembrar"), e "põe um timer de 5 minutos" tentava
programas que não existem e dizia que o timer estava rodando. Nenhum aviso era agendado.
Aqui a frase vira uma rotina de uma vez na agenda que o app já tem (tars_rotinas); na hora, o pedido "Lembrete: ..." sai por regra
(resposta_da_rotina) e a janela avisa como avisa qualquer rotina. Só dispara com o openTARS aberto (ou na bandeja).
"""
import datetime as dt
import re
import unicodedata

import tars_rotinas

_NUMEROS = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10,
            "quinze": 15, "vinte": 20, "trinta": 30, "quarenta": 40, "meia": 30, "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "five": 5,
            "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30}
_N = r"(\d+|um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez|quinze|vinte|trinta|quarenta|a|an|one|two|three|five|ten|fifteen|twenty|thirty)"
_PEDE = re.compile(r"^(?:por favor |please |pode |can you )?(?:me lembra|me lembre|lembra-me|me avisa|me avise|avisa-me|remind me|ping me)\b")
_PEDE_SEM_DUVIDA = re.compile(r"^(?:por favor |please |pode |can you )?(?:me lembra|me lembre|lembra-me|remind me)\b")
_TIMER = re.compile(r"\b(?:timer|temporizador|cronometro|alarme|alarm)\b")
_DAQUI = re.compile(r"\b(?:daqui a|daqui|em|dentro de|in|after)\s+" + _N + r"\s*(minutos?|mins?|min|horas?|h|hours?|segundos?|seconds?|s)\b")
_DURACAO = re.compile(_N + r"[\s-]*(minutos?|mins?|min|minute|horas?|hours?|h|segundos?|seconds?|s)\b")
_HORA = re.compile(r"\b(?:as|a|at|pras|para as|ao meio)\s*(\d{1,2})(?:[:h](\d{2}))?\s*(?:h|horas)?\s*(am|pm|da manha|da tarde|da noite)?\b|\b(\d{1,2})\s*(am|pm)\b|\b(meio[- ]dia|noon|midnight|meia[- ]noite)\b")
_AMANHA = re.compile(r"\b(amanha|tomorrow)\b")


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)).lower().strip()


def _numero(texto):
    return int(texto) if texto.isdigit() else _NUMEROS.get(texto, 1)


def _segundos(numero, unidade):
    u = unidade[0]
    return _numero(numero) * (3600 if u == "h" else 1 if u == "s" else 60)


def _quando(n, agora):
    """O datetime pedido, ou None se a frase não diz quando."""
    a = _DAQUI.search(n)
    if a:
        return agora + dt.timedelta(seconds=_segundos(a.group(1), a.group(2)))
    h = _HORA.search(n)
    if not h:
        return None
    if h.group(6):
        hora, minuto = (12, 0) if h.group(6).startswith(("meio", "noon")) else (0, 0)
    else:
        hora = int(h.group(1) or h.group(4))
        minuto = int(h.group(2) or 0)
        periodo = h.group(3) or h.group(5) or ""
        if periodo in ("pm", "da tarde", "da noite") and hora < 12:
            hora += 12
        if periodo in ("am", "da manha") and hora == 12:
            hora = 0
    if hora > 23 or minuto > 59:
        return None
    alvo = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
    if _AMANHA.search(n):
        alvo += dt.timedelta(days=1)
    elif alvo <= agora:
        alvo += dt.timedelta(days=1)
    return alvo


def _o_que(original, n):
    """O texto do lembrete, com os acentos e as maiúsculas de quem escreveu: o pedido sem o "me lembra" e sem o quando."""
    base = original.strip() if len(original.strip()) == len(n) else n
    apagar = [False] * len(n)
    for padrao in (_PEDE, _DAQUI, _HORA, _AMANHA):
        for m in padrao.finditer(n):
            for k in range(m.start(), m.end()):
                apagar[k] = True
    texto = " ".join("".join(" " if apagar[k] else c for k, c in enumerate(base)).split())
    texto = re.sub(r"^(?:de|que|para|pra|to|that|about)\s+", "", texto, flags=re.IGNORECASE)
    return re.sub(r"\s+(?:de|para|pra|to|e|and)$", "", texto, flags=re.IGNORECASE).strip(" ,.!?")


def entender(texto, agora=None):
    """{'tipo': 'lembrete'|'timer', 'quando': datetime, 'texto': ...}, {'tipo': 'falta_hora'} ou None."""
    n = _sem_acento(texto)
    agora = agora or dt.datetime.now().replace(microsecond=0)
    if _TIMER.search(n) and re.search(r"\b(poe|ponha|coloca|coloque|liga|ligue|cria|crie|marca|marque|faz|set|start|put|make|timer de|timer for)\b|^timer\b", n):
        d = _DURACAO.search(n)
        if not d:
            return {"tipo": "falta_hora"}
        segundos = _segundos(d.group(1), d.group(2))
        rotulo = f"{_numero(d.group(1))} {d.group(2)}"
        return {"tipo": "timer", "quando": agora + dt.timedelta(seconds=segundos), "texto": rotulo}
    if not _PEDE.search(n):
        return None
    quando = _quando(n, agora)
    if quando is None:          # "me avisa se..." sem hora não é lembrete; "me lembra de..." sem hora pergunta quando
        return {"tipo": "falta_hora"} if _PEDE_SEM_DUVIDA.search(n) else None
    return {"tipo": "lembrete", "quando": quando, "texto": _o_que(texto, n) or ("isso" if re.search(r"[ãçáé]|\bde\b", n) else "this")}


def agendar(pedido, idioma, agenda=None):
    """Cria a rotina e devolve a frase de confirmação; None se a frase não é de lembrete nem de timer."""
    e = entender(pedido)
    if e is None:
        return None
    pt = idioma == "pt"
    if e["tipo"] == "falta_hora":
        return "Quando te lembro? Por exemplo: daqui a 30 minutos, ou amanhã às 9h." if pt else "When should I remind you? For example: in 30 minutes, or tomorrow at 9 am."
    agenda = agenda or tars_rotinas.Agenda()
    if e["tipo"] == "timer":
        nome, aviso = (f"Timer de {e['texto']}", f"Timer: {e['texto']} terminaram.") if pt else (f"{e['texto']} timer", f"Timer: {e['texto']} are up.")
    else:
        nome, aviso = (("Lembrete: " if pt else "Reminder: ") + e["texto"])[:tars_rotinas.LIMITE_NOME], ("Lembrete: " if pt else "Reminder: ") + e["texto"]
    rotina, erro = agenda.criar(nome, aviso, {"tipo": "uma_vez", "data": e["quando"].isoformat()}, ativa=True, aprovada=True, origem="pessoa")
    if erro:
        return ("Não consegui agendar (" + erro + ")." if pt else "I couldn't schedule it (" + erro + ").")
    dia = "" if e["quando"].date() == dt.date.today() else (" de amanhã" if pt else " tomorrow") if e["quando"].date() == dt.date.today() + dt.timedelta(days=1) \
        else f" de {e['quando']:%d/%m}" if pt else f" on {e['quando']:%m/%d}"
    hora = f"{e['quando']:%H:%M}"
    if e["tipo"] == "timer":
        return f"Timer de {e['texto']} ligado: toca às {hora}{dia}." if pt else f"{e['texto']} timer set: it goes off at {hora}{dia}."
    return f"Combinado: às {hora}{dia} eu te lembro de {e['texto']}." if pt else f"Got it: at {hora}{dia} I'll remind you to {e['texto']}."


_AVISO = re.compile(r"^(lembrete|reminder|timer):\s*(.+)$", re.IGNORECASE)


def resposta_da_rotina(pedido):
    """Quando a rotina dispara, o pedido "Lembrete: X" volta como o próprio aviso, sem o modelo."""
    a = _AVISO.match((pedido or "").strip())
    return f"⏰ {pedido.strip()}" if a else None
