"""
Raccolta quote tennis (Challenger + ITF) da MoviOdds.
Gira ogni 15 minuti su GitHub Actions.

Salva in data/:
  quote.csv     -> una riga ogni volta che la quota "To Win Match" di una partita
                   pre-match cambia (o la prima volta che la vediamo = apertura).
                   L'ultima riga di ogni partita prima del live = chiusura.
  punteggi.csv  -> ultimo punteggio live visto (controllo incrociato sul vincitore).
  stato.json    -> memoria interna (ultima quota/punteggio salvati per partita).
"""

import csv
import json
import os
import re
import urllib.request
from datetime import datetime, timezone

URL = "https://moviodds.com/odds?sport=tennis&site=com"
DATA = "data"
F_QUOTE = os.path.join(DATA, "quote.csv")
F_PUNTEGGI = os.path.join(DATA, "punteggi.csv")
F_STATO = os.path.join(DATA, "stato.json")

MERCATO_VINCENTE = "83"  # "To Win Match"

RE_TORNEO = re.compile(r"^(Challenger|M\d+|W\d+)\s")
RE_DOPPIO = re.compile(r"\s(MD|WD|XD)$")

COL_QUOTE = ["letto_utc", "id", "torneo", "livello", "doppio", "home", "away",
             "inizio_utc", "quota_home", "quota_away", "quota_cambiata_utc"]
COL_PUNTEGGI = ["letto_utc", "id", "torneo", "home", "away", "punteggio"]


def livello(torneo):
    if torneo.startswith("Challenger"):
        return "Challenger"
    if torneo.startswith("M"):
        return "ITF-M"
    return "ITF-W"


def scarica():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def aggiungi(file, colonne, righe):
    if not righe:
        return
    nuovo = not os.path.exists(file)
    with open(file, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=colonne)
        if nuovo:
            w.writeheader()
        w.writerows(righe)


def main():
    os.makedirs(DATA, exist_ok=True)
    stato = {}
    if os.path.exists(F_STATO):
        with open(F_STATO, encoding="utf-8") as f:
            stato = json.load(f)

    adesso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    dati = scarica()

    righe_quote, righe_punteggi = [], []
    for m in dati.get("matches", []):
        torneo = (m.get("league") or "").strip()
        if not RE_TORNEO.match(torneo):
            continue
        mid = str(m.get("id"))
        s = stato.setdefault(mid, {})

        if m.get("in_play"):
            punteggio = m.get("score")
            if punteggio and punteggio != s.get("punteggio"):
                s["punteggio"] = punteggio
                righe_punteggi.append({
                    "letto_utc": adesso, "id": mid, "torneo": torneo,
                    "home": m.get("home"), "away": m.get("away"),
                    "punteggio": json.dumps(punteggio, ensure_ascii=False)
                    if not isinstance(punteggio, str) else punteggio,
                })
            continue

        quote = [q for q in m.get("quotes", [])
                 if str(q.get("group_id")) == MERCATO_VINCENTE]
        q_home = next((q for q in quote if q.get("label") == m.get("home")), None)
        q_away = next((q for q in quote if q.get("label") == m.get("away")), None)
        if not q_home or not q_away:
            continue

        qh = round(float(q_home["odds_dec"]), 3)
        qa = round(float(q_away["odds_dec"]), 3)
        if s.get("quota") == [qh, qa]:
            continue  # nessun cambio: non riscriviamo
        s["quota"] = [qh, qa]
        righe_quote.append({
            "letto_utc": adesso, "id": mid, "torneo": torneo,
            "livello": livello(torneo),
            "doppio": 1 if RE_DOPPIO.search(torneo) else 0,
            "home": m.get("home"), "away": m.get("away"),
            "inizio_utc": m.get("kickoff_utc"),
            "quota_home": qh, "quota_away": qa,
            "quota_cambiata_utc": max(q_home.get("ts", ""), q_away.get("ts", "")),
        })

    aggiungi(F_QUOTE, COL_QUOTE, righe_quote)
    aggiungi(F_PUNTEGGI, COL_PUNTEGGI, righe_punteggi)
    with open(F_STATO, "w", encoding="utf-8") as f:
        json.dump(stato, f, ensure_ascii=False)

    print(f"{adesso}: {len(righe_quote)} quote nuove/cambiate, "
          f"{len(righe_punteggi)} punteggi live aggiornati")


if __name__ == "__main__":
    main()
