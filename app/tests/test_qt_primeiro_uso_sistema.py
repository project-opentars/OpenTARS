"""5.2 (F3.5): o passo "Permissões e atalho" do primeiro uso. No macOS mostra Acessibilidade e Gravação de Tela com o
estado de cada uma e o botão que abre os Ajustes; no Windows, o atalho das ações e o iniciar com o sistema; no Linux o
passo não existe. As funções do sistema são de mentira aqui (as de verdade estão em tars_plataforma/macos.py)."""
import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import RAIZ  # noqa: E402,F401
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import tars_plataforma as plataforma  # noqa: E402
import tars_assistente  # noqa: E402
import tars_atalho  # noqa: E402
from tars_qt import primeiro_uso  # noqa: E402

app = QApplication.instance() or QApplication([])
original = plataforma.sistema, plataforma.permissoes, plataforma.pedir_permissao
estado, pedidos = {"acessibilidade": True, "tela": False}, []
try:
    plataforma.sistema = lambda: "macos"
    plataforma.permissoes = lambda: dict(estado)
    plataforma.pedir_permissao = pedidos.append
    pu = importlib.reload(primeiro_uso)
    assert pu.PASSOS[-1] == "sistema" and pu.DEPOIS_DO_TESTE == "sistema"
    jan = pu.JanelaPrimeiroUso()
    jan.ir("sistema")
    pag = jan.paginas["sistema"]
    assert pag.pedidos["acessibilidade"].text() == pu.t("pu.sist.concedida") and not pag.pedidos["acessibilidade"].isEnabled()
    assert pag.pedidos["tela"].isEnabled()
    pag.pedidos["tela"].click()
    assert pedidos == ["tela"], pedidos
    estado["tela"] = True          # a pessoa concedeu em Ajustes e voltou: o relógio da página atualiza
    pag.atualizar()
    assert pag.pedidos["tela"].text() == pu.t("pu.sist.concedida")
    jan.paginas["teste"].b_continuar.setEnabled(True)
    jan.paginas["teste"].b_continuar.click()
    assert jan.atual == "sistema"
    print("OK: macOS: Acessibilidade e Gravação de Tela com o estado, o botão pede a permissão e a lista se atualiza")
    jan.close()

    plataforma.sistema = lambda: "windows"
    inicio, registrado = {"ligado": False}, []
    originais_win = tars_assistente.inicia_com_sistema, tars_assistente.iniciar_com_sistema, tars_atalho.registrar_acoes
    tars_assistente.inicia_com_sistema = lambda: inicio["ligado"]
    tars_assistente.iniciar_com_sistema = lambda v: inicio.update(ligado=v) or v
    tars_atalho.registrar_acoes = lambda: registrado.append(1) or (True, "")
    try:
        pu = importlib.reload(primeiro_uso)
        jan = pu.JanelaPrimeiroUso()
        jan.ir("sistema")
        pag = jan.paginas["sistema"]
        assert pag.b_inicio.text() == pu.t("pu.sist.desligado")
        pag.b_inicio.click()
        assert inicio["ligado"] and pag.b_inicio.text() == pu.t("pu.sist.ligado")
        pag.b_atalho.click()
        assert registrado and pag.b_atalho.text() == pu.t("pu.sist.ligado")
        print("OK: Windows: o atalho Ctrl+Alt+R e o iniciar com o sistema ligam pelo passo (desligados por padrão)")
        jan.close()
    finally:
        tars_assistente.inicia_com_sistema, tars_assistente.iniciar_com_sistema, tars_atalho.registrar_acoes = originais_win

    plataforma.sistema = lambda: "linux"
    pu = importlib.reload(primeiro_uso)
    assert "sistema" not in pu.PASSOS and pu.DEPOIS_DO_TESTE == "pronto"
    jan = pu.JanelaPrimeiroUso()
    assert "sistema" not in jan.paginas
    print("OK: Linux: o passo não existe e o teste leva direto ao pronto")
    jan.close()
finally:
    plataforma.sistema, plataforma.permissoes, plataforma.pedir_permissao = original
    importlib.reload(primeiro_uso)
print("test_qt_primeiro_uso_sistema: TUDO OK.")
