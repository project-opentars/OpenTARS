"""5.3 (F4+++): a voz em português, só a lógica (sem microfone, sem Whisper, sem Kokoro): texto que soa natural falado, frases que o
Whisper inventa no silêncio, "TARS" em português, e a resposta falada curta."""
import os
import tempfile

os.environ.setdefault("XDG_DATA_HOME", tempfile.mkdtemp(prefix="opentars-dados-"))
from _util import carregar_tars  # noqa: E402

voz = carregar_tars().voz_lib
P = voz.preparar_para_fala

# dinheiro, horas, unidades, em português
assert P("O plano custa R$ 1.234,50 por mês.", "pt_BR") == "O plano custa 1234 reais e 50 centavos por mês."
assert P("Só R$ 1,00 e R$ 20 e R$ 3,5", "pt_BR") == "Só 1 real e 20 reais e 3 reais e 50 centavos"
assert P("A reunião é às 14h30 e termina às 16h, ou 1h depois, 9:05.", "pt_BR") == "A reunião é às 14 e 30 e termina às 16 horas, ou 1 hora depois, 9 e 05."
assert P("Pesa 2kg, mede 30 cm e anda a 80 km/h, 25 °C.", "pt_BR") == "Pesa 2 quilos, mede 30 centímetros e anda a 80 quilômetros por hora, 25 graus."
assert P("Custa $ 1,234.50 e $5 e $1", "en") == "Custa 1234 dollars and 50 cents e 5 dollars e 1 dollar"
assert P("It weighs 2kg and runs at 80 km/h", "en") == "It weighs 2 kilograms and runs at 80 kilometers per hour"
assert P("Rodou 12 min em 3 meses", "pt_BR") == "Rodou 12 min em 3 meses", "min e meses não são unidades"
print("OK: dinheiro (R$ e $), horas (14h30, 16h, 9:05) e unidades (kg, cm, mm, km/h) saem como se fala")

# o Whisper em português inventa despedida de vídeo no silêncio; frase de verdade nunca é cortada
for lixo in ("Obrigado por assistir!", "Se inscreva no canal.", "Deixe seu like", "Não se esqueça de se inscrever no canal", "Até a próxima!",
             "Tchau, tchau.", "[Música]", "(risos)", "Legendas realizadas pela comunidade Amara.org", "Tradução e legendas por João"):
    assert voz.e_alucinacao(lixo), lixo
for fala in ("abre o navegador", "tchau", "obrigado, TARS", "me lembra de ir ao banco às 14h", "quanto é 2 mais 2", "a música está alta demais"):
    assert not voz.e_alucinacao(fala), fala
print("OK: despedidas de vídeo e anotações entre colchetes caem; pedido de verdade não")

# "TARS" no começo em português
for texto, resto in (("Ei, TARS, abre o Firefox.", "abre o Firefox"), ("Oi Tars, que horas são?", "que horas são"), ("Olá TARS", "")):
    chamou, r = voz.achar_ativacao(texto)
    assert chamou and r == resto, (texto, chamou, r)
for texto in ("a gente falou do tars ontem à noite no jantar", "estrelas no céu"):
    assert not voz.achar_ativacao(texto)[0], texto
print("OK: a palavra de ativação em português")

# resposta falada curta
longo = ("A capital da França é Paris. Ela fica às margens do rio Sena. Tem cerca de dois milhões de habitantes. "
         "É famosa pela Torre Eiffel. Também tem o Louvre, um dos maiores museus do mundo. Recebe milhões de turistas por ano. "
         "Paris também é conhecida pela moda, pela gastronomia e pelos cafés. A cidade tem vinte distritos, numerados em espiral.")
assert len(longo) > voz.FALA_CURTA_CHARS
curto = voz.encurtar_para_fala(longo, "pt_BR")
assert curto == "A capital da França é Paris. Ela fica às margens do rio Sena. Tem cerca de dois milhões de habitantes. O resto está na tela.", curto
assert voz.encurtar_para_fala("Pronto, abri o Firefox.", "pt_BR") == "Pronto, abri o Firefox."
assert voz.encurtar_para_fala("Uma. Duas. Três.", "en") == "Uma. Duas. Três."
assert voz.encurtar_para_fala("x" * 400, "en") == "x" * 400, "sem frases para cortar, o texto passa como está (o limite geral é outro)"
assert voz.encurtar_para_fala(longo, "en").endswith("The rest is on the screen.")
assert voz.encurtar_para_fala("", "pt_BR") == ""
print("OK: resposta longa vira três frases e 'o resto está na tela'; resposta curta passa inteira")

# o Falador usa a preferência (curta por padrão; a pessoa pode pedir as respostas inteiras)
falado = []
f = voz.Falador()
f._falar = lambda texto, idioma, ao_terminar=None: falado.append(texto)
assert voz.PREFERENCIAS["curta"] is True
f.falar(longo, "pt_BR", esperar=True)
assert falado[-1].endswith("O resto está na tela.")
voz.configurar(curta=False)
f.falar(longo, "pt_BR", esperar=True)
assert "Recebe milhões de turistas por ano" in falado[-1] and not falado[-1].endswith("O resto está na tela.")
f.falar(longo, "pt_BR", esperar=True, curta=True)
assert falado[-1].endswith("O resto está na tela."), "o pedido explícito vale mais que a preferência"
voz.configurar(curta=True)
print("OK: o Falador fala curto por padrão; 'ler inteira' nas configurações desliga o corte")
print("TUDO OK.")
