#!/usr/bin/env python3
"""
fetch_dokument.py  --  Lager 3

Hamtar detaljerad betankandedata per dok_id fran Riksdagens API och sparar
ratt i data/dokument/.

Endpoint: https://data.riksdagen.se/dokument/<dok_id>.json

Vad som hamtas per betankande:
  - Beslutssammanfattning (kort text fran utskottet)
  - "Beslut i korthet" (notis, HTML) for webbsidan
  - Alla forslagspunkter med beslutstyp, vilka motioner de gallde,
    och vad voteringar stalldes mot (t.ex. "utskottets forslag mot
    reservation 3 (V)")
  - Reservationer med partibeteckning per punkt

Designprinciper:
  - Aterupptagningsbart: hoppar over dok_id som redan finns pa disk
  - Sparar ratt svar utan bearbetning -- ingen HTML-stadning har
  - Bygger data/dokument_index.json med komprimerade nyckelfalt per
    betankande (beslutsdatum, antal punkter/acklamationer/voteringar)
    sa att webbsidan slipper lasa alla 470 filer for statusraden
  - Varnar direkt om forvantade falt saknas i ett svar

Kors som:
    python fetch_dokument.py
    python fetch_dokument.py --force   # hamtar om aven befintliga filer
"""

import json
import sys
import time
from pathlib import Path

import requests

# -- Konfiguration -------------------------------------------------------------

FORCE = "--force" in sys.argv

DOK_BASE   = "https://data.riksdagen.se/dokument"
PAUS       = 0.5   # sekunder mellan anrop

INPUT_PATH = Path("data") / "betankanden.json"
OUTPUT_DIR = Path("data") / "dokument"
INDEX_PATH = Path("data") / "dokument_index.json"


# -- Hjalp: normalisera API-struktur ------------------------------------------

def to_list(raw) -> list:
    """Hantera att ett API-falt kan vara dict, lista eller null."""
    if raw is None:
        return []
    if isinstance(raw, dict):
        return [raw]
    return raw


def uppgift_map(uppgifter: list) -> dict:
    """Returnerar {kod: text} for alla uppgifter."""
    return {u.get("kod", ""): (u.get("text") or "") for u in uppgifter}


# -- Berakning av indexpost ----------------------------------------------------

def berakna_index(dok_id: str, raw: dict, verbose: bool = True) -> dict:
    """
    Extraherar nyckelfalt ur ett ratt API-svar.
    verbose=True: skriver ut varningar (anvands vid nedladdning).
    verbose=False: tyst (anvands vid aterstart da filen redan finns).
    """

    def varna(msg: str) -> None:
        if verbose:
            print(f"    VARNING [{dok_id}]: {msg}")

    dokst = raw.get("dokumentstatus")
    if not dokst:
        varna("saknar 'dokumentstatus' -- API-strukturen har andrats?")
        return {"dok_id": dok_id, "fel": "saknar dokumentstatus"}

    # -- Uppgifter (beslutsdatum, sammanfattning m.m.) -------------------------
    uppg_raw = (dokst.get("dokuppgift") or {}).get("uppgift")
    if uppg_raw is None:
        varna("saknar 'dokuppgift.uppgift'")
    uppg = uppgift_map(to_list(uppg_raw))

    beslutsdatum = (uppg.get("beslutdatumtid") or "")[:10] or None
    if not beslutsdatum:
        varna("saknar 'beslutdatumtid' -- beslutsdatum okant")

    sammanfattning = uppg.get("beslutssammanfattningusk") or ""
    if not sammanfattning:
        varna("saknar 'beslutssammanfattningusk' -- ingen kort sammanfattning")

    # -- Forslagspunkter -------------------------------------------------------
    ufs_raw = (dokst.get("dokutskottsforslag") or {}).get("utskottsforslag")
    if ufs_raw is None:
        varna("saknar 'dokutskottsforslag.utskottsforslag'")
    punkter = to_list(ufs_raw)

    antal_punkter      = len(punkter)
    antal_acklamationer = 0
    antal_voteringar   = 0

    for p in punkter:
        vid = (p.get("votering_id") or "").strip()
        bt  = (p.get("beslutstyp") or "").lower()

        if vid:
            antal_voteringar += 1
        elif bt == "acklamation":
            antal_acklamationer += 1
        else:
            # Okand beslutstyp utan votering_id -- rakhna som acklamation
            if bt and bt != "acklamation":
                varna(f"okand beslutstyp '{bt}' pa punkt {p.get('punkt')} (ingen votering_id)")
            antal_acklamationer += 1

    if antal_acklamationer + antal_voteringar != antal_punkter:
        varna(
            f"punkt-summan stammar inte: "
            f"{antal_acklamationer}a + {antal_voteringar}v != {antal_punkter}p"
        )

    return {
        "dok_id":                dok_id,
        "beslutsdatum":          beslutsdatum,
        "antal_punkter":         antal_punkter,
        "antal_acklamationer":   antal_acklamationer,
        "antal_voteringar":      antal_voteringar,
        "beslutssammanfattning": sammanfattning,
    }


# -- Startpunkt ----------------------------------------------------------------

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    betankanden = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    totalt = len(betankanden)

    print(f"=== Lager 3: dokument-detaljer | {totalt} betankanden ===")
    print(f"    Output:  {OUTPUT_DIR}/")
    print(f"    Index:   {INDEX_PATH}")
    print(f"    Paus:    {PAUS} s mellan anrop")
    print(f"    Force:   {'ja' if FORCE else 'nej (hoppar over befintliga)'}")
    print()

    session = requests.Session()
    session.headers["User-Agent"] = "riksdag-analys/0.1 (pedagogiskt projekt)"

    index    = []
    hamtade  = 0
    hoppade  = 0
    fel      = 0

    for i, bet in enumerate(betankanden, 1):
        dok_id   = bet["dok_id"]
        out_path = OUTPUT_DIR / f"{dok_id}.json"

        # -- Hoppa over om filen redan finns -----------------------------------
        if not FORCE and out_path.exists():
            raw = json.loads(out_path.read_text(encoding="utf-8"))
            index.append(berakna_index(dok_id, raw, verbose=False))
            hoppade += 1
            continue

        # -- Hamta ------------------------------------------------------------
        # API:et kraver gemena svenska bokstaver i dok_id (t.ex. FoU, inte FOU).
        # betankanden.json lagrar dem med versaler (U+00D6 osv) -- normalisera
        # till gemener innan URL:en byggs.
        url_id = dok_id.replace("Ö", "ö").replace("Å", "å").replace("Ä", "ä")
        url = f"{DOK_BASE}/{url_id}.json"
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            raw = resp.json()
        except Exception as exc:
            print(f"  FEL [{i:>3}/{totalt}] {dok_id}: {exc}")
            fel += 1
            time.sleep(PAUS)
            continue

        out_path.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        idx = berakna_index(dok_id, raw, verbose=True)
        index.append(idx)
        hamtade += 1

        s = idx
        status = (
            f"{s.get('beslutsdatum') or '?':10}  "
            f"{s.get('antal_punkter',0):2}p  "
            f"{s.get('antal_acklamationer',0):2}a  "
            f"{s.get('antal_voteringar',0):2}v"
        )
        print(f"  [{i:>3}/{totalt}] {dok_id:<16}  {status}")

        time.sleep(PAUS)

    # -- Skriv index -----------------------------------------------------------
    # Sortera pa beslutsdatum (None sist) for konsekvent ordning
    index.sort(key=lambda r: (r.get("beslutsdatum") or "9999"))

    INDEX_PATH.write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print("-" * 60)
    print(f"  Hamtade:   {hamtade}")
    print(f"  Hoppade:   {hoppade}  (fanns redan pa disk)")
    print(f"  Fel:       {fel}")
    print(f"  Index:     {INDEX_PATH}  ({len(index)} poster)")
    print("-" * 60)


if __name__ == "__main__":
    main()
