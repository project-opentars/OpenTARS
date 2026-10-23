"""4.0 Endurance Neo: aviso de versão nova.
(4.6: a lixeira, o desfazer e a área de transferência saíram.)

Tudo numa pasta pessoal falsa (HOME/XDG em pastas temporárias)."""

import json
import os
import sys
import tempfile
from pathlib import Path

CASA = tempfile.mkdtemp(prefix="opentars-casa-")
os.environ["HOME"] = CASA
for var, sub in (("XDG_CONFIG_HOME", ".config"), ("XDG_DATA_HOME", ".local/share"), ("XDG_CACHE_HOME", ".cache")):
    os.environ[var] = os.path.join(CASA, sub)
os.environ["TARS_ARQUIVO_SESSOES"] = os.path.join(CASA, "sessoes.json")

from _util import carregar_tars  # noqa: E402

tars = carregar_tars()


# ------------------------------------------------------------
# 1. Aviso de versão nova
# ------------------------------------------------------------
at = tars.atualizacao
publicado = 'VERSAO = "4.1"\nCODINOME = "Endurance Max"\nREVISAO = 2099010101\n'
assert at.ler_versao(publicado) == {"revisao": 2099010101, "versao": "4.1", "codinome": "Endurance Max"}
assert at.ler_versao("<html>404</html>") is None
cache = Path(CASA) / "versao.json"
del os.environ["TARS_SEM_AVISO_VERSAO"]
chamadas = []


def buscar():
    chamadas.append(1)
    return publicado


assert at.versao_nova(tars.REVISAO, buscar=buscar, cache=cache, agora=1000)["versao"] == "4.1"
assert at.versao_nova(tars.REVISAO, buscar=buscar, cache=cache, agora=1000 + 3600)
assert len(chamadas) == 1, "a segunda vez, no mesmo dia, vem do cache"
assert at.versao_nova(tars.REVISAO, buscar=buscar, cache=cache, agora=1000 + 25 * 3600) and len(chamadas) == 2
assert at.versao_nova(2100000000, buscar=buscar, cache=cache, agora=1000 + 25 * 3600) is None
assert at.versao_nova(tars.REVISAO, buscar=lambda: 1 / 0, cache=Path(CASA) / "v2.json") is None, "sem internet: quieto"
assert at.ler_versao(open(tars.__file__, encoding="utf-8").read())["revisao"] == tars.REVISAO
os.environ["TARS_SEM_AVISO_VERSAO"] = "1"
assert at.versao_nova(0, buscar=buscar, cache=Path(CASA) / "v3.json") is None
del os.environ["TARS_SEM_AVISO_VERSAO"]
aviso = tars.aviso_versao_nova(buscar=lambda: publicado)
assert aviso and "4.1 Endurance Max" in aviso, aviso
os.environ["TARS_SEM_AVISO_VERSAO"] = "1"
print("OK: aviso de versão nova (GitHub, 1x por dia, quieto sem internet, TARS_SEM_AVISO_VERSAO=1 desliga)")

for idioma in ("pt_BR", "en"):
    with open(os.path.join(os.path.dirname(tars.__file__), "idiomas", f"{idioma}.json"), encoding="utf-8") as f:
        assert "versao.nova" in json.load(f), idioma
print("OK: textos do aviso de versão nos dois idiomas")

print("\nTUDO OK.")
