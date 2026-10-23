"""O progresso do download do Gargantua (~2,5 GB, mais que um inteiro de 32 bits) chega na tela.

Antes, o sinal era Signal(float, int, int, object): com o total passando de 2.147.483.647 bytes o Qt estourava, a
atualização se perdia e a barra ficava em 0% enquanto o Ollama já estava em 53%.
Precisa de PySide6 (se não houver, o teste se marca PULADO)."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QCoreApplication
except ImportError:
    print("test_qt_download_grande: PULADO (PySide6 não instalado)")
    sys.exit(0)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tars_qt.primeiro_uso import Sinais  # noqa: E402
import tars_primeiro_uso as pu  # noqa: E402

app = QCoreApplication.instance() or QCoreApplication([])
sinais = Sinais()
recebidos = []
sinais.progresso.connect(lambda *a: recebidos.append(a))

# o caso real: modelo de 2,5 GB, baixado até 53%
total = 2_497_281_056
feito = int(total * 0.53)
sinais.progresso.emit(feito / total, feito, total, 120.0)
assert recebidos, "a atualização de um download grande se perdeu (estouro de 32 bits)"
assert recebidos[-1][1] == feito and recebidos[-1][2] == total, recebidos[-1]
assert 0.52 < recebidos[-1][0] < 0.54
print("OK: o progresso de um download de 2,5 GB chega inteiro na tela (sem estourar 32 bits)")

# o mesmo caminho do download de verdade: Progresso -> sinal, com as camadas somadas
p = pu.Progresso()
p.atualizar({"status": "pulling abc", "digest": "abc", "total": total, "completed": feito})
p.atualizar({"status": "pulling def", "digest": "def", "total": 1723, "completed": 1723})
recebidos.clear()
sinais.progresso.emit(p.fracao, p.feito, p.total, p.segundos_restantes())
assert recebidos and recebidos[-1][2] == total + 1723 and 0.52 < recebidos[-1][0] < 0.54, recebidos
print("OK: camadas somadas passam de 2 GB e chegam")
print("\nTUDO OK.")
