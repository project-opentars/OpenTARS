"""5.3 (F4+++): agenda (.ics) e notas (Markdown) por código, sem modelo. Calendário de mentira com os casos que quebram leitores
simples: repetição semanal e mensal, exceção, instância alterada, dia inteiro, fuso, cancelado, linha dobrada. Desligado por padrão."""
import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
base = Path(tempfile.mkdtemp(prefix="opentars-integ-"))
os.environ["TARS_ARQUIVO_CONFIG"] = str(base / "config.json")
os.environ["HOME"] = str(base)
import tars_i18n  # noqa: E402
import tars_integracoes as ig  # noqa: E402

AGORA = dt.datetime(2026, 11, 8, 12, 0)          # domingo
ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:dentista
DTSTART:20261109T090000
DTEND:20261109T100000
SUMMARY:Dentista
LOCATION:Clínica Sorriso\\, sala 3
END:VEVENT
BEGIN:VEVENT
UID:daily
DTSTART:20261101T083000
DTEND:20261101T090000
RRULE:FREQ=DAILY;INTERVAL=1
EXDATE:20261110T083000
SUMMARY:Daily do time
END:VEVENT
BEGIN:VEVENT
UID:semanal
DTSTART:20261026T140000
DTEND:20261026T150000
RRULE:FREQ=WEEKLY;BYDAY=MO,WE
SUMMARY:Aula de inglês
END:VEVENT
BEGIN:VEVENT
UID:mensal
DTSTART:20260908T180000
DTEND:20260908T190000
RRULE:FREQ=MONTHLY;BYDAY=2TU
SUMMARY:Clube do livro
END:VEVENT
BEGIN:VEVENT
UID:contado
DTSTART:20261109T120000
DTEND:20261109T130000
RRULE:FREQ=DAILY;COUNT=2
SUMMARY:Almoço com a Ana
END:VEVENT
BEGIN:VEVENT
UID:semanal
RECURRENCE-ID:20261111T140000
DTSTART:20261111T160000
DTEND:20261111T170000
SUMMARY:Aula de inglês (remarcada)
END:VEVENT
BEGIN:VEVENT
UID:aniversario
DTSTART;VALUE=DATE:20261109
DTEND;VALUE=DATE:20261110
SUMMARY:Aniversário da Marina
END:VEVENT
BEGIN:VEVENT
UID:cancelado
DTSTART:20261109T110000
DTEND:20261109T120000
STATUS:CANCELLED
SUMMARY:Reunião cancelada
END:VEVENT
BEGIN:VEVENT
UID:dobrada
DTSTART:20261109T153000
DTEND:20261109T160000
SUMMARY:Revisão do contrato com o jurídico e
  o financeiro
END:VEVENT
BEGIN:VEVENT
UID:utc
DTSTART:20261109T210000Z
DTEND:20261109T220000Z
SUMMARY:Chamada com os EUA
END:VEVENT
END:VCALENDAR
"""
arq = base / "agenda.ics"
arq.write_text(ICS, encoding="utf-8")

# desligado por padrão: sem fonte, a frase vai para o modelo
assert ig.agendas() == [] and ig.pasta_de_notas() is None
assert ig.responder_agenda("o que tenho amanhã?", "pt", AGORA) is None and ig.responder("cria uma nota: x", "pt") is None
print("OK: sem agenda e sem pasta de notas escolhidas, nada responde (o pedido segue para o modelo)")

amanha = ig.responder_agenda("o que tenho amanhã?", "pt", AGORA, fontes=[str(arq)])
linhas = amanha.splitlines()
hora_eua = dt.datetime(2026, 11, 9, 21).replace(tzinfo=dt.timezone.utc).astimezone().replace(tzinfo=None)
assert linhas[0] == f"Amanhã você tem {6 + (hora_eua.date() == dt.date(2026, 11, 9))} compromissos:", amanha     # a chamada em UTC depende do fuso do computador
corpo = "\n".join(linhas[1:])
for esperado in ("Aniversário da Marina", "Daily do time", "Dentista (Clínica Sorriso, sala 3)", "Almoço com a Ana", "Aula de inglês",
                 "Revisão do contrato com o jurídico e o financeiro"):
    assert esperado in corpo, (esperado, amanha)
assert "Reunião cancelada" not in corpo, "evento cancelado não aparece"
assert "dia inteiro  Aniversário" in corpo and "09:00–10:00  Dentista" in corpo, corpo
assert (hora_eua.date() == dt.date(2026, 11, 9)) == ("Chamada com os EUA" in corpo), "o evento em UTC cai no dia certo do horário local"
print("OK: amanhã: repetição diária e semanal, dia inteiro, evento cancelado fora, linha dobrada e UTC no horário local")

# exceção e instância alterada
terca = ig.responder_agenda("what's on my calendar on Tuesday?", "en", AGORA, fontes=[str(arq)])
assert "Daily" not in terca, "o dia 10 tem exceção (EXDATE)"
assert "Book club" not in terca and "Clube do livro" in terca, terca            # 10/11/2026 é a 2ª terça: o evento mensal cai nela
quarta = ig.responder_agenda("o que tenho na quarta?", "pt", AGORA, fontes=[str(arq)])
assert "Aula de inglês (remarcada)" in quarta and "14:00" not in quarta and "16:00–17:00" in quarta, quarta
print("OK: exceção (EXDATE), 2ª terça do mês (BYDAY=2TU) e instância alterada (RECURRENCE-ID)")

# COUNT=2: dias 9 e 10, não o 11
dia11 = ig.responder_agenda("do I have anything on Wednesday?", "en", AGORA, fontes=[str(arq)])
assert "Lunch" not in dia11 and "Almoço" not in dia11, dia11
assert "Almoço com a Ana" in ig.responder_agenda("o que tenho amanhã", "pt", AGORA, fontes=[str(arq)])
assert "Almoço com a Ana" in ig.responder_agenda("o que tenho na terça", "pt", AGORA, fontes=[str(arq)])
print("OK: COUNT conta a partir do primeiro dia (2 ocorrências, não 2 a partir de hoje)")

# semana, próximo, vazio e frases que não são da agenda
QUARTA = dt.datetime(2026, 11, 11, 9, 0)           # esta semana = o que resta da semana (segunda a domingo)
semana = ig.responder_agenda("o que tenho esta semana?", "pt", QUARTA, fontes=[str(arq)])
assert "Esta semana você tem" in semana and "Aula de inglês (remarcada)" in semana and "Dentista" not in semana, semana
que_vem = ig.responder_agenda("what's on my calendar next week?", "en", AGORA, fontes=[str(arq)])
assert "Next week you have" in que_vem and "Dentista" in que_vem and "Mon 09/11" in que_vem, que_vem
assert ig.responder_agenda("qual meu próximo compromisso?", "pt", AGORA, fontes=[str(arq)]).startswith("Seu próximo compromisso: 09/11")
assert ig.responder_agenda("what is my next meeting", "en", AGORA, fontes=[str(arq)]).startswith("Your next event:")
vazio = base / "vazia.ics"
vazio.write_text("BEGIN:VCALENDAR\nEND:VCALENDAR\n")
assert ig.responder_agenda("o que tenho hoje?", "pt", AGORA, fontes=[str(vazio)]) == "Não há nada na agenda para hoje."
assert ig.responder_agenda("o que tenho na pasta Downloads?", "pt", AGORA, fontes=[str(arq)]) is None
assert ig.responder_agenda("quanto é 2 mais 2?", "pt", AGORA, fontes=[str(arq)]) is None
assert "Não consegui ler" in ig.responder_agenda("o que tenho hoje", "pt", AGORA, fontes=[str(base / "nao-existe.ics")])
print("OK: semana, próximo compromisso, agenda vazia, arquivo que sumiu e frases que não são da agenda")

# notas
pasta = base / "Notas"
assert ig.responder_notas("cria uma nota: comprar pão e leite", "pt", pasta=pasta).startswith("Nota criada: ")
assert ig.responder_notas("create a note about the trip to Lisbon\nbook the hotel", "en", pasta=pasta).startswith("Note created: ")
assert ig.responder_notas("cria uma nota", "pt", pasta=pasta) == "Diga o que escrever: cria uma nota: comprar pão."
nomes = sorted(p.name for p in pasta.iterdir())
assert len(nomes) == 2 and all(n.endswith(".md") and n[:4] == "2026" or n[:2] == "20" for n in nomes), nomes
primeira = next(p for p in pasta.iterdir() if "pao" in p.name)
assert primeira.read_text(encoding="utf-8") == "# comprar pão e leite\n\n", repr(primeira.read_text(encoding="utf-8"))
ig.responder_notas("cria uma nota: comprar pão e leite", "pt", pasta=pasta)          # mesmo dia, mesmo título: não sobrescreve
assert len(list(pasta.iterdir())) == 3 and primeira.exists()
achei = ig.responder_notas("minhas notas sobre Lisbon", "en", pasta=pasta)
assert "Found 1 in your notes" in achei and "lisbon" in achei.lower(), achei
lida = ig.responder_notas("show the note lisbon", "en", pasta=pasta)
assert lida.startswith("2026") and "book the hotel" in lida, lida
assert "Não achei nada nas notas sobre foguete" in ig.responder_notas("minhas notas sobre foguete", "pt", pasta=pasta)
assert ig.responder_notas("o que é uma nota fiscal?", "pt", pasta=pasta) is None and ig.responder_notas("anota que eu gosto de café", "pt", pasta=pasta) is None
print("OK: notas: cria .md novo (nunca por cima), acha, lê, e não confunde com memória nem com 'nota fiscal'")

# ligado pela configuração, o resolver do assistente usa as duas
tars_i18n.salvar_config(agenda_ics=[str(arq)], notas_pasta=str(pasta))
assert ig.agendas() == [str(arq)] and ig.pasta_de_notas() == pasta
assert ig.responder("minhas notas sobre foguete", "pt").startswith("Não achei nada nas notas")
import tars_atalhos  # noqa: E402
fala, ok = tars_atalhos._uma_parte("minhas notas sobre foguete", "pt", None, {}, True)
assert ok and "foguete" in fala
print("OK: pela configuração, o resolver do assistente (tars_atalhos) responde agenda e notas")
print("TUDO OK.")
