"""5.2 (decisão do Enzo, 25/10): os modelinhos de foto, todos baixados obrigatoriamente e rodando na CPU (ONNX Runtime):
tirar o fundo (BiRefNet lite), aumentar a resolução (Real-ESRGAN general x4v3), selecionar por clique (MobileSAM) e
remover um objeto (MI-GAN, com a máscara do selecionar). Cada arquivo tem endereço com o commit fixo e o SHA-256
conferido; o que não confere é apagado. Sem Qt.

Medido em 25/10 no PC do Enzo (16 threads, só CPU): tirar o fundo ~9 s por foto (3 s de carga na primeira), selecionar
~0,5 s, remover ~1 s, aumentar ~0,5 s a cada pedaço de 256 px."""
import hashlib
import os
import threading
import urllib.request
from pathlib import Path

import tars_plataforma as plataforma

_HF = "https://huggingface.co/"
# nome: (arquivo, endereço com o commit fixo, SHA-256, bytes, licença)
CATALOGO = {
    "fundo": ("birefnet_lite.onnx",
              _HF + "onnx-community/BiRefNet_lite-ONNX/resolve/de15b22ba131738a16dff04aab8bdf8dc32e3ac1/onnx/model.onnx",
              "5600024376f572a557870a5eb0afb1e5961636bef4e1e22132025467d0f03333", 224005088, "MIT"),
    "aumentar": ("realesr_general_x4v3.onnx",
                 _HF + "vlad-grig/realesr-general-x4v3-onnx/resolve/0e95d93e454cf6b5de9bdf5a1c9e7ec340d38231/onnx/model.onnx",
                 "7b10e80021ec3e0ff35017ae5022791879d93a799b2e201e1010a37510202266", 4866420, "BSD-3-Clause"),
    "remover": ("migan_pipeline_v2.onnx",
                _HF + "andraniksargsyan/migan/resolve/406830d0fa60666da0071c342ad2fbc8f30c5c64/migan_pipeline_v2.onnx",
                "6f1f3530a1a2324b19752018ce756088b07973cda8d7d890034ace5c8a48c40b", 28079181, "MIT"),
    "selecionar_codificador": ("mobilesam_encoder.onnx",
                               _HF + "Acly/MobileSAM/resolve/0d3b403339b4674a82493d5e97964dd78089ddc8/mobile_sam_image_encoder.onnx",
                               "580f5fb648ea1062c0aabc26217aed56921985f03f0cbbd852bba81d760cc749", 28157093, "MIT"),
    "selecionar_decodificador": ("mobilesam_decoder.onnx",
                                 _HF + "Acly/MobileSAM/resolve/0d3b403339b4674a82493d5e97964dd78089ddc8/sam_mask_decoder_single.onnx",
                                 "93915fc7c993ab9d59ab8c9ccd3bce37f7509c81ab4150a74abd4d2abbd8570d", 16501323, "MIT"),
}
LADO_MAXIMO_AUMENTADO = 4096        # aumentar nunca passa disso no lado maior (memória e tempo na CPU)


def pasta():
    return Path(os.environ.get("TARS_PASTA_MODELINHOS") or plataforma.pastas()["dados"] / "modelinhos")


def caminho(nome):
    return pasta() / CATALOGO[nome][0]


def faltando():
    """Os modelinhos que ainda não estão no disco (pelo tamanho; o hash foi conferido ao baixar). Os testes do app
    (TARS_SEM_MODELINHOS=1) não baixam ~300 MB da internet."""
    if os.environ.get("TARS_SEM_MODELINHOS") == "1":
        return []
    return [n for n, (_, _, _, tam, _) in CATALOGO.items() if not (caminho(n).is_file() and caminho(n).stat().st_size == tam)]


def bytes_faltando():
    return sum(CATALOGO[n][3] for n in faltando())


def baixar(nome, ao_progredir=None, cancelado=None, abrir=None):
    """Baixa um modelinho para um .part, confere o SHA-256 e só então põe no lugar. (ok, erro)."""
    arquivo, url, sha, tamanho, _ = CATALOGO[nome]
    destino = pasta() / arquivo
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(arquivo + ".part")
    soma, feito = hashlib.sha256(), 0
    try:
        with (abrir or urllib.request.urlopen)(urllib.request.Request(url, headers={"User-Agent": "openTARS"}), timeout=60) as r, \
                open(parcial, "wb") as f:
            while True:
                if cancelado and cancelado():
                    raise InterruptedError("cancelado")
                bloco = r.read(1 << 20)
                if not bloco:
                    break
                f.write(bloco)
                soma.update(bloco)
                feito += len(bloco)
                if ao_progredir:
                    ao_progredir(feito, tamanho)
    except InterruptedError:
        parcial.unlink(missing_ok=True)
        return False, "cancelado"
    except OSError as e:
        parcial.unlink(missing_ok=True)
        return False, str(e)
    if soma.hexdigest() != sha:
        parcial.unlink(missing_ok=True)
        return False, f"SHA-256 diferente em {arquivo}"
    os.replace(parcial, destino)
    return True, ""


def baixar_todos(ao_progredir=None, cancelado=None, abrir=None):
    """Baixa o que falta, um por um. ao_progredir(feito, total) é do conjunto. (ok, erro)."""
    nomes = faltando()
    total, antes = sum(CATALOGO[n][3] for n in nomes), 0
    for n in nomes:
        ok, erro = baixar(n, (lambda f, _t, a=antes: ao_progredir(a + f, total)) if ao_progredir else None, cancelado, abrir)
        if not ok:
            return False, erro
        antes += CATALOGO[n][3]
    return True, ""


# ------------------------------------------------------------
# Os modelos (sessões abertas uma vez e guardadas)
# ------------------------------------------------------------
_SESSOES, _TRAVA = {}, threading.Lock()


def _sessao(nome):
    with _TRAVA:
        if nome not in _SESSOES:
            import onnxruntime
            if not caminho(nome).is_file():
                raise FileNotFoundError(f"modelinho {nome} não baixado")
            _SESSOES[nome] = onnxruntime.InferenceSession(str(caminho(nome)), providers=["CPUExecutionProvider"])
        return _SESSOES[nome]


def tirar_fundo(imagem):
    """A foto (PIL) com o fundo transparente (RGBA)."""
    import numpy as np
    from PIL import Image
    rgb = imagem.convert("RGB")
    x = np.asarray(rgb.resize((1024, 1024), Image.BILINEAR), dtype=np.float32) / 255.0
    x = (x - (0.485, 0.456, 0.406)) / (0.229, 0.224, 0.225)
    saida = _sessao("fundo").run(None, {"input_image": x.transpose(2, 0, 1)[None].astype(np.float32)})[0][0, 0]
    alfa = 1.0 / (1.0 + np.exp(-saida))                       # o modelo devolve logits
    mascara = Image.fromarray((alfa * 255).astype(np.uint8)).resize(rgb.size, Image.BILINEAR)
    resultado = rgb.convert("RGBA")
    resultado.putalpha(mascara)
    return resultado


def aumentar(imagem, pedaco=256, borda=16):
    """A foto com 4x a resolução (menos, se passar de LADO_MAXIMO_AUMENTADO), em pedaços para caber na memória."""
    import numpy as np
    from PIL import Image
    rgb = imagem.convert("RGB")
    w, h = rgb.size
    x = np.asarray(rgb, dtype=np.float32) / 255.0
    saida = np.zeros((h * 4, w * 4, 3), dtype=np.float32)
    sessao = _sessao("aumentar")
    for y0 in range(0, h, pedaco):
        for x0 in range(0, w, pedaco):
            ya, xa = max(0, y0 - borda), max(0, x0 - borda)
            yb, xb = min(h, y0 + pedaco + borda), min(w, x0 + pedaco + borda)
            r = sessao.run(None, {"input": x[ya:yb, xa:xb].transpose(2, 0, 1)[None]})[0][0].transpose(1, 2, 0)
            dy, dx = (y0 - ya) * 4, (x0 - xa) * 4
            ph, pw = min(pedaco, h - y0) * 4, min(pedaco, w - x0) * 4
            saida[y0 * 4:y0 * 4 + ph, x0 * 4:x0 * 4 + pw] = r[dy:dy + ph, dx:dx + pw]
    final = Image.fromarray((np.clip(saida, 0, 1) * 255).round().astype(np.uint8))
    if max(final.size) > LADO_MAXIMO_AUMENTADO:
        final.thumbnail((LADO_MAXIMO_AUMENTADO, LADO_MAXIMO_AUMENTADO), Image.LANCZOS)
    return final


def selecionar(imagem, ponto):
    """A máscara (PIL "L", 255 = o objeto) do que está no ponto (x, y) clicado, na resolução da foto."""
    import numpy as np
    from PIL import Image
    rgb = imagem.convert("RGB")
    w, h = rgb.size
    escala = 1024 / max(w, h)
    reduzida = rgb.resize((max(1, round(w * escala)), max(1, round(h * escala))), Image.BILINEAR)
    emb = _sessao("selecionar_codificador").run(None, {"input_image": np.asarray(reduzida, dtype=np.float32)})[0]
    pontos = np.array([[[ponto[0] * escala, ponto[1] * escala], [0, 0]]], dtype=np.float32)
    rotulos = np.array([[1, -1]], dtype=np.float32)          # o ponto clicado e o "ponto vazio" que o SAM pede
    mascaras = _sessao("selecionar_decodificador").run(None, {
        "image_embeddings": emb, "point_coords": pontos, "point_labels": rotulos,
        "mask_input": np.zeros((1, 1, 256, 256), np.float32), "has_mask_input": np.zeros(1, np.float32),
        "orig_im_size": np.array([h, w], np.float32)})[0]
    return Image.fromarray(((mascaras[0, 0] > 0) * 255).astype(np.uint8))


def remover(imagem, mascara, folga=8):
    """A foto sem o que a máscara marca (255 = tirar), preenchido pelo MI-GAN. A máscara cresce `folga` px (a borda do
    objeto não fica de contorno)."""
    import numpy as np
    from PIL import ImageFilter
    rgb = imagem.convert("RGB")
    m = mascara.convert("L").resize(rgb.size).filter(ImageFilter.MaxFilter(folga * 2 + 1))
    manter = (np.asarray(m) < 128).astype(np.uint8) * 255   # no MI-GAN 255 = manter, 0 = buraco (conferido em 25/10)
    from PIL import Image
    saida = _sessao("remover").run(None, {"image": np.asarray(rgb).transpose(2, 0, 1)[None],
                                          "mask": manter[None, None]})[0][0]
    return Image.fromarray(saida.transpose(1, 2, 0))
