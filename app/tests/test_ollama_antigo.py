"""17/10: baixar um modelo que pede um Ollama mais novo (o Gargantua Lite em Qwen3.5) dá uma mensagem que diz o que fazer, não o
erro cru do Ollama ("412" / "requires a newer version of Ollama")."""
import io
import json
import urllib.error

from _util import RAIZ  # noqa: F401

import tars_primeiro_uso as pu


class Resposta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


linhas = b'{"status": "pulling manifest"}\n{"error": "pull model manifest: 412: this model requires a newer version of Ollama"}\n'
ok, erro = pu.baixar_modelo("ProjectOpenTARS/Gargantua:lite", "http://x", abrir=lambda p, timeout=0: Resposta(linhas))
assert not ok and "install.sh" in erro and "412" not in erro, erro


def http_412(p, timeout=0):
    raise urllib.error.HTTPError("http://x", 412, "x", {}, io.BytesIO(json.dumps({"error": "requires a newer version"}).encode()))


ok, erro = pu.baixar_modelo("x", "http://x", abrir=http_412)
assert not ok and "install.sh" in erro, erro
ok, erro = pu.baixar_modelo("x", "http://x", abrir=lambda p, timeout=0: Resposta(b'{"error": "file does not exist"}\n'))
assert erro == "file does not exist", "os outros erros continuam como vêm"
print("OK: Ollama velho demais vira 'atualize o Ollama'; os outros erros continuam iguais")
print("\nTUDO OK.")
