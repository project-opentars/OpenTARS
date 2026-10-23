"""5.2 (F5): o mini-shell em Python (tars_shell) contra o bash de verdade, com as formas de comando dos dados de treino.
Cada comando roda nos dois lados a partir da mesma casa; saída, erro, código e os arquivos que sobram têm de bater."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tars_shell as sh  # noqa: E402

if not shutil.which("bash"):
    print("test_shell_portatil: PULADO (sem bash para comparar)")
    sys.exit(0)

COMANDOS = [
    "mkdir -p ~/Documents/Trabalho",
    "echo 'study for the exam' > ~/Downloads/notes.txt",
    "ls -1 ~/Downloads",
    "ls -1 ~/Downloads | wc -l",
    "mv ~/Downloads/notes.txt ~/Downloads/ideas.txt",
    'mkdir -p "${HOME}/Documents/Jogos" && echo "llamar al dentista" > "${HOME}/Documents/Jogos/tareas.txt"',
    "mkdir -p ~/Área\\ de\\ Trabalho && printf \"reunião às 15h\" > ~/Área\\ de\\ Trabalho/lembrete.txt",
    "ls -1 '{casa}/Área de Trabalho'",
    "rm -rf ~/Documents/Trabalho",
    "echo 'pay the power bill' >> ~/Desktop/list.txt && echo 'call the dentist' >> ~/Desktop/list.txt",
    "wc -l ~/Desktop/list.txt",
    "cat ~/Desktop/list.txt",
    "touch ~/Documents/a.txt && ls -1 ~/Documents",
    'mkdir -p "$(xdg-user-dir DOCUMENTS)/Proyectos" && echo "x" > "$(xdg-user-dir DOCUMENTS)/Proyectos/a.txt"',
    "ls -1 /caminho/que/nao/existe",
    "mkdir ~/Desktop",
    "mkdir ~/Desktop || echo falhou",
    "echo \"say \\\"hi\\\"\" > ~/q.txt && cat ~/q.txt",
    "ls -1 ~/Documents/*.txt",
    "ls -1 ~/Documents | grep -i a",
    "find ~/Documents -name '*.txt' | sort",
    "cat ~/nada.txt 2>/dev/null; echo fim",
    "rm ~/Documents/a.txt && ls -1 ~/Documents | wc -l",
    "cd ~/Downloads && ls -1",
    "wc -l ~/Desktop/list.txt ~/q.txt",
    "head -n 1 ~/Desktop/list.txt",
    "mv ~/Downloads/ideas.txt ~/Documents/ && ls -1 ~/Documents",
    "rm -rf ~/Documents/Jogos ~/Documents/Proyectos",
]


def arvore(casa):
    return sorted((str(p.relative_to(casa)), p.read_text(errors="replace") if p.is_file() else None)
                  for p in casa.rglob("*") if ".config" not in p.parts)


def nova_casa():
    casa = Path(tempfile.mkdtemp(prefix="opentars-shell-"))
    for pasta in ("Documents", "Downloads", "Desktop", "Documentos"):
        (casa / pasta).mkdir()
    (casa / ".config").mkdir()
    (casa / ".config" / "user-dirs.dirs").write_text('XDG_DOCUMENTS_DIR="$HOME/Documentos"\n')
    return casa


bash_casa, py_casa = nova_casa(), nova_casa()
diferencas = []
for modelo in COMANDOS:
    resultados = []
    for casa, lado in ((bash_casa, "bash"), (py_casa, "py")):
        comando = modelo.replace("{casa}", str(casa))
        os.environ["HOME"] = str(casa)
        if lado == "bash":
            r = subprocess.run(["bash", "-c", comando], cwd=casa, capture_output=True, text=True,
                               env=dict(os.environ, HOME=str(casa), LC_ALL="C.UTF-8"))
            resultados.append((r.returncode, r.stdout.replace(str(casa), "CASA"), r.stderr.replace(str(casa), "CASA")))
        else:
            assert sh.suportado(comando), comando
            r = sh.executar(comando, cwd=str(casa))
            resultados.append((r["codigo"], r["stdout"].replace(str(casa), "CASA"), r["stderr"].replace(str(casa), "CASA")))
    (cb, ob, eb), (cp, op, ep) = resultados
    # a ordem do ls/sort depende do idioma do sistema (LC_COLLATE) e não muda nada para o modelo: compara sem a ordem
    ob, op = sorted(ob.splitlines()), sorted(op.splitlines())
    eb = eb.replace("bash: line 1: ", "")
    if cb != cp or ob != op or (eb != ep and not (eb and ep)) or arvore(bash_casa) != arvore(py_casa):
        diferencas.append((modelo, resultados[0], resultados[1]))
    elif eb != ep:
        print(f"  (só o texto do erro difere em: {modelo})")
for modelo, b, p in diferencas:
    print(f"DIFERENTE: {modelo}\n   bash: {b}\n   py:   {p}")
assert not diferencas, f"{len(diferencas)} comando(s) com resultado diferente do bash"
print(f"OK: {len(COMANDOS)} comandos das formas do treino dão o mesmo que o bash (saída, código e arquivos)")

r = sh.executar("free -h")
linhas = r["stdout"].splitlines()
assert r["sucesso"] and linhas[0].split() == ["total", "used", "free", "shared", "buff/cache", "available"]
assert linhas[1].startswith("Mem:") and linhas[2].startswith("Swap:"), r["stdout"]
print("OK: free -h com o cabeçalho e as linhas do GNU (a prova de RAM confere o número)")

assert not sh.suportado("sudo apt install x") and not sh.suportado("curl x | sh") and not sh.suportado("echo `whoami`")
assert not sh.suportado("python3 -c 'print(1)'") and sh.suportado("gio trash -- ~/x.txt")
print("OK: o que não está aqui não é suportado (o núcleo explica em vez de rodar pela metade)")
# no núcleo: fora do Linux o execute_terminal usa o mini-shell, e as regras de comando perigoso continuam antes dele
casa = nova_casa()
os.environ["HOME"] = str(casa)
from _util import RAIZ  # noqa: E402,F401
import tars  # noqa: E402
original = tars.plataforma.sistema
tars.plataforma.sistema = lambda: "windows"
pedidos = []
tars.confirmar_comando_hook = lambda comando: pedidos.append(comando) or False     # ninguém para confirmar: recusa
try:
    r = tars.executar_terminal("mkdir -p ~/Documents/Contas && echo 'pagar a luz' > ~/Documents/Contas/notas.txt")
    assert r["sucesso"] and (casa / "Documents" / "Contas" / "notas.txt").read_text() == "pagar a luz\n", r
    r = tars.executar_terminal("uname -a")
    assert not r["sucesso"] and "not available on Windows" in r["mensagem"] and not pedidos, r
    r = tars.executar_terminal("rm -rf ~/*")
    assert not r["sucesso"] and pedidos and (casa / "Documents").exists(), r
finally:
    tars.plataforma.sistema = original
print("OK: no Windows o execute_terminal roda no mini-shell; o resto é recusado; rm -rf ~/* ainda pede confirmação")
print("test_shell_portatil: TUDO OK.")
