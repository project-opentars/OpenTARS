# openTARS — nucleo/memoria.py
# Memória de preferências (3.0): as ferramentas remember/forget que a IA
# usa. A lógica (arquivo, limites) fica em tars_memoria.py. (Endurance
# Neo: as rotinas agendadas saíram; até a 4.0 isto era nucleo/rotinas.py.)
#
# Parte do núcleo: o tars.py executa este arquivo DENTRO do próprio
# namespace (ver _carregar_nucleo), então tudo aqui é tars.<nome> e as
# partes enxergam umas às outras sem import. Os testes que trocam
# tars.<função> por uma falsa continuam valendo pra todas as partes.
# flake8: noqa

# ============================================================
# MEMÓRIA
# ============================================================

memoria = memoria_lib.Memoria()

# Um pedido por vez (a janela e a barra rápida não atropelam um pedido em andamento).
TRAVA_PEDIDO = threading.RLock()


def lembrar_ferramenta(a):
    ok, erro = memoria.lembrar(a.get("fact") or a.get("text") or "")
    if not ok:
        return {"sucesso": False, "mensagem": f"ERROR: {erro}."}
    return {"sucesso": True, "mensagem": "SUCCESS: saved. It will be in your instructions from now on."}


def esquecer_ferramenta(a):
    fora = memoria.esquecer(a.get("fact") or a.get("text") or "")
    if not fora:
        return {"sucesso": False, "mensagem": "Nothing saved matches that. The saved facts are in your instructions."}
    return {"sucesso": True, "mensagem": "SUCCESS: forgot: " + "; ".join(fora)}


TOOLS_MEMORIA = [
    _ferramenta(
        "remember",
        "Saves a short fact the user wants you to remember in every future conversation (their browser, "
        "folders, names, preferences). Only when the user asks to remember, or states a lasting preference.",
        {"fact": {"type": "string", "description": "The fact, short and in the user's words."}},
        ["fact"],
    ),
    _ferramenta(
        "forget",
        "Forgets saved facts that contain these words ('*' forgets everything).",
        {"fact": {"type": "string"}},
        ["fact"],
    ),
]
TOOLS_ROTINAS = TOOLS_MEMORIA  # nome antigo (o kit do Gargantua ainda procura por ele)
TOOLS.extend(TOOLS_MEMORIA)
_cache_esquemas.clear()
_FERRAMENTAS_MEMORIA = {f["function"]["name"] for f in TOOLS_MEMORIA}
_FERRAMENTAS_SO_SE_PEDIDAS.update(_FERRAMENTAS_MEMORIA)

_DISPATCH_FERRAMENTAS.update({
    "remember": lembrar_ferramenta,
    "forget": esquecer_ferramenta,
})
_APELIDOS_FERRAMENTAS.update({
    "save_memory": "remember", "memorize": "remember", "save_preference": "remember", "remember_fact": "remember",
    "forget_memory": "forget", "delete_memory": "forget",
})
_APELIDOS_ARGUMENTOS.update({
    "fact": ("memory", "text", "content", "preference", "info", "information"),
})


def ferramentas_do_pedido(tarefa, texto):
    """As ferramentas da tarefa + as de memória, se o pedido fala disso
    (sem pesar a lista das tarefas que nada têm a ver)."""
    base = ferramentas_para(tarefa)
    nomes = {f["function"]["name"] for f in base}
    extras = set()
    if memoria_lib.fala_de_memoria(texto):
        extras |= _FERRAMENTAS_MEMORIA
    faltam = [f for f in TOOLS_MEMORIA if f["function"]["name"] in extras - nomes]
    return base + faltam
