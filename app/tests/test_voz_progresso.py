"""26/10: o download da voz tem barra de verdade: o Kokoro é medido em bytes (Content-Length), o resto fica em movimento.
Sem internet: `requests.get` é de mentira."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["TARS_PASTA_KOKORO"] = tempfile.mkdtemp(prefix="opentars-kokoro-")
from _util import RAIZ  # noqa: E402,F401

import requests  # noqa: E402
import tars_voz as voz  # noqa: E402

voz.pasta_kokoro = lambda: Path(os.environ["TARS_PASTA_KOKORO"])
TAMANHOS = {"kokoro-v1.0.onnx": 3_000_000, "voices-v1.0.bin": 1_000_000}


class _Resp:
    def __init__(self, url):
        self.tamanho = TAMANHOS[next(n for n in TAMANHOS if n in url)]
        self.headers = {"Content-Length": str(self.tamanho)}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, bloco):
        for i in range(0, self.tamanho, bloco):
            yield b"x" * min(bloco, self.tamanho - i)


requests.get = lambda url, **k: _Resp(url)
passos = []
ok, erro = voz.baixar_voz("en", lambda m: None, progresso=lambda f, t: passos.append((round(f, 3), t)))
assert ok, erro
fracoes = [f for f, _ in passos]
assert fracoes == sorted(fracoes) and fracoes[-1] > 0.99 and fracoes[0] < 0.1, fracoes[:3]
assert all("MB" in t for _, t in passos)
assert (voz.pasta_kokoro() / "kokoro-v1.0.onnx").stat().st_size == 3_000_000 and not list(voz.pasta_kokoro().glob("*.parte"))
print("OK: o download do Kokoro reporta a fração em bytes, do começo ao fim, sem sobra de arquivo parcial")

passos.clear()
ok, _ = voz.baixar_voz("en", lambda m: None, progresso=lambda f, t: passos.append(f))
assert ok and passos == [], "já baixado: nada a medir"
print("OK: o que já está baixado não baixa de novo")

# a janela: a barra mostra a fração e some no fim
from PySide6.QtWidgets import QApplication  # noqa: E402
from tars_qt import configuracoes as cfgmod  # noqa: E402
app = QApplication.instance() or QApplication([])


class _N:
    def config_voz(self): return {"falar": False}
    def preferencias_voz(self): return {"velocidade": 1.0}
    def voz_atual(self): return "af_heart"
    def o_que_falta_voz(self): return ["voz"]
    def descrever_falta_voz(self, f): return "voz"
    def salvar_config_voz(self, **k): pass

    def instalar_voz(self, avisar=None, progresso=None):
        progresso(None, "pip install faster-whisper")
        progresso(0.5, "kokoro-v1.0.onnx: 160 / 310 MB")
        return True, ""


class _C:
    nucleo = _N()
    def depois(self, f): f()
    def em_segundo_plano(self, trabalho, pronto): pronto(trabalho())


pagina = cfgmod.PVoz(_C())
vistos = []
original = pagina.barra.setValue
pagina.barra.setValue = lambda v: (vistos.append(v), original(v))[1]
pagina._instalar()
assert 50 in vistos and not pagina.barra.isVisibleTo(pagina)
print("OK: a janela mostra a barra do download da voz e a esconde no fim")
print("test_voz_progresso: TUDO OK.")
