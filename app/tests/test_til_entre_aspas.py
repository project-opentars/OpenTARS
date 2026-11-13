"""10/11: o ~ entre aspas (mkdir -p "~/x") criava uma pasta chamada "~" e a ferramenta dizia sucesso. til_entre_aspas() corrige;
aqui com um bash de verdade numa casa temporária e com o mini-shell."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _util  # noqa: F401,E402
import tars  # noqa: E402

f = tars.til_entre_aspas
assert f('mkdir -p "~/Documentos/Jogos"') == 'mkdir -p ~/"Documentos/Jogos"'
assert f("mkdir -p '~/Downloads/Faculdade'") == "mkdir -p ~/'Downloads/Faculdade'"
assert f('mkdir -p "~/Área de Trabalho/Receitas" && echo oi > "~/Área de Trabalho/Receitas/lista.txt"') == \
    'mkdir -p ~/"Área de Trabalho/Receitas" && echo oi > ~/"Área de Trabalho/Receitas/lista.txt"'
assert f('ls "~"') == "ls ~"
for intacto in ("mkdir -p ~/Documentos/Jogos", 'echo "a ~ b"', 'cat "$HOME/x"', 'mkdir -p "/tmp/~/x"', "ls -la"):
    assert f(intacto) == intacto, intacto
print("OK: o ~ sai das aspas só no começo de um caminho; o resto fica como está")

casa = tempfile.mkdtemp(prefix="til-")
env = {**os.environ, "HOME": casa}
for comando in ('mkdir -p "~/Documentos/Jogos"', "mkdir -p '~/Downloads/Faculdade'", 'mkdir -p "~/Área de Trabalho/Receitas"'):
    cwd = tempfile.mkdtemp(prefix="cwd-")
    subprocess.run(["bash", "-c", f(comando)], cwd=cwd, env=env, check=True)
    assert not os.path.exists(os.path.join(cwd, "~")), "criou a pasta '~' literal"
assert all(os.path.isdir(os.path.join(casa, p)) for p in ("Documentos/Jogos", "Downloads/Faculdade", "Área de Trabalho/Receitas"))
print("OK: no bash de verdade as pastas saem na casa, e nenhuma pasta '~' aparece na pasta atual")

import tars_shell as sh  # noqa: E402
os.environ["HOME"] = casa
r = sh.executar(f('mkdir -p "~/Mini/Pasta"'))
assert os.path.isdir(os.path.join(casa, "Mini", "Pasta")), r
print("OK: o mini-shell (Windows e macOS) também cria na casa")
print("TUDO OK.")
