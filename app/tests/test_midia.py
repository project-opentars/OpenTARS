"""5.3 (F4+++): controle de música por frase (tars_midia), sem tocar nada: o gdbus, o osascript e as teclas do Windows são falsos."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["TARS_ARQUIVO_CONFIG"] = os.path.join(tempfile.mkdtemp(prefix="opentars-midia-"), "config.json")
import tars_midia as m  # noqa: E402
import tars_plataforma as plataforma  # noqa: E402

# as frases: o que é de mídia e o que NÃO é (continue/next/stop sozinhos são do chat; "toca X" é uma busca)
casos = {"pausa a música": "pause", "pause the music": "pause", "pausa": "pause", "Pause.": "pause", "dá pause": "pause", "para a música": "pause",
         "stop the music": "pause", "toca a música": "play", "continua a música": "play", "play": "play", "dá play": "play", "resume the music": "play",
         "volta a tocar": "play", "próxima música": "next", "pula a faixa": "next", "skip the song": "next", "next track": "next", "vai para a próxima": "next",
         "música anterior": "previous", "volta a música": "previous", "previous song": "previous", "go back the song": "previous",
         "que música está tocando?": "agora", "qual a música que está tocando": "agora", "what's playing": "agora", "what is this song": "agora",
         "o que está tocando agora": "agora"}
for frase, esperado in casos.items():
    assert m.acao_da_frase(frase) == esperado, (frase, m.acao_da_frase(frase), esperado)
for nao in ("continue", "next", "stop", "para", "continua", "pula", "toca Legião Urbana", "play something by Queen", "toca Faroeste Caboclo",
            "pausa o download", "para o servidor", "que música você gosta", "what song did Queen write", "abre o navegador", "o próximo passo é"):
    assert m.acao_da_frase(nao) is None, nao
print("OK: as frases de mídia, e as que parecem mas não são (continue, next, 'toca X', 'pausa o download')")

# Linux: MPRIS pelo gdbus
chamadas = []
saidas = {"ListNames": "(['org.freedesktop.DBus', ':1.9', 'org.mpris.MediaPlayer2.firefox.instance4242', 'org.mpris.MediaPlayer2.spotify'],)",
          "firefox": {"PlaybackStatus": "(<'Paused'>,)", "Metadata": "(<{'xesam:title': <'Vídeo de gatos'>}>,)"},
          "spotify": {"PlaybackStatus": "(<'Playing'>,)",
                      "Metadata": "(<{'mpris:trackid': <objectpath '/x'>, 'xesam:artist': <['Legião Urbana', 'Outro']>, 'xesam:title': <'Eduardo e Mônica'>}>,)"}}


def gdbus_falso(comando, tempo=4):
    chamadas.append(comando)
    if "ListNames" in comando[-1]:
        return saidas["ListNames"]
    destino = comando[comando.index("--dest") + 1]
    if comando[-1] == "org.freedesktop.DBus.Properties.Get" or "Properties.Get" in " ".join(comando):
        return saidas["spotify" if "spotify" in destino else "firefox"][comando[-1]]
    return "()"


m._rodar = gdbus_falso
plataforma.sistema = lambda: "linux"
assert m.agir("agora", "pt") == "Tocando agora: Eduardo e Mônica, Legião Urbana (Spotify)."
assert m.agir("agora", "en").startswith("Now playing: Eduardo e Mônica, Legião Urbana")
chamadas.clear()
assert m.agir("pause", "pt") == "Pausei."
assert chamadas[-1][chamadas[-1].index("--dest") + 1] == "org.mpris.MediaPlayer2.spotify" and chamadas[-1][-1] == "org.mpris.MediaPlayer2.Player.Pause"
saidas["spotify"]["PlaybackStatus"] = "(<'Paused'>,)"           # tudo pausado: pega o primeiro que está pausado
assert m._escolher_player(["org.mpris.MediaPlayer2.firefox.instance4242", "org.mpris.MediaPlayer2.spotify"]) == "org.mpris.MediaPlayer2.firefox.instance4242"
assert m.agir("agora", "pt") == "Está pausado: Vídeo de gatos (Firefox)."
saidas["firefox"]["PlaybackStatus"] = "(<'Stopped'>,)"
saidas["spotify"]["PlaybackStatus"] = "(<'Stopped'>,)"
assert m.agir("agora", "pt") == "Não tem nada tocando agora."
saidas["ListNames"] = "(['org.freedesktop.DBus', ':1.9'],)"
assert m.agir("next", "pt") == "Não achei nenhum player de música ou vídeo aberto."
m._rodar = lambda c, t=4: (_ for _ in ()).throw(RuntimeError("gdbus: command not found"))
assert m.agir("play", "en").startswith("I couldn't control the player (gdbus")
print("OK: Linux: escolhe o player que toca, controla pelo MPRIS, diz o que toca (inclusive aspas e acentos), e avisa quando não há player")

# macOS
plataforma.sistema = lambda: "macos"
scripts = []


def osascript_falso(comando, tempo=4):
    scripts.append(comando[-1])
    s = comando[-1]
    if "is running" in s:
        return "true\n" if "Spotify" in s else "false\n"
    if "player state" in s:
        return "playing\n"
    if "name of current track" in s:
        return "Eduardo e Mônica\n"
    if "artist of current track" in s:
        return "Legião Urbana\n"
    return ""


m._rodar = osascript_falso
assert m.agir("agora", "pt") == "Tocando agora: Eduardo e Mônica, Legião Urbana (Spotify)."
assert m.agir("next", "en") == "Next." and scripts[-1] == 'tell application "Spotify" to next track'
assert m.agir("pause", "pt") == "Pausei." and scripts[-1] == 'tell application "Spotify" to pause'
m._rodar = lambda c, t=4: "false\n"
assert m.agir("play", "pt") == "Não achei nenhum player de música ou vídeo aberto."
print("OK: macOS: Spotify e Music pelo osascript")

# Windows: teclas de mídia; "o que toca" diz que não sabe
plataforma.sistema = lambda: "windows"
assert m.agir("agora", "pt").startswith("No Windows eu consigo pausar")
teclas = []


class _Usuario:
    @staticmethod
    def keybd_event(tecla, varredura, sinalizadores, extra):
        teclas.append((tecla, sinalizadores))


class _Win:
    user32 = _Usuario


import ctypes  # noqa: E402
ctypes.windll = _Win
assert m.agir("pause", "pt") == "Pausei." and teclas == [(0xB3, 0), (0xB3, 2)]
teclas.clear()
assert m.agir("next", "en") == "Next." and teclas == [(0xB0, 0), (0xB0, 2)]
print("OK: Windows: teclas de mídia (tocar/pausar, próxima, anterior); não finge saber o que toca")

# pelo resolver do assistente (sem modelo)
plataforma.sistema = lambda: "linux"
m._rodar = gdbus_falso
saidas["ListNames"] = "(['org.mpris.MediaPlayer2.spotify'],)"
saidas["spotify"]["PlaybackStatus"] = "(<'Playing'>,)"
import tars_atalhos  # noqa: E402
fala, ok = tars_atalhos._uma_parte("pausa a música", "pt", None, {}, True)
assert ok and fala == "Pausei."
assert tars_atalhos.tars_midia.responder("toca Legião Urbana", "pt") is None, "'toca X' segue para o modelo"
print("OK: o resolver do assistente responde mídia; 'toca X' continua com o modelo")
print("TUDO OK.")
