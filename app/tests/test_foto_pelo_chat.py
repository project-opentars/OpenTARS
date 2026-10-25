"""5.2 (25/10): editar foto pelo chat, pelo código (sem o modelo): foto anexada ou citada + uma frase que o tars_fotos entende
vira uma cópia ao lado da original e a resposta mostra a imagem. Sem foto ou sem frase de edição, segue para o modelo."""
import os
import tempfile
from pathlib import Path

from _util import carregar_tars

tars = carregar_tars()
from PIL import Image  # noqa: E402

pasta = Path(tempfile.mkdtemp(prefix="opentars-chat-foto-"))
foto = pasta / "IMG_9.jpg"
Image.new("RGB", (400, 300), (40, 90, 160)).save(foto)
antes = foto.read_bytes()
anexos, _ = tars.anexos_lib.carregar_varios([str(foto)])
eventos = []
tars.emitir = lambda tipo, **d: eventos.append((tipo, d))
resposta = tars._editar_foto_pelo_chat("deixa quadrada e mais clara", anexos)
copia = pasta / ("IMG_9-" + tars.t("foto.sufixo") + ".jpg")
assert copia.exists() and Image.open(copia).size == (300, 300) and foto.read_bytes() == antes, resposta
assert f"]({copia})" in resposta and ("resposta", {"texto": resposta, "inicio": True, "apos_pensamento": False}) in eventos
assert tars.conversa[-1] == {"role": "assistant", "content": resposta}
print("OK: foto anexada + frase vira cópia ao lado da original, a resposta mostra a imagem e fica na conversa")

assert tars._editar_foto_pelo_chat("o que tem nessa foto?", anexos) is None, "sem frase de edição: vai para o modelo (visão)"
assert tars._editar_foto_pelo_chat("deixa quadrada", None) is None, "sem foto: vai para o modelo"
print("OK: sem frase de edição ou sem foto, o pedido segue para o modelo")
print("test_foto_pelo_chat: TUDO OK.")
