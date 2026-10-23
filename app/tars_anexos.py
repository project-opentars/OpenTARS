"""openTARS 4.5 Endurance: arquivos anexados ao pedido.

O usuário anexa arquivos (botão 📎 na janela, /anexar no terminal, ou
arrastando o arquivo pro terminal) e a IA recebe o conteúdo junto com a
pergunta:
  * imagens: vão como imagem pra um modelo que enxerga (ou viram texto,
    descritas por um modelo de visão, se o escolhido não enxerga);
  * texto, código, CSV, JSON, logs...: o conteúdo entra na mensagem
    (cortado se for enorme);
  * PDF (pdftotext ou pypdf), DOCX e ODT: o texto é extraído;
  * pasta: a lista dos arquivos;
  * qualquer outro binário: só o nome, o tamanho e o caminho, pra IA
    poder usar o arquivo com um comando.

Este módulo é puro (só lê o arquivo; não fala com modelo nenhum).
"""

import base64
import io
import os
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse

import tars_ambiente as ambiente

MAX_ANEXOS = 8
LIMITE_TEXTO_CHARS = 20000          # por arquivo
LIMITE_TOTAL_CHARS = 30000          # soma dos anexos de um pedido (o núcleo ajusta ao contexto da IA)
LIMITE_LEITURA_BYTES = 4_000_000    # de um arquivo de texto lê no máximo isso
LIMITE_IMAGEM_BYTES = 30_000_000
LADO_MAXIMO_IMAGEM = 1600
LIMITE_PASTA_ITENS = 100

EXT_IMAGEM = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
EXT_DOCX = {".docx"}
EXT_ODT = {".odt", ".ods", ".odp"}
EXT_BINARIAS = {
    ".zip", ".gz", ".xz", ".bz2", ".7z", ".rar", ".tar", ".deb", ".rpm", ".iso", ".exe", ".bin", ".so", ".o",
    ".mp3", ".wav", ".flac", ".ogg", ".mp4", ".mkv", ".avi", ".mov", ".webm", ".xlsx", ".xls", ".pptx", ".ppt",
    ".gguf", ".safetensors", ".pt", ".pth", ".onnx", ".sqlite", ".db", ".woff", ".woff2", ".ttf", ".otf",
}


class ErroAnexo(Exception):
    """Mensagem já pronta pra mostrar ao usuário."""


@dataclass
class Anexo:
    caminho: str
    nome: str
    tipo: str                      # imagem | texto | pdf | docx | pasta | binario
    bytes: int = 0
    texto: str = ""                # conteúdo extraído (tipo != imagem)
    imagem_b64: str = ""
    largura: int = 0
    altura: int = 0
    truncado: bool = False
    avisos: list = field(default_factory=list)

    def resumo(self):
        if self.tipo == "imagem":
            return f"{self.nome} (image {self.largura}x{self.altura})"
        if self.tipo == "pasta":
            return f"{self.nome}/ (folder)"
        return f"{self.nome} ({tamanho_legivel(self.bytes)})"


def _existe(caminho):
    """Path.exists() levanta PermissionError (Python <= 3.12) se a pasta de cima não pode ser atravessada (/root/x)."""
    try:
        return Path(caminho).exists()
    except OSError:
        return False


def tamanho_legivel(n):
    n = float(n)
    for unidade in ("B", "KB", "MB", "GB"):
        if n < 1024 or unidade == "GB":
            return f"{n:.0f} {unidade}" if unidade == "B" else f"{n:.1f} {unidade}"
        n /= 1024


# ------------------------------------------------------------
# Caminho vindo de um campo, do arrastar-e-soltar ou de um comando
# ------------------------------------------------------------

def normalizar_caminho(entrada, wsl=None):
    """Aceita 'aspas', file:///url%20codificada, ~/x, caminho com espaço
    escapado ('a\\ b', como alguns terminais colam) e, no WSL, C:\\Users\\...
    Devolve um Path (que pode não existir)."""
    t = str(entrada or "").strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
        t = t[1:-1]
    elif "\\ " in t:
        t = t.replace("\\ ", " ")
    if t.lower().startswith("file://"):
        t = unquote(urlparse(t).path)
        if re.match(r"^/[A-Za-z]:/", t):  # file:///C:/x
            t = t[1:]
    wsl = ambiente.e_wsl() if wsl is None else wsl
    if ambiente.parece_caminho_windows(t) and (wsl or not _existe(Path(t))):
        t = ambiente.caminho_do_windows(t)
    return Path(os.path.expanduser(t))


# ------------------------------------------------------------
# Leitura por tipo
# ------------------------------------------------------------

def _e_binario(amostra):
    if b"\x00" in amostra:
        return True
    if not amostra:
        return False
    estranhos = sum(1 for b in amostra if b < 9 or (13 < b < 32))
    return estranhos / len(amostra) > 0.2


def _decodificar(bruto):
    if bruto[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return bruto.decode("utf-16")
        except UnicodeDecodeError:
            pass
    try:
        # incremental: um caractere cortado no fim da leitura parcial (o arquivo passou do limite) não vira erro
        import codecs
        return codecs.getincrementaldecoder("utf-8-sig")().decode(bruto, final=False)
    except UnicodeDecodeError:
        return bruto.decode("latin-1")


def _cortar(texto, limite):
    if len(texto) <= limite:
        return texto, False
    return texto[:limite] + f"\n[... cut: {len(texto) - limite} more characters not shown ...]", True


def _ler_imagem(caminho, anexo):
    from PIL import Image
    if anexo.bytes > LIMITE_IMAGEM_BYTES:
        raise ErroAnexo(f"'{anexo.nome}' is too big for an image ({tamanho_legivel(anexo.bytes)}; the limit is "
                        f"{tamanho_legivel(LIMITE_IMAGEM_BYTES)}).")
    try:
        with Image.open(caminho) as img:
            img.seek(0)
            img.load()
            tem_alfa = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
            if tem_alfa:
                fundo = Image.new("RGB", img.size, (255, 255, 255))
                fundo.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
                img = fundo
            else:
                img = img.convert("RGB")
            if max(img.size) > LADO_MAXIMO_IMAGEM:
                razao = LADO_MAXIMO_IMAGEM / max(img.size)
                img = img.resize((max(1, round(img.width * razao)), max(1, round(img.height * razao))), Image.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format="PNG" if tem_alfa else "JPEG", **({} if tem_alfa else {"quality": 90}))
            anexo.largura, anexo.altura = img.size
    except ErroAnexo:
        raise
    except Exception as e:
        raise ErroAnexo(f"I could not open '{anexo.nome}' as an image ({type(e).__name__}).")
    anexo.imagem_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")


def _texto_do_pdf(caminho):
    if shutil.which("pdftotext"):
        try:
            r = subprocess.run(["pdftotext", "-layout", "-q", str(caminho), "-"], capture_output=True, timeout=60)
            if r.returncode == 0:
                return r.stdout.decode("utf-8", "replace")
        except Exception:
            pass
    try:
        import pypdf
        leitor = pypdf.PdfReader(str(caminho))
        return "\n\n".join((p.extract_text() or "") for p in leitor.pages)
    except ImportError:
        raise ErroAnexo("To read PDFs install poppler-utils (sudo apt install poppler-utils).")
    except Exception as e:
        raise ErroAnexo(f"I could not read the PDF ({type(e).__name__}).")


def _texto_de_xml_zip(caminho, interno, paragrafo):
    try:
        with zipfile.ZipFile(caminho) as z:
            xml = z.read(interno).decode("utf-8", "replace")
    except Exception as e:
        raise ErroAnexo(f"I could not read the document ({type(e).__name__}).")
    xml = re.sub(paragrafo, "\n", xml)
    xml = re.sub(r"<[^>]+>", "", xml)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'")):
        xml = xml.replace(a, b)
    return re.sub(r"\n{3,}", "\n\n", xml).strip()


def _listar_pasta(caminho):
    itens = []
    try:
        for i, p in enumerate(sorted(caminho.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))):
            if i >= LIMITE_PASTA_ITENS:
                itens.append(f"[... more items not shown ...]")
                break
            itens.append(p.name + ("/" if p.is_dir() else ""))
    except OSError as e:
        raise ErroAnexo(f"I could not list the folder ({e.strerror or e}).")
    return "\n".join(itens)


def carregar(entrada, wsl=None):
    """Lê um arquivo ou pasta e devolve um Anexo. ErroAnexo se não der."""
    caminho = normalizar_caminho(entrada, wsl)
    if not str(entrada or "").strip():
        raise ErroAnexo("No file given.")
    if not _existe(caminho):
        raise ErroAnexo(f"'{caminho}' does not exist.")
    try:
        caminho = caminho.resolve()
    except OSError:
        pass
    anexo = Anexo(caminho=str(caminho), nome=caminho.name or str(caminho), tipo="texto")

    if caminho.is_dir():
        anexo.tipo = "pasta"
        anexo.texto = _listar_pasta(caminho)
        return anexo
    if not caminho.is_file():
        raise ErroAnexo(f"'{caminho}' is not a regular file.")
    try:
        anexo.bytes = caminho.stat().st_size
        with open(caminho, "rb") as f:
            amostra = f.read(4096)
    except OSError as e:
        raise ErroAnexo(f"I cannot read '{anexo.nome}' ({e.strerror or e}).")

    ext = caminho.suffix.lower()
    if ext in EXT_IMAGEM:
        anexo.tipo = "imagem"
        _ler_imagem(caminho, anexo)
        return anexo
    if ext == ".pdf" or amostra.startswith(b"%PDF"):
        anexo.tipo = "pdf"
        texto = _texto_do_pdf(caminho).strip()
        if not texto:
            anexo.avisos.append("no text found (scanned PDF?)")
        anexo.texto, anexo.truncado = _cortar(texto, LIMITE_TEXTO_CHARS)
        return anexo
    if ext in EXT_DOCX:
        anexo.tipo = "docx"
        texto = _texto_de_xml_zip(caminho, "word/document.xml", r"</w:p>|<w:br\s*/>")
        anexo.texto, anexo.truncado = _cortar(texto, LIMITE_TEXTO_CHARS)
        return anexo
    if ext in EXT_ODT:
        anexo.tipo = "docx"
        texto = _texto_de_xml_zip(caminho, "content.xml", r"</text:p>|</text:h>|<text:line-break/>")
        anexo.texto, anexo.truncado = _cortar(texto, LIMITE_TEXTO_CHARS)
        return anexo
    utf16 = amostra[:2] in (b"\xff\xfe", b"\xfe\xff")  # texto UTF-16 tem NULs, mas não é binário
    if ext in EXT_BINARIAS or (_e_binario(amostra) and not utf16):
        anexo.tipo = "binario"
        anexo.avisos.append("binary file: the content is not included, use the path with a command if you need it")
        return anexo

    with open(caminho, "rb") as f:
        bruto = f.read(LIMITE_LEITURA_BYTES)
    texto = _decodificar(bruto)
    anexo.texto, anexo.truncado = _cortar(texto, LIMITE_TEXTO_CHARS)
    if anexo.bytes > LIMITE_LEITURA_BYTES:
        anexo.truncado = True
    return anexo


def carregar_varios(entradas, wsl=None, ja_anexados=()):
    """([Anexo], [mensagens de erro]) — um erro não derruba os outros.
    Respeita MAX_ANEXOS contando os que já estavam anexados."""
    prontos, erros = [], []
    ja = {a.caminho for a in ja_anexados}
    for entrada in entradas:
        if len(ja) + len(prontos) >= MAX_ANEXOS:
            erros.append(f"At most {MAX_ANEXOS} attachments per message.")
            break
        try:
            a = carregar(entrada, wsl)
        except ErroAnexo as e:
            erros.append(str(e))
            continue
        if a.caminho in ja or any(a.caminho == p.caminho for p in prontos):
            continue
        prontos.append(a)
    return prontos, erros


# ------------------------------------------------------------
# O que vai pra IA
# ------------------------------------------------------------

def _cabecalho(a):
    extras = f"; {'; '.join(a.avisos)}" if a.avisos else ""
    return f"{a.nome} (path: {a.caminho}, {a.tipo}, {tamanho_legivel(a.bytes) if a.bytes else 'folder'}{extras})"


def montar_bloco(anexos, descricoes=None, limite_total=None):
    """Texto que acompanha a pergunta. 'descricoes': {caminho: texto} das
    imagens quando o modelo não enxerga (descritas por outro modelo)."""
    if not anexos:
        return ""
    descricoes = descricoes or {}
    partes = ["[Files attached by the user to this message. Their content is below; the paths let you use them "
              "with commands if needed.]"]
    restante = limite_total if limite_total is not None else LIMITE_TOTAL_CHARS
    for a in anexos:
        if a.tipo == "imagem":
            if a.caminho in descricoes:
                partes.append(f"--- image: {_cabecalho(a)} ---\n(You cannot see images. A vision model described it:)\n"
                              f"{descricoes[a.caminho]}\n--- end of {a.nome} ---")
            else:
                partes.append(f"--- image: {_cabecalho(a)} --- (the image is attached to this message)")
            continue
        if a.tipo == "binario":
            partes.append(f"--- file: {_cabecalho(a)} ---")
            continue
        corpo = a.texto
        aviso = ""
        if len(corpo) > restante:
            corpo = corpo[:max(restante, 0)]
            aviso = "\n[... cut: the attachments of this message are too long ...]"
        restante -= len(corpo)
        if a.truncado and not aviso:
            aviso = "\n[... the file is longer than what is shown ...]"
        partes.append(f"--- file: {_cabecalho(a)} ---\n{corpo}{aviso}\n--- end of {a.nome} ---")
    return "\n\n".join(partes)


def imagens_b64(anexos):
    return [a.imagem_b64 for a in anexos if a.tipo == "imagem" and a.imagem_b64]


# ------------------------------------------------------------
# Terminal: achar caminhos numa linha ("@arquivo", arrastar e soltar)
# ------------------------------------------------------------

_ARROBA = re.compile(r"(?<!\S)@(\"[^\"]+\"|'[^']+'|\S+)")


def separar_arrobas(linha):
    """'resuma @notas.txt e @"meu doc.pdf"' -> ('resuma e', ['notas.txt', 'meu doc.pdf']),
    só dos '@caminho' que existem de fato (o resto continua no texto)."""
    achados = []

    def troca(m):
        bruto = m.group(1)
        if bruto[0] in "\"'" and bruto[-1] == bruto[0]:
            bruto = bruto[1:-1]
        if bruto and _existe(normalizar_caminho(bruto)):
            achados.append(bruto)
            return ""
        return m.group(0)

    texto = _ARROBA.sub(troca, linha)
    return re.sub(r"\s{2,}", " ", texto).strip(), achados


def linha_e_so_caminho(linha):
    """Quem arrasta um arquivo pro terminal cola só o caminho: se a linha
    inteira (com ou sem aspas) é um arquivo/pasta que existe, devolve-o."""
    t = str(linha or "").strip()
    if not t or "\n" in t or len(t) > 1000:
        return None
    candidatos = [t]
    # vários arrastados de uma vez: 'a.png' 'b.txt'
    entre_aspas = re.findall(r"'([^']+)'|\"([^\"]+)\"", t)
    if len(entre_aspas) > 1 and not re.sub(r"'[^']*'|\"[^\"]*\"|\s+", "", t):
        candidatos = [a or b for a, b in entre_aspas]
    caminhos = []
    for c in candidatos:
        if not (c.startswith(("/", "~", "file://", "'", '"', ".")) or ambiente.parece_caminho_windows(c)):
            return None
        p = normalizar_caminho(c)
        if not _existe(p):
            return None
        caminhos.append(c)
    return caminhos

# ------------------------------------------------------------
# Imagens citadas no texto do pedido ("veja home/pictures/foto.png")
# ------------------------------------------------------------
_RE_IMAGEM_NO_TEXTO = re.compile(r"""(?:"([^"\n]+\.(?:png|jpe?g|webp|gif|bmp))"|'([^'\n]+\.(?:png|jpe?g|webp|gif|bmp))'|"""
                                 r"""((?:file://)?[^\s"'<>|]+\.(?:png|jpe?g|webp|gif|bmp)))""", re.IGNORECASE)
_APELIDOS_PASTAS = {"pictures": ("Pictures", "Imagens"), "imagens": ("Imagens", "Pictures"),
                    "downloads": ("Downloads", "Transferências", "Descargas", "Téléchargements"),
                    "documents": ("Documents", "Documentos"), "documentos": ("Documentos", "Documents"),
                    "desktop": ("Desktop", "Área de Trabalho", "Escritorio", "Bureau", "Schreibtisch"),
                    "área de trabalho": ("Área de Trabalho", "Desktop"), "area de trabalho": ("Área de Trabalho", "Desktop"),
                    "home": ()}


def _resolver_sem_caixa(base, partes):
    """Anda por `partes` a partir de `base`, aceitando maiúscula/minúscula diferente e os nomes de pasta em
    português/inglês (pictures = Imagens). Volta atrás se o caminho não continuar: com ~/Documents E ~/Documentos,
    "Documents/foto.png" acha a foto que está em Documentos (antes parava na primeira). None se não achar."""
    partes = [p for p in partes if p and p != "."]
    atual = Path(base)
    if not partes:
        return atual
    parte, resto = partes[0], partes[1:]
    try:
        nomes = {p.name.lower(): p.name for p in atual.iterdir()}
    except OSError:
        return None
    opcoes = [nomes[n] for n in dict.fromkeys([parte.lower()] + [a.lower() for a in _APELIDOS_PASTAS.get(parte.lower(), ())])
              if n in nomes]
    for nome in opcoes:
        achado = _resolver_sem_caixa(atual / nome, resto)
        if achado is not None and (resto or achado.exists()):
            return achado
    return None


def resolver_caminho_citado(token):
    """Caminho existente (Path) pro que a pessoa escreveu, ou None. Aceita: absoluto, ~/x, relativo à pasta
    pessoal, "home/pictures/x.png" (sem a barra), e erro de maiúscula."""
    bruto = str(token or "").strip()
    if not bruto:
        return None
    try:
        direto = normalizar_caminho(bruto)
        if _existe(direto) and direto.is_file():
            return direto
    except Exception:
        pass
    limpo = bruto[7:] if bruto.lower().startswith("file://") else bruto
    partes = [p for p in re.split(r"[\\/]+", limpo) if p]
    casa = Path.home()
    candidatos = []
    if partes and partes[0].lower() == "home":
        candidatos.append((casa, partes[1:]))          # "home/pictures/x.png" = ~/pictures/x.png
        candidatos.append((Path("/home"), partes[1:]))
    candidatos.append((casa, partes))
    if limpo.startswith("/"):
        candidatos.insert(0, (Path("/"), partes))
    for base, resto in candidatos:
        achado = _resolver_sem_caixa(base, resto)
        if achado is not None and _existe(achado) and achado.is_file():
            return achado
    return None


def achar_imagens_no_texto(texto, maximo=3):
    """[Path] das imagens que o pedido cita e que existem (sem repetir)."""
    achadas = []
    for m in _RE_IMAGEM_NO_TEXTO.finditer(texto or ""):
        token = next(g for g in m.groups() if g)
        caminho = resolver_caminho_citado(token)
        if caminho is not None and caminho not in achadas:
            achadas.append(caminho)
        if len(achadas) >= maximo:
            break
    return achadas

