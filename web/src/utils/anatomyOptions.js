export const FEMALE_TEXTURE_OPTIONS = [
  { value: 'Perky', key: 'perky', i18nKey: 'anatomy.textures.perky', fallback: 'Perky', label: 'Perky' },
  { value: 'Firm', key: 'firm', i18nKey: 'anatomy.textures.firm', fallback: 'Firm', label: 'Firm' },
  { value: 'Supple', key: 'supple', i18nKey: 'anatomy.textures.supple', fallback: 'Supple', label: 'Supple' },
  { value: 'Teardrop', key: 'teardrop', i18nKey: 'anatomy.textures.teardrop', fallback: 'Teardrop', label: 'Teardrop' },
  { value: 'Plush', key: 'plush', i18nKey: 'anatomy.textures.plush', fallback: 'Plush', label: 'Plush' },
  { value: 'Pillowy', key: 'pillowy', i18nKey: 'anatomy.textures.pillowy', fallback: 'Pillowy', label: 'Pillowy' },
  { value: 'Bouncy', key: 'bouncy', i18nKey: 'anatomy.textures.bouncy', fallback: 'Bouncy', label: 'Bouncy' },
  { value: 'Delicate', key: 'delicate', i18nKey: 'anatomy.textures.delicate', fallback: 'Delicate', label: 'Delicate' },
  { value: 'Sensitive', key: 'sensitive', i18nKey: 'anatomy.textures.sensitive', fallback: 'Sensitive', label: 'Sensitive' },
];

export const MALE_TEXTURE_OPTIONS = [
  { value: 'Firm', key: 'firm', i18nKey: 'anatomy.textures.firm', fallback: 'Firm', label: 'Firm' },
  { value: 'Veined', key: 'veined', i18nKey: 'anatomy.textures.veined', fallback: 'Veined', label: 'Veined' },
  { value: 'Smooth', key: 'smooth', i18nKey: 'anatomy.textures.smooth', fallback: 'Smooth', label: 'Smooth' },
  { value: 'Thick', key: 'thick', i18nKey: 'anatomy.textures.thick', fallback: 'Thick', label: 'Thick' },
  { value: 'Heavy', key: 'heavy', i18nKey: 'anatomy.textures.heavy', fallback: 'Heavy', label: 'Heavy' },
  { value: 'Curved', key: 'curved', i18nKey: 'anatomy.textures.curved', fallback: 'Curved', label: 'Curved' },
  { value: 'Tapered', key: 'tapered', i18nKey: 'anatomy.textures.tapered', fallback: 'Tapered', label: 'Tapered' },
  { value: 'Sensitive', key: 'sensitive', i18nKey: 'anatomy.textures.sensitive', fallback: 'Sensitive', label: 'Sensitive' },
];

const TEXTURE_LABEL_CONFIG = {
  perky: { canonical: 'Perky', i18nKey: 'anatomy.textures.perky', fallback: 'Perky' },
  firm: { canonical: 'Firm', i18nKey: 'anatomy.textures.firm', fallback: 'Firm' },
  supple: { canonical: 'Supple', i18nKey: 'anatomy.textures.supple', fallback: 'Supple' },
  teardrop: { canonical: 'Teardrop', i18nKey: 'anatomy.textures.teardrop', fallback: 'Teardrop' },
  plush: { canonical: 'Plush', i18nKey: 'anatomy.textures.plush', fallback: 'Plush' },
  pillowy: { canonical: 'Pillowy', i18nKey: 'anatomy.textures.pillowy', fallback: 'Pillowy' },
  bouncy: { canonical: 'Bouncy', i18nKey: 'anatomy.textures.bouncy', fallback: 'Bouncy' },
  delicate: { canonical: 'Delicate', i18nKey: 'anatomy.textures.delicate', fallback: 'Delicate' },
  sensitive: { canonical: 'Sensitive', i18nKey: 'anatomy.textures.sensitive', fallback: 'Sensitive' },
  veined: { canonical: 'Veined', i18nKey: 'anatomy.textures.veined', fallback: 'Veined' },
  smooth: { canonical: 'Smooth', i18nKey: 'anatomy.textures.smooth', fallback: 'Smooth' },
  thick: { canonical: 'Thick', i18nKey: 'anatomy.textures.thick', fallback: 'Thick' },
  heavy: { canonical: 'Heavy', i18nKey: 'anatomy.textures.heavy', fallback: 'Heavy' },
  curved: { canonical: 'Curved', i18nKey: 'anatomy.textures.curved', fallback: 'Curved' },
  tapered: { canonical: 'Tapered', i18nKey: 'anatomy.textures.tapered', fallback: 'Tapered' },
};

const LEGACY_FEMALE_TEXTURE_MAP = {
  'perky & high-set': 'Perky',
  'pillowy soft & yielding': 'Pillowy',
  'firm & toned': 'Firm',
  'smooth & supple': 'Supple',
  'warm & supple': 'Supple',
  'heavy & plush': 'Plush',
  'bouncy & sensitive': 'Bouncy',
  'tender & delicate': 'Delicate',
  'shapely teardrop': 'Teardrop',
  'compact & dense': 'Firm',
  'sensitive & responsive': 'Sensitive',
  'soft & downy chest fur': 'Supple',
  'silky fur-rimmed': 'Supple',
  'velvety underbelly down': 'Plush',
  'fluffy plush-accented': 'Plush',
  'silky warm with smooth micro-scales': 'Supple',
  'supple with shimmering scale borders': 'Supple',
  'sleek & supple drake-contour': 'Firm',
  'serpentine smooth with fine scales': 'Supple',
  'downy feather-lined': 'Delicate',
  'light & buoyant': 'Perky',
  'velvety plumage accents': 'Supple',
  'glistening & ultra-smooth': 'Supple',
  'soft scaled flank accents': 'Supple',
};

const LEGACY_MALE_TEXTURE_MAP = {
  'veined & firm': 'Veined',
  'smooth & heavy': 'Heavy',
  'toned & athletic': 'Firm',
  'warm & pulsing': 'Sensitive',
  'slender & ultra-sensitive': 'Sensitive',
  'dense & formidable': 'Thick',
  'balanced & firm': 'Firm',
  'soft fur-ringed base': 'Smooth',
  'sleek scaled base & firm': 'Firm',
  'sturdy draconic build': 'Thick',
  'silky fur-dusted & resilient': 'Firm',
};

const SPECIES_SURFACE_CONFIG = {
  furred: { key: 'furred', i18nKey: 'anatomy.species_surface.furred', fallback: 'Downy Fur' },
  scaled: { key: 'scaled', i18nKey: 'anatomy.species_surface.scaled', fallback: 'Micro-Scales' },
  feathered: { key: 'feathered', i18nKey: 'anatomy.species_surface.feathered', fallback: 'Downy Plumage' },
  aquatic: { key: 'aquatic', i18nKey: 'anatomy.species_surface.aquatic', fallback: 'Glistening Skin' },
  fever_warm: { key: 'fever_warm', i18nKey: 'anatomy.species_surface.fever_warm', fallback: 'Fever-Warm Skin' },
  porcelain_silky: { key: 'porcelain_silky', i18nKey: 'anatomy.species_surface.porcelain_silky', fallback: 'Porcelain-Silky Skin' },
  bio_synthetic: { key: 'bio_synthetic', i18nKey: 'anatomy.species_surface.bio_synthetic', fallback: 'Bio-Synthetic Skin' },
};

export const STATURE_OPTIONS = [
  { value: 'miniature', i18nKey: 'build.stature.miniature', fallback: 'Miniature', rangeHint: '(Under 140 cm / <4\'7")' },
  { value: 'short', i18nKey: 'build.stature.short', fallback: 'Short', rangeHint: '(~145–158 cm / 4\'9"–5\'2")' },
  { value: 'below_average', i18nKey: 'build.stature.below_average', fallback: 'Below Average', rangeHint: '(~158–168 cm / 5\'2"–5\'6")' },
  { value: 'average', i18nKey: 'build.stature.average', fallback: 'Average', rangeHint: '(~168–178 cm / 5\'6"–5\'10")' },
  { value: 'tall', i18nKey: 'build.stature.tall', fallback: 'Tall', rangeHint: '(~178–190 cm / 5\'10"–6\'3")' },
  { value: 'towering', i18nKey: 'build.stature.towering', fallback: 'Towering', rangeHint: '(193+ cm / 6\'4"+)' },
];

export const PHYSIQUE_OPTIONS = [
  { value: 'Slim', key: 'slim', i18nKey: 'build.physique.slim', fallback: 'Slim' },
  { value: 'Average', key: 'average', i18nKey: 'build.physique.average', fallback: 'Average' },
  { value: 'Athletic', key: 'athletic', i18nKey: 'build.physique.athletic', fallback: 'Athletic' },
  { value: 'Muscular', key: 'muscular', i18nKey: 'build.physique.muscular', fallback: 'Muscular' },
  { value: 'Voluptuous', key: 'voluptuous', i18nKey: 'build.physique.voluptuous', fallback: 'Voluptuous' },
  { value: 'Stocky', key: 'stocky', i18nKey: 'build.physique.stocky', fallback: 'Stocky' },
  { value: 'Chubby', key: 'chubby', i18nKey: 'build.physique.chubby', fallback: 'Chubby' },
];

const MALE_GENDER_TOKEN_RE = /\b(?:male|man|boy|lord|he|him|his|m|masculine|guy|sir|mr)\b/i;
const FEMALE_GENDER_TOKEN_RE = /\b(?:female|woman|girl|lady|she|her|hers|f|fem|feminine|ms|mrs|miss)\b/i;

export const isMaleGender = (gender) => {
  const g = String(gender || '').trim();
  if (!g) return false;
  return MALE_GENDER_TOKEN_RE.test(g) && !FEMALE_GENDER_TOKEN_RE.test(g);
};

export const isFemaleGender = (gender) => {
  const g = String(gender || '').trim();
  if (!g) return false;
  return FEMALE_GENDER_TOKEN_RE.test(g) && !MALE_GENDER_TOKEN_RE.test(g);
};

export const getAllowedPhysiqueOptions = (gender, _stature = '', race = '') => {
  const male = isMaleGender(gender);
  const fem = isFemaleGender(gender);
  const isBunian = String(race || '').toLowerCase().includes('bunian');
  return PHYSIQUE_OPTIONS.filter((opt) => {
    if (male && opt.value === 'Voluptuous') return false;
    if (fem && opt.value === 'Muscular') return false;
    if (isBunian && (opt.value === 'Stocky' || opt.value === 'Chubby')) return false;
    return true;
  });
};

export const healPhysiqueForSelection = (physique, gender, _stature = '', race = '') => {
  if (!physique) return '';
  const male = isMaleGender(gender);
  const fem = isFemaleGender(gender);
  const isBunian = String(race || '').toLowerCase().includes('bunian');
  const low = String(physique).trim().toLowerCase();
  let mapped = physique;
  if (['petite', 'slender', 'petite & soft', 'hourglass & slender', 'slender & lanky'].includes(low)) {
    mapped = 'Slim';
  } else if (['curvy', 'soft & curved', 'hourglass', 'shapely'].includes(low)) {
    mapped = male ? 'Average' : 'Voluptuous';
  }
  if (mapped === 'Voluptuous' && male) {
    mapped = 'Average';
  }
  if (mapped === 'Muscular' && fem) {
    mapped = 'Athletic';
  }
  if (isBunian && (mapped === 'Stocky' || mapped === 'Chubby')) {
    return 'Slim';
  }
  return mapped;
};

const pickWeighted = (weightMap) => {
  const entries = Object.entries(weightMap).filter(([, w]) => w > 0);
  const total = entries.reduce((sum, [, w]) => sum + w, 0);
  if (total <= 0) return entries[0]?.[0] || '';
  let roll = Math.random() * total;
  for (const [key, w] of entries) {
    roll -= w;
    if (roll <= 0) return key;
  }
  return entries[0][0];
};

export const rollClientBuild = (race = '', gender = '') => {
  const r = String(race || 'human').trim().toLowerCase();
  const male = isMaleGender(gender);
  const fem = isFemaleGender(gender);

  const pickBracket = (maleW, femW) => {
    if (male) return maleW;
    if (fem) return femW;
    const mid = {};
    const keys = new Set([...Object.keys(maleW), ...Object.keys(femW)]);
    for (const k of keys) {
      mid[k] = ((maleW[k] || 0) + (femW[k] || 0)) / 2;
    }
    return mid;
  };

  let statureWeights;
  if (['dwarf', 'gnome', 'halfling', 'goblin', 'kobold', 'pixie', 'fairy'].some((k) => r.includes(k))) {
    statureWeights = { miniature: 1.0 };
  } else if (r.includes('half') || r.includes('hybrid') || r.includes('cheetah')) {
    statureWeights = pickBracket(
      { short: 0.05, below_average: 0.15, average: 0.5, tall: 0.25, towering: 0.05 },
      { short: 0.1, below_average: 0.34, average: 0.45, tall: 0.1, towering: 0.01 },
    );
  } else if (['rabbit', 'bunny', 'mouse', 'rat', 'hamster', 'squirrel', 'hedgehog'].some((k) => r.includes(k))) {
    statureWeights = pickBracket(
      { short: 0.34, below_average: 0.45, average: 0.15, tall: 0.05, towering: 0.01 },
      { short: 0.55, below_average: 0.35, average: 0.07, tall: 0.02, towering: 0.01 },
    );
  } else if (['cat', 'neko', 'fox', 'kitsune', 'fennec', 'ferret', 'weasel'].some((k) => r.includes(k))) {
    statureWeights = pickBracket(
      { short: 0.1, below_average: 0.3, average: 0.43, tall: 0.15, towering: 0.02 },
      { short: 0.15, below_average: 0.45, average: 0.34, tall: 0.05, towering: 0.01 },
    );
  } else if (['elf', 'drow', 'angel', 'bunian'].some((k) => r.includes(k))) {
    statureWeights = pickBracket(
      { short: 0.02, below_average: 0.08, average: 0.4, tall: 0.38, towering: 0.12 },
      { short: 0.04, below_average: 0.16, average: 0.45, tall: 0.28, towering: 0.07 },
    );
  } else if (
    ['wolf', 'tiger', 'lion', 'bear', 'dragon', 'orc', 'minotaur', 'rhino', 'elephant', 'boar', 'bovine'].some((k) => r.includes(k))
    || /(?:\boni\b|\bgiant\b|\btroll\b|\bogre\b|\box(?:en)?\b)/.test(r)
  ) {
    statureWeights = pickBracket(
      { short: 0.01, below_average: 0.04, average: 0.25, tall: 0.45, towering: 0.25 },
      { short: 0.01, below_average: 0.14, average: 0.55, tall: 0.2, towering: 0.1 },
    );
  } else {
    statureWeights = pickBracket(
      { short: 0.05, below_average: 0.15, average: 0.5, tall: 0.25, towering: 0.05 },
      { short: 0.1, below_average: 0.34, average: 0.45, tall: 0.1, towering: 0.01 },
    );
  }

  const stature = pickWeighted(statureWeights) || 'average';

  let allowed = getAllowedPhysiqueOptions(gender, stature, r).map((o) => o.value);
  if (allowed.length === 0) allowed = ['Average'];

  const baseWeights = male
    ? { Average: 1.1, Athletic: 1.0, Slim: 0.85, Muscular: 0.85, Stocky: 0.45, Chubby: 0.15 }
    : fem
      ? { Slim: 1.4, Average: 1.25, Athletic: 1.0, Voluptuous: 0.95, Stocky: 0.25, Chubby: 0.15 }
      : { Average: 1.0, Slim: 1.0, Athletic: 0.95, Muscular: 0.6, Voluptuous: 0.6, Stocky: 0.35, Chubby: 0.15 };

  const pWeights = {};
  for (const p of allowed) {
    pWeights[p] = baseWeights[p] ?? 0.5;
  }

  if (['miniature', 'short', 'below_average'].includes(stature)) {
    if ('Slim' in pWeights) pWeights.Slim *= 1.6;
    if ('Stocky' in pWeights) pWeights.Stocky *= 1.3;
    if ('Voluptuous' in pWeights) pWeights.Voluptuous *= 1.1;
  } else if (['tall', 'towering'].includes(stature)) {
    if ('Slim' in pWeights) pWeights.Slim *= 1.5;
    if ('Athletic' in pWeights) pWeights.Athletic *= 1.4;
    if ('Muscular' in pWeights) pWeights.Muscular *= 1.4;
    if ('Voluptuous' in pWeights) pWeights.Voluptuous *= 1.2;
  }

  if (r.includes('bunian')) {
    if ('Slim' in pWeights) pWeights.Slim *= 2.0;
    if ('Athletic' in pWeights) pWeights.Athletic *= 1.4;
    if ('Voluptuous' in pWeights) pWeights.Voluptuous *= 1.1;
  } else if (['elf', 'dark_elf', 'drow'].some((k) => r.includes(k))) {
    if ('Slim' in pWeights) pWeights.Slim *= 2.0;
    if ('Athletic' in pWeights) pWeights.Athletic *= 1.4;
  }

  if (r.includes('dwarf')) {
    if ('Stocky' in pWeights) pWeights.Stocky *= 2.8;
    if ('Muscular' in pWeights) pWeights.Muscular *= 1.8;
    if (fem && 'Athletic' in pWeights) pWeights.Athletic *= 1.4;
    if ('Voluptuous' in pWeights) pWeights.Voluptuous *= 1.15;
    if ('Slim' in pWeights) pWeights.Slim *= 0.6;
  }

  const isSmallBeast = [
    'cat', 'neko', 'fox', 'kitsune', 'fennec', 'rabbit', 'bunny',
    'mouse', 'rat', 'hamster', 'squirrel', 'hedgehog', 'ferret', 'weasel',
  ].some((k) => r.includes(k));
  const isLargeBeast = !isSmallBeast && (
    ['wolf', 'tiger', 'lion', 'bear', 'dragon', 'orc', 'minotaur', 'rhino', 'elephant', 'boar', 'bovine'].some((k) => r.includes(k))
    || /(?:\boni\b|\bgiant\b|\btroll\b|\bogre\b|\box(?:en)?\b)/.test(r)
  );

  if (isLargeBeast) {
    if ('Athletic' in pWeights) pWeights.Athletic *= fem ? 1.8 : 1.5;
    if ('Muscular' in pWeights) pWeights.Muscular *= 1.8;
    if ('Stocky' in pWeights) pWeights.Stocky *= 1.4;
    if ('Voluptuous' in pWeights) pWeights.Voluptuous *= 1.3;
    if ('Slim' in pWeights) pWeights.Slim *= 0.65;
  } else if (isSmallBeast) {
    if ('Slim' in pWeights) pWeights.Slim *= 2.0;
    if ('Voluptuous' in pWeights) pWeights.Voluptuous *= 1.1;
    if ('Muscular' in pWeights) pWeights.Muscular *= 0.5;
    if ('Stocky' in pWeights) pWeights.Stocky *= 0.5;
  }

  const physique = pickWeighted(pWeights) || allowed[0] || 'Average';
  return { stature, physique };
};

export const classifyAssetSizeTierClient = (sizeStr, isMale = false) => {
  const s = String(sizeStr || '').trim().toLowerCase();
  if (!s) return 'average';
  if (isMale) {
    const inchMatch = s.match(/(\d+(?:\.\d+)?)\s*(?:"|inch)/i);
    if (inchMatch) {
      const val = Number.parseFloat(inchMatch[1]);
      if (!Number.isNaN(val)) {
        if (val < 4.5) return val >= 3.5 ? 'small' : 'flat';
        if (val < 6.0) return 'average';
        if (val < 8.0) return 'large';
        return 'huge';
      }
    }
    if (['tiny', 'micro', 'very small', 'puny', 'barely'].some((w) => s.includes(w))) return 'flat';
    if (['small', 'modest', 'compact', 'petite', 'below average', 'slender & ultra-sensitive'].some((w) => s.includes(w))) return 'small';
    if (['huge', 'massive', 'enormous', 'gigantic', 'hyper', 'colossal', 'dense & formidable'].some((w) => s.includes(w))) return 'huge';
    if (['large', 'thick', 'above average', 'heavy', 'big', 'generous', 'formidable'].some((w) => s.includes(w))) return 'large';
    return 'average';
  }
  if (/\b(aa|aaa)(?:\+)?-cup\b/i.test(s) || ['almost flat', 'barely there'].some((w) => s.includes(w))) return 'flat';
  if (/\b([e-h]+(?:\+)?-cup)\b/i.test(s) || ['huge', 'massive', 'hyper', 'bountiful e', 'bountiful', 'gigantic'].some((w) => s.includes(w))) return 'huge';
  if (/\b(d{1,3}(?:\+)?-cup)\b/i.test(s) || ['voluptuous d', 'generous dd', 'full d', 'heavy d', 'busty', 'stacked', 'voluptuous'].some((w) => s.includes(w))) return 'large';
  if (/\b(c(?:\+)?-cup)\b/i.test(s) || ['shapely c', 'full c', 'toned c', 'proportional', 'moderate'].some((w) => s.includes(w))) return 'average';
  if (/\b([ab](?:\+)?-cup)\b/i.test(s) || ['modest b', 'perky b', 'soft a'].some((w) => s.includes(w))) return 'small';
  if (['flat', 'tiny', 'barely'].some((w) => s.includes(w))) return 'flat';
  if (['large', 'heavy'].some((w) => s.includes(w))) return 'large';
  if (['small', 'petite', 'modest', 'perky', 'slender'].some((w) => s.includes(w))) return 'small';
  return 'average';
};

export const normalizeAssetTextureClient = (raw, isMale = false) => {
  if (!raw || typeof raw !== 'string') return '';
  const clean = raw.replace(/\s+/g, ' ').trim();
  const low = clean.toLowerCase();
  if (!low || ['unknown', 'none', 'null', 'n/a', 'auto', '__auto__'].includes(low)) return '';

  const list = isMale ? MALE_TEXTURE_OPTIONS : FEMALE_TEXTURE_OPTIONS;
  const exact = list.find((o) => o.value.toLowerCase() === low);
  if (exact) return exact.value;

  const legMap = isMale ? LEGACY_MALE_TEXTURE_MAP : LEGACY_FEMALE_TEXTURE_MAP;
  if (legMap[low]) return legMap[low];

  if (isMale) {
    if (low.includes('veined') || low.includes('throbbing')) return 'Veined';
    if (low.includes('curved') || low.includes('angled')) return 'Curved';
    if (low.includes('tapered') || low.includes('slender')) return 'Tapered';
    if (low.includes('heavy')) return 'Heavy';
    if (['thick', 'dense', 'formidable', 'sturdy', 'girthy'].some((k) => low.includes(k))) return 'Thick';
    if (['firm', 'toned', 'compact', 'athletic', 'resilient'].some((k) => low.includes(k))) return 'Firm';
    if (['sensitive', 'responsive', 'pulsing', 'trembling'].some((k) => low.includes(k))) return 'Sensitive';
    if (['smooth', 'silky', 'glistening', 'velvety', 'supple', 'soft', 'warm', 'fur', 'scale', 'feather', 'plumage'].some((k) => low.includes(k))) return 'Smooth';
  } else {
    if (['perky', 'high-set', 'high set', 'buoyant'].some((k) => low.includes(k))) return 'Perky';
    if (['pillowy', 'yielding'].some((k) => low.includes(k))) return 'Pillowy';
    if (low.includes('plush') || low.includes('heavy')) return 'Plush';
    if (low.includes('bouncy')) return 'Bouncy';
    if (low.includes('teardrop')) return 'Teardrop';
    if (['delicate', 'tender'].some((k) => low.includes(k))) return 'Delicate';
    if (['firm', 'toned', 'compact', 'athletic', 'resilient', 'dense'].some((k) => low.includes(k))) return 'Firm';
    if (['sensitive', 'responsive', 'pulsing', 'trembling'].some((k) => low.includes(k))) return 'Sensitive';
    if (['smooth', 'silky', 'glistening', 'velvety', 'supple', 'soft', 'warm', 'fur', 'scale', 'feather', 'plumage'].some((k) => low.includes(k))) return 'Supple';
  }
  return '';
};

export const getAllowedTextureOptions = (isMale = false, sizeTier = 'average') => {
  const tier = String(sizeTier || 'average').trim().toLowerCase();
  if (isMale) {
    return MALE_TEXTURE_OPTIONS.filter((opt) => {
      if ((tier === 'flat' || tier === 'small') && (opt.value === 'Heavy' || opt.value === 'Thick')) return false;
      if (tier === 'huge' && opt.value === 'Tapered') return false;
      return true;
    });
  }
  return FEMALE_TEXTURE_OPTIONS.filter((opt) => {
    if (tier === 'flat' && ['Plush', 'Pillowy', 'Bouncy', 'Teardrop'].includes(opt.value)) return false;
    if (tier === 'small' && ['Plush', 'Pillowy', 'Bouncy'].includes(opt.value)) return false;
    if ((tier === 'large' || tier === 'huge') && opt.value === 'Delicate') return false;
    return true;
  });
};

export const healTextureForSelection = (texture, isMale = false, sizeTier = 'average') => {
  if (!texture) return '';
  const tier = String(sizeTier || 'average').trim().toLowerCase();
  const norm = normalizeAssetTextureClient(texture, isMale);
  if (!norm) return '';
  if (isMale) {
    if (tier === 'flat' || tier === 'small') {
      if (norm === 'Heavy') return 'Firm';
      if (norm === 'Thick') return 'Smooth';
    } else if (tier === 'huge' && norm === 'Tapered') {
      return 'Thick';
    }
    return norm;
  }
  if (tier === 'flat') {
    if (['Plush', 'Pillowy', 'Teardrop'].includes(norm)) return 'Supple';
    if (norm === 'Bouncy') return 'Perky';
  } else if (tier === 'small') {
    if (['Plush', 'Pillowy'].includes(norm)) return 'Supple';
    if (norm === 'Bouncy') return 'Perky';
  } else if ((tier === 'large' || tier === 'huge') && norm === 'Delicate') {
    return 'Supple';
  }
  return norm;
};

export const getSpeciesSurfaceClient = (race = '', skinType = '') => {
  const r = String(race || '').trim().toLowerCase();
  const st = String(skinType || '').trim().toLowerCase();
  if (r === 'kitsune:myobu_fox' || r.includes('half') || r.includes('hybrid')) return null;
  if (['cyborg', 'android', 'synth'].some((k) => r.includes(k)) || st === 'synthetic') {
    return SPECIES_SURFACE_CONFIG.bio_synthetic;
  }
  if (['angel', 'elf', 'dark_elf', 'drow', 'orang_bunian', 'bunian'].some((k) => r.includes(k))) {
    return SPECIES_SURFACE_CONFIG.porcelain_silky;
  }
  if (['demon', 'tiefling', 'oni', 'succubus', 'incubus'].some((k) => r.includes(k))) {
    return SPECIES_SURFACE_CONFIG.fever_warm;
  }
  if (['dragon', 'dragonkin', 'reptile', 'snake', 'lizard', 'serpentine', 'scaly'].some((k) => r.includes(k)) || st === 'scaly') {
    return SPECIES_SURFACE_CONFIG.scaled;
  }
  if (['avian', 'bird', 'harpy', 'feathered'].some((k) => r.includes(k)) || st === 'feathered') {
    return SPECIES_SURFACE_CONFIG.feathered;
  }
  if (['aquatic', 'merfolk', 'siren', 'fish'].some((k) => r.includes(k))) {
    return SPECIES_SURFACE_CONFIG.aquatic;
  }
  if (
    st !== 'skin' &&
    ([
      'beastfolk', 'fox', 'cat', 'neko', 'kitsune', 'wolf', 'rabbit', 'bunny',
      'tiger', 'lion', 'bear', 'mouse', 'rat', 'hamster', 'squirrel',
      'hedgehog', 'ferret', 'weasel', 'fennec', 'cheetah', 'minotaur', 'boar', 'bovine',
    ].some((k) => r.includes(k)) || st === 'furry')
  ) {
    return SPECIES_SURFACE_CONFIG.furred;
  }
  return null;
};

export const rollClientAssetTexture = (isMale = false, sizeTier = 'average', race = '', physique = '') => {
  const allowed = getAllowedTextureOptions(isMale, sizeTier).map((o) => o.value);
  if (allowed.length === 0) return isMale ? 'Firm' : 'Supple';

  const tier = String(sizeTier || 'average').trim().toLowerCase();
  const weights = {};
  for (const item of allowed) weights[item] = 1.0;

  if (isMale) {
    if (tier === 'flat' || tier === 'small') {
      if ('Firm' in weights) weights.Firm *= 1.4;
      if ('Smooth' in weights) weights.Smooth *= 1.5;
      if ('Sensitive' in weights) weights.Sensitive *= 1.5;
      if ('Tapered' in weights) weights.Tapered *= 1.4;
    } else if (tier === 'large' || tier === 'huge') {
      if ('Thick' in weights) weights.Thick *= 1.6;
      if ('Heavy' in weights) weights.Heavy *= 1.5;
      if ('Veined' in weights) weights.Veined *= 1.5;
      if ('Curved' in weights) weights.Curved *= 1.3;
      if (tier === 'large' && 'Tapered' in weights) weights.Tapered *= 0.5;
    }
  } else {
    if (tier === 'flat' || tier === 'small') {
      if ('Perky' in weights) weights.Perky *= 1.6;
      if ('Delicate' in weights) weights.Delicate *= 1.5;
      if ('Firm' in weights) weights.Firm *= 1.3;
      if ('Sensitive' in weights) weights.Sensitive *= 1.3;
    } else if (tier === 'large' || tier === 'huge') {
      if ('Pillowy' in weights) weights.Pillowy *= 1.6;
      if ('Plush' in weights) weights.Plush *= 1.6;
      if ('Bouncy' in weights) weights.Bouncy *= 1.5;
      if ('Teardrop' in weights) weights.Teardrop *= 1.3;
      if ('Perky' in weights) weights.Perky *= tier === 'huge' ? 0.35 : 0.6;
    }
  }

  const p = String(physique || '').trim().toLowerCase();
  if (['athletic', 'muscular', 'toned', 'fit'].some((k) => p.includes(k))) {
    if ('Firm' in weights) weights.Firm *= 1.6;
    if ('Perky' in weights) weights.Perky *= 1.3;
    if ('Veined' in weights) weights.Veined *= 1.5;
  } else if (['voluptuous', 'chubby', 'overweight', 'plump'].some((k) => p.includes(k))) {
    if ('Pillowy' in weights) weights.Pillowy *= 1.6;
    if ('Plush' in weights) weights.Plush *= 1.6;
    if ('Bouncy' in weights) weights.Bouncy *= 1.3;
    if ('Heavy' in weights) weights.Heavy *= 1.5;
    if ('Thick' in weights) weights.Thick *= 1.5;
  } else if (['slim', 'petite', 'slender', 'thin', 'lean'].some((k) => p.includes(k))) {
    if ('Delicate' in weights) weights.Delicate *= 1.5;
    if ('Perky' in weights) weights.Perky *= 1.4;
    if ('Sensitive' in weights) weights.Sensitive *= 1.3;
    if ('Tapered' in weights) weights.Tapered *= 1.4;
    if ('Smooth' in weights) weights.Smooth *= 1.3;
  } else if (p.includes('curvy')) {
    if ('Supple' in weights) weights.Supple *= 1.4;
    if ('Teardrop' in weights) weights.Teardrop *= 1.4;
    if ('Plush' in weights) weights.Plush *= 1.3;
    if ('Bouncy' in weights) weights.Bouncy *= 1.3;
  } else if (p.includes('stocky')) {
    if ('Firm' in weights) weights.Firm *= 1.3;
    if ('Plush' in weights) weights.Plush *= 1.3;
    if ('Thick' in weights) weights.Thick *= 1.5;
    if ('Heavy' in weights) weights.Heavy *= 1.4;
  }

  const r = String(race || '').trim().toLowerCase();
  const surf = getSpeciesSurfaceClient(r)?.key || 'natural';
  const isSmallBeast = ['cat', 'neko', 'fox', 'kitsune', 'fennec', 'rabbit', 'bunny', 'mouse', 'rat', 'hamster', 'squirrel', 'hedgehog', 'ferret', 'weasel'].some((k) => r.includes(k));
  const isLargeRace = !isSmallBeast && (['wolf', 'tiger', 'lion', 'bear', 'dragon', 'orc', 'minotaur', 'rhino', 'elephant', 'boar', 'bovine', 'dwarf'].some((k) => r.includes(k)) || /\box(en)?\b/.test(r));

  if (surf === 'porcelain_silky' || isSmallBeast) {
    ['Perky', 'Supple', 'Delicate', 'Sensitive', 'Smooth', 'Tapered'].forEach((k) => {
      if (k in weights) weights[k] *= 1.25;
    });
  } else if (surf === 'scaled' || isLargeRace) {
    ['Firm', 'Plush', 'Thick', 'Heavy', 'Veined'].forEach((k) => {
      if (k in weights) weights[k] *= 1.25;
    });
  } else if (surf === 'fever_warm') {
    ['Sensitive', 'Supple', 'Plush', 'Veined', 'Curved', 'Heavy'].forEach((k) => {
      if (k in weights) weights[k] *= 1.25;
    });
  } else if (surf === 'bio_synthetic') {
    ['Firm', 'Perky', 'Smooth', 'Supple'].forEach((k) => {
      if (k in weights) weights[k] *= 1.3;
    });
  }

  return pickWeighted(weights) || allowed[0];
};

export const stripTextureFromSizeClient = (sizeStr, isMale = false) => {
  let s = String(sizeStr || '').replace(/^\((.*?)\)$/, '$1').trim();
  if (!s) return '';
  s = s.replace(/\s*\([^()]+\)\s*$/, '').trim();
  const legKeys = Object.keys(isMale ? LEGACY_MALE_TEXTURE_MAP : LEGACY_FEMALE_TEXTURE_MAP).sort((a, b) => b.length - a.length);
  const canonSet = new Set((isMale ? MALE_TEXTURE_OPTIONS : FEMALE_TEXTURE_OPTIONS).map((o) => o.value.toLowerCase()));
  let changed = true;
  while (changed && s) {
    changed = false;
    const sLow = s.toLowerCase();
    for (const leg of legKeys) {
      if (sLow === leg) return '';
      if (sLow.startsWith(`${leg} `)) {
        s = s.slice(leg.length).replace(/^[\s,-]+/, '').trim();
        changed = true;
        break;
      }
    }
    if (changed) continue;
    const firstSpace = s.indexOf(' ');
    if (firstSpace > 0) {
      const firstWord = s.slice(0, firstSpace).replace(/[,-]+$/, '').toLowerCase();
      if (canonSet.has(firstWord)) {
        s = s.slice(firstSpace + 1).trim();
        changed = true;
      }
    }
  }
  return s;
};

export const formatAssetTexture = (rawTex, isMale = false, t = null) => {
  const clean = String(rawTex || '').trim();
  if (!clean) return '';
  const norm = normalizeAssetTextureClient(clean, isMale);
  const cfg = norm ? TEXTURE_LABEL_CONFIG[norm.toLowerCase()] : null;
  if (cfg) {
    return typeof t === 'function' ? t(cfg.i18nKey, cfg.fallback) : cfg.fallback;
  }
  return clean;
};

export const REAR_SIZE_OPTIONS = [
  { value: 'flat', label: 'Flat', i18nKey: 'anatomy.rear_sizes.flat', selectKey: 'character.rear_flat', selectFallback: 'Flat (Sleek / Minimal)' },
  { value: 'small', label: 'Compact', i18nKey: 'anatomy.rear_sizes.small', selectKey: 'character.rear_small', selectFallback: 'Compact (Trim / Petite)' },
  { value: 'average', label: 'Shapely', i18nKey: 'anatomy.rear_sizes.average', selectKey: 'character.rear_average', selectFallback: 'Shapely (Balanced / Natural)' },
  { value: 'large', label: 'Plump', i18nKey: 'anatomy.rear_sizes.large', selectKey: 'character.rear_large', selectFallback: 'Plump (Curvy / Full)' },
  { value: 'huge', label: 'Bountiful', i18nKey: 'anatomy.rear_sizes.huge', selectKey: 'character.rear_huge', selectFallback: 'Bountiful (Wide / Voluptuous)' },
];

export const REAR_TEXTURE_OPTIONS = [
  { value: 'Firm', label: 'Firm', i18nKey: 'anatomy.rear_textures.firm' },
  { value: 'Taut', label: 'Taut', i18nKey: 'anatomy.rear_textures.taut' },
  { value: 'Supple', label: 'Supple', i18nKey: 'anatomy.rear_textures.supple' },
  { value: 'Rounded', label: 'Rounded', i18nKey: 'anatomy.rear_textures.rounded' },
  { value: 'Plush', label: 'Plush', i18nKey: 'anatomy.rear_textures.plush' },
  { value: 'Jiggly', label: 'Jiggly', i18nKey: 'anatomy.rear_textures.jiggly' },
];

export const HEIGHT_PREFERENCE_KEYS = ['taller_partner', 'shorter_partner'];
export const BODY_PREFERENCE_KEYS = [
  'smaller_bb',
  'bigger_bb',
  'smaller_ass',
  'bigger_ass',
  'taller_partner',
  'shorter_partner',
];

const REAR_TEXTURE_SYNONYMS_CLIENT = {
  firm: 'Firm',
  sculpted: 'Firm',
  toned: 'Taut',
  tight: 'Taut',
  taut: 'Taut',
  athletic: 'Firm',
  supple: 'Supple',
  soft: 'Supple',
  smooth: 'Supple',
  warm: 'Supple',
  velvety: 'Supple',
  silky: 'Supple',
  rounded: 'Rounded',
  round: 'Rounded',
  curvy: 'Rounded',
  full: 'Rounded',
  peach: 'Rounded',
  plush: 'Plush',
  pillowy: 'Plush',
  cushiony: 'Plush',
  heavy: 'Plush',
  jiggly: 'Jiggly',
  bouncy: 'Jiggly',
  wobbly: 'Jiggly',
  yielding: 'Plush',
};

const REAR_PREF_FALLBACKS = {
  smaller_bb: 'Smaller Breasts',
  bigger_bb: 'Bigger Breasts',
  smaller_ass: 'Smaller Rear',
  bigger_ass: 'Bigger Rear',
  taller_partner: 'Taller Partners',
  shorter_partner: 'Shorter Partners',
};

export const normalizeRearTextureClient = (raw) => {
  const clean = String(raw || '').trim();
  if (!clean) return '';
  const low = clean.toLowerCase().replace(/[\s-]+/g, '_');
  if (REAR_TEXTURE_SYNONYMS_CLIENT[low]) return REAR_TEXTURE_SYNONYMS_CLIENT[low];
  const exact = REAR_TEXTURE_OPTIONS.find((o) => o.value.toLowerCase() === clean.toLowerCase());
  return exact ? exact.value : '';
};

const REAR_SIZE_CANON_LABELS = {
  flat: 'Flat',
  small: 'Compact',
  average: 'Shapely',
  large: 'Plump',
  huge: 'Bountiful',
};

export const stripRearTextureFromSizeClient = (sizeStr) => {
  let s = String(sizeStr || '').replace(/^\((.*?)\)$/, '$1').trim();
  if (!s) return '';
  s = s.replace(/\s*\([^()]+\)\s*$/, '').trim();
  const sizeLabelTokens = new Set(Object.values(REAR_SIZE_CANON_LABELS).map((l) => l.toLowerCase()));
  const texTokens = new Set([
    ...REAR_TEXTURE_OPTIONS.map((o) => o.value.toLowerCase()),
    ...Object.keys(REAR_TEXTURE_SYNONYMS_CLIENT),
  ]);
  sizeLabelTokens.forEach((tok) => texTokens.delete(tok));
  const noiseTokens = new Set(['rear', 'ass', 'butt', 'hips']);
  const parts = s.split(/\s+/).map((p) => p.replace(/^[, -]+|[,-]+$/g, '')).filter(Boolean);
  const remaining = parts.filter((p) => {
    const low = p.toLowerCase();
    const norm = low.replace(/-/g, '_');
    return !texTokens.has(low) && !texTokens.has(norm) && !noiseTokens.has(low);
  });
  return remaining.join(' ').trim();
};

export const classifyRearSizeTierClient = (sizeStr) => {
  const s = String(sizeStr || '').trim();
  if (!s || ['none', 'unknown', 'null', 'n/a', 'auto', '__auto__'].includes(s.toLowerCase())) {
    return 'average';
  }
  const bare = stripRearTextureFromSizeClient(s).toLowerCase();
  if (!bare) return 'average';
  if (['flat', 'tiny', 'slight', 'barely'].some((k) => bare.includes(k))) return 'flat';
  if (['compact', 'small', 'modest'].some((k) => bare.includes(k))) return 'small';
  if (['bountiful', 'huge', 'massive', 'enormous', 'gigantic', 'colossal', 'voluptuous'].some((k) => bare.includes(k))) return 'huge';
  if (['plump', 'large', 'generous', 'thick', 'wide', 'full', 'heavy', 'curvy'].some((k) => bare.includes(k))) return 'large';
  if (['shapely', 'average', 'medium', 'moderate', 'balanced'].some((k) => bare.includes(k))) return 'average';
  return 'average';
};

export const getAllowedRearTextureOptions = (sizeTier = 'average') => {
  const tier = String(sizeTier || 'average').trim().toLowerCase();
  const excluded = new Set();
  if (tier === 'flat' || tier === 'small') {
    excluded.add('Plush');
    excluded.add('Jiggly');
  } else if (tier === 'large' || tier === 'huge') {
    excluded.add('Taut');
  }
  return REAR_TEXTURE_OPTIONS.filter((o) => !excluded.has(o.value));
};

export const healRearTextureForSelection = (texture, sizeTier = 'average') => {
  if (!texture) return '';
  const tier = String(sizeTier || 'average').trim().toLowerCase();
  const norm = normalizeRearTextureClient(texture);
  if (!norm) return '';
  if ((tier === 'flat' || tier === 'small') && (norm === 'Plush' || norm === 'Jiggly')) {
    return 'Supple';
  }
  if ((tier === 'large' || tier === 'huge') && norm === 'Taut') {
    return 'Firm';
  }
  return norm;
};

export const rollClientRearTexture = (sizeTier = 'average', race = '', physique = '') => {
  const allowed = getAllowedRearTextureOptions(sizeTier).map((o) => o.value);
  if (allowed.length === 0) return 'Supple';

  const tier = String(sizeTier || 'average').trim().toLowerCase();
  const weights = {};
  for (const item of allowed) weights[item] = 1.0;

  if (tier === 'flat' || tier === 'small') {
    if ('Taut' in weights) weights.Taut *= 1.6;
    if ('Firm' in weights) weights.Firm *= 1.5;
    if ('Supple' in weights) weights.Supple *= 1.3;
  } else if (tier === 'large' || tier === 'huge') {
    if ('Plush' in weights) weights.Plush *= 1.6;
    if ('Jiggly' in weights) weights.Jiggly *= 1.6;
    if ('Rounded' in weights) weights.Rounded *= 1.4;
  } else {
    if ('Rounded' in weights) weights.Rounded *= 1.3;
    if ('Supple' in weights) weights.Supple *= 1.3;
  }

  const p = String(physique || '').trim().toLowerCase();
  if (['athletic', 'muscular', 'toned', 'fit'].some((k) => p.includes(k))) {
    if ('Firm' in weights) weights.Firm *= 1.6;
    if ('Taut' in weights) weights.Taut *= 1.5;
  } else if (['voluptuous', 'chubby', 'overweight', 'plump'].some((k) => p.includes(k))) {
    if ('Plush' in weights) weights.Plush *= 1.6;
    if ('Jiggly' in weights) weights.Jiggly *= 1.5;
    if ('Rounded' in weights) weights.Rounded *= 1.3;
  } else if (['slim', 'petite', 'slender', 'thin', 'lean'].some((k) => p.includes(k))) {
    if ('Taut' in weights) weights.Taut *= 1.4;
    if ('Firm' in weights) weights.Firm *= 1.3;
    if ('Supple' in weights) weights.Supple *= 1.3;
  } else if (p.includes('curvy')) {
    if ('Rounded' in weights) weights.Rounded *= 1.5;
    if ('Supple' in weights) weights.Supple *= 1.4;
    if ('Plush' in weights) weights.Plush *= 1.3;
  }

  const r = String(race || '').trim().toLowerCase();
  const surf = getSpeciesSurfaceClient(r)?.key || 'natural';
  if (surf === 'porcelain_silky' || surf === 'bio_synthetic') {
    ['Firm', 'Taut', 'Supple'].forEach((k) => {
      if (k in weights) weights[k] *= 1.25;
    });
  } else if (surf === 'fever_warm') {
    ['Plush', 'Supple', 'Jiggly'].forEach((k) => {
      if (k in weights) weights[k] *= 1.25;
    });
  }

  return pickWeighted(weights) || allowed[0];
};

export const formatRearSizeLabel = (sizeStr, t = null) => {
  const bare = stripRearTextureFromSizeClient(sizeStr);
  if (!bare) return '';
  const tier = classifyRearSizeTierClient(bare);
  const opt = REAR_SIZE_OPTIONS.find((o) => o.value === tier);
  if (opt) {
    return typeof t === 'function' ? t(opt.i18nKey, opt.label) : opt.label;
  }
  return bare;
};

export const formatRearTexture = (rawTex, t = null) => {
  const clean = String(rawTex || '').trim();
  if (!clean) return '';
  const norm = normalizeRearTextureClient(clean);
  const opt = norm ? REAR_TEXTURE_OPTIONS.find((o) => o.value === norm) : null;
  if (opt) {
    return typeof t === 'function' ? t(opt.i18nKey, opt.label) : opt.label;
  }
  return clean;
};

export const formatFusedRear = (sizeStr, texStr, t = null) => {
  const sizeOnly = formatRearSizeLabel(sizeStr, t);
  if (!sizeOnly) return { label: '', sizeOnly: '', textureOnly: '' };
  const textureOnly = formatRearTexture(texStr, t);
  if (textureOnly && !sizeOnly.toLowerCase().includes(textureOnly.toLowerCase())) {
    return { label: `${textureOnly} ${sizeOnly}`, sizeOnly, textureOnly };
  }
  return { label: sizeOnly, sizeOnly, textureOnly };
};

export const isFeralRearExcluded = (race = '') => {
  const r = String(race || '').trim().toLowerCase();
  return ['kitsune:myobu_fox', 'kitsune_myobu_fox', 'kitsune:fox', 'myobu_fox'].includes(r);
};

export const formatBodyPreferenceLabel = (key, t = null) => {
  const norm = String(key || '').trim().toLowerCase();
  if (!norm) return '';
  const fallback = REAR_PREF_FALLBACKS[norm] || norm.replace(/_/g, ' ');
  return typeof t === 'function' ? t(`contacts.body_prefs.${norm}`, fallback) : fallback;
};
