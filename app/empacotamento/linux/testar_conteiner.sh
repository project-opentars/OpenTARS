#!/bin/bash
# Teste do instalar.sh num contêiner de Fedora, Arch ou openSUSE (o CI usa; à mão também):
#   docker run --rm -v "$PWD/app:/fonte:ro" fedora:latest bash /fonte/empacotamento/linux/testar_conteiner.sh
# Instala como root (pacotes do sistema), depois como usuário comum, confere o ambiente, o diagnóstico, alguns testes,
# a janela de verdade num X virtual, e remove. Sem Ollama e sem modelo.
set -euo pipefail
INSTALADOR=/fonte/empacotamento/linux/instalar.sh
passo() { echo; echo "######## $*"; }

if command -v pacman >/dev/null; then
    passo "Arch: o contêiner vem com a base velha; atualizar antes (o instalador pede isso no Arch)"
    pacman -Syu --noconfirm >/dev/null
fi

passo "Instalação como root (pacotes do sistema)"
time bash "$INSTALADOR" --fonte /fonte --sem-ollama

passo "Pacotes só para o teste: Xvfb"
if command -v dnf >/dev/null; then dnf install -y -q xorg-x11-server-Xvfb xorg-x11-xauth util-linux >/dev/null
elif command -v pacman >/dev/null; then pacman -S --needed --noconfirm xorg-server-xvfb xorg-xauth >/dev/null
elif command -v zypper >/dev/null; then zypper --non-interactive install --no-recommends xvfb-run xauth gawk >/dev/null
fi

passo "Usuário comum: instalação sem pacotes do sistema"
useradd -m ana
su - ana -c "bash $INSTALADOR --fonte /fonte --sem-ollama --sem-sistema" | tail -4
su - ana -c 'ls -la ~/.local/bin/ && head -3 ~/.local/share/applications/opentars.desktop && grep -E "^Exec=" ~/.local/share/applications/opentars.desktop'
su - ana -c 'grep -n "DIR_OPENTARS=\|^PYTHON=\|--chat" ~/.local/bin/opentars-gui'

passo "Python, PyGObject/AT-SPI e Qt no ambiente instalado"
su - ana -c '~/.local/share/opentars-app/venv/bin/python3 --version'
su - ana -c '~/.local/share/opentars-app/venv/bin/python3 -c "import gi; gi.require_version(\"Atspi\", \"2.0\"); from gi.repository import Atspi; print(\"atspi ok\")"'
su - ana -c 'cd ~/.local/share/opentars-app/app && QT_QPA_PLATFORM=offscreen ~/.local/share/opentars-app/venv/bin/python3 -c "import tars_qt.principal; print(\"qt ok\")"'
passo "Bibliotecas que o plugin xcb do Qt não achou (vazio = todas presentes)"
su - ana -c 'ldd ~/.local/share/opentars-app/venv/lib/python3*/site-packages/PySide6/Qt/plugins/platforms/libqxcb.so | grep "not found" || true'

passo "Diagnóstico pelo comando instalado"
su - ana -c '~/.local/bin/opentars --diagnostico' > /tmp/diag.txt 2>&1 || true
tail -25 /tmp/diag.txt
su - ana -c 'test -f ~/opentars-autoteste.txt && echo "relatório salvo"'

passo "Dicas de instalação com o gerenciador daqui"
su - ana -c 'cd ~/.local/share/opentars-app/app && ~/.local/share/opentars-app/venv/bin/python3 -c "import tars_plataforma as p; print(p.comando_instalar(\"python3-gi\", \"gir1.2-atspi-2.0\", \"python3-tk\", \"poppler-utils\"))"'

passo "Testes do app no ambiente instalado"
for t in test_plataforma test_shell_portatil test_probes_servico test_acessibilidade_outros_sistemas test_atalhos_outros_sistemas; do
    su - ana -c "cd ~/.local/share/opentars-app/app/tests && ~/.local/share/opentars-app/venv/bin/python3 $t.py" 2>&1 | tail -1
done

passo "A janela de verdade abre (opentars-gui num X virtual por 25 s)"
codigo=0
su - ana -c 'timeout 25 xvfb-run -a ~/.local/bin/opentars-gui' > /tmp/gui.txt 2>&1 || codigo=$?
echo "código de saída: $codigo (124 = continuou aberta até o timeout)"
tail -5 /tmp/gui.txt
if grep -q "Aborted\|Crashed\|could not load the Qt platform plugin" /tmp/gui.txt; then
    echo "FALHOU: a janela Qt não abriu (o app caiu para a janela simples)"; exit 1
fi
[ "$codigo" = 124 ] || { echo "FALHOU: a janela fechou sozinha"; exit 1; }
su - ana -c 'grep -il "traceback" ~/.tars_log/*.log 2>/dev/null && tail -20 ~/.tars_log/qt.log || echo "sem traceback nos logs"'

passo "Remoção"
su - ana -c "bash $INSTALADOR --remover" | tail -1
su - ana -c 'test ! -e ~/.local/share/opentars-app && test ! -e ~/.local/bin/opentars-gui && test ! -e ~/.local/share/applications/opentars.desktop && echo "removido"'
echo "FIM OK"
