import time

from _util import carregar_tars
tars = carregar_tars()

# 4.6: wait_seconds saiu; quem ainda o chama cai no sleep do terminal, limitado a 5 s
inicio = time.time()
resultado = tars.executar_ferramenta("wait_seconds", {"seconds": 0.05})
assert resultado["sucesso"] and time.time() - inicio < 2
print("OK: wait_seconds antigo vira sleep no terminal:", resultado["mensagem"][:60])

# abrir_aplicativo confirma por polling (processo aparece rápido = retorno rápido)
tars.psutil.process_iter = lambda *a, **k: iter([
    type("P", (), {"info": {"name": "minhaapp", "cmdline": ["minhaapp"]}})()
])
tars.shutil.which = lambda nome: "/usr/bin/minhaapp" if nome == "minhaapp" else None
tars.subprocess.Popen = lambda *a, **k: None

inicio = time.time()
r = tars.abrir_aplicativo("minhaapp")
decorrido = time.time() - inicio
assert r["sucesso"]
assert decorrido < tars.TIMEOUT_POLL_PROCESSO_SEG
print(f"OK: app confirmado rápido via polling ({decorrido:.2f}s, bem abaixo do teto de {tars.TIMEOUT_POLL_PROCESSO_SEG}s)")

print("\nTUDO OK.")
