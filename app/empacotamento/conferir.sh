#!/bin/bash
# Conferência antes de publicar o app (16/10). Junta as travas dos defeitos que já escaparam:
#   1. textos: idiomas iguais, chaves existentes, nenhum glifo fora da IBM Plex, tudo compila (tests/test_textos.py);
#   2. a suíte inteira, sem nenhuma falha aceita;
#   3. fumaça na TELA DE VERDADE (tests/fumaca_tela_real.py): a suíte roda em tela falsa e com cache de fontes novo,
#      e por isso não viu a queda dos Probes na 2026101603;
#   4. REVISAO maior que a do .deb publicado (o mesmo número duas vezes já confundiu instalações do Lab).
# Uso: bash empacotamento/conferir.sh   (em fonte/app; código 0 = pode empacotar)

set -uo pipefail
cd "$(dirname "$0")/.."
PY=/usr/share/opentars/venv/bin/python3
[ -x "$PY" ] || PY=python3
CONHECIDAS=""            # 16/10: as três "de ambiente" eram defeitos dos testes e foram corrigidas; nenhuma falha é aceita
problemas=()
registro=$(mktemp)
trap 'rm -f "$registro"' EXIT

echo "== 1/4 Textos, glifos e compilação"
(cd tests && "$PY" test_textos.py) || problemas+=("textos (tests/test_textos.py)")

echo "== 2/4 Suíte (alguns minutos)"
if command -v xvfb-run >/dev/null; then
    (cd tests && xvfb-run -a "$PY" -u run_all.py) > "$registro" 2>&1
else
    (cd tests && QT_QPA_PLATFORM=offscreen "$PY" -u run_all.py) > "$registro" 2>&1
fi
linha=$(grep -E "^FALHARAM \(" "$registro" | tail -1)
if [ -n "$linha" ]; then
    for teste in $(echo "${linha#*: }" | tr ',' ' '); do
        case " $CONHECIDAS " in *" $teste "*) ;; *) problemas+=("suíte: $teste");; esac
    done
fi
echo "${linha:-suíte sem falhas}"

echo "== 3/4 Fumaça na tela de verdade"
if (cd tests && timeout 300 "$PY" fumaca_tela_real.py) > /dev/null 2>&1; then
    echo "a janela abriu todas as telas sem cair"
else
    problemas+=("fumaça na tela real (rode: cd tests && $PY fumaca_tela_real.py)")
fi

echo "== 4/4 REVISAO"
nova=$(grep -oP '^REVISAO = \K\d+' tars.py)
publicado="../../opentars_all.deb"
if [ -f "$publicado" ]; then
    antiga=$(dpkg-deb -f "$publicado" Version 2>/dev/null | grep -oP '\+\K\d+$' || echo 0)
    if [ "${nova:-0}" -le "${antiga:-0}" ]; then
        problemas+=("REVISAO $nova não é maior que a do opentars_all.deb da entrega ($antiga): suba em tars.py")
    fi
    echo "REVISAO nova $nova, entrega $antiga"
fi

echo
if [ ${#problemas[@]} -eq 0 ]; then
    echo "CONFERÊNCIA OK: pode rodar bash empacotamento/build.sh"
    exit 0
fi
echo "CONFERÊNCIA FALHOU:"
printf '  - %s\n' "${problemas[@]}"
exit 1
