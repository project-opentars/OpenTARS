"""Ações do sistema por frase (F4++ do PLANO_5.3.md, 07/11): volume, mudo, brilho, modo escuro, Wi-Fi, Bluetooth, não perturbe, bloquear.

Medido antes: "aumenta o volume" virava um clique num botão do navegador e várias tentativas com programas errados. Aqui a frase vira
o comando certo para esta máquina (o primeiro que existir), e passa pelo execute_terminal como qualquer outro.
shortcut: só Linux por enquanto (PipeWire/PulseAudio/ALSA, gsettings do GNOME, nmcli, rfkill, loginctl); no Windows e no macOS o
pedido segue para o modelo como antes.
"""
import re
import shutil

_MAIS = r"\b(aumenta|aumente|sobe|suba|mais alto|aumentar|levanta|turn up|raise|increase|louder|up)\b"
_MENOS = r"\b(abaixa|abaixe|diminui|diminua|baixa|baixe|mais baixo|reduz|reduza|turn down|lower|decrease|quieter|down)\b"


def _volume(sinal):
    if shutil.which("wpctl"):
        return f"wpctl set-volume -l 1.0 @DEFAULT_AUDIO_SINK@ 10%{sinal}"
    if shutil.which("pactl"):
        return f"pactl set-sink-volume @DEFAULT_SINK@ {sinal}10%"
    if shutil.which("amixer"):
        return f"amixer -q set Master 10%{sinal}"
    return None


def _mudo():
    if shutil.which("wpctl"):
        return "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"
    if shutil.which("pactl"):
        return "pactl set-sink-mute @DEFAULT_SINK@ toggle"
    if shutil.which("amixer"):
        return "amixer -q set Master toggle"
    return None


def _brilho(sinal):
    if shutil.which("brightnessctl"):
        return f"brightnessctl -q set 10%{sinal}"
    if shutil.which("gdbus"):
        passo = "StepUp" if sinal == "+" else "StepDown"
        return f"gdbus call --session --dest org.gnome.SettingsDaemon.Power --object-path /org/gnome/SettingsDaemon/Power --method org.gnome.SettingsDaemon.Power.Screen.{passo}"
    return None


ACOES = (   # (padrão no pedido normalizado, função que devolve o comando, chave da resposta)
    (r"\b(volume|som|audio|sound)\b.*" + _MAIS + "|" + _MAIS + r".*\b(volume|som|audio|sound)\b", lambda: _volume("+"), "vol_mais"),
    (r"\b(volume|som|audio|sound)\b.*" + _MENOS + "|" + _MENOS + r".*\b(volume|som|audio|sound)\b|\bsom mais baixo\b", lambda: _volume("-"), "vol_menos"),
    (r"\b(muta|mute|silencia|silencie|tira o som|sem som|desmuta|unmute)\b", _mudo, "mudo"),
    (r"\b(brilho|brightness|tela mais clara|screen brighter)\b.*" + _MAIS + "|" + _MAIS + r".*\b(brilho|brightness)\b", lambda: _brilho("+"), "brilho_mais"),
    (r"\b(brilho|brightness)\b.*" + _MENOS + "|" + _MENOS + r".*\b(brilho|brightness)\b", lambda: _brilho("-"), "brilho_menos"),
    (r"\b(modo escuro|tema escuro|dark mode|dark theme)\b", lambda: "gsettings set org.gnome.desktop.interface color-scheme prefer-dark" if shutil.which("gsettings") else None, "escuro"),
    (r"\b(modo claro|tema claro|light mode|light theme)\b", lambda: "gsettings set org.gnome.desktop.interface color-scheme default" if shutil.which("gsettings") else None, "claro"),
    (r"\b(desliga|desligue|desativa|desative|turn off|disable)\b.*\b(wi-?fi|wireless)\b", lambda: "nmcli radio wifi off" if shutil.which("nmcli") else None, "wifi_off"),
    (r"\b(liga|ligue|ativa|ative|turn on|enable)\b.*\b(wi-?fi|wireless)\b", lambda: "nmcli radio wifi on" if shutil.which("nmcli") else None, "wifi_on"),
    (r"\b(desliga|desligue|desativa|desative|turn off|disable)\b.*\bbluetooth\b", lambda: "rfkill block bluetooth" if shutil.which("rfkill") else None, "bt_off"),
    (r"\b(liga|ligue|ativa|ative|turn on|enable)\b.*\bbluetooth\b", lambda: "rfkill unblock bluetooth" if shutil.which("rfkill") else None, "bt_on"),
    (r"\b(nao perturbe|do not disturb|silencia as notificacoes|mute notifications)\b", lambda: "gsettings set org.gnome.desktop.notifications show-banners false" if shutil.which("gsettings") else None, "dnd"),
    (r"\b(bloqueia|bloqueie|trava|trave|lock)\b.*\b(tela|computador|pc|screen|computer)\b", lambda: "loginctl lock-session" if shutil.which("loginctl") else None, "bloquear"),
)

TEXTOS = {
    "pt": {"vol_mais": "Aumentei o volume.", "vol_menos": "Baixei o volume.", "mudo": "Troquei o mudo.", "brilho_mais": "Aumentei o brilho.",
           "brilho_menos": "Baixei o brilho.", "escuro": "Modo escuro ligado.", "claro": "Modo claro ligado.", "wifi_off": "Wi-Fi desligado.",
           "wifi_on": "Wi-Fi ligado.", "bt_off": "Bluetooth desligado.", "bt_on": "Bluetooth ligado.", "dnd": "Não perturbe ligado: as notificações não aparecem.",
           "bloquear": "Tela bloqueada.", "sem": "Não achei como fazer isso neste computador."},
    "en": {"vol_mais": "Volume turned up.", "vol_menos": "Volume turned down.", "mudo": "Mute toggled.", "brilho_mais": "Brightness up.",
           "brilho_menos": "Brightness down.", "escuro": "Dark mode on.", "claro": "Light mode on.", "wifi_off": "Wi-Fi off.", "wifi_on": "Wi-Fi on.",
           "bt_off": "Bluetooth off.", "bt_on": "Bluetooth on.", "dnd": "Do not disturb on: notifications won't pop up.", "bloquear": "Screen locked.",
           "sem": "I couldn't find a way to do that on this computer."},
}


def plano(n, idioma):
    """{'comando': ..., 'feito': frase} para a ação pedida, {'fala': ...} se a máquina não tem como, ou None."""
    for padrao, comando, chave in ACOES:
        if re.search(padrao, n):
            c = comando()
            textos = TEXTOS["pt" if idioma == "pt" else "en"]
            return {"comando": c, "feito": textos[chave]} if c else {"fala": textos["sem"]}
    return None
