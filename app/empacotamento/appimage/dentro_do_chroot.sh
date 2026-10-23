#!/bin/bash
# Roda DENTRO do chroot Ubuntu 22.04 (glibc 2.35): monta /opt/AppDir com Python 3.12 portátil, PySide6, PyGObject
# (acessibilidade) e o openTARS. Chamado por build.sh. Variáveis: PROXY, NOPROXY (opcionais).
set -euo pipefail
AD=/opt/AppDir
PBS=/tmp/pbs.tgz
export PIP_CERT=/tmp/ca/ca-bundle.crt SSL_CERT_FILE=/tmp/ca/ca-bundle.crt REQUESTS_CA_BUNDLE=/tmp/ca/ca-bundle.crt
[ -n "${PROXY:-}" ] && export HTTPS_PROXY="$PROXY" https_proxy="$PROXY"
[ -n "${NOPROXY:-}" ] && export NO_PROXY="$NOPROXY" no_proxy="$NOPROXY"

rm -rf "$AD"; mkdir -p "$AD"
tar xzf "$PBS" -C "$AD"                     # cria $AD/python (relocável)
PY="$AD/python/bin/python3"
SP="$AD/python/lib/python3.12/site-packages"

"$PY" -m pip install --quiet --no-warn-script-location "PyGObject<3.51" pycairo patchelf -r /tmp/req.txt
PATCHELF="$AD/python/bin/patchelf"

# ---------- poda: o que o openTARS não usa ----------
PS="$SP/PySide6"
( cd "$PS"
  rm -rf Qt/qml Qt/translations Qt/libexec examples include glue typesystems scripts
  rm -f assistant linguist lupdate lrelease qmlls qmlformat qmllint qmlcachegen qmltyperegistrar designer rcc uic svgtoqml pyside6-* 2>/dev/null || true
  rm -rf Qt/plugins/designer Qt/plugins/qmltooling Qt/plugins/qmllint Qt/plugins/tls 2>/dev/null || true
  for f in *.abi3.so; do
      case "$f" in QtCore*|QtGui*|QtWidgets*|QtSvg*|QtSvgWidgets*|QtTest*|QtDBus*|QtNetwork*) ;; *) rm -f "$f" "${f%%.*}.pyi" ;; esac
  done
  rm -f *.pyi
  ( cd Qt/lib && rm -f libQt6Quick* libQt6Qml* libQt6Designer* libQt6Help* libQt6UiTools* libQt6WaylandCompositor* \
        libQt6Labs* libQt6Pdf* libQt6VirtualKeyboard* libQt6Multimedia* libQt6WebEngine* libQt6Sql* libQt6Concurrent* \
        libQt6Xml* libQt6PrintSupport* libQt6Positioning* libQt6Location* libQt6Bluetooth* libQt6Sensors* \
        libQt6Nfc* libQt6SerialPort* libQt6Test-nope 2>/dev/null || true )
)
( cd "$PS/Qt" && rm -f lib/libQt6Lottie* lib/libQt6EglFS* lib/libQt6EglFsKms* lib/libQt6WaylandEglCompositorHwIntegration* \
      plugins/platforms/libqeglfs* plugins/platforms/libqlinuxfb* plugins/platforms/libqvkkhrdisplay* plugins/platforms/libqvnc* \
      plugins/egldeviceintegrations -r 2>/dev/null || true; rm -rf plugins/egldeviceintegrations plugins/generic plugins/platforminputcontexts/libqtvirtualkeyboardplugin.so )
find "$SP" -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf "$AD/python/share" "$AD/python/include" "$AD/python/lib/pkgconfig" "$AD/python/lib/libpython3.12.a" \
       "$AD/python/lib/python3.12/test" "$AD/python/lib/python3.12/idlelib" "$AD/python/lib/python3.12/turtledemo" \
       "$AD/python/lib/python3.12/config-3.12-x86_64-linux-gnu" "$AD/python/lib/python3.12/ensurepip"
find "$AD/python/lib/python3.12" -type d \( -name test -o -name tests \) -prune -exec rm -rf {} + 2>/dev/null || true
rm -f "$AD/python/bin/idle3"* "$AD/python/bin/2to3"* "$AD/python/bin/pydoc"* "$AD/python/bin/pip"* "$AD/python/bin/python3-config" \
      "$AD/python/bin/python3.12-config"

# símbolos de depuração (o libpython sozinho tinha 200 MB)
find "$AD/python" -type f \( -name '*.so' -o -name '*.so.*' -o -name 'python3*' \) -exec sh -c '[ "$(head -c4 "$1" | tail -c3)" = ELF ] && strip --strip-unneeded "$1" 2>/dev/null' _ {} \; || true

# ---------- bibliotecas que o sistema do usuário costuma NÃO ter ----------
EXCLUI='^(libc|libm|libdl|libpthread|librt|libutil|libresolv|libnsl|libanl|libBrokenLocale|libcrypt|ld-linux.*|linux-vdso|libgcc_s|libstdc\+\+|libX11|libX11-xcb|libxcb|libXau|libXdmcp|libGL|libGLX|libGLdispatch|libEGL|libOpenGL|libGLESv2|libdrm|libfontconfig|libfreetype|libexpat|libpng16|libdbus-1|libsystemd|libudev|libcap|libgcrypt|libgpg-error|liblz4|liblzma|libzstd|libbsd|libmd|libglib-2\.0|libgobject-2\.0|libgio-2\.0|libgmodule-2\.0|libpcre|libmount|libblkid|libselinux|libz|libuuid)\.so'
coletar() {   # coletar <destino> <arquivos ou nomes de .so>...: copia o fecho das dependências (menos o EXCLUI)
    local destino="$1"; shift
    mkdir -p "$destino"
    local alvo
    for alvo in "$@"; do
        [ -e "$alvo" ] || alvo="$(ldconfig -p | awk -v n="$alvo" '$1==n {print $NF}' | head -1 || true)"
        [ -n "$alvo" ] && [ -e "$alvo" ] || continue
        ldd "$alvo" 2>/dev/null | awk '/=>/ && $3 ~ /^\// {print $3}' | while read -r lib; do
            base="$(basename "$lib")"
            [[ "$base" =~ $EXCLUI ]] && continue
            case "$lib" in "$AD"/*) continue ;; esac
            [ -e "$destino/$base" ] || cp -L "$lib" "$destino/$base"
        done
        case "$alvo" in "$AD"/*) ;; *) b="$(basename "$alvo")"; [[ "$b" =~ $EXCLUI ]] || { [ -e "$destino/$b" ] || cp -L "$alvo" "$destino/$b"; } ;; esac
    done
}
GI="$SP/gi"
GILIBS="$GI/lib"
coletar "$GILIBS" "$GI"/_gi*.so "$SP"/gi/_gi_cairo*.so "$SP"/cairo/_cairo*.so libatspi.so.0 libgirepository-1.0.so.1
# bibliotecas do Qt (plugin xcb): as que faltam numa instalação mínima
coletar "$PS/Qt/lib" libxcb-cursor.so.0 libxcb-icccm.so.4 libxcb-image.so.0 libxcb-keysyms.so.1 libxcb-render-util.so.0 \
        libxcb-shape.so.0 libxcb-xkb.so.1 libxkbcommon-x11.so.0 libxkbcommon.so.0 libxcb-util.so.1 libxcb-xinerama.so.0 \
        libxcb-randr.so.0 libxcb-sync.so.1 libxcb-xfixes.so.0
# rpath: cada pasta enxerga as suas (sem LD_LIBRARY_PATH, que vazaria para os programas que o TARS abre)
for f in "$GI"/_gi*.so "$SP"/cairo/_cairo*.so; do
    [ -e "$f" ] || continue
    case "$f" in "$SP"/cairo/*) "$PATCHELF" --set-rpath '$ORIGIN/../gi/lib' "$f" ;; *) "$PATCHELF" --set-rpath '$ORIGIN/lib' "$f" ;; esac
done
for f in "$GILIBS"/*.so*; do [ -L "$f" ] || "$PATCHELF" --set-rpath '$ORIGIN' "$f" 2>/dev/null || true; done
for f in "$PS"/Qt/lib/libxcb-*.so* "$PS"/Qt/lib/libxkbcommon*.so*; do [ -L "$f" ] || "$PATCHELF" --set-rpath '$ORIGIN' "$f" 2>/dev/null || true; done

# typelibs (Atspi, GLib, GObject, Gio, cairo...); a glib em si vem do sistema (os módulos do GIO dele continuam valendo)
mkdir -p "$AD/lib/girepository-1.0"
cp /usr/lib/x86_64-linux-gnu/girepository-1.0/*.typelib "$AD/lib/girepository-1.0/"

# ---------- o programa ----------
rm -rf "$AD/opentars"; mkdir -p "$AD/opentars"
cp -r /tmp/app/. "$AD/opentars/"
find "$AD/opentars" -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
"$PY" -m compileall -q "$AD/opentars" >/dev/null 2>&1 || true     # abre mais rápido (o AppImage é só leitura)

# ---------- pip e patchelf não vão no pacote ----------
"$PY" -m pip uninstall -y -q patchelf >/dev/null 2>&1 || true
rm -rf "$SP"/pip* "$SP"/_distutils_hack 2>/dev/null || true
find "$SP" -name 'patchelf*' -prune -exec rm -rf {} + 2>/dev/null || true
du -sh "$AD"
