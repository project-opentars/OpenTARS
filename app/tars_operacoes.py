"""As operações de arquivo mais comuns, com os nomes ligados ao disco (nomes.py) e uma frase pronta com a resposta.

Medido em 07/11 (prova de capacidade, tools/prova): o modelo de 270M acertava 2 de 7 leituras e 0 de 7 escritas, porque trocava
o caminho ("Documents/notas.txt" virava "/notas.txt") e não sabia contar, comparar nem resumir a saída. Aqui cada operação é uma
regra geral (ver, contar, procurar, maior e menor, copiar, mover, renomear, criar, acrescentar, executável, compactar) e o resultado
volta como frase: "aparece 5 vezes em ~/logs/app.log", não só a saída crua.

plano() devolve None (não é com estas regras), uma string (o comando) ou um dict:
  {"comando": ..., "resumo": chave, "alvo": ..., "nota": ...} ou {"fala": ...}.
"""
import os
import re
import shlex
import shutil

import tars_nomes as nomes
from tars_atalhos_textos import t

TIPOS = {"fotos": ("jpg", "jpeg", "png", "gif", "webp", "heic"), "imagens": ("jpg", "jpeg", "png", "gif", "webp", "heic"),
         "photos": ("jpg", "jpeg", "png", "gif", "webp", "heic"), "pictures": ("jpg", "jpeg", "png", "gif", "webp", "heic"),
         "images": ("jpg", "jpeg", "png", "gif", "webp", "heic"), "videos": ("mp4", "mkv", "avi", "mov", "webm"),
         "musicas": ("mp3", "flac", "ogg", "wav", "m4a"), "music": ("mp3", "flac", "ogg", "wav", "m4a"), "pdfs": ("pdf",)}
_ARTIGO = r"(?:(?:o|a|os|as|um|uma|the|an?|my|meu|minha|meus|minhas)\s+)?"
_PASTA = r"(?:(?:a|uma|the|an?)\s+)?(?:nova\s+|new\s+)?(?:pasta|folder|diretorio|directory)\s+(?:nova\s+|new\s+)?(?:chamada\s+|called\s+|named\s+)?"
_ARQ = r"(?:(?:o|um|the|an?)\s+)?(?:arquivo|file)\s+(?:chamado\s+|called\s+|named\s+)?"
_FIM = r"\s*[?.!]*$"
_DE = r"\s+(?:d[oae]s?|from|in|inside|em|na|no|of|dentro d[aeo])\s+"


class Frase:
    def __init__(self, pedido, n):
        self.n = n
        self.orig = pedido.strip() if len(pedido.strip()) == len(n) else n

    def busca(self, padrao):
        return re.search(padrao, self.n)

    def g(self, achado, i):
        return self.orig[achado.start(i):achado.end(i)] if achado.group(i) is not None else None


def _q(caminho):
    """Entre aspas para o shell, com o ~ do lado de fora."""
    if caminho == "~":
        return "~"
    if caminho.startswith("~/"):
        return "~/" + shlex.quote(caminho[2:])
    return shlex.quote(caminho)


def _rel(real):
    """Como aparece no comando: ~/x para o que está na casa, o caminho inteiro para o resto."""
    return nomes.bonito(real)


def _limpar_alvo(texto):
    texto = re.sub(r"\s+(?:inteir[ao]|tod[ao]|completa(?:mente)?|entire|whole|completely)\b", "", texto.strip(), flags=re.IGNORECASE)   # "a pasta projetos inteira"
    texto = re.sub(r"^(?:dentro d[aeo]s?|inside(?: of)?|into|para dentro d[aeo])\s+", "", texto.strip(), flags=re.IGNORECASE)
    texto = re.sub(r"^(?:" + _PASTA + r"|" + _ARQ + r")", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"^(?:o|a|os|as|the|my|meu|minha|um|uma)\s+", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\s+(?:folder|directory|dir|pasta|file|arquivo)$", "", texto, flags=re.IGNORECASE)     # "the logs folder"
    return texto.strip(" '\"?.!,")


def _fonte(texto, pasta=False, arquivo=False):
    """(caminho real, nota) do que a pessoa citou e precisa existir. nota explica quando o nome foi corrigido."""
    alvo = _limpar_alvo(texto)
    if not alvo:
        return None, None
    contexto = re.match(r"^(.+?)\s+(?:d[oae]s?|from|in|inside|em|na|no|of)\s+(?:projeto\s+|project\s+)?(.+)$", alvo)
    if contexto and not nomes.exato(alvo):             # "leia-me do Downloads", "README do projeto sensor"
        pasta_real, _ = nomes.resolver(_limpar_alvo(contexto.group(2)), pasta=True)
        if pasta_real:
            alvo = os.path.join(pasta_real, _limpar_alvo(contexto.group(1)))
    real, certeza = nomes.resolver(alvo, pasta, arquivo)
    if certeza == "parecido":
        alvo = nomes.bonito(alvo)
        return real, ("usei" if "/" in alvo or "." in alvo and os.path.basename(alvo).lower() != os.path.basename(real).lower() else "achei", alvo, _rel(real))
    return real, None


def _nota(nota, idioma):
    if not nota:
        return None
    return t("nome_corrigido" if nota[0] == "usei" else "achei_em", idioma, pedido=nota[1], real=nota[2])


def _resultado(comando, idioma, resumo=None, alvo=None, nota=None, **extra):
    r = {"comando": comando}
    if resumo:
        r["resumo"] = resumo
    if alvo:
        r["alvo"] = alvo
    if nota:
        r["nota"] = _nota(nota, idioma)
    r.update(extra)
    return r


def _nao_achei(texto, idioma, mesma_extensao=True):
    alvo = _limpar_alvo(texto)
    sugestoes = nomes.parecidos(alvo) or (nomes.com_mesma_extensao(alvo) if mesma_extensao else [])
    if sugestoes:
        return {"fala": t("nao_achei_arquivo_sugestao", idioma, nome=alvo, sugestoes=", ".join(_rel(s) for s in sugestoes[:3]))}
    return {"fala": t("nao_achei_arquivo", idioma, nome=alvo)}


def _arquivo_ou_substituto(texto, idioma):
    """O arquivo citado; se ele não existe, o único parecido (ou o log certo para "log.txt"). (real, nota) ou (None, resposta)."""
    real, nota = _fonte(texto, arquivo=True)
    if real:
        return real, nota
    alvo = _limpar_alvo(texto)
    if "." in os.path.basename(alvo):
        candidatos = nomes.com_mesma_extensao(alvo)
        base = re.sub(r"\.[a-z0-9]+$", "", os.path.basename(alvo).lower())
        fortes = [c for c in candidatos if base and base in c[len(nomes.casa()):].lower()]
        if len(fortes) == 1:
            return fortes[0], ("usei", alvo, _rel(fortes[0]))
    return None, _nao_achei(texto, idioma)


def _parece_caminho(texto):
    return bool(re.search(r"[/~]|\.[a-z0-9]{1,6}$", _limpar_alvo(texto)))


# ---------------- leitura ----------------

def _ocorrencias(f, idioma):
    a = f.busca(r"\b(?:quantas vezes|quantos|quantas|how many times(?: does)?|how many|count(?: the)?(?: times)?)\s+(?:o |a |os |as |the )?(?:palavra |word |texto |text )?"
                r"[\"']?(.+?)[\"']?\s+(?:aparecem?|tem|existem|ha|sao|appears?|occurs?|shows? up|are there|is there|are|is)?\s*(?:no|na|em|in|dentro d[oe])\s+"
                + _ARTIGO + r"(?:arquivo |file )?(\S+?)" + _FIM)
    if not a or re.match(r"^(linhas|lines|arquivos|files|pastas|folders)$", a.group(1)):
        return None
    termo = re.sub(r"^(?:aparecem?|appears?|tem|ha|existe)\s+", "", f.g(a, 1).strip(" '\""), flags=re.IGNORECASE)   # "quantas vezes aparece ERROR"
    termo = {"erros": "error", "errors": "error", "avisos": "warn", "warnings": "warn", "alertas": "warn"}.get(termo.lower(), termo)
    real, nota = _arquivo_ou_substituto(f.g(a, 2), idioma)
    if not real:
        return nota
    return _resultado(f"grep -ci -- {shlex.quote(termo)} {_q(_rel(real))}", idioma, "ocorrencias", _rel(real), nota, termo=termo)


def _contar_linhas(f, idioma):
    a = f.busca(r"\b(?:quantas linhas|how many lines|conta(?:r)? as linhas|conte as linhas|count (?:the )?lines|numero de linhas)\b(?:\s+(?:tem|ha|existem|does|has|are there))?"
                r"(?:\s+(?:d[oae]s?|of|in|em|no|na))?\s+" + _ARTIGO + r"(?:arquivo |file )?(\S+?)(?:\s+(?:tem|have|has))?" + _FIM)
    if not a:
        return None
    real, nota = _arquivo_ou_substituto(f.g(a, 1), idioma)
    if not real:
        return nota
    return _resultado(f"wc -l {_q(_rel(real))}", idioma, "linhas", _rel(real), nota)     # com "<" a segurança pediria aprovação de uma leitura


def _contar_arquivos(f, idioma):
    a = f.busca(r"\b(?:quantos arquivos|how many files|conta(?:r)? (?:os |quantos )?arquivos|count (?:the )?files)\b(?:\s+(?:tem|ha|existem|are there|there are))?"
                r"(?:\s+(?:no|na|em|in|dentro d[oe]))?\s+" + _ARTIGO + r"(?:pasta |folder )?(\S+?)" + _FIM)
    if not a:
        return None
    real, nota = _fonte(f.g(a, 1), pasta=True)
    if not real:
        return None
    return _resultado(f"find {_q(_rel(real))} -maxdepth 1 -type f | wc -l", idioma, "contar_arquivos", _rel(real), nota)


def _qual_arquivo(f, idioma):
    a = f.busca(r"\b(?:(?:em |no )?(?:qual|que) arquivo|which file|what file|onde (?:esta|fica) (?:escrit[oa]|anotad[oa]|guardad[oa])|(?:tem |ha |existe )?algum arquivo|(?:is there )?any file)\s+"
                r"(?:(?:falando|que fala|mencionando|que menciona|que tem|com|sobre|about|mentioning|that mentions|with|containing|that has)\s+)?"
                r"(?:(?:esta|tem|fala|contem|menciona|cita|aparece|has|contains|mentions|talks|says|is|esta escrit[oa]|foi escrit[oa])\s+)?"
                r"(?:(?:escrit[oa]|de|sobre|about|anotad[oa])\s+)?(?:a |o |as |os |the )?(.+?)" + _FIM)
    if not a:
        return None
    termo = f.g(a, 1).strip(" '\"")
    termo = re.sub(r"\s+(?:escrit[oa]|written|mentioned)$", "", termo)
    if len(termo) < 3:
        return None
    return _resultado(f"grep -ril --exclude-dir='.*' -- {shlex.quote(termo)} ~ 2>/dev/null | head -20", idioma, "arquivos_com", termo=termo)


def _maior_menor(f, idioma):
    a = f.busca(r"\b(maior|menor|biggest|largest|smallest)\s+(?:arquivo|file)\b(?:.{0,15}?" + _DE + r"(?:a pasta |pasta |the folder |my |minha )?(\S+?))?" + _FIM) \
        or f.busca(r"\b(?:arquivo|file)\s+(mais pesado|mais leve|mais grande|mais pequeno|heaviest|lightest)\b(?:.{0,15}?" + _DE + r"(?:a pasta |pasta |the folder |my |minha )?(\S+?))?" + _FIM) \
        or f.busca(r"\b(heaviest|lightest)\s+(?:file)\b(?:.{0,15}?" + _DE + r"(?:the folder |my )?(\S+?))?" + _FIM)
    if not a:
        return None
    pasta = nomes.casa()
    nota = None
    if a.group(2):
        pasta, nota = _fonte(f.g(a, 2), pasta=True)
        if not pasta:
            return None
    ordem = "-lhS" if a.group(1) in ("maior", "biggest", "largest", "mais pesado", "mais grande", "heaviest") else "-lhSr"
    return _resultado(f"ls {ordem} {_q(_rel(pasta))} | grep -v '^[dt]' | head -n 1", idioma, "maior" if ordem == "-lhS" else "menor", _rel(pasta), nota)


def _so_pastas(f, idioma):
    a = f.busca(r"\b(?:so|apenas|somente|only|just)\s+(?:as |os |the )?(?:pastas|diretorios|folders|directories)\b(?:" + _DE + r"(?:a pasta |the folder |my |minha )?(\S+?))?" + _FIM)
    if not a:
        return None
    pasta = nomes.casa()
    if a.group(1) and not re.match(r"^(home|casa|minha home)$", a.group(1)):
        pasta = _fonte(f.g(a, 1), pasta=True)[0] or pasta
    return _resultado(f"find {_q(_rel(pasta))} -mindepth 1 -maxdepth 1 -type d -not -name '.*' | sort", idioma, "lista")


def _escondidos(f, idioma):
    if f.busca(r"\b(?:arquivos |files )?(?:escondidos|ocultos|hidden)\b"):
        return _resultado("ls -A ~ | grep '^\\.'", idioma, "lista")
    return None


def _linhas_com(f, idioma):
    a = f.busca(r"\b(?:procura|procure|acha|ache|mostra|mostre|find|show|list|lista|get|pega|pegue)\s+(?:me\s+)?(?:as |the |all (?:the )?|todas as )?(?:linhas|lines)\s+(?:com|que tem|que contem|with|containing|that have|that contain|matching)\s+"
                r"[\"']?(.+?)[\"']?\s+(?:no|na|em|in|from|of|do|da)\s+" + _ARTIGO + r"(?:arquivo |file )?(\S+?)" + _FIM)
    if not a:
        return None
    real, nota = _arquivo_ou_substituto(f.g(a, 2), idioma)
    if not real:
        return nota
    return _resultado(f"grep -n -- {shlex.quote(f.g(a, 1))} {_q(_rel(real))}", idioma, "achados", _rel(real), nota)


def _ultimas(f, idioma):
    a = f.busca(r"\b(?:(?:as )?ultimas linhas|(?:the )?last lines|o final|the end|tail)\b" + _DE + _ARTIGO + r"(?:arquivo |file )?(\S+?)" + _FIM)
    if f.busca(r"\b(write|escreve|escreva|add|adiciona|append|acrescenta|put|coloca|insere)\b"):
        return None                      # "write X at the end of" é para escrever
    if not a or re.search(r"\d", f.n[:a.start(1)]):       # "as 5 últimas linhas" é com a regra que lê o número
        return None
    real, nota = _arquivo_ou_substituto(f.g(a, 1), idioma)
    if not real:
        return nota
    return _resultado(f"tail -n 20 {_q(_rel(real))}", idioma, nota=nota, alvo=_rel(real))


_VAZIAS_ASSUNTO = {"o", "a", "os", "as", "de", "do", "da", "dos", "das", "meu", "minha", "the", "of", "my", "with", "com", "sobre", "about", "e", "and"}


def _arquivo_sobre(assunto):
    """O arquivo cujo nome tem uma palavra do assunto ou cujo texto tem a frase. None se não há um só candidato claro."""
    palavras = [p for p in re.findall(r"[\w-]+", assunto.lower()) if p not in _VAZIAS_ASSUNTO and len(p) > 2]
    for palavra in sorted(palavras, key=len, reverse=True):
        real, certeza = nomes.resolver(palavra, arquivo=True)
        if real:
            return real
    import subprocess
    try:
        achados = subprocess.run(["grep", "-ril", "--exclude-dir=.*", "--", assunto.strip(), nomes.casa()], capture_output=True, text=True, timeout=10).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return None
    return achados[0] if len(achados) == 1 else None


def _ver(f, idioma):
    a = f.busca(r"^(?:por favor |please |pode |can you )?(?:mostra|mostre|abre|abra|abrir|le|leia|ler|ver|veja|exibe|exiba|show|open|read|display|cat|print|me mostra)\s+"
                r"(?:me\s+)?(?:o conteudo d[eoa]\s+|the contents? of\s+|o que (?:tem|ficou|sobrou|restou|ha|existe) (?:n[oa]|em)\s+|what(?:'s| is) (?:left )?in\s+)?(.+?)" + _FIM)
    if not a or f.busca(r"\b(processos|processes|memoria|memory|disco|disk|temperatura|temperature|ip|pinos?|pins?|gpio|log do sistema|system log|portas|ports|linhas|lines)\b"):
        return None
    texto = f.g(a, 1)
    sobre = re.match(r"^(?:o |a |the |my )?(?:arquivo|file)\s+(?:d[aoe]s?|about|with|sobre|com)\s+(.+)$", texto.strip(), re.IGNORECASE)
    if sobre:                            # "o arquivo da senha do wifi": o arquivo cujo nome ou texto fala disso
        achado = _arquivo_sobre(sobre.group(1))
        if achado:
            return _resultado(f"head -n 100 {_q(_rel(achado))}", idioma, nota=("achei", sobre.group(1), _rel(achado)))
    real, nota = _fonte(texto)
    if not real:
        nome = _limpar_alvo(texto)
        if " " in nome and not re.search(r"\s(?:d[oae]s?|from|in|em|na|no)\s", nome):
            return None                  # "the first 3 lines of x" não é um nome de arquivo
        if _parece_caminho(texto) or re.search(r"\b(arquivo|file)\b", f.n):
            real, resposta = _arquivo_ou_substituto(texto, idioma)
            if not real:
                return resposta
            nota = resposta
        else:
            return None
    if os.path.isdir(real):
        return _resultado(f"ls -la {_q(_rel(real))}", idioma, nota=nota)
    return _resultado(f"head -n 100 {_q(_rel(real))}", idioma, nota=nota)


def _por_extensao(f, idioma):
    a = f.busca(r"\b(?:lista|liste|listar|procura|procure|acha|ache|encontra|encontre|mostra|mostre|find|list|show|locate)\s+(?:todos os |todas as |os |as |all (?:the )?|the |my |meus |minhas )?"
                r"(?:(?:arquivos|files|fotos|photos|imagens|images|pictures|videos|documentos|documents)\s+)?\*?\.([a-z0-9]{1,8})(?:\s+(?:arquivos|files))?(?:" + _DE + r"(?:a pasta |the folder |my |minha )?(\S+?))?" + _FIM)
    if not a:
        return None
    pasta, nota = (_fonte(f.g(a, 2), pasta=True) if a.group(2) else (nomes.casa(), None))
    if not pasta:
        return None
    return _resultado(f"find {_q(_rel(pasta))} -iname '*.{a.group(1)}' -not -path '*/.*' 2>/dev/null | head -50", idioma, "achados", _rel(pasta), nota)


def _mkdir_dentro(f, idioma):
    a = f.busca(r"\b(?:cria|crie|criar|faz|faca|make|create)\s+(?:a |uma |the |an? )?(?:nova |new )?(?:pasta|folder|directory|diretorio)\s+(?:chamada\s+|called\s+|named\s+)?([\w.-]+)\s+"
                r"(?:dentro d[aeo]s?|inside(?: of)?|in|em|na|no|under)\s+(?:a pasta |the folder |my |minha )?(\S+?)" + _FIM)
    if not a:
        return None
    pai = nomes.exato(_limpar_alvo(f.g(a, 2)))
    if not pai or not os.path.isdir(pai):
        return None                      # pai que não existe ou caminho absoluto: as regras antigas
    destino = _rel(pai) + "/" + f.g(a, 1)
    return _resultado(f"mkdir -p {_q(destino)}", idioma, lugar=destino)


def _mkdir(f, idioma):
    a = f.busca(r"\b(?:cria|crie|criar|faz|faca|make|create)\s+(?:a |uma |the |an? )?(?:nova |new )?(?:pasta|folder|directory|diretorio)\s+(?:nova\s+|new\s+)?(?:chamada\s+|called\s+|named\s+)?"
                r"((?:[\w.-]+/)+[\w.-]+/?)" + _FIM)
    if not a:
        return None                      # nomes simples e caminhos absolutos ficam com as regras antigas
    caminho = f.g(a, 1).rstrip("/")
    primeiro, _, resto = caminho.partition("/")
    real = nomes.exato(primeiro)
    base = _rel(real) if real and os.path.isdir(real) else "~/" + primeiro
    destino = base + "/" + resto
    return _resultado(f"mkdir -p {_q(destino)}", idioma, lugar=destino)


def _tamanho_por_pasta(f, idioma):
    if f.busca(r"\b(cada pasta|cada diretorio|each folder|each directory|por pasta|per folder|todas as pastas|all folders|which folders?|quais pastas)\b") and \
            f.busca(r"\b(espaco|tamanho|ocupa|ocupam|pesa|pesam|size|space|big|large|takes?|uses?|maiores|biggest|largest)\b"):
        return _resultado("du -sh ~/*/ 2>/dev/null | sort -h", idioma)
    return None


def _tamanho(f, idioma):
    a = f.busca(r"\b(?:tamanho|quanto ocupa|quanto pesa|quanto espaco (?:ocupa|usa)?|how big|how large|how much space(?: does)?|size of|disk usage of)\b"
                r"(?:\s+(?:tem|e|is|does|uses))?(?:\s+(?:d[oae]|of|the))?\s+" + _ARTIGO + r"(?:pasta |folder |arquivo |file )?(\S+?)(?:\s+(?:folder|use|take|ocupa|have|has))?" + _FIM)
    if not a:
        return None
    real, nota = _fonte(f.g(a, 1))
    if not real:
        return None
    return _resultado(f"du -sh {_q(_rel(real))}", idioma, "tamanho", _rel(real), nota)


# ---------------- escrita ----------------

def _executavel(f, idioma):
    a = (f.busca(r"\b(?:torna|torne|deixa|deixe|make|marca|marque|set)\s+(.+?)\s+(?:executavel|executable|runnable)" + _FIM)
         or f.busca(r"\bpermissao de execucao\s+(?:pr[oa]|para (?:o |a )?|ao |a |no |na |em )?(.+?)" + _FIM)
         or f.busca(r"\b(?:give|add) (?:execute|exec|execution) permissions? (?:to|on|for) (.+?)" + _FIM)
         or f.busca(r"\bchmod \+x\s+(\S+)" + _FIM))
    if not a:
        return None
    real, nota = _arquivo_ou_substituto(f.g(a, 1), idioma)
    if not real:
        return nota
    return _resultado(f"chmod +x {_q(_rel(real))}", idioma, nota=nota)


def _compactar(f, idioma):
    a = f.busca(r"\b(compacta|compacte|comprime|comprima|zipa|zipe|zip|compress|archive|empacota|empacote)\s+" + _ARTIGO + r"(?:pasta |folder |arquivo |file )?(\S+?)"
                r"(?:\s+(?:num|numa|em um|em uma|em|into|to|as|no|como)\s+(?:um |an? )?(?:arquivo |file )?(\S+?\.(?:tar\.gz|tgz|zip|tar)))?" + _FIM)
    if not a:
        return None
    real, nota = _fonte(f.g(a, 2))
    if not real:
        return None
    destino = f.g(a, 3) or (os.path.basename(real) + (".zip" if a.group(1).startswith("zip") else ".tar.gz"))
    origem = _rel(real)
    if destino.endswith(".zip"):
        return _resultado(f"zip -qr {_q(destino)} {_q(origem)}", idioma, nota=nota, criou=destino)
    return _resultado(f"tar czf {_q(destino)} -C {_q(_rel(os.path.dirname(real)))} {shlex.quote(os.path.basename(real))}", idioma, nota=nota, criou=destino)


def _texto(trecho):
    return trecho.strip().strip("'\"“”‘’")


def _script(f, idioma):
    verbo = r"(imprime|imprima|mostra|mostre|escreve|escreva|diz|diga|exibe|prints?|shows?|says?|echoes|outputs?|roda|rode|executa|execute|runs?|executes?|chama|calls?)"
    a = f.busca(r"\b(?:cria|crie|criar|faz|faca|make|create|put|coloca|coloque|poe|ponha|escreve|escreva|write)\s+(?:(?:in|inside|into|em|na|no|dentro d[aeo])\s+(\S+)\s+)?"
                r"(?:um |uma |o |a |an? |the )?(?:script |arquivo |file |programa |program )?(?:chamado |called |named )?(\S+?\.(?:sh|py))"
                r"(?:\s+(?:in|inside|into|em|na|no|dentro d[aeo])\s+(\S+))?\s+(?:que|that|which|to)\s+" + verbo + r"\s+(.+?)" + _FIM)
    if not a:
        return None
    nome, pasta = f.g(a, 2), f.g(a, 1) or f.g(a, 3)
    if pasta and pasta not in ("it", "ela"):
        real = nomes.exato(pasta)
        nome = os.path.join(_rel(real) if real else pasta, nome)
    acao, resto = a.group(4), _texto(f.g(a, 5))
    roda = acao.startswith(("roda", "rode", "executa", "execute", "run", "chama", "call"))
    if nome.endswith(".py"):
        corpo = f"import subprocess\nsubprocess.run({resto!r}, shell=True)\n" if roda else f"print({resto!r})\n"
        conteudo = "#!/usr/bin/env python3\n" + corpo
    else:
        conteudo = "#!/bin/sh\n" + (resto if roda else f"echo {shlex.quote(resto)}") + "\n"
    return _resultado(f"printf '%s' {shlex.quote(conteudo)} > {_q(nome)} && chmod +x {_q(nome)}", idioma, criou=nome)


def _criar_com_texto(f, idioma):
    a = f.busca(r"\b(?:cria|crie|criar|faz|faca|make|create|escreve|escreva|write)\s+(?:um |o |a |an? |the )?(?:novo |nova |new )?(?:arquivo |file |nota |note )?"
                r"(?:chamado |called |named )?(\S+?\.[a-z0-9]{1,6})\s+(?:com o texto|com|with the text|with|escrito|escrita|dizendo|contendo|saying|that says|containing)\s*:?\s+(.+)$")
    if not a:
        return None
    destino = f.g(a, 1)
    dono = os.path.dirname(destino)
    if dono and not os.path.isdir(os.path.expanduser(dono)):
        real = nomes.exato(dono)
        if real:
            destino = os.path.join(_rel(real), os.path.basename(destino))
    valor = _DINAMICO.get(re.sub(r"^(?:a |o |the )", "", f.n[a.start(2):a.end(2)].strip(" .'\"")))
    if valor:                            # "com a data de hoje" quer a data, não as palavras
        return _resultado(f"{valor} > {_q(destino)}", idioma, criou=destino)
    return _resultado(f"printf '%s\\n' {shlex.quote(_texto(f.g(a, 2)))} > {_q(destino)}", idioma, criou=destino)


_DINAMICO = {"data de hoje": "date '+%d/%m/%Y'", "data": "date '+%d/%m/%Y'", "data atual": "date '+%d/%m/%Y'", "today's date": "date +%F", "todays date": "date +%F",
             "date": "date +%F", "current date": "date +%F", "hora": "date +%H:%M", "hora atual": "date +%H:%M", "time": "date +%H:%M", "current time": "date +%H:%M",
             "data e hora": "date '+%d/%m/%Y %H:%M'", "date and time": "date '+%F %H:%M'", "meu ip": "hostname -I", "ip": "hostname -I", "my ip": "hostname -I"}


def _acrescentar(f, idioma):
    a = f.busca(r"\b(?:adiciona|adicione|acrescenta|acrescente|coloca|coloque|poe|ponha|append|add|insere|insira|escreve|escreva|write|put)\s+(?:a linha |uma linha |the line |a line |o texto |the text )?"
                r"(.+?)\s+(?:no fim d[eoa]|no final d[eoa]|ao final d[eoa]|ao fim d[eoa]|at the end of|to the end of|to|into|em|no|na)\s+" + _ARTIGO + r"(?:arquivo |file )?(\S+?)" + _FIM)
    if not a:
        return None
    real, nota = _fonte(f.g(a, 2), arquivo=True)
    if not real:
        return None              # arquivo novo: é com "cria" ou com o modelo
    return _resultado(f"printf '%s\\n' {shlex.quote(_texto(f.g(a, 1)))} >> {_q(_rel(real))}", idioma, nota=nota)


def _destino(texto):
    """(caminho do destino, é pasta?) a partir do que vem depois de "para"."""
    pasta = bool(re.match(r"^\s*" + _PASTA, texto, re.IGNORECASE)) or bool(re.search(r"\b(pasta|folder|diretorio|directory)$", texto.strip(), re.IGNORECASE))
    alvo = re.sub(r"\s+(?:pasta|folder|diretorio|directory)$", "", _limpar_alvo(texto), flags=re.IGNORECASE)
    real = nomes.exato(alvo)
    if real and os.path.isdir(real):
        return _rel(real), True
    if not pasta and not re.search(r"\.[a-z0-9]{1,6}$", alvo) and not re.search(r"[/~]", alvo):
        pasta = bool(re.match(r"^[A-Z]", alvo))         # "para Imagens": nome próprio de pasta
    return alvo, pasta


def _copiar_mover(f, idioma):
    a = f.busca(r"\b(copia|copie|copiar|copy|move|mova|mover|leva|leve)\s+(?:todas as |todos os |all (?:the )?|as |os |the |minhas |meus |my )?"
                r"(?:(fotos|imagens|photos|pictures|images|videos|musicas|music|pdfs)(?:\s+\*?\.([a-z0-9]{2,5}))?|(?:arquivos\s+|files\s+)?\*?\.([a-z0-9]{2,5})(?:\s+(?:files|arquivos|fotos))?)"
                + _DE + r"(?:a pasta |pasta |the folder |my |minha )?(\S+?)\s+(?:para|pra|pro|to|into|em)\s+(.+?)" + _FIM)
    if a:
        origem, nota = _fonte(f.g(a, 5), pasta=True)
        if not origem:
            return None
        extensao = a.group(3) or a.group(4)
        extensoes = (extensao,) if extensao else TIPOS[a.group(2)]
        presentes = [e for e in extensoes if any(n.lower().endswith("." + e) for n in os.listdir(origem))]
        if not presentes:
            return {"fala": t("nenhum_tipo", idioma, pasta=_rel(origem))}
        destino, _ = _destino(f.g(a, 6))
        programa = "mv" if a.group(1).startswith(("mov", "mova", "lev")) else "cp"
        globs = " ".join(f"{_q(_rel(origem))}/*.{e}" for e in presentes)
        return _resultado(f"mkdir -p {_q(destino)} && {programa} {globs} {_q(destino)}/", idioma, nota=nota, lugar=destino)
    a = f.busca(r"\b(copia|copie|copiar|copy|move|mova|mover|leva|leve|duplica|duplique|duplicate|fa[zc]a? uma copia d[eoa]s?|make a copy of)\s+" + _ARTIGO
                + r"(?:arquivo |pasta |file |folder )?(\S+?)\s+(?:para|pra|pro|to|into|em|como|as|com o nome|named|called|chamad[ao])\s+(.+?)" + _FIM)
    if not a:
        return None
    if re.match(r"(dupl|faz uma|faca uma|fa uma|make a)", a.group(1)) or re.search(r"\s(como|as|com o nome|named|called|chamad[ao])\s", f.n[a.end(2):a.start(3) + 1]):
        origem, nota = _fonte(f.g(a, 2))
        if not origem:
            return None
        destino = _limpar_alvo(f.g(a, 3))
        if "/" not in destino:                 # a cópia fica ao lado do original
            destino = os.path.join(os.path.dirname(_rel(origem)), destino)
        return _resultado(f"cp -r {_q(_rel(origem))} {_q(destino)}", idioma, nota=nota)
    origem, nota = _fonte(f.g(a, 2))
    if not origem:
        return None                # nome que não existe: as regras antigas mostram o erro de verdade
    destino, pasta = _destino(f.g(a, 3))
    programa = "mv" if a.group(1).startswith(("mov", "mova", "lev")) else "cp -r"
    if pasta:
        criar = "" if os.path.isdir(os.path.expanduser(destino)) else f"mkdir -p {_q(destino)} && "
        return _resultado(f"{criar}{programa} {_q(_rel(origem))} {_q(destino)}/", idioma, nota=nota, lugar=destino)
    return _resultado(f"{programa} {_q(_rel(origem))} {_q(destino)}", idioma, nota=nota)


def _renomear(f, idioma):
    a = f.busca(r"\b(?:renomeia|renomeie|renomear|rename|muda o nome d[aeo])\s+" + _ARTIGO + r"(?:arquivo |pasta |file |folder )?(\S+?)\s+(?:para|pra|to|as|como)\s+(\S+?)" + _FIM)
    if not a:
        return None
    origem, nota = _fonte(f.g(a, 1))
    if not origem:
        return None
    destino = f.g(a, 2)
    if "/" not in destino:                 # renomear fica na mesma pasta
        destino = os.path.join(os.path.dirname(_rel(origem)), destino)
    return _resultado(f"mv {_q(_rel(origem))} {_q(destino)}", idioma, nota=nota)


def _apagar_parecido(f, idioma):
    """Apagar com o nome errado não corrige sozinho: pergunta se é o parecido."""
    a = f.busca(r"^(?:por favor |please )?(?:apaga|apague|apagar|deleta|delete|remove|remova|exclui|exclua)\s+" + _ARTIGO + r"(?:arquivo |pasta |file |folder )?(\S+?)"
                r"(?:\s+(?:inteir[ao]|tod[ao]|entire|whole|completely|folder|pasta))?" + _FIM)
    if not a:
        return None
    real = nomes.exato(_limpar_alvo(f.g(a, 1)))
    if real:                    # "apaga a pasta projetos inteira": o caminho real; rm -r pede a confirmação do app
        return _resultado(("rm -r " if os.path.isdir(real) else "rm ") + _q(_rel(real)), idioma)
    sugestoes = nomes.parecidos(_limpar_alvo(f.g(a, 1)))
    if not sugestoes:
        return None
    return {"fala": t("apagar_parecido", idioma, nome=_limpar_alvo(f.g(a, 1)), real=_rel(sugestoes[0]))}


def _descompactar(f, idioma):
    a = f.busca(r"\b(?:descompacta|descompacte|descompactar|extrai|extraia|extrair|extract|unzip|untar|unpack|abre o zip|abra o zip)\s+" + _ARTIGO + r"(?:arquivo |file )?(\S+?\.(?:tar\.gz|tgz|tar|zip|tar\.xz|tar\.bz2))"
                r"(?:\s+(?:em|na|no|numa|num|para|pra|into|to|in)\s+(?:a |uma |the |an? )?(?:nova |new )?(?:pasta |folder |diretorio |directory )?(?:chamada |called |named )?(\S+?))?" + _FIM)
    if not a:
        return None
    real, nota = _arquivo_ou_substituto(f.g(a, 1), idioma)
    if not real:
        return nota
    destino = f.g(a, 2) or "."
    origem = _q(_rel(real))
    extrair = f"unzip -q {origem} -d {_q(destino)}" if real.endswith(".zip") else f"tar xf {origem} -C {_q(destino)}"
    return _resultado((f"mkdir -p {_q(destino)} && " if destino != "." else "") + extrair, idioma, nota=nota, lugar=destino if destino != "." else None)


def _trocar(f, idioma):
    a = f.busca(r"\b(?:troca|troque|trocar|substitui|substitua|substituir|replace|change|muda|mude)\s+(?:a palavra |o texto |the word |the text |todas as ocorrencias de |all )?[\"']?(.+?)[\"']?\s+"
                r"(?:por|pelo|pela|with|to|by|para)\s+[\"']?(.+?)[\"']?\s+(?:no|na|em|in|dentro d[oae])\s+" + _ARTIGO + r"(?:arquivo |file )?(\S+?)" + _FIM)
    if not a:
        return None
    real, nota = _fonte(f.g(a, 3), arquivo=True)
    if not real:
        return _nao_achei(f.g(a, 3), idioma)
    escapar = lambda texto: re.sub(r"([/\\&.*\[\]^$])", r"\\\1", texto)    # noqa: E731
    return _resultado(f"sed -i {shlex.quote('s/' + escapar(f.g(a, 1)) + '/' + escapar(f.g(a, 2)) + '/g')} {_q(_rel(real))}", idioma, nota=nota)


_UNIDADE_TEMPO = {"minuto": ("mmin", 1), "minutos": ("mmin", 1), "minute": ("mmin", 1), "minutes": ("mmin", 1), "hora": ("mmin", 60), "horas": ("mmin", 60),
                  "hour": ("mmin", 60), "hours": ("mmin", 60), "dia": ("mtime", 1), "dias": ("mtime", 1), "day": ("mtime", 1), "days": ("mtime", 1),
                  "semana": ("mtime", 7), "semanas": ("mtime", 7), "week": ("mtime", 7), "weeks": ("mtime", 7)}


def _recentes(f, idioma):
    a = f.busca(r"\b(?:arquivos|files)\s+(?:que (?:foram |eu )?|eu |i |that i |i've |ive )?(?:modificad[oa]s|alterad[oa]s|mudad[oa]s|editad[oa]s|criad[oa]s|mexid[oa]s|"
                r"mexi|editei|alterei|modifiquei|criei|mudei|modified|changed|edited|created|touched)\b"
                r"(?:.{0,20}?\b(?:(\d+)\s+)?(minutos?|horas?|dias?|semanas?|minutes?|hours?|days?|weeks?)\b|.{0,20}?\b(hoje|today|ontem|yesterday)\b)?")
    if not a:
        return None
    if a.group(3) in ("ontem", "yesterday"):
        teste = "-mtime -2"
    elif a.group(2):
        tipo, fator = _UNIDADE_TEMPO[a.group(2)]
        teste = f"-{tipo} -{int(a.group(1) or 1) * fator}"
    else:
        teste = "-mtime -1"                       # "hoje" e o padrão: as últimas 24 horas
    return _resultado(f"find ~ -type f {teste} -not -path '*/.*' 2>/dev/null | head -50", idioma, "achados", "~")


_LINGUAGENS = {"python": "py", "javascript": "js", "typescript": "ts", "shell": "sh", "bash": "sh", "c": "c", "c++": "cpp", "java": "java", "go": "go", "rust": "rs", "html": "html", "css": "css"}


def _linhas_de_codigo(f, idioma):
    a = f.busca(r"\b(?:linhas de codigo|lines of code|loc)\b(?:\s+(?:em |de |in |of )?(python|javascript|typescript|shell|bash|c\+\+|java|go|rust|html|css|c))?.{0,25}?(?:" + _DE + r"(?:a pasta |pasta |the folder |my )?(\S+?))?" + _FIM)
    if not a:
        return None
    linguagem = a.group(1) or (re.search(r"\b(python|javascript|typescript|shell|bash|java|rust|html|css)\b", f.n) or [None, None])[1] or "python"
    pasta = nomes.casa()
    nota = None
    if a.group(2):
        pasta, nota = _fonte(f.g(a, 2), pasta=True)
        if not pasta:
            return None
    return _resultado(f"find {_q(_rel(pasta))} -name '*.{_LINGUAGENS[linguagem]}' -not -path '*/.*' -print0 | wc -l --files0-from=- | tail -n 1", idioma, "loc", _rel(pasta), nota)


_COMO_VERSAO = {"python": "python3", "pip": "pip3", "node": "node", "nodejs": "node"}


def _versao(f, idioma):
    a = f.busca(r"\b(?:versao|version)\s+(?:d[oae] |of (?:the )?|of my )?(?:programa |the )?([a-z][\w.+-]*)") or f.busca(r"\b([a-z][\w.+-]*)\s+version\b")
    if not a or a.group(1) in ("kernel", "linux", "sistema", "system", "os", "do", "of", "the", "which", "what", "qual", "my", "minha", "nova", "new", "latest"):
        return None
    programa = _COMO_VERSAO.get(a.group(1), a.group(1))
    if not shutil.which(programa):
        return {"fala": t("nao_instalado", idioma, programa=a.group(1), pacote=a.group(1))}
    return _resultado(f"{programa} --version 2>&1 | head -n 1", idioma)


def _gpio(f, idioma):
    if f.busca(r"\b(pinos|pins|gpio|chips? de gpio|gpio chips?)\b") and f.busca(r"\b(quais|lista|liste|list|which|what|existem|mostra|show|tem)\b") \
            and not f.busca(r"\b(p[a-k]\d{1,2}|gpio ?\d{1,3})\b"):
        return _resultado("gpioinfo" if shutil.which("gpioinfo") else "ls -l /dev/gpiochip*", idioma)
    return None


OPERACOES = (_gpio, _versao, _descompactar, _trocar, _recentes, _linhas_de_codigo, _ocorrencias, _contar_linhas, _contar_arquivos, _qual_arquivo, _maior_menor, _so_pastas, _escondidos, _linhas_com, _acrescentar, _ultimas, _por_extensao, _tamanho_por_pasta, _tamanho,
             _mkdir_dentro, _mkdir, _executavel, _compactar, _script, _criar_com_texto, _copiar_mover, _renomear, _apagar_parecido, _ver)


def plano(pedido, n, idioma="pt"):
    f = Frase(pedido, n)
    for operacao in OPERACOES:
        r = operacao(f, idioma)
        if r:
            return r
    return None


# ---------------- a resposta em palavras ----------------

def resumir(plano_, resultado, idioma):
    """Uma frase com o que a saída quer dizer, ou None quando a saída já fala por si."""
    chave, alvo = plano_.get("resumo"), plano_.get("alvo")
    saida = (resultado.get("stdout") or "").strip()
    linhas = [l for l in saida.splitlines() if l.strip()]
    if chave == "linhas" and saida.split()[:1] and saida.split()[0].isdigit():
        return t("r_linhas", idioma, n=int(saida.split()[0]), alvo=alvo)
    if chave == "ocorrencias":
        n = int(saida) if saida.isdigit() else 0
        return t("r_ocorrencias", idioma, n=n, termo=plano_.get("termo"), alvo=alvo)
    if chave == "contar_arquivos" and saida.isdigit():
        return t("r_arquivos", idioma, n=int(saida), alvo=alvo)
    if chave == "arquivos_com":
        if not linhas:
            return t("r_nenhum_arquivo", idioma, termo=plano_.get("termo"))
        return t("r_esta_em", idioma, lista=", ".join(nomes.bonito(l) for l in linhas[:5]))
    if chave in ("maior", "menor") and linhas:
        partes = linhas[0].split(None, 8)
        if len(partes) >= 9:
            return (t("r_maior", idioma, nome=partes[8], tamanho=partes[4], alvo=alvo) if chave == "maior" else t("r_menor", idioma, nome=partes[8], tamanho=partes[4], alvo=alvo))
    if chave == "loc":
        numero = re.match(r"\s*(\d+)", saida)
        return t("r_loc", idioma, n=int(numero.group(1)), alvo=alvo) if numero else None
    if chave == "achados":
        return t("r_achados", idioma, n=len(linhas), alvo=alvo) if linhas else t("r_nada_achado", idioma, alvo=alvo)
    if chave == "tamanho" and linhas:
        return t("r_tamanho", idioma, tamanho=linhas[0].split()[0], alvo=alvo)
    return None
