"""18/10: a lógica (sem Qt) de qual Gargantua o primeiro uso baixa e reconhece; o Cooper foi descontinuado."""
from _util import RAIZ  # noqa: F401

import tars_primeiro_uso as pu

assert pu.MODELO_GARGANTUA == "ProjectOpenTARS/Gargantua-2" and pu.MODELO_GARGANTUA_LITE == "ProjectOpenTARS/Gargantua-2:lite"
assert not hasattr(pu, "MODELO_COOPER") and not hasattr(pu, "tem_cooper") and not hasattr(pu, "cabe_com_cooper")
# Gargantua-2 (:latest) é o 2B oficial; Gargantua-2:lite é o 0,8B, que conta como Lite (variante)
for m in ("ProjectOpenTARS/Gargantua-2", "ProjectOpenTARS/Gargantua-2:latest", "gargantua-2"):
    assert pu.e_gargantua_2(m) and not pu.e_variante_do_gargantua(m), m
for m in ("ProjectOpenTARS/Gargantua-2:lite", "ProjectOpenTARS/Gargantua:2.0-lite", "ProjectOpenTARS/Gargantua:code"):
    assert pu.e_variante_do_gargantua(m), m
assert pu.tem_gargantua(["ProjectOpenTARS/Gargantua-2"]) and pu.tem_gargantua(["ProjectOpenTARS/Gargantua:latest"])
assert not pu.tem_gargantua(["ProjectOpenTARS/Gargantua-2:lite"]), "o Lite não vale como o Gargantua oficial"
assert not pu.tem_gargantua(["ProjectOpenTARS/Gargantua:code", "qwen3:4b"]) and pu.tem_gargantua_2(["ProjectOpenTARS/Gargantua-2"])
assert not pu.tem_gargantua_2(["ProjectOpenTARS/Gargantua-2:lite"])
assert not pu.tem_gargantua_2(["ProjectOpenTARS/Gargantua:latest"])
# o 2 vai na frente do 1.x quando os dois estão instalados
assert pu.nome_do_gargantua(["ProjectOpenTARS/Gargantua:latest", "ProjectOpenTARS/Gargantua-2:latest"]) == "ProjectOpenTARS/Gargantua-2:latest"
assert pu.nome_do_gargantua(["ProjectOpenTARS/Gargantua:latest"]) == "ProjectOpenTARS/Gargantua:latest"
assert pu.TAMANHO_GARGANTUA_GB == 1.7
print("OK: Gargantua 2 é o principal; o 1.x continua valendo; o Cooper saiu")
print("\nTUDO OK.")
