"""Travas contra defeitos que já aconteceram (16/10), para pegar antes de publicar:
  * pt_BR e en com as mesmas chaves, os mesmos tipos e os mesmos {campos} (campo diferente derruba o format);
  * toda chave t("...") escrita no código existe nos dois idiomas (chave faltando aparece crua na tela), e também as
    famílias montadas com f-string (probes.r.sis_{condição} etc.);
  * nenhum texto dos idiomas nem literal das telas Qt usa glifo fora da IBM Plex (o "●" derrubou a janela nos Probes);
  * todo .py do app compila."""
import json
import py_compile
import re
import sys
import tempfile
from pathlib import Path

from _util import RAIZ

RAIZ = Path(RAIZ)
pt = json.loads((RAIZ / "idiomas" / "pt_BR.json").read_text(encoding="utf-8"))
en = json.loads((RAIZ / "idiomas" / "en.json").read_text(encoding="utf-8"))
campos = lambda v: sorted(re.findall(r"\{(\w+)", v)) if isinstance(v, str) else None  # noqa: E731

assert set(pt) == set(en), f"chaves só num idioma: {sorted(set(pt) ^ set(en))}"
assert not [k for k in pt if type(pt[k]) is not type(en[k])], "tipos diferentes entre idiomas"
diferentes = [k for k in pt if campos(pt[k]) != campos(en[k])]
assert not diferentes, f"{{campos}} diferentes entre pt_BR e en: {diferentes}"
print(f"OK: pt_BR e en com as mesmas {len(pt)} chaves, tipos e campos")

fontes_py = [p for p in RAIZ.rglob("*.py") if not set(p.relative_to(RAIZ).parts[:1]) & {"build", "dist", "tests", "gargantua"}]
usadas = {}
for p in fontes_py:
    for m in re.finditer(r"""\bt\(\s*["']([\w.]+)["']""", p.read_text(encoding="utf-8")):
        usadas.setdefault(m.group(1), p.name)
faltam = {k: arq for k, arq in usadas.items() if k not in pt}
assert not faltam, f"chaves usadas no código que não existem nos idiomas: {faltam}"
sys.path.insert(0, str(RAIZ))
import tars_modos  # noqa: E402
import tars_probes as tp  # noqa: E402
familias = ([f"probes.tipo.{x}" for x in ("pasta", "web", "feed", "sistema", "programa", "git", "palavras")]
            + [f"probes.tipo.{x}_ex" for x in ("pasta", "web", "feed", "sistema", "programa", "git", "palavras")]
            + [f"acoes.{g}.{x}" for g, xs in (("aba", ("reescrever", "resumir", "traduzir", "perguntar")),
                                               ("resultado", ("reescrever", "resumir", "traduzir", "perguntar")),
                                               ("opcao", ("corrigir", "formal", "informal", "para_en", "para_pt"))) for x in xs]
            + [f"acoes.atalho_{s}" for s in ("linux", "windows", "macos")]
            + [f"probes.r.sis_{c}" for c in tp.CONDICOES_DO_SISTEMA] + [f"probes.pp.q_sis_{c}" for c in tp.CONDICOES_DO_SISTEMA]
            + [f"probes.pp.n_sis_{c}" for c in tp.CONDICOES_DO_SISTEMA] + [f"probes.f.sis_{c}" for c in tp.CONDICOES_DO_SISTEMA]
            + [f"probes.r.prog_{e}" for e in tp.EVENTOS_DO_PROGRAMA] + [f"probes.pp.q_prog_{e}" for e in tp.EVENTOS_DO_PROGRAMA]
            + [f"probes.f.prog_{e}" for e in tp.EVENTOS_DO_PROGRAMA]
            + [f"probes.erro_{e}" for e in ("json", "ferramentas", "sem_modelo", "sem_resposta", "missao", "limite", "destino")]
            + [f"modo.{m}.{x}" for m in tars_modos.MODOS for x in ("nome", "desc")])
assert not [k for k in familias if k not in pt], f"chaves dinâmicas faltando: {[k for k in familias if k not in pt]}"
print(f"OK: as {len(usadas)} chaves do código e as {len(familias)} dinâmicas existem nos dois idiomas")

try:
    from PySide6.QtGui import QGuiApplication, QRawFont
except ImportError:
    print("(sem PySide6: glifos não conferidos)")
else:
    app = QGuiApplication.instance() or QGuiApplication(["teste", "-platform", "offscreen"])
    plex = [QRawFont(str(f), 15) for f in sorted((RAIZ / "tars_qt" / "fontes").glob("*.ttf"))]
    assert plex, "fontes da IBM Plex não encontradas"
    fora = lambda texto: {c for c in texto if ord(c) > 0x7F and not any(f.supportsCharacter(ord(c)) for f in plex)}  # noqa: E731
    ruins = {f"{k}@{nome}": fora(v) for nome, d in (("pt_BR", pt), ("en", en)) for k, v in d.items()
             if isinstance(v, str) and fora(v)}
    assert not ruins, f"textos com glifo fora da IBM Plex (derruba a janela em algumas máquinas): {ruins}"
    from tars_qt import tema
    trocados = set(tema._TROCAS.keys())       # a tabela de trocas e quem procura esses sinais podem citá-los
    ruins = {}
    for p in list((RAIZ / "tars_qt").glob("*.py")) + [RAIZ / "tars_probes.py", RAIZ / "tars_modos.py"]:
        for n, linha in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if linha.lstrip().startswith("#"):
                continue
            f = {c for c in fora(linha) if ord(c) not in trocados}
            if f:
                ruins[f"{p.name}:{n}"] = f
    assert not ruins, f"literais das telas com glifo fora da IBM Plex: {ruins}"
    print("OK: nenhum texto dos idiomas nem literal das telas usa glifo fora da IBM Plex")

with tempfile.TemporaryDirectory() as pasta:
    for p in fontes_py:
        py_compile.compile(str(p), cfile=str(Path(pasta) / "x.pyc"), doraise=True)
print(f"OK: os {len(fontes_py)} arquivos .py do app compilam")
print("\nTUDO OK.")
