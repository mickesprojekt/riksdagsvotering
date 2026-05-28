#!/usr/bin/env python3
"""
fetch_votes.py

Hämtar alla voteringsrader för ett riksmöte via betänkande-strategin:

  Fas 1 — Hämtar lista på alla betänkanden (doktyp=bet) för riksmötet.
           Dokumentlistan har fungerande paginering via @nasta_sida.

  Fas 2 — För varje betänkandes dok_id: hämtar dess voteringsrader och
           sparar direkt till disk. Hoppar över dok_ids som redan är klara.

  Fas 3 — Bygger ett index och skriver ut sammanfattning.

Återupptagningsbar: avbryt och kör igen — klara betänkanden hoppas över.

Körs som:
    python fetch_votes.py
    python fetch_votes.py 2024/25
"""

import json
import sys
import time
from pathlib import Path

import requests

# ── Konfiguration ─────────────────────────────────────────────────────────────

RIKSMOTE      = sys.argv[1] if len(sys.argv) > 1 else "2025/26"
RIKSMOTE_SAFE = RIKSMOTE.replace("/", "_")   # "2025_26" — säkert i filnamn

BET_BASE  = "https://data.riksdagen.se/dokumentlista/"
VOTE_BASE = "https://data.riksdagen.se/voteringlista/"

BET_SZ   = 100     # Betänkanden per sida (dokumentlistan paginerar korrekt med p=N)
VOTE_SZ  = 10000   # Rader per betänkande-anrop. Inga bevis att p fungerar här,
                   # men dokumentlistan klarar p — voteringlistan kräver stor sz.
DELAY_S  = 0.5     # Sekunder mellan anrop — respektfullt mot Riksdagens servrar

# Säkerhetsgränser: varna om unikt voteringsantal verkar orimligt
MIN_VOTERINGAR = 50
MAX_VOTERINGAR = 5000

DATA_DIR   = Path("data") / "voteringar"
STATE_PATH = Path("data") / f"state_{RIKSMOTE_SAFE}.json"
INDEX_PATH = Path("data") / "voteringar_index.json"


# ── URL-byggare ───────────────────────────────────────────────────────────────
#
# VIKTIG LÄXA FRÅN FÖREGÅENDE VERSION:
#   requests.get(url, params={"rm": "2025/26"}) → skickar rm=2025%2F26 → API ignorerar filtret
#   Lösning: bygg hela URL:en som en f-sträng — requests rör inte värden som
#   redan finns i strängen. Gäller ALLA anrop i det här skriptet.

def bet_url(page: int) -> str:
    """URL för en sida ur betänkande-listan."""
    return (
        f"{BET_BASE}?doktyp=bet&rm={RIKSMOTE}"
        f"&utformat=json&sz={BET_SZ}&p={page}"
    )


def vote_url(dok_id: str) -> str:
    """URL för alla voteringsrader kopplade till ett specifikt betänkande."""
    return f"{VOTE_BASE}?dok_id={dok_id}&utformat=json&sz={VOTE_SZ}"


# ── Normalisering ─────────────────────────────────────────────────────────────

def to_list(raw) -> list[dict]:
    """
    Hanterar API-egenheten: "votering" kan vara lista, enstaka dict eller null.
    Returnerar alltid list[dict].
    """
    if raw is None:
        return []
    if isinstance(raw, dict):
        return [raw]
    return raw


# ── Checkpoint ────────────────────────────────────────────────────────────────

def load_state() -> dict:
    """
    Läser checkpointen, eller returnerar tomt starttillstånd.

    Robust mot gamla format: den föregående versionen sparade
    {"last_page": ..., "total_rows": ...} utan "completed_dok_ids".
    Med .get(..., []) kraschar vi inte — vi börjar bara om från noll,
    vilket är korrekt beteende när formatet har bytt.
    """
    if STATE_PATH.exists():
        saved = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return {
            "rm":                 RIKSMOTE,
            "completed_dok_ids":  saved.get("completed_dok_ids", []),
        }
    return {"rm": RIKSMOTE, "completed_dok_ids": []}


def save_state(state: dict) -> None:
    """Skriver checkpointen till disk efter varje lyckat betänkande-anrop."""
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── Fas 1: Betänkande-lista ───────────────────────────────────────────────────

def fetch_betankanden(session: requests.Session) -> list[dict]:
    """
    Hämtar alla betänkanden för riksmötet via dokumentlistan.

    Dokumentlistan har fungerande paginering (till skillnad från voteringlistan).
    Vi räknar sidorna med p=1, 2, 3, ... och slutar när vi får färre
    dokument än BET_SZ — precis som man förväntar sig av en API med sidstorlek.
    """
    all_bets: list[dict] = []
    page = 1

    while True:
        resp = session.get(bet_url(page), timeout=30)
        resp.raise_for_status()
        data  = resp.json()
        lista = data.get("dokumentlista", {})
        total = lista.get("@traffar", "?")
        docs  = to_list(lista.get("dokument"))

        if not docs:
            break

        for doc in docs:
            all_bets.append({
                "dok_id":     doc.get("dok_id", "").upper(),
                "beteckning": doc.get("beteckning", ""),
                "organ":      doc.get("organ", ""),
                "datum":      doc.get("datum", ""),
                "titel":      doc.get("titel", ""),
            })

        print(f"  Betänkanden hämtade: {len(all_bets)}/{total}", end="\r", flush=True)

        if len(docs) < BET_SZ:
            break   # Sista sidan
        page += 1
        time.sleep(DELAY_S)

    print()
    return all_bets


# ── Fas 2: Voteringar per betänkande ─────────────────────────────────────────

def fetch_and_group(session: requests.Session, dok_id: str) -> dict[str, list[dict]]:
    """
    Hämtar alla voteringsrader för ett betänkande och grupperar per votering_id.
    Deduplicerar på (votering_id, intressent_id) — primärnyckeln i datan.

    Varnar om vi fick exakt VOTE_SZ rader tillbaka: det tyder på att svaret
    kan ha trunkerat — betänkandet kanske har fler rader än vi bad om.
    """
    resp = session.get(vote_url(dok_id), timeout=60)
    resp.raise_for_status()
    rows = to_list(resp.json().get("voteringlista", {}).get("votering"))

    if len(rows) == VOTE_SZ:
        print(
            f"\n  VARNING: {dok_id} gav exakt {VOTE_SZ} rader — "
            f"svaret kan vara trunkerat. Överväg att öka VOTE_SZ."
        )

    # Deduplicera och gruppera i ett svep
    by_vote: dict[str, list[dict]] = {}
    seen: set[tuple] = set()
    for row in rows:
        key = (row.get("votering_id"), row.get("intressent_id"))
        if key in seen:
            continue
        seen.add(key)
        vid = row.get("votering_id") or "OKÄNT_ID"
        by_vote.setdefault(vid, []).append(row)

    return by_vote


def save_votes(by_vote: dict[str, list[dict]]) -> set[str]:
    """
    Skriver en JSON-fil per votering_id till DATA_DIR.

    Skriver INTE över befintliga filer — det gör att en avbruten körning
    kan återupptas utan att förlora redan sparad data.
    Returnerar mängden votering_ids som nu finns (nya + gamla).
    """
    written: set[str] = set()
    for vid, rows in by_vote.items():
        path = DATA_DIR / f"{vid}.json"
        if not path.exists():
            path.write_text(
                json.dumps(rows, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        written.add(vid)
    return written


# ── Fas 3: Index och sammanfattning ───────────────────────────────────────────

def build_index_and_count() -> tuple[int, int, int]:
    """
    Läser alla per-votering JSON-filer och:
      - Bygger ett index (voteringar_index.json)
      - Räknar totalt antal rader
      - Räknar antal huvud/sakfrågan-rader

    BUGGFIX jämfört med föregående version:
      Tidigare räknades "huvud/sakfrågan" från rå JSONL utan deduplicering,
      medan "totalt" räknades från deduplikerade filer. De var inte jämförbara
      och gav motstridiga siffror (t.ex. huvud/sakfrågan > totalt).

      Nu räknas BÅDA från exakt samma källa — de befintliga JSON-filerna —
      så siffrorna alltid är konsistenta och jämförbara.
    """
    index:           list[dict] = []
    total_rows:      int = 0
    huvud_sakfragan: int = 0

    for path in sorted(DATA_DIR.glob("*.json")):
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not rows:
            continue

        # Båda räknarna läser från samma variabel `rows` — ingen risk för avvikelse
        total_rows      += len(rows)
        huvud_sakfragan += sum(
            1 for r in rows
            if r.get("votering") == "huvud" and r.get("avser") == "sakfrågan"
        )

        first = rows[0]
        index.append({
            "votering_id":  path.stem,
            "rm":           first.get("rm"),
            "beteckning":   first.get("beteckning"),
            "punkt":        first.get("punkt"),
            "dok_id":       first.get("dok_id"),
            "datum":        (first.get("systemdatum") or "")[:10],
            "antal_roster": len(rows),
        })

    index.sort(key=lambda x: x["datum"])
    INDEX_PATH.write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return len(index), total_rows, huvud_sakfragan


# ── Startpunkt ────────────────────────────────────────────────────────────────

def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"=== Riksdag-hämtare | riksmöte {RIKSMOTE} | betänkande-strategi ===")
    print(f"    Votering-filer: {DATA_DIR}/")
    print(f"    Checkpoint:     {STATE_PATH}")
    print(f"    Paus/anrop:     {DELAY_S} s  |  Max rader/betänkande: {VOTE_SZ}")
    print()

    session = requests.Session()
    session.headers["User-Agent"] = "riksdag-analys/0.1 (pedagogiskt projekt)"

    # ── Fas 1 ──────────────────────────────────────────────────────────────────
    print("── Fas 1: Hämtar betänkande-lista ───────────────────────────────────")
    betankanden = fetch_betankanden(session)

    if not betankanden:
        print(f"Inga betänkanden hittades för riksmöte {RIKSMOTE}.")
        print("Kontrollera att formatet är korrekt, t.ex. '2025/26'.")
        sys.exit(1)

    print(f"Hittade {len(betankanden)} betänkanden.\n")
    time.sleep(DELAY_S)

    # ── Fas 2 ──────────────────────────────────────────────────────────────────
    print("── Fas 2: Hämtar voteringar per betänkande ──────────────────────────")

    state     = load_state()
    completed = set(state["completed_dok_ids"])

    # Räkna in votering_ids som redan finns på disk — viktigt för korrekt
    # räknare vid återupptagning av en avbruten körning
    seen_vids: set[str] = {p.stem for p in DATA_DIR.glob("*.json")}

    if completed:
        print(
            f"Återupptar: {len(completed)} betänkanden klara, "
            f"{len(seen_vids)} unika voteringar på disk.\n"
        )

    todo = [b for b in betankanden if b["dok_id"] not in completed]

    for i, bet in enumerate(todo, start=1):
        dok_id = bet["dok_id"]

        # Löpande räknare: visar unika voteringar, INTE råa rader
        print(
            f"  [{i:>3}/{len(todo)}]  {dok_id:<14}"
            f"  {len(seen_vids):>4} unika voteringar totalt",
            end="\r", flush=True,
        )

        try:
            by_vote  = fetch_and_group(session, dok_id)
            new_vids = save_votes(by_vote)
            seen_vids.update(new_vids)

            state["completed_dok_ids"].append(dok_id)
            save_state(state)   # Checkpoint sparas efter varje lyckat betänkande

        except requests.exceptions.Timeout:
            print(f"\n  Timeout vid {dok_id} — hoppar över, fortsätter.")
        except requests.exceptions.HTTPError as exc:
            print(f"\n  HTTP-fel vid {dok_id}: {exc} — hoppar över, fortsätter.")
        except requests.exceptions.RequestException as exc:
            print(f"\n  Nätverksfel vid {dok_id}: {exc} — hoppar över, fortsätter.")

        time.sleep(DELAY_S)

    print(f"\n\nFas 2 klar. {len(seen_vids)} unika voteringar hämtade.\n")

    # ── Säkerhetskontroll ─────────────────────────────────────────────────────
    n = len(seen_vids)
    if n < MIN_VOTERINGAR:
        print(
            f"VARNING: Bara {n} unika voteringar — misstänkt få för ett helt riksmöte.\n"
            f"Kontrollera att rm-filtret fungerar och att betänkandena faktiskt\n"
            f"innehåller voteringsdata (nya betänkanden kanske inte har röstats på än)."
        )
    elif n > MAX_VOTERINGAR:
        print(
            f"VARNING: {n} unika voteringar — misstänkt många.\n"
            f"Kan tyda på att filtret hämtade data från flera riksmöten."
        )
    else:
        print(f"Voteringsantalet ({n}) ligger inom förväntat intervall ({MIN_VOTERINGAR}–{MAX_VOTERINGAR}).")
    print()

    # ── Fas 3 ──────────────────────────────────────────────────────────────────
    print("── Fas 3: Bygger index ───────────────────────────────────────────────")
    n_votes, n_rows, huvud_sakfragan = build_index_and_count()

    # Rimlighetskoll: huvud/sakfrågan ska alltid vara <= totalt
    if huvud_sakfragan > n_rows:
        print(
            f"  FEL i räknelogiken: huvud/sakfrågan ({huvud_sakfragan}) > "
            f"totalt ({n_rows}). Undersök datan."
        )

    print(f"\n{'─' * 56}")
    print(f"  Riksmöte:               {RIKSMOTE}")
    print(f"  Betänkanden hämtade:    {len(betankanden)}")
    print(f"  Unika voteringar:       {n_votes}")
    print(f"  Enskilda röster totalt: {n_rows:>8}")
    print(f"  Därav huvud/sakfrågan:  {huvud_sakfragan:>8}  ← analysunderlag")
    print(f"  Votering-filer:         {DATA_DIR}/")
    print(f"  Index:                  {INDEX_PATH}")
    print(f"{'─' * 56}")


if __name__ == "__main__":
    main()
