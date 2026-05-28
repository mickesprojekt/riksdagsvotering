#!/usr/bin/env python3
"""
fetch_betankanden.py  —  Lager 1

Hämtar metadata för alla betänkanden (titel, dok_id, utskott, datum)
för ett riksmöte och sparar som data/betankanden.json.

Ingen röstdata hämtas här — bara betänkandenas skelett.
Röstdata på partinivå hämtas av Lager 2 (fetch_partirost.py).

Körs som:
    python fetch_betankanden.py
    python fetch_betankanden.py 2024/25
"""

import json
import sys
import time
from pathlib import Path

import requests

# ── Konfiguration ─────────────────────────────────────────────────────────────

RIKSMOTE    = sys.argv[1] if len(sys.argv) > 1 else "2025/26"
BASE_URL    = "https://data.riksdagen.se/dokumentlista/"
PAGE_SIZE   = 100     # Betänkanden per sida
DELAY_S     = 0.5     # Paus mellan sidanrop
OUTPUT_PATH = Path("data") / "betankanden.json"


# ── URL-byggare ───────────────────────────────────────────────────────────────

def page_url(page: int) -> str:
    # Samma fix som tidigare: bygg URL som ren sträng så att snedstrecket
    # i "2025/26" inte URL-enkodas till %2F av requests.
    return (
        f"{BASE_URL}?doktyp=bet&rm={RIKSMOTE}"
        f"&utformat=json&sz={PAGE_SIZE}&p={page}"
    )


# ── Hämtning ─────────────────────────────────────────────────────────────────

def fetch_all(session: requests.Session) -> list[dict]:
    """
    Paginerar dokumentlistan tills alla betänkanden är hämtade.
    Dokumentlistan stöder p-paginering korrekt (till skillnad från voteringlistan).
    """
    all_bets: list[dict] = []
    page = 1

    while True:
        resp = session.get(page_url(page), timeout=30)
        resp.raise_for_status()

        lista = resp.json().get("dokumentlista", {})
        total = lista.get("@traffar", "?")
        docs  = lista.get("dokument", [])

        # API-egenhet: enstaka träff returneras som dict, inte lista
        if isinstance(docs, dict):
            docs = [docs]
        if not docs:
            break

        for doc in docs:
            all_bets.append({
                "dok_id":     doc.get("dok_id", "").upper(),
                "rm":         doc.get("rm", ""),
                "beteckning": doc.get("beteckning", ""),
                "organ":      doc.get("organ", ""),       # Utskottskod, t.ex. "AU", "JuU"
                "datum":      doc.get("datum", ""),
                "publicerad": doc.get("publicerad", ""),
                "titel":      doc.get("titel", ""),
                "status":     doc.get("status", ""),      # T.ex. "Kammaren har beslutat"
            })

        print(f"  {len(all_bets)}/{total} betänkanden hämtade", end="\r", flush=True)

        if len(docs) < PAGE_SIZE:
            break   # Färre än en full sida → sista sidan

        page += 1
        time.sleep(DELAY_S)

    print()
    return all_bets


# ── Startpunkt ────────────────────────────────────────────────────────────────

def main() -> None:
    Path("data").mkdir(exist_ok=True)

    print(f"Hämtar betänkande-metadata för riksmöte {RIKSMOTE}...")
    print(f"URL exempel (sida 1): {page_url(1)}\n")

    session = requests.Session()
    session.headers["User-Agent"] = "riksdag-analys/0.1 (pedagogiskt projekt)"

    betankanden = fetch_all(session)

    if not betankanden:
        print("Inga betänkanden hittades.")
        print("Kontrollera riksmötesformatet, t.ex. '2025/26'.")
        sys.exit(1)

    # Sortera kronologiskt
    betankanden.sort(key=lambda b: b["datum"])

    OUTPUT_PATH.write_text(
        json.dumps(betankanden, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # ── Förhandsvisning ───────────────────────────────────────────────────────
    print(f"\nSparade {len(betankanden)} betänkanden → {OUTPUT_PATH}\n")
    print(f"{'Beteckning':<10}  {'Organ':<6}  {'Datum':<12}  Titel")
    print("─" * 85)
    for b in betankanden[:10]:
        titel = b["titel"]
        if len(titel) > 52:
            titel = titel[:51] + "…"
        print(f"{b['beteckning']:<10}  {b['organ']:<6}  {b['datum']:<12}  {titel}")

    if len(betankanden) > 10:
        print(f"  … och {len(betankanden) - 10} till.\n")

    # ── Utskottsfördelning ────────────────────────────────────────────────────
    organ_count: dict[str, int] = {}
    for b in betankanden:
        organ_count[b["organ"]] = organ_count.get(b["organ"], 0) + 1

    print("Betänkanden per utskott:")
    for organ, count in sorted(organ_count.items(), key=lambda x: -x[1]):
        print(f"  {organ:<6}  {count}")


if __name__ == "__main__":
    main()
