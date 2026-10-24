"""5.2 (F4.8): editar uma foto por frase, só com o Pillow. A frase vira operações (pt e en); o resultado é sempre uma cópia
(a original não muda, nada é sobrescrito); a cópia sai sem EXIF e com a orientação aplicada."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image  # noqa: E402

import tars_fotos as f  # noqa: E402

casos = {
    "corta em quadrado e deixa mais clara": [("quadrado",), ("brilho", 1.2)],
    "deixa 30% mais escura e em preto e branco": [("brilho", 0.7), ("cinza",)],
    "gira pra esquerda": [("girar", -90)],
    "vira de cabeça para baixo": [("girar", 180)],
    "reduz para mandar por e-mail": [("reduzir", f.LADO_EMAIL)],
    "make it square, brighter and black and white": [("quadrado",), ("brilho", 1.2), ("cinza",)],
    "corta em 16:9 e salva em png": [("proporcao", 16, 9), ("formato", "png")],
    "resize to 800 px for whatsapp": [("reduzir", 800)],
    "espelha": [("espelhar",)],
    "bom dia": [],
}
for frase, esperado in casos.items():
    assert f.entender(frase) == esperado, (frase, f.entender(frase))
assert f.descrever(f.entender("corta em quadrado e deixa mais clara")) == "cortar no centro em quadrado e clarear 20%"
assert f.descrever(f.entender("make it square and brighter"), "en") == "crop to a centered square and brighten 20%"
print("OK: a frase vira operações em português e em inglês, e a descrição diz o que foi entendido")

pasta = Path(tempfile.mkdtemp(prefix="opentars-fotos-"))
foto = pasta / "IMG_2041.jpg"
exif = Image.Exif()
exif[0x0112] = 6                                    # o celular gravou "girar 90°" no EXIF
exif[0x010F] = "Celular da Ana"                     # e o aparelho (metadado que não deve ir junto)
Image.new("RGB", (400, 300), (40, 90, 160)).save(foto, exif=exif.tobytes())
antes = foto.read_bytes()

ops = f.entender("corta em quadrado e deixa mais clara")
copia = f.salvar_copia(foto, ops)
assert copia.name == "IMG_2041-editada.jpg" and foto.read_bytes() == antes
with Image.open(copia) as c:
    assert c.size == (300, 300) and not c.getexif(), (c.size, dict(c.getexif()))
    assert sum(c.getpixel((150, 150))) > 40 + 90 + 160
copia2 = f.salvar_copia(foto, f.entender("gira e reduz para 200 px"))
assert copia2.name == "IMG_2041-editada-2.jpg"
with Image.open(copia2) as c:
    assert max(c.size) == 200 and c.size == (200, 150), c.size       # EXIF 6 (retrato) + girar 90° = paisagem
png = f.salvar_copia(foto, f.entender("salva em png"))
assert png.suffix == ".png" and png.exists()
print("OK: sempre uma cópia nova, a original intacta, sem EXIF, orientação aplicada, sem sobrescrever")

a, d, tam_antes, tam_depois = f.previa(foto, ops)
assert a[:8] == d[:8] == b"\x89PNG\r\n\x1a\n" and tam_antes == (300, 400) and tam_depois == (300, 300)
assert f._dimensoes((4032, 3024), f.entender("quadrado e reduz para e-mail")) == (1600, 1600)
assert f.e_foto("x.JPG") and not f.e_foto("x.pdf")
print("OK: a prévia mostra antes e depois e o tamanho final sem processar a foto inteira")
print("test_fotos: TUDO OK.")
