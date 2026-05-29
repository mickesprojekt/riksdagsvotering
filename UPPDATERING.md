# Uppdatera sidan med ny voteringsdata

Den här filen förklarar hur du hämtar ny data från riksdagen och publicerar den på GitHub.
Skriven för att vara självförklarande även om du inte rört projektet på länge.

---

## När ska du uppdatera?

Riksdagen röstar vanligtvis en till två gånger i veckan under sessionstiden (september–juni).
Efter varje omröstningsvecka dyker nya voteringar upp i Riksdagens öppna data.

Bra tillfällen att uppdatera:
- En gång i veckan under aktiv sessionstid
- Efter att något uppmärksammat betänkande har röstats igenom

Du kan snabbkolla på [riksdagen.se/sv/dokument-och-lagar/riksdagens-arbete/voteringar/](https://www.riksdagen.se/sv/dokument-och-lagar/riksdagens-arbete/voteringar/)
om det kommit nya voteringar sedan förra gången.

---

## Steg-för-steg: uppdatera datan

Öppna PowerShell och kör följande kommandon i ordning.

### 1. Gå till projektmappen

```powershell
cd C:\Users\mikey\riksdag-analys
```

### 2. Hämta listan över betänkanden

```powershell
python fetch_betankanden.py
```

**Vad det gör:** Hämtar en lista över alla betänkanden för riksmöte 2025/26 och sparar
den i `data/betankanden.json`. Nya betänkanden som tillkommit sedan förra gången läggs till.

### 3. Hämta voteringsdata (tvinga ny nedladdning)

```powershell
python fetch_partirost.py --force
```

**Vad det gör:** Laddar ner den senaste versionen av Riksdagens bulk-ZIP med all voteringsdata.
Flaggan `--force` är viktig — utan den används den gamla cachade filen och du missar nya voteringar.
Skriptet sparar aggregerade partiröster i `data/partirost/` och uppdaterar automatiskt
tidsstämpeln i `data/senast_uppdaterad.json`.

### 4. Hämta dokumentdata

```powershell
python fetch_dokument.py
```

**Vad det gör:** Hämtar fullständiga dokumentdata (sammanfattningar, motionstext m.m.)
för varje betänkande och sparar dem i `data/dokument/`. Filer som redan finns hoppas över,
så det är bara nya betänkanden som laddas ner.

### 5. Generera analysfilerna

```powershell
python analyze_partirost.py
```

**Vad det gör:** Räknar igenom all voteringsdata och genererar `data/analysis.json` och
`data/analysis_matris.csv` med partiöverenstämmelse och partilinjer.

---

## Verifiera att uppdateringen lyckades

### Kontrollera antalet voteringar

I utskriften från steg 3 (fetch_partirost.py) visas en rad i stil med:

```
  Voteringar inlästa:         543  (förväntat ~527)
```

Om siffran ökat jämfört med förra gången (527 vid senaste körning) har nya voteringar
kommit med. Om siffran är oförändrad har inga nya voteringar tillkommit sedan förra körningen.

**OBS:** Om siffran avviker kraftigt (mer än dubbelt eller mindre än hälften) — stanna upp
och läs varningsmeddelandet som visas. Det kan tyda på att ZIP-filen är felaktig.

### Kontrollera tidsstämpeln

```powershell
Get-Content data\senast_uppdaterad.json
```

Ska visa något i stil med `{"uppdaterad": "2026-06-04T14:22:00"}` med dagens datum och tid.

### Kontrollera i webbläsaren

Starta servern (om den inte redan kör):

```powershell
python -m http.server 8000
```

Öppna [http://localhost:8000](http://localhost:8000) och gör en hård omladdning
(**Ctrl+Shift+R**) för att undvika att webbläsaren visar cachad data.
Sidfoten ska visa det nya datumet under "Data hämtad".

---

## Uppdatera EXPECTED-konstanterna (vid behov)

Om antalet voteringar ökat permanent (inte bara en engångsgrej) bör du uppdatera
förväntningskonstanterna i skripten så att du fortsätter få vettiga varningar.

Öppna `fetch_partirost.py` och ändra:
```python
EXPECTED_VOTERINGAR  = 527   # ← sätt till det nya antalet
EXPECTED_BETANKANDEN = 196   # ← uppdatera vid behov
```

Gör samma sak i `analyze_partirost.py`:
```python
EXPECTED_VOTERINGAR = 527   # ← samma nya antal
```

---

## Pusha till GitHub

När du är nöjd med uppdateringen laddar du upp ändringarna:

```powershell
git add data/
git commit -m "Uppdaterar data 2026-06-04"
git push
```

**Vad varje rad gör:**
- `git add data/` — markerar alla ändrade datafiler (hela data-mappen, cache utesluts automatiskt av .gitignore)
- `git commit -m "..."` — sparar en ögonblicksbild lokalt med ett beskrivande meddelande (byt datumet)
- `git push` — laddar upp till GitHub

---

## Vanliga problem

### Servern kör fortfarande på port 8000

Om du får "Address already in use" när du försöker starta `python -m http.server 8000`:

```powershell
# Hitta vilket program som använder porten
netstat -ano | findstr :8000

# Avsluta processen (byt ut XXXX mot PID-numret från föregående kommando)
taskkill /PID XXXX /F
```

### Webbläsaren visar gammal data trots uppdatering

Webbläsaren kan cacha JSON-filerna. Lösning:
1. Öppna DevTools (F12) → Network-fliken → kryssa i **Disable cache**
2. Ladda om sidan

Alternativt: Högerklicka på uppdateringsknappen → **Empty Cache and Hard Reload**.

### fetch_partirost.py varnar om fel antal voteringar

Skriptet jämför med `EXPECTED_VOTERINGAR`. En varning betyder inte att något gick fel —
det är bara en påminnelse om att antalet avviker från det förväntade. Läs igenom
voteringstabellen i utskriften och kontrollera att inga rader ser konstiga ut
(t.ex. väldigt få röster, `< 150`).

### En betänkande-fil saknas i data/dokument/

Om `fetch_dokument.py` misslyckades för ett specifikt betänkande kan du köra om det
ensamt med:

```powershell
python fetch_dokument.py
```

Skriptet hoppar automatiskt över filer som redan finns och försöker bara ladda ner
det som saknas.

### Du vet inte vad som ändrats sedan sist

```powershell
git diff --stat HEAD
```

Visar vilka filer som ändrats och hur många rader som lagts till eller tagits bort
jämfört med senaste commit.
