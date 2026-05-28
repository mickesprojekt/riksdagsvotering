'use strict';

// ── Konstanter ─────────────────────────────────────────────────────────────────

const UTSKOTT = {
  'AU':   'Arbetsmarknadsutskottet',
  'CU':   'Civilutskottet',
  'FiU':  'Finansutskottet',
  'FöU':  'Försvarsutskottet',
  'JuU':  'Justitieutskottet',
  'KU':   'Konstitutionsutskottet',
  'KrU':  'Kulturutskottet',
  'MJU':  'Miljö- och jordbruksutskottet',
  'NU':   'Näringsutskottet',
  'SkU':  'Skatteutskottet',
  'SfU':  'Socialförsäkringsutskottet',
  'SoU':  'Socialutskottet',
  'TU':   'Trafikutskottet',
  'UbU':  'Utbildningsutskottet',
  'UFöU': 'Sammansatta utrikes- och försvarsutskottet',
  'UU':   'Utrikesutskottet',
};

// Politisk ordning vänster → höger (känd och faktisk spektrumplacering)
const PARTI_ORDNING = ['V', 'S', 'MP', 'C', 'L', 'KD', 'M', 'SD'];

const PARTI_NAMN = {
  'V':  'Vänsterpartiet',
  'S':  'Socialdemokraterna',
  'MP': 'Miljöpartiet',
  'C':  'Centerpartiet',
  'L':  'Liberalerna',
  'KD': 'Kristdemokraterna',
  'M':  'Moderaterna',
  'SD': 'Sverigedemokraterna',
};

// Rösttyper — ordning och visningsnamn
const ROSTTYPER = [
  { nyckel: 'Ja',          etikett: 'Ja',     css: 'ja'       },
  { nyckel: 'Nej',         etikett: 'Nej',    css: 'nej'      },
  { nyckel: 'Avstår',      etikett: 'Avstår', css: 'avstar'   },
  { nyckel: 'Frånvarande', etikett: 'Frånv.', css: 'franvaro' },
];

// ── Tillstånd ──────────────────────────────────────────────────────────────────

const tillstand = {
  betankanden:    null,   // data/betankanden.json — alla 470
  partirostIndex: null,   // data/partirost_index.json — en rad per votering
  partirostCache: {},     // dok_id → voteringsarray (laddas vid behov)
  dokumentIndex:  null,   // data/dokument_index.json — beslutsdatum + punkträkning
  dokumentCache:  {},     // dok_id → rå dokumentdata (laddas vid behov)
};

// ── Datahämtning ───────────────────────────────────────────────────────────────

async function laddaStartdata() {
  const [betankanden, index, dokumentIndex] = await Promise.all([
    fetch('data/betankanden.json').then(r => r.json()),
    fetch('data/partirost_index.json').then(r => r.json()),
    fetch('data/dokument_index.json').then(r => r.json()),
  ]);
  tillstand.betankanden    = betankanden;
  tillstand.partirostIndex = index;
  tillstand.dokumentIndex  = dokumentIndex;
}

async function laddaPartirost(dokId) {
  if (tillstand.partirostCache[dokId]) return tillstand.partirostCache[dokId];
  try {
    const data = await fetch(`data/partirost/${dokId}.json`).then(r => r.json());
    tillstand.partirostCache[dokId] = data;
    return data;
  } catch (_) {
    return [];
  }
}

async function laddaDokument(dokId) {
  if (tillstand.dokumentCache[dokId]) return tillstand.dokumentCache[dokId];
  try {
    const data = await fetch(`data/dokument/${dokId}.json`).then(r => r.json());
    tillstand.dokumentCache[dokId] = data;
    return data;
  } catch (_) {
    return null;
  }
}

function hamtaNotis(dokData) {
  const uppgRaw = dokData?.dokumentstatus?.dokuppgift?.uppgift;
  if (!uppgRaw) return null;
  const lista = Array.isArray(uppgRaw) ? uppgRaw : [uppgRaw];
  return lista.find(u => u.kod === 'notis')?.text || null;
}

function hamtaUtskottsforslag(dokData, voteringId) {
  let ufs = dokData?.dokumentstatus?.dokutskottsforslag?.utskottsforslag;
  if (!ufs) return null;
  if (!Array.isArray(ufs)) ufs = [ufs];
  const vid = voteringId.toLowerCase();
  return ufs.find(p => (p.votering_id || '').trim().toLowerCase() === vid) || null;
}

function hamtaVoteringCaption(punkt) {
  const vs = punkt?.votering_sammanfattning_html;
  if (!vs || typeof vs !== 'object') return null;
  // table kan vara en lista när punkten hade både sakfråga och motivfråga —
  // ta alltid första elementet (sakfrågan)
  const table = Array.isArray(vs.table) ? vs.table[0] : vs.table;
  if (!table) return null;
  const cap = table.caption;
  if (!cap) return null;
  return { rubrik: cap.b || '', text: cap['#text'] || '' };
}

// ── Router ─────────────────────────────────────────────────────────────────────
// Hash-baserad routing: # = hem | #betankande/<dok_id> | #votering/<vid>/<dok_id>

function route() {
  const hash  = location.hash || '#';
  const delar = hash.slice(1).split('/').map(s => { try { return decodeURIComponent(s); } catch(_) { return s; } });
  const vy    = delar[0] || '';

  if      (!vy)                    visaHem();
  else if (vy === 'utskott')       visaUtskott(delar[1]);
  else if (vy === 'betankande')    visaBetankande(delar[1]);
  else if (vy === 'votering')      visaVotering(delar[1], delar[2]);
  else if (vy === 'om')            visaOm();
  else if (vy === 'ordlista')      visaOrdlista();
  else if (vy === 'processen')     visaProcessen();
  else                             visaHem();
}

// ── Vy: Om sidan ───────────────────────────────────────────────────────────────

function visaOm() {
  app().innerHTML = `
    <nav class="brodsmulenav">
      <a href="#">← Tillbaka</a>
    </nav>
    <section class="om-sida">
      <h1>Om sidan</h1>
      <p>
        Tanken med denna sida är att du snabbt ska kunna få en inblick i de frågor där
        partierna är så oeniga att de går till omröstning. De flesta beslut tas i enighet
        och syns därför inte här.
      </p>
      <p>
        Riksdagsvotering.se sammanställer riksdagens egna offentliga uppgifter och
        presenterar dem i ett enklare format. För den som är ännu mer intresserad så
        länkar vi även till originalet för varje betänkande.
      </p>

      <h2>Ansvarsfriskrivning</h2>
      <p>
        Sammanfattningarna är skrivna av riksdagen, oftast av utskottsmajoriteten, och
        återges ordagrant. De speglar därför utskottets perspektiv. Reservationer och
        avvikande meningar finns med men får inte alltid lika mycket utrymme som
        majoritetens linje.
      </p>
      <p>
        Sidan tar inte ställning och tolkar inte. Data licensieras under
        <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">CC BY 4.0</a>.
      </p>

    </section>
  `;
}

// ── Vy: Ordlista ───────────────────────────────────────────────────────────────

function visaOrdlista() {
  app().innerHTML = `
    <nav class="brodsmulenav">
      <a href="#">← Tillbaka</a>
    </nav>
    <section class="om-sida">
      <h1>Ordlista</h1>
      <dl class="ordlista">
        <div>
          <dt>Acklamation</dt>
          <dd>när alla i riksdagen är överens och säger ja tillsammans, utan att rösterna behöver räknas</dd>
        </div>
        <div>
          <dt>Avslå</dt>
          <dd>att säga nej till ett förslag</dd>
        </div>
        <div>
          <dt>Betänkande</dt>
          <dd>ett färdigt förslag från ett utskott, som hela riksdagen sedan röstar om</dd>
        </div>
        <div>
          <dt>Kammaren</dt>
          <dd>hela riksdagen samlad i salen, där de slutgiltiga besluten tas</dd>
        </div>
        <div>
          <dt>Ledamot</dt>
          <dd>en politiker som folket har röstat in i riksdagen. Det finns 349 stycken</dd>
        </div>
        <div>
          <dt>Motion</dt>
          <dd>ett förslag från en eller flera ledamöter (alltså inte från regeringen)</dd>
        </div>
        <div>
          <dt>Motivfråga</dt>
          <dd>en omröstning om motiveringen till ett beslut, alltså vilka skäl som ska anges, snarare än själva beslutet. Den här sidan visar bara omröstningar om sakfrågan, inte motivfrågor</dd>
        </div>
        <div>
          <dt>Reservation</dt>
          <dd>ett annat förslag från de i utskottet som inte höll med majoriteten. Det ställs ofta mot utskottets förslag i en omröstning</dd>
        </div>
        <div>
          <dt>Sakfråga</dt>
          <dd>själva beslutet i sig, alltså vad riksdagen faktiskt bestämmer (till skillnad från motivfrågan, som handlar om skälen bakom)</dd>
        </div>
        <div>
          <dt>Utskott</dt>
          <dd>en mindre grupp ledamöter som går igenom och förbereder frågor inom ett visst område, till exempel skola eller skatt, innan hela riksdagen röstar</dd>
        </div>
        <div>
          <dt>Votering</dt>
          <dd>en omröstning där varje ledamots röst räknas</dd>
        </div>
        <div>
          <dt>Yrka</dt>
          <dd>att lägga fram en begäran om något, ofta inuti en motion. En motion kan innehålla flera yrkanden om olika saker</dd>
        </div>
      </dl>
    </section>
  `;
}

// ── Vy: Processen ──────────────────────────────────────────────────────────────

function visaProcessen() {
  app().innerHTML = `
    <nav class="brodsmulenav">
      <a href="#">← Tillbaka</a>
    </nav>
    <section class="om-sida">
      <h1>Processen</h1>
      <p>
        Varje beslut i riksdagen börjar med ett betänkande, vilket är ett utskotts
        färdiga förslag. Ett betänkande innehåller flera förslagspunkter, och varje
        punkt avgörs var för sig. Är alla partier eniga om en punkt klubbas den med
        acklamation (utan omröstning). Finns det en reservation — ett konkurrerande
        förslag från en minoritet i utskottet — kan punkten gå till votering, där
        kammaren röstar mellan utskottets förslag och reservationen. Den här sidan
        visar bara de punkter som gick till votering, eftersom det är där partiernas
        skiljelinjer syns.
      </p>
      <div class="process-diagram">
        <svg width="100%" viewBox="0 0 680 470" role="img"><title>Beslutsvägen för en förslagspunkt</title><desc>Ett betänkande innehåller flera förslagspunkter. Varje punkt avgörs antingen med acklamation om alla är eniga, eller med votering om det finns en reservation.</desc>
<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M2 1L8 5L2 9" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<g><rect x="250" y="30" width="180" height="56" rx="8" fill="#F1EFE8" stroke="#5F5E5A" stroke-width="0.5"/>
<text x="340" y="50" text-anchor="middle" dominant-baseline="central" font-size="14" font-weight="500" fill="#2C2C2A">Betänkande</text>
<text x="340" y="68" text-anchor="middle" dominant-baseline="central" font-size="12" fill="#5F5E5A">utskottets förslag</text></g>
<line x1="340" y1="86" x2="340" y2="120" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#arrow)"/>
<g><rect x="250" y="120" width="180" height="56" rx="8" fill="#EEEDFE" stroke="#534AB7" stroke-width="0.5"/>
<text x="340" y="140" text-anchor="middle" dominant-baseline="central" font-size="14" font-weight="500" fill="#26215C">Förslagspunkt</text>
<text x="340" y="158" text-anchor="middle" dominant-baseline="central" font-size="12" fill="#534AB7">en punkt att besluta</text></g>
<line x1="300" y1="176" x2="180" y2="230" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#arrow)"/>
<line x1="380" y1="176" x2="500" y2="230" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#arrow)"/>
<g><rect x="70" y="230" width="220" height="56" rx="8" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/>
<text x="180" y="250" text-anchor="middle" dominant-baseline="central" font-size="14" font-weight="500" fill="#04342C">Alla eniga</text>
<text x="180" y="268" text-anchor="middle" dominant-baseline="central" font-size="12" fill="#0F6E56">ingen vill rösta</text></g>
<g><rect x="390" y="230" width="220" height="56" rx="8" fill="#FAEEDA" stroke="#854F0B" stroke-width="0.5"/>
<text x="500" y="250" text-anchor="middle" dominant-baseline="central" font-size="14" font-weight="500" fill="#412402">Reservation</text>
<text x="500" y="268" text-anchor="middle" dominant-baseline="central" font-size="12" fill="#854F0B">någon tycker annat</text></g>
<line x1="180" y1="286" x2="180" y2="330" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#arrow)"/>
<line x1="500" y1="286" x2="500" y2="330" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#arrow)"/>
<g><rect x="70" y="330" width="220" height="56" rx="8" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/>
<text x="180" y="350" text-anchor="middle" dominant-baseline="central" font-size="14" font-weight="500" fill="#04342C">Acklamation</text>
<text x="180" y="368" text-anchor="middle" dominant-baseline="central" font-size="12" fill="#0F6E56">beslut utan omröstning</text></g>
<g><rect x="390" y="330" width="220" height="56" rx="8" fill="#FAEEDA" stroke="#854F0B" stroke-width="0.5"/>
<text x="500" y="350" text-anchor="middle" dominant-baseline="central" font-size="14" font-weight="500" fill="#412402">Votering</text>
<text x="500" y="368" text-anchor="middle" dominant-baseline="central" font-size="12" fill="#854F0B">kammaren röstar</text></g>
<line x1="180" y1="386" x2="180" y2="420" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#arrow)"/>
<line x1="500" y1="386" x2="500" y2="420" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#arrow)"/>
<g><rect x="70" y="420" width="220" height="40" rx="8" fill="#F1EFE8" stroke="#5F5E5A" stroke-width="0.5"/>
<text x="180" y="440" text-anchor="middle" dominant-baseline="central" font-size="14" font-weight="500" fill="#2C2C2A">Beslut</text></g>
<g><rect x="390" y="420" width="220" height="40" rx="8" fill="#F1EFE8" stroke="#5F5E5A" stroke-width="0.5"/>
<text x="500" y="440" text-anchor="middle" dominant-baseline="central" font-size="14" font-weight="500" fill="#2C2C2A">Beslut</text></g>
</svg>
      </div>
      <p>
        När du klickar på en votering visas en ruta med punktens rubrik och de motioner
        den gällde. En motion är ett förslag som väckts av en eller flera ledamöter, och
        namnen som står efter motionen är de som lämnat in den, där partibeteckningen inom
        parentes visar vilket parti de tillhör. "M.fl." betyder att fler ledamöter står
        bakom än de som nämns vid namn. Längst ned i rutan står vad omröstningen ställdes
        mot. Om det exempelvis står "Utskottets förslag mot reservation 1 (MP)", betyder
        det att utskottets förslag stod mot ett alternativt förslag från MP. I rösttabellen
        gäller då: ja = rösta för utskottets förslag, nej = rösta för reservationen.
      </p>
    </section>
  `;
}

// ── Vy: Förstasida ─────────────────────────────────────────────────────────────

function visaHem() {
  // Betänkanden per organ (alla 470)
  const betPerOrgan = {};
  for (const b of tillstand.betankanden) {
    betPerOrgan[b.organ] = (betPerOrgan[b.organ] || 0) + 1;
  }

  // Voteringar per dok_id, sedan summerat per organ
  const votPerDok = {};
  for (const v of tillstand.partirostIndex) {
    votPerDok[v.dok_id] = (votPerDok[v.dok_id] || 0) + 1;
  }
  const votPerOrgan = {};
  for (const b of tillstand.betankanden) {
    votPerOrgan[b.organ] = (votPerOrgan[b.organ] || 0) + (votPerDok[b.dok_id] || 0);
  }

  // Alla unika organ, sorterade efter fullständigt namn
  const alleOrganer = [...new Set(tillstand.betankanden.map(b => b.organ))]
    .sort((a, b) => (UTSKOTT[a] || a).localeCompare(UTSKOTT[b] || b, 'sv'));

  // Statistik för ingress
  const betMedVoteringar = tillstand.betankanden.filter(b => votPerDok[b.dok_id]);

  app().innerHTML = `
    <section class="intro">
      <h1>Riksdagens voteringar 2025/26</h1>
      <p class="ingress">
        De slutliga besluten i riksdagen fattas i kammaren.
        Beslutsformerna är två: antingen votering, eller acklamation.
        Votering används bara när partierna är oeniga — de flesta beslut fattas
        med acklamation och syns aldrig i röstdatabasen.
        Högst upp på sidan finns en ordlista som förklarar de centrala begreppen,
        och vill du veta mer kan du även klicka på <a href="#om">om sidan</a>.
      </p>
      <div class="statistik-rad">
        <div class="statistik-siffra">
          <strong>${tillstand.betankanden.length}</strong>
          <span>betänkanden totalt</span>
        </div>
        <div class="statistik-siffra">
          <strong>${betMedVoteringar.length}</strong>
          <span>gick till votering</span>
        </div>
        <div class="statistik-siffra">
          <strong>${tillstand.partirostIndex.length}</strong>
          <span>omröstningar</span>
        </div>
      </div>
    </section>

    <h2 class="sektionsrubrik">Utskott</h2>

    <ul class="utskott-lista">
      ${alleOrganer.map(organ => {
        const nBet = betPerOrgan[organ] || 0;
        const nVot = votPerOrgan[organ] || 0;
        return `
          <li>
            <a href="#utskott/${organ}" class="utskott-bar">
              <span class="utskott-namn">${UTSKOTT[organ] || organ}</span>
              <span class="utskott-tal">
                <span>${nBet} ${nBet === 1 ? 'betänkande' : 'betänkanden'}</span>
                <span>${nVot} ${nVot === 1 ? 'votering' : 'voteringar'}</span>
              </span>
            </a>
          </li>
        `;
      }).join('')}
    </ul>
  `;
}

// ── Vy: Utskott ────────────────────────────────────────────────────────────────

function visaUtskott(organ) {
  const antalVoteringar = {};
  for (const v of tillstand.partirostIndex) {
    antalVoteringar[v.dok_id] = (antalVoteringar[v.dok_id] || 0) + 1;
  }

  const allaBetankanden = tillstand.betankanden.filter(b => b.organ === organ);
  // Visa bara betänkanden med minst en votering i listan
  const betankanden = allaBetankanden.filter(b => antalVoteringar[b.dok_id]);
  const utskottNamn = UTSKOTT[organ] || organ;

  const totaltVoteringar = betankanden
    .reduce((sum, b) => sum + (antalVoteringar[b.dok_id] || 0), 0);

  const ingenVoteringRuta = totaltVoteringar === 0 ? `
    <div class="ingen-votering-info">
      Utskottet har hittills inte haft några voteringar under riksmötet 2025/26 (pågående).
      Alla beslut har fattats med acklamation.
    </div>` : '';

  app().innerHTML = `
    <nav class="brodsmulenav">
      <a href="#">← Alla utskott</a>
    </nav>

    <section class="betankande-huvud">
      <h1>${utskottNamn}</h1>
    </section>

    ${ingenVoteringRuta}

    <ul class="betankande-lista">
      ${betankanden.map(b => {
        const nVot = antalVoteringar[b.dok_id] || 0;
        return `
          <li>
            <a href="#betankande/${b.dok_id}" class="betankande-kort">
              <span class="beteckning">${b.beteckning}</span>
              <span class="titel">${b.titel}</span>
              <span class="antal-voteringar${nVot === 0 ? ' acklamation' : ''}">
                ${nVot > 0
                  ? `${nVot} ${nVot === 1 ? 'votering' : 'voteringar'}`
                  : 'acklamation'}
              </span>
            </a>
          </li>
        `;
      }).join('')}
    </ul>
  `;
}

// ── Vy: Betänkande ─────────────────────────────────────────────────────────────

async function visaBetankande(dokId) {
  app().innerHTML = '<p class="laddar">Laddar…</p>';

  const bet = tillstand.betankanden.find(b => b.dok_id === dokId);
  if (!bet) {
    app().innerHTML = `<p class="fel">Betänkande ${dokId} hittades inte.</p>
      <p><a href="#">← Tillbaka</a></p>`;
    return;
  }

  const [voteringar, dokData] = await Promise.all([
    laddaPartirost(dokId),
    laddaDokument(dokId),
  ]);

  // Länk till riksdagen.se — beteckning + dok_id i gemener
  const riksdagenUrl =
    `https://www.riksdagen.se/sv/dokument-och-lagar/dokument/betankande/` +
    `${bet.beteckning.toLowerCase()}_${dokId.toLowerCase()}/`;

  const idxPost = tillstand.dokumentIndex?.find(d => d.dok_id === dokId) || null;
  const notis   = hamtaNotis(dokData);

  const statusrad = idxPost ? `
    <div class="beslutsstatus">
      Beslutades i kammaren ${formatDatum(idxPost.beslutsdatum)}.
      Förslagspunkter: ${idxPost.antal_punkter},
      Acklamationer: ${idxPost.antal_acklamationer},
      Voteringar: ${idxPost.antal_voteringar}.
    </div>` : '';

  const sammanfattning = notis ? `
    <section class="riksdagens-sammanfattning">
      <h2 class="sammanfattning-rubrik">
        Riksdagens sammanfattning
        <a href="${riksdagenUrl}" target="_blank" rel="noopener" class="kallank">Källa på riksdagen.se ↗</a>
      </h2>
      <div class="sammanfattning-html">${sanera(notis)}</div>
    </section>` : '';

  app().innerHTML = `
    <nav class="brodsmulenav">
      <a href="#">Alla utskott</a>
      <span class="brodsmulesep">›</span>
      <a href="#utskott/${bet.organ}">${UTSKOTT[bet.organ] || bet.organ}</a>
    </nav>

    <section class="betankande-huvud">
      <span class="beteckning-stor">${bet.beteckning}</span>
      <h1>${bet.titel}</h1>
      <p class="meta-rad">
        <span>${UTSKOTT[bet.organ] || bet.organ}</span>
        <span>${formatDatum(bet.datum)}</span>
        <a href="${riksdagenUrl}" target="_blank" rel="noopener">
          Originaldokument på riksdagen.se ↗
        </a>
      </p>
    </section>

    ${statusrad}
    ${sammanfattning}

    <h2 class="sektionsrubrik">
      Voteringar — ${voteringar.length}
      ${voteringar.length === 1 ? 'omröstning' : 'omröstningar'}
    </h2>

    ${voteringar.length === 0
      ? '<p>Inga voteringar registrerade för detta betänkande.</p>'
      : `<ul class="votering-lista">
          ${voteringar.map(v => `
            <li>
              <a href="#votering/${v.votering_id}/${dokId}" class="votering-kort">
                <span class="punkt-etikett">Punkt ${v.punkt}</span>
                <span class="datum-liten">${formatDatum(v.datum)}</span>
                <span class="chip-rad">
                  ${bygChips(v.huvud_sakfragan.totalt)}
                </span>
              </a>
            </li>
          `).join('')}
        </ul>`
    }
  `;
}

// ── Vy: Votering ───────────────────────────────────────────────────────────────

async function visaVotering(voteringId, dokId) {
  app().innerHTML = '<p class="laddar">Laddar…</p>';

  // dok_id kan saknas i äldre bokmärken — sök i index
  if (!dokId) {
    const post = tillstand.partirostIndex.find(v => v.votering_id === voteringId);
    if (post) dokId = post.dok_id;
  }

  const bet = tillstand.betankanden.find(b => b.dok_id === dokId) || {};
  const [voteringar, dokData] = await Promise.all([
    laddaPartirost(dokId),
    laddaDokument(dokId),
  ]);
  const votering = voteringar.find(v => v.votering_id === voteringId);

  if (!votering) {
    app().innerHTML = `<p class="fel">Votering ${voteringId} hittades inte.</p>
      <p><a href="#betankande/${dokId}">← Tillbaka till ${bet.beteckning || dokId}</a></p>`;
    return;
  }

  const hs      = votering.huvud_sakfragan;
  const roster  = hs.parti_roster;
  const partier = sorteraPartier(Object.keys(roster).filter(p => p !== '-'));

  // Lägg okänt parti sist om det finns
  if (roster['-']) partier.push('-');

  const punkt   = hamtaUtskottsforslag(dokData, voteringId);
  const caption = punkt ? hamtaVoteringCaption(punkt) : null;

  const punktDetalj = punkt ? `
    <section class="votering-detalj">
      ${punkt.rubrik ? `<h2 class="detalj-rubrik">${esc(punkt.rubrik)}</h2>` : ''}
      ${punkt.forslag ? `<div class="detalj-forslag">${sanera(punkt.forslag)}</div>` : ''}
      ${caption && caption.text ? `
        <p class="votering-mot">
          <strong>${esc(caption.rubrik)}</strong>${caption.rubrik && caption.text ? ' — ' : ''}${esc(caption.text)}
        </p>` : ''}
    </section>` : '';

  app().innerHTML = `
    <nav class="brodsmulenav">
      <a href="#">Alla utskott</a>
      <span class="brodsmulesep">›</span>
      <a href="#utskott/${votering.organ}">${UTSKOTT[votering.organ] || votering.organ}</a>
      <span class="brodsmulesep">›</span>
      <a href="#betankande/${dokId}">${bet.beteckning || dokId}</a>
    </nav>

    <section class="votering-huvud">
      <h1>${bet.beteckning || dokId} — punkt ${votering.punkt}</h1>
      <p class="meta-rad">
        <span>${UTSKOTT[votering.organ] || votering.organ || ''}</span>
        <span>${formatDatum(votering.datum)}</span>
        <span>${hs.antal_ledamoter} ledamöter</span>
      </p>
      <p class="forklaring">
        Siffrorna gäller huvudomröstningen om sakfrågan.
        Varje ledamot röstar individuellt — partiintern splittring syns direkt i kolumnerna.
      </p>
    </section>

    ${punktDetalj}

    <table class="roster-tabell">
      <thead>
        <tr>
          <th class="parti-kol">Parti</th>
          ${ROSTTYPER.map(rt =>
            `<th class="${rt.css}">${rt.etikett}</th>`
          ).join('')}
          <th class="visuell-kol">Ja / Nej</th>
        </tr>
      </thead>
      <tbody>
        ${partier.map(parti => {
          const r = roster[parti];
          return `
            <tr>
              <td class="parti-cell">
                <span class="parti-farg parti-${parti}"></span>
                <span class="parti-kod">${parti}</span>
                <span class="parti-namn">${PARTI_NAMN[parti] || ''}</span>
              </td>
              ${ROSTTYPER.map(rt => {
                const n   = r[rt.nyckel] ?? 0;
                const nol = n === 0 ? ' noll' : '';
                return `<td class="antal ${rt.css}${nol}">${n}</td>`;
              }).join('')}
              <td class="visuell">${janejStapel(r['Ja'] ?? 0, r['Nej'] ?? 0)}</td>
            </tr>
          `;
        }).join('')}
      </tbody>
      <tfoot>
        <tr>
          <td class="parti-cell"><span class="parti-kod">Totalt</span></td>
          ${ROSTTYPER.map(rt => {
            const n = hs.totalt[rt.nyckel] ?? 0;
            return `<td class="antal ${rt.css}">${n}</td>`;
          }).join('')}
          <td></td>
        </tr>
      </tfoot>
    </table>

    <p class="kallnot">
      Primärkälla: <a href="https://data.riksdagen.se/voteringlista/?votering_id=${voteringId}&utformat=json"
        target="_blank" rel="noopener">data.riksdagen.se</a>
      — votering_id: <code>${voteringId}</code>
    </p>
  `;
}

// ── Hjälpfunktioner ────────────────────────────────────────────────────────────

function app() {
  return document.getElementById('app');
}

// Sanerar HTML från externa källor — behåller formatering, tar bort skript/händelsehanterare.
function sanera(html) {
  return DOMPurify.sanitize(html);
}

// HTML-kodar en textsträng som ska renderas som text, inte markup.
function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatDatum(s) {
  if (!s) return '';
  // Parsa som lokal datum (YYYY-MM-DD) — undvik tidszonsförskjutning
  const [y, m, d] = s.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('sv-SE', {
    year: 'numeric', month: 'long', day: 'numeric',
  });
}

function sorteraPartier(lista) {
  return [...lista].sort((a, b) => {
    const ia = PARTI_ORDNING.indexOf(a);
    const ib = PARTI_ORDNING.indexOf(b);
    if (ia === -1 && ib === -1) return a.localeCompare(b, 'sv');
    if (ia === -1) return 1;
    if (ib === -1) return -1;
    return ia - ib;
  });
}

function bygChips(totalt) {
  return ROSTTYPER
    .filter(rt => (totalt[rt.nyckel] ?? 0) > 0)
    .map(rt => `<span class="chip ${rt.css}">${totalt[rt.nyckel]} ${rt.etikett}</span>`)
    .join('');
}

function janejStapel(ja, nej) {
  const tot = ja + nej;
  if (tot === 0) return '<span class="bar-tom">—</span>';
  const pctJa = Math.round((ja / tot) * 100);
  return `<div class="ja-nej-bar">
    <div class="bar-ja"  style="width:${pctJa}%"></div>
    <div class="bar-nej" style="width:${100 - pctJa}%"></div>
  </div>`;
}

// ── Start ──────────────────────────────────────────────────────────────────────

window.addEventListener('hashchange', route);

laddaStartdata()
  .then(route)
  .catch(fel => {
    app().innerHTML = `
      <p class="fel">Kunde inte ladda data: ${fel.message}</p>
      <div class="fel">
        <p>Sidan måste öppnas via en lokal webbserver, inte direkt från disk.</p>
        <p>Kör detta i terminalen (i projektmappen):</p>
        <pre>python -m http.server 8000</pre>
        <p>Öppna sedan <strong>http://localhost:8000</strong> i webbläsaren.</p>
      </div>
    `;
  });
