"""openTARS: memória (preferências que a pessoa pediu pra lembrar).

Memória = frases curtas ("meu navegador é o Brave", "a pasta de projetos
é ~/dev"). Vão no prompt de todo pedido. Ficam em
~/.config/opentars/memoria.json. (Endurance Neo: as rotinas agendadas
saíram; até a 4.0 este arquivo era o tars_rotinas.py.)"""

import datetime as dt
import json
import os
import re
import threading
import time
import unicodedata
from pathlib import Path

import tars_plataforma as plataforma


def pasta_config():
    return plataforma.pastas()["config"]


def guardar_quebrado(caminho):
    """Arquivo que não abre como JSON: guarda uma cópia (.corrompido) antes que o próximo salvamento o sobrescreva."""
    try:
        os.replace(caminho, str(caminho) + ".corrompido")
    except OSError:
        pass


def _ler(caminho, padrao):
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except OSError:
        return padrao
    except ValueError:
        guardar_quebrado(caminho)
        return padrao


def gravar_texto_atomico(caminho, texto, modo=0o600):
    """Escreve num arquivo temporário ÚNICO (0600) na mesma pasta, fsync e rename: duas gravações ao mesmo tempo
    não se misturam e uma queda no meio não deixa o arquivo pela metade."""
    import tempfile
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    fd, temporario = tempfile.mkstemp(prefix="." + caminho.name + ".", suffix=".tmp", dir=str(caminho.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temporario, modo)
        for tentativa in range(50):
            try:
                os.replace(temporario, caminho)
                break
            except PermissionError:      # Windows: alguém lendo o arquivo agora bloqueia a troca por um instante
                if os.name != "nt" or tentativa == 49:
                    raise
                time.sleep(0.02)
    except BaseException:
        try:
            os.unlink(temporario)
        except OSError:
            pass
        raise


def _gravar(caminho, dados):
    gravar_texto_atomico(caminho, json.dumps(dados, ensure_ascii=False, indent=1))


def _normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto or "").lower())
    return " ".join("".join(c for c in texto if not unicodedata.combining(c)).split())


LIMITE_MEMORIAS = 40
LIMITE_CHARS_MEMORIA = 200


class Memoria:
    def __init__(self, caminho=None, agora=None):
        self.caminho = Path(caminho or pasta_config() / "memoria.json")
        self.agora = agora or dt.datetime.now
        self._trava = threading.Lock()

    def listar(self):
        return [m["texto"] for m in _ler(self.caminho, []) if isinstance(m, dict) and m.get("texto")]

    def lembrar(self, texto):
        """Guarda (ou atualiza, se já houver uma parecida). Devolve (ok, erro)."""
        texto = " ".join(str(texto or "").split())
        if not texto:
            return False, "empty"
        if len(texto) > LIMITE_CHARS_MEMORIA:
            return False, f"too long (max {LIMITE_CHARS_MEMORIA} characters): keep it short"
        with self._trava:
            itens = [m for m in _ler(self.caminho, []) if isinstance(m, dict) and m.get("texto")]
            chave = _normalizar(texto)
            itens = [m for m in itens if _normalizar(m["texto"]) != chave]
            itens.append({"texto": texto, "quando": self.agora().isoformat(timespec="seconds")})
            _gravar(self.caminho, itens[-LIMITE_MEMORIAS:])
        return True, None

    def esquecer(self, alvo):
        """Tira as memórias que contêm 'alvo' (ou todas com '*'). Devolve as tiradas."""
        chave = _normalizar(alvo)
        if not chave:
            return []
        with self._trava:
            itens = [m for m in _ler(self.caminho, []) if isinstance(m, dict) and m.get("texto")]
            fora = [m["texto"] for m in itens if chave == "*" or chave in _normalizar(m["texto"])]
            if fora:
                _gravar(self.caminho, [m for m in itens if m["texto"] not in fora])
        return fora

    def para_prompt(self):
        itens = self.listar()
        if not itens:
            return ""
        linhas = "\n".join(f"- {x}" for x in itens)
        return ("\nWHAT THE USER ASKED YOU TO REMEMBER (use it: e.g. their browser, folders, names; "
                "don't ask again what is here):\n" + linhas + "\n")


# ------------------------------------------------------------
# O pedido fala de lembrar/esquecer? (aí a IA ganha essas ferramentas)
# ------------------------------------------------------------
_RE_MEMORIA = re.compile(
    r"\b(lembr(?!ete)\w*|memoriz\w*|esquec\w*|remember\w*|memori[sz]e\w*|forget\w*|recuerd\w*|olvid\w*|"
    r"souvien\w*|retien\w*|oubli\w*|merk\w*|vergiss\w*|erinner\w*|what do you know about me|"
    r"o que (voce )?sabe (sobre|de) mim|"
    # "keep in memory", "save it to memory", "na memória", "salve na memoria" (a palavra memória em si já pede a ferramenta)
    r"memor(?:y|ies|ia|ias)|memoire|speicher\w*|"
    r"keep in mind|bear in mind|note (?:that|this|down)|from now on|"
    r"tenha em mente|de agora em diante|daqui pra frente|anote?\w* que|guard[ae]\w* (?:que|isso|essa|esse))\b")


def fala_de_memoria(texto):
    return bool(_RE_MEMORIA.search(_normalizar(texto))) or intencao_de_lembrar(texto) is not None


# ------------------------------------------------------------
# O pedido MANDA salvar uma coisa? (aí o openTARS salva, mesmo que o modelo não chame a ferramenta)
# ------------------------------------------------------------
# Só o imperativo no COMEÇO do pedido ("lembra que...", "keep in memory ..."): "você lembra?", "lembre-me de ligar
# amanhã" (lembrete, não preferência) e frases no meio de outro assunto não contam.
_FATO = r"(?P<fato>[^\n]{3,300})"
_PEDE = r"(?:(?:por favor|please|pf|pfv|s'il te pla[iî]t|por favor,?)[ ,]+)?"
_RE_LEMBRAR = [re.compile(p, re.IGNORECASE) for p in (
    # en: "keep/save/put this in memory (that) X", "remember (that) X", "keep in mind (that) X", "note (that) X"
    r"^" + _PEDE + r"(?:keep|save|store|put|add|write|record)\s+(?:(?:this|that|it)\s+)?(?:in|to|into|on)\s+(?:your\s+|my\s+|the\s+)?"
    r"memor(?:y|ies)\s*(?:that\b|:|,|-)?\s*" + _FATO,
    r"^" + _PEDE + r"(?:remember|memorize|memorise)\s*(?:that\b|this\b|:|,|-)?\s*" + _FATO,
    r"^" + _PEDE + r"(?:keep|bear)\s+in\s+mind\s*(?:that\b|:|,|-)?\s*" + _FATO,
    r"^" + _PEDE + r"note\s+(?:down\s+)?(?:that\b|this\b|:)\s*" + _FATO,
    # pt: "lembre/guarde/salve/anote (na memória) que X", "tenha em mente que X"
    r"^" + _PEDE + r"(?:guard[ae]|salv[ae]|anot[ae]|grav[ae]|registr[ae])\s+(?:isso\s+|essa\s+|esse\s+)?(?:na|em|a)?\s*mem[oó]ria\s*"
    r"(?:que\b|:|,|-)?\s*" + _FATO,
    r"^" + _PEDE + r"(?:guard[ae]|anot[ae]|memoriz[ae]|lembr[ae](?!-?me\b)|lembra(?!-?me\b))(?:-se)?\s+(?:de\s+)?(?:que\b|isso\b|:|,|-)\s*" + _FATO,
    r"^" + _PEDE + r"(?:memoriz[ae])\s+" + _FATO,
    r"^" + _PEDE + r"tenha\s+em\s+mente\s*(?:que\b|:|,|-)?\s*" + _FATO,
    # es / fr / de
    r"^" + _PEDE + r"(?:recuerda|memoriza|guarda\s+en\s+(?:la\s+)?memoria|ten\s+en\s+cuenta)\s*(?:que\b|:|,|-)?\s*" + _FATO,
    r"^" + _PEDE + r"(?:souviens-toi|rappelle-toi|retiens|m[ée]morise|garde\s+en\s+m[ée]moire)\s*(?:que\b|:|,|-)?\s*" + _FATO,
    r"^" + _PEDE + r"(?:merk\s+dir|merke\s+dir|erinnere\s+dich\s+daran)\s*,?\s*(?:dass\b|:|,|-)?\s*" + _FATO,
)]


def intencao_de_lembrar(texto):
    """O fato que o pedido manda salvar ("keep in memory i use brave as my browser" -> "i use brave as my browser"),
    ou None. Pergunta ("você lembra?") e lembrete ("lembre-me de...") não são pedido de salvar."""
    texto = (texto or "").strip()
    if not texto or texto.endswith("?"):
        return None
    primeira = texto.split("\n", 1)[0] if "\n" in texto[:300] else texto
    for padrao in _RE_LEMBRAR:
        m = padrao.match(primeira)
        if m:
            fato = m.group("fato").strip(" \t:,;-–—\"'`")
            fato = re.sub(r"^(?:que|that|dass|isso|this)\s+", "", fato, flags=re.IGNORECASE).strip()
            if len(fato) >= 3:
                return fato
    return None
