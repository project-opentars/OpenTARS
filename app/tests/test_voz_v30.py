"""3.0: voz — microfone em trechos, palavra de ativação "TARS", texto pra
fala, e o Ouvinte de ponta a ponta com áudio sintético e um "Whisper" falso.
Não precisa de microfone, Whisper nem Piper instalados."""

import array
import math
import os
import tempfile

os.environ.setdefault("XDG_DATA_HOME", tempfile.mkdtemp(prefix="opentars-dados-"))
from _util import carregar_tars  # noqa: E402

tars = carregar_tars()
voz = tars.voz_lib
TAXA = voz.TAXA


def tom(segundos, amplitude=6000, freq=220):
    n = int(TAXA * segundos)
    a = array.array("h", (int(amplitude * math.sin(2 * math.pi * freq * i / TAXA)) for i in range(n)))
    return a.tobytes()


def silencio(segundos, amplitude=40):
    n = int(TAXA * segundos)
    a = array.array("h", ((amplitude if (i // 7) % 2 else -amplitude) for i in range(n)))
    return a.tobytes()


def frequencia(audio):
    """Frequência do tom no áudio (ignora o silêncio): o 'Whisper' falso
    reconhece a fala pela 'voz' (cada frase de teste tem um tom)."""
    a = array.array("h")
    a.frombytes(audio)
    fortes = [x for x in a if abs(x) > 300]
    if len(fortes) < 100:
        return 0
    trocas = sum(1 for x, y in zip(a, a[1:]) if abs(x) > 300 or abs(y) > 300 if (x < 0) != (y < 0))
    return trocas / 2 / (len(fortes) / TAXA)


# ------------------------------------------------------------
# 1. Segmentador: acha as falas no meio do silêncio
# ------------------------------------------------------------
audio = silencio(1.0) + tom(0.8) + silencio(1.0) + tom(0.1) + silencio(1.0) + tom(1.5, freq=330) + silencio(1.0)
seg = voz.Segmentador()
trechos = []
for i in range(0, len(audio), 1234):  # pedaços de tamanho qualquer, como vêm do arecord
    trechos += seg.alimentar(audio[i:i + 1234])
assert len(trechos) == 2, [len(t) for t in trechos]                    # o estalo de 0,1 s não conta
dur = [len(t) / 2 / TAXA for t in trechos]
assert 0.8 <= dur[0] <= 0.8 + (voz.SILENCIO_FIM_MS + voz.PRE_ROLL_MS) / 1000 + 0.1, dur
assert 1.5 <= dur[1] <= 1.5 + (voz.SILENCIO_FIM_MS + voz.PRE_ROLL_MS) / 1000 + 0.1, dur
assert seg.limiar == voz.LIMIAR_MINIMO, "ruído baixo: limiar mínimo"
print(f"OK: segmentador acha as 2 falas ({dur[0]:.2f}s e {dur[1]:.2f}s) e ignora o estalo de 0,1 s")

barulho = voz.Segmentador()
for _ in range(50):
    barulho.alimentar(silencio(0.1, amplitude=900))
assert barulho.limiar > 2000 and not barulho.alimentar(silencio(2, amplitude=900)), "ruído de fundo alto não é fala"
print(f"OK: com ruído de fundo (ventoinha), o limiar sobe pra {barulho.limiar:.0f} e o ruído não vira fala")

# ------------------------------------------------------------
# 2. Palavra de ativação
# ------------------------------------------------------------
casos = {
    "TARS, abre o Firefox.": (True, "abre o Firefox"),
    "Ei Tars abre o spotify": (True, "abre o spotify"),
    "Hey Tarz, what's the weather?": (True, "what's the weather"),
    "ok thars": (True, ""),
    "Tars.": (True, ""),
    "OpenTARS, fecha a aba": (True, "fecha a aba"),
    "Oye Tars, abre el navegador": (True, "abre el navegador"),
    "eu tava vendo aquele filme com o tars ontem": (False, ""),
    "abre o firefox": (False, ""),
    "Mars is a planet": (False, ""),
    "tarsila do amaral": (False, ""),
    "Ei… TARS, abre o Firefox": (True, "abre o Firefox"),       # "…" vira 3 caracteres no NFKD
    "Olá TARS, ﬁnaliza o download": (True, "ﬁnaliza o download"),
}
for frase, esperado in casos.items():
    assert voz.achar_ativacao(frase) == esperado, (frase, voz.achar_ativacao(frase))
print(f"OK: 'TARS' no começo (e variações do Whisper) chama; no meio da frase ou parecido, não ({len(casos)} casos)")

# ------------------------------------------------------------
# 3. Texto -> fala
# ------------------------------------------------------------
md = ("## Pronto!\n\nAbri o **Firefox** e pesquisei [RTX 5060](https://x.com/y).\n\n"
      "```bash\nsudo apt update\n```\n- item um\n- item dois 🚀\n| a | b |\n")
fala = voz.limpar_para_fala(md)
assert fala == "Pronto!. Abri o Firefox e pesquisei RTX 5060. item um. item dois" or "sudo" not in fala, fala
assert "**" not in fala and "http" not in fala and "sudo" not in fala and "🚀" not in fala and "|" not in fala, fala
longo = voz.limpar_para_fala("Frase curta. " * 200)
assert len(longo) <= voz.LIMITE_FALA and longo.endswith("."), longo[-30:]
print(f"OK: markdown, código, links e emoji saem da fala: '{fala}'")

# ------------------------------------------------------------
# 4. Programas e o que falta
# ------------------------------------------------------------
assert voz.comando_gravar(lambda p: p == "parecord")[0] == "parecord"
assert voz.comando_gravar(lambda p: False) is None
assert voz.comando_tocar(lambda p: p in ("aplay", "paplay"))[0] == "paplay"
falta = voz.o_que_falta("pt_BR", existe=lambda p: False, tem_modulo=lambda m: False)
assert falta == ["faster-whisper", "kokoro-onnx", "voz", "gravador", "tocador"], falta
# 4.0: Kokoro (um modelo pra todas as vozes); Piper só de reserva
assert voz.arquivo_voz("pt_BR").name == voz.arquivo_voz("en").name == "kokoro-v1.0.onnx"
assert voz.voz_kokoro("pt_BR") == ("pf_dora", "pt-br") and voz.voz_kokoro("de") == ("af_heart", "en-us")
assert voz.urls_voz_piper("pt_BR")[0].endswith("en/en_US/lessac/medium/en_US-lessac-medium.onnx?download=true")
texto = tars.descrever_falta_voz(["kokoro-onnx", "gravador"])
assert "kokoro-onnx" in texto and "alsa-utils" in texto, texto
print("OK: acha gravador/tocador que houver, diz o que falta (em português) e de onde vem a voz de cada idioma")

# ------------------------------------------------------------
# 5. Ouvinte de ponta a ponta (áudio sintético, Whisper falso)
# ------------------------------------------------------------


class WhisperFalso:
    """Devolve o texto 'falado' no trecho: pela frequência do tom (chaves
    >= 100, em Hz) ou pela duração (chaves pequenas, em segundos)."""

    def __init__(self, falas):
        self.falas = falas
        self.chamadas = 0

    def transcrever(self, audio, idioma=None, dica="", rapido=False):
        self.chamadas += 1
        if min(self.falas) >= 100:
            f = frequencia(audio)
            return min(self.falas.items(), key=lambda kv: abs(kv[0] - f))[1]
        dur = len(audio) / 2 / TAXA
        return min(self.falas.items(), key=lambda kv: abs(kv[0] - dur))[1]


def rodar_ouvinte(modo, blocos, falas):
    pedidos, estados = [], []
    rapido, bom = WhisperFalso(falas), WhisperFalso(falas)
    ouv = voz.Ouvinte(pedidos.append, "pt_BR", modo=modo, ao_estado=estados.append,
                      gravar=lambda: iter(blocos), transcritor=bom, transcritor_ativacao=rapido)
    ouv._rodar()
    return pedidos, estados, rapido, bom


def picotar(audio, n=3200):
    return [audio[i:i + n] for i in range(0, len(audio), n)]


falas = {200: "o tempo está bom hoje", 300: "TARS, abre a calculadora", 400: "Tars", 500: "fecha o spotify"}
audio = (silencio(0.5) + tom(1.0, freq=200) + silencio(1) + tom(1.8, freq=300) + silencio(1) + tom(0.6, freq=400)
         + silencio(1) + tom(1.3, freq=500) + silencio(1))
pedidos, estados, rapido, bom = rodar_ouvinte("ativacao", picotar(audio), falas)
assert pedidos == ["abre a calculadora", "fecha o spotify"], (pedidos, falas)
assert "chamado" in estados and estados[-1] == "parado"
assert rapido.chamadas == 3 and bom.chamadas == 2, (rapido.chamadas, bom.chamadas)
print("OK: conversa normal é ignorada; 'TARS, abre a calculadora' vira pedido; 'TARS' + pausa + 'fecha o spotify' também")

pedidos, estados, _, bom = rodar_ouvinte("uma_vez", picotar(silencio(0.3) + tom(1.2) + silencio(1) + tom(1.2)),
                                         {1.9: "abre o gimp", 1.8: "abre o gimp", 2.0: "abre o gimp"})
assert pedidos == ["abre o gimp"] and bom.chamadas == 1, (pedidos, bom.chamadas)
print("OK: 'Falar agora' (Ctrl+M): a primeira fala é o pedido, sem precisar dizer TARS, e para de ouvir")


class FaladorFalso:
    def __init__(self):
        import threading
        self.falando = threading.Event()


f = FaladorFalso()
f.falando.set()
pedidos = []
ouv = voz.Ouvinte(pedidos.append, "pt_BR", modo="uma_vez", falador=f,
                  gravar=lambda: iter(picotar(silencio(0.3) + tom(1.2) + silencio(1))),
                  transcritor=WhisperFalso({1.9: "TARS, desliga"}), transcritor_ativacao=WhisperFalso({1.9: "x"}))
ouv._rodar()
assert pedidos == [], "enquanto o openTARS fala, ele não ouve a própria voz"
print("OK: enquanto está falando, não escuta (a própria voz não vira pedido)")

# ------------------------------------------------------------
# 6. Responder falando só quando a pessoa quer
# ------------------------------------------------------------
falou = []
tars.falador = lambda: type("F", (), {"falar": lambda self, texto, idioma, ao_terminar=None: falou.append(texto) or True})()
tars.o_que_falta_voz = lambda: []
tars.salvar_config_voz(falar=False)
assert not tars.falar_resposta("Abri o Firefox.") and falou == []
assert tars.falar_resposta("Abri o Firefox.", forcar=True) and falou == ["Abri o Firefox."]
tars.salvar_config_voz(falar=True)
assert tars.config_voz()["falar"] and tars.falar_resposta("Pronto.")
assert not tars.falar_resposta(tars.RESPOSTA_INTERROMPIDA)
tars.o_que_falta_voz = lambda: ["voz"]
assert not tars.falar_resposta("Pronto.", forcar=True), "sem a voz instalada, fica quieto"
print("OK: fala a resposta se 'responder falando' estiver ligado ou se o pedido veio por voz")

# duas falas seguidas: a primeira acabar não pode "destravar" o microfone
fal = voz.Falador()
fal._comecou()
fal._comecou()
fal._acabou()
assert fal.falando.is_set(), "a segunda fala ainda está tocando"
fal._acabou()
assert not fal.falando.is_set()
print("OK: com duas falas sobrepostas, o microfone só volta quando a última acaba")

# ------------------------------------------------------------
# 7. Resposta rápida ao "TARS" (Endurance Neo: Whisper sempre em inglês)
# ------------------------------------------------------------
class ModeloFalso:
    def __init__(self):
        self.opcoes = []

    def transcribe(self, dados, **opcoes):
        self.opcoes.append(dict(opcoes))
        if "without_timestamps" in opcoes:
            raise TypeError("transcribe() got an unexpected keyword argument 'without_timestamps'")
        return iter([type("S", (), {"text": " TARS, open the browser."})()]), None


tr = voz.Transcritor("teste")
voz.Transcritor._cache["teste"] = modelo = ModeloFalso()
assert tr.transcrever(silencio(0.5), "pt_BR", rapido=True) == "TARS, open the browser."
o = modelo.opcoes[-1]
assert o["language"] == "pt" and o["initial_prompt"] == "TARS, openTARS." and o["temperature"] == 0.0
assert o["max_new_tokens"] == 12 and o["beam_size"] == 1 and "without_timestamps" not in o
assert tr.transcrever(silencio(0.5), "en", rapido=True) and modelo.opcoes[-1]["language"] == "en"
assert voz.achar_ativacao("Tas, open Firefox") == (False, "")
print("OK: Whisper no idioma da voz (pt/en), só com o nome de dica, sem refazer com outras temperaturas; "
      "faster-whisper antigo funciona")


class WhisperCronometrado(WhisperFalso):
    def __init__(self, falas, nome, linha):
        super().__init__(falas)
        self.nome, self.linha, self.aquecido = nome, linha, False

    def transcrever(self, audio, idioma=None, dica="", rapido=False):
        self.linha.append((self.nome, round(len(audio) / 2 / TAXA, 2)))
        return super().transcrever(audio, idioma, rapido=rapido)

    def aquecer(self):
        self.aquecido = True


class FaladorConfirma:
    def __init__(self):
        self.falando = threading.Event()
        self.confirmados = []

    def confirmar(self, idioma):
        self.confirmados.append(idioma)

    def preparar_confirmacao(self, idioma):
        pass


import threading  # noqa: E402

linha, estados, pedidos = [], [], []
audio = silencio(0.4) + tom(2.2) + silencio(1.0)
rapido = WhisperCronometrado({220: "TARS, abre"}, "tiny", linha)
bom = WhisperCronometrado({220: "TARS, abre a calculadora"}, "base", linha)


def estado(e):
    estados.append((e, len(linha)))


ouv = voz.Ouvinte(pedidos.append, "pt_BR", ao_estado=estado, gravar=lambda: iter(picotar(audio, 1600)),
                  transcritor=bom, transcritor_ativacao=rapido, falador=FaladorConfirma())
ouv._rodar()
assert rapido.aquecido and bom.aquecido, "os dois Whisper são aquecidos antes da primeira fala"
assert pedidos == ["abre a calculadora"], pedidos
assert [n for n, _ in linha] == ["tiny", "base"], linha           # o tiny não roda de novo no fim
assert linha[0][1] <= voz.CEDO_MAX_S, linha                       # só o começo da fala
chamado = next(i for i, (e, _) in enumerate(estados) if e == "chamado")
transcrevendo = next(i for i, (e, _) in enumerate(estados) if e == "transcrevendo")
assert chamado < transcrevendo and estados[0][0] == "carregando"
print("OK: 'TARS, abre a calculadora' — o nome é conferido com a pessoa ainda falando (tela mostra na hora); "
      "no fim, só o pedido é transcrito")

# "TARS" sozinho: responde "Sim?" e a próxima fala é o pedido; depois, conversa sem o nome
f = FaladorConfirma()
audio = silencio(0.4) + tom(0.5, freq=400) + silencio(1.0) + tom(1.2, freq=250) + silencio(1.0)
pedidos = []
ouv = voz.Ouvinte(pedidos.append, "pt_BR", gravar=lambda: iter(picotar(audio, 1600)), falador=f,
                  transcritor=WhisperFalso({250: "abre o gimp", 400: "Tars"}),
                  transcritor_ativacao=WhisperFalso({400: "Tars.", 250: "abre o gimp"}))
ouv._rodar()
assert f.confirmados == ["pt_BR"] and pedidos == ["abre o gimp"], (f.confirmados, pedidos)
ouv._thread = type("T", (), {"is_alive": lambda self: True})()
ouv.abrir_conversa()
assert ouv._esperando_pedido()
print("OK: 'TARS' sozinho responde 'Sim?' (na voz do idioma) e ouve o pedido; depois de responder, dá pra "
      "continuar sem dizer o nome")

wav = voz.sininho_wav()
assert wav[:4] == b"RIFF" and len(wav) > 5000
print("OK: sininho de confirmação gerado na hora (sem arquivo nenhum pra baixar)")

# 5.0: "segurar para falar": soltar o botão fecha a fala em andamento sem esperar o silêncio
seg = voz.Segmentador()
seg.alimentar(b"\x00\x00" * (voz.TAXA * 1))                # 1 s de silêncio: aprende o ruído de fundo
fala_parcial = bytes(voz.array.array("h", [8000, -8000] * (voz.TAXA // 2)))   # 1 s de "fala", sem silêncio depois
assert seg.alimentar(fala_parcial) == [] and seg.falando_ms > 0
trecho = seg.encerrar()
assert trecho and seg.falando_ms == 0 and seg.encerrar() is None
seg2 = voz.Segmentador()
seg2.alimentar(b"\x00\x00" * (voz.TAXA * 1))
seg2.alimentar(bytes(voz.array.array("h", [8000, -8000] * 800)))   # 100 ms: curto demais
assert seg2.encerrar() is None, "estalo curtíssimo não vira pedido"

# ... e pelo Ouvinte: soltou o botão, o pedido sai
silencio_ini = b"\x00\x00" * (voz.TAXA * 1)
fala = bytes(voz.array.array("h", [8000, -8000] * (voz.TAXA // 2)))
pedidos5 = []
ouv5 = voz.Ouvinte(pedidos5.append, "en", modo="uma_vez", aquecer=False,
                   transcritor=type("T", (), {"transcrever": lambda self, a, i=None, dica=None, rapido=False, vocabulario=None: "open the browser",
                                              "aquecer": lambda self: None})(),
                   transcritor_ativacao=type("T", (), {"transcrever": lambda self, *a, **k: "", "aquecer": lambda self: None})())


def fonte5():
    yield silencio_ini
    yield fala
    ouv5.terminar_fala()          # soltou o botão
    yield b"\x00\x00" * 480      # o próximo bloco já fecha o trecho
    yield b"\x00\x00" * 480


ouv5._gravar = fonte5
ouv5.iniciar()
ouv5._thread.join(timeout=10)
assert pedidos5 == ["open the browser"], pedidos5
print("OK: soltar o botão fecha a fala em andamento (segurar para falar)")

print("\nTUDO OK.")
