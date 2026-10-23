"""Backend do Windows. Só o que não depende de teste na máquina; o resto entra na fase F5 do PLANO_5.2.md."""
import os

from . import NaoSuportado


def abrir(alvo):
    os.startfile(str(alvo))  # noqa: S606  (só existe no Windows)


def teclas_de_colar():
    return ("ctrl", "v")


def __getattr__(funcao):
    """O que ainda não existe aqui levanta NaoSuportado com a fase, em vez de falhar em silêncio."""
    if funcao.startswith("__"):
        raise AttributeError(funcao)

    def falta(*_args, **_kwargs):
        raise NaoSuportado(f"{funcao} ainda não existe no windows: entra na fase F5 da 5.2")
    return falta
