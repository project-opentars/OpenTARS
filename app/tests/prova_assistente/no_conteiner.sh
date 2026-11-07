#!/bin/bash
# Roda a prova do assistente num contêiner descartável, com o Ollama e o SearXNG desta máquina (rede do host).
#   bash tests/prova_assistente/no_conteiner.sh [dev|guardada|final|todas] [ids...]
#   MODELO=nome bash ...   (padrão: ProjectOpenTARS/Gargantua-2:latest)
set -euo pipefail
cd "$(dirname "$0")/../.."
docker --context default build -q -t opentars-prova-assistente tests/prova_assistente >/dev/null
mkdir -p tests/prova_assistente/resultados
docker --context default run --rm --network host -v "$PWD":/app:ro -v /usr/share/opentars/venv:/usr/share/opentars/venv:ro \
  -v "$PWD/tests/prova_assistente/resultados":/saida -e MODELO="${MODELO:-ProjectOpenTARS/Gargantua-2:latest}" \
  opentars-prova-assistente /usr/share/opentars/venv/bin/python3 /app/tests/prova_assistente/rodar.py "$@"
