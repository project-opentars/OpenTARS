"""O decisor por roteiro: a visão (falsa) só diz onde clicar; sem achar, a missão termina sem clicar no escuro."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tars_vm_decisor as d

respostas = iter(['{"x": 500, "y": 250}', "não sei", "não sei"])
dec = d.por_roteiro([{"achar": "Terminal", "acao": "duplo"}, {"digitar": "ls\n"}, {"atalho": "ctrl+l"}, {"esperar": 5}, {"achar": "Fantasma"}],
                    perguntar=lambda png, p: next(respostas), tamanho=lambda png: (1280, 800))
assert dec("t.png", []) == {"tipo": "duplo", "x": 640, "y": 200}, "milésimos viram pixels"
assert dec("t.png", []) == {"tipo": "digitar", "texto": "ls\n"}
assert dec("t.png", []) == {"tipo": "atalho", "teclas": "ctrl+l"}
assert dec("t.png", []) == {"tipo": "esperar", "segundos": 5}
assert dec("t.png", []) == {"tipo": "esperar", "segundos": 3}, "primeira falha: espera e tenta de novo"
r = dec("t.png", [])
assert r["tipo"] == "terminar" and "Fantasma" in r["resultado"], "sem achar, termina sem clicar"
print("TUDO OK.")
