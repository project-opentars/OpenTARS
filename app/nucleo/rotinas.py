# openTARS — nucleo/rotinas.py
# 5.0: rotinas agendadas. As ferramentas schedule_task / list_tasks / delete_task só aparecem quando o pedido fala
# de agendar (e NÃO para o Gargantua, que foi treinado só com as ferramentas de antes). A lógica fica em
# tars_rotinas.py. Uma rotina criada pela IA nasce DESLIGADA e sem aprovação: quem liga é a pessoa, na janela
# (Configurações > Rotinas), vendo o pedido e escolhendo o que ela pode fazer sem perguntar.
# flake8: noqa

agenda = agenda_lib.Agenda()

_ERROS_AGENDA = {
    "nome": "the routine needs a name", "pedido": "the request is empty or longer than 500 characters",
    "limite": f"too many routines (max {agenda_lib.LIMITE_ROTINAS}); delete one first",
    "tipo": "when_type must be daily, weekly, interval or once", "hora": "time must look like 08:30",
    "dias": "weekly needs days (mon..sun)", "intervalo": f"every_minutes must be {agenda_lib.INTERVALO_MINIMO} or more",
    "data": "date must look like 2026-10-31T09:00",
}


def agendar_ferramenta(a):
    tipo = {"daily": "diaria", "weekly": "semanal", "interval": "intervalo", "once": "uma_vez"}.get(
        str(a.get("when_type") or "").strip().lower(), str(a.get("when_type") or "").strip().lower())
    quando = {"tipo": tipo, "hora": a.get("time"), "dias": a.get("days"),
              "cada_minutos": a.get("every_minutes"), "data": a.get("date")}
    if sum(1 for x in agenda.listar() if x.get("origem") == "ia" and not x.get("aprovada")) >= 8:
        return {"sucesso": False, "mensagem": "ERROR: there are already 8 routines waiting for the user's approval; "
                                              "ask the user to review them in Settings > Routines first."}
    r, erro = agenda.criar(a.get("name"), a.get("request"), quando, permitidas=(), ativa=False, aprovada=False, origem="ia")
    if erro:
        return {"sucesso": False, "mensagem": "ERROR: " + _ERROS_AGENDA.get(erro, erro) + "."}
    return {"sucesso": True, "mensagem": (
        f"SUCCESS: saved '{r['nome']}' as PENDING. It is NOT active yet: the user must open "
        "Settings > Routines, review it and approve it. Tell the user that.")}


def listar_agenda_ferramenta(a):
    rotinas = agenda.listar()
    if not rotinas:
        return {"sucesso": True, "mensagem": "No routines yet."}
    linhas = []
    for r in rotinas:
        estado = "active" if r["ativa"] else ("pending approval" if not r["aprovada"] else "off")
        linhas.append(f"- {r['nome']} [{estado}]: {r['pedido'][:80]} ({r['quando']['tipo']})")
    return {"sucesso": True, "mensagem": "\n".join(linhas)}


def apagar_agenda_ferramenta(a):
    chave = " ".join(str(a.get("name") or "").lower().split())
    achadas = [x for x in agenda.listar() if " ".join(str(x.get("nome")).lower().split()) == chave] if chave else []
    if len(achadas) != 1:
        return {"sucesso": False, "mensagem": "No single routine has exactly that name. Use list_tasks."}
    r = achadas[0]
    if r.get("origem") != "ia":
        return {"sucesso": False, "mensagem": f"'{r['nome']}' was created by the user: only the user can delete it "
                                              "(Settings > Routines)."}
    agenda.apagar(r["id"])
    return {"sucesso": True, "mensagem": f"SUCCESS: deleted '{r['nome']}'."}


TOOLS_AGENDA = [
    _ferramenta(
        "schedule_task",
        "Schedules a request that openTARS runs by itself at a set time (every day, some weekdays, every N minutes "
        "or once). It is saved PENDING: the user has to approve it in Settings > Routines. Only when the user asks "
        "to schedule or repeat something.",
        {"name": {"type": "string", "description": "Short name of the routine."},
         "request": {"type": "string", "description": "What to do, as the user would ask it."},
         "when_type": {"type": "string", "enum": ["daily", "weekly", "interval", "once"]},
         "time": {"type": "string", "description": "HH:MM, for daily and weekly."},
         "days": {"type": "array", "items": {"type": "string"}, "description": "For weekly: mon, tue, wed, thu, fri, sat, sun."},
         "every_minutes": {"type": "integer", "description": "For interval (5 or more)."},
         "date": {"type": "string", "description": "For once: 2026-10-31T09:00."}},
        ["name", "request", "when_type"],
    ),
    _ferramenta("list_tasks", "Lists the scheduled routines.", {}),
    _ferramenta("delete_task", "Deletes a scheduled routine by name.", {"name": {"type": "string"}}, ["name"]),
]
_TOOLS_EXTRAS.extend(TOOLS_AGENDA)
_cache_esquemas.clear()
_FERRAMENTAS_AGENDA = {f["function"]["name"] for f in TOOLS_AGENDA}
_FERRAMENTAS_SO_SE_PEDIDAS.update(_FERRAMENTAS_AGENDA)
_DISPATCH_FERRAMENTAS.update({
    "schedule_task": agendar_ferramenta,
    "list_tasks": listar_agenda_ferramenta,
    "delete_task": apagar_agenda_ferramenta,
})
_APELIDOS_FERRAMENTAS.update({
    "create_task": "schedule_task", "schedule": "schedule_task", "add_routine": "schedule_task", "create_routine": "schedule_task",
    "schedule_routine": "schedule_task", "list_routines": "list_tasks", "list_schedule": "list_tasks",
    "remove_task": "delete_task", "delete_routine": "delete_task", "cancel_task": "delete_task",
})

_ferramentas_do_pedido_sem_agenda = ferramentas_do_pedido


def ferramentas_do_pedido(tarefa, texto):
    """As de antes + as da agenda, se o pedido fala de agendar."""
    base = _ferramentas_do_pedido_sem_agenda(tarefa, texto)
    if agenda_lib.fala_de_rotina(texto):
        nomes = {f["function"]["name"] for f in base}
        base = base + [f for f in TOOLS_AGENDA if f["function"]["name"] not in nomes]
    return base
