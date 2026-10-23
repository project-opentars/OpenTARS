"""Backend do macOS. Só o que não depende de teste na máquina; o resto entra na fase F6 do PLANO_5.2.md."""
import subprocess

from . import NaoSuportado


def abrir(alvo):
    subprocess.Popen(["open", str(alvo)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def teclas_de_colar():
    return ("command", "v")


def __getattr__(funcao):
    """O que ainda não existe aqui levanta NaoSuportado com a fase, em vez de falhar em silêncio."""
    if funcao.startswith("__"):
        raise AttributeError(funcao)

    def falta(*_args, **_kwargs):
        raise NaoSuportado(f"{funcao} ainda não existe no macos: entra na fase F6 da 5.2")
    return falta
