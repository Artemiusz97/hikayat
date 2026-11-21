const EMPTY_TOKENS = new Set(['', 'unknown', 'none', 'null', 'n/a', 'undefined']);

const cleanDemoValue = (val) => {
  if (val === null || val === undefined) return '';
  const str = String(val).trim();
  return EMPTY_TOKENS.has(str.toLowerCase()) ? '' : str;
};

const pickDemoField = (npc, keys, includeAppearance = false) => {
  if (!npc || typeof npc !== 'object') return '';
  const basic = npc.basic_info && typeof npc.basic_info === 'object' ? npc.basic_info : null;
  const appearance = includeAppearance && npc.appearance && typeof npc.appearance === 'object' ? npc.appearance : null;
  const sources = appearance ? [npc, basic, appearance] : [npc, basic];
  for (const src of sources) {
    if (!src) continue;
    for (const key of keys) {
      const val = cleanDemoValue(src[key]);
      if (val) return val;
    }
  }
  return '';
};

export const formatTitle = (str) => {
  const clean = cleanDemoValue(str);
  if (!clean) return '';
  return clean.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
};

export const formatRace = (str, t) => {
  const raw = cleanDemoValue(str);
  if (!raw) return '';
  const clean = raw.toLowerCase().replace(/-/g, '_');
  if (clean === 'human') {
    return typeof t === 'function' ? t('scene.race_human', 'Human') : 'Human';
  }
  if (clean === 'dark_elf') return 'Dark Elf';
  if (clean === 'irradiated_human') return 'Irradiated Human';
  if (clean === 'orang_bunian') return 'Orang Bunian';
  if (clean === 'kitsune:humanoid') return 'Kitsune (Humanoid)';
  if (clean === 'kitsune:myobu_fox') return 'Kitsune (Spirit Fox)';
  if (clean === 'half_beast' || clean === 'halfbeast') return 'Half-Beast';
  if (clean === 'hybrid') return 'Hybrid';
  if (clean.includes(':')) {
    const [category, species] = clean.split(':', 2);
    const catTitle = formatTitle(category);
    const specTitle = formatTitle(species);
    if (category === 'half_beast' || category === 'halfbeast') return `${specTitle} Half-Beast`;
    if (category === 'hybrid') return `${specTitle} Hybrid`;
    if (category === 'beastfolk') return `${specTitle} Beastfolk`;
    if (category === 'alien') return `${specTitle} Alien`;
    if (category === 'mutant') return `${specTitle} Mutant`;
    return `${specTitle} ${catTitle}`.trim();
  }
  return formatTitle(clean);
};

const AGE_CATEGORY_CONFIG = {
  child: {
    i18nKey: 'scene.age_child',
    fallback: 'Child',
    pillClass: 'bg-sky-950/50 text-sky-300 border-sky-700/45',
  },
  teen: {
    i18nKey: 'scene.age_teen',
    fallback: 'Teen',
    pillClass: 'bg-amber-950/50 text-amber-300 border-amber-700/45',
  },
  young_adult: {
    i18nKey: 'scene.age_young_adult',
    fallback: 'Young Adult',
    pillClass: 'bg-teal-950/50 text-teal-300 border-teal-700/45',
  },
  adult: {
    i18nKey: 'scene.age_adult',
    fallback: 'Adult',
    pillClass: 'bg-indigo-950/50 text-indigo-300 border-indigo-700/45',
  },
  middle_aged: {
    i18nKey: 'scene.age_middle_aged',
    fallback: 'Middle-Aged',
    pillClass: 'bg-violet-950/45 text-violet-300 border-violet-700/45',
  },
  elder: {
    i18nKey: 'scene.age_elder',
    fallback: 'Elder',
    pillClass: 'bg-stone-900/70 text-stone-300 border-stone-600/50',
  },
  senior: {
    i18nKey: 'scene.age_elder',
    fallback: 'Elder',
    pillClass: 'bg-stone-900/70 text-stone-300 border-stone-600/50',
  },
};

export const formatAgeCategory = (rawAgeGroup, t) => {
  const raw = cleanDemoValue(rawAgeGroup);
  if (!raw) return null;
  const clean = raw.toLowerCase().replace(/[-\s]+/g, '_');
  const cfg = AGE_CATEGORY_CONFIG[clean];
  if (cfg) {
    return {
      key: clean === 'senior' ? 'elder' : clean,
      label: typeof t === 'function' ? t(cfg.i18nKey, cfg.fallback) : cfg.fallback,
      pillClass: cfg.pillClass,
    };
  }
  return {
    key: clean,
    label: formatTitle(clean),
    pillClass: 'bg-slate-900/70 text-slate-300 border-slate-700/55',
  };
};

export const formatGender = (rawGender, t) => {
  const raw = cleanDemoValue(rawGender);
  if (!raw) return null;
  const clean = raw.toLowerCase().replace(/[-\s]+/g, '_');
  if (clean === 'female' || clean === 'f' || clean === 'woman' || clean === 'girl') {
    return {
      key: 'female',
      symbol: '♀',
      label: typeof t === 'function' ? t('scene.gender_female', 'Female') : 'Female',
      pillClass: 'bg-rose-950/40 text-rose-200/90 border-rose-800/45',
    };
  }
  if (clean === 'male' || clean === 'm' || clean === 'man' || clean === 'boy') {
    return {
      key: 'male',
      symbol: '♂',
      label: typeof t === 'function' ? t('scene.gender_male', 'Male') : 'Male',
      pillClass: 'bg-sky-950/40 text-sky-200/90 border-sky-800/45',
    };
  }
  if (clean === 'non_binary' || clean === 'nonbinary' || clean === 'nb') {
    return {
      key: 'non_binary',
      symbol: '⚧',
      label: typeof t === 'function' ? t('scene.gender_non_binary', 'Non-Binary') : 'Non-Binary',
      pillClass: 'bg-purple-950/40 text-purple-200/90 border-purple-800/45',
    };
  }
  return {
    key: clean,
    symbol: '',
    label: formatTitle(raw),
    pillClass: 'bg-slate-900/70 text-slate-200 border-slate-700/55',
  };
};

export const resolveNpcDemographics = (npc, t) => {
  if (!npc || typeof npc !== 'object') {
    return { ageCategory: null, genderInfo: null, raceLabel: '', hasAny: false };
  }
  const ageCategory = formatAgeCategory(pickDemoField(npc, ['age_group'], false), t);
  const genderInfo = formatGender(pickDemoField(npc, ['gender'], true), t);
  const raceLabel = formatRace(pickDemoField(npc, ['race'], true), t);
  const hasAny = Boolean(ageCategory || genderInfo || raceLabel);
  return { ageCategory, genderInfo, raceLabel, hasAny };
};
