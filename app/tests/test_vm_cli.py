"""5.3 (F7): `opentars --missao-vm` com a VM e o modelo de mentira: pede aprovação para liberar arquivos e apaga a quarentena."""
import os, tempfile
from pathlib import Path
from _util import carregar_tars  # noqa: F401
import tars_vm, tars_vm_cli as cli, tars_vm_agente as ag
from tars_i18n import t

linhas = []
tars_vm.o_que_falta = lambda d=None: []
base = Path(tempfile.mkdtemp()) / "base.qcow2"; base.write_text("x")
tars_vm.imagem_base = lambda: base
cli.PASTA_LIBERADA = Path(tempfile.mkdtemp()) / "liberados"
quarentena = Path(tempfile.mkdtemp()); (quarentena / "a.txt").write_text("oi")
resultado = {"resultado": "feito", "motivo": "terminou", "segundos": 5, "passos": ["x"], "acessos": ["example.com:443"],
             "arquivos": [{"nome": "a.txt", "tamanho": 2, "caminho": str(quarentena / "a.txt")}], "quarentena": str(quarentena)}
rodar = lambda decisor, **k: (k["ao_passo"](0, "atalho ctrl+alt+t"), resultado)[1]
cmd = ["--missao-vm", "crie a.txt"]
inst = lambda: [ag.MODELO]
assert cli.executar("h", ["--missao-vm"], t, inst, saida=linhas.append, rodar=rodar) == 2
assert cli.executar("h", cmd, t, lambda: [], saida=linhas.append, rodar=rodar) == 1          # sem o Pro instalado
# "não": nada é copiado e a quarentena some
assert cli.executar("h", cmd, t, inst, entrada=lambda p: "n", saida=linhas.append, rodar=rodar) == 0
assert not cli.PASTA_LIBERADA.exists() and not quarentena.exists()
# "sim": copia
quarentena.mkdir(); (quarentena / "a.txt").write_text("oi")
assert cli.executar("h", cmd, t, inst, entrada=lambda p: "s", saida=linhas.append, rodar=rodar) == 0
assert (cli.PASTA_LIBERADA / "a.txt").read_text() == "oi" and not quarentena.exists()
print("TUDO OK.")
