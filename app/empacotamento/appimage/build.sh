#!/bin/bash
# Monta o AppImage do openTARS (x86_64) pra rodar na maioria das distros.
#
#   sudo bash empacotamento/appimage/build.sh     (gera dist/openTARS-<versão>-x86_64.AppImage e dist/SHA256SUMS.novo)
#
# Como: monta um chroot Ubuntu 22.04 (glibc 2.35: o AppImage roda em qualquer distro com glibc igual ou mais nova),
# põe dentro um Python 3.12 portátil (python-build-standalone), o PySide6, o PyGObject (acessibilidade) e o
# openTARS, e empacota com o appimagetool. Precisa de: root (chroot), debootstrap, squashfs-tools, curl, ~3 GB livres e
# rede para archive.ubuntu.com, pypi.org e github.com. O resultado vem de fora dos binários do sistema onde roda
# (o Ollama e as ferramentas do desktop continuam sendo do sistema do usuário, como no .deb).

set -euo pipefail

AQUI="$(cd "$(dirname "$0")" && pwd)"
RAIZ="$(cd "$AQUI/../.." && pwd)"
VERSAO="$(grep -m1 '^VERSAO = ' "$RAIZ/tars.py" | cut -d'"' -f2)"
[ -n "$VERSAO" ] || { echo "VERSAO não encontrada em tars.py" >&2; exit 1; }
[ "$(id -u)" = 0 ] || { echo "Precisa de root (chroot): sudo bash $0" >&2; exit 1; }
for ferramenta in debootstrap mksquashfs curl; do
    command -v "$ferramenta" >/dev/null || { echo "Falta '$ferramenta' (sudo apt install debootstrap squashfs-tools curl)" >&2; exit 1; }
done

PBS_URL="${PBS_URL:-https://github.com/astral-sh/python-build-standalone/releases/download/20241016/cpython-3.12.7+20241016-x86_64-unknown-linux-gnu-install_only.tar.gz}"
TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
RUNTIME_URL="https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64"
CACHE="${TARS_CACHE_APPIMAGE:-$RAIZ/build/appimage-cache}"
ROOTFS="${TARS_ROOTFS:-$CACHE/jammy}"
SAIDA="$RAIZ/dist"
mkdir -p "$CACHE" "$SAIDA"

baixar() { [ -s "$CACHE/$2" ] || { echo "Baixando $2…"; curl -fsSL --retry 3 -o "$CACHE/$2.parte" "$1" && mv "$CACHE/$2.parte" "$CACHE/$2"; }; }
baixar "$PBS_URL" pbs.tgz
baixar "$TOOL_URL" appimagetool.AppImage
baixar "$RUNTIME_URL" runtime-x86_64
chmod +x "$CACHE/appimagetool.AppImage"

if [ ! -x "$ROOTFS/usr/bin/gcc" ]; then
    echo "Montando o Ubuntu 22.04 (uma vez só; fica em $ROOTFS)…"
    rm -rf "$ROOTFS"
    debootstrap --components=main,universe --variant=minbase \
        --include=build-essential,pkg-config,libgirepository1.0-dev,libcairo2-dev,gir1.2-atspi-2.0,libatspi2.0-0,libxcb-cursor0,libxcb-icccm4,libxcb-image0,libxcb-keysyms1,libxcb-render-util0,libxcb-shape0,libxcb-xkb1,libxkbcommon-x11-0,libxcb-xinerama0,libxcb-randr0,libxcb-sync1,libxcb-xfixes0,libxcb-util1 \
        jammy "$ROOTFS" http://archive.ubuntu.com/ubuntu
fi

# o que entra no chroot
rm -rf "$ROOTFS/tmp/app" "$ROOTFS/tmp/ca"
mkdir -p "$ROOTFS/tmp/app" "$ROOTFS/tmp/ca"
cp "$RAIZ"/tars*.py "$ROOTFS/tmp/app/"
for pasta in nucleo modelos idiomas tars_qt; do cp -r "$RAIZ/$pasta" "$ROOTFS/tmp/app/$pasta"; done
cp "$CACHE/pbs.tgz" "$ROOTFS/tmp/pbs.tgz"
cp "$AQUI/requirements.txt" "$AQUI/dentro_do_chroot.sh" "$ROOTFS/tmp/"
mv "$ROOTFS/tmp/requirements.txt" "$ROOTFS/tmp/req.txt"
cp /etc/resolv.conf "$ROOTFS/etc/resolv.conf"
for ca in "${SSL_CERT_FILE:-}" /root/.ccr/ca-bundle.crt /etc/ssl/certs/ca-certificates.crt; do
    [ -n "$ca" ] && [ -s "$ca" ] && { cp "$ca" "$ROOTFS/tmp/ca/ca-bundle.crt"; break; }
done
mount --bind /dev "$ROOTFS/dev" 2>/dev/null || true
mount -t proc proc "$ROOTFS/proc" 2>/dev/null || true
trap 'umount "$ROOTFS/proc" "$ROOTFS/dev" 2>/dev/null || true' EXIT

chroot "$ROOTFS" env PROXY="${HTTPS_PROXY:-}" NOPROXY="${NO_PROXY:-}" bash /tmp/dentro_do_chroot.sh

# AppDir final
TRABALHO="$RAIZ/build/appimage"
rm -rf "$TRABALHO"; mkdir -p "$TRABALHO"
cp -a "$ROOTFS/opt/AppDir" "$TRABALHO/AppDir"
cp "$AQUI/AppRun" "$AQUI/opentars.desktop" "$AQUI/opentars.svg" "$TRABALHO/AppDir/"
chmod 755 "$TRABALHO/AppDir/AppRun"
ln -sf opentars.svg "$TRABALHO/AppDir/.DirIcon"

DESTINO="$SAIDA/openTARS-${VERSAO}-x86_64.AppImage"
rm -f "$DESTINO"
ARCH=x86_64 "$CACHE/appimagetool.AppImage" --appimage-extract-and-run --comp zstd \
    --runtime-file "$CACHE/runtime-x86_64" "$TRABALHO/AppDir" "$DESTINO"
chmod 755 "$DESTINO"
( cd "$SAIDA" && sha256sum "$(basename "$DESTINO")" > SHA256SUMS.novo )
echo "Pronto: $DESTINO ($(du -h "$DESTINO" | cut -f1))"
echo "Some o conteúdo de dist/SHA256SUMS.novo ao SHA256SUMS da release (o .deb também entra)."
