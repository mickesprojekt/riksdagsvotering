#!/usr/bin/env python3
"""
analyze_partirost.py

Läser data/partirost/ och beräknar:

  1. Verifiering — antal röster per votering, varna om något verkar saknas
  2. Partilinje per votering — majoritetsröst (Ja/Nej), med råa siffror bredvid
  3. Överensstämmelsematris — för varje partipar: hur ofta de röstade lika

Inga slutsatser eller tolkningar genereras — bara räknade fakta.

Output:
    data/analysis.json          — fullständig strukturerad data
    data/analysis_matris.csv    — matrisen som CSV

Körs som:
    python analyze_partirost.py
    python analyze_partirost.py 2024/25
"""

import csv
import json
import sys
from datetime import date
from pathlib import Path

# -- Konfiguration -------------------------------------------------------------

RIKSMOTE = sys.argv[1] if len(sys.argv) > 1 else "2025/26"

PARTIROST_DIR = Path("data") / "partirost"
BETANKANDEN   = Path("data") / "betankanden.json"
OUTPUT_JSON   = Path("data") / "analysis.json"
OUTPUT_CSV    = Path("data") / "analysis_matris.csv"

# Varna om en votering har färre huvud/sakfrågan-röster än detta
# (förväntat: ~349 ledamöter; varna om mer än hälften saknas)
WARN_ROSTER_UNDER = 150

EXPECTED_VOTERINGAR = 527


# -- Läs indata ----------------------------------------------------------------

def load_voteringar() -> list[dict]:
    voteringar = []
    for path in sorted(PARTIROST_DIR.glob("*.json")):
        for v in json.loads(path.read_text(encoding="utf-8")):
            voteringar.append(v)
    return voteringar


def load_titlar() -> dict[str, str]:
    if not BETANKANDEN.exists():
        return {}
    return {
        b["dok_id"]: b.get("titel", "")
        for b in json.loads(BETANKANDEN.read_text(encoding="utf-8"))
    }


# -- Partilinje ----------------------------------------------------------------

def bestam_linje(roster: dict[str, int]) -> str:
    """
    Partiets linje = majoritetsröst bland Ja/Nej.
    Avstår och Frånvarande räknas inte in i majoriteten.

    "Ja"    — fler Ja än Nej
    "Nej"   — fler Nej än Ja
    "Delad" — lika många Ja och Nej (båda > 0)
    "Ingen" — inga Ja eller Nej (alla avstår/frånvarande)
    """
    ja  = roster.get("Ja",  0)
    nej = roster.get("Nej", 0)
    if ja == 0 and nej == 0:
        return "Ingen"
    if ja > nej:
        return "Ja"
    if nej > ja:
        return "Nej"
    return "Delad"


# -- Överensstämmelse ----------------------------------------------------------

def bygg_matris(voteringar: list[dict], partier: list[str]) -> dict[str, dict]:
    """
    Beräknar parvisa överensstämmelser.

    För varje par (A, B):
      voteringar_totalt              — alla voteringar i datasetet
      voteringar_med_linje_for_bada  — voteringar där BÅDA har linje Ja eller Nej
      voteringar_lika                — av dessa, hur många de röstade lika
      andel_lika                     — lika / med_linje (null om nämnaren är 0)

    Voteringar där ett parti har linje "Delad" eller "Ingen" exkluderas från
    täljare och nämnare men syns ändå via voteringar_totalt.
    """
    matris: dict[str, dict] = {}

    for i, pa in enumerate(partier):
        for pb in partier[i + 1:]:
            lika = 0
            med_linje = 0

            for v in voteringar:
                la = v["partilinjer"].get(pa, {}).get("linje")
                lb = v["partilinjer"].get(pb, {}).get("linje")
                if la in ("Ja", "Nej") and lb in ("Ja", "Nej"):
                    med_linje += 1
                    if la == lb:
                        lika += 1

            andel = round(lika / med_linje, 4) if med_linje > 0 else None

            matris[f"{pa}-{pb}"] = {
                "parti_a":                       pa,
                "parti_b":                       pb,
                "voteringar_totalt":             len(voteringar),
                "voteringar_med_linje_for_bada": med_linje,
                "voteringar_lika":               lika,
                "andel_lika":                    andel,
            }

    return matris


# -- Terminalutskrift ----------------------------------------------------------

def _skriv_tabell(matris: dict, partier: list[str], cell_fn) -> None:
    """Generisk matristabell. cell_fn(rad: dict, col: int) -> str."""
    COL = 7
    print(" " * 6 + "".join(f"{p:>{COL}}" for p in partier))
    print("-" * (6 + COL * len(partier)))
    for pa in partier:
        rad = f"{pa:<6}"
        for pb in partier:
            if pa == pb:
                rad += f"{'—':>{COL}}"
            else:
                key = f"{pa}-{pb}" if f"{pa}-{pb}" in matris else f"{pb}-{pa}"
                rad += cell_fn(matris[key], COL)
        print(rad)


def skriv_andel_tabell(matris: dict, partier: list[str]) -> None:
    def cell(r, c):
        a = r["andel_lika"]
        return f"{'?':>{c}}" if a is None else f"{a:>{c}.0%}"
    _skriv_tabell(matris, partier, cell)


def skriv_n_tabell(matris: dict, partier: list[str]) -> None:
    """Visar N = voteringar_med_linje_for_bada per partipar."""
    def cell(r, c):
        return f"{r['voteringar_med_linje_for_bada']:>{c}}"
    _skriv_tabell(matris, partier, cell)


# -- Startpunkt ----------------------------------------------------------------

def main() -> None:
    print(f"=== Partiröst-analys | riksmöte {RIKSMOTE} ===\n")

    voteringar_raw = load_voteringar()
    titlar         = load_titlar()

    if not voteringar_raw:
        print(f"Inga voteringar hittades i {PARTIROST_DIR}/")
        print("Kör fetch_partirost.py (Lager 2) först.")
        raise SystemExit(1)

    # -- Verifiering -----------------------------------------------------------
    print("-- Verifiering ------------------------------------------------------")
    varningar: list[str] = []

    n = len(voteringar_raw)
    if n != EXPECTED_VOTERINGAR:
        msg = f"Hittade {n} voteringar, förväntat {EXPECTED_VOTERINGAR}."
        varningar.append(msg)
        print(f"VARNING: {msg}")

    # Sortera kronologiskt för tabellen
    voteringar_raw.sort(key=lambda v: (v["datum"], v["punkt"].zfill(4)))

    print(
        f"\n{'votering_id':<38}  {'datum':<12}  {'bet.':<10}  "
        f"{'pkt':>3}  {'hs-röster':>9}"
    )
    print("-" * 80)

    for v in voteringar_raw:
        n_hs = v["huvud_sakfragan"]["antal_ledamoter"]
        varning = ""
        if n_hs < WARN_ROSTER_UNDER:
            msg = (
                f"{v['votering_id']}: {n_hs} huvud/sakfrågan-röster "
                f"(< {WARN_ROSTER_UNDER}) — möjlig sz-trunkering."
            )
            varningar.append(msg)
            varning = "  << VARNING"
        print(
            f"{v['votering_id']:<38}  {v['datum']:<12}  {v['beteckning']:<10}  "
            f"{v['punkt']:>3}  {n_hs:>9}{varning}"
        )

    print()
    if varningar:
        print(f"{len(varningar)} varning(ar) — se ovan.\n")
    else:
        print("Verifiering OK — inga varningar.\n")

    # -- Partier ---------------------------------------------------------------
    alla_partier: set[str] = set()
    for v in voteringar_raw:
        alla_partier.update(v["huvud_sakfragan"]["parti_roster"].keys())
    alla_partier.discard("-")   # Okänt parti — utesluts ur matrisen
    partier = sorted(alla_partier)

    print(f"Partier i datan: {', '.join(partier)}\n")

    # -- Bygg votering-poster med partilinjer ----------------------------------
    voteringar_ut: list[dict] = []

    for v in voteringar_raw:
        hs          = v["huvud_sakfragan"]
        partilinjer = {
            parti: {
                "linje":  bestam_linje(roster),
                "roster": roster,   # Råa siffror — linje är alltid spårbar
            }
            for parti, roster in hs["parti_roster"].items()
        }

        voteringar_ut.append({
            "votering_id": v["votering_id"],
            "dok_id":      v["dok_id"],
            "beteckning":  v["beteckning"],
            "organ":       v["organ"],
            "punkt":       v["punkt"],
            "datum":       v["datum"],
            "titel":       titlar.get(v["dok_id"], ""),
            "totalt":      hs["totalt"],
            "partilinjer": partilinjer,
        })

    # -- Matris ----------------------------------------------------------------
    matris = bygg_matris(voteringar_ut, partier)

    print(
        "-- Andel lika (överensstämmelse, huvud/sakfrågan) ----------------------"
    )
    print(
        "   Andel voteringar med samma linje, av de där BÅDA hade tydlig Ja/Nej-linje\n"
    )
    skriv_andel_tabell(matris, partier)
    print()

    print(
        "-- N — jämförelseunderlag per partipar ---------------------------------"
    )
    print(
        "   Antal voteringar som andelen ovan bygger på (lågt N -> andelen är osäkrare)\n"
    )
    skriv_n_tabell(matris, partier)
    print()

    # -- Skriv JSON ------------------------------------------------------------
    output = {
        "meta": {
            "riksmote":               RIKSMOTE,
            "genererad":              str(date.today()),
            "antal_voteringar":       len(voteringar_ut),
            "partier":                partier,
            "metod_partilinje": (
                "Majoritetsröst bland Ja/Nej per parti per votering. "
                "Avstår och Frånvarande räknas inte in i majoriteten. "
                "Lika antal Ja och Nej (båda > 0) -> 'Delad'. "
                "Inga Ja eller Nej -> 'Ingen'."
            ),
            "metod_overensstammelse": (
                "Andel voteringar där båda partier hade linje Ja eller Nej och röstade lika. "
                "Voteringar med linje 'Delad' eller 'Ingen' exkluderas ur täljare och nämnare. "
                "voteringar_totalt inkluderas alltid som referens."
            ),
        },
        "verifiering": {
            "voteringar_hittade":    len(voteringar_raw),
            "voteringar_forvantat":  EXPECTED_VOTERINGAR,
            "varningar":             varningar,
        },
        "voteringar":               voteringar_ut,
        "overensstammelse_matris":  matris,
    }

    OUTPUT_JSON.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Sparade {OUTPUT_JSON}")

    # -- Skriv CSV -------------------------------------------------------------
    fieldnames = [
        "parti_a", "parti_b",
        "voteringar_totalt",
        "voteringar_med_linje_for_bada",
        "voteringar_lika",
        "andel_lika",
    ]
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rad in matris.values():
            writer.writerow(rad)

    print(f"Sparade {OUTPUT_CSV}")
    print(
        f"\nKlart. {len(voteringar_ut)} voteringar, "
        f"{len(partier)} partier, {len(matris)} partipar analyserade."
    )


if __name__ == "__main__":
    main()
