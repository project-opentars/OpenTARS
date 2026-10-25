"""5.2: o `opentars` do terminal como processo de verdade (nos três sistemas): --version, --help, -p, --chat com pedido, o
chat interativo por stdin e o diagnóstico, contra um Ollama de mentira. Nenhum pode cair com Traceback nem sair com código
errado. Pegaria o terminal quebrado no Windows e no macOS."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import RAIZ  # noqa: E402

import fake_ollama  # noqa: E402

servidor, url = fake_ollama.subir(modelos=["ProjectOpenTARS/Gargantua-2:latest"], resposta="Olá, tudo certo por aqui.")
casa = tempfile.mkdtemp(prefix="opentars-cli-")
env = dict(os.environ, HOME=casa, USERPROFILE=casa, APPDATA=casa, LOCALAPPDATA=casa, XDG_CONFIG_HOME=casa + "/.config",
           OLLAMA_HOST=url, TARS_IDIOMA="en", TARS_SEM_AVISO_VERSAO="1", TARS_SEM_ATALHO="1", TARS_DIR_LOG=casa + "/log",
           TARS_ARQUIVO_CONFIG=casa + "/config.json", TARS_ARQUIVO_SESSOES=casa + "/sessoes.json", TARS_GARGANTUA="completo",
           TARS_ARQUIVO_AUTOTESTE=casa + "/autoteste.txt", PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
env.pop("QT_QPA_PLATFORM", None)


def rodar(argumentos, entrada=None, ambiente=None, espera=120):
    r = subprocess.run([sys.executable, str(Path(RAIZ) / "tars.py"), *argumentos], input=entrada, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=espera, env=ambiente or env, cwd=casa)
    return r.returncode, r.stdout + r.stderr


def sem_queda(nome, saida):
    assert "Traceback" not in saida and "Error:" not in saida.split("\n\n")[0][:0], (nome, saida[-1500:])


codigo, saida = rodar(["--version"])
assert codigo == 0 and "5.2" in saida and "Traceback" not in saida, (codigo, saida)
codigo, saida = rodar(["--help"])
assert codigo == 0 and "--chat" in saida and "Traceback" not in saida, (codigo, saida[-800:])
print("OK: --version e --help")

codigo, saida = rodar(["-p", "say hello"])
assert codigo == 0 and "Olá, tudo certo por aqui." in saida and "Traceback" not in saida, (codigo, saida[-1500:])
print("OK: -p responde e sai com 0")

codigo, saida = rodar(["--chat", "say hello"])
assert codigo == 0 and "Olá, tudo certo por aqui." in saida and "Traceback" not in saida, (codigo, saida[-1500:])
print("OK: --chat com pedido responde e sai com 0")

codigo, saida = rodar(["--chat"], entrada="say hello\n/sair\n")
assert codigo == 0 and "Olá, tudo certo por aqui." in saida and "Traceback" not in saida, (codigo, saida[-1500:])
assert "\x01" not in saida and "\x02" not in saida, "marcas do readline vazaram para a tela (sem readline, no Windows)"
print("OK: o chat interativo por stdin responde, sai com /sair e não deixa lixo de readline")

codigo, saida = rodar(["--chat"], entrada="say hello\n/sair\n", ambiente=dict(env, PYTHONUTF8="0", PYTHONIOENCODING="cp1252"))
assert codigo == 0 and "Traceback" not in saida, (codigo, saida[-1500:])
print("OK: o chat não cai com a saída em cp1252 (sem UTF-8)")

# o modelo pede ferramentas de verdade: criar pasta e arquivo pelo execute_terminal (no Windows, o mini-shell em Python)
servidor.roteiro = [{"ferramenta": ("execute_terminal", {"command": "mkdir Projeto"})},
                    {"ferramenta": ("execute_terminal", {"command": "echo ola > Projeto/nota.txt"})},
                    {"ferramenta": ("execute_terminal", {"command": "ls Projeto"})},
                    {"texto": "Pronto: a pasta Projeto está criada."}]
codigo, saida = rodar(["-p", "create a folder called Projeto with a note inside"])
assert codigo == 0 and "Traceback" not in saida, (codigo, saida[-2000:])
assert (Path(casa) / "Projeto").is_dir() and (Path(casa) / "Projeto" / "nota.txt").exists(), (os.listdir(casa), saida[-2000:])
servidor.roteiro = None
print("OK: o terminal executa ferramentas de verdade (mkdir, echo > arquivo, ls)")

# a conversa interativa também usa ferramentas
servidor.roteiro = [{"ferramenta": ("execute_terminal", {"command": "mkdir Outra"})}, {"texto": "Feito."}]
codigo, saida = rodar(["--chat"], entrada="create Outra\n/sair\n")
assert codigo == 0 and "Traceback" not in saida and (Path(casa) / "Outra").is_dir(), (codigo, os.listdir(casa), saida[-2000:])
servidor.roteiro = None
print("OK: o chat interativo executa ferramentas")

codigo, saida = rodar(["--diagnostico"])
assert "Traceback" not in saida, (codigo, saida[-1500:])
print("OK: --diagnostico não cai")
servidor.shutdown()
print("test_cli_portatil: TUDO OK.")
