"""5.3 (F4+++): integrações do assistente com a agenda e com as notas da pessoa, resolvidas por código (sem o modelo) e
DESLIGADAS por padrão: só valem depois de a pessoa dizer, nas Configurações > Assistente, qual arquivo .ics (ou link) e qual
pasta de notas usar. Só biblioteca padrão (mais o `requests` do app para o link do calendário). Nada sai do computador: o
calendário é só lido, e as notas são arquivos Markdown comuns numa pasta que a pessoa escolheu.

Agenda: lê eventos de arquivos .ics (Google, Outlook, Apple e Thunderbird exportam) com repetição diária, semanal, mensal e anual
(INTERVAL, COUNT, UNTIL, BYDAY, BYMONTHDAY, exceções e instâncias alteradas). Responde "o que tenho amanhã?", "what's on my
calendar this week?", "qual meu próximo compromisso?".
  Limites: sem enviar convite nem criar evento (só leitura); fuso com nome do Windows ("W. Europe Standard Time") que o sistema
  não conhece é tratado como horário local; BYSETPOS e regras raras ficam de fora e o evento só vale na primeira data.
Notas: "cria uma nota: ..." grava um .md novo (nunca por cima de outro) e "minhas notas sobre X" / "show the note X" procura e lê.
"""
import datetime as dt
import re
import time
import unicodedata
from pathlib import Path

import tars_i18n

CACHE_LINK_S = 900
LIMITE_ITERACOES = 6000
LIMITE_LISTA = 15
_cache_link = {}

TEXTOS = {
    "pt": {"nada": "Não há nada na agenda para {quando}.", "um": "{Quando} você tem 1 compromisso:", "varios": "{Quando} você tem {n} compromissos:",
           "dia_inteiro": "dia inteiro", "proximo": "Seu próximo compromisso: {quando}, {titulo}{local}.", "sem_proximo": "Não achei compromisso nos próximos 60 dias.",
           "mais": "… e mais {n}.", "erro": "Não consegui ler a agenda ({erro}).",
           "nota_criada": "Nota criada: {nome}, em {pasta}.", "nota_vazia": "Diga o que escrever: cria uma nota: comprar pão.",
           "notas_nada": "Não achei nada nas notas sobre {termo}.", "notas_achei": "Achei {n} em suas notas:", "nota_texto": "{nome}:\n{texto}",
           "nota_nao_achei": "Não achei a nota {termo}.",
           "hoje": "hoje", "amanha": "amanhã", "depois": "depois de amanhã", "semana": "esta semana", "semana_que_vem": "a semana que vem",
           "dias": ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]},
    "en": {"nada": "There is nothing on your calendar for {quando}.", "um": "{Quando} you have 1 event:", "varios": "{Quando} you have {n} events:",
           "dia_inteiro": "all day", "proximo": "Your next event: {quando}, {titulo}{local}.", "sem_proximo": "I found no events in the next 60 days.",
           "mais": "… and {n} more.", "erro": "I couldn't read the calendar ({erro}).",
           "nota_criada": "Note created: {nome}, in {pasta}.", "nota_vazia": "Tell me what to write: create a note: buy bread.",
           "notas_nada": "I found nothing about {termo} in your notes.", "notas_achei": "Found {n} in your notes:", "nota_texto": "{nome}:\n{texto}",
           "nota_nao_achei": "I couldn't find the note {termo}.",
           "hoje": "today", "amanha": "tomorrow", "depois": "the day after tomorrow", "semana": "this week", "semana_que_vem": "next week",
           "dias": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]},
}
_DIAS_ICS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def _t(chave, idioma, **kw):
    return TEXTOS["pt" if idioma == "pt" else "en"][chave].format(**kw) if kw else TEXTOS["pt" if idioma == "pt" else "en"][chave]


def normalizar(texto):
    return unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()


# ---------------------------------------------------------------- configuração (desligado por padrão)
def agendas():
    """Os arquivos .ics ou links escolhidos pela pessoa; lista vazia = agenda desligada."""
    valor = tars_i18n.ler_config().get("agenda_ics") or []
    return [str(v).strip() for v in ([valor] if isinstance(valor, str) else valor) if str(v).strip()]


def pasta_de_notas():
    valor = str(tars_i18n.ler_config().get("notas_pasta") or "").strip()
    return Path(valor).expanduser() if valor else None


# ---------------------------------------------------------------- ICS: ler
def _desdobrar(texto):
    """Linhas do iCalendar: uma linha que começa com espaço ou tab continua a anterior."""
    linhas = []
    for bruta in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if bruta[:1] in (" ", "\t") and linhas:
            linhas[-1] += bruta[1:]
        elif bruta:
            linhas.append(bruta)
    return linhas


def _propriedade(linha):
    cabeca, _, valor = linha.partition(":")
    nome, *params = cabeca.split(";")
    p = {}
    for par in params:
        k, _, v = par.partition("=")
        p[k.upper()] = v.strip('"')
    return nome.upper(), p, valor


def _desescapar(valor):
    return valor.replace("\\n", " ").replace("\\N", " ").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def _fuso(nome):
    if not nome:
        return None
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(nome)
    except Exception:  # noqa: BLE001  (nome do Windows ou sem tzdata: horário local)
        return None


def _quando(valor, params):
    """(data e hora SEM fuso no horário do próprio evento, fuso, dia_inteiro)."""
    valor = valor.strip()
    if params.get("VALUE") == "DATE" or (len(valor) == 8 and valor.isdigit()):
        return dt.datetime.strptime(valor[:8], "%Y%m%d"), None, True
    utc = valor.endswith("Z")
    naive = dt.datetime.strptime(valor.rstrip("Z")[:15], "%Y%m%dT%H%M%S")
    if utc:
        return naive, dt.timezone.utc, False
    return naive, _fuso(params.get("TZID")), False


def _local(naive, fuso):
    """O horário da parede do evento, no horário local do computador, sem fuso."""
    if fuso is None:
        return naive
    return naive.replace(tzinfo=fuso).astimezone().replace(tzinfo=None)


def _duracao(valor):
    m = re.fullmatch(r"([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", valor.strip())
    if not m:
        return dt.timedelta(0)
    sinal = -1 if m.group(1) == "-" else 1
    sem, dia, h, mi, s = (int(x or 0) for x in m.groups()[1:])
    return sinal * dt.timedelta(weeks=sem, days=dia, hours=h, minutes=mi, seconds=s)


def ler_ics(texto):
    """Os eventos do texto de um .ics: [{uid, inicio, fuso, dia_inteiro, duracao, titulo, local, regra, excecoes, id_instancia}]."""
    eventos, atual = [], None
    for linha in _desdobrar(texto):
        if linha.upper() == "BEGIN:VEVENT":
            atual = {"props": []}
        elif linha.upper() == "END:VEVENT" and atual is not None:
            e = _montar(atual["props"])
            if e:
                eventos.append(e)
            atual = None
        elif atual is not None:
            atual["props"].append(_propriedade(linha))
    return eventos


def _montar(props):
    d = {}
    excecoes = []
    for nome, p, valor in props:
        if nome == "EXDATE":
            excecoes += [(v, p) for v in valor.split(",") if v.strip()]
        else:
            d.setdefault(nome, (p, valor))
    if "DTSTART" not in d or d.get("STATUS", ({}, ""))[1].upper() == "CANCELLED":
        return None
    try:
        inicio, fuso, inteiro = _quando(d["DTSTART"][1], d["DTSTART"][0])
        if "DTEND" in d:
            fim, fuso_fim, _ = _quando(d["DTEND"][1], d["DTEND"][0])
            duracao = (fim - inicio) if fuso_fim == fuso else _local(fim, fuso_fim) - _local(inicio, fuso)
        elif "DURATION" in d:
            duracao = _duracao(d["DURATION"][1])
        else:
            duracao = dt.timedelta(days=1) if inteiro else dt.timedelta(0)
        regra = {}
        for parte in (d.get("RRULE", ({}, ""))[1]).split(";"):
            k, _, v = parte.partition("=")
            if k:
                regra[k.upper()] = v
        sem = {_quando(v, p)[0] for v, p in excecoes}
        instancia = _quando(d["RECURRENCE-ID"][1], d["RECURRENCE-ID"][0])[0] if "RECURRENCE-ID" in d else None
    except (ValueError, KeyError):
        return None
    return {"uid": d.get("UID", ({}, ""))[1], "inicio": inicio, "fuso": fuso, "dia_inteiro": inteiro, "duracao": duracao,
            "titulo": _desescapar(d.get("SUMMARY", ({}, ""))[1]) or "(sem título)", "local": _desescapar(d.get("LOCATION", ({}, ""))[1]),
            "regra": regra, "excecoes": sem, "id_instancia": instancia}


# ---------------------------------------------------------------- ICS: repetir
def _passos_da_regra(e):
    """As datas (horário da parede do evento) de cada ocorrência, em ordem, a partir do início. Para quando a regra acaba."""
    r, inicio = e["regra"], e["inicio"]
    if not r.get("FREQ"):
        yield inicio
        return
    freq, intervalo = r["FREQ"].upper(), max(1, int(r.get("INTERVAL") or 1))
    contagem = int(r["COUNT"]) if r.get("COUNT", "").isdigit() else None
    ate = None
    if r.get("UNTIL"):
        try:
            u, fuso_u, _ = _quando(r["UNTIL"], {})
            ate = u if fuso_u is None else _local(u, fuso_u)
            ate = ate + dt.timedelta(days=1) if len(r["UNTIL"]) == 8 else ate
        except ValueError:
            ate = None
    emitidos = 0
    hora = inicio.time()
    por_dia = [(int(m.group(1) or 0), _DIAS_ICS[m.group(2)]) for m in re.finditer(r"([+-]?\d+)?(MO|TU|WE|TH|FR|SA|SU)", r.get("BYDAY", ""))]
    dias_mes = [int(x) for x in r.get("BYMONTHDAY", "").split(",") if x.strip("-").isdigit()]

    def candidatos():
        if freq == "DAILY":
            n = 0
            while True:
                yield inicio + dt.timedelta(days=n * intervalo)
                n += 1
        elif freq == "WEEKLY":
            segunda = inicio - dt.timedelta(days=inicio.weekday())
            dias = sorted({d for _, d in por_dia}) or [inicio.weekday()]
            n = 0
            while True:
                base = segunda + dt.timedelta(weeks=n * intervalo)
                for d in dias:
                    yield dt.datetime.combine((base + dt.timedelta(days=d)).date(), hora)
                n += 1
        elif freq in ("MONTHLY", "YEARLY"):
            n = 0
            while True:
                total = (inicio.year * 12 + inicio.month - 1) + (n * intervalo * (12 if freq == "YEARLY" else 1))
                ano, mes = divmod(total, 12)
                mes += 1
                if freq == "YEARLY" and por_dia == [] and not dias_mes:
                    dias = [inicio.day]
                else:
                    dias = list(dias_mes) or []
                    if por_dia and freq == "MONTHLY":
                        dias += _dias_da_semana_do_mes(ano, mes, por_dia)
                    if not dias:
                        dias = [inicio.day]
                ultimo = (dt.date(ano + (mes == 12), mes % 12 + 1, 1) - dt.timedelta(days=1)).day
                for d in sorted(set(dias)):
                    d = ultimo + 1 + d if d < 0 else d
                    if 1 <= d <= ultimo:
                        yield dt.datetime.combine(dt.date(ano, mes, d), hora)
                n += 1
        else:
            yield inicio

    for c in candidatos():
        if c < inicio:
            continue
        if ate is not None and c >= ate:
            return
        emitidos += 1
        if contagem is not None and emitidos > contagem:
            return
        yield c
        if emitidos >= LIMITE_ITERACOES:
            return


def _dias_da_semana_do_mes(ano, mes, por_dia):
    """BYDAY com ordinal (2TU, -1FR) ou sem (todas as terças) dentro do mês."""
    dias = []
    ultimo = (dt.date(ano + (mes == 12), mes % 12 + 1, 1) - dt.timedelta(days=1)).day
    for ordinal, dia in por_dia:
        do_dia = [d for d in range(1, ultimo + 1) if dt.date(ano, mes, d).weekday() == dia]
        if not ordinal:
            dias += do_dia
        elif 0 < ordinal <= len(do_dia):
            dias.append(do_dia[ordinal - 1])
        elif ordinal < 0 and -ordinal <= len(do_dia):
            dias.append(do_dia[ordinal])
    return dias


def ocorrencias(eventos, de, ate):
    """[(inicio, fim, evento)] que tocam [de, ate), no horário local, em ordem."""
    alteradas = {(e["uid"], e["id_instancia"]) for e in eventos if e["id_instancia"] is not None}
    saida = []
    for e in eventos:
        for naive in _passos_da_regra(e):
            local = naive if e["dia_inteiro"] else _local(naive, e["fuso"])
            if local >= ate:
                break                                   # as ocorrências vêm em ordem: o resto é depois do período
            if naive in e["excecoes"] or (e["uid"], naive) in alteradas:
                continue
            fim = local + e["duracao"]
            if fim > de or (not e["duracao"] and local >= de):
                saida.append((local, fim, e))
    saida.sort(key=lambda x: (x[0], x[2]["titulo"]))
    return saida


def eventos_das_fontes(fontes=None, agora=None):
    """Lê os .ics escolhidos (arquivos ou links). Devolve (eventos, erros). O link tem cache de 15 minutos."""
    eventos, erros = [], []
    for fonte in (fontes if fontes is not None else agendas()):
        try:
            if re.match(r"https?://", fonte, re.I) or fonte.lower().startswith("webcal://"):
                texto = _baixar(fonte.replace("webcal://", "https://", 1))
            else:
                texto = Path(fonte).expanduser().read_text(encoding="utf-8", errors="replace")
            eventos += ler_ics(texto)
        except Exception as e:  # noqa: BLE001  (arquivo sumiu, sem rede: a resposta diz, o resto continua)
            erros.append(f"{type(e).__name__}")
    return eventos, erros


def _baixar(url):
    guardado = _cache_link.get(url)
    if guardado and time.monotonic() - guardado[0] < CACHE_LINK_S:
        return guardado[1]
    import requests
    r = requests.get(url, timeout=10, headers={"User-Agent": "openTARS"})
    r.raise_for_status()
    _cache_link[url] = (time.monotonic(), r.text)
    return r.text


# ---------------------------------------------------------------- agenda: entender a frase
_AGENDA = re.compile(r"\b(agenda|compromiss\w*|calendar\w*|calendario|meetings?|events?|eventos?|reuni\w+|schedule)\b")
_TEMPO = re.compile(r"\b(hoje|today|amanha|tomorrow|depois de amanha|day after tomorrow|esta semana|essa semana|nesta semana|this week|"
                    r"semana que vem|proxima semana|next week|segunda|terca|quarta|quinta|sexta|sabado|domingo|monday|tuesday|wednesday|"
                    r"thursday|friday|saturday|sunday)\b")
_PROXIMO = re.compile(r"\b(proximo|proxima|next|upcoming)\b.*\b(compromisso|evento|reuniao|meeting|event|appointment)\b|"
                      r"\b(compromisso|evento|reuniao|meeting|event|appointment)\b.*\b(proximo|proxima|next)\b")
_NOMES_DIA = {"segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5, "domingo": 6,
              "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}


def _intervalo(n, hoje):
    """(início, fim, nome do período em pt/en) para a frase normalizada, ou None."""
    dia = dt.datetime.combine(hoje, dt.time())
    if re.search(r"\b(depois de amanha|day after tomorrow)\b", n):
        return dia + dt.timedelta(days=2), dia + dt.timedelta(days=3), "depois"
    if re.search(r"\b(amanha|tomorrow)\b", n):
        return dia + dt.timedelta(days=1), dia + dt.timedelta(days=2), "amanha"
    if re.search(r"\b(semana que vem|proxima semana|next week)\b", n):
        segunda = dia + dt.timedelta(days=7 - hoje.weekday())
        return segunda, segunda + dt.timedelta(days=7), "semana_que_vem"
    if re.search(r"\b(esta semana|essa semana|nesta semana|this week)\b", n):
        return dia, dia + dt.timedelta(days=7 - hoje.weekday()), "semana"
    if re.search(r"\b(hoje|today)\b", n):
        return dia, dia + dt.timedelta(days=1), "hoje"
    for nome, numero in _NOMES_DIA.items():
        if re.search(rf"\b{nome}\b", n):
            alvo = dia + dt.timedelta(days=(numero - hoje.weekday()) % 7)
            return alvo, alvo + dt.timedelta(days=1), ("dia", numero)
    return None


def _periodo_texto(periodo, idioma, inicio):
    if isinstance(periodo, tuple):
        nome = TEXTOS["pt" if idioma == "pt" else "en"]["dias"][periodo[1]]
        return (f"{'na' if periodo[1] < 5 else 'no'} {nome}" if idioma == "pt" else f"on {nome}") + f" ({inicio:%d/%m})"
    return _t(periodo, idioma)


def _hora(local, fim, inteiro, idioma):
    if inteiro:
        return _t("dia_inteiro", idioma)
    return f"{local:%H:%M}" + (f"–{fim:%H:%M}" if fim != local and fim.date() == local.date() else "")


def responder_agenda(pedido, idioma, agora=None, fontes=None):
    """O texto da resposta sobre a agenda, ou None quando a frase não é sobre a agenda (ou a agenda está desligada)."""
    fontes = agendas() if fontes is None else fontes
    n = normalizar(pedido)
    if not fontes:
        return None
    proximo = bool(_PROXIMO.search(n))
    intervalo = None if proximo else _intervalo(n, (agora or dt.datetime.now()).date())
    pede = proximo or (intervalo is not None and bool(_AGENDA.search(n) or re.search(r"\b(tenho|do i have|have i|i have|what do i)\b", n)))
    if not pede:
        return None
    eventos, erros = eventos_das_fontes(fontes)
    if erros and not eventos:
        return _t("erro", idioma, erro=erros[0])
    agora = agora or dt.datetime.now()
    if proximo:
        for inicio, fim, e in ocorrencias(eventos, agora, agora + dt.timedelta(days=60)):
            quando = f"{inicio:%d/%m} {_hora(inicio, fim, e['dia_inteiro'], idioma)}"
            return _t("proximo", idioma, quando=quando, titulo=e["titulo"], local=f" ({e['local']})" if e["local"] else "")
        return _t("sem_proximo", idioma)
    de, ate, periodo = intervalo
    achados = ocorrencias(eventos, de, ate)
    nome = _periodo_texto(periodo, idioma, de)
    if not achados:
        return _t("nada", idioma, quando=nome)
    cabeca = _t("um" if len(achados) == 1 else "varios", idioma, Quando=_cap(nome), n=len(achados))
    linhas = [cabeca]
    multi_dia = (ate - de).days > 1
    for inicio, fim, e in achados[:LIMITE_LISTA]:
        dia = f"{TEXTOS['pt' if idioma == 'pt' else 'en']['dias'][inicio.weekday()][:3]} {inicio:%d/%m} " if multi_dia else ""
        linhas.append(f"• {dia}{_hora(inicio, fim, e['dia_inteiro'], idioma)}  {e['titulo']}" + (f" ({e['local']})" if e["local"] else ""))
    if len(achados) > LIMITE_LISTA:
        linhas.append(_t("mais", idioma, n=len(achados) - LIMITE_LISTA))
    return "\n".join(linhas)


def _cap(s):
    return s[:1].upper() + s[1:]


# ---------------------------------------------------------------- notas em Markdown
_CRIAR_NOTA = re.compile(r"^\s*(?:por favor,?\s+|please,?\s+)?(?:cri[ae]r?|fa[zç]a?|salv[ae]|escrev[ae]r?|anot[ae]r?|nova|create|make|take|new|add|save|write)\s+"
                         r"(?:(?:uma|a|an)\s+)?(?:(?:nova|new)\s+)?n[oó]ta\b\s*(?:sobre|de|com|dizendo|que|about|saying|that|:|-)?\s*:?\s*(?P<corpo>.*)$",
                         re.IGNORECASE | re.DOTALL)
_CRIAR_NOTA_EN = re.compile(r"^\s*(?:please,?\s+)?(?:create|make|take|new|add|save|write)\s+(?:(?:a|an)\s+)?(?:(?:new)\s+)?note\b\s*(?:about|saying|that|:|-)?\s*:?\s*(?P<corpo>.*)$",
                            re.IGNORECASE | re.DOTALL)
_ACHAR_NOTA = re.compile(r"\b(?:minhas\s+)?notas?\s+(?:sobre|de|com|about|on|for)\s+(?P<termo>.+)$|"
                         r"\b(?:procura|busca|ache|acha|procure|busque|search|find|look)\w*\s+(?:nas?\s+)?(?:minhas\s+)?(?:notas|my notes|in my notes|notes)\s+(?P<termo2>.+)$", re.IGNORECASE)
_LER_NOTA = re.compile(r"^\s*(?:abre|abra|mostra|mostre|le|ler|leia|show|open|read)\s+(?:a\s+|the\s+|minha\s+|my\s+)*(?:nota|note)\s+(?P<termo>.+?)\s*$", re.IGNORECASE)


def _nome_de_arquivo(texto):
    base = normalizar(texto.strip().splitlines()[0] if texto.strip() else "nota")
    slug = "-".join(re.findall(r"[a-z0-9]+", base)[:7]) or "nota"
    return slug[:60]


def criar_nota(corpo, pasta=None, agora=None):
    """Grava uma nota nova e devolve o caminho. Nunca escreve por cima: se o nome existe, ganha -2, -3..."""
    pasta = Path(pasta or pasta_de_notas())
    pasta.mkdir(parents=True, exist_ok=True)
    corpo = corpo.strip()
    titulo = corpo.splitlines()[0][:80]
    base = f"{(agora or dt.datetime.now()):%Y-%m-%d}-{_nome_de_arquivo(corpo)}"
    destino, k = pasta / f"{base}.md", 2
    while destino.exists():
        destino = pasta / f"{base}-{k}.md"
        k += 1
    resto = "\n".join(corpo.splitlines()[1:]).strip()
    destino.write_text(f"# {titulo}\n\n" + (resto + "\n" if resto else ""), encoding="utf-8")
    return destino


def achar_notas(termo, pasta=None, limite=5):
    import tars_busca_arquivos as busca
    pasta = Path(pasta or pasta_de_notas())
    if not pasta.is_dir():
        return []
    achados = busca.buscar(termo, raiz=pasta, limite=limite * 2, indice=False)
    return [a for a in achados if a["nome"].lower().endswith((".md", ".txt"))][:limite]


def responder_notas(pedido, idioma, pasta=None):
    """Cria, procura ou lê notas. None quando a frase não é de nota, ou as notas estão desligadas (sem pasta)."""
    pasta = pasta or pasta_de_notas()
    if pasta is None:
        return None
    m = _CRIAR_NOTA.match(pedido) or _CRIAR_NOTA_EN.match(pedido)
    if m:
        corpo = (m.group("corpo") or "").strip()
        if not corpo:
            return _t("nota_vazia", idioma)
        destino = criar_nota(corpo, pasta)
        return _t("nota_criada", idioma, nome=destino.name, pasta=str(destino.parent).replace(str(Path.home()), "~", 1))
    m = _LER_NOTA.match(pedido)
    if m:
        termo = m.group("termo").strip(" ?.!")
        achados = achar_notas(termo, pasta, 1)
        if not achados:
            return _t("nota_nao_achei", idioma, termo=termo)
        texto = Path(achados[0]["caminho"]).read_text(encoding="utf-8", errors="replace").strip()
        return _t("nota_texto", idioma, nome=achados[0]["nome"], texto=texto[:900] + ("…" if len(texto) > 900 else ""))
    m = _ACHAR_NOTA.search(pedido)
    if m:
        termo = (m.group("termo") or m.group("termo2") or "").strip(" ?.!")
        if not termo:
            return None
        achados = achar_notas(termo, pasta)
        if not achados:
            return _t("notas_nada", idioma, termo=termo)
        linhas = [_t("notas_achei", idioma, n=len(achados))]
        for a in achados:
            linhas.append(f"• {a['nome']}" + (f": {a['trecho']}" if a["trecho"] else ""))
        return "\n".join(linhas)
    return None


def responder(pedido, idioma):
    """Agenda e notas por código; None se a frase não é com elas (ou as duas estão desligadas, o padrão)."""
    return responder_notas(pedido, idioma) or responder_agenda(pedido, idioma)
