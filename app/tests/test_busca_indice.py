"""5.3 (F4+): o índice local de arquivos (opcional): dá o mesmo resultado da busca sem índice, só relê o que mudou, tira o que
sumiu, respeita as pastas ocultas e se apaga ao desligar. Sem modelo."""
import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
base = Path(tempfile.mkdtemp(prefix="opentars-indice-"))
os.environ["TARS_ARQUIVO_CONFIG"] = str(base / "config.json")
os.environ["XDG_DATA_HOME"] = str(base / "dados")
os.environ["LOCALAPPDATA"] = str(base / "dados")
os.environ["HOME"] = str(base / "casa")
import tars_busca_arquivos as b  # noqa: E402

casa = base / "casa"
(casa / "Documentos" / "Moradia").mkdir(parents=True)
(casa / "Downloads").mkdir()
(casa / ".escondida").mkdir()
(casa / "Documentos" / "Moradia" / "Contrato de aluguel 2024 (assinado).txt").write_text("O LOCATÁRIO obriga-se a restituir o imóvel.")
(casa / "Downloads" / "minuta.txt").write_text("Minuta do contrato de aluguel, versão de 2023, para revisão.")
with zipfile.ZipFile(casa / "Downloads" / "notas.docx", "w") as z:
    z.writestr("word/document.xml", "<w:p>Reunião sobre o aluguel do galpão em 2024</w:p>")
(casa / "Downloads" / "receita.txt").write_text("bolo de cenoura")
(casa / ".escondida" / "contrato aluguel 2024.txt").write_text("não deve aparecer")

# desligado por padrão, e sem índice a busca anda pelas pastas
assert not b.indice_ligado() and b.indice_idade() is None and b.buscar_no_indice("aluguel", casa) is None
sem_indice = b.buscar("contrato de aluguel de 2024", casa)
assert sem_indice and sem_indice[0]["nome"].startswith("Contrato de aluguel 2024")

# montar: lê tudo uma vez
r = b.atualizar_indice(casa)
assert r["arquivos"] == 4 and r["lidos"] == 4 and r["removidos"] == 0, r
assert b.indice_idade() is not None and b.indice_idade() < 5
com_indice = b.buscar_no_indice("contrato de aluguel de 2024", casa)
assert [a["caminho"] for a in com_indice] == [a["caminho"] for a in sem_indice], (com_indice, sem_indice)
assert all(a["trecho"] or a["nome"].startswith("receita") for a in com_indice)
assert not any(".escondida" in a["caminho"] for a in com_indice) and b.buscar_no_indice("bolo", casa)[0]["nome"] == "receita.txt"
print("OK: o índice dá o mesmo resultado da busca sem índice, e não entra em pasta oculta")

# a segunda atualização só relê o que mudou; o que sumiu sai
time.sleep(0.05)
(casa / "Downloads" / "receita.txt").write_text("bolo de laranja com cobertura")
os.utime(casa / "Downloads" / "receita.txt", (time.time() + 5, time.time() + 5))
(casa / "Downloads" / "minuta.txt").unlink()
r = b.atualizar_indice(casa)
assert r["lidos"] == 1 and r["removidos"] == 1 and r["arquivos"] == 3, r
assert b.buscar_no_indice("laranja", casa)[0]["nome"] == "receita.txt" and not b.buscar_no_indice("minuta", casa)
print("OK: a atualização relê só o que mudou e tira o que sumiu")

# buscar() usa o índice só quando ligado; desligar apaga o arquivo
assert b.buscar("laranja", casa) == [] or b.buscar("laranja", casa)[0]["nome"] == "receita.txt"
b.ligar_indice(True)
assert b.indice_ligado() and b.buscar("laranja", casa)[0]["nome"] == "receita.txt"
b.ligar_indice(False)
assert not b.indice_ligado() and not b.caminho_do_indice().exists(), "desligar apaga o índice"
print("OK: ligado, a busca lê do índice; desligar apaga o arquivo do índice")
print("TUDO OK.")
