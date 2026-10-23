#!/bin/bash
# Monta o .deb do openTARS a partir dos arquivos-fonte.
# Uso: bash empacotamento/build.sh   (gera dist/opentars_<versão>_all.deb)

set -euo pipefail
umask 022      # pastas 0755 / arquivos 0644 no pacote, qualquer que seja a umask de quem compila (dpkg-deb recusa DEBIAN 0700)

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
# Versão tem uma fonte só: a constante VERSAO do tars.py.
VERSAO="$(grep -m1 '^VERSAO = ' "$RAIZ/tars.py" | cut -d'"' -f2)"
[ -n "$VERSAO" ] || { echo "VERSAO não encontrada em tars.py" >&2; exit 1; }
REVISAO="$(grep -m1 '^REVISAO = ' "$RAIZ/tars.py" | cut -d' ' -f3)"
[ -n "$REVISAO" ] || { echo "REVISAO não encontrada em tars.py" >&2; exit 1; }
FONTE="$RAIZ/empacotamento"
PKG="$RAIZ/build/opentars_${VERSAO}"
SAIDA="$RAIZ/dist"

rm -rf "$PKG"
mkdir -p "$PKG/DEBIAN" \
         "$PKG/usr/bin" \
         "$PKG/usr/share/opentars" \
         "$PKG/usr/share/applications" \
         "$PKG/usr/share/icons/hicolor/scalable/apps" \
         "$PKG/usr/share/doc/opentars" \
         "$SAIDA"

# Programa: os módulos tars*.py e os textos de cada idioma
for modulo in "$RAIZ"/tars*.py; do
    install -m 644 "$modulo" "$PKG/usr/share/opentars/$(basename "$modulo")"
done
# 5.2: a camada de plataforma (um backend por sistema)
install -d "$PKG/usr/share/opentars/tars_plataforma"
install -m 644 "$RAIZ"/tars_plataforma/*.py "$PKG/usr/share/opentars/tars_plataforma/"
# 5.0: a janela em Qt (PySide6): tars_qt/ com as fontes IBM Plex (licença OFL)
install -d "$PKG/usr/share/opentars/tars_qt/fontes"
install -m 644 "$RAIZ"/tars_qt/*.py "$PKG/usr/share/opentars/tars_qt/"
install -m 644 "$RAIZ"/tars_qt/fontes/* "$PKG/usr/share/opentars/tars_qt/fontes/"
# Núcleo em partes (3.0): o tars.py executa nucleo/*.py
install -d "$PKG/usr/share/opentars/nucleo"
install -m 644 "$RAIZ"/nucleo/*.py "$PKG/usr/share/opentars/nucleo/"
# Murph (3.0.4): o modelo que decide o tipo do pedido
install -d "$PKG/usr/share/opentars/modelos"
install -m 644 "$RAIZ"/modelos/*.json "$PKG/usr/share/opentars/modelos/"
install -d "$PKG/usr/share/opentars/idiomas"
install -m 644 "$RAIZ"/idiomas/*.json "$PKG/usr/share/opentars/idiomas/"
install -m 755 "$FONTE/setup.sh"     "$PKG/usr/share/opentars/setup.sh"

# Comandos (+ atalhos com o nome antigo)
install -m 755 "$FONTE/bin/opentars"     "$PKG/usr/bin/opentars"
install -m 755 "$FONTE/bin/opentars-gui" "$PKG/usr/bin/opentars-gui"
ln -s opentars     "$PKG/usr/bin/tars"
ln -s opentars-gui "$PKG/usr/bin/tars-gui"

# Menu (os atalhos saem dos modelos, com os nomes em todos os idiomas) e ícone
python3 "$FONTE/gerar_desktop.py" "$FONTE/desktop" "$PKG/usr/share/applications"
chmod 644 "$PKG"/usr/share/applications/*.desktop
install -m 644 "$FONTE/icone/opentars.svg" "$PKG/usr/share/icons/hicolor/scalable/apps/opentars.svg"

# Documentação
install -m 644 "$FONTE/doc/copyright" "$PKG/usr/share/doc/opentars/copyright"
gzip -9n -c "$FONTE/doc/changelog" > "$PKG/usr/share/doc/opentars/changelog.gz"
chmod 644 "$PKG/usr/share/doc/opentars/changelog.gz"

# Controle
TAMANHO=$(du -sk --exclude=DEBIAN "$PKG" | cut -f1)
sed -e "s/@VERSAO@/$VERSAO+$REVISAO/" -e "s/@TAMANHO@/$TAMANHO/" "$FONTE/debian/control" > "$PKG/DEBIAN/control"
install -m 755 "$FONTE/debian/postinst" "$PKG/DEBIAN/postinst"
install -m 755 "$FONTE/debian/postrm"   "$PKG/DEBIAN/postrm"

dpkg-deb --root-owner-group --build "$PKG" "$SAIDA/opentars_${VERSAO}_all.deb"
echo "Gerado: $SAIDA/opentars_${VERSAO}_all.deb"
