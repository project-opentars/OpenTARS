"""5.2 (F4, buscar arquivos): acha arquivos na pasta pessoal pelo nome e pelo texto de dentro, a partir de uma frase
("o contrato de aluguel de 2024"). Sem modelo e sem índice (os embeddings saíram na 4.0): anda pelas pastas com limite
de tempo e de arquivos, lê o texto dos tipos comuns (txt, md, csv, docx, odt e pdf pelo pdftotext, se houver) e pontua.
Só leitura: não abre, não move, não apaga. Igual nos três sistemas; só biblioteca padrão.
"""
import os
import re
import shutil
import sqlite3
import subprocess
import time
import unicodedata
import zipfile
from pathlib import Path

import tars_i18n
import tars_plataforma as plataforma

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


# ---------------------------------------------------------------- índice local (5.3, F4+): opcional, desligado por padrão
# Um arquivo SQLite na pasta de dados do openTARS com o nome, a pasta e o começo do texto de cada arquivo, para a busca ser
# instantânea em pastas grandes. Fica só neste computador, nunca é enviado, e se apaga ao desligar. Sem embeddings: continua
# sendo nome e palavras, como a busca sem índice.
TEXTO_NO_INDICE = 8000            # caracteres do começo de cada arquivo
VALIDADE_INDICE_S = 3600          # a busca atualiza o índice (em segundo plano) se ele tem mais de uma hora


def indice_ligado():
    return bool(tars_i18n.ler_config().get("indice_arquivos"))


def caminho_do_indice():
    return plataforma.pastas()["dados"] / "indice-arquivos.db"


def ligar_indice(ligado):
    """Liga ou desliga. Desligar apaga o arquivo do índice: nada fica guardado."""
    tars_i18n.salvar_config(indice_arquivos=bool(ligado))
    if not ligado:
        try:
            caminho_do_indice().unlink()
        except OSError:
            pass


def _abrir_indice(caminho):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    banco = sqlite3.connect(str(caminho), timeout=10)
    banco.execute("CREATE TABLE IF NOT EXISTS arquivos (caminho TEXT PRIMARY KEY, mtime REAL, nome TEXT, texto TEXT, busca TEXT)")
    banco.execute("CREATE TABLE IF NOT EXISTS meta (chave TEXT PRIMARY KEY, valor TEXT)")
    return banco


def atualizar_indice(raiz=None, tempo=25.0, ler=texto_do_arquivo, caminho=None):
    """Põe no índice os arquivos novos ou mudados (por data de modificação) e tira os que sumiram. Devolve
    {"arquivos": n, "lidos": n, "removidos": n}. Corta no tempo: o que não deu volta na próxima atualização."""
    global LIMITE_TEMPO_S
    raiz = Path(raiz or Path.home())
    banco = _abrir_indice(caminho or caminho_do_indice())
    inicio = time.monotonic()
    guardados = {c: m for c, m in banco.execute("SELECT caminho, mtime FROM arquivos")}
    vistos, lidos = set(), 0
    antes, LIMITE_TEMPO_S = LIMITE_TEMPO_S, tempo      # a varredura do índice pode demorar mais que a busca sem índice
    try:
        for arquivo in _arquivos(raiz, inicio):
            chave = str(arquivo)
            try:
                st = arquivo.stat()
            except OSError:
                continue
            vistos.add(chave)
            if guardados.get(chave) == st.st_mtime:
                continue
            texto = ""
            if arquivo.suffix.lower() in LEGIVEIS and st.st_size <= LIMITE_TAMANHO:
                texto = (ler(arquivo) or "")[:TEXTO_NO_INDICE * 2]
                texto = " ".join(texto.split())[:TEXTO_NO_INDICE]
            pastas = " ".join(arquivo.relative_to(raiz).parts[:-1])
            banco.execute("INSERT OR REPLACE INTO arquivos VALUES (?,?,?,?,?)",
                          (chave, st.st_mtime, arquivo.name, texto, normalizar(f"{arquivo.stem} {pastas} {texto}")))
            lidos += 1
    finally:
        LIMITE_TEMPO_S = antes
    completo = time.monotonic() - inicio < tempo
    sumiram = [c for c in guardados if c not in vistos] if completo else []     # só apaga se a varredura foi até o fim
    banco.executemany("DELETE FROM arquivos WHERE caminho=?", [(c,) for c in sumiram])
    banco.execute("INSERT OR REPLACE INTO meta VALUES ('atualizado', ?)", (str(time.time()),))
    banco.commit()
    total = banco.execute("SELECT COUNT(*) FROM arquivos").fetchone()[0]
    banco.close()
    return {"arquivos": total, "lidos": lidos, "removidos": len(sumiram)}


def indice_idade(caminho=None):
    """Segundos desde a última atualização, ou None se não há índice."""
    caminho = caminho or caminho_do_indice()
    if not caminho.exists():
        return None
    try:
        banco = _abrir_indice(caminho)
        linha = banco.execute("SELECT valor FROM meta WHERE chave='atualizado'").fetchone()
        banco.close()
        return time.time() - float(linha[0]) if linha else None
    except (sqlite3.Error, ValueError):
        return None


def buscar_no_indice(frase, raiz=None, limite=5, caminho=None):
    """O mesmo resultado de buscar(), lido do índice (instantâneo). None se não há índice para usar."""
    palavras = termos(frase)
    if not palavras:
        return []
    caminho = caminho or caminho_do_indice()
    if indice_idade(caminho) is None:
        return None
    raiz = str(Path(raiz or Path.home()))
    banco = _abrir_indice(caminho)
    try:
        filtro = " OR ".join("busca LIKE ?" for _ in palavras)
        linhas = banco.execute(f"SELECT caminho, mtime, nome, texto, busca FROM arquivos WHERE caminho LIKE ? AND ({filtro})",
                               [raiz.rstrip(os.sep) + os.sep + "%"] + [f"%{p}%" for p in palavras]).fetchall()
    finally:
        banco.close()
    minimo = max(1, (len(palavras) + 1) // 2)
    achados = []
    for arquivo, modificado, nome, texto, busca_n in linhas:
        stem = normalizar(Path(nome).stem)
        pasta_n = normalizar(" ".join(Path(arquivo).relative_to(raiz).parts[:-1]))
        no_nome = {p for p in palavras if p in stem}
        na_pasta = {p for p in palavras if p in pasta_n} - no_nome
        no_texto = {p for p in palavras if texto and p in normalizar(texto)} - no_nome - na_pasta
        if len(no_nome | na_pasta | no_texto) < minimo:
            continue
        achados.append({"caminho": arquivo, "nome": nome, "pasta": str(Path(arquivo).parent), "modificado": modificado,
                        "trecho": _trecho(texto, palavras) if texto else "",
                        "sem_texto": nome.lower().endswith(".pdf") and not texto.strip(),
                        "pontos": 3 * len(no_nome) + 2 * len(na_pasta) + len(no_texto)})
    achados.sort(key=lambda a: (-a["pontos"], -a["modificado"]))
    return achados[:limite]


def buscar(frase, raiz=None, limite=5, ler=texto_do_arquivo, indice=None):
    """Com o índice ligado e existente, lê dele (e, se ele tem mais de uma hora, o atualiza em segundo plano); senão anda pelas
    pastas como na 5.2. `indice`: True/False força; None segue a configuração."""
    usar = indice_ligado() if indice is None else indice
    if usar:
        achados = buscar_no_indice(frase, raiz, limite)
        if achados is not None:
            idade = indice_idade()
            if idade is not None and idade > VALIDADE_INDICE_S:
                import threading
                threading.Thread(target=lambda: atualizar_indice(raiz), daemon=True).start()
            return achados
    return _buscar_andando(frase, raiz, limite, ler)


def _buscar_andando(frase, raiz=None, limite=5, ler=texto_do_arquivo):
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
