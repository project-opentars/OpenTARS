#!/usr/bin/env bash
# Gera os 3 manifestos do winget para uma Release do openTARS.
#   bash gerar.sh 5.3 CAMINHO/opentars-setup.exe [saida]
# Depois: copiar a pasta para manifests/p/project-opentars/openTARS/<versao>/ de um fork de microsoft/winget-pkgs e abrir o PR.
set -euo pipefail
VERSAO="$1"; EXE="$2"; SAIDA="${3:-saida/$VERSAO}"
SHA=$(sha256sum "$EXE" | cut -d' ' -f1 | tr a-f A-F)
URL="https://github.com/project-opentars/OpenTARS/releases/download/$VERSAO/opentars-setup.exe"
mkdir -p "$SAIDA"
P=project-opentars.openTARS
cat > "$SAIDA/$P.yaml" <<Y
# yaml-language-server: \$schema=https://aka.ms/winget-manifest.version.1.6.0.schema.json
PackageIdentifier: $P
PackageVersion: $VERSAO
DefaultLocale: en-US
ManifestType: version
ManifestVersion: 1.6.0
Y
cat > "$SAIDA/$P.installer.yaml" <<Y
# yaml-language-server: \$schema=https://aka.ms/winget-manifest.installer.1.6.0.schema.json
PackageIdentifier: $P
PackageVersion: $VERSAO
InstallerType: inno
Scope: user
InstallModes: [interactive, silent, silentWithProgress]
InstallerSwitches:
  Silent: /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
  SilentWithProgress: /SILENT /SUPPRESSMSGBOXES /NORESTART
UpgradeBehavior: install
ReleaseDate: $(date +%F)
Installers:
  - Architecture: x64
    InstallerUrl: $URL
    InstallerSha256: $SHA
ManifestType: installer
ManifestVersion: 1.6.0
Y
cat > "$SAIDA/$P.locale.en-US.yaml" <<Y
# yaml-language-server: \$schema=https://aka.ms/winget-manifest.defaultLocale.1.6.0.schema.json
PackageIdentifier: $P
PackageVersion: $VERSAO
PackageLocale: en-US
Publisher: project-opentars
PublisherUrl: https://project-opentars.github.io/OpenTARS/
PublisherSupportUrl: https://github.com/project-opentars/OpenTARS/issues
PackageName: openTARS
PackageUrl: https://project-opentars.github.io/OpenTARS/
License: MIT
LicenseUrl: https://github.com/project-opentars/OpenTARS/blob/main/LICENSE
ShortDescription: A 100% local AI assistant for your computer, local by default.
Description: openTARS runs small AI models on your own machine (llama.cpp), controls apps, files and the screen with your approval, and keeps your data at home. Cloud is optional and off by default.
Moniker: opentars
Tags: [ai, assistant, local, llm, privacy, llama-cpp]
ManifestType: defaultLocale
ManifestVersion: 1.6.0
Y
echo "Manifestos em $SAIDA (SHA-256 $SHA)"
