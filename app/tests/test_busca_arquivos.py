"""5.2 (F4): buscar arquivos por uma frase, pelo nome, pela pasta e pelo texto de dentro, sem modelo."""
import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tars_busca_arquivos as b  # noqa: E402

casa = Path(tempfile.mkdtemp(prefix="opentars-busca-"))
(casa / "Documentos" / "Moradia").mkdir(parents=True)
(casa / "Downloads").mkdir()
(casa / ".escondida").mkdir()
(casa / "node_modules").mkdir()
(casa / "Documentos" / "Moradia" / "Contrato de aluguel 2024 (assinado).txt").write_text(
    "O LOCATÁRIO obriga-se a restituir o imóvel nas mesmas condições em que o recebeu.")
(casa / "Downloads" / "minuta.txt").write_text("Minuta do contrato de aluguel, versão de 2023, para revisão.")
with zipfile.ZipFile(casa / "Downloads" / "notas.docx", "w") as z:
    z.writestr("word/document.xml", "<w:p>Reunião sobre o aluguel do galpão em 2024</w:p>")
(casa / "Downloads" / "receita.txt").write_text("bolo de cenoura")
(casa / ".escondida" / "contrato aluguel 2024.txt").write_text("não deve aparecer")
(casa / "node_modules" / "contrato-aluguel-2024.js").write_text("não deve aparecer")
antigo = time.time() - 86400 * 30
os.utime(casa / "Downloads" / "minuta.txt", (antigo, antigo))

assert b.termos("o contrato de aluguel de 2024") == ["contrato", "aluguel", "2024"]
assert b.termos("Ache o arquivo da reunião") == ["reuniao"]

r = b.buscar("o contrato de aluguel de 2024", raiz=casa)
nomes = [x["nome"] for x in r]
assert nomes[0] == "Contrato de aluguel 2024 (assinado).txt", nomes
assert "minuta.txt" in nomes and "notas.docx" in nomes and "receita.txt" not in nomes, nomes
assert not any("escondida" in x["caminho"] or "node_modules" in x["caminho"] for x in r), r
assert "LOCATÁRIO" in r[0]["trecho"] or "restituir" in r[0]["trecho"], r[0]
print("OK: acha pelo nome (melhor), pelo texto de dentro (docx também); ignora pastas ocultas e de programas")

assert b.buscar("receita de bolo", raiz=casa)[0]["nome"] == "receita.txt"
assert b.buscar("planilha de viagens a marte", raiz=casa) == []
assert b.buscar("de o a", raiz=casa) == []
print("OK: frase sem palavra útil ou sem arquivo que bata devolve nada")
print("test_busca_arquivos: TUDO OK.")
