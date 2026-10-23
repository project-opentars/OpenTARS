"""4.0 Endurance: voz natural (Kokoro) e ouvir melhor (Whisper, "TARS").

- 5.0 Tesseract: voz em inglês e em português (Kokoro pf_dora/pm_alex/pm_santa, Whisper multilíngue);
- texto preparado pra fala (contas, datas, caminhos, unidades, "openTARS");
- fala frase a frase (a primeira toca enquanto as outras são geradas) e o
  "Parar" corta no meio;
- voz escolhida e velocidade (config.json -> Kokoro);
- Whisper escolhido pelo hardware, "TARS" mais tolerante, frases fantasma descartadas.
"""

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

for var in ("XDG_RUNTIME_DIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
    os.environ[var] = tempfile.mkdtemp(prefix=f"opentars-{var.lower()}-")
os.environ["TARS_ARQUIVO_SESSOES"] = os.path.join(tempfile.mkdtemp(), "sessoes.json")

from _util import carregar_tars  # noqa: E402

tars = carregar_tars()
voz = tars.voz_lib

# 1. Texto -> fala (Endurance Neo: a voz é só em inglês)
P = voz.preparar_para_fala
casos = {
    "Opened the calculator: 12 x 8 = 96.": "Opened the calculator: 12 times 8 equals 96.",
    "The result is 8,148.": "The result is 8148.",
    "I created /home/sam/Desktop/notes.txt for you.": "I created notes.txt for you.",
    "You have 3.5 GB free (45%).": "You have 3.5 gigabytes free (45 percent).",
    "Today is 2026-10-01.": "Today is October 1, 2026.",
    "Your screen is 1920x1080.": "Your screen is 1920 by 1080.",
    "It takes 3-5 minutes.": "It takes 3 to 5 minutes.",
    "281 - 54 = 227": "281 minus 54 equals 227",
    "I am Gargantua, the openTARS AI. You can call me TARS.":
        "I am Gargantua, the open Tars AI. You can call me Tars.",
}
for entrada, esperado in casos.items():
    assert P(entrada, "en") == esperado, (entrada, P(entrada, "en"))
assert P("12 x 8 = 96, on 2026-10-01; 1,234 files", "en") == "12 times 8 equals 96, on October 1, 2026; 1234 files"
assert P("Done! Opened Firefox.") == "Done! Opened Firefox."
print("OK: math, dates, paths and units become natural English speech")

frases = voz.dividir_frases("Oi. Abri o Firefox e pesquisei o que você pediu, já está na tela. Pronto! "
                            "Quer que eu salve a página nos seus favoritos? " + "Uma frase bem comprida, " * 20 + "fim.")
assert len(frases) >= 3 and all(len(f) <= 270 for f in frases) and frases[0].startswith("Oi."), frases
assert " ".join(frases).replace("  ", " ").startswith("Oi. Abri o Firefox")
print(f"OK: resposta longa vira {len(frases)} trechos (o primeiro toca enquanto os outros são gerados)")

# 2. Voz escolhida e velocidade (Kokoro, só inglês)
assert set(voz.VOZES_DISPONIVEIS) == {"en", "pt_BR"}
assert set(voz.VOZES_DISPONIVEIS["en"]) == {"heart", "bella", "michael", "emma"}
assert set(voz.VOZES_DISPONIVEIS["pt_BR"]) == {"dora", "alex", "santa"}
assert voz.IDIOMAS_COM_VOZ == ("en", "pt_BR") and voz.tem_voz("en") and voz.tem_voz("pt_BR") and not voz.tem_voz("de")
assert voz.nome_da_voz("en") == "heart" and voz.voz_kokoro("en") == ("af_heart", "en-us")
assert voz.nome_da_voz("pt_BR") == "dora" and voz.voz_kokoro("pt_BR") == ("pf_dora", "pt-br")
assert voz.voz_kokoro("de") == ("af_heart", "en-us"), "idioma sem voz cai na voz em inglês"
assert voz.voz_kokoro("pt_BR", "santa") == ("pm_santa", "pt-br")
voz.configurar(vozes={"en": "michael", "pt_BR": "alex"}, velocidade=1.25)
assert voz.voz_kokoro("en") == ("am_michael", "en-us") and voz.voz_kokoro("pt_BR") == ("pm_alex", "pt-br")
assert voz.voz_kokoro("en", "emma") == ("bf_emma", "en-gb")
assert voz.PREFERENCIAS["velocidade"] == 1.25
voz.configurar(velocidade=9)
assert voz.PREFERENCIAS["velocidade"] == voz.VELOCIDADE_MAX
voz.configurar(vozes={"en": "nao-existe"}, velocidade=1.0)
assert voz.nome_da_voz("en") == "heart"

tars.i18n.definir_idioma("en")
ok, msg = tars.escolher_voz("dora")
assert not ok and "heart" in msg
for arquivo in voz.arquivos_kokoro():  # já baixado: não vai pra internet
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_bytes(b"x" * 2000)
ok, msg = tars.escolher_voz("Bella")
assert ok and tars.preferencias_voz()["vozes"]["en"] == "bella" and voz.voz_kokoro("en")[0] == "af_bella"
assert tars.definir_velocidade_voz("1,1")[0] and abs(voz.PREFERENCIAS["velocidade"] - 1.1) < 1e-9
assert not tars.definir_velocidade_voz("rápido")[0]
assert "Bella" in tars.frase_de_teste_voz()
print("OK: Kokoro voices (Heart, Bella, Michael, Emma); choice and speed go from config.json to Kokoro")

# 2a. Português (5.0): vozes pf_dora / pm_alex / pm_santa, Whisper multilíngue, texto falado em português
tars.i18n.definir_idioma("pt_BR")
assert tars.voz_no_idioma() and tars.voz_atual() == "dora"
ok, msg = tars.escolher_voz("heart")
assert not ok and "dora" in msg
ok, msg = tars.escolher_voz("Santa")
assert ok and tars.preferencias_voz()["vozes"]["pt_BR"] == "santa" and voz.voz_kokoro("pt_BR") == ("pm_santa", "pt-br")
assert voz._idioma_whisper["l"] == "pt_BR"
voz._config_whisper.clear()
assert voz.config_whisper(forcar=True, memoria=(2500, 6144))["pedido"] == ("small", "cpu", "int8")
assert voz.config_whisper(forcar=True, memoria=(5600, 6144))["ativacao"] == ("base", "cuda", "int8_float16")
voz._config_whisper.clear()
assert voz.CONFIRMACOES["pt_BR"] == "Sim?"
assert voz.preparar_para_fala("12 x 8 = 96 em 2026-10-01 (16GB, 1.234 arquivos, 50%)", "pt_BR") == \
    "12 vezes 8 igual a 96 em primeiro de outubro de 2026 (16 gigabytes, 1234 arquivos, 50 por cento)"
assert voz.e_alucinacao("Legendas pela comunidade Amara.org") and voz.e_alucinacao("Obrigado por assistir!")
assert not voz.e_alucinacao("abre o navegador")
tars.i18n.definir_idioma("en")
voz._config_whisper.clear()
tars.aplicar_preferencias_voz()
print("OK: voz em português (Dora, Alex, Santa), Whisper multilíngue, números/datas/unidades falados em português")

# 2b. Whisper escolhido pelo hardware (modelos .en no processador)
voz._config_whisper.clear()
assert voz.config_whisper(forcar=True, memoria=(5600, 6144))["pedido"] == ("large-v3-turbo", "cuda", "int8_float16")
assert voz.config_whisper(forcar=True, memoria=(2500, 6144))["pedido"] == ("small.en", "cpu", "int8")
assert voz.config_whisper(forcar=True, memoria=(3000, 12288))["pedido"][1] == "cuda"
medir_placa = voz._memoria_da_placa
voz._memoria_da_placa = lambda: None       # sem placa de vídeo (antes media a placa de verdade e dependia da VRAM livre)
assert voz.config_whisper(forcar=True, memoria=None)["ativacao"] == ("base.en", "cpu", "int8")
voz._memoria_da_placa = medir_placa
voz._config_whisper["placa_falhou"] = True
assert voz.config_whisper(forcar=True, memoria=(5600, 6144))["pedido"][1] == "cpu"
voz._config_whisper.clear()
print("OK: Whisper large-v3-turbo on the GPU when there is room, small.en on the CPU; GPU failure -> CPU")

# 2c. "TARS" mais tolerante, sem ligar à toa; frases inventadas pelo Whisper
for texto in ("Tars, open Firefox", "Tarz, what time is it", "hey Thars, close Discord",
              "Dars, search for a recipe", "ok tares open spotify", "Tarzo open the calculator"):
    chamou, resto = voz.achar_ativacao(texto)
    assert chamou and resto, (texto, chamou, resto)
for texto in ("Tas, open Firefox", "stars", "we were talking about tars last night at dinner", "starship"):
    assert not voz.achar_ativacao(texto)[0], texto
assert voz.parece_chamado("Taz, open firefox") and not voz.parece_chamado("open firefox")
for texto in ("Thanks for watching!", "Subtitles by the Amara.org community", "Please subscribe", "...", "♪♪"):
    assert voz.e_alucinacao(texto), texto
assert not voz.e_alucinacao("open the browser and search thanks for watching")
print("OK: 'TARS' heard in more spellings (tarz, thars, dars...), not 'tas'; Whisper ghost phrases dropped")

# 2d. Transcrição do pedido: vocabulário dos apps, beam 5, detector de voz
class ModeloFalso:
    def __init__(self, texto):
        self.texto, self.opcoes = texto, []

    def transcribe(self, dados, **opcoes):
        self.opcoes.append(opcoes)
        return iter([type("S", (), {"text": self.texto})()]), None


voz.Transcritor._cache["pedido-teste"] = m = ModeloFalso(" open Steam")
tr = voz.Transcritor("pedido-teste")
assert tr.transcrever(b"\0\0" * 1600, "en", vocabulario=["Steam", "Discord"]) == "open Steam"
o = m.opcoes[-1]
assert o["beam_size"] == 5 and o["vad_filter"] is True and "Steam" in o["hotwords"] and "initial_prompt" not in o, o
voz.Transcritor._cache["fantasma"] = ModeloFalso(" Thanks for watching!")
assert voz.Transcritor("fantasma").transcrever(b"\0\0" * 1600, "en") == ""
print("OK: pedido transcrito com os nomes dos apps como vocabulário, busca mais cuidadosa e sem frases fantasma")

# 2e. Segunda chance: o modelo rápido ouviu "Taz", o bom confere e acha o "TARS"
class TranscritorFalso:
    def __init__(self, texto):
        self.texto, self.vocabularios = texto, []

    def transcrever(self, audio, idioma=None, dica=None, rapido=False, vocabulario=None):
        self.vocabularios.append(vocabulario)
        return self.texto


rapido_ruim, bom = TranscritorFalso("Taz, open"), TranscritorFalso("Tars, open Firefox.")
ouv = voz.Ouvinte(lambda texto: None, "en", transcritor=bom, transcritor_ativacao=rapido_ruim, aquecer=False,
                  vocabulario=lambda: ["Firefox", "Steam"])
assert ouv._nome_no_trecho(b"\0\0" * 16000 * 2, None, "en") == (True, "open Firefox")
assert bom.vocabularios[-1] == ["Firefox", "Steam"]
rapido_nada = TranscritorFalso("Good morning everyone")
ouv2 = voz.Ouvinte(lambda texto: None, "en", transcritor=bom, transcritor_ativacao=rapido_nada, aquecer=False)
bom.vocabularios.clear()
assert ouv2._nome_no_trecho(b"\0\0" * 16000 * 2, None, "en") == (False, "") and not bom.vocabularios
print("OK: 'Taz' no modelo rápido -> o modelo bom confere e acha 'TARS'; fala comum nem passa pelo modelo bom")

# 3. Fala frase a frase, com Parar no meio
geradas, tocadas = [], []


class FaladorTeste(voz.Falador):
    def _gerar(self, texto, idioma, destino, cancelar=None):
        time.sleep(0.05)
        geradas.append(texto)
        Path(destino).write_bytes(b"RIFF" + b"\0" * 100)
        return True

    def _tocar_arquivo(self, tocador, wav, cancelar):
        if cancelar.is_set():
            return
        tocadas.append(geradas[len(tocadas)])
        time.sleep(0.15)


f = FaladorTeste(tocar=["true"])
texto = "Primeira frase, com um pouco de texto pra ter tamanho. Segunda frase, também com bastante texto. " \
        "Terceira frase, a última, igualmente longa pra não juntar."
f._falar_de_fato(texto, "en")
assert tocadas == geradas and len(tocadas) == 3, (geradas, tocadas)
assert not f.falando.is_set()
assert not list(Path(tempfile.gettempdir()).glob("opentars-fala-*.wav")), "wav temporário ficou pra trás"
geradas.clear(), tocadas.clear()
t = threading.Thread(target=f._falar_de_fato, args=(texto, "en"))
t.start()
time.sleep(0.12)
f.parar()
t.join(3)
assert not t.is_alive() and len(tocadas) < 3 and not f.falando.is_set(), tocadas
print("OK: fala frase a frase, sem sobrar arquivo, e o Parar corta no meio")

print("\nTUDO OK.")
