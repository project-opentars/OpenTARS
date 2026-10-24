"""5.2 (F4, buscar arquivos): acha arquivos na pasta pessoal pelo nome e pelo texto de dentro, a partir de uma frase
("o contrato de aluguel de 2024"). Sem modelo e sem índice (os embeddings saíram na 4.0): anda pelas pastas com limite
de tempo e de arquivos, lê o texto dos tipos comuns (txt, md, csv, docx, odt e pdf pelo pdftotext, se houver) e pontua.
Só leitura: não abre, não move, não apaga. Igual nos três sistemas; só biblioteca padrão.
"""
import os
import re
import shutil
import subprocess
import time
import unicodedata
import zipfile
from pathlib import Path

VAZIAS = set("""o a os as um uma uns umas de da do das dos e em no na nos nas para pra por com que meu minha meus minhas
onde esta está esse essa este aquele aquela ao aos qual quais tem sobre ache acha achar encontre encontrar procure procurar
busque buscar busca arquivo arquivos documento documentos pasta the an of in on for my where is are file files find search
folder document documents me eu i""".split())
TEXTO = {".txt", ".md", ".csv", ".rtf", ".tex"}      # documentos; código e configuração só valem pelo nome
LEGIVEIS = TEXTO | {".docx", ".odt", ".pdf"}
PULAR = {"node_modules", "venv", ".venv", "__pycache__", "site-packages", "AppData", "Library", "snap", "go", "build", "dist"}
LIMITE_ARQUIVOS = 30000
LIMITE_TEMPO_S = 4.0
LIMITE_LEITURAS = 300
LIMITE_TAMANHO = 20 * 1024 * 1024
PROFUNDIDADE = 6


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()
    return texto


def termos(frase):
    """As palavras que importam da frase, sem acento e sem as vazias ("o contrato de aluguel de 2024" -> contrato, aluguel, 2024)."""
    return [p for p in dict.fromkeys(re.findall(r"[a-z0-9]+", normalizar(frase))) if p not in VAZIAS and len(p) > 1]


def texto_do_arquivo(caminho, limite=200_000):
    """O texto de dentro, ou "" se o tipo não tem texto que dê para ler (PDF que é só imagem, por exemplo)."""
    ext = caminho.suffix.lower()
    try:
        if ext in TEXTO:
            with open(caminho, "rb") as f:
                return f.read(limite).decode("utf-8", "replace")
        if ext in (".docx", ".odt"):
            with zipfile.ZipFile(caminho) as z:
                xml = z.read("word/document.xml" if ext == ".docx" else "content.xml")[:limite * 4].decode("utf-8", "replace")
            return re.sub(r"<[^>]+>", " ", xml)
        if ext == ".pdf" and shutil.which("pdftotext"):
            r = subprocess.run(["pdftotext", "-l", "5", "-q", str(caminho), "-"], capture_output=True, timeout=8)
            return r.stdout[:limite].decode("utf-8", "replace")
    except (OSError, zipfile.BadZipFile, KeyError, subprocess.SubprocessError):
        pass
    return ""


def _arquivos(raiz, inicio):
    """Os arquivos sob a raiz, sem pastas ocultas nem de programas, até os limites."""
    contados = 0
    raiz = Path(raiz)
    for pasta, subpastas, nomes in os.walk(raiz):
        profundidade = len(Path(pasta).relative_to(raiz).parts)
        subpastas[:] = [] if profundidade >= PROFUNDIDADE else \
            [s for s in subpastas if not s.startswith(".") and s not in PULAR]
        for nome in nomes:
            if nome.startswith("."):
                continue
            contados += 1
            if contados > LIMITE_ARQUIVOS or time.monotonic() - inicio > LIMITE_TEMPO_S:
                return
            yield Path(pasta) / nome


def _trecho(texto, palavras, largura=140):
    plano = " ".join(texto.split())
    normal = normalizar(plano)
    pos = min((normal.find(p) for p in palavras if normal.find(p) >= 0), default=0)    # sem a palavra no texto: o começo
    inicio = max(0, pos - largura // 3)
    return ("…" if inicio else "") + plano[inicio:inicio + largura].strip() + "…"


def buscar(frase, raiz=None, limite=5, ler=texto_do_arquivo):
    """[{caminho, nome, pasta, modificado, trecho, sem_texto, pontos}] do melhor para o pior. Um arquivo entra quando
    tem pelo menos metade das palavras da frase no nome, na pasta ou no texto."""
    palavras = termos(frase)
    if not palavras:
        return []
    raiz = Path(raiz or Path.home())
    inicio = time.monotonic()
    candidatos = []
    for caminho in _arquivos(raiz, inicio):
        nome = normalizar(caminho.stem)
        pastas = normalizar(" ".join(caminho.relative_to(raiz).parts[:-1]))
        no_nome = {p for p in palavras if p in nome}
        na_pasta = {p for p in palavras if p in pastas} - no_nome
        candidatos.append([caminho, no_nome, na_pasta])
    # o texto de dentro: primeiro os que já batem pelo nome, depois os mais recentes
    def mtime(c):
        try:
            return c[0].stat().st_mtime
        except OSError:
            return 0
    legiveis = [c for c in candidatos if c[0].suffix.lower() in LEGIVEIS]
    legiveis.sort(key=lambda c: (-len(c[1]), -mtime(c)))
    textos = {}
    for c in legiveis[:LIMITE_LEITURAS]:
        try:
            if c[0].stat().st_size > LIMITE_TAMANHO:
                continue
        except OSError:
            continue
        textos[c[0]] = ler(c[0])
    minimo = max(1, (len(palavras) + 1) // 2)
    achados = []
    for caminho, no_nome, na_pasta in candidatos:
        texto = textos.get(caminho, "")
        no_texto = {p for p in palavras if p in normalizar(texto)} - no_nome - na_pasta if texto else set()
        if len(no_nome | na_pasta | no_texto) < minimo:
            continue
        try:
            modificado = caminho.stat().st_mtime
        except OSError:
            continue
        achados.append({"caminho": str(caminho), "nome": caminho.name, "pasta": str(caminho.parent),
                        "modificado": modificado, "trecho": _trecho(texto, palavras) if texto else "",
                        "sem_texto": caminho.suffix.lower() == ".pdf" and caminho in textos and not texto.strip(),
                        "pontos": 3 * len(no_nome) + 2 * len(na_pasta) + len(no_texto)})
    achados.sort(key=lambda a: (-a["pontos"], -a["modificado"]))
    return achados[:limite]
