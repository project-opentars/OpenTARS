"""python3 -m tars_qt [--primeiro-uso]

Abre o assistente de primeiro uso (se ainda não foi feito, ou com
--primeiro-uso pra forçar) e, ao terminar, abre o openTARS.
"""

import os
import time
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


def abrir_principal(argv=None):
    """Abre a janela principal (ou a barra rápida, com --rapido) em Qt. Sem PySide6 (ou com --tk), cai na 4.6 em Tkinter."""
    argv = list(sys.argv if argv is None else argv)
    if "--tk" not in argv:
        try:
            from tars_qt.primeiro_uso import criar_aplicativo
            from tars_qt.principal import JanelaPrincipal
        except ImportError:
            JanelaPrincipal = None
        if JanelaPrincipal is not None:
            return _rodar_principal(argv, criar_aplicativo, JanelaPrincipal)
    import tars_plataforma
    comando = tars_plataforma.lancador("opentars-gui")
    extra = [a for a in argv if a in ("--rapido", "--quick")]
    argumentos = [comando, "--tk"] + extra if comando else [sys.executable, str(RAIZ / "tars_gui.py"), "--tk"] + extra
    subprocess.Popen(argumentos, start_new_session=True)
    return 0


_LOG_ABERTO = []


def _ligar_diagnostico():
    """Se a janela cair, o motivo fica em ~/.tars_log/qt.log (erro do Python ou queda do Qt, com a pilha).
    Chamado já no começo de main(), pra pegar também uma queda na importação do Qt."""
    if _LOG_ABERTO:
        return _LOG_ABERTO[0]
    import faulthandler
    import traceback
    try:
        pasta = Path(os.environ.get("TARS_DIR_LOG", str(Path.home() / ".tars_log")))
        pasta.mkdir(parents=True, exist_ok=True)
        arquivo = open(pasta / "qt.log", "a", encoding="utf-8", buffering=1)
        arquivo.write(f"\n--- {__import__('time').strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        faulthandler.enable(arquivo, all_threads=True)
        try:        # os avisos do próprio Qt ("Timers cannot be started from another thread" etc.) iam pro terminal e se perdiam
            from PySide6.QtCore import qInstallMessageHandler

            def mensagem_qt(tipo, contexto, mensagem):
                arquivo.write(f"[Qt {getattr(tipo, 'name', tipo)}] {mensagem}\n")
                if sys.__stderr__ and ("Warning" not in str(getattr(tipo, "name", tipo)) or "thread" in mensagem.lower()):
                    sys.__stderr__.write(f"[Qt] {mensagem}\n")
            qInstallMessageHandler(mensagem_qt)
        except Exception:
            pass

        def gancho(tipo, valor, tb):
            arquivo.write("".join(traceback.format_exception(tipo, valor, tb)))
            sys.__excepthook__(tipo, valor, tb)

        sys.excepthook = gancho
        import threading
        threading.excepthook = lambda a: gancho(a.exc_type, a.exc_value, a.exc_traceback)
        _LOG_ABERTO.append(arquivo)
        return arquivo
    except OSError:
        return None


def _rodar_principal(argv, criar_aplicativo, JanelaPrincipal):
    _log_qt = _ligar_diagnostico()  # noqa: F841  (fica aberto enquanto o programa roda)
    import tars_instancia
    comando = "rapido" if any(a in ("--rapido", "--quick") for a in argv) else \
        "acoes" if any(a in ("--acoes", "--actions") for a in argv) else \
        "residente" if "--residente" in argv else "mostrar"
    id_inicio = os.environ.pop("DESKTOP_STARTUP_ID", None)
    servidor = tars_instancia.Servidor()
    if not servidor.travar():
        # já existe uma instância; ela pode ainda estar carregando e não ter aberto o socket: espera um pouco
        # em vez de seguir (dois processos brigando pelo mesmo socket e pelas mesmas conversas)
        for _ in range(16):
            if tars_instancia.enviar(comando, id_inicio):
                return 0
            time.sleep(0.5)
        return 0
    import tars as nucleo
    from . import fio
    app = criar_aplicativo(argv)
    app.setQuitOnLastWindowClosed(False)    # barra rápida e bandeja: quem encerra é a janela (closeEvent)
    atual = {"janela": None}
    primeira = [True]
    servidor.escutar(lambda cmd, _id: atual["janela"] and fio.emitir(atual["janela"].pedido_externo, cmd))
    try:
        while True:
            janela = JanelaPrincipal(nucleo)
            atual["janela"] = janela
            if comando in ("rapido", "acoes", "residente") and primeira[0]:
                janela.trazer_para_frente(comando)
            else:
                janela.show()
            primeira[0] = False
            app.exec()
            if not getattr(janela, "reconstruir", False):
                return 0
    finally:
        servidor.fechar()


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    _ligar_diagnostico()
    import tars_primeiro_uso as pu

    forcar = "--primeiro-uso" in argv
    if (pu.primeiro_uso_concluido() or os.environ.get("TARS_SEM_ASSISTENTE") == "1") and not forcar:
        return abrir_principal(argv)

    try:
        from tars_qt.primeiro_uso import JanelaPrimeiroUso, criar_aplicativo
    except ImportError:   # sem PySide6: a 4.6 (Tkinter) segue funcionando
        return abrir_principal(argv + ["--tk"])

    app = criar_aplicativo(argv)
    janela = JanelaPrimeiroUso()
    janela.show()
    app.exec()
    if janela.terminou and "--sem-principal" not in argv and not os.environ.get("TARS_SEM_PRINCIPAL"):
        return abrir_principal(argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
