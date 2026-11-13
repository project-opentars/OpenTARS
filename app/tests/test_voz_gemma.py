"""5.3 (decisão do Enzo, 13/11): o pedido falado vai para o Gargantua 2.5 pelo motor; o Whisper é a reserva.
Sem modelo de verdade: motor, Gemma e Whisper são de mentira. O caminho real foi medido à parte (tests/medir_voz.py)."""
import base64
import io
import json
import os
import sys
import wave

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tars_motor_local as motor  # noqa: E402
import tars_voz as voz  # noqa: E402


class Whisper:
    def __init__(self):
        self.chamadas = []

    def transcrever(self, audio, idioma=None, dica=None, rapido=False, vocabulario=None):
        self.chamadas.append(rapido)
        return "pelo whisper"

    def aquecer(self):
        self.chamadas.append("aquecer")


audio = b"\x01\x00" * 1600
w = Whisper()
gemma = []
t = voz.TranscritorGemma(w, motor=lambda: ("http://motor", "ProjectOpenTARS/Gargantua-2.5:latest"),
                         transcrever=lambda a, i, host, modelo: gemma.append((host, modelo)) or "abre o firefox")
assert t.transcrever(audio, "pt_BR") == "abre o firefox" and t.ultimo == "gemma" and w.chamadas == []
assert t.transcrever(audio, "pt_BR", rapido=True) == "pelo whisper" and w.chamadas == [True] and len(gemma) == 1
print("OK: o pedido vai para o Gemma; a palavra de ativação (rápido) continua no Whisper")

for falha in (lambda *a: "", lambda *a: (_ for _ in ()).throw(OSError("motor caiu"))):
    t = voz.TranscritorGemma(w, motor=lambda: ("http://motor", "x"), transcrever=falha)
    assert t.transcrever(audio, "en") == "pelo whisper" and t.ultimo == "whisper"
t = voz.TranscritorGemma(w, motor=lambda: None, transcrever=lambda *a: 1 / 0)
assert t.transcrever(audio, "en") == "pelo whisper"
print("OK: resposta vazia, erro ou motor sem modelo que ouve: vale o Whisper")


class Resposta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


enviados = []


def abrir(pedido, timeout=None):
    enviados.append(json.loads(pedido.data))
    return Resposta(json.dumps({"message": {"content": enviados[-1]["_resposta"] if "_resposta" in enviados[-1] else ' "Abre o Firefox." '}}).encode())


assert voz.transcrever_com_gemma(audio, "pt_BR", "http://motor", "M", abrir=abrir) == "Abre o Firefox."
corpo = enviados[-1]
mensagem = corpo["messages"][0]
assert corpo["model"] == "M" and corpo["think"] is False and "português" in mensagem["content"]
with wave.open(io.BytesIO(base64.b64decode(mensagem["audio"][0]))) as arq:
    assert (arq.getframerate(), arq.getnchannels(), arq.getsampwidth(), arq.readframes(10_000)) == (16000, 1, 2, audio)
print("OK: o áudio vai como WAV 16 kHz mono no campo audio, com o pedido de transcrever no idioma da voz")

convertido = motor.para_openai({"messages": [mensagem]}, "ProjectOpenTARS/Gargantua-2.5:latest")
partes = convertido["messages"][0]["content"]
assert partes[0]["type"] == "text" and partes[1] == {"type": "input_audio", "input_audio": {"data": mensagem["audio"][0], "format": "wav"}}
assert motor._tem_imagem({"messages": [mensagem]})
print("OK: o motor passa o áudio ao llama-server como input_audio e carrega o projetor")

for silencio in ("[silence]", "(inaudible)"):
    assert voz.transcrever_com_gemma(audio, "en", "http://motor", "M", abrir=lambda p, timeout=None: Resposta(
        json.dumps({"message": {"content": silencio}}).encode())) == ""
print("OK: '[silence]' e '(inaudible)' contam como nada dito (o Whisper tenta)")

longa = " ".join(["palavra"] * 40)
assert voz.transcrever_com_gemma(audio, "en", "http://motor", "M", abrir=lambda p, timeout=None: Resposta(
    json.dumps({"message": {"content": longa}}).encode())) == ""
assert voz.MODELOS_QUE_OUVEM == ("ProjectOpenTARS/Gargantua-2.5:latest",)
print("OK: texto demais para o tempo de fala volta para o Whisper; só o 2.5 ouve (o Lite respondia em vez de transcrever)")

os.environ["TARS_MOTOR"] = "ollama"
assert voz._motor_que_ouve() is None
print("OK: com o Ollama escolhido o áudio não vai ao modelo (o Ollama ignoraria o campo e o modelo inventaria)")
print("TUDO OK.")
