"""3.0 Miller: o "opentars" sozinho confere o ambiente e diz onde conversar
(a conversa fica na janela); os argumentos continuam funcionando."""

import io
import contextlib
import sys
import types

from _util import carregar_tars

tars = carregar_tars()

chamado = {}
falso = types.ModuleType("tars_autoteste")
falso.executar = lambda nucleo, completo=False: chamado.update(completo=completo) or 0
sys.modules["tars_autoteste"] = falso

sys.argv = ["opentars"]
saida = io.StringIO()
with contextlib.redirect_stdout(saida):
    try:
        tars.main()
    except SystemExit as e:
        codigo = e.code
assert codigo == 0 and chamado == {"completo": False}, (codigo, chamado)
assert "opentars-gui" in saida.getvalue(), saida.getvalue()
print("OK: 'opentars' sozinho roda o diagnóstico e aponta pra janela")

sys.argv = ["opentars", "--version"]
saida = io.StringIO()
with contextlib.redirect_stdout(saida):
    tars.main()
assert tars.VERSAO_EXIBIDA in saida.getvalue() and "5.2 Ranger" in saida.getvalue(), saida.getvalue()
sys.argv = ["opentars", "--help"]
saida = io.StringIO()
with contextlib.redirect_stdout(saida):
    tars.main()
assert "--explicar" in saida.getvalue() and "--chat" in saida.getvalue()  # 4.5: voltou a conversa no terminal
assert "--cooper" not in saida.getvalue(), "18/10: o Cooper foi descontinuado e saiu da ajuda"
assert not hasattr(tars, "tela_inicial") and not hasattr(tars, "MODELO_AJUDANTE_ANTIGO")
assert not {"move_mouse", "get_screen_size", "get_mouse_position", "get_current_directory"} & set(tars._DISPATCH_FERRAMENTAS)
print("OK: --version e --help continuam; conversa no terminal, ferramentas aposentadas e restos do gemma3:270m saíram")

print("\nTUDO OK.")

# --voz: antes só existia no comentário e caía no diagnóstico
import io, sys as _sys
chamado = []
tars.modo_voz_terminal = lambda: chamado.append(1) or 0
antigo_argv, _sys.argv = _sys.argv, ["opentars", "--voz"]
try:
    tars.main()
except SystemExit as e:
    assert e.code == 0
finally:
    _sys.argv = antigo_argv
assert chamado == [1], "opentars --voz tem que chamar modo_voz_terminal"
print("OK: opentars --voz chama o modo de voz")
