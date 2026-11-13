"""5.3 (F4+): perguntar sobre a tela pelo TEXTO da janela (acessibilidade), sem imagem e sem modelo. Árvore de mentira: o que
vira texto, o que nunca entra (senha), o corte, e a janela certa (nunca o próprio openTARS)."""
import os
import sys

from _util import carregar_tars  # noqa: F401  (põe o app no sys.path e isola a casa)

import tars_acessibilidade as acess  # noqa: E402

# 1. juntar: ordem de leitura, sem repetir, botões no fim, corte no limite
texto = acess.montar_texto_da_janela(["Disk C: is 92% full", "  Free   up space ", "Disk C: is 92% full", "", None],
                                     ["Clean up", "Settings", "Clean up", ""])
assert texto == "Disk C: is 92% full\nFree up space\n\nButtons and links: Clean up, Settings", repr(texto)
assert acess.montar_texto_da_janela([], ["Salvar"]) == "Buttons and links: Salvar"
assert len(acess.montar_texto_da_janela(["x" * 500] * 1, [], limite=100)) == 100
assert acess.montar_texto_da_janela([], []) == ""
print("OK: o texto da janela: ordem de leitura, sem repetir, botões no fim, corte no limite")

# 2. a janela: pega a pedida, ignora o próprio processo, e nunca lê campo de senha
no = lambda n: object()  # noqa: E731
itens = [(no(1), "label", "", set(), "texto"), (no(2), "entry", "Name", {"editable"}, "campo"),
         (no(3), "password-text", "Password", {"editable"}, "campo"), (no(4), "push-button", "Sign in", set(), "clicavel"),
         (no(5), "push-button", "", set(), "clicavel")]
conteudo = {itens[0][0]: "Welcome back", itens[1][0]: "enzo", itens[2][0]: "••••••", itens[3][0]: "Sign in"}
acess.indisponivel = lambda: None
acess.janelas = lambda: [{"no": object(), "app": "Browser", "pid": 111, "titulo": "Login", "ativa": True},
                         {"no": object(), "app": "openTARS", "pid": os.getpid(), "titulo": "openTARS", "ativa": False}]
acess._itens = lambda janela, forcar=False: itens
acess._texto_do_no = lambda n, papel, limite=0: conteudo.get(n, "")
lido = acess.texto_da_janela(pid=111, titulo="Login")
assert lido["titulo"] == "Login" and lido["app"] == "Browser"
assert "Welcome back" in lido["texto"] and "enzo" in lido["texto"] and "Buttons and links: Sign in" in lido["texto"], lido
assert "••••" not in lido["texto"] and "Password" not in lido["texto"], "campo de senha nunca entra"
assert acess.texto_da_janela(pid=os.getpid()) is None or acess.texto_da_janela(pid=os.getpid())["titulo"] != "openTARS", "o próprio openTARS não é lido"
acess.janelas = lambda: []
assert acess.texto_da_janela() is None, "sem janela, sem texto"
acess.indisponivel = lambda: "sem acessibilidade"
assert acess.texto_da_janela(pid=111) is None, "sem acessibilidade devolve None (o app cai no print)"
print("OK: lê a janela pedida, nunca o próprio openTARS, nunca campo de senha; sem acessibilidade devolve None")
print("TUDO OK.")
