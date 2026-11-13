"""5.3 (F7, passo 1 e a base do 2): a máquina virtual dos Probes do Pro (só Linux, QEMU/KVM direto, sem libvirt e sem root).

Este arquivo só cuida da IMAGEM e do que cerca a VM; o que um Probe faz lá dentro (quais ferramentas, como a tela é lida e
clicada, o aviso de saída) é o passo 2 em diante e espera a decisão do Enzo (portão do PLANO_5.3.md).

- Imagem base: Debian 12 "genericcloud" (334 MB) + um desktop leve (Xfce, Firefox, terminal), montada UMA vez numa VM de construção
  (o kernel "cloud" não tem driver de vídeo e a tela ficava preta: a base troca ele pelo kernel normal; achado de 08/11)
  (o módulo `mounts` do cloud-init criava /home/probe como root ANTES do usuário existir: sem dotfiles e sem dono, o Xfce não abria e o
  login automático voltava para a tela de senha; o ponto de montagem agora nasce no runcmd, depois do usuário; achado de 08/11)
  que baixa os pacotes do Debian, e depois só lida. Cada missão roda num overlay descartável: reset = apagar o overlay.
- A construção NÃO monta nenhuma pasta do computador na VM (sem virtfs, sem USB, sem arquivo do host além da semente do cloud-init)
  e a VM não leva chave, senha nem nada da conta de quem usa.
- Limite conhecido da imagem: o SHA-512 vem do mesmo servidor (cloud.debian.org, por HTTPS); a assinatura GPG da Debian não é
  conferida aqui.
- ISOLAMENTO, achado de 08/11 (a decidir no passo 3): com a rede "user" do QEMU a VM alcança o PC pelo endereço 10.0.2.2, ou seja,
  qualquer serviço que escute em 127.0.0.1 (SSH, Docker, bancos, o próprio Ollama). `restrict=on` fecha isso, mas fecha a internet
  também. Por isso a missão usa `restrict=on` e só o que for encaminhado (guestfwd) para o Ollama; internet livre pede um proxy
  ou outro desenho, e "enviar pede aprovação" não dá para impor na rede (HTTPS não deixa ver o método): é decisão de ferramenta.
"""
import hashlib
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import tars_motor_local
import tars_plataforma as plataforma

SERVIDOR = "https://cloud.debian.org/images/cloud/bookworm/latest/"
IMAGEM_ORIGEM = "debian-12-genericcloud-amd64.qcow2"
TAMANHO_ORIGEM_MB = 334
ESPACO_MINIMO_GB = 12          # a imagem montada ocupa ~3 a 5 GB; sobra para o download e para as missões
RAM_CONSTRUCAO_MB = 4096
CPUS_CONSTRUCAO = 4
TEMPO_CONSTRUCAO_S = 20 * 60          # medido em 08/11: instalar o desktop leva ~3 minutos; o resto é a VM desligando
ENDERECO_PROXY = "10.0.2.100:3128"    # onde a VM enxerga o proxy de saída do PC (guestfwd): a única porta que ela alcança fora de si
PACOTES_DESKTOP = ("linux-image-amd64", "xfce4", "xfce4-terminal", "lightdm", "firefox-esr", "xdg-utils", "curl", "ca-certificates", "xclip", "xdotool")
USUARIO_VM = "probe"


def pasta():
    return plataforma.pastas()["dados"] / "vm"


def imagem_base():
    return pasta() / "base.qcow2"


def _achar(*nomes):
    return next((shutil.which(n) for n in nomes if shutil.which(n)), None)


def diagnostico():
    """O que a VM precisa e o que há neste computador. Sem nada instalado ou alterado."""
    livre = shutil.disk_usage(pasta().parent if pasta().parent.exists() else Path.home()).free / 1e9
    return {"linux": plataforma.sistema() == "linux", "kvm": os.access("/dev/kvm", os.R_OK | os.W_OK),
            "qemu": _achar("qemu-system-x86_64"), "qemu_img": _achar("qemu-img"),
            "iso": _achar("genisoimage", "mkisofs", "xorriso"), "livre_gb": round(livre, 1),
            "base_pronta": imagem_base().exists()}


def o_que_falta(d=None):
    d = d or diagnostico()
    falta = []
    if not d["linux"]:
        falta.append("linux")
    if not d["kvm"]:
        falta.append("kvm")
    for chave, nome in (("qemu", "qemu-system-x86_64"), ("qemu_img", "qemu-img"), ("iso", "genisoimage")):
        if not d[chave]:
            falta.append(nome)
    if d["livre_gb"] < ESPACO_MINIMO_GB:
        falta.append(f"espaço ({d['livre_gb']} GB livres; precisa de {ESPACO_MINIMO_GB})")
    return falta


# ---------------------------------------------------------------- baixar a imagem do Debian (hash conferido)
def hash_da_imagem(texto_sha512sums, nome=IMAGEM_ORIGEM):
    """O SHA-512 do arquivo no SHA512SUMS do Debian, ou None."""
    for linha in texto_sha512sums.splitlines():
        m = re.fullmatch(r"([0-9a-f]{128})\s+\*?(\S+)", linha.strip())
        if m and m.group(2) == nome:
            return m.group(1)
    return None


def baixar_base_debian(destino=None, ao_progresso=None, baixar=tars_motor_local.baixar, ler_texto=None):
    """Baixa a imagem do Debian e confere o SHA-512 do SHA512SUMS do mesmo servidor. Devolve o caminho."""
    import urllib.request
    ler = ler_texto or (lambda url: urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "openTARS"}), timeout=30).read().decode())
    sha = hash_da_imagem(ler(SERVIDOR + "SHA512SUMS"))
    if not sha:
        raise ValueError("o SHA512SUMS do Debian não traz a imagem esperada")
    destino = Path(destino or pasta() / "debian-origem.qcow2")
    return baixar(SERVIDOR + IMAGEM_ORIGEM, destino, sha, ao_progresso, algoritmo="sha512")


# ---------------------------------------------------------------- a semente do cloud-init (instala o desktop e desliga)
def user_data():
    """O cloud-config da construção: um usuário sem senha de login, o desktop leve, entrada automática e desligar no fim.
    Não parar os serviços do cloud-init aqui dentro (`disable --now` mata o próprio cloud-final que está rodando estes comandos, e
    o `power_state` nunca roda: erro de 08/11, a VM ficou ligada até o limite de tempo). Para o cloud-init não rodar de novo, o
    arquivo /etc/cloud/cloud-init.disabled basta."""
    pacotes = "\n".join(f"  - {p}" for p in PACOTES_DESKTOP)
    return f"""#cloud-config
hostname: probe
users:
  - name: {USUARIO_VM}
    shell: /bin/bash
    lock_passwd: true
    sudo: ALL=(ALL) NOPASSWD:ALL
package_update: true
packages:
{pacotes}
write_files:
  - path: /etc/lightdm/lightdm.conf.d/50-probe.conf
    content: |
      [Seat:*]
      autologin-user={USUARIO_VM}
      autologin-session=xfce
  - path: /usr/lib/firefox-esr/distribution/policies.json
    content: |
      {{"policies": {{"Proxy": {{"Mode": "manual", "HTTPProxy": "{ENDERECO_PROXY}", "SSLProxy": "{ENDERECO_PROXY}", "UseHTTPProxyForAllProtocols": true, "Locked": true}},
        "DisableAppUpdate": true, "DontCheckDefaultBrowser": true, "OverrideFirstRunPage": "", "OverridePostUpdatePage": ""}}}}
runcmd:
  - mkdir -p /home/{USUARIO_VM}/saida
  - cp -rn /etc/skel/. /home/{USUARIO_VM}/
  - chown -R {USUARIO_VM}:{USUARIO_VM} /home/{USUARIO_VM}
  - echo 'LABEL=SAIDA /home/{USUARIO_VM}/saida vfat defaults,nofail,umask=000 0 0' >> /etc/fstab
  - systemctl set-default graphical.target
  - DEBIAN_FRONTEND=noninteractive apt-get purge -y linux-image-cloud-amd64 'linux-image-*-cloud-amd64' || true
  - update-grub
  - apt-get clean
  - printf 'http_proxy=http://{ENDERECO_PROXY}\\nhttps_proxy=http://{ENDERECO_PROXY}\\nHTTP_PROXY=http://{ENDERECO_PROXY}\\nHTTPS_PROXY=http://{ENDERECO_PROXY}\\nno_proxy=localhost,127.0.0.1\\n' >> /etc/environment
  - printf 'Acquire::http::Proxy "http://{ENDERECO_PROXY}";\\nAcquire::https::Proxy "http://{ENDERECO_PROXY}";\\n' > /etc/apt/apt.conf.d/99probe
  - touch /etc/cloud/cloud-init.disabled
power_state:
  mode: poweroff
  message: "base do openTARS pronta"
  timeout: 30
  condition: true
"""


def meta_data():
    return "instance-id: opentars-probe-base\nlocal-hostname: probe\n"


def criar_semente(pasta_destino, rodar=None):
    """Monta o seed.iso (rótulo cidata) com o user-data e o meta-data. Só estes dois arquivos entram."""
    rodar = rodar or (lambda argv: subprocess.run(argv, check=True, capture_output=True, text=True, timeout=60))
    pasta_destino = Path(pasta_destino)
    pasta_destino.mkdir(parents=True, exist_ok=True)
    (pasta_destino / "user-data").write_text(user_data(), encoding="utf-8")
    (pasta_destino / "meta-data").write_text(meta_data(), encoding="utf-8")
    ferramenta = _achar("genisoimage", "mkisofs", "xorriso")
    if not ferramenta:
        raise RuntimeError("falta genisoimage (ou mkisofs, ou xorriso) para montar a semente")
    iso = pasta_destino / "seed.iso"
    argv = [ferramenta, "-output", str(iso), "-volid", "cidata", "-joliet", "-rock", str(pasta_destino / "user-data"), str(pasta_destino / "meta-data")]
    if ferramenta.endswith("xorriso"):
        argv = [ferramenta, "-as", "mkisofs"] + argv[1:]
    rodar(argv)
    return iso


# ---------------------------------------------------------------- QEMU
def argumentos_qemu(disco, semente=None, ram_mb=RAM_CONSTRUCAO_MB, cpus=CPUS_CONSTRUCAO, internet=True, ollama=None, log=None, controle=None):
    """A linha do qemu. NUNCA monta pasta do computador (sem virtfs, fsdev nem USB). `internet=False` é o modo da missão: rede "user"
    com restrict=on, e só o encaminhamento para o Ollama (ollama=(porta_do_host)) chega ao computador; a VM o enxerga em 10.0.2.100:11434."""
    rede = "user,id=n0"
    if not internet:
        rede += ",restrict=on"
        if ollama:
            rede += f",guestfwd=tcp:10.0.2.100:11434-tcp:127.0.0.1:{int(ollama)}"
    argv = ["qemu-system-x86_64", "-enable-kvm", "-cpu", "host", "-m", str(int(ram_mb)), "-smp", str(int(cpus)),
            "-drive", f"file={disco},if=virtio,format=qcow2", "-netdev", rede, "-device", "virtio-net-pci,netdev=n0",
            "-display", "none", "-nodefaults", "-vga", "virtio", "-no-reboot"]
    if semente:
        argv += ["-drive", f"file={semente},if=virtio,media=cdrom,readonly=on,format=raw"]
    if log:
        argv += ["-serial", f"file:{log}"]
    if controle:        # o canal de FORA (decidido em 08/11): um socket unix só do usuário, sem porta de rede; a VM não tem agente
        argv += ["-device", "virtio-tablet-pci", "-device", "virtio-keyboard-pci", "-qmp", f"unix:{controle},server=on,wait=off"]
    return argv


# ---------------------------------------------------------------- overlay descartável (reset = apagar)
def criar_overlay(base, destino, rodar=None):
    rodar = rodar or (lambda argv: subprocess.run(argv, check=True, capture_output=True, text=True, timeout=60))
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.unlink(missing_ok=True)
    rodar(["qemu-img", "create", "-f", "qcow2", "-F", "qcow2", "-b", str(Path(base).resolve()), str(destino)])
    return destino


def apagar_overlay(overlay):
    """Reset: o overlay some e a base continua intacta (nunca é aberta para escrita pelas missões)."""
    Path(overlay).unlink(missing_ok=True)


# ---------------------------------------------------------------- montar a imagem base (a parte que baixa e instala)
def construir_base(ao_progresso=None, avisar=print, popen=subprocess.Popen, esperar=time.sleep):
    """Baixa o Debian, instala o desktop leve numa VM de construção (com internet), espera ela desligar e guarda a base já
    comprimida. Devolve {segundos, tamanho_mb}. Demora minutos e usa a internet: só roda por pedido da pessoa."""
    falta = o_que_falta()
    if falta:
        raise RuntimeError("falta: " + ", ".join(falta))
    inicio = time.monotonic()
    pasta().mkdir(parents=True, exist_ok=True)
    origem = baixar_base_debian(ao_progresso=ao_progresso)
    trabalho = pasta() / "construcao"
    trabalho.mkdir(exist_ok=True)
    disco = trabalho / "disco.qcow2"
    shutil.copy2(origem, disco)
    subprocess.run(["qemu-img", "resize", str(disco), "8G"], check=True, capture_output=True, timeout=60)
    semente = criar_semente(trabalho)
    log = trabalho / "console.log"
    avisar("montando o desktop na VM de construção…")
    processo = popen(argumentos_qemu(disco, semente, log=log), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    limite = time.monotonic() + TEMPO_CONSTRUCAO_S
    while processo.poll() is None:
        if time.monotonic() > limite:
            processo.kill()
            raise TimeoutError("a construção passou de 20 minutos (a VM não desligou sozinha)")
        esperar(5)
    if processo.returncode != 0:
        raise RuntimeError(f"o qemu terminou com erro {processo.returncode} (veja {log})")
    temporario = pasta() / "base.qcow2.novo"
    subprocess.run(["qemu-img", "convert", "-O", "qcow2", "-c", str(disco), str(temporario)], check=True, capture_output=True, timeout=1800)
    os.replace(temporario, imagem_base())
    shutil.rmtree(trabalho, ignore_errors=True)
    origem.unlink(missing_ok=True)
    return {"segundos": round(time.monotonic() - inicio), "tamanho_mb": round(imagem_base().stat().st_size / 1e6)}
