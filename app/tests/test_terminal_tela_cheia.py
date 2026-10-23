"""16/10: programas de tela cheia (htop, vim, less...) abrem numa janela de terminal em vez de rodar sem terminal, onde
falhavam com "Error opening terminal" e o modelo concluía que não estavam instalados. Comando com pipe, redirecionamento
ou 'top -b' continua rodando normal (é texto). Sem sessão gráfica, a mensagem sugere um comando sem tela. O comando
perigoso continua passando pela confirmação antes."""
import os

from _util import carregar_tars

tars = carregar_tars()

for comando, esperado in (("htop", "htop"), ("sudo nano /etc/hosts", "nano"), ("vim notas.txt", "vim"), ("man ls", "man"),
                          ("TERM=xterm less x.log", "less"), ("/usr/bin/btop", "btop"), ("top", "top"),
                          ("top -bn1", None), ("top -b -n 1", None), ("htop | head", None), ("less x > y", None),
                          ("ls -la", None), ("free -h", None), ("echo htop", None), ("cd x && vim y", None)):
    assert tars.programa_de_tela(comando) == esperado, (comando, tars.programa_de_tela(comando))
print("OK: reconhece programa de tela cheia sozinho, e não com pipe, redirecionamento ou 'top -b'")

abertos = []


class Popen:
    def __init__(self, argv, **k):
        abertos.append(argv)


real_popen, real_which = tars.subprocess.Popen, tars.shutil.which
tars.subprocess.Popen = Popen
tars.shutil.which = lambda p: "/usr/bin/" + p if p in ("gnome-terminal", "xterm") else None
os.environ["DISPLAY"] = ":99"
r = tars.executar_terminal("htop")
assert r["sucesso"] and "terminal window" in r["mensagem"] and "gnome-terminal" in r["mensagem"], r
assert abertos[-1][:4] == ["gnome-terminal", "--", "bash", "-c"] and abertos[-1][4].startswith("htop;"), abertos
print("OK: htop abre numa janela de terminal e o modelo fica sabendo")

tars.shutil.which = lambda p: None
r = tars.executar_terminal("htop")
assert not r["sucesso"] and "top -bn1" in r["mensagem"]
os.environ.pop("DISPLAY", None)
os.environ.pop("WAYLAND_DISPLAY", None)
r = tars.executar_terminal("vim x")
assert not r["sucesso"] and "no graphical session" in r["mensagem"]
print("OK: sem terminal instalado ou sem sessão gráfica, a mensagem sugere um comando sem tela")

tars.subprocess.Popen, tars.shutil.which = real_popen, real_which
r = tars.executar_terminal("echo oi")
assert r["sucesso"] and "oi" in r["stdout"], r
print("OK: comando comum continua igual")
print("\nTUDO OK.")
