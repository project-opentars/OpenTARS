"""5.3 (F4++): ações do sistema por frase no Windows e no macOS (volume, mudo, brilho, tema, Wi-Fi, Bluetooth, bloquear), com os
programas do sistema trocados por falsos: nada muda no computador. Confirmação no que desliga; o que o sistema não deixa, diz."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["TARS_ARQUIVO_CONFIG"] = os.path.join(tempfile.mkdtemp(prefix="opentars-sis-"), "config.json")
import tars_atalhos  # noqa: E402
import tars_plataforma as plataforma  # noqa: E402
import tars_sistema_frases as sf  # noqa: E402

N = tars_atalhos.normalizar
chamadas, teclas = [], []
sf._rodar = lambda argv, tempo=15: chamadas.append(argv) or ""
sf._tecla_windows = lambda tecla, vezes=1: teclas.append((tecla, vezes))
perguntas = []


class Core:
    _resposta = True

    def _confirmar_comando_perigoso(self, texto):
        perguntas.append(texto)
        return self._resposta


core = Core()

# as frases viram a mesma ação nos dois sistemas
for frase, chave in (("aumenta o volume", "vol_mais"), ("turn the volume down", "vol_menos"), ("muta o som", "mudo"), ("aumenta o brilho", "brilho_mais"),
                     ("diminui o brilho", "brilho_menos"), ("liga o modo escuro", "escuro"), ("turn on light mode", "claro"),
                     ("desliga o wifi", "wifi_off"), ("turn on bluetooth", "bt_on"), ("bloqueia a tela", "bloquear")):
    assert sf.chave_da_frase(N(frase)) == chave, (frase, sf.chave_da_frase(N(frase)))
assert sf.chave_da_frase(N("abre o navegador")) is None and sf.responder_outros(N("aumenta o volume"), "pt", "linux", core) is None
print("OK: as frases viram a mesma ação; no Linux o caminho é o do execute_terminal (responder_outros devolve None)")

# Windows
assert sf.responder_outros(N("aumenta o volume"), "pt", "windows", core) == "Aumentei o volume." and teclas[-1] == (0xAF, 5)
assert sf.responder_outros(N("abaixa o volume"), "pt", "windows", core) == "Baixei o volume." and teclas[-1] == (0xAE, 5)
assert sf.responder_outros(N("muta"), "en", "windows", core) == "Mute toggled." and teclas[-1] == (0xAD, 1)
chamadas.clear()
assert sf.responder_outros(N("liga o modo escuro"), "pt", "windows", core) == "Modo escuro ligado."
assert len(chamadas) == 2 and all(c[0] == "reg" and "AppsUseLightTheme" in c[3:] or "SystemUsesLightTheme" in c for c in chamadas) and chamadas[0][-2] == "0"
chamadas.clear()
assert sf.responder_outros(N("aumenta o brilho"), "pt", "windows", core) == "Aumentei o brilho." and chamadas[0][0] == "powershell" and "+10" in chamadas[0][-1]
assert sf.responder_outros(N("bloqueia o computador"), "en", "windows", core) == "Screen locked." and chamadas[-1][0] == "rundll32.exe"
assert "administrador" in sf.responder_outros(N("liga o wifi"), "pt", "windows", core) and "administrator" in sf.responder_outros(N("turn off bluetooth"), "en", "windows", core)
assert not perguntas, "o que o Windows não deixa fazer nem pergunta"
assert sf.responder_outros(N("liga o não perturbe"), "pt", "windows", core) == "Não sei fazer isso neste sistema: Não perturbe."
print("OK: Windows: volume e mudo por teclas de mídia, tema pelo registro, brilho pelo PowerShell, bloquear; Wi-Fi e Bluetooth dizem que precisam de administrador")

# macOS
chamadas.clear()
assert sf.responder_outros(N("aumenta o volume"), "pt", "macos", core) == "Aumentei o volume." and "+ 10" in chamadas[-1][-1]
assert sf.responder_outros(N("liga o modo escuro"), "en", "macos", core) == "Dark mode on." and "dark mode to true" in chamadas[-1][-1]
chamadas.clear()
assert sf.responder_outros(N("diminui o brilho"), "pt", "macos", core) == "Baixei o brilho." and [c[-1] for c in chamadas].count('tell application "System Events" to key code 145') == 4
assert sf.responder_outros(N("bloqueia a tela"), "pt", "macos", core) == "Tela bloqueada." and "control down, command down" in chamadas[-1][-1]
sf._rodar = lambda argv, tempo=15: chamadas.append(argv) or ("Hardware Port: Wi-Fi\nDevice: en7\n" if argv[1] == "-listallhardwareports" else "")
chamadas.clear()
assert sf.responder_outros(N("liga o wifi"), "pt", "macos", core) == "Wi-Fi ligado." and chamadas[-1] == ["networksetup", "-setairportpower", "en7", "on"]
assert not perguntas, "ligar não pergunta"
print("OK: macOS: volume e mudo e brilho e tema e bloquear pelo osascript, Wi-Fi pelo networksetup (acha a placa)")

# o que desliga pergunta antes; "não" não mexe em nada
chamadas.clear()
core._resposta = False
assert sf.responder_outros(N("desliga o wifi"), "pt", "macos", core) == "Tudo bem, não mexi." and perguntas == ["turn off Wi-Fi"] and not chamadas
core._resposta = True
assert sf.responder_outros(N("desliga o wifi"), "pt", "macos", core) == "Wi-Fi desligado." and chamadas[-1][-1] == "off"
sf.shutil.which = lambda nome: None
assert "blueutil" in sf.responder_outros(N("liga o bluetooth"), "pt", "macos", core)
print("OK: o que desliga pergunta antes (e 'não' não mexe em nada); Bluetooth no Mac pede o blueutil")

# falhas do sistema viram frase, não erro
def quebra(argv, tempo=15):
    raise RuntimeError("sem permissão")


sf._rodar = quebra
assert sf.responder_outros(N("aumenta o volume"), "pt", "macos", core) == "Não consegui (sem permissão)."
print("OK: erro do sistema vira frase")

# pelo resolver do assistente (sem modelo)
plataforma.sistema = lambda: "windows"
sf._rodar = lambda argv, tempo=15: ""
tars_atalhos.memoria = lambda *a: None          # o teste não tem a memória do app
fala, ok = tars_atalhos._uma_parte("aumenta o volume", "pt", core, {}, False)
assert ok and fala == "Aumentei o volume."
print("OK: o resolver do assistente usa as ações no Windows (linux=False)")
print("TUDO OK.")
