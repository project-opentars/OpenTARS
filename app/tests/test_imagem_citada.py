"""Pedido que cita uma imagem ("use o cooper para ver home/pictures/01-home.png"): anexa sozinho e o Cooper descreve."""
import os, tempfile
from pathlib import Path
casa = tempfile.mkdtemp()
os.environ["HOME"] = casa
from _util import carregar_tars
from PIL import Image
tars = carregar_tars()
anx = tars.anexos_lib
(Path(casa) / "Imagens").mkdir()
foto = Path(casa) / "Imagens" / "01-home.png"
Image.new("RGB", (300, 200), (10, 120, 200)).save(foto)
(Path(casa) / "Pictures2").mkdir()

for texto in ("use o cooper para ver home/pictures/01-home.png",
              f"olha {foto}", "veja ~/Imagens/01-home.png", "veja 'Imagens/01-HOME.png' por favor",
              'abra "~/Imagens/01-home.png".'):
    achou = anx.achar_imagens_no_texto(texto)
    assert achou and achou[0].resolve() == foto.resolve(), (texto, achou)
print("OK: acha a imagem citada (home/pictures = Imagens, maiúscula, ~, aspas)")
assert anx.achar_imagens_no_texto("veja home/pictures/nao_existe.png") == []
assert anx.achar_imagens_no_texto("sem imagem nenhuma aqui") == []
print("OK: arquivo inexistente ou sem imagem no texto: nada")

lista, erros = anx.carregar_varios([str(foto)])
tars.catalogar_modelos = lambda: {"gargantua": {"capacidades_conhecidas": True, "capacidades": ["tools"]}}
tars.descrever_com_visao = lambda img, pedido: ("a blue rectangle", "cooper:fake")
conteudo, imagens = tars.montar_mensagem_com_anexos("o que tem na imagem?", lista, "gargantua")
assert not imagens and "a blue rectangle" in conteudo, conteudo[-400:]
print("OK: modelo sem visão recebe a descrição do Cooper da imagem anexada")
print("TUDO OK.")
