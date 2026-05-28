#!/usr/bin/env python3
"""
fetch_partirost.py  —  Lager 2  (v3)

Hämtar ALL voteringsdata för ett riksmöte via bulk-ZIP-filen från
data.riksdagen.se och aggregerar partiröster per votering_id.

Varför ZIP i stället för voteringlista-API:et:
  API:et data.riksdagen.se/voteringlista/ har ett hårt tak på 10 000 rader
  oavsett sz-parametern. Med ~349 ledamöter per votering ger det bara de
  senaste ~28 voteringarna. Riksmöte 2025/26 har 535 voteringar — API:et
  returnerar 5 % av dessa. Bulk-ZIP:en innehåller ALLA voteringar utan
  begränsning och kräver bara ett nätverksanrop.

Designprinciper:
  - Metadata (dok_id, punkt, votering_id) hämtas ur filnamnet i ZIP:en
  - Partiröster sparas som råa antal (Ja/Nej/Avstår/Frånvarande per parti),
    aldrig förenklat till en ståndpunkt
  - Huvud/sakfrågan-rader och övriga sparas i separata sektioner per votering
    — inget kastas
  - ZIP:en cachas i data/cache/ — vid omkörning används cachen om --force
    inte anges
  - Varna om totalen avviker kraftigt från förväntat (535 voteringar /
    198 betänkanden per undersökning 2026-05-26)

Output: data/partirost/<dok_id>.json  — en fil per betänkande
        data/partirost_index.json     — index med huvud/sakfrågan-summor per votering

Körs som:
    python fetch_partirost.py
    python fetch_partirost.py 2024/25
    python fetch_partirost.py 2025/26 --force   # tvingar ny nedladdning
"""

import io
import json
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import requests

# ── Konfiguration ─────────────────────────────────────────────────────────────

RIKSMOTE = sys.argv[1] if len(sys.argv) > 1 else "2025/26"
FORCE    = "--force" in sys.argv

_rm_normaliserat = RIKSMOTE.replace("/", "")
ZIP_URL = (
    f"https://data.riksdagen.se/dataset/votering/"
    f"votering-{_rm_normaliserat}.json.zip"
)

# Förväntade totaler för 2025/26 — uppdatera om riksmötet fortsätter
EXPECTED_VOTERINGAR  = 527
EXPECTED_BETANKANDEN = 196

ROST_TYPER = ["Ja", "Nej", "Avstår", "Frånvarande"]

INPUT_PATH = Path("data") / "betankanden.json"
OUTPUT_DIR = Path("data") / "partirost"
INDEX_PATH = Path("data") / "partirost_index.json"
CACHE_DIR  = Path("data") / "cache"
ZIP_CACHE  = CACHE_DIR / f"votering-{_rm_normaliserat}.json.zip"


# ── ZIP-hantering ─────────────────────────────────────────────────────────────

def hamta_zip(session: requests.Session) -> tuple[bytes, bool]:
    """
    Returnerar (zip-bytes, laddades_ner).
    Hämtar från nätet om cachen saknas eller --force anges.
    """
    if not FORCE and ZIP_CACHE.exists():
        print(f"Använder cachad ZIP: {ZIP_CACHE}")
        return ZIP_CACHE.read_bytes(), False

    print(f"Laddar ner ZIP: {ZIP_URL}")
    resp = session.get(ZIP_URL, timeout=120)
    resp.raise_for_status()
    data = resp.content
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ZIP_CACHE.write_bytes(data)
    print(f"Sparade {len(data) / 1024 / 1024:.1f} MB → {ZIP_CACHE}")
    return data, True


# ── Parsning av filnamn ───────────────────────────────────────────────────────

# Exempelfilnamn: HD01CU3-1-BB923736-F0A7-42AF-93D6-4D6E39BBD778.json
_FILNAMN_RE = re.compile(r"^(HD\d+[A-Za-z]+\d+)-(\d+)-([0-9A-Fa-f-]{36})\.json$")


def parse_filnamn(namn: str) -> tuple[str, str, str] | None:
    """Returnerar (dok_id, punkt, votering_id) eller None om formatet inte stämmer."""
    m = _FILNAMN_RE.match(namn)
    if not m:
        return None
    return m.group(1).upper(), m.group(2), m.group(3).upper()


def las_rader(data: bytes) -> list[dict]:
    """
    Läser röstraderna ur en votering-JSON. Hanterar två möjliga format:
      1. Lista direkt: [{...}, ...]
      2. Insvept:      {"voteringlista": {"votering": [{...}, ...]}}
    """
    raw = json.loads(data.decode("utf-8"))
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        # ZIP-filer använder "dokvotering"; API-svar använder "voteringlista"
        vl  = raw.get("dokvotering") or raw.get("voteringlista") or {}
        vot = vl.get("votering")
        if vot is None:
            return []
        if isinstance(vot, dict):
            return [vot]
        return vot
    return []


# ── Aggregering (identisk med v2) ─────────────────────────────────────────────

def aggregera_parti(rows: list[dict]) -> dict[str, dict[str, int]]:
    """
    Räknar Ja/Nej/Avstår/Frånvarande per parti.
    Alla fyra alternativ sparas alltid — även om värdet är 0.
    """
    parti_roster: dict[str, dict[str, int]] = {}
    for r in rows:
        parti = r.get("parti") or "-"
        rost  = r.get("rost")
        if rost not in ROST_TYPER:
            rost = "Frånvarande"
        if parti not in parti_roster:
            parti_roster[parti] = {t: 0 for t in ROST_TYPER}
        parti_roster[parti][rost] += 1
    return parti_roster


def summera(parti_roster: dict[str, dict[str, int]]) -> dict[str, int]:
    return {t: sum(p[t] for p in parti_roster.values()) for t in ROST_TYPER}


def aggregera_votering(
    vid: str,
    dok_id: str,
    punkt: str,
    rows: list[dict],
    organ_lookup: dict[str, str],
) -> dict:
    """
    Aggregerar alla rader för ett votering_id.
    dok_id och punkt hämtas ur filnamnet (tillförlitligare än raddatan).
    beteckning och datum hämtas ur raddatan.
    """
    first      = rows[0] if rows else {}
    # ZIP-filer har "datum"; API-svar hade "systemdatum"
    datum      = (first.get("datum") or first.get("systemdatum") or "")[:10]
    beteckning = first.get("beteckning") or ""
    organ      = organ_lookup.get(dok_id, "")

    huvud_sak = [
        r for r in rows
        if r.get("votering") == "huvud" and r.get("avser") == "sakfrågan"
    ]
    hs_parti_roster = aggregera_parti(huvud_sak)
    hs_totalt       = summera(hs_parti_roster)

    ovriga_rows = [
        r for r in rows
        if not (r.get("votering") == "huvud" and r.get("avser") == "sakfrågan")
    ]
    ovriga_by_typ: dict[tuple, list[dict]] = {}
    for r in ovriga_rows:
        key = (r.get("votering") or "", r.get("avser") or "")
        ovriga_by_typ.setdefault(key, []).append(r)

    ovriga_list = []
    for (vot, avs), grp in sorted(ovriga_by_typ.items()):
        pr = aggregera_parti(grp)
        ovriga_list.append({
            "votering":        vot,
            "avser":           avs,
            "antal_ledamoter": len(grp),
            "parti_roster":    pr,
            "totalt":          summera(pr),
        })

    return {
        "votering_id":     vid,
        "dok_id":          dok_id,
        "beteckning":      beteckning,
        "organ":           organ,
        "punkt":           punkt,
        "datum":           datum,
        "huvud_sakfragan": {
            "antal_ledamoter": len(huvud_sak),
            "parti_roster":    hs_parti_roster,
            "totalt":          hs_totalt,
        },
        "ovriga":          ovriga_list,
    }


# ── Startpunkt ────────────────────────────────────────────────────────────────

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    organ_lookup: dict[str, str] = {}
    if INPUT_PATH.exists():
        for b in json.loads(INPUT_PATH.read_text(encoding="utf-8")):
            organ_lookup[b["dok_id"]] = b.get("organ", "")
    else:
        print(f"OBS: {INPUT_PATH} saknas — organ-kolumnen lämnas tom i output.")

    print(f"=== Lager 2: partiröster via ZIP | riksmöte {RIKSMOTE} ===")
    print(f"    ZIP:    {ZIP_URL}")
    print(f"    Cache:  {ZIP_CACHE}")
    print(f"    Output: {OUTPUT_DIR}/")
    print()

    session = requests.Session()
    session.headers["User-Agent"] = "riksdag-analys/0.1 (pedagogiskt projekt)"

    # ── Hämta ZIP (eller använd cache) ───────────────────────────────────────
    zip_data, laddades_ner = hamta_zip(session)
    zf     = zipfile.ZipFile(io.BytesIO(zip_data))
    namnen = zf.namelist()
    print(f"Filer i ZIP: {len(namnen)}\n")

    # ── Läs varje votering ───────────────────────────────────────────────────
    voteringar: list[dict] = []
    ignorerade = 0

    for namn in sorted(namnen):
        parsed = parse_filnamn(namn)
        if parsed is None:
            ignorerade += 1
            continue
        dok_id, punkt, vid = parsed
        rows = las_rader(zf.read(namn))
        agg = aggregera_votering(vid, dok_id, punkt, rows, organ_lookup)
        # Hoppa over voteringar utan sakfraga-rader (t.ex. motivfrage-voteringar)
        if agg["huvud_sakfragan"]["antal_ledamoter"] == 0:
            ignorerade += 1
            continue
        voteringar.append(agg)

    if ignorerade:
        print(f"Ignorerade {ignorerade} filer som inte matchade namnmönstret.\n")

    voteringar.sort(key=lambda v: (v["datum"], v["punkt"].zfill(4)))

    n_vids = len(voteringar)
    by_dok: dict[str, list[dict]] = {}
    for v in voteringar:
        by_dok.setdefault(v["dok_id"], []).append(v)
    n_bet = len(by_dok)

    # ── Rimlighetskontroll ────────────────────────────────────────────────────
    if n_vids < EXPECTED_VOTERINGAR // 2:
        print(
            f"VARNING: Bara {n_vids} voteringar (förväntat ~{EXPECTED_VOTERINGAR}). "
            f"ZIP:en kan vara ofullständig eller tillhöra fel riksmöte."
        )
    elif n_vids > EXPECTED_VOTERINGAR * 3:
        print(
            f"VARNING: {n_vids} voteringar (förväntat ~{EXPECTED_VOTERINGAR}). "
            f"ZIP:en kan innehålla data från flera riksmöten."
        )

    if n_bet < EXPECTED_BETANKANDEN // 2:
        print(
            f"VARNING: Bara {n_bet} betänkanden (förväntat ~{EXPECTED_BETANKANDEN}). "
            f"Kontrollera att ZIP:en är komplett."
        )

    # ── Verifiera CU3 ────────────────────────────────────────────────────────
    cu3 = [v for v in voteringar if v["dok_id"] == "HD01CU3"]
    if cu3:
        print(f"CU3 verifierat: {len(cu3)} votering(ar) inlasta. OK")
    else:
        print("VARNING: Inga CU3-voteringar hittades.")

    print()
    print(f"Betänkanden med voteringar: {n_bet}")
    for dok_id in sorted(by_dok):
        vots = by_dok[dok_id]
        bet  = vots[0]["beteckning"]
        org  = vots[0]["organ"]
        print(f"  {dok_id:<16}  {bet:<10}  {org:<6}  {len(vots)} voteringar")

    print()

    # ── Rensa gamla filer och skriv nya ──────────────────────────────────────
    gamla = list(OUTPUT_DIR.glob("*.json"))
    if gamla:
        print(f"Tar bort {len(gamla)} gamla filer i {OUTPUT_DIR}/...")
        for p in gamla:
            p.unlink()

    for dok_id, vots in by_dok.items():
        out_path = OUTPUT_DIR / f"{dok_id}.json"
        out_path.write_text(
            json.dumps(vots, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(f"Sparade {n_bet} betänkande-filer.\n")

    # ── Index ─────────────────────────────────────────────────────────────────
    index: list[dict] = [
        {
            "votering_id": v["votering_id"],
            "dok_id":      v["dok_id"],
            "beteckning":  v["beteckning"],
            "organ":       v["organ"],
            "punkt":       v["punkt"],
            "datum":       v["datum"],
            "totalt":      v["huvud_sakfragan"]["totalt"],
        }
        for v in voteringar
    ]
    INDEX_PATH.write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # ── Sammanfattning ────────────────────────────────────────────────────────
    totalt_ja  = sum(e["totalt"]["Ja"]  for e in index)
    totalt_nej = sum(e["totalt"]["Nej"] for e in index)

    print("-" * 60)
    print(f"  Riksmöte:                   {RIKSMOTE}")
    print(f"  Nätverksanrop:              {'1 (ZIP nedladdad)' if laddades_ner else '0 (cachad ZIP)'}")
    print(f"  Voteringar inlästa:         {n_vids}  (förväntat ~{EXPECTED_VOTERINGAR})")
    print(f"  Betänkanden med voteringar: {n_bet}  (förväntat ~{EXPECTED_BETANKANDEN})")
    print(f"  Totalt Ja  (huvud/sak):     {totalt_ja:>8}")
    print(f"  Totalt Nej (huvud/sak):     {totalt_nej:>8}")
    print(f"  Output:                     {OUTPUT_DIR}/")
    print(f"  Index:                      {INDEX_PATH}")
    print("-" * 60)

    # ── Tidsstämpel ───────────────────────────────────────────────────────────
    stamp_path = Path("data") / "senast_uppdaterad.json"
    stamp_path.write_text(
        json.dumps({"uppdaterad": datetime.now().isoformat(timespec="seconds")},
                   ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  Tidsstämpel:                {stamp_path}")


if __name__ == "__main__":
    main()
