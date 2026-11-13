"""Perguntas sobre o mundo respondidas pelos resultados do SearXNG da pessoa, sem o modelo (F4 do PLANO_5.3.md, 07/11).

Veio do openTARS Pi: separa o assunto da relação ("Guernica" e "pintou"), procura de dois jeitos e escolhe a frase que tem o tipo
de resposta que a pergunta quer (nome, ano, medida, lugar). Medido em 07/11 no app: "quem escreveu Grande Sertão: Veredas?" saía
"Jorge Amado" de memória. Aqui a resposta é a frase de um resultado, com o site; sem resultado bom, devolve None e o modelo segue."""
import html
import re
import unicodedata
import urllib.parse

import tars_web



def _limpar(texto):
    texto = re.sub(r"\[(?:nota |note )?\d+\]", "", texto)                  # marcas de nota da Wikipédia: "[1]", "[nota 1]"
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", texto)).split())


_VAZIAS = set("o a os as um uma uns umas de do da dos das no na nos nas em que qual quais quem como onde quando quanto quanta quantos quantas e é foi são "
              "era por para pra sobre me explica explique explicar diga fala the of what whats which who whom how where when why is are was were do does did "
              "an in on at for to it its explain tell define please my mine i eu meu minha meus minhas you voce você".split())


def chaves(texto):
    """As palavras que importam: 'what is the' na busca da Wikipédia trazia 'What Is a Nation?' (medido na placa, 06/11)."""
    return [p for p in re.findall(r"\w+", texto.lower()) if p not in _VAZIAS and (len(p) > 1 or p.isdigit())]


def raizes(texto):
    """As chaves cortadas em 5 letras: "descobriu" acha "descoberta", "invented" acha "invention"."""
    return {p[:5] for p in chaves(texto)}


# O que a pergunta quer de volta. Escolher a frase pelo tipo da resposta acerta mais que só contar palavras:
# "quem pintou Guernica" quer um nome, "quando acabou a guerra" quer um ano (prova de capacidade, 07/11).
_TIPOS = (("ano", r"\b(em que ano|que ano|qual ano|quando|when|what year|which year|in what year)\b"),
          ("medida", r"\b(altura|alto|alta|tall|height|high|comprimento|length|long|distancia|distance|far|longe|peso|weight|profundidade|deep|depth|area)\b"),
          ("numero", r"\b(quantos|quantas|how many|how much|populacao|population)\b"),
          ("nome", r"\bcapital\b|\b(qual|what|which|quem|who)\b.{0,12}\b(maior|menor|mais|largest|biggest|smallest|longest|highest|tallest|first|primeir[oa]|extenso)\b"),
          ("definicao", r"^(quem foi|quem e|who was|who is|who were|o que e|o que sao|what is|what are|what was|define|defina)\b"),
          ("nome", r"^(quem|who|whom)\b"),
          ("lugar", r"^(onde|where)\b"))
_PADRAO_TIPO = {
    "ano": r"\b(1[0-9]{3}|20[0-9]{2})\b",
    "medida": r"\d[\d.,\s\u00a0]*\s?(m|metros|metres|meters|km|quil[oô]metros|kilometres|kilometers|ft|feet|p[eé]s|mi|miles|milhas|kg|toneladas|tonnes)\b",
    "numero": r"\d",
}
# Relações comuns e as raízes que aparecem no texto (o verbo da pergunta raramente é o da frase: "wrote" e "written").
_RELACOES = (({"pintou", "pintado", "pintor", "painted", "painter", "painting", "pintura", "quadro"}, {"pint", "pain", "quad"}),
             ({"escreveu", "escrito", "escritor", "autor", "wrote", "written", "writer", "author", "write"}, {"escr", "writ", "wrot", "auto", "auth", "nove", "roma"}),
             ({"descobriu", "descoberta", "descobridor", "discovered", "discovery", "discoverer"}, {"desc", "disc", "cheg"}),
             ({"inventou", "invencao", "inventor", "invented", "invention"}, {"inve", "pate"}),
             ({"fundou", "fundada", "fundado", "fundador", "founded", "founder"}, {"fund", "foun"}),
             ({"nasceu", "nascimento", "born", "birth"}, {"nasc", "born", "birt"}),
             ({"morreu", "morte", "died", "death", "die"}, {"morr", "mort", "died", "deat"}),
             ({"terminou", "acabou", "fim", "end", "ended", "ending"}, {"term", "acab", "fim", "end", "ende"}),
             ({"comecou", "inicio", "began", "start", "started", "begin"}, {"come", "inic", "bega", "star"}),
             ({"pisou", "pousou", "chegou", "walked", "landed", "landing"}, {"pis", "pous", "cheg", "walk", "land", "aterr"}),
             ({"caiu", "queda", "fell", "fall"}, {"cai", "qued", "fell", "fall", "derr"}),
             ({"maior", "largest", "biggest"}, {"maior", "larg", "bigg"}), ({"menor", "smallest"}, {"menor", "smal"}),
             ({"extenso", "longest", "comprido"}, {"exte", "long", "compr"}),
             ({"capital"}, {"capital"}), ({"altura", "tall", "height", "alta", "alto", "high"}, {"altu", "tall", "heig", "metr", "high", "alt"}))
_SO_DA_PERGUNTA = {"ano", "year", "quando", "when", "vez", "pela", "time", "mais", "most", "fica", "ficam", "located", "localizada", "localizado",
                   "situada", "situado", "esta", "está"}
_INICIO_PERGUNTA = re.compile(r"^(?:quem|qual|quais|quando|onde|como|o que|em que ano|que ano|who|what|which|when|where|how|why|did|does|do|is|are|was|were)"
                              r"(?:\s+(?:e|é|foi|era|são|sao|is|was|are|were|did|does|do|the|a|o|os|as))*\s+", re.IGNORECASE)
_ROMANOS = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5"}
_MAIUSCULAS_COMUNS = {"the", "it", "its", "in", "a", "an", "o", "os", "as", "em", "no", "na", "este", "esta", "this", "he", "she", "ele", "ela", "segundo",
                      "according", "also", "however", "during", "durante", "after", "depois", "before", "antes"}


def tipo_de_resposta(consulta):
    n = "".join(c for c in unicodedata.normalize("NFKD", consulta) if not unicodedata.combining(c)).lower().strip()
    return next((tipo for tipo, padrao in _TIPOS if re.search(padrao, n)), None)


class _Grupos(frozenset):
    """As raízes de cada relação da pergunta: um grupo conta uma vez só, por mais sinônimos que a frase tenha."""
    def __new__(cls, grupos):
        objeto = super().__new__(cls, [r for g in grupos for r in g])
        objeto.grupos = list(grupos)
        return objeto


def _relacao(palavras):
    """(palavras que são a relação, raízes que a frase deve ter, agrupadas por relação)."""
    usadas, grupos = set(), []
    for formas, alvo in _RELACOES:
        achadas = formas & set(palavras)
        if achadas:
            usadas |= achadas
            grupos.append(frozenset(alvo))
    return usadas, _Grupos(grupos)


def _r4(texto):
    return {_ROMANOS.get(p, p)[:4] for p in chaves(texto)}


_INTERVALO = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\)?\s*[–-]\s*(?:\d{1,2}\s+\w+\s+)?(1[0-9]{3}|20[0-9]{2})\b")


_SUPERLATIVOS = {"maior", "larg", "bigg", "menor", "smal", "exte", "long", "compr"}


def _tem_relacao(frase, raizes_rel, titulo="", assunto4=frozenset()):
    """Quantas raízes da relação a frase tem, sem contar as que só repetem o título ("Discover America" não descobriu nada)."""
    do_titulo = set(chaves(titulo))
    tokens = re.findall(r"[\wÀ-ú'-]+", frase)
    minusculas = " ".join(p for i, p in enumerate(tokens) if i == 0 or not p[:1].isupper())     # "Murder, She Wrote" é nome, não "escreveu"
    palavras = [p for p in chaves(minusculas) if p not in do_titulo]
    grupos = getattr(raizes_rel, "grupos", [frozenset([r]) for r in raizes_rel])
    achadas = 0
    for grupo in grupos:
        if grupo & _SUPERLATIVOS:        # "maior" só conta colado no assunto: "o maior oceano", não "a maior parte"
            achadas += any(p.startswith(r) and i + 1 < len(palavras) and any(q[:4] in assunto4 for q in palavras[i + 1:i + 3])
                           for r in grupo for i, p in enumerate(palavras))
        else:
            achadas += any(p.startswith(r) for r in grupo for p in palavras)
    if not achadas and raizes_rel & {"term", "end", "come", "star", "cai", "qued"} and _INTERVALO.search(frase):
        achadas = 1                      # "(1939 – 1945)": o intervalo diz quando começou e quando acabou
    return achadas


def nomes_novos(frase, pergunta):
    """Nomes próprios da frase que não estão na pergunta (a primeira palavra da frase não conta: é maiúscula por ser a primeira)."""
    ja = {p[:4] for p in chaves(pergunta)}
    tokens = re.findall(r"[\wÀ-ú'-]+", frase)
    return [p for p in tokens[1:] if p[:1].isupper() and p.lower() not in _MAIUSCULAS_COMUNS and p.lower()[:4] not in ja and not p.isupper()]


def _titulo_e_outro_nome(titulo, consulta):
    """O título é um nome que a pergunta não tem (Júpiter para "maior planeta"), e não o próprio assunto ("Lista de planetas")."""
    do_titulo, da_pergunta = _r4(titulo), _r4(consulta)
    return bool(titulo) and not (do_titulo & da_pergunta) and titulo[:1].isupper()


def _nota_da_frase(frase, consulta, tipo, raizes_rel, assunto, titulo=""):
    """(nota, responde?). Responde quando tem o tipo de resposta que a pergunta quer junto com a relação pedida."""
    rel = _tem_relacao(frase, raizes_rel, titulo, {_ROMANOS.get(p, p)[:4] for p in chaves(consulta)})
    if rel and re.search(r"\b(segund[oa]|terceir[oa]|quart[oa]|second|third|fourth)\s+(maior|menor|mais|largest|biggest|smallest|longest|highest)\b", frase.lower()):
        rel -= 1                         # "o segundo maior planeta anão" não é o maior
    nota = len(_r4(frase) & {_ROMANOS.get(p, p)[:4] for p in assunto}) + 2 * rel
    tem_tipo = False
    if tipo == "nome":                   # o nome novo pode ser o próprio título: "Júpiter é o maior planeta"
        novo = nomes_novos(frase, consulta) or _titulo_e_outro_nome(titulo, consulta)
        tem_tipo = bool(novo) and (rel or not raizes_rel)
    elif tipo in _PADRAO_TIPO:
        tem_tipo = bool(re.search(_PADRAO_TIPO[tipo], frase, re.IGNORECASE)) and (rel or not raizes_rel)
    if tem_tipo:
        nota += 3
    if tipo in ("nome", "lugar") and re.search(r"\b(maior|menor|largest|biggest|smallest|longest|mais extenso)\s+(\w+)", frase.lower()):
        nota += 2 * any(p[:4] in {a[:4] for a in assunto} for p in re.findall(r"\b(?:maior|menor|largest|biggest|smallest|longest|extenso)\s+(\w+)", frase.lower()))
    return nota, bool(tem_tipo or (rel and tipo is None))


def melhor_frase(texto, consulta, assunto=""):
    """A frase do resumo que melhor responde: a que tem a relação e o tipo de resposta que a pergunta pede.
    As palavras do título não contam: na página France, quem responde "capital of France" é a frase que fala de capital."""
    frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ú])", texto) if f.strip()]
    if not frases:
        return ""
    palavras = chaves(consulta)
    usadas, raizes_rel = _relacao(palavras)
    resto = [p for p in palavras if p not in usadas and p not in _SO_DA_PERGUNTA]
    procura = set(resto) - set(chaves(assunto)) or set(resto)
    tipo = tipo_de_resposta(consulta)
    return max(frases, key=lambda f: (_nota_da_frase(f, consulta, tipo, raizes_rel, procura, assunto)[0], -frases.index(f)))


def responder(consulta, buscar=None):
    """{'trecho', 'titulo', 'url'} da frase que responde, ou None (sem SearXNG, sem resultado ou sem frase que responda)."""
    buscar = buscar or tars_web.buscar
    palavras = list(dict.fromkeys(chaves(consulta))) or consulta.split()
    usadas, raizes_rel = _relacao(palavras)
    assunto = [p for p in palavras if p not in usadas and p not in _SO_DA_PERGUNTA] or palavras
    tipo = tipo_de_resposta(consulta)
    natural = _INICIO_PERGUNTA.sub("", consulta.strip(" ?!.")).strip() or consulta
    resultados, vistos = [], set()
    for q in dict.fromkeys([natural, " ".join(assunto)]):
        try:
            achados = buscar(q)
        except (OSError, ValueError):
            achados = []
        for r in achados:
            if r.get("url") not in vistos:
                vistos.add(r.get("url"))
                resultados.append(r)
    melhor = None
    for ordem, r in enumerate(resultados[:12]):
        titulo = re.sub(r"\s*[-–|].*$", "", r.get("titulo", ""))          # "Guernica – Wikipédia" vira "Guernica"
        frase = melhor_frase(_limpar(r.get("trecho", "")), consulta, titulo)
        if not frase:
            continue
        do_titulo = _r4(titulo)
        cobre = len(do_titulo & {_ROMANOS.get(p, p)[:4] for p in assunto})
        nota_frase, responde = _nota_da_frase(frase, consulta, tipo, raizes_rel, [p for p in assunto if p[:4] not in do_titulo], titulo)
        if tipo in ("definicao", "lugar"):
            responde = cobre >= max(1, len(assunto) - (tipo == "definicao"))
        nota = 3 * cobre + nota_frase + (4 if responde else 0) - 0.2 * ordem
        if responde and (melhor is None or nota > melhor[0]):
            melhor = (nota, {"trecho": _recorte(frase, raizes_rel), "titulo": r.get("titulo", ""), "url": r.get("url", "")})
    return melhor[1] if melhor else None


def _recorte(frase, raizes_rel, tamanho=300):
    """A frase inteira se couber; senão o pedaço em volta da relação, que é onde a resposta costuma estar."""
    if len(frase) <= tamanho:
        return frase
    minusculas = frase.lower()
    posicoes = [m.start() for r in raizes_rel for m in re.finditer(r"\b" + re.escape(r), minusculas)]
    if not posicoes or min(posicoes) < tamanho - 80:
        return frase[:tamanho - 1].rsplit(" ", 1)[0] + "…"
    inicio = max(0, min(posicoes) - 120)
    return "…" + frase[inicio:inicio + tamanho - 2].split(" ", 1)[-1].rsplit(" ", 1)[0] + "…"
