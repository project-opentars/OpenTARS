"""take_screenshot(file=...): a IA "olha" um arquivo de imagem (o Cooper descreve se o modelo não enxerga).
Pasta pessoal temporária (antes gravava na de verdade e, se falhasse, deixava ~/Documentos/Foto.PNG), com Documents E
Documentos, como no PC do Enzo: "Documents/foto.png" tem de achar a foto que está em Documentos."""
import os
import tempfile
os.environ["HOME"] = tempfile.mkdtemp(prefix="opentars-casa-")
from _util import carregar_tars  # noqa: E402
from PIL import Image  # noqa: E402
tars = carregar_tars()

d = tempfile.mkdtemp()
foto = os.path.join(d, "foto.png")
Image.new("RGB", (900, 500), (200, 30, 30)).save(foto)

r = tars.executar_ferramenta("take_screenshot", {"file": foto})
assert r["sucesso"] and r["_imagem_b64"] and r["arquivo"].endswith("foto.png"), r
print("OK: take_screenshot(file) carrega a imagem do arquivo")

r = tars.executar_ferramenta("look_at_image", {"image_path": foto})   # apelidos de nome e de argumento
assert r["sucesso"] and r["_imagem_b64"], r
print("OK: look_at_image(image_path=...) vira take_screenshot(file=...)")

r = tars.executar_ferramenta("take_screenshot", {"file": os.path.join(d, "nao_existe.png")})
assert not r["sucesso"] and "not found" in r["mensagem"].lower()
print("OK: arquivo que não existe dá erro claro")

# caminhos como a IA costuma escrever: relativo, pasta em outro idioma, maiúscula
casa = os.path.expanduser("~")
assert casa == os.environ["HOME"] and "opentars-casa-" in casa
os.makedirs(os.path.join(casa, "Documentos"), exist_ok=True)
os.makedirs(os.path.join(casa, "Documents"), exist_ok=True)       # as duas: o resolvedor tem de voltar atrás
Image.new("RGB", (50, 50), (1, 2, 3)).save(os.path.join(casa, "Documentos", "Foto.PNG"))
for escrito in ("~/Documentos/Foto.PNG", "Documents/foto.png", "home/documentos/foto.png"):
    r = tars.executar_ferramenta("take_screenshot", {"file": escrito})
    assert r["sucesso"], (escrito, r["mensagem"])
print("OK: caminho relativo, pasta em inglês/português e maiúscula também funcionam")
os.remove(os.path.join(casa, "Documentos", "Foto.PNG"))

# modelo sem visão: o Cooper descreve (aqui, falso) e a mensagem diz que é uma foto, não a tela
tars.descrever_com_visao = lambda img, pedido: ("a red rectangle", "cooper:fake")
texto = tars._print_em_texto("x", "o que tem nessa imagem?", "gargantua", None, "/x/foto.png")
assert "a red rectangle" in texto and "don't click" in texto and "foto.png" in texto, texto
print("OK: modelo sem visão recebe a descrição do Cooper da foto")
print("TUDO OK.")
