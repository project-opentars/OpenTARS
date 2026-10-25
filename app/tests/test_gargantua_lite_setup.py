"""5.1: máquina fraca recebe o Gargantua Lite no primeiro uso e no instalador (decisão de 09/10: sem placa de vídeo com
4 GB E com até 6 GB de RAM OU menos de 4 threads). TARS_GARGANTUA=lite|completo força. Sem Ollama, sem rede."""
import os
import subprocess
import tempfile
from pathlib import Path

from _util import RAIZ  # noqa: F401

import tars_primeiro_uso as pu

os.environ.pop("TARS_GARGANTUA", None)
assert not pu.maquina_fraca(vram_mb=6144, ram_mb=2000, threads=2), "placa de 6 GB nunca é máquina fraca"
assert pu.maquina_fraca(vram_mb=0, ram_mb=4000, threads=8), "pouca RAM sem placa"
assert pu.maquina_fraca(vram_mb=2048, ram_mb=16000, threads=2), "poucas threads e placa pequena"
assert not pu.maquina_fraca(vram_mb=0, ram_mb=16000, threads=8), "sem placa mas com RAM e threads: o 4B"
os.environ["TARS_GARGANTUA"] = "lite"
assert pu.maquina_fraca(vram_mb=24000) and pu.gargantua_desta_maquina() == "ProjectOpenTARS/Gargantua-2:lite"
assert pu.tamanho_gargantua_gb() == pu.TAMANHO_GARGANTUA_LITE_GB
assert pu.tem_gargantua_desta_maquina(["ProjectOpenTARS/Gargantua:lite"])
assert pu.tem_gargantua_desta_maquina(["ProjectOpenTARS/Gargantua:latest"]), "o oficial sempre serve"
assert not pu.tem_gargantua_desta_maquina(["ProjectOpenTARS/Gargantua:code", "qwen3:4b"])
assert pu.nome_do_gargantua(["qwen3:4b", "ProjectOpenTARS/Gargantua:1.2-lite"]) == "ProjectOpenTARS/Gargantua:1.2-lite"
os.environ["TARS_GARGANTUA"] = "completo"
assert not pu.maquina_fraca(vram_mb=0, ram_mb=1000, threads=1) and pu.gargantua_desta_maquina() == pu.MODELO_GARGANTUA
assert not pu.tem_gargantua_desta_maquina(["ProjectOpenTARS/Gargantua:lite"]), "fora da máquina fraca o Lite não basta"
os.environ["TARS_GARGANTUA"] = "completo"
assert pu.faltam_no_primeiro_uso([]) == [pu.MODELO_GARGANTUA, pu.MODELO_GARGANTUA_LITE]
assert pu.faltam_no_primeiro_uso(["ProjectOpenTARS/Gargantua:latest"]) == [pu.MODELO_GARGANTUA_LITE], "o 1.x vale como principal"
assert pu.faltam_no_primeiro_uso(["projectopentars/gargantua-2:lite", "ProjectOpenTARS/Gargantua-2:latest"]) == []
os.environ["TARS_GARGANTUA"] = "lite"
assert pu.faltam_no_primeiro_uso([]) == [pu.MODELO_GARGANTUA_LITE], "máquina fraca: só o Lite"
os.environ["TARS_GARGANTUA"] = "completo"
print("OK: a regra da máquina fraca, o modelo e o tamanho certos, e TARS_GARGANTUA força")

# o instalador usa a mesma regra
setup = (Path(RAIZ) / "empacotamento" / "setup.sh").read_text(encoding="utf-8")
inicio = setup.index('MODELO_GARGANTUA="${TARS_MODELO_GARGANTUA:-ProjectOpenTARS/Gargantua-2}"')
fim = setup.index("gargantua_instalado() {")
bloco = setup[inicio:fim] + '\necho "MODELO=$MODELO_GARGANTUA"\n'
pasta = Path(tempfile.mkdtemp())
(pasta / "bin").mkdir()
smi = pasta / "bin" / "nvidia-smi"


def rodar(env_extra, vram=None):
    if vram is None:
        smi.unlink(missing_ok=True)
    else:
        smi.write_text(f"#!/bin/sh\necho {vram}\n")
        smi.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k not in ("TARS_GARGANTUA", "TARS_MODELO_GARGANTUA")}
    env.update(env_extra, PATH=f"{pasta / 'bin'}:/usr/bin:/bin")
    saida = subprocess.run(["bash", "-c", bloco], capture_output=True, text=True, env=env).stdout
    return saida.strip().splitlines()[-1]


assert rodar({"TARS_GARGANTUA": "lite"}) == "MODELO=ProjectOpenTARS/Gargantua-2:lite"
assert rodar({"TARS_GARGANTUA": "completo"}) == "MODELO=ProjectOpenTARS/Gargantua-2"
assert rodar({}, vram=6144) == "MODELO=ProjectOpenTARS/Gargantua-2", "placa de 6 GB: o Gargantua 2"
assert rodar({"TARS_MODELO_GARGANTUA": "meu/gargantua", "TARS_GARGANTUA": "lite"}) == "MODELO=meu/gargantua"
print("OK: o setup.sh escolhe o mesmo modelo (e respeita TARS_MODELO_GARGANTUA)")
print("\nTUDO OK.")
