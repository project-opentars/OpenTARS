# Ubuntu 24.04: o mesmo Python 3.12 do venv do openTARS, que entra montado só para leitura. A prova roda aqui dentro para
# nunca tocar a máquina de quem roda (lição de 01/11: um comando com caminho absoluto escaparia da casa temporária).
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-requests python3-psutil python3-pil curl ca-certificates zstd pciutils procps iproute2 zip unzip file systemd git alsa-utils \
    && rm -rf /var/lib/apt/lists/*
ENV LANG=C.UTF-8
