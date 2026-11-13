"""5.3: nenhum endereço da API do motor mora fora de tars_motor.py. É o que deixa a troca do Ollama pelo llama.cpp num lugar só."""
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import tars_motor  # noqa: E402

assert tars_motor.url("conversa", "http://127.0.0.1:11434") == "http://127.0.0.1:11434/api/chat"
assert tars_motor.url("modelos", "http://127.0.0.1:11434/") == "http://127.0.0.1:11434/api/tags"

achados = []
for arquivo in [*RAIZ.glob("*.py"), *RAIZ.glob("nucleo/*.py"), *RAIZ.glob("tars_qt/*.py"), *RAIZ.glob("tars_plataforma/*.py")]:
    if arquivo.name in ("tars_motor.py", "tars_motor_local.py"):      # o motor local é o outro lado dessa API
        continue
    for numero, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
        if re.search(r"""["'}]/api/[a-z]+""", linha):
            achados.append(f"{arquivo.name}:{numero}: {linha.strip()[:80]}")
assert not achados, "endereço do motor fora de tars_motor.py:\n" + "\n".join(achados)
print("OK: a API do motor mora em tars_motor.py")
