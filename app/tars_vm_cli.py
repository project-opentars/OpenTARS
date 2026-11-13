"""5.3 (F7): `opentars --missao-vm "pedido"`: uma missão do Gargantua Pro dentro da VM descartável, pelo terminal. Mostra cada passo,
e o que o agente guardou na pasta de saída só vai para o PC se a pessoa disser sim (a quarentena é apagada de qualquer jeito)."""
import shutil
from pathlib import Path

import tars_vm
import tars_vm_agente as agente
import tars_vm_missao as missao_vm

PASTA_LIBERADA = Path.home() / "Downloads" / "openTARS-vm"


def executar(host, argumentos, t, instalados=None, entrada=input, saida=print, rodar=missao_vm.executar, perguntar=None):
    pedido = " ".join(a for a in argumentos[argumentos.index("--missao-vm") + 1:] if not a.startswith("--")).strip()
    if not pedido:
        saida(t("vm.cli.uso"))
        return 2
    falta = tars_vm.o_que_falta()
    if falta:
        saida(t("vm.cli.falta", falta=", ".join(falta)))
        return 1
    if not tars_vm.imagem_base().exists():
        saida(t("vm.cli.sem_base"))
        return 1
    nomes = [n.lower() for n in (instalados() if instalados else [])]
    if agente.MODELO.lower() not in nomes:
        saida(t("vm.cli.sem_pro", modelo=agente.MODELO))
        return 1
    saida(t("vm.cli.comecando", pedido=pedido))
    perguntar = perguntar or (lambda png, texto, sistema: agente.perguntar_modelo(png, texto, sistema, host=host))
    r = rodar(agente.por_modelo(pedido, perguntar=perguntar), internet=True, ao_passo=lambda i, f: saida(f"  {i + 1}. {f}"))
    saida(t("vm.cli.resultado", motivo=r["motivo"], segundos=r["segundos"], resultado=r["resultado"] or "-"))
    for acesso in r["acessos"][:10]:
        saida(t("vm.cli.acesso", acesso=acesso))
    arquivos = r["arquivos"]
    try:
        if arquivos:
            saida(t("vm.cli.arquivos", n=len(arquivos), lista=", ".join(f"{a['nome']} ({a['tamanho']} B)" for a in arquivos[:10])))
            if entrada(t("vm.cli.liberar", pasta=PASTA_LIBERADA)).strip().lower() in ("s", "sim", "y", "yes"):
                for a in arquivos:
                    saida("  -> " + str(missao_vm.liberar(a, PASTA_LIBERADA / a["nome"])))
            else:
                saida(t("vm.cli.descartados"))
    finally:
        if r.get("quarentena"):
            shutil.rmtree(r["quarentena"], ignore_errors=True)
    return 0 if r["motivo"] == "terminou" else 1
