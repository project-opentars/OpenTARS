"""5.2: o atalho global no Windows (RegisterHotKey) e no macOS (RegisterEventHotKey): a conversão da combinação e o
cadastro do atalho das ações de texto. O registro de verdade só acontece no sistema certo, com a janela aberta."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import RAIZ  # noqa: E402,F401
import tars_atalho as a  # noqa: E402
import tars_i18n  # noqa: E402

assert a.para_windows("<Primary><Alt>r") == (2 | 1, ord("R"))
assert a.para_windows("<Primary><Alt>space") == (3, 0x20) and a.para_windows("<Super>F5") == (8, 0x74)
assert a.para_windows("<Primary>ç") is None
print("OK: Windows: Ctrl+Alt+R vira MOD_CONTROL|MOD_ALT e 'R'")

assert a.para_macos("<Primary><Alt>r") == (0x1000 | 0x0800, 15)          # controlKey|optionKey, kVK_ANSI_R
assert a.para_macos("<Primary><Shift>space") == (0x1200, 0x31) and a.para_macos("<Super>F12") == (0x0100, 0x6F)
assert a.para_macos("<Primary>m") == (0x1000, 46) and a.para_macos("<Primary>0") == (0x1000, 29)
assert a.para_macos("<Primary>ç") is None and a.para_macos("<Primary>") is None
print("OK: macOS: Ctrl+Alt+R vira controlKey|optionKey e kVK_ANSI_R (o Command fica livre para os apps)")

original = a.plataforma.sistema
try:
    for sistema in ("windows", "macos"):
        a.plataforma.sistema = lambda s=sistema: s
        tars_i18n.salvar_config(atalho_acoes_registrado=False)
        ok, mensagem = a.registrar_acoes("<Primary><Alt>r")
        assert ok and tars_i18n.ler_config().get("atalho_acoes_registrado") and "Ctrl" in mensagem, mensagem
        assert ("macOS" in mensagem) == (sistema == "macos"), mensagem
        assert a.registrar_acoes("<Primary>ç") == (False, tars_i18n.t("atalho.invalido"))
finally:
    a.plataforma.sistema = original
print("OK: no Windows e no macOS o atalho das ações fica guardado para a janela escutar")

import tars_qt.atalhos_macos as m  # noqa: E402  (o Carbon só é carregado ao criar; aqui só o módulo)
assert m._codigo("keyb") == 0x6B657962 and m.ASSINATURA == m._codigo("oTAR")
print("test_atalhos_outros_sistemas: TUDO OK.")
