"""Ações do sistema por frase (F4++ do PLANO_5.3.md, 07/11): volume, mudo, brilho, modo escuro, Wi-Fi, Bluetooth, não perturbe, bloquear.

Medido antes: "aumenta o volume" virava um clique num botão do navegador e várias tentativas com programas errados. Aqui a frase vira
o comando certo para esta máquina (o primeiro que existir), e passa pelo execute_terminal como qualquer outro.
Linux: o comando vai pelo execute_terminal (PipeWire/PulseAudio/ALSA, gsettings do GNOME, nmcli, rfkill, loginctl).
Windows e macOS (5.3): as mesmas frases, executadas direto por programas do próprio sistema (teclas de mídia e PowerShell no
Windows; osascript e networksetup no macOS), com confirmação no que desliga (Wi-Fi, Bluetooth). O que o sistema não deixa fazer
sem administrador (Wi-Fi e Bluetooth no Windows) a resposta diz, em vez de fingir. Nada disso foi usado num Windows ou Mac de verdade.
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


# ---------------------------------------------------------------- Windows e macOS (5.3): executado direto, sem o execute_terminal
import subprocess  # noqa: E402

TEXTOS["pt"].update({"nao_sei": "Não sei fazer isso neste sistema: {coisa}.", "falhou": "Não consegui ({erro}).", "negado": "Tudo bem, não mexi.",
                     "sem_admin": "No Windows não dá para ligar ou desligar o {coisa} sem permissão de administrador. Use o painel de ações rápidas (Win+A).",
                     "sem_blueutil": "No macOS preciso do programa blueutil para o Bluetooth (brew install blueutil)."})
TEXTOS["en"].update({"nao_sei": "I don't know how to do that on this system: {coisa}.", "falhou": "I couldn't ({erro}).", "negado": "Okay, I left it alone.",
                     "sem_admin": "On Windows I can't turn {coisa} on or off without administrator permission. Use the quick settings panel (Win+A).",
                     "sem_blueutil": "On macOS I need the blueutil program for Bluetooth (brew install blueutil)."})
CONFIRMAR = {"wifi_off": "turn off Wi-Fi", "bt_off": "turn off Bluetooth"}        # o que desliga pergunta antes (Linux não pergunta: já era assim)
COISAS = {"wifi_on": "Wi-Fi", "wifi_off": "Wi-Fi", "bt_on": "Bluetooth", "bt_off": "Bluetooth", "dnd": "Não perturbe"}


def _rodar(argv, tempo=15):
    r = subprocess.run(argv, capture_output=True, text=True, timeout=tempo)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or f"código {r.returncode}").strip().splitlines()[-1][:100] if (r.stderr or r.stdout).strip() else f"código {r.returncode}")
    return r.stdout


def _tecla_windows(tecla, vezes=1):
    import ctypes
    for _ in range(vezes):
        ctypes.windll.user32.keybd_event(tecla, 0, 0, 0)
        ctypes.windll.user32.keybd_event(tecla, 0, 2, 0)


def _powershell(comando):
    return _rodar(["powershell", "-NoProfile", "-NonInteractive", "-Command", comando])


def _brilho_windows(passo):
    _powershell("$b=(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness).CurrentBrightness;"
                f"$n=[Math]::Min(100,[Math]::Max(0,$b{'+' if passo > 0 else '-'}10));"
                "Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | "
                "Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{Timeout=1;Brightness=$n} | Out-Null")


def _tema_windows(claro):
    for nome in ("AppsUseLightTheme", "SystemUsesLightTheme"):
        _rodar(["reg", "add", r"HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "/v", nome, "/t", "REG_DWORD",
                "/d", "1" if claro else "0", "/f"])


WINDOWS = {
    "vol_mais": lambda: _tecla_windows(0xAF, 5), "vol_menos": lambda: _tecla_windows(0xAE, 5), "mudo": lambda: _tecla_windows(0xAD),
    "brilho_mais": lambda: _brilho_windows(1), "brilho_menos": lambda: _brilho_windows(-1),
    "escuro": lambda: _tema_windows(False), "claro": lambda: _tema_windows(True),
    "bloquear": lambda: _rodar(["rundll32.exe", "user32.dll,LockWorkStation"]),
}


def _osascript(script):
    return _rodar(["osascript", "-e", script])


def _wifi_mac(ligado):
    texto = _rodar(["networksetup", "-listallhardwareports"])
    m = re.search(r"Hardware Port: (?:Wi-Fi|AirPort)\s*\nDevice: (\w+)", texto)
    if not m:
        raise RuntimeError("sem placa Wi-Fi")
    _rodar(["networksetup", "-setairportpower", m.group(1), "on" if ligado else "off"])


def _bluetooth_mac(ligado):
    if not shutil.which("blueutil"):
        raise LookupError("sem_blueutil")
    _rodar(["blueutil", "--power", "1" if ligado else "0"])


MACOS = {
    "vol_mais": lambda: _osascript("set volume output volume ((output volume of (get volume settings)) + 10)"),
    "vol_menos": lambda: _osascript("set volume output volume ((output volume of (get volume settings)) - 10)"),
    "mudo": lambda: _osascript("set volume output muted (not (output muted of (get volume settings)))"),
    "brilho_mais": lambda: [_osascript('tell application "System Events" to key code 144') for _ in range(4)],
    "brilho_menos": lambda: [_osascript('tell application "System Events" to key code 145') for _ in range(4)],
    "escuro": lambda: _osascript('tell application "System Events" to tell appearance preferences to set dark mode to true'),
    "claro": lambda: _osascript('tell application "System Events" to tell appearance preferences to set dark mode to false'),
    "wifi_on": lambda: _wifi_mac(True), "wifi_off": lambda: _wifi_mac(False),
    "bt_on": lambda: _bluetooth_mac(True), "bt_off": lambda: _bluetooth_mac(False),
    "bloquear": lambda: _osascript('tell application "System Events" to keystroke "q" using {control down, command down}'),
}


def chave_da_frase(n):
    """A ação do sistema que a frase pede ("vol_mais", "escuro"...), ou None."""
    for padrao, _comando, chave in ACOES:
        if re.search(padrao, n):
            return chave
    return None


def responder_outros(n, idioma, sistema, core=None):
    """Windows e macOS: faz a ação e devolve a frase da resposta, ou None se a frase não é de uma ação do sistema (ou o sistema é
    o Linux, que segue pelo execute_terminal). `core`: o módulo tars, para a pergunta de confirmação no que desliga."""
    if sistema not in ("windows", "macos"):
        return None
    chave = chave_da_frase(n)
    if chave is None:
        return None
    textos = TEXTOS["pt" if idioma == "pt" else "en"]
    tabela = WINDOWS if sistema == "windows" else MACOS
    if chave not in tabela:
        if sistema == "windows" and chave in ("wifi_on", "wifi_off", "bt_on", "bt_off"):
            return textos["sem_admin"].format(coisa=COISAS[chave])
        return textos["nao_sei"].format(coisa=COISAS.get(chave, chave))
    if chave in CONFIRMAR and core is not None and not core._confirmar_comando_perigoso(CONFIRMAR[chave]):
        return textos["negado"]
    try:
        tabela[chave]()
    except LookupError as e:
        return textos[str(e)]
    except (OSError, RuntimeError, subprocess.SubprocessError, AttributeError) as e:
        return textos["falhou"].format(erro=str(e)[:80] or type(e).__name__)
    return textos[chave]
