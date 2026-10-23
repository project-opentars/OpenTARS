"""O instalador não segura a instalação com o download de 2,5 GB quando não há terminal para mostrá-lo.

Pela loja de aplicativos (PackageKit) o script roda sem terminal: um `ollama pull` na frente deixava a barra da loja
parada em 0% por minutos enquanto o Ollama já estava em 50%. Sem terminal, o download vai pra segundo plano (o assistente
de primeiro uso acompanha o mesmo download). Com terminal, continua na frente, com a barra do Ollama."""
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
setup = (RAIZ / "empacotamento" / "setup.sh").read_text(encoding="utf-8")
inicio = setup.index('MODELO_GARGANTUA="${TARS_MODELO_GARGANTUA:-ProjectOpenTARS/Gargantua-2}"')
fim = setup.index("# 4. Modelo de conversa")
bloco = setup[inicio:fim]
assert "gargantua_segundo_plano" in bloco and "[ -t 1 ]" in bloco

pasta = Path(tempfile.mkdtemp())
(pasta / "bin").mkdir()
registro = pasta / "chamadas.log"
fim_do_pull = pasta / "pull-terminou"
falso = pasta / "bin" / "ollama"
falso.write_text(f'#!/bin/bash\necho "ollama $*" >> "{registro}"\nsleep 2\ntouch "{fim_do_pull}"\n')
falso.chmod(0o755)
(pasta / "harness.sh").write_text(
    'servico_pronto=1\n'
    'msg()   { echo "MSG: $*"; }\n'
    'aviso() { echo "AVISO: $*"; }\n'
    't() { echo "T:$1"; }\n'
    'modelos_instalados() { echo ""; }\n' + bloco + '\necho "FIM-DO-BLOCO"\n')
env = dict(os.environ, PATH=f"{pasta / 'bin'}:{os.environ['PATH']}")


def rodar(com_terminal):
    fim_do_pull.unlink(missing_ok=True)
    registro.unlink(missing_ok=True)
    t0 = time.time()
    if com_terminal:
        r = subprocess.run(["script", "-qec", f"bash {pasta / 'harness.sh'}", "/dev/null"], env=env, capture_output=True,
                           text=True, timeout=60)
    else:
        r = subprocess.run(["bash", str(pasta / "harness.sh")], env=env, capture_output=True, text=True, timeout=60)
    return r.stdout, time.time() - t0


# 1) SEM terminal: o bloco termina logo, o pull roda solto e nada de "não baixou" (ele ainda está baixando)
saida, segundos = rodar(com_terminal=False)
assert "FIM-DO-BLOCO" in saida and "T:gargantua_segundo_plano" in saida, saida
assert "T:nao_baixou" not in saida and "T:pode_demorar" not in saida, saida
assert segundos < 1.5, f"o instalador esperou o download ({segundos:.1f}s): a loja ficaria parada"
limite = time.time() + 10
while not fim_do_pull.exists() and time.time() < limite:
    time.sleep(0.1)
assert fim_do_pull.exists(), "o download em segundo plano não rodou até o fim"
assert "ollama pull ProjectOpenTARS/Gargantua" in registro.read_text()
print(f"OK: sem terminal o instalador termina em {segundos:.1f}s e o download segue solto, em segundo plano")

# 2) COM terminal: baixa na frente (a barra do Ollama aparece), como sempre foi
if shutil.which("script"):
    saida, segundos = rodar(com_terminal=True)
    assert "T:pode_demorar" in saida and "T:gargantua_segundo_plano" not in saida, saida
    assert segundos >= 2 and fim_do_pull.exists(), f"deveria esperar o download na frente ({segundos:.1f}s)"
    assert "ollama pull ProjectOpenTARS/Gargantua" in registro.read_text()
    print(f"OK: com terminal o download continua na frente ({segundos:.1f}s), com a barra do Ollama")
else:
    print("PULADO (com terminal): comando 'script' não encontrado")

# 3) já instalado: não baixa nada (antes e depois da mudança)
(pasta / "harness.sh").write_text((pasta / "harness.sh").read_text().replace('modelos_instalados() { echo ""; }',
                                                                              'modelos_instalados() { echo "ProjectOpenTARS/Gargantua:latest"; }'))
fim_do_pull.unlink(missing_ok=True)
registro.unlink(missing_ok=True)
saida = subprocess.run(["bash", str(pasta / "harness.sh")], env=env, capture_output=True, text=True, timeout=30).stdout
assert "T:gargantua_ja" in saida and not registro.exists(), saida
print("OK: com o Gargantua já instalado não baixa nada")

print("\nTUDO OK.")
