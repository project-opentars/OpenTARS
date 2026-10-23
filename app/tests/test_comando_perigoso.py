from _util import carregar_tars
import builtins
tars = carregar_tars()

casos_perigosos = ["rm -rf /", "rm -rf ~/projeto", "sudo dd if=/dev/zero of=/dev/sda", "mkfs.ext4 /dev/sdb1", "shutdown now", ":(){ :|:& };:"]
casos_seguros = ["ls -la", "echo oi", "rm arquivo.txt", "df -h", "cat README.md"]

for cmd in casos_perigosos:
    assert tars._comando_e_perigoso(cmd), f"deveria ser perigoso: {cmd}"
print("OK: todos os comandos perigosos foram detectados")

for cmd in casos_seguros:
    assert not tars._comando_e_perigoso(cmd), f"nao deveria ser perigoso: {cmd}"
print("OK: comandos seguros nao disparam confirmacao")

# mv que some com o arquivo ou tira a raiz/a pasta pessoal do lugar (o padrão antigo não pegava nada útil)
for cmd in ["mv ~/projeto /dev/null", "mv -f dados.db /dev/null", "mv / /tmp/x", "mv ~ /tmp/casa", "mv $HOME /mnt/x"]:
    assert tars._comando_e_perigoso(cmd), f"deveria ser perigoso: {cmd}"
for cmd in ["mv a.txt b.txt", "mv ~/a.txt ~/b.txt", "mv relatorio.pdf ~/Documentos/", "ls /dev/null"]:
    assert not tars._comando_e_perigoso(cmd), f"nao deveria ser perigoso: {cmd}"
print("OK: mv pra /dev/null e mv da raiz/da casa pedem confirmação; mv comum não")

# Simula usuario recusando -> comando nao roda
builtins.input = lambda *a, **k: "n"
r = tars.executar_terminal("rm -rf /tmp/teste")
assert r["sucesso"] is False
assert "cancelled" in r["mensagem"].lower()
print("OK: recusa cancela o comando:", r["mensagem"])

# Simula usuario confirmando -> comando roda de fato
builtins.input = lambda *a, **k: "s"
r = tars.executar_terminal("echo teste_perigoso_confirmado")
print("resultado apos confirmar (comando inofensivo usado so p/ nao mexer no disco de verdade):", r)

print("\nTUDO OK.")
