"""5.3 (F4+++): controle de música e vídeo por frase, sem o modelo: "pausa a música", "próxima faixa", "que música está tocando?".

Linux: qualquer player que fale MPRIS (Spotify, VLC, Rhythmbox, Firefox, Chromium, o YouTube no navegador...) pelo `gdbus`, que vem
com o GNOME e o glib. Windows: as teclas de mídia do sistema (tocar/pausar, próxima, anterior); o Windows não deixa um programa
simples ler o que está tocando, então "que música é?" diz que não sabe. macOS: Spotify e Music pelo `osascript`.
Só age quando a frase pede (nunca sozinho), e nunca abre nem fecha programas. Não foi usado com um player de verdade fora do Linux.
"""
import re
import subprocess
import sys
import unicodedata

import tars_plataforma as plataforma

TEXTOS = {
    "pt": {"play_pause": "Pronto.", "pause": "Pausei.", "play": "Toquei.", "next": "Próxima.", "previous": "Voltei.", "stop": "Parei.",
           "nenhum": "Não achei nenhum player de música ou vídeo aberto.", "tocando": "Tocando agora: {titulo}{artista} ({app}).",
           "pausado": "Está pausado: {titulo}{artista} ({app}).", "nada": "Não tem nada tocando agora.",
           "nao_sei": "No Windows eu consigo pausar, tocar e pular, mas não sei dizer o que está tocando.", "falhou": "Não consegui controlar o player ({erro})."},
    "en": {"play_pause": "Done.", "pause": "Paused.", "play": "Playing.", "next": "Next.", "previous": "Back.", "stop": "Stopped.",
           "nenhum": "I didn't find any music or video player open.", "tocando": "Now playing: {titulo}{artista} ({app}).",
           "pausado": "Paused: {titulo}{artista} ({app}).", "nada": "Nothing is playing right now.",
           "nao_sei": "On Windows I can pause, play and skip, but I can't tell what is playing.", "falhou": "I couldn't control the player ({erro})."},
}
METODOS = {"play_pause": "PlayPause", "pause": "Pause", "play": "Play", "next": "Next", "previous": "Previous", "stop": "Stop"}
TECLAS_WINDOWS = {"play_pause": 0xB3, "pause": 0xB3, "play": 0xB3, "next": 0xB0, "previous": 0xB1, "stop": 0xB2}
COMANDOS_MAC = {"play_pause": "playpause", "pause": "pause", "play": "play", "next": "next track", "previous": "previous track", "stop": "pause"}
PLAYERS_MAC = ("Spotify", "Music")


def _t(chave, idioma, **kw):
    s = TEXTOS["pt" if idioma == "pt" else "en"][chave]
    return s.format(**kw) if kw else s


def normalizar(texto):
    return unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower().strip(" .!?,")


def _rodar(comando, tempo=4):
    """O texto de saída, ou levanta OSError / SubprocessError / RuntimeError. (Os testes trocam esta função por uma falsa.)"""
    r = subprocess.run(comando, capture_output=True, text=True, timeout=tempo)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or f"código {r.returncode}").strip()[:120])
    return r.stdout


# ---------------------------------------------------------------- Linux: MPRIS pelo gdbus
def _players_mpris():
    saida = _rodar(["gdbus", "call", "--session", "--dest", "org.freedesktop.DBus", "--object-path", "/org/freedesktop/DBus",
                    "--method", "org.freedesktop.DBus.ListNames"])
    return [n for n in re.findall(r"'(org\.mpris\.MediaPlayer2\.[^']+)'", saida)]


def _propriedade(player, nome):
    return _rodar(["gdbus", "call", "--session", "--dest", player, "--object-path", "/org/mpris/MediaPlayer2", "--method",
                   "org.freedesktop.DBus.Properties.Get", "org.mpris.MediaPlayer2.Player", nome])


def _estado(player):
    """'Playing', 'Paused' ou 'Stopped'; '' se não respondeu."""
    try:
        m = re.search(r"'(Playing|Paused|Stopped)'", _propriedade(player, "PlaybackStatus"))
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return ""
    return m.group(1) if m else ""


def _escolher_player(players):
    """O que está tocando; senão o que está pausado; senão o primeiro."""
    estados = {p: _estado(p) for p in players}
    for desejado in ("Playing", "Paused"):
        for p, e in estados.items():
            if e == desejado:
                return p
    return players[0] if players else None


def _nome_do_player(player):
    nome = player.split("org.mpris.MediaPlayer2.", 1)[-1]
    return re.sub(r"\.instance\d+$", "", nome).capitalize()


def _metadados(player):
    texto = _propriedade(player, "Metadata")
    titulo = re.search(r"'xesam:title': <'((?:[^'\\]|\\.)*)'>", texto)
    artista = re.search(r"'xesam:artist': <\['((?:[^'\\]|\\.)*)'", texto)
    desescapar = lambda s: s.replace("\\'", "'").replace("\\\\", "\\")  # noqa: E731
    return (desescapar(titulo.group(1)) if titulo else "", desescapar(artista.group(1)) if artista else "")


def _linux(acao, idioma):
    players = _players_mpris()
    if not players:
        return _t("nenhum", idioma)
    player = _escolher_player(players)
    if acao == "agora":
        titulo, artista = _metadados(player)
        estado = _estado(player)
        if not titulo or estado == "Stopped":
            return _t("nada", idioma)
        return _t("tocando" if estado == "Playing" else "pausado", idioma, titulo=titulo,
                  artista=f", {artista}" if artista else "", app=_nome_do_player(player))
    _rodar(["gdbus", "call", "--session", "--dest", player, "--object-path", "/org/mpris/MediaPlayer2", "--method",
            f"org.mpris.MediaPlayer2.Player.{METODOS[acao]}"])
    return _t(acao, idioma)


# ---------------------------------------------------------------- Windows e macOS
def _windows(acao, idioma):
    if acao == "agora":
        return _t("nao_sei", idioma)
    import ctypes
    tecla = TECLAS_WINDOWS[acao]
    ctypes.windll.user32.keybd_event(tecla, 0, 0, 0)          # aperta e solta a tecla de mídia
    ctypes.windll.user32.keybd_event(tecla, 0, 2, 0)
    return _t(acao, idioma)


def _mac(acao, idioma):
    aberto = [p for p in PLAYERS_MAC if _rodar(["osascript", "-e", f'application "{p}" is running']).strip() == "true"]
    if not aberto:
        return _t("nenhum", idioma)
    player = aberto[0]
    if acao == "agora":
        estado = _rodar(["osascript", "-e", f'tell application "{player}" to player state as string']).strip()
        if estado not in ("playing", "paused"):
            return _t("nada", idioma)
        titulo = _rodar(["osascript", "-e", f'tell application "{player}" to name of current track']).strip()
        artista = _rodar(["osascript", "-e", f'tell application "{player}" to artist of current track']).strip()
        return _t("tocando" if estado == "playing" else "pausado", idioma, titulo=titulo, artista=f", {artista}" if artista else "", app=player)
    _rodar(["osascript", "-e", f'tell application "{player}" to {COMANDOS_MAC[acao]}'])
    return _t(acao, idioma)


def agir(acao, idioma="pt"):
    """Faz a ação ("play_pause", "pause", "play", "next", "previous", "stop" ou "agora") e devolve a frase da resposta."""
    try:
        sistema = plataforma.sistema()
        return {"windows": _windows, "macos": _mac}.get(sistema, _linux)(acao, idioma)
    except (OSError, RuntimeError, subprocess.SubprocessError, AttributeError) as e:
        return _t("falhou", idioma, erro=str(e)[:80] or type(e).__name__)


# ---------------------------------------------------------------- entender a frase
_MIDIA = r"(musica|musicas|faixa|song|songs|track|music|player|spotify|video|videos|podcast)"
_ACOES = (
    ("agora", re.compile(rf"^(que|qual|what)\b.*\b{_MIDIA}\b.*\b(tocando|esta tocando|playing|is this)\b|^(what'?s|what is) (this song|playing( now)?)$|"
                         r"^(que|qual) (musica|faixa) (e|eh|esta tocando)( essa| esta| agora)?$|^o que esta tocando( agora)?$")),
    ("next", re.compile(rf"^(pula|pule|passa|passe|skip|next)\b( a| o| the)? {_MIDIA}$|^(proxima|proximo|next) (musica|faixa|song|track|video)$|"
                        r"^(vai|va|ir) (para|pra|a|to) (a )?(proxima|next)( (musica|faixa|song|track))?$")),
    ("previous", re.compile(rf"^(volta|volte|previous|go back)\b( a| o| the)? {_MIDIA}$|^(musica|faixa) anterior$|^(previous|last) (song|track|music)$")),
    ("pause", re.compile(rf"^(pausa|pause|pare|para|stop)\b( a| o| the) {_MIDIA}$|^(pausa|pause)$|^(da|de|dar) pause$|^(pausa|pause) {_MIDIA}$")),
    ("play", re.compile(rf"^(toca|toque|continua|continue|retoma|retome|resume|play|unpause)\b( a| o| the)? {_MIDIA}$|^(play)$|^(da|de|dar) play$|"
                        r"^(volta|volte) a tocar$")),
)


def acao_da_frase(pedido):
    """A ação de mídia que a frase pede, ou None. Só frases completas e sem objeto: "toca Legião Urbana" NÃO entra (é uma busca)."""
    n = normalizar(pedido)
    if len(n) > 80:
        return None
    for acao, regra in _ACOES:
        if regra.search(n):
            return acao
    return None


def responder(pedido, idioma):
    acao = acao_da_frase(pedido)
    return agir(acao, idioma) if acao else None
