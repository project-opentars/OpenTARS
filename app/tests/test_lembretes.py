"""5.3 (F4++): lembretes e timers por frase, sem o modelo. Só o entendimento da frase (nada é agendado)."""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tars_lembretes as l  # noqa: E402

A = dt.datetime(2026, 11, 13, 16, 12)
for frase in ("Set a timer for 10 minutes", "start a timer for 10 minutes", "set a 10 minute timer", "põe um timer de 10 minutos", "set a timer for 10 min"):
    e = l.entender(frase, A)
    assert e["tipo"] == "timer" and e["quando"] == A + dt.timedelta(minutes=10), (frase, e)
assert l.entender("set a timer for 2 hours", A)["quando"] == A + dt.timedelta(hours=2)
e = l.entender("Remind me at 5 pm to call Mom", A)
assert e == {"tipo": "lembrete", "quando": dt.datetime(2026, 11, 13, 17, 0), "texto": "call Mom"}, e
assert l.entender("me lembra de tomar água daqui a 30 minutos", A)["quando"] == A + dt.timedelta(minutes=30)
e = l.entender("remind me in 30 minutes to stretch", A)
assert e["quando"] == A + dt.timedelta(minutes=30) and e["texto"] == "stretch", e
assert l.entender("põe um timer", A) == {"tipo": "falta_hora"}
print("TUDO OK.")
