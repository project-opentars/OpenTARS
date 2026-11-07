"""Liga o nome que a pessoa escreveu ao arquivo de verdade.

A pessoa escreve "o relatorio", "leia-me", "Documents/nota.txt" ou "a pasta musicas"; o disco tem relatorio-2026.txt, Leia-me.TXT,
notas.txt e musicas/. As regras e os comandos do modelo passam por aqui antes de rodar, então um nome quase certo vira o certo
(ou vira uma pergunta, quando apagar seria o efeito).
"""
import difflib
import os
import re
import unicodedata

APELIDOS = {"documentos": "Documents", "documents": "Documents", "downloads": "Downloads", "area de trabalho": "Desktop", "desktop": "Desktop",
            "imagens": "Pictures", "pictures": "Pictures", "musicas": "Music", "music": "Music", "videos": "Videos", "home": "", "pessoal": "",
            "minha home": "", "pasta pessoal": "", "my home": "", "home folder": ""}
PROFUNDIDADE = 3
LIMITE = 4000          # numa placa com cartão SD, procurar não pode demorar


def _chave(texto):
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)).lower()


def casa():
    return os.path.expanduser("~")


def _absoluto(caminho):
    caminho = os.path.expanduser(caminho)
    return caminho if os.path.isabs(caminho) else os.path.join(casa(), caminho)


def bonito(caminho):
    """O caminho como a pessoa escreveria: ~/x em vez de /home/enzo/x."""
    c = casa()
    return "~" + caminho[len(c):] if caminho == c or caminho.startswith(c + "/") else caminho


def _filhos(pasta):
    try:
        return os.listdir(pasta)
    except OSError:
        return []


def _segmento(pasta, nome):
    """O filho de `pasta` que é `nome` sem olhar maiúsculas e acentos, ou None."""
    alvo = _chave(nome)
    for filho in _filhos(pasta):
        if _chave(filho) == alvo:
            return filho
    return None


def exato(caminho):
    """O caminho real se ele existe, ignorando maiúsculas, acentos e apelido de pasta ("documentos/x" = Documents/x). Senão None."""
    caminho = caminho.strip().rstrip(".,;:!?")
    if not caminho:
        return None
    chave = _chave(caminho.rstrip("/"))
    if chave in APELIDOS and not os.path.exists(_absoluto(caminho)):
        alvo = os.path.join(casa(), APELIDOS[chave]).rstrip("/")
        return alvo if os.path.isdir(alvo) or not APELIDOS[chave] else None
    absoluto = _absoluto(caminho)
    if os.path.exists(absoluto):
        return absoluto.rstrip("/") or "/"
    partes = absoluto.strip("/").split("/")
    atual = "/"
    for parte in partes:
        achado = _segmento(atual, parte)
        if achado is None:
            apelido = APELIDOS.get(_chave(parte))
            if apelido and os.path.isdir(os.path.join(atual, apelido)):
                achado = apelido
        if achado is None:
            return None
        atual = os.path.join(atual, achado)
    return atual


def _andar(raiz, profundidade=PROFUNDIDADE):
    """Arquivos e pastas até `profundidade`, sem os escondidos, os mais rasos primeiro."""
    vistos, fila = 0, [(raiz, 0)]
    while fila:
        pasta, nivel = fila.pop(0)
        for nome in sorted(_filhos(pasta)):
            if nome.startswith("."):
                continue
            caminho = os.path.join(pasta, nome)
            yield caminho
            vistos += 1
            if vistos > LIMITE:
                return
            if nivel + 1 < profundidade and os.path.isdir(caminho) and not os.path.islink(caminho):
                fila.append((caminho, nivel + 1))


def _sem_ext(nome):
    return re.sub(r"\.[a-z0-9]{1,6}$", "", nome)


_SINONIMOS = {"readme": ("leiame", "leia-me"), "leiame": ("readme", "leia-me"), "leia-me": ("readme", "leiame")}


def _notas(caminho, pasta=False, arquivo=False):
    """[(nota, candidato)] para um nome que não existe, do melhor para o pior.
    Dentro da pasta que a pessoa citou; se ela não citou, na casa toda (até 3 níveis)."""
    caminho = caminho.strip().rstrip("/")
    dono, nome = os.path.split(caminho)
    raiz = (exato(dono) or resolver(dono, pasta=True)[0]) if dono else casa()     # "projets/sensor/x" também
    alvo = _chave(nome)
    if not raiz or not alvo:
        return []
    alvo_base = _sem_ext(alvo)
    tem_ext = alvo_base != alvo
    outros = _SINONIMOS.get(alvo_base, ())         # "readme" acha o LEIAME.md
    dentro = raiz == casa() or raiz.startswith(casa() + "/")
    notas = []
    for candidato in _andar(raiz, PROFUNDIDADE if dentro else 1):     # fora da casa, só a própria pasta
        if (pasta and not os.path.isdir(candidato)) or (arquivo and not os.path.isfile(candidato)):
            continue
        base = _chave(os.path.basename(candidato))
        sem = _sem_ext(base)
        if base == alvo:
            nota = 1.0
        elif sem == alvo or (sem == alvo_base and not tem_ext) or sem in outros:
            nota = 0.95                                  # leia-me -> Leia-me.TXT (velho.txt não vira velho.deb)
        elif len(alvo_base) >= 4 and sem.startswith(alvo_base):
            nota = 0.85                                  # relatorio -> relatorio-2026.txt
        else:
            nota = difflib.SequenceMatcher(None, alvo, base).ratio()
            if nota < 0.8:
                continue                                 # nota.txt -> notas.txt passa; log.txt -> app.log não
        notas.append((nota - 0.02 * candidato[len(raiz):].count("/"), candidato))
    return sorted(notas, key=lambda x: -x[0])


def parecidos(caminho, pasta=False, arquivo=False, maximo=3):
    return [c for _, c in _notas(caminho, pasta, arquivo)[:maximo]]


def resolver(caminho, pasta=False, arquivo=False):
    """(caminho real, certeza). certeza: 'exato' (existe), 'parecido' (um candidato bem à frente dos outros) ou None."""
    real = exato(caminho)
    if real and (not pasta or os.path.isdir(real)) and (not arquivo or os.path.isfile(real)):
        return real, "exato"
    notas = _notas(caminho, pasta, arquivo)
    if notas and notas[0][0] >= 0.8 and (len(notas) == 1 or notas[1][0] < notas[0][0] - 0.05):
        return notas[0][1], "parecido"
    return None, None


def com_mesma_extensao(caminho):
    """Quando a pessoa erra o nome inteiro ("log.txt" e só existe "logs/app.log"): primeiro os que têm o nome-base, depois a mesma extensão."""
    nome = _chave(os.path.basename(caminho))
    ext, base = os.path.splitext(nome)[1], _sem_ext(nome)
    achados = []
    for candidato in _andar(casa()):
        if os.path.isfile(candidato):
            b = _chave(candidato[len(casa()):])
            nota = 2 if base and base in b else 1 if ext and b.endswith(ext) else 0
            if nota:
                achados.append((nota, candidato))
    return [c for _, c in sorted(achados, key=lambda x: -x[0])[:5]]
