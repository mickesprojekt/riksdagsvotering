# Riksdag-analys

## Syfte

Analysera svensk politik baserat på **faktiska handlingar** i riksdagen —
röstbeteende, motioner, interpellationer och utskottsbeslut — hämtade direkt
från Riksdagens öppna data-API (data.riksdagen.se).

## Neutralitetsprincipen

> Vi visar primärkällor och faktiska handlingar, inte vad partier säger om sig själva.

Projektet tar **inga partipolitiska ståndpunkter** och gör **inga normativa
bedömningar** om vilka ståndpunkter som är rätta eller fel. Analysen begränsas
till att:

- Redovisa hur ledamöter faktiskt röstade
- Visa vilka motioner som undertecknades och av vem
- Mäta konsekvens mellan deklarerade ståndpunkter och faktiska röster

Alla påståenden ska vara direkt spårbara till ett `dok_id` eller `votering_id`
i Riksdagens databas. Inget ska påstås som inte kan verifieras mot primärkällan.

## Metodval: Överensstämmelseanalys

När vi analyserar hur ledamöter eller partier röstar filtrerar vi alltid på:

```
votering = "huvud"      # Huvudomröstningen — exkluderar kontrapropositioner
avser    = "sakfrågan"  # Substansen i ärendet — exkluderar formella bifallanderöster
```

Dessa filter säkerställer att vi mäter den faktiska ståndpunkten i sak och
inte procedurella röster som kan ge missvisande signal.

### Hantering av "Avstår" och "Frånvarande"

Dessa rapporteras **alltid separat** och slås aldrig ihop med varken Ja eller Nej:

| Röst        | Tolkning i analysen                                    |
|-------------|--------------------------------------------------------|
| `Ja`        | Stödjer förslaget                                      |
| `Nej`       | Motsätter sig förslaget                                |
| `Avstår`    | Aktiv icke-position — räknas separat, aldrig som Nej  |
| `Frånvarande` | Ingen röst avgiven — räknas separat, aldrig som Avstår |

Frånvaro är analytiskt relevant (t.ex. hög frånvarograd hos ett parti) men
ska inte tolkas som en ståndpunkt i sakfrågan.

## Datakällor

| Endpoint          | Vad det innehåller                        | Primärnyckel     |
|-------------------|-------------------------------------------|------------------|
| `voteringlista`   | En rad per ledamot per omröstning         | `votering_id`    |
| `dokumentlista`   | Motioner, propositioner, betänkanden      | `dok_id`         |
| `ledamotslista`   | Ledamotsprofiler, mandat, valkrets        | `intressent_id`  |

`intressent_id` är den stabila nyckeln som kopplar samman en ledamot
över alla tre datakällor och över riksmötesgränser.

## Projektstruktur

```
riksdag-analys/
├── CLAUDE.md                   # Detta dokument
├── fetch_votes.py              # Hämtar voteringsdata för ett riksmöte
├── requirements.txt
└── data/
    ├── voteringar/             # En JSON-fil per unik votering_id
    └── voteringar_index.json   # Snabbindex med metadata per votering
```
