"""5.2 (25/10): os modelinhos de foto. O download confere o SHA-256 (arquivo trocado é apagado, nada fica pela metade); com
os modelos de verdade no disco (TARS_MODELINHOS_REAIS=pasta), roda os quatro numa foto desenhada aqui."""
import hashlib
import io
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import RAIZ  # noqa: E402,F401
os.environ.pop("TARS_SEM_MODELINHOS", None)

reais = os.environ.get("TARS_MODELINHOS_REAIS")
os.environ["TARS_PASTA_MODELINHOS"] = reais or tempfile.mkdtemp(prefix="opentars-modelinhos-")
import tars_modelinhos as mm  # noqa: E402


class _Resposta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


if not reais:
    assert set(mm.faltando()) == set(mm.CATALOGO)
    conteudo = b"x" * 1000
    original = dict(mm.CATALOGO)
    mm.CATALOGO["aumentar"] = ("teste.onnx", "https://exemplo/teste.onnx", hashlib.sha256(conteudo).hexdigest(), 1000, "MIT")
    vistos = []
    ok, erro = mm.baixar("aumentar", ao_progredir=lambda f, t: vistos.append((f, t)), abrir=lambda *a, **k: _Resposta(conteudo))
    assert ok and mm.caminho("aumentar").read_bytes() == conteudo and vistos[-1] == (1000, 1000), (ok, erro)
    assert "aumentar" not in mm.faltando()
    mm.caminho("aumentar").unlink()
    ok, erro = mm.baixar("aumentar", abrir=lambda *a, **k: _Resposta(b"y" * 1000))
    assert not ok and "SHA-256" in erro and not mm.caminho("aumentar").exists()
    assert not list(mm.pasta().glob("*.part")), "nada fica pela metade"
    ok, erro = mm.baixar("aumentar", cancelado=lambda: True, abrir=lambda *a, **k: _Resposta(conteudo))
    assert not ok and erro == "cancelado" and not list(mm.pasta().glob("*.part"))
    mm.CATALOGO.clear()
    mm.CATALOGO.update(original)
    for nome, (arquivo, url, sha, tam, licenca) in mm.CATALOGO.items():
        assert "/resolve/" in url and len(url.split("/resolve/")[1].split("/")[0]) == 40, "commit fixo no endereço"
        assert len(sha) == 64 and tam > 0 and licenca in ("MIT", "BSD-3-Clause"), nome
    print("OK: o download confere o SHA-256, apaga o que não confere, cancela sem sobra; endereços com commit fixo")
else:
    from PIL import Image, ImageDraw
    assert not mm.faltando(), mm.faltando()
    foto = Image.new("RGB", (640, 480), (120, 170, 220))
    d = ImageDraw.Draw(foto)
    d.rectangle([0, 320, 640, 480], fill=(90, 140, 70))
    d.ellipse([260, 140, 380, 260], fill=(220, 40, 40))
    sem = mm.tirar_fundo(foto)
    assert sem.mode == "RGBA" and sem.size == foto.size
    m = mm.selecionar(foto, (320, 200))
    area = sum(1 for v in m.getdata() if v)
    assert 0.8 * 3.1416 * 60 * 60 < area < 1.3 * 3.1416 * 60 * 60, area
    limpa = mm.remover(foto, m)
    r, g, b = limpa.getpixel((320, 200))
    assert not (r > 180 and g < 90), (r, g, b)          # o círculo vermelho saiu
    grande = mm.aumentar(foto.crop((0, 0, 200, 150)))
    assert grande.size == (800, 600), grande.size
    print("OK: os quatro modelinhos de verdade: fundo, selecionar por clique, remover o objeto e aumentar 4x")
    import tars_fotos as fotos
    assert fotos.entender("tira o fundo dessa foto") == [("sem_fundo",)]
    assert fotos.entender("remove the background and make it square") == [("sem_fundo",), ("quadrado",)]
    assert fotos.entender("aumenta a resolução") == [("aumentar",)]
    pasta = Path(tempfile.mkdtemp())
    foto.save(pasta / "IMG_1.jpg")
    copia = fotos.salvar_copia(pasta / "IMG_1.jpg", [("sem_fundo",), ("remover", 320, 200)], "edited")
    assert copia.name == "IMG_1-edited.png", copia
    resultado = Image.open(copia)
    assert resultado.mode == "RGBA" and resultado.size == (640, 480)
    antes, depois, t_antes, t_depois = fotos.previa(pasta / "IMG_1.jpg", [("aumentar",), ("remover", 320, 200)])
    assert t_antes == (640, 480) and t_depois == (2560, 1920), t_depois
    print("OK: a frase vira as operações dos modelinhos; a cópia sem fundo sai em PNG; a prévia calcula o tamanho 4x")
print("test_modelinhos: TUDO OK.")
