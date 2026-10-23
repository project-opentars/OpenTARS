"""openTARS 3.0: voz.

- ouvir: o microfone (arecord / parecord / pw-record, o que houver) vira
  trechos de fala (Segmentador: energia com piso de ruído que se adapta);
- palavra de ativação: cada trecho curto passa por um Whisper pequeno
  (tiny); se começa com "TARS" ("ei TARS", "ok TARS"...), o trecho é
  transcrito de novo com o modelo melhor e o que vem depois do nome é o
  pedido. "TARS" sozinho: o próximo trecho é o pedido;
- transcrever: faster-whisper (roda na CPU, int8);
- falar: Piper (voz neural local) + o tocador que houver (pw-play,
  paplay, aplay).

Tudo 100% local. As dependências (faster-whisper, piper-tts) e os modelos
(~470 MB de bibliotecas, ~220 MB dos modelos do Whisper e ~60 MB por voz) só são baixados quando a pessoa
liga a voz (instalar()).

A lógica pura (Segmentador, achar_ativacao, limpar_para_fala, escolhas de
voz e de programa) não depende de nada instalado e é testada sozinha."""

import array
import importlib.util
import json
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from pathlib import Path

import tars_plataforma as plataforma

TAXA = 16000               # Hz, mono, 16 bits: o que o Whisper quer
BYTES_AMOSTRA = 2
QUADRO_MS = 30

# ------------------------------------------------------------
# Onde ficam os modelos
# ------------------------------------------------------------


def pasta_dados():
    return plataforma.pastas()["dados"] / "voz"


def pasta_pacotes():
    """Onde o openTARS instala as bibliotecas da voz: na pasta da PESSOA (o
    Python do openTARS fica em /usr/share, que é do root), uma por versão
    do Python (atualizar o sistema não quebra)."""
    return pasta_dados() / f"python{sys.version_info.major}.{sys.version_info.minor}"


def _ativar_pacotes():
    pasta = str(pasta_pacotes())
    if Path(pasta).is_dir() and pasta not in sys.path:
        sys.path.append(pasta)
    return pasta


_ativar_pacotes()

# ------------------------------------------------------------
# Whisper (ouvir): escolhido sozinho pelo hardware (4.0)
# ------------------------------------------------------------
# Na placa (NVIDIA com memória sobrando): large-v3-turbo, preciso e rápido. Só no
# processador: small (multilíngue; em inglês, small.en: os ".en" acertam mais).
# TARS_WHISPER / TARS_WHISPER_ATIVACAO trocam os modelos;
# TARS_WHISPER_DISPOSITIVO=cpu|cuda|auto força o lugar.
MODELO_WHISPER = os.environ.get("TARS_WHISPER") or None             # None = escolher sozinho
MODELO_WHISPER_ATIVACAO = os.environ.get("TARS_WHISPER_ATIVACAO") or None
WHISPER_PLACA = ("large-v3-turbo", "base")    # (pedido, "TARS") na placa (5.0: multilíngue, serve pro português)
WHISPER_PLACA_EN = ("large-v3-turbo", "base.en")
WHISPER_CPU = ("small", "base")               # (pedido, "TARS") no processador, multilíngue (português e inglês)
WHISPER_CPU_EN = ("small.en", "base.en")      # só em inglês os ".en" acertam mais
VRAM_LIVRE_MIN_MB = 4500                      # placa de 6 GB vazia: cabe o Whisper (~1 GB) + o Gargantua (~3 GB)
VRAM_LIVRE_MIN_GRANDE_MB = 2000               # placa de 8 GB ou mais
_config_whisper = {}
_idioma_whisper = {"l": "en"}   # idioma da voz em uso (muda o modelo escolhido)


def _memoria_da_placa():
    """(livre_mb, total_mb) da NVIDIA, ou None."""
    if not shutil.which("nvidia-smi"):
        return None
    try:
        saida = subprocess.run(["nvidia-smi", "--query-gpu=memory.free,memory.total", "--format=csv,noheader,nounits"],
                               capture_output=True, text=True, timeout=5).stdout.strip().splitlines()
        livre, total = (int(x) for x in saida[0].split(","))
        return livre, total
    except Exception:
        return None


def placa_serve_pro_whisper(memoria=None):
    memoria = memoria if memoria is not None else _memoria_da_placa()
    if not memoria:
        return False
    livre, total = memoria
    return livre >= VRAM_LIVRE_MIN_MB or (total >= 8000 and livre >= VRAM_LIVRE_MIN_GRANDE_MB)


def config_whisper(forcar=False, memoria=None):
    """{'pedido': (modelo, dispositivo, tipo), 'ativacao': (...)}."""
    if _config_whisper and not forcar and _config_whisper.get("idioma") == _idioma_whisper["l"]:
        return dict(_config_whisper)
    lugar = (os.environ.get("TARS_WHISPER_DISPOSITIVO") or "auto").lower()
    placa = lugar == "cuda" or (lugar == "auto" and not _config_whisper.get("placa_falhou")
                                and placa_serve_pro_whisper(memoria))
    ingles = _idioma_whisper["l"] == "en"
    pedido, ativacao = (WHISPER_PLACA_EN if ingles else WHISPER_PLACA) if placa else (WHISPER_CPU_EN if ingles else WHISPER_CPU)
    dispositivo, tipo = ("cuda", "int8_float16") if placa else ("cpu", "int8")
    _config_whisper.update(idioma=_idioma_whisper["l"], pedido=(MODELO_WHISPER or pedido, dispositivo, tipo),
                           ativacao=(MODELO_WHISPER_ATIVACAO or ativacao, dispositivo, tipo))
    return dict(_config_whisper)


def _preparar_cuda():
    """O faster-whisper na placa precisa das bibliotecas cuBLAS e cuDNN. Elas
    vêm do pip (nvidia-cublas-cu12, nvidia-cudnn-cu12) na pasta da voz:
    carrega antes, pra o ctranslate2 achar sem mexer no LD_LIBRARY_PATH."""
    import ctypes
    import glob
    base = pasta_pacotes() / "nvidia"
    for padrao in ("cublas/lib/libcublasLt.so*", "cublas/lib/libcublas.so*", "cudnn/lib/libcudnn*.so*"):
        for arquivo in sorted(glob.glob(str(base / padrao))):
            try:
                ctypes.CDLL(arquivo, mode=ctypes.RTLD_GLOBAL)
            except OSError:
                pass


# ------------------------------------------------------------
# Falar: Kokoro (4.0)
# ------------------------------------------------------------
# Kokoro-82M (Apache 2.0) pelo onnxruntime, no processador: soa natural,
# bem diferente do Piper (que ficou só de reserva). Um modelo só pra todas
# as vozes; a fonética vem do espeak-ng que o kokoro-onnx já traz.
KOKORO_ARQUIVOS = {
    "kokoro-v1.0.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
    "voices-v1.0.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
}
KOKORO_LINGUA = {"en": "en-us", "pt_BR": "pt-br"}

# nome -> (voz do Kokoro, descrição curta). A primeira é a padrão.
# 5.0 Tesseract: o português voltou (Kokoro pt-br: menos natural que o inglês, mas funciona).
VOZES_DISPONIVEIS = {
    "pt_BR": {
        "dora": ("pf_dora", "feminina (padrão)"),
        "alex": ("pm_alex", "masculina"),
        "santa": ("pm_santa", "masculina, grave"),
    },
    "en": {
        "heart": ("af_heart", "female, warm (default)"),
        "bella": ("af_bella", "female, bright"),
        "michael": ("am_michael", "male"),
        "emma": ("bf_emma", "female, British"),
    },
}

# Reserva: Piper (rhasspy/piper-voices), se o Kokoro não estiver instalado
# mas a voz antiga já estiver baixada.
VOZES = {
    "en": ("en", "en_US", "lessac", "medium"),
}
URL_VOZ = ("https://huggingface.co/rhasspy/piper-voices/resolve/main/"
           "{familia}/{codigo}/{nome}/{qualidade}/{codigo}-{nome}-{qualidade}{extensao}?download=true")

# Preferências que o núcleo passa (config.json): voz escolhida por idioma,
# velocidade (1.0 = normal; 1.2 = 20% mais rápida) e pausa entre frases.
PREFERENCIAS = {"vozes": {}, "velocidade": 1.0, "pausa": 0.15}
VELOCIDADE_MIN, VELOCIDADE_MAX = 0.7, 1.6


def configurar(vozes=None, velocidade=None, pausa=None, idioma=None):
    if idioma is not None:
        _idioma_whisper["l"] = idioma if idioma in IDIOMA_WHISPER else "en"
    if vozes is not None:
        PREFERENCIAS["vozes"] = {k: v for k, v in vozes.items() if v in VOZES_DISPONIVEIS.get(k, {})}
    if velocidade is not None:
        PREFERENCIAS["velocidade"] = min(VELOCIDADE_MAX, max(VELOCIDADE_MIN, float(velocidade)))
    if pausa is not None:
        PREFERENCIAS["pausa"] = min(1.5, max(0.0, float(pausa)))


def _idioma_voz(idioma):
    return idioma if idioma in VOZES_DISPONIVEIS else "en"


def nome_da_voz(idioma, nome=None):
    """Nome curto da voz pedida, da escolhida ou da padrão ('dora')."""
    disponiveis = VOZES_DISPONIVEIS[_idioma_voz(idioma)]
    nome = nome or PREFERENCIAS["vozes"].get(_idioma_voz(idioma))
    return nome if nome in disponiveis else next(iter(disponiveis))


def voz_kokoro(idioma, nome=None):
    """('af_heart', 'en-us')"""
    codigo = VOZES_DISPONIVEIS[_idioma_voz(idioma)][nome_da_voz(idioma, nome)][0]
    lingua = "en-gb" if codigo.startswith("b") else KOKORO_LINGUA[_idioma_voz(idioma)]
    return codigo, lingua


def pasta_kokoro():
    return pasta_dados() / "kokoro"


def arquivos_kokoro():
    return pasta_kokoro() / "kokoro-v1.0.onnx", pasta_kokoro() / "voices-v1.0.bin"


def kokoro_baixado():
    return all(a.exists() and a.stat().st_size > 1000 for a in arquivos_kokoro())


def arquivo_voz(idioma, nome=None):
    """O arquivo que precisa existir pra falar: o modelo do Kokoro (o mesmo
    pra todas as vozes)."""
    return arquivos_kokoro()[0]


def arquivo_voz_piper(idioma):
    familia, codigo, nome, qualidade = VOZES.get(idioma) or VOZES["en"]
    return pasta_dados() / f"{codigo}-{nome}-{qualidade}.onnx"


def urls_voz_piper(idioma):
    familia, codigo, nome, qualidade = VOZES.get(idioma) or VOZES["en"]
    campos = dict(familia=familia, codigo=codigo, nome=nome, qualidade=qualidade)
    return URL_VOZ.format(extensao=".onnx", **campos), URL_VOZ.format(extensao=".onnx.json", **campos)


IDIOMA_WHISPER = {"en": "en", "pt_BR": "pt"}
IDIOMAS_COM_VOZ = ("en", "pt_BR")


def tem_voz(idioma):
    """Ouvir e falar em inglês e em português (5.0)."""
    return str(idioma or "") in IDIOMAS_COM_VOZ

# Só o nome, sem frase de exemplo: uma frase longa (a do 3.0 Miller, em
# português) fazia o Whisper "ouvir" coisas que ninguém falou.
DICA = "TARS, openTARS."

# O que o TARS responde quando ouve só o nome
CONFIRMACOES = {"en": "Yes?", "pt_BR": "Sim?"}


# ------------------------------------------------------------
# Programas de áudio
# ------------------------------------------------------------
GRAVADORES = (
    ("arecord", ["arecord", "-q", "-f", "S16_LE", "-r", str(TAXA), "-c", "1", "-t", "raw"]),
    ("parecord", ["parecord", "--raw", f"--rate={TAXA}", "--channels=1", "--format=s16le"]),
    ("pw-record", ["pw-record", "--rate", str(TAXA), "--channels", "1", "--format", "s16", "-"]),
)
TOCADORES = (
    ("pw-play", ["pw-play"]),
    ("paplay", ["paplay"]),
    ("aplay", ["aplay", "-q"]),
)


def _primeiro(programas, existe=shutil.which):
    for programa, comando in programas:
        if existe(programa):
            return list(comando)
    return None


def comando_gravar(existe=shutil.which):
    return _primeiro(GRAVADORES, existe)


def comando_tocar(existe=shutil.which):
    return _primeiro(TOCADORES, existe)


def _tem_modulo(nome):
    try:
        return importlib.util.find_spec(nome) is not None
    except (ImportError, ValueError):
        return False


def o_que_falta(idioma="en", existe=shutil.which, tem_modulo=_tem_modulo):
    """Lista do que falta pra voz funcionar (vazia = pronta). Cada item é
    uma chave curta: 'faster-whisper', 'kokoro-onnx', 'voz', 'gravador', 'tocador'."""
    falta = []
    if not tem_modulo("faster_whisper"):
        falta.append("faster-whisper")
    if not tem_modulo("kokoro_onnx"):
        falta.append("kokoro-onnx")
    if not kokoro_baixado():
        falta.append("voz")
    if not comando_gravar(existe):
        falta.append("gravador")
    if not comando_tocar(existe):
        falta.append("tocador")
    return falta


# ------------------------------------------------------------
# Instalação (só quando a pessoa liga a voz)
# ------------------------------------------------------------
PACOTES = ("faster-whisper", "kokoro-onnx")
# Só com placa NVIDIA: as bibliotecas que o Whisper usa na placa (~1 GB).
PACOTES_PLACA = ("nvidia-cublas-cu12", "nvidia-cudnn-cu12==9.*")


def _pip(pacotes, avisar):
    avisar("pip install " + " ".join(pacotes))
    pasta = pasta_pacotes()
    pasta.mkdir(parents=True, exist_ok=True)
    comando = [sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", "--target", str(pasta), *pacotes]
    r = subprocess.run(comando, capture_output=True, text=True)
    _ativar_pacotes()
    importlib.invalidate_caches()
    return r.returncode == 0, (r.stderr or r.stdout or "pip failed").strip()[-600:]


def _tem_bibliotecas_placa():
    return (pasta_pacotes() / "nvidia" / "cudnn").is_dir() and (pasta_pacotes() / "nvidia" / "cublas").is_dir()


def instalar(idioma, avisar=print):
    """Instala as bibliotecas no Python do openTARS, baixa o Kokoro e os
    modelos do Whisper. Devolve (ok, mensagem)."""
    falta = o_que_falta(idioma)
    if "faster-whisper" in falta or "kokoro-onnx" in falta:
        ok, erro = _pip(PACOTES, avisar)
        if not ok:
            return False, erro
    lugar = (os.environ.get("TARS_WHISPER_DISPOSITIVO") or "auto").lower()
    if lugar != "cpu" and placa_serve_pro_whisper() and not _tem_bibliotecas_placa():
        ok, _erro = _pip(PACOTES_PLACA, avisar)  # sem elas, o Whisper fica no processador
        if not ok:
            _config_whisper["placa_falhou"] = True
    if not kokoro_baixado():
        ok, erro = baixar_voz(idioma, avisar)
        if not ok:
            return False, erro
    config = config_whisper(forcar=True)
    avisar(f"Whisper {config['ativacao'][0]} + {config['pedido'][0]} ({config['pedido'][1]})")
    try:
        Transcritor(papel="ativacao").carregar()
        Transcritor(papel="pedido").carregar()
    except Exception as e:
        return False, f"Whisper: {e}"
    falta = o_que_falta(idioma)
    if falta:
        return False, "missing: " + ", ".join(falta)
    return True, ""


def _baixar(url, caminho, avisar):
    import requests  # só aqui: o resto do módulo não precisa

    avisar(f"{caminho.name}...")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(caminho.suffix + ".parte")
    try:
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(temporario, "wb") as f:
                for bloco in r.iter_content(1 << 16):
                    f.write(bloco)
        os.replace(temporario, caminho)
        return True, ""
    except Exception as e:
        try:
            temporario.unlink()
        except OSError:
            pass
        return False, f"{caminho.name}: {e}"


def baixar_voz(idioma, avisar=print, nome=None):
    """Baixa o Kokoro (~340 MB, uma vez: serve pra todas as vozes)."""
    for nome_arquivo, url in KOKORO_ARQUIVOS.items():
        caminho = pasta_kokoro() / nome_arquivo
        if caminho.exists() and caminho.stat().st_size > 1000:
            continue
        ok, erro = _baixar(url, caminho, avisar)
        if not ok:
            return False, erro
    return True, ""


# ------------------------------------------------------------
# Segmentador: microfone -> trechos de fala
# ------------------------------------------------------------
LIMIAR_MINIMO = 180        # RMS (0–32768): abaixo disso nunca é fala
FATOR_RUIDO = 3.0          # fala = mais que 3x o ruído de fundo
SILENCIO_FIM_MS = 600      # tanto silêncio encerra o trecho
FALA_MINIMA_MS = 250       # menos que isso é estalo, tosse, clique
FALA_MAXIMA_S = 12
PRE_ROLL_MS = 300          # o começo da palavra fica abaixo do limiar
AQUECIMENTO_MS = 250       # o começo só aprende o ruído de fundo (ventoinha, rua)


def rms(quadro):
    amostras = array.array("h")
    amostras.frombytes(quadro[: len(quadro) - len(quadro) % 2])
    if sys.byteorder == "big":
        amostras.byteswap()
    if not amostras:
        return 0.0
    return math.sqrt(sum(a * a for a in amostras) / len(amostras))


class Segmentador:
    """Recebe áudio cru (16 kHz, 16 bits, mono) em pedaços de qualquer
    tamanho e devolve os trechos de fala completos (bytes)."""

    def __init__(self, taxa=TAXA, quadro_ms=QUADRO_MS):
        self.bytes_quadro = int(taxa * quadro_ms / 1000) * BYTES_AMOSTRA
        self.quadro_ms = quadro_ms
        self.piso = None
        self._resto = b""
        self._pre = []
        self._fala = []
        self._silencio_ms = 0
        self._fala_ms = 0
        self._aquecido_ms = 0
        self.id_trecho = 0        # sobe a cada fala que começa

    @property
    def limiar(self):
        return max(LIMIAR_MINIMO, (self.piso or 0) * FATOR_RUIDO)

    def alimentar(self, dados):
        return [trecho for _id, trecho in self.alimentar_com_id(dados)]

    def alimentar_com_id(self, dados):
        """Como alimentar(), mas cada trecho vem com o id da fala: [(id, bytes)]."""
        prontos = []
        dados = self._resto + dados
        n = len(dados) - len(dados) % self.bytes_quadro
        self._resto = dados[n:]
        for i in range(0, n, self.bytes_quadro):
            ident = self.id_trecho
            trecho = self._quadro(dados[i:i + self.bytes_quadro])
            if trecho:
                prontos.append((ident, trecho))
        return prontos

    @property
    def falando_ms(self):
        """Quanto da fala EM ANDAMENTO já chegou (0 se ninguém está falando)."""
        return len(self._fala) * self.quadro_ms if self._fala else 0

    def audio_parcial(self, max_s):
        """O começo da fala em andamento (até max_s segundos)."""
        return b"".join(self._fala[:int(max_s * 1000 / self.quadro_ms)])

    def encerrar(self):
        """Fecha a fala em andamento agora (o botão "segurar para falar" foi solto). bytes ou None."""
        if not self._fala:
            return None
        fala, fala_ms = b"".join(self._fala), self._fala_ms
        self._fala, self._fala_ms, self._silencio_ms = [], 0, 0
        return fala if fala_ms >= FALA_MINIMA_MS else None

    def _quadro(self, quadro):
        energia = rms(quadro)
        if self._aquecido_ms < AQUECIMENTO_MS:
            # o quadro mais quieto do começo é o ruído de fundo; os quadros
            # ficam no pre-roll (quem já começou a falar não perde o início)
            self._aquecido_ms += self.quadro_ms
            self.piso = energia if self.piso is None else min(self.piso, energia)
            self._pre.append(quadro)
            if len(self._pre) * self.quadro_ms > PRE_ROLL_MS:
                self._pre.pop(0)
            return None
        falando = energia > self.limiar
        if not self._fala:
            if falando:
                self.id_trecho += 1
                self._fala = list(self._pre) + [quadro]
                self._fala_ms = self.quadro_ms
                self._silencio_ms = 0
                self._pre = []
                return None
            # silêncio: aprende o ruído de fundo e guarda o pre-roll
            self.piso = energia if self.piso is None else 0.95 * self.piso + 0.05 * energia
            self._pre.append(quadro)
            if len(self._pre) * self.quadro_ms > PRE_ROLL_MS:
                self._pre.pop(0)
            return None
        self._fala.append(quadro)
        if falando:
            self._fala_ms += self.quadro_ms
            self._silencio_ms = 0
        else:
            self._silencio_ms += self.quadro_ms
        total_ms = len(self._fala) * self.quadro_ms
        if self._silencio_ms >= SILENCIO_FIM_MS or total_ms >= FALA_MAXIMA_S * 1000:
            fala, fala_ms = b"".join(self._fala), self._fala_ms
            self._fala, self._fala_ms, self._silencio_ms = [], 0, 0
            if fala_ms >= FALA_MINIMA_MS:
                return fala
        return None


# ------------------------------------------------------------
# Palavra de ativação
# ------------------------------------------------------------
# O Whisper escreve "TARS" de vários jeitos: Tars, Tarz, Thars, Taars...
# Como o Whisper costuma escrever "TARS" falado: tars, tarz, thars, taars,
# tares, dars, ters...
_RE_ATIVACAO = re.compile(
    r"\b(?:open[\s-]?)?(?:th?|d)(?:a{1,2}|e)r(?:[sz]{1,2}[oe]?|es)h?\b[\s,.!?:;…-]*", re.IGNORECASE)
PALAVRAS_ANTES_MAX = 2     # "ei TARS", "ok TARS", "hey there TARS": o nome vem logo no começo


def _sem_acento(texto):
    """Tira acentos SEM mudar o tamanho do texto (um caractere por
    caractere): as posições achadas valem pro texto original."""
    return "".join(unicodedata.normalize("NFD", ch)[0] for ch in texto)


def achar_ativacao(texto):
    """(chamou, resto): 'Ei TARS, abre o Firefox.' -> (True, 'abre o Firefox.').
    Só vale com o nome no começo (até 2 palavras antes), pra não ligar
    quando alguém só fala SOBRE o TARS."""
    original = (texto or "").strip()
    achado = _RE_ATIVACAO.search(_sem_acento(original))
    if not achado:
        return False, ""
    antes = re.findall(r"\w+", original[:achado.start()])
    if len(antes) > PALAVRAS_ANTES_MAX:
        return False, ""
    resto = original[achado.end():].strip(" \t,.;:!?-…")
    if resto and not re.search(r"\w", resto):
        resto = ""
    return True, resto


def parece_chamado(texto):
    """O modelo rápido ouviu algo PARECIDO com "TARS" no começo ("Taz",
    "Tarde", "Dárcio")? Aí o modelo bom confere de novo, em vez de perder
    o chamado."""
    import difflib
    palavras = re.findall(r"[a-z]+", _sem_acento((texto or "").lower()))[:PALAVRAS_ANTES_MAX + 1]
    return any(difflib.SequenceMatcher(None, p, "tars").ratio() >= 0.55 for p in palavras if 3 <= len(p) <= 7)


# Frases que o Whisper "ouve" no silêncio ou no barulho (vieram das legendas
# com que ele foi treinado). Se o trecho inteiro é isso, ninguém falou nada.
_ALUCINACOES = re.compile(
    r"^\W*(thanks? (you )?for watching|subtitles? by.*|please subscribe|(music|applause|laughter|silence)|"
    r"obrigad[oa] por assistir|legendas? (pela|por|de).*|inscreva-se.*|(música|palmas|risos|silêncio)|"
    r"\.+|♪+)\W*$", re.IGNORECASE)


def e_alucinacao(texto):
    return bool(_ALUCINACOES.match((texto or "").strip())) or "amara.org" in (texto or "").lower()


# ------------------------------------------------------------
# Texto -> fala
# ------------------------------------------------------------
LIMITE_FALA = 700  # caracteres: resposta longa é lida até aí (o resto está na tela)


def limpar_para_fala(texto, limite=LIMITE_FALA):
    """Tira o que não se fala: blocos de código, markdown, links, emoji."""
    t = texto or ""
    t = re.sub(r"```.*?(```|$)", " ", t, flags=re.S)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"^\s*[-*•]\s+", "", t, flags=re.M)
    t = re.sub(r"^\s*\|.*\|\s*$", " ", t, flags=re.M)      # tabelas
    t = re.sub(r"[*_~]{1,3}([^*_~\n]+)[*_~]{1,3}", r"\1", t)
    t = "".join(ch for ch in t if unicodedata.category(ch) not in ("So", "Cs", "Co"))
    t = re.sub(r"\s*\n\s*", ". ", t.strip())
    t = re.sub(r"\.(\s*\.)+", ".", t)
    t = re.sub(r"([!?:;])\.", r"\1", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" .")
    if len(t) > limite:
        corte = t[:limite]
        fim = max(corte.rfind(". "), corte.rfind("! "), corte.rfind("? "))
        t = corte[:fim + 1] if fim > limite // 3 else corte.rsplit(" ", 1)[0] + "..."
    return t


# O texto já limpo vira algo que soa natural falado. "12 x 8 = 96", "1,234",
# "2026-10-01", "1920x1080" ou "GB" saem estranhos lidos ao pé da letra: aqui viram
# "12 times 8 equals 96", "1234", "October 1, 2026", "1920 by 1080", "gigabytes"
# (em português: "12 vezes 8 igual a 96", "1 de outubro de 2026", "1920 por 1080").
_FALA = {
    "en": {
        "unidades": {"GB": "gigabytes", "MB": "megabytes", "KB": "kilobytes", "TB": "terabytes", "GHz": "gigahertz",
                     "MHz": "megahertz", "km": "kilometers", "ms": "milliseconds", "°C": "degrees", "%": "percent"},
        "operadores": {"x": "times", "*": "times", "×": "times", "/": "divided by", "÷": "divided by", "+": "plus",
                       "-": "minus", "=": "equals"},
        "meses": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                  "November", "December"],
        "data": lambda dia, mes, ano: f"{mes} {dia}, {ano}",
        "por": "by", "ate": "to", "igual": "equals", "marca": "open Tars", "nome": "Tars",
    },
    "pt_BR": {
        "unidades": {"GB": "gigabytes", "MB": "megabytes", "KB": "kilobytes", "TB": "terabytes", "GHz": "gigahertz",
                     "MHz": "megahertz", "km": "quilômetros", "ms": "milissegundos", "°C": "graus", "%": "por cento"},
        "operadores": {"x": "vezes", "*": "vezes", "×": "vezes", "/": "dividido por", "÷": "dividido por",
                       "+": "mais", "-": "menos", "=": "igual a"},
        "meses": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
                  "outubro", "novembro", "dezembro"],
        "data": lambda dia, mes, ano: f"{'primeiro' if dia == 1 else dia} de {mes} de {ano}",
        "por": "por", "ate": "a", "igual": "igual a", "marca": "open Tars", "nome": "Tars",
    },
}
# nomes antigos (testes e quem importa)
_UNIDADES = _FALA["en"]["unidades"]
_OPERADORES = _FALA["en"]["operadores"]
_MESES = _FALA["en"]["meses"]


def preparar_para_fala(texto, idioma="en"):
    f = _FALA.get(idioma) or _FALA["en"]
    pt = idioma == "pt_BR"
    t = texto or ""
    # Caminhos: só o último nome ("/home/sam/Desktop/notes.txt" -> "notes.txt")
    t = re.sub(r"(?:~|/[\w.-]+)(?:/[\w .-]+?)*/([\w.-]+(?: [\w.-]+)?)(?=[\s,.;:!?)]|$)", lambda m: m.group(1), t)
    t = re.sub(r"\bopenTARS\b", f["marca"], t, flags=re.I)
    t = re.sub(r"\bTARS\b", f["nome"], t)
    # milhares: "1,234" (inglês) e "1.234" (português) viram "1234"
    t = re.sub(r"\b\d{1,3}(?:\.\d{3})+\b" if pt else r"\b\d{1,3}(?:,\d{3})+\b",
               lambda m: re.sub(r"[.,]", "", m.group(0)), t)

    def data(m):
        ano, mes, dia = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f["data"](dia, f["meses"][mes - 1], ano) if 1 <= mes <= 12 and 1 <= dia <= 31 else m.group(0)

    t = re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", data, t)
    t = re.sub(r"\b(\d{3,})x(\d{3,})\b", rf"\1 {f['por']} \2", t)
    t = re.sub(r"\b(\d+)-(\d+)\b", rf"\1 {f['ate']} \2", t)
    t = re.sub(r"(?<=\d)\s*([x*×/÷+=-])\s*(?=\d)", lambda m: f" {f['operadores'][m.group(1)]} ", t)
    t = re.sub(r"(?<=\d)\s*=\s*", f" {f['igual']} ", t)
    for unidade, nome in f["unidades"].items():
        t = re.sub(rf"(?<=\d)\s?{re.escape(unidade)}(?![\w])", f" {nome}", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def dividir_frases(texto, minimo=40, maximo=260):
    """Frases pra falar uma de cada vez (a primeira começa a tocar enquanto
    as outras ainda são geradas). Frases curtas se juntam; longas quebram
    na vírgula."""
    partes = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", texto or "") if p.strip()]
    frases = []
    for parte in partes:
        while len(parte) > maximo:
            corte = parte.rfind(", ", 0, maximo)
            corte = corte + 1 if corte > minimo else parte.rfind(" ", 0, maximo)
            if corte <= 0:
                break
            frases.append(parte[:corte].strip())
            parte = parte[corte:].strip()
        if frases and (len(frases[-1]) < minimo or len(parte) < minimo // 2) and len(frases[-1]) + len(parte) < maximo:
            frases[-1] = f"{frases[-1]} {parte}"
        else:
            frases.append(parte)
    return frases


# ------------------------------------------------------------
# Whisper
# ------------------------------------------------------------
class Transcritor:
    """papel 'pedido' ou 'ativacao' escolhe o modelo e o lugar pelo hardware
    (config_whisper). Com um nome explícito (Transcritor("small")), usa
    esse modelo no lugar escolhido."""
    _cache = {}
    _trava = threading.Lock()

    def __init__(self, tamanho=None, papel="pedido"):
        self._tamanho_fixo = tamanho
        self.papel = papel

    @property
    def tamanho(self):
        return self._tamanho_fixo or config_whisper()[self.papel][0]

    def _onde(self):
        _nome, dispositivo, tipo = config_whisper()[self.papel]
        return dispositivo, tipo

    def carregar(self):
        with self._trava:
            nome = self.tamanho
            if nome in self._cache:  # nome explícito já carregado (ou um falso, nos testes)
                return self._cache[nome]
            dispositivo, tipo = self._onde()
            chave = f"{nome}@{dispositivo}"
            modelo = self._cache.get(chave)
            if modelo is None:
                from faster_whisper import WhisperModel
                if dispositivo == "cuda":
                    try:
                        _preparar_cuda()
                        modelo = WhisperModel(nome, device="cuda", compute_type=tipo)
                    except Exception:
                        # sem cuDNN/cuBLAS, driver velho, placa cheia: volta pro processador
                        _config_whisper["placa_falhou"] = True
                        config_whisper(forcar=True)
                        nome = self._tamanho_fixo or config_whisper()[self.papel][0]
                        chave = f"{nome}@cpu"
                        modelo = self._cache.get(chave)
                if modelo is None:
                    modelo = WhisperModel(nome, device="cpu", compute_type="int8")
                self._cache[chave] = modelo
            return modelo

    def transcrever(self, audio, idioma=None, dica=None, rapido=False, vocabulario=None):
        """Texto do áudio (bytes 16 kHz 16 bits mono). rapido=True: só
        pra achar o "TARS" (poucos tokens). vocabulario: palavras que
        provavelmente aparecem (nomes dos apps): o Whisper erra menos nelas."""
        import numpy as np

        dados = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        lingua = IDIOMA_WHISPER.get(idioma or _idioma_whisper["l"], "en")
        if rapido:
            opcoes = dict(language=lingua, beam_size=1, vad_filter=False,
                          initial_prompt=dica or DICA, condition_on_previous_text=False, temperature=0.0,
                          without_timestamps=True, max_new_tokens=12, hotwords="TARS")
        else:
            # O pedido: busca mais cuidadosa (beam 5) e o detector de voz (Silero) tira o silêncio
            # e o barulho, que é onde o Whisper inventa frases. Sem frase de exemplo no prompt.
            palavras = ["TARS", "openTARS"] + [v for v in (vocabulario or []) if v][:40]
            opcoes = dict(language=lingua, beam_size=5, vad_filter=True,
                          condition_on_previous_text=False, temperature=0.0, without_timestamps=True,
                          hotwords=", ".join(dict.fromkeys(palavras)))
            if dica:
                opcoes["initial_prompt"] = dica
        modelo = self.carregar()
        while True:
            try:
                segmentos, _info = modelo.transcribe(dados, **opcoes)
                texto = " ".join(s.text.strip() for s in segmentos).strip()
                return "" if e_alucinacao(texto) else texto
            except TypeError as e:  # faster-whisper antigo: tira a opção que ele não conhece
                opcao = next((k for k in ("max_new_tokens", "without_timestamps", "hotwords") if k in opcoes
                              and k in str(e)), None)
                if not opcao:
                    raise
                opcoes.pop(opcao)

    def aquecer(self):
        """Carrega e roda uma vez (a primeira transcrição é a mais lenta)."""
        self.transcrever(b"\x00\x00" * (TAXA // 2), _idioma_whisper["l"], rapido=True)


# ------------------------------------------------------------
# Falar (Kokoro; Piper de reserva)
# ------------------------------------------------------------
class Falador:
    def __init__(self, tocar=None):
        self._kokoro = None              # processo que guarda o Kokoro carregado
        self._trava_kokoro = threading.Lock()
        self._processos = []
        self._trava = threading.Lock()
        self.falando = threading.Event()   # ligado enquanto QUALQUER fala estiver em andamento
        self._falas = 0
        self._tocar = tocar

    def _comecou(self):
        with self._trava:
            self._falas += 1
            self.falando.set()

    def _acabou(self):
        with self._trava:
            self._falas = max(0, self._falas - 1)
            if not self._falas:
                self.falando.clear()

    def falar(self, texto, idioma, esperar=False, ao_terminar=None):
        texto = limpar_para_fala(texto)
        if not texto:
            return False
        thread = threading.Thread(target=self._falar, args=(texto, idioma, ao_terminar), daemon=True)
        thread.start()
        if esperar:
            thread.join()
        return True

    # --- "Sim?" quando ouve só o nome ---
    @staticmethod
    def _arquivo_confirmacao(idioma):
        return pasta_dados() / "cache" / f"sim-{idioma}-{nome_da_voz(idioma)}.wav"

    def preparar_confirmacao(self, idioma):
        """Gera (uma vez por voz) o "Sim?" na voz do idioma, pra tocar na hora."""
        if kokoro_baixado() and _tem_modulo("kokoro_onnx"):
            with self._trava_kokoro:  # já deixa o Kokoro carregado pra primeira resposta
                self._iniciar_kokoro()
        destino = self._arquivo_confirmacao(idioma)
        if destino.exists() or not (kokoro_baixado() or arquivo_voz_piper(idioma).exists()):
            return destino.exists()
        destino.parent.mkdir(parents=True, exist_ok=True)
        return self._sintetizar(CONFIRMACOES.get(idioma, "Yes?"), idioma, destino) and destino.exists()

    def confirmar(self, idioma):
        """Toca o "Sim?" (ou um sininho, se a voz ainda não estiver pronta)
        sem travar: é o sinal de que ouviu o nome."""
        tocador = self._tocar or comando_tocar()
        if not tocador:
            return False
        arquivo = self._arquivo_confirmacao(idioma)
        if not arquivo.exists():
            arquivo = pasta_dados() / "cache" / "sininho.wav"
            if not arquivo.exists():
                arquivo.parent.mkdir(parents=True, exist_ok=True)
                arquivo.write_bytes(sininho_wav())
        self._comecou()  # já conta como falando: o microfone não ouve o próprio "Sim?"

        def tocar():
            try:
                subprocess.run(tocador + [str(arquivo)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=10)
            except Exception:
                pass
            finally:
                self._acabou()
        threading.Thread(target=tocar, daemon=True).start()
        return True

    @staticmethod
    def _ambiente():
        ambiente = dict(os.environ)
        ambiente["PYTHONPATH"] = os.pathsep.join(
            x for x in (str(pasta_pacotes()), os.environ.get("PYTHONPATH", "")) if x)
        return ambiente

    @staticmethod
    def _opcoes_piper():
        """Velocidade e pausa entre frases (4.1). Um Piper antigo que não
        conheça as opções faz o Falador tentar de novo sem elas."""
        if Falador._piper_sem_opcoes:
            return []
        velocidade = PREFERENCIAS["velocidade"] or 1.0
        return ["--length-scale", f"{1.0 / velocidade:.3f}", "--sentence-silence", f"{PREFERENCIAS['pausa']:.2f}"]

    _piper_sem_opcoes = False

    # --- Kokoro: um processo que carrega o modelo uma vez e gera frase por frase ---
    def _iniciar_kokoro(self):
        if self._kokoro is not None and self._kokoro.poll() is None:
            return self._kokoro
        modelo, vozes = arquivos_kokoro()
        ambiente = self._ambiente()
        # a pasta da voz vem PRIMEIRO: o numpy/onnxruntime dela, não os do sistema
        self._kokoro = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--kokoro", str(modelo), str(vozes)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=ambiente,
            text=True, bufsize=1)
        if not self._ler_kokoro(timeout=90).get("pronto"):
            self._fechar_kokoro()
            return None
        return self._kokoro

    def _ler_kokoro(self, timeout):
        import select
        processo = self._kokoro
        if processo is None or processo.stdout is None:
            return {}
        prontos, _, _ = select.select([processo.stdout], [], [], timeout)
        if not prontos:
            return {}
        linha = processo.stdout.readline()
        try:
            return json.loads(linha) if linha else {}
        except ValueError:
            return {}

    def _fechar_kokoro(self):
        processo, self._kokoro = self._kokoro, None
        if processo is not None and processo.poll() is None:
            try:
                processo.kill()
                processo.wait(timeout=5)
            except Exception:
                pass

    def _gerar_kokoro(self, texto, idioma, destino):
        voz, lingua = voz_kokoro(idioma)
        with self._trava_kokoro:
            for _tentativa in range(2):  # se o processo morreu, sobe de novo uma vez
                processo = self._iniciar_kokoro()
                if processo is None:
                    return False
                pedido = {"texto": texto, "voz": voz, "lingua": lingua, "destino": str(destino),
                          "velocidade": PREFERENCIAS["velocidade"], "pausa": PREFERENCIAS["pausa"]}
                try:
                    processo.stdin.write(json.dumps(pedido, ensure_ascii=False) + "\n")
                    processo.stdin.flush()
                except (BrokenPipeError, OSError):
                    self._fechar_kokoro()
                    continue
                resposta = self._ler_kokoro(timeout=120)
                if resposta.get("ok"):
                    return Path(destino).exists() and Path(destino).stat().st_size > 44
                self._fechar_kokoro()
            return False

    def _gerar(self, texto, idioma, destino, cancelar=None):
        """Texto -> wav: Kokoro; se não der, o Piper (se a voz antiga existir)."""
        if cancelar is not None and cancelar.is_set():
            return False
        if kokoro_baixado() and _tem_modulo("kokoro_onnx") and self._gerar_kokoro(texto, idioma, destino):
            return True
        if arquivo_voz_piper(idioma).exists() and _tem_modulo("piper"):
            return self._gerar_piper(texto, idioma, destino, cancelar)
        return False

    def _gerar_piper(self, texto, idioma, destino, cancelar=None):
        """Piper (reserva): texto -> wav. True se deu certo."""
        for opcoes in ([self._opcoes_piper()] + ([[]] if self._opcoes_piper() else [])):
            if cancelar is not None and cancelar.is_set():
                return False
            processo = None
            try:
                processo = subprocess.Popen(
                    [sys.executable, "-m", "piper", "-m", str(arquivo_voz_piper(idioma)), "-f", str(destino), *opcoes],
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=self._ambiente())
                with self._trava:
                    self._processos.append(processo)
                processo.communicate(texto.encode("utf-8"), timeout=120)
                if processo.returncode == 0 and Path(destino).exists() and Path(destino).stat().st_size > 44:
                    return True
            except Exception:
                pass
            finally:
                if processo is not None and processo.poll() is None:
                    try:
                        processo.kill()
                        processo.wait(timeout=5)
                    except Exception:
                        pass
            if opcoes:
                Falador._piper_sem_opcoes = True  # tenta de novo sem as opções
        return False

    def _sintetizar(self, texto, idioma, destino):
        return self._gerar(texto, idioma, destino)

    def _falar(self, texto, idioma, ao_terminar=None):
        try:
            self._falar_de_fato(texto, idioma)
        finally:
            if ao_terminar is not None:
                try:
                    ao_terminar()
                except Exception:
                    pass

    def _tocar_arquivo(self, tocador, wav, cancelar):
        if cancelar.is_set():
            return
        tocar = subprocess.Popen(tocador + [wav], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with self._trava:
            self._processos.append(tocar)
        try:
            tocar.wait(timeout=300)
        except Exception:
            pass
        finally:
            if tocar.poll() is None:
                try:
                    tocar.kill()
                    tocar.wait(timeout=5)
                except Exception:
                    pass

    def _falar_de_fato(self, texto, idioma):
        """4.1: frase a frase. A primeira frase começa a tocar enquanto as
        próximas ainda estão sendo geradas: resposta longa não fica muda
        esperando o Piper gerar tudo."""
        self.parar()
        tocador = self._tocar or comando_tocar()
        if not (kokoro_baixado() or arquivo_voz_piper(idioma).exists()) or not tocador:
            return
        cancelar = threading.Event()
        with self._trava:
            self._cancelar_atual = cancelar
        frases = dividir_frases(preparar_para_fala(texto, idioma)) or [texto]
        fila = queue.Queue()
        fim = object()
        self._comecou()

        def produzir():
            try:
                for frase in frases:
                    if cancelar.is_set():
                        break
                    fd, wav = tempfile.mkstemp(suffix=".wav", prefix="opentars-fala-")
                    os.close(fd)
                    if not self._gerar(frase, idioma, wav, cancelar):
                        _apagar(wav)
                        break
                    fila.put(wav)
            finally:
                fila.put(fim)

        threading.Thread(target=produzir, daemon=True).start()
        try:
            while True:
                try:
                    item = fila.get(timeout=150)
                except queue.Empty:
                    break
                if item is fim:
                    break
                try:
                    self._tocar_arquivo(tocador, item, cancelar)
                finally:
                    _apagar(item)
        finally:
            cancelar.set()
            while True:  # o que sobrou na fila (cancelado no meio)
                try:
                    item = fila.get_nowait()
                except queue.Empty:
                    break
                if item is not fim:
                    _apagar(item)
            with self._trava:
                self._processos = [p for p in self._processos if p.poll() is None]
            self._acabou()

    def parar(self):
        with self._trava:
            cancelar = getattr(self, "_cancelar_atual", None)
            if cancelar is not None:
                cancelar.set()
            for p in self._processos:
                if p.poll() is None:
                    try:
                        p.terminate()
                    except Exception:
                        pass
            self._processos = []


def _apagar(caminho):
    try:
        os.unlink(caminho)
    except OSError:
        pass


# ------------------------------------------------------------
# Ouvir
# ------------------------------------------------------------
ESPERA_PEDIDO_S = 8      # depois de "TARS" sozinho, quanto tempo espera o pedido
ESPERA_CONVERSA_S = 7    # depois de responder falando: dá pra continuar sem dizer "TARS"
CEDO_MS = 650            # com tanto de fala, já confere se começou com "TARS" (sem esperar a pausa)
SILENCIO_DIGITAL_S = 4.0  # gravador que só entrega zeros por tanto tempo está no dispositivo errado
CEDO_MAX_S = 1.6         # o nome vem no começo: basta olhar esse pedaço
SEGUNDA_CHANCE_MAX_S = 8 # trecho até esse tamanho, com algo parecido com "TARS", o modelo bom confere


class Ouvinte:
    """Escuta o microfone numa thread.

    modo "ativacao": fica ouvindo; cada trecho que começa com "TARS" vira
    pedido (ao_pedido(texto)). modo "uma_vez": o primeiro trecho de fala é
    o pedido e para (o botão "Falar agora"). modo "continua": conversa
    contínua, TODO trecho de fala é pedido, sem precisar dizer "TARS" (se
    a pessoa disser, o nome é ignorado).

    Pra responder rápido (3.0 Miller):
    - os dois Whisper são carregados e "aquecidos" assim que começa a ouvir
      (antes, o primeiro "TARS" esperava o modelo carregar);
    - com ~0,65 s de fala, já confere (em paralelo, sem parar de gravar) se
      começou com "TARS": a tela mostra na hora que ouviu, e no fim da fala
      só falta transcrever o pedido;
    - "TARS" sozinho: responde "Sim?" na voz do idioma (ou um sininho) e o
      próximo trecho é o pedido;
    - depois de responder falando, dá pra continuar sem dizer "TARS"
      (abrir_conversa).

    ao_estado(estado): "carregando", "ouvindo", "chamado" (ouviu o nome),
    "conversa" (pode continuar sem o nome), "transcrevendo", "parado",
    ou "erro:<motivo>"."""

    def __init__(self, ao_pedido, idioma, modo="ativacao", ao_estado=None, falador=None,
                 gravar=None, transcritor=None, transcritor_ativacao=None, aquecer=True, vocabulario=None):
        self.ao_pedido = ao_pedido
        self.idioma = idioma if callable(idioma) else (lambda: idioma)
        self.modo = modo
        self.ao_estado = ao_estado or (lambda estado: None)
        self.falador = falador
        self._gravar = gravar
        self._transcritor = transcritor or Transcritor(papel="pedido")
        self._ativacao = transcritor_ativacao or Transcritor(papel="ativacao")
        # 4.0: palavras que provavelmente aparecem no pedido (nomes dos apps instalados)
        self._vocabulario = vocabulario or (lambda: [])
        self._aquecer = aquecer
        self._parar = threading.Event()
        self._thread = None
        self._processo = None
        self.chamado_ate = 0.0
        # conferência "cedo" do nome: id do trecho -> (chamou, resto); e a thread em andamento
        self._cedo = {}
        self._cedo_id = None
        self._cedo_thread = None
        self._fechar = threading.Event()   # 5.0: "segurar para falar": soltou, fecha o trecho

    def terminar_fala(self):
        """Soltou o botão: o que já foi falado vira o pedido, sem esperar o silêncio."""
        self._fechar.set()

    @property
    def ativo(self):
        return self._thread is not None and self._thread.is_alive()

    def iniciar(self):
        if self.ativo:
            if not self._parar.is_set():
                return
            self._thread.join(timeout=3)      # desligou e ligou de novo: espera a rodada antiga terminar de verdade
            if self.ativo:
                return
        self._parar.clear()
        self._thread = threading.Thread(target=self._rodar, daemon=True)
        self._thread.start()

    def parar(self):
        self._parar.set()
        if self._processo is not None:
            try:
                self._processo.terminate()
            except Exception:
                pass

    def abrir_conversa(self, segundos=ESPERA_CONVERSA_S):
        """Por alguns segundos, a próxima fala é pedido mesmo sem "TARS"."""
        if self.ativo and self.modo == "ativacao":
            self.chamado_ate = time.monotonic() + segundos
            self.ao_estado("conversa")

    def _preparar(self):
        """Carrega os modelos (e o "Sim?" falado) antes da primeira fala."""
        if not self._aquecer:
            return
        self.ao_estado("carregando")
        for transcritor in ((self._ativacao, self._transcritor) if self.modo == "ativacao" else (self._transcritor,)):
            try:
                transcritor.aquecer()
            except Exception:
                pass
        if self.falador is not None and hasattr(self.falador, "preparar_confirmacao"):
            # gera o "Sim?" e já deixa o Kokoro carregado: a primeira resposta sai sem esperar
            threading.Thread(target=self.falador.preparar_confirmacao, args=(self.idioma(),), daemon=True).start()

    def _fonte(self):
        """Iterador de pedaços de áudio cru. Se o gravador morre na hora (sem microfone, sem permissão,
        dispositivo errado) ou só entrega silêncio digital, tenta o próximo (arecord, parecord, pw-record);
        se nenhum serve, levanta um erro com a mensagem do próprio gravador (antes ficava mudo e "parado")."""
        if self._gravar is not None:
            yield from self._gravar()
            return
        candidatos = [c for p, c in GRAVADORES if shutil.which(p)]
        if not candidatos:
            raise RuntimeError("no recorder (install alsa-utils or pulseaudio-utils)")
        erros = []
        for comando in candidatos:
            self._processo = subprocess.Popen(comando, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            inicio = time.monotonic()
            recebeu = 0
            som = False
            motivo = ""
            try:
                while not self._parar.is_set():
                    bloco = self._processo.stdout.read(1600)  # 50 ms: reage mais rápido ao fim da fala
                    if not bloco:
                        motivo = "o gravador parou"
                        break
                    recebeu += len(bloco)
                    if not som and rms(bloco) > 0:
                        som = True
                    if not som and time.monotonic() - inicio > SILENCIO_DIGITAL_S:
                        motivo = "só silêncio (microfone mudo ou dispositivo errado)"
                        break
                    yield bloco
            finally:
                try:
                    self._processo.terminate()
                    self._processo.wait(timeout=2)       # sem isto o gravador morto ficava zumbi
                except Exception:
                    pass
            if self._parar.is_set():
                return
            try:
                detalhe = (self._processo.stderr.read() or b"").decode("utf-8", "replace").strip()[:200]
            except Exception:
                detalhe = ""
            erros.append(f"{comando[0]}: {motivo}{' - ' + detalhe if detalhe else ''}")
            if som and time.monotonic() - inicio > 3:
                return          # funcionou um tempo e caiu depois: não é problema de dispositivo; fecha normalmente
        raise RuntimeError("microfone: " + " | ".join(erros))

    def _rodar(self):
        segmentador = Segmentador()
        try:
            self._preparar()
            self.ao_estado("ouvindo")
            for bloco in self._fonte():
                if self._parar.is_set():
                    break
                if self.falador is not None and self.falador.falando.is_set():
                    continue  # não ouve a própria voz
                prontos = segmentador.alimentar_com_id(bloco)
                if self._fechar.is_set():
                    self._fechar.clear()
                    resto = segmentador.encerrar()
                    if resto:
                        prontos.append((segmentador.id_trecho, resto))
                    elif not prontos and self.modo == "uma_vez":
                        self._parar.set()   # soltou sem ter falado nada
                self._conferir_cedo(segmentador)
                for ident, trecho in prontos:
                    if self._tratar(trecho, ident) and self.modo == "uma_vez":
                        self._parar.set()
                        break
                if self._parar.is_set():
                    break
        except Exception as e:
            self.ao_estado(f"erro:{e}")
            return
        self.ao_estado("parado")

    # --- nome conferido enquanto a pessoa ainda fala ---
    def _esperando_pedido(self):
        return self.modo in ("uma_vez", "continua") or time.monotonic() < self.chamado_ate

    def _conferir_cedo(self, segmentador):
        if (self.modo != "ativacao" or self._esperando_pedido() or segmentador.falando_ms < CEDO_MS
                or segmentador.id_trecho == self._cedo_id
                or (self._cedo_thread is not None and self._cedo_thread.is_alive())):
            return
        ident = self._cedo_id = segmentador.id_trecho
        audio = segmentador.audio_parcial(CEDO_MAX_S)
        idioma = self.idioma()

        def conferir():
            try:
                rapido = self._ativacao.transcrever(audio, idioma, rapido=True)
                chamou, resto = achar_ativacao(rapido)
            except Exception:
                rapido, chamou, resto = "", False, ""
            self._cedo[ident] = (chamou, resto, rapido)
            if chamou:
                self.ao_estado("chamado")  # a pessoa vê na hora que foi ouvida

        self._cedo_thread = threading.Thread(target=conferir, daemon=True)
        self._cedo_thread.start()

    def _transcrever_pedido(self, trecho, idioma):
        try:
            vocabulario = list(self._vocabulario() or [])
        except Exception:
            vocabulario = []
        try:
            return self._transcritor.transcrever(trecho, idioma, vocabulario=vocabulario)
        except TypeError:  # transcritor sem vocabulário (testes, versões antigas)
            return self._transcritor.transcrever(trecho, idioma)

    def _nome_no_trecho(self, trecho, ident, idioma):
        """(chamou, resto) do começo do trecho: da conferência cedo, se houve.
        4.0: se o modelo rápido ouviu algo PARECIDO com "TARS" ("Taz", "Tarde"),
        o modelo bom confere o trecho inteiro antes de desistir."""
        if ident is not None and ident == self._cedo_id and self._cedo_thread is not None:
            self._cedo_thread.join(timeout=10)
        if ident in self._cedo:
            chamou, resto, rapido = self._cedo.pop(ident)
        else:
            inicio = trecho[:int(CEDO_MAX_S * TAXA) * BYTES_AMOSTRA]
            rapido = self._ativacao.transcrever(inicio, idioma, rapido=True)
            chamou, resto = achar_ativacao(rapido)
        if not chamou and parece_chamado(rapido) and len(trecho) / BYTES_AMOSTRA / TAXA <= SEGUNDA_CHANCE_MAX_S:
            chamou, resto = achar_ativacao(self._transcrever_pedido(trecho, idioma))
        return chamou, resto

    def _confirmar_chamado(self, idioma):
        if self.falador is not None and hasattr(self.falador, "confirmar"):
            try:
                self.falador.confirmar(idioma)
            except Exception:
                pass

    def _tratar(self, trecho, ident=None):
        """True se o trecho virou pedido."""
        idioma = self.idioma()
        if self._esperando_pedido():
            self.ao_estado("transcrevendo")
            texto = self._transcrever_pedido(trecho, idioma)
            chamou, resto = achar_ativacao(texto)
            texto = resto if chamou and resto else texto
            self.chamado_ate = 0.0
            if texto and re.search(r"\w", texto) and not (chamou and not resto):
                self.ao_pedido(texto)
                self.ao_estado("ouvindo")
                return True
            if chamou:  # disse só "TARS" de novo: continua esperando
                self.chamado_ate = time.monotonic() + ESPERA_PEDIDO_S
                self._confirmar_chamado(idioma)
                self.ao_estado("chamado")
                return False
            self.ao_estado("ouvindo")
            return False
        chamou, resto = self._nome_no_trecho(trecho, ident, idioma)
        if not chamou:
            return False
        duracao = len(trecho) / BYTES_AMOSTRA / TAXA
        if resto or duracao > CEDO_MAX_S:
            # o pedido veio junto ("TARS, abre o Firefox"): o bom transcreve tudo
            self.ao_estado("transcrevendo")
            completo = self._transcrever_pedido(trecho, idioma)
            chamou2, resto2 = achar_ativacao(completo)
            pedido = resto2 or (resto if chamou2 else completo)
            if pedido and re.search(r"\w", pedido):
                self.ao_pedido(pedido)
                self.ao_estado("ouvindo")
                return True
        # só o nome: "Sim?" e o próximo trecho é o pedido
        self.chamado_ate = time.monotonic() + ESPERA_PEDIDO_S
        self._confirmar_chamado(idioma)
        self.ao_estado("chamado")
        return False


def sininho_wav(taxa=22050):
    """Dois toques curtos (mi-si), baixinho: "ouvi você"."""
    import io
    import wave

    amostras = array.array("h")
    for freq, dur in ((659.25, 0.09), (987.77, 0.13)):
        n = int(taxa * dur)
        for i in range(n):
            envelope = min(1.0, i / (taxa * 0.01), (n - i) / (taxa * 0.04))
            amostras.append(int(7000 * envelope * math.sin(2 * math.pi * freq * i / taxa)))
    if sys.byteorder == "big":
        amostras.byteswap()
    saida = io.BytesIO()
    with wave.open(saida, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(amostras.tobytes())
    return saida.getvalue()


# ------------------------------------------------------------
# Processo do Kokoro: "python tars_voz.py --kokoro MODELO VOZES"
# ------------------------------------------------------------
def _trabalhador_kokoro(modelo, vozes):
    """Carrega o Kokoro uma vez e gera um wav por linha recebida:
    {"texto", "voz", "lingua", "velocidade", "pausa", "destino"} -> {"ok": true}."""
    import wave

    import numpy as np
    from kokoro_onnx import Kokoro

    kokoro = Kokoro(modelo, vozes)
    print(json.dumps({"pronto": True}), flush=True)
    for linha in sys.stdin:
        try:
            p = json.loads(linha)
            velocidade = min(2.0, max(0.5, float(p.get("velocidade") or 1.0)))
            amostras, taxa = kokoro.create(p["texto"], voice=p["voz"], speed=velocidade, lang=p["lingua"])
            pausa = np.zeros(int(taxa * float(p.get("pausa") or 0)), dtype=np.float32)
            dados = np.concatenate([np.asarray(amostras, dtype=np.float32).reshape(-1), pausa])
            pcm = (np.clip(dados, -1.0, 1.0) * 32767).astype("<i2").tobytes()
            with wave.open(p["destino"], "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(int(taxa))
                w.writeframes(pcm)
            print(json.dumps({"ok": True}), flush=True)
        except Exception as e:
            print(json.dumps({"ok": False, "erro": str(e)[:300]}), flush=True)


if __name__ == "__main__" and len(sys.argv) >= 4 and sys.argv[1] == "--kokoro":
    _trabalhador_kokoro(sys.argv[2], sys.argv[3])
