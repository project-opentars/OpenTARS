"""Entrega, na thread da janela, o que as threads de trabalho querem mostrar.

Emitir um sinal do Qt de uma thread comum do Python cria uma cópia do argumento (dict, lista, objeto) FORA da thread
dona do objeto; com algumas versões do PySide6 isso corrompe a memória e o app cai em pontos aleatórios (em `stat`,
em `readinto`...). Aqui as threads só colocam o trabalho numa fila do Python, e um QTimer da thread da janela o executa:
nenhum objeto do Qt é tocado fora da thread dele."""

import queue
import sys
import threading

from PySide6.QtCore import QObject, QTimer

_fila = queue.SimpleQueue()
_relogio = None
_PRINCIPAL = threading.main_thread()


def _drenar():
    for _ in range(500):                     # um lote por tique: a janela não engasga com uma enxurrada
        try:
            funcao, args = _fila.get_nowait()
        except queue.Empty:
            return
        try:
            funcao(*args)
        except RuntimeError:                  # o objeto C++ já foi destruído (janela fechando)
            pass
        except Exception:
            import traceback
            traceback.print_exc(file=sys.__stderr__)


def iniciar(pai=None):
    """Liga o relógio que esvazia a fila. Chamar uma vez, na thread da janela, depois de criar o QApplication."""
    global _relogio
    if _relogio is None:
        _relogio = QTimer(pai if isinstance(pai, QObject) else None)
        _relogio.setInterval(10)
        _relogio.timeout.connect(_drenar)
        _relogio.start()
    return _relogio


def no_principal(funcao, *args):
    """Roda `funcao(*args)` na thread da janela (já, se for ela quem chama)."""
    if threading.current_thread() is _PRINCIPAL and _relogio is not None:
        funcao(*args)
    else:
        _fila.put((funcao, args))


def emitir(sinal, *args):
    """sinal.emit(*args), mas sempre na thread da janela."""
    no_principal(sinal.emit, *args)
