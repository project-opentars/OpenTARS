"""5.2: abrir e fechar programas no Windows e no macOS pelo núcleo, com o catálogo e as janelas da plataforma de mentira.
O caminho de verdade (Get-StartApps, EnumWindows, Quartz) é testado em test_plataforma_windows/_macos, no sistema certo."""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import RAIZ  # noqa: E402,F401
import tars  # noqa: E402

CATALOGO = {
    "windows": [{"nome": "Calculator", "outros_nomes": [], "id": "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",
                 "comando": ["explorer.exe", "shell:AppsFolder\\Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"]},
                {"nome": "Calculator", "outros_nomes": ["calculadora", "calc"], "id": "calc.exe", "comando": ["calc.exe"]}],
    "macos": [{"nome": "Calculadora", "outros_nomes": ["Calculator"], "id": "Calculator",
               "comando": ["open", "-a", "/System/Applications/Calculator.app"]}],
}
JANELA = {"windows": {"titulo": "Calculator", "classe": "ApplicationFrameWindow CalculatorApp"},
          "macos": {"titulo": "Calculadora", "classe": "Calculadora"}}

originais = {n: getattr(tars, n) for n in ("listar_janelas_x", "janela_ativa_x", "focar_janela_x", "fechar_janela_x",
                                           "SESSAO_GRAFICA", "_usar_quadro_tela_inteira")}
original_sistema, original_programas, original_popen = tars.plataforma.sistema, tars.plataforma.programas, tars.subprocess.Popen
try:
    for sistema, sessao in (("windows", "windows"), ("macos", "aqua")):
        tars.plataforma.sistema = lambda s=sistema: s
        tars.plataforma.programas = lambda s=sistema: CATALOGO[s]
        tars._cache_desktop.update(dados=None, ts=0)

        # no Windows em inglês o nome é "Calculator": "calculadora" acha o calc.exe pelos outros nomes
        achado = tars._buscar_app_no_sistema("calculadora")
        assert achado and achado["comando"] == CATALOGO[sistema][-1]["comando"], achado
        pedido = "calculator" if sistema == "windows" else "calculadora"
        achado = tars._buscar_app_no_sistema(pedido)
        assert achado and achado["comando"] == CATALOGO[sistema][0]["comando"], achado
        termos = tars._termos_do_app(pedido, achado)
        assert "explorer.exe" not in termos and "open" not in termos and "calculator" in [t.lower() for t in termos], termos

        # o explorer.exe sai com código 1 e o open sai logo: a janela que aparece depois é que conta
        janelas = [{"id": 1, "titulo": "Downloads", "classe": "CabinetWClass explorer", "pid": 10,
                    "x": 0, "y": 0, "largura": 800, "altura": 600, "minimizada": False}]
        focadas, fechadas = [], []

        class Proc:
            pid = 99

            def __init__(self, *_a, **_k):
                janelas.append(dict(JANELA[sistema], id=2, pid=50, x=10, y=10, largura=400, altura=600, minimizada=False))

            def poll(self):
                return 1 if sistema == "windows" else 0

        tars.subprocess.Popen = Proc
        tars.listar_janelas_x = lambda: list(janelas)
        tars.janela_ativa_x = lambda: 1
        tars.focar_janela_x = focadas.append
        def fechar(i, janelas=janelas, fechadas=fechadas):
            fechadas.append(i)
            janelas[:] = [j for j in janelas if j["id"] != i]
        tars.fechar_janela_x = fechar
        tars._usar_quadro_tela_inteira = lambda: None
        tars.SESSAO_GRAFICA = sessao

        r = tars.abrir_aplicativo(pedido)
        assert r["sucesso"] and r["janela"]["titulo"] == JANELA[sistema]["titulo"] and focadas == [2], (r, focadas)

        r = tars._fechar_pelas_janelas(pedido)
        assert r and fechadas == [2] and r[0] == [JANELA[sistema]["titulo"]], (r, fechadas)
        print(f"OK: {sistema}: acha a calculadora no catálogo, abre, espera a janela, foca e fecha pela janela")
finally:
    tars.plataforma.sistema, tars.plataforma.programas, tars.subprocess.Popen = original_sistema, original_programas, original_popen
    for nome, valor in originais.items():
        setattr(tars, nome, valor)
    tars._cache_desktop.update(dados=None, ts=0)
print("test_apps_outros_sistemas: TUDO OK.")
