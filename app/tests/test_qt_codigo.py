#!/usr/bin/env python3
"""A janelinha de código da conversa Qt (como a do Tk): cerca vira caixa com Copiar; sem cerca continua Markdown."""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    print("test_qt_codigo: PULADO (PySide6 não instalado)")
    sys.exit(0)
app = QApplication.instance() or QApplication([])
from tars_qt import conversa, tema
app.setStyleSheet(tema.folha_principal() if hasattr(tema, "folha_principal") else "")

# 1. partir_em_blocos
p = conversa.partir_em_blocos("Veja:\n```python\nprint('oi')\n```\nPronto.\n```\n\n```\nfim ```ls``` no meio")
tipos = [x[0] for x in p]
assert tipos == ["texto", "codigo", "texto"], tipos
assert p[1][1:] == ("print('oi')", "python"), p[1]
assert "```ls```" in p[2][1], "cerca no meio da frase não é bloco"
print("OK: o texto é partido em texto, código, texto")

# 2. bloco aberto (resposta cortada) vira código; sem cerca não vira nada
assert conversa.partir_em_blocos("```bash\nls -la")[0] == ("codigo", "ls -la", "bash")
assert [x[0] for x in conversa.partir_em_blocos("só texto **negrito**")] == ["texto"]
print("OK: cerca aberta e texto simples")

# 3. o widget
b = conversa.BlocoTexto()
b.acrescentar("Faça assim:\n```python\nprint(\"Hello, World!\")\nx = 1\n```\nDepois rode.")
b.concluir()
caixas = [w for w in b._pecas if isinstance(w, conversa.CaixaCodigo)]
assert len(caixas) == 1 and len(b._pecas) == 3
c = caixas[0]
assert c.titulo.text() == "python" and c.texto.toPlainText() == 'print("Hello, World!")\nx = 1'
assert c.texto.isReadOnly()
c.botao.click()
assert app.clipboard().text() == 'print("Hello, World!")\nx = 1'
assert "✓" in c.botao.text()
print("OK: caixa com linguagem, só leitura e botão Copiar")

# 4. sem código: o rótulo único de sempre; e texto() continua inteiro
b2 = conversa.BlocoTexto(); b2.acrescentar("oi **tudo**"); b2.concluir()
assert not b2._pecas and b2.texto() == "oi **tudo**"
assert b.texto().startswith("Faça assim")
print("OK: sem cerca nada muda")

# 5. altura limitada a 24 linhas, e linha sem nome mostra "código"
grande = conversa.CaixaCodigo("\n".join(f"l{i}" for i in range(60)))
assert grande.titulo.text() in ("código", "code")
assert grande.texto.height() < 600
print("OK: bloco grande tem altura limitada e nome padrão")

# 6. imagem para olhar
w = conversa.MensagemIA(); w.resize(780, 400)
w.acrescentar_texto("I'll create a simple script:\n```python\nprint(\"Hello, World!\")\n```\nSave it as `hello.py` and run it.\n```bash\npython3 hello.py\n```\n")
w.fim_do_trecho(); w.show(); app.processEvents()
alvo = os.environ.get("TARS_FOTO")
if alvo:
    w.grab().save(alvo)
# 7. linha larga: aparece a barra horizontal e a caixa cresce o necessário (e não mais)
larga = conversa.CaixaCodigo("x = '" + "a" * 400 + "'"); larga.resize(400, 200); larga.show(); app.processEvents()
assert larga.texto.horizontalScrollBar().maximum() > 0 and larga.texto.height() == larga._altura + 14
curta = conversa.CaixaCodigo("x = 1"); curta.resize(400, 200); curta.show(); app.processEvents()
assert curta.texto.height() == curta._altura
print("OK: a barra horizontal só ocupa espaço quando existe")
print("TUDO OK.")
