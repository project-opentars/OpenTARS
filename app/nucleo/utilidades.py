# openTARS — nucleo/utilidades.py
# Aviso de versão nova e o filtro de ferramentas quando não há interface gráfica.
# - aviso_versao_nova(): uma vez por dia confere no GitHub se saiu openTARS
#   novo (tars_atualizacao.py); a janela e o diagnóstico mostram.
# - ferramentas_do_pedido(): sem tela (servidor, SSH, WSL sem WSLg), não oferece
#   o que só funciona com ela.
# (4.6: a área de transferência e a lixeira/desfazer saíram daqui.)
#
# Parte do núcleo: o tars.py executa este arquivo DENTRO do próprio
# namespace (ver _carregar_nucleo). Vem depois de "memoria".
# flake8: noqa

_ferramentas_do_pedido_base = ferramentas_do_pedido


def ferramentas_do_pedido(tarefa, texto):
    base = _ferramentas_do_pedido_base(tarefa, texto)
    if SEM_INTERFACE:  # 4.5: sem tela, não oferece o que só funciona com ela
        base = [f for f in base if f["function"]["name"] not in FERRAMENTAS_SO_COM_TELA]
    return base


def aviso_versao_nova(buscar=None):
    """Texto do aviso, se saiu openTARS mais novo que este; senão None."""
    try:
        nova = atualizacao.versao_nova(REVISAO, buscar=buscar)
    except Exception:
        return None
    if not nova:
        return None
    nome = f"{nova.get('versao', '')} {nova.get('codinome', '')}".strip()
    return t("versao.nova", versao=nome)
