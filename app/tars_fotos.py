"""5.2 (F4.8, mock-up aprovado em 24/10): editar uma foto por frase ("corta em quadrado e deixa mais clara"), só com o
Pillow, sem modelo de imagem: a frase vira operações por regras (português e inglês), a prévia mostra antes e depois, e o
resultado é **sempre uma cópia** na mesma pasta (a original nunca muda; nada é sobrescrito). A cópia sai sem os metadados
da foto (EXIF: localização, aparelho), com a orientação já aplicada. Sem Qt."""
import io
import re
import unicodedata
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps

EXTENSOES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
LADO_EMAIL = 1600
QUALIDADE = {"normal": 90, "email": 82}
FORMATOS = {"png": ("PNG", ".png"), "jpg": ("JPEG", ".jpg"), "jpeg": ("JPEG", ".jpg"), "webp": ("WEBP", ".webp")}


def e_foto(caminho):
    return Path(caminho).suffix.lower() in EXTENSOES


def _normal(texto):
    return unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()


def _porcentagem(trecho, padrao=20):
    m = re.search(r"(\d{1,3})\s*%", trecho)
    return min(int(m.group(1)), 90) if m else padrao


def entender(frase):
    """A frase vira uma lista de operações, na ordem em que aparecem. Cada uma é uma tupla: ("quadrado",),
    ("proporcao", 16, 9), ("brilho", 1.2), ("contraste", 1.2), ("girar", graus no sentido do relógio), ("espelhar",),
    ("cinza",), ("reduzir", lado), ("formato", "png"). Palavra que não é operação é ignorada."""
    texto = _normal(frase)
    achados = []          # (posição na frase, operação)

    def achar(padrao, operacao):
        m = re.search(padrao, texto)
        if m:
            achados.append((m.start(), operacao(m)))

    achar(r"quadrad|square", lambda m: ("quadrado",))
    achar(r"\b(16|4|3|9)\s*[:x/]\s*(9|3|2|16)\b", lambda m: ("proporcao", int(m.group(1)), int(m.group(2))))
    achar(r"mais clar|clare|ilumin|brighter|lighter|brighten|lighten",
          lambda m: ("brilho", 1 + _porcentagem(texto[max(0, m.start() - 12):m.start() + 40]) / 100))
    achar(r"mais escur|escurec|darker|darken", lambda m: ("brilho", 1 - _porcentagem(texto[max(0, m.start() - 12):m.start() + 40]) / 100))
    achar(r"mais contraste|aumenta o contraste|more contrast|increase contrast", lambda m: ("contraste", 1.25))
    achar(r"menos contraste|less contrast", lambda m: ("contraste", 0.8))
    achar(r"\bgir|rotat|\bvir[ae]\b", lambda m: ("girar", 180 if re.search(r"180|cabeca para baixo|upside", texto) else
                                                  -90 if re.search(r"esquerda|anti.?horario|left|counter", texto) else 90))
    achar(r"espelh|invert[ae] (a foto|a imagem|horizontal)|flip|mirror", lambda m: ("espelhar",))
    achar(r"preto e branco|preto-e-branco|cinza|black and white|black-and-white|grayscale|greyscale|b&w",
          lambda m: ("cinza",))
    achar(r"e-?mail|whats|menor|reduz|diminu|comprim|smaller|shrink|compress|resize for",
          lambda m: ("reduzir", int(n.group(1)) if (n := re.search(r"(\d{3,4})\s*(px|pixels?)\b", texto)) else LADO_EMAIL))
    achar(r"\b(para|pra|em|to|as|into)\s+(png|jpe?g|webp)\b", lambda m: ("formato", m.group(2)))
    vistos, saida = set(), []
    for _pos, op in sorted(achados, key=lambda x: x[0]):
        if op[0] not in vistos:              # "mais clara, mais clara" é uma vez só
            vistos.add(op[0])
            saida.append(op)
    return saida


def descrever(operacoes, idioma="pt_BR"):
    """'cortar no centro em quadrado e clarear 20%' (ou em inglês), para a pessoa conferir o que foi entendido."""
    pt = idioma.startswith("pt")
    partes = []
    for op in operacoes:
        nome = op[0]
        if nome == "quadrado":
            partes.append("cortar no centro em quadrado" if pt else "crop to a centered square")
        elif nome == "proporcao":
            partes.append(f"cortar no centro em {op[1]}:{op[2]}" if pt else f"crop to a centered {op[1]}:{op[2]}")
        elif nome == "brilho":
            p = round(abs(op[1] - 1) * 100)
            partes.append((f"clarear {p}%" if op[1] > 1 else f"escurecer {p}%") if pt else
                          (f"brighten {p}%" if op[1] > 1 else f"darken {p}%"))
        elif nome == "contraste":
            partes.append(("mais contraste" if op[1] > 1 else "menos contraste") if pt else
                          ("more contrast" if op[1] > 1 else "less contrast"))
        elif nome == "girar":
            g = {90: "90° no sentido do relógio", -90: "90° no sentido anti-horário", 180: "180°"}[op[1]] if pt else \
                {90: "90° clockwise", -90: "90° counterclockwise", 180: "180°"}[op[1]]
            partes.append(("girar " if pt else "rotate ") + g)
        elif nome == "espelhar":
            partes.append("espelhar" if pt else "mirror")
        elif nome == "cinza":
            partes.append("deixar em preto e branco" if pt else "make it black and white")
        elif nome == "reduzir":
            partes.append(f"reduzir para no máximo {op[1]} px" if pt else f"shrink to at most {op[1]} px")
        elif nome == "formato":
            partes.append(f"salvar como {op[1].upper()}" if pt else f"save as {op[1].upper()}")
    if not partes:
        return ""
    return ", ".join(partes[:-1]) + (" e " if pt else " and ") + partes[-1] if len(partes) > 1 else partes[0]


def _cortar(imagem, a, b):
    """Corte no centro na proporção a:b."""
    w, h = imagem.size
    if w / h > a / b:
        novo_w = round(h * a / b)
        x = (w - novo_w) // 2
        return imagem.crop((x, 0, x + novo_w, h))
    novo_h = round(w * b / a)
    y = (h - novo_h) // 2
    return imagem.crop((0, y, w, y + novo_h))


def aplicar(imagem, operacoes):
    """A imagem com as operações (uma nova; a recebida não muda)."""
    imagem = ImageOps.exif_transpose(imagem)            # a orientação que o celular grava vira pixels de verdade
    for op in operacoes:
        nome = op[0]
        if nome == "quadrado":
            imagem = _cortar(imagem, 1, 1)
        elif nome == "proporcao":
            imagem = _cortar(imagem, op[1], op[2])
        elif nome in ("brilho", "contraste"):
            if imagem.mode not in ("RGB", "RGBA", "L"):
                imagem = imagem.convert("RGBA" if "A" in imagem.getbands() else "RGB")
            imagem = (ImageEnhance.Brightness if nome == "brilho" else ImageEnhance.Contrast)(imagem).enhance(op[1])
        elif nome == "girar":
            imagem = imagem.rotate(-op[1], expand=True)
        elif nome == "espelhar":
            imagem = ImageOps.mirror(imagem)
        elif nome == "cinza":
            imagem = ImageOps.grayscale(imagem)
        elif nome == "reduzir":
            imagem = imagem.copy()
            imagem.thumbnail((op[1], op[1]))
    return imagem


def nome_da_copia(caminho, operacoes, sufixo="editada"):
    """IMG_2041.jpg -> IMG_2041-editada.jpg (ou -editada-2...; "edited" em inglês), com a extensão do formato pedido.
    Nunca um que exista."""
    caminho = Path(caminho)
    formato = next((op[1] for op in operacoes if op[0] == "formato"), None)
    ext = FORMATOS[formato][1] if formato else caminho.suffix
    destino, n = caminho.with_name(f"{caminho.stem}-{sufixo}{ext}"), 2
    while destino.exists():
        destino, n = caminho.with_name(f"{caminho.stem}-{sufixo}-{n}{ext}"), n + 1
    return destino


def salvar_copia(caminho, operacoes, sufixo="editada"):
    """Aplica e salva a cópia ao lado da original. Devolve o caminho da cópia. A original não é tocada."""
    destino = nome_da_copia(caminho, operacoes, sufixo)
    with Image.open(caminho) as original:
        resultado = aplicar(original, operacoes)
    formato = Image.registered_extensions().get(destino.suffix.lower(), "PNG")
    if formato == "JPEG" and resultado.mode not in ("RGB", "L"):
        resultado = resultado.convert("RGB")
    opcoes = {"quality": QUALIDADE["email" if any(op[0] == "reduzir" for op in operacoes) else "normal"],
              "optimize": True} if formato in ("JPEG", "WEBP") else {}
    with open(destino, "xb") as f:                      # "x": se alguém criou o arquivo no meio tempo, não sobrescreve
        resultado.save(f, format=formato, **opcoes)
    return destino


def previa(caminho, operacoes, lado=360):
    """(png do antes, png do depois, (largura, altura) antes, (largura, altura) depois), em bytes, para a tela."""
    with Image.open(caminho) as original:
        tamanho_antes = ImageOps.exif_transpose(original).size
        original.draft("RGB", (lado * 2, lado * 2))     # JPEG grande: carrega já reduzido (rápido)
        reduzida = ImageOps.exif_transpose(original.copy())
    reduzida.thumbnail((lado, lado))
    depois = aplicar(reduzida, [op for op in operacoes if op[0] != "reduzir"])     # na prévia, reduzir não aparece
    return _png(reduzida), _png(depois), tamanho_antes, _dimensoes(tamanho_antes, operacoes)


def _dimensoes(tamanho, operacoes):
    """O tamanho final, calculado sem processar a foto inteira."""
    w, h = tamanho
    for op in operacoes:
        if op[0] in ("quadrado", "proporcao"):
            a, b = (1, 1) if op[0] == "quadrado" else (op[1], op[2])
            w, h = (round(h * a / b), h) if w / h > a / b else (w, round(w * b / a))
        elif op[0] == "girar" and op[1] != 180:
            w, h = h, w
        elif op[0] == "reduzir" and max(w, h) > op[1]:
            f = op[1] / max(w, h)
            w, h = max(1, round(w * f)), max(1, round(h * f))
    return w, h


def _png(imagem):
    saida = io.BytesIO()
    (imagem.convert("RGBA") if imagem.mode not in ("RGB", "RGBA", "L") else imagem).save(saida, format="PNG")
    return saida.getvalue()
