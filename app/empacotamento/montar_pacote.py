#!/usr/bin/env python3
"""Monta o openTARS empacotado do Windows e do macOS (14/11/2026, decisão do Enzo: o app vem pronto, a instalação não baixa
nada). Roda no CI, no sistema de destino:

    python app/empacotamento/montar_pacote.py --saida dist/pacote

O que sai em --saida:
  Windows: openTARS/ com runtime/ (Python 3.12 portátil com as dependências), app/ (o código, com o llama-server em
           app/motor-embutido/) e bin/opentars.cmd. O Inno Setup (windows/opentars.iss) embrulha essa pasta no setup.exe.
  macOS:   openTARS.app (Contents/Resources/runtime, app, bin/opentars), assinado ad-hoc, e openTARS-macos-<máquina>.dmg.

Por que um Python portátil e não PyInstaller: o app sobe processos com sys.executable (motor, Probes, voz, prova) e carrega o
núcleo por exec de arquivos .py; com um Python de verdade dentro do pacote tudo isso continua igual ao Linux, sem um
"congelamento" que mudaria o comportamento.
"""
import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parent.parent          # fonte/app
sys.path.insert(0, str(APP))

# python-build-standalone (Astral), versão fixa: 3.12.16 de 26/10/2026, conferida pelo SHA-256 publicado no GitHub
_PBS = "https://github.com/astral-sh/python-build-standalone/releases/download/20261026/"
PYTHON = {
    ("windows", "x86_64"): ("cpython-3.12.16+20261026-x86_64-pc-windows-msvc-install_only.tar.gz",
                            "590dfcbe3a34c07301e6332e13e2188b98655cd072b08afa45a7998dc4c22bc5"),
    ("macos", "arm64"): ("cpython-3.12.16+20261026-aarch64-apple-darwin-install_only.tar.gz",
                         "fbf4afef53c2a6b72bb741bc06d5671a9dfaf87bd84e5aa73ac9b3d0d589f14e"),
    ("macos", "x86_64"): ("cpython-3.12.16+20261026-x86_64-apple-darwin-install_only.tar.gz",
                          "a962e47df522889eaa7ff0d6a56203f1079f68aabb65ffdbe8455f362bc769f3"),
}
DEPENDENCIAS = ["requests", "psutil", "pyautogui", "pillow", "PySide6-Essentials", "numpy", "onnxruntime", "keyring", "pip"]
EXTRAS = {"windows": ["uiautomation"], "macos": ["pyobjc-framework-ApplicationServices", "pyobjc-framework-Quartz"]}
# o que não vai para o pacote: testes, o kit de treino, a documentação, o empacotamento dos outros sistemas, restos de build
FORA = {"tests", "gargantua", "docs", "build", "dist", "__pycache__", ".git", "appimage", "debian", "winget", "linux"}


def sistema_e_maquina():
    s = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    m = platform.machine().lower()
    return s, {"amd64": "x86_64", "aarch64": "arm64"}.get(m, m)


def baixar(url, destino, sha):
    destino = Path(destino)
    if destino.exists() and hashlib.sha256(destino.read_bytes()).hexdigest() == sha:
        return destino
    print("baixando", url, flush=True)
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "openTARS-build"}), timeout=300) as r:
        destino.write_bytes(r.read())
    if hashlib.sha256(destino.read_bytes()).hexdigest() != sha:
        destino.unlink()
        raise SystemExit(f"SHA-256 errado: {url}")
    return destino


def python_do(runtime, s):
    return runtime / ("python.exe" if s == "windows" else "bin/python3")


def montar_runtime(runtime, s, m, cache):
    arquivo, sha = PYTHON[(s, m)]
    pacote = baixar(_PBS + arquivo.replace("+", "%2B"), cache / arquivo, sha)
    temporario = runtime.parent / "python-extraido"
    shutil.rmtree(temporario, ignore_errors=True)
    with tarfile.open(pacote) as t:
        t.extractall(temporario, filter="data")
    shutil.rmtree(runtime, ignore_errors=True)
    shutil.move(str(temporario / "python"), runtime)
    shutil.rmtree(temporario)
    py = python_do(runtime, s)
    subprocess.run([str(py), "-m", "pip", "install", "--no-warn-script-location", "--disable-pip-version-check", "--no-cache-dir",
                    *DEPENDENCIAS, *EXTRAS.get(s, [])], check=True)
    # o pacote não precisa do que só serve para compilar (cabeçalhos) nem dos testes do próprio Python
    for sobra in ("include", "Lib/test", "lib/python3.12/test", "Lib/idlelib", "lib/python3.12/idlelib"):
        shutil.rmtree(runtime / sobra, ignore_errors=True)
    subprocess.run([str(py), "-c", "import PySide6.QtWidgets, numpy, onnxruntime, requests, psutil, PIL; print('dependências ok')"], check=True)
    return py


def copiar_app(destino):
    def ignorar(pasta, nomes):
        fora = {n for n in nomes if n in FORA or n.endswith((".pyc", ".deb", ".log"))}
        if Path(pasta).name == "empacotamento":                 # só ficam os ícones e os scripts do próprio sistema
            fora |= {n for n in nomes if n not in ("windows", "macos", "icone", "desktop")}
        return fora
    shutil.rmtree(destino, ignore_errors=True)
    shutil.copytree(APP, destino, ignore=ignorar)


def embutir_motor(app_destino, s, m, cache):
    """O llama-server da versão fixa do motor, para esta máquina (Vulkan e CPU no Windows; Metal ou CPU no macOS)."""
    import zipfile
    import tars_motor_local as motor
    for (sistema, maquina, variante), (arquivo, sha) in motor.BINARIOS.items():
        if (sistema, maquina) != (s, m):
            continue
        pacote = baixar(motor._GH + arquivo, cache / arquivo, sha)
        raiz = app_destino / "motor-embutido" / motor.VERSAO_LLAMA / variante
        shutil.rmtree(raiz, ignore_errors=True)
        raiz.mkdir(parents=True)
        if arquivo.endswith(".zip"):
            with zipfile.ZipFile(pacote) as z:
                z.extractall(raiz)
        else:
            with tarfile.open(pacote) as t:
                t.extractall(raiz, filter="data")
        for executavel in raiz.rglob("llama-server*"):
            executavel.chmod(0o755)
        # só o servidor e as bibliotecas dele: as outras ferramentas do llama.cpp (llama-cli, quantize...) ficam de fora
        for f in raiz.rglob("*"):
            if f.is_file() and f.name.startswith("llama-") and not f.name.startswith("llama-server"):
                f.unlink()
        print("motor embutido:", variante, flush=True)


def versao_do_app():
    import re
    texto = (APP / "tars.py").read_text(encoding="utf-8")
    return re.search(r'^VERSAO\s*=\s*"([^"]+)"', texto, re.M).group(1), re.search(r"^REVISAO\s*=\s*(\d+)", texto, re.M).group(1)


def montar_windows(saida, cache):
    raiz = saida / "openTARS"
    raiz.mkdir(parents=True, exist_ok=True)
    montar_runtime(raiz / "runtime", "windows", "x86_64", cache)
    copiar_app(raiz / "app")
    embutir_motor(raiz / "app", "windows", "x86_64", cache)
    (raiz / "app" / ".empacotado").write_text("windows\n")
    (raiz / "bin").mkdir(exist_ok=True)
    # o comando do terminal; %~dp0 é a pasta deste .cmd, então o pacote funciona em qualquer pasta
    (raiz / "bin" / "opentars.cmd").write_text('@echo off\r\nset PYTHONUTF8=1\r\n"%~dp0..\\runtime\\python.exe" "%~dp0..\\app\\tars.py" %*\r\n',
                                              encoding="ascii")
    print("pronto:", raiz)


INFO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>openTARS</string>
  <key>CFBundleDisplayName</key><string>openTARS</string>
  <key>CFBundleIdentifier</key><string>io.github.project-opentars.opentars</string>
  <key>CFBundleExecutable</key><string>openTARS</string>
  <key>CFBundleIconFile</key><string>opentars</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>{versao}</string>
  <key>CFBundleVersion</key><string>{revisao}</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSMicrophoneUsageDescription</key><string>openTARS listens for your voice requests when you turn the voice on. The audio stays on this Mac.</string>
  <key>NSAppleEventsUsageDescription</key><string>openTARS opens and controls apps when you ask it to.</string>
</dict></plist>
"""

# o lançador: entra na pasta do código e troca de processo para o Python do próprio app (exec), que vira o processo do app
LANCADOR_MAC = """#!/bin/bash
RES="$(cd "$(dirname "$0")/../Resources" && pwd)"
cd "$RES/app" && exec "$RES/runtime/bin/python3" -m tars_qt "$@"
"""
CLI_MAC = """#!/bin/bash
# o comando opentars do terminal (o instalar.sh liga ~/.local/bin/opentars a este arquivo)
ALVO="$0"
while [ -L "$ALVO" ]; do ALVO="$(readlink "$ALVO")"; done
RES="$(cd "$(dirname "$ALVO")/.." && pwd)"
exec "$RES/runtime/bin/python3" "$RES/app/tars.py" "$@"
"""


def montar_macos(saida, cache):
    s, m = "macos", sistema_e_maquina()[1]
    pacote = saida / "openTARS.app"
    shutil.rmtree(pacote, ignore_errors=True)
    recursos = pacote / "Contents" / "Resources"
    (pacote / "Contents" / "MacOS").mkdir(parents=True)
    recursos.mkdir(parents=True)
    montar_runtime(recursos / "runtime", s, m, cache)
    copiar_app(recursos / "app")
    embutir_motor(recursos / "app", s, m, cache)
    (recursos / "app" / ".empacotado").write_text("macos\n")
    shutil.copy(APP / "empacotamento" / "macos" / "opentars.icns", recursos / "opentars.icns")
    versao, revisao = versao_do_app()
    (pacote / "Contents" / "Info.plist").write_text(INFO_PLIST.format(versao=versao, revisao=revisao))
    lancador = pacote / "Contents" / "MacOS" / "openTARS"
    lancador.write_text(LANCADOR_MAC)
    (recursos / "bin").mkdir()
    cli = recursos / "bin" / "opentars"
    cli.write_text(CLI_MAC)
    for f in (lancador, cli):
        f.chmod(0o755)
    # assinatura ad-hoc (grátis, sem conta da Apple): o Apple Silicon só roda código assinado
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(pacote)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(pacote)], check=True)
    dmg = saida / f"openTARS-macos-{m}.dmg"
    dmg.unlink(missing_ok=True)
    pasta_dmg = saida / "dmg"
    shutil.rmtree(pasta_dmg, ignore_errors=True)
    pasta_dmg.mkdir()
    subprocess.run(["ditto", str(pacote), str(pasta_dmg / "openTARS.app")], check=True)
    os.symlink("/Applications", pasta_dmg / "Applications")      # arrastar para Aplicativos, como todo .dmg
    subprocess.run(["hdiutil", "create", "-volname", "openTARS", "-srcfolder", str(pasta_dmg), "-ov", "-format", "UDZO", str(dmg)], check=True)
    shutil.rmtree(pasta_dmg)
    print("pronto:", dmg)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--saida", required=True)
    a = p.parse_args()
    saida = Path(a.saida).resolve()
    cache = saida / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    s, _ = sistema_e_maquina()
    if s == "windows":
        montar_windows(saida, cache)
    elif s == "macos":
        montar_macos(saida, cache)
    else:
        raise SystemExit("o pacote empacotado é do Windows e do macOS; no Linux o app sai como .deb (build.sh)")


if __name__ == "__main__":
    main()
