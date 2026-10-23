"""3.1.1: "abre o editor de texto" no Zorin abria o Vim (GenericName "Text
Editor", Terminal=true), que falha sem um terminal. Com um editor de janela
instalado, ele ganha; pedindo "vim" pelo nome, continua sendo o Vim."""
from _util import carregar_tars

tars = carregar_tars()
VIM = {"nome": "Vim", "outros_nomes": ["Text Editor", "Editor de texto"], "arquivo": "/usr/share/applications/vim.desktop",
       "exec": "vim %F", "terminal": True}
GNOME = {"nome": "Text Editor", "outros_nomes": ["Editor de Texto"], "exec": "gnome-text-editor %U", "terminal": False,
         "arquivo": "/usr/share/applications/org.gnome.TextEditor.desktop"}
tars.shutil.which = lambda x: None
for ordem in ([VIM, GNOME], [GNOME, VIM]):
    tars.desktop_entries = lambda forcar=False, o=ordem: o
    for pedido in ("editor de texto", "text editor"):
        assert tars._buscar_app_no_sistema(pedido)["nome"] == "Text Editor", pedido
    assert tars._buscar_app_no_sistema("vim")["nome"] == "Vim"
tars.desktop_entries = lambda forcar=False: [VIM]
assert tars._buscar_app_no_sistema("editor de texto")["nome"] == "Vim"  # sem outro, o Vim ainda serve
print("OK: 'editor de texto' abre o editor de janela, não o Vim; 'vim' continua abrindo o Vim")
