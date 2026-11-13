"""11/11 (F11): o comando para reabrir um app Chromium com a acessibilidade ligada (a parte pura; o teste com Chrome de verdade
rodou à mão em barramento D-Bus isolado: 4 nós antes, 212 depois)."""
from _util import carregar_tars
t = carregar_tars()
assert t.comando_com_acessibilidade(["/opt/x/app", "--a"]) == ["/opt/x/app", "--force-renderer-accessibility", "--a"]
ja = ["/opt/x/app", "--force-renderer-accessibility"]
assert t.comando_com_acessibilidade(ja) == ja
assert t.reabrir_com_acessibilidade(2 ** 22 + 1)[0] is False          # processo que não existe: não faz nada
print("TUDO OK.")
