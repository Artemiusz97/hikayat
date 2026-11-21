// Scenario-aware backdrop registry and time-of-day atmospheric grading.
// Pure ES module with zero React dependencies.

export const IN_GAME_BACKGROUND_IDS = [
  'fantasy',
  'dark_fantasy',
  'isekai_fantasy',
  'sci_fi',
  'cyberpunk',
  'steampunk',
  'high_school_drama',
  'slice_of_life',
  'nuclear_post_apocalypse',
  'anomalous_incursions',
  'anomalous_high_school',
];

export const BACKGROUND_IDS = ['menu', ...IN_GAME_BACKGROUND_IDS];

export const BACKGROUND_URLS = Object.fromEntries(
  BACKGROUND_IDS.map((id) => [id, `/backgrounds/${id}.webp`])
);

const IN_GAME_SET = new Set(IN_GAME_BACKGROUND_IDS);

const normalizeTags = (source) => {
  const asList = (v) =>
    Array.isArray(v)
      ? v
      : typeof v === 'string' && v
        ? v.split(/[\s,|]+/)
        : [];
  return asList(source?.scenario_tags)
    .concat(asList(source?.tags))
    .map((x) => String(x).toLowerCase().trim())
    .filter(Boolean);
};

/**
 * Resolve a session or scenario-like object to one of the 12 bundled backdrop IDs.
 * Returns `'menu'` when no scenario source is active.
 */
export function resolveScenarioBackdrop(source) {
  if (!source) return 'menu';

  const rawKey = String(
    source.scenario || source.scenario_key || source.key || ''
  )
    .trim()
    .toLowerCase();

  const baseKey = rawKey.replace(/^(?:nsfw_|gore_|furry_)+/i, '');
  if (baseKey && IN_GAME_SET.has(baseKey)) {
    return baseKey;
  }

  const tags = normalizeTags(source);
  const hay = [
    rawKey,
    ...tags,
    source.scenario_display_name,
    source.display_name,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();

  if (
    hay.includes('anomal') &&
    (hay.includes('school') || hay.includes('campus') || hay.includes('academy'))
  ) {
    return 'anomalous_high_school';
  }
  if (
    hay.includes('anomal') ||
    hay.includes('incursion') ||
    hay.includes('urban_fantasy') ||
    hay.includes('urban fantasy')
  ) {
    return 'anomalous_incursions';
  }
  if (
    hay.includes('apocalyp') ||
    hay.includes('wasteland') ||
    hay.includes('nuclear') ||
    hay.includes('fallout') ||
    hay.includes('post_apocalypse') ||
    hay.includes('post-apocalypse')
  ) {
    return 'nuclear_post_apocalypse';
  }
  if (
    hay.includes('cyber') ||
    hay.includes('neon') ||
    hay.includes('chrome')
  ) {
    return 'cyberpunk';
  }
  if (
    hay.includes('sci_fi') ||
    hay.includes('sci-fi') ||
    hay.includes('space') ||
    hay.includes('outer rim') ||
    hay.includes('star')
  ) {
    return 'sci_fi';
  }
  if (
    hay.includes('steam') ||
    hay.includes('brass') ||
    hay.includes('aether')
  ) {
    return 'steampunk';
  }
  if (
    hay.includes('dark_fantasy') ||
    hay.includes('dark fantasy') ||
    hay.includes('grimdark') ||
    hay.includes('horror') ||
    hay.includes('cursed')
  ) {
    return 'dark_fantasy';
  }
  if (hay.includes('isekai')) {
    return 'isekai_fantasy';
  }
  if (
    hay.includes('high_school') ||
    hay.includes('high school') ||
    hay.includes('school') ||
    hay.includes('academy')
  ) {
    return 'high_school_drama';
  }
  if (
    hay.includes('slice_of_life') ||
    hay.includes('slice of life') ||
    hay.includes('cozy') ||
    hay.includes('cafe') ||
    hay.includes('latte')
  ) {
    return 'slice_of_life';
  }

  return 'fantasy';
}

/**
 * Parse a session clock string (e.g. "Day 1 • 08:00", "7:30 PM", "Dusk")
 * into a coarse time-of-day atmospheric phase.
 */
export function resolveTimeOfDayPhase(formattedTime, currentMinute = null) {
  const text = formattedTime ? String(formattedTime).trim() : '';

  let hour = null;

  if (text) {
    // 12-hour format with AM/PM (check first so "7:30 PM" becomes 19)
    const match12 = text.match(/\b(1[0-2]|0?[1-9]):([0-5]\d)\s*(AM|PM)\b/i);
    if (match12) {
      const rawH = Number(match12[1]);
      const mer = match12[3].toUpperCase();
      hour = mer === 'PM' ? (rawH === 12 ? 12 : rawH + 12) : (rawH === 12 ? 0 : rawH);
    } else {
      // 24-hour format HH:MM
      const match24 = text.match(/\b([01]?\d|2[0-3]):([0-5]\d)\b/);
      if (match24) {
        hour = Number(match24[1]);
      }
    }
  }

  if (
    (hour === null || Number.isNaN(hour)) &&
    currentMinute !== null &&
    currentMinute !== undefined &&
    currentMinute !== ''
  ) {
    const parsedMinute = Number(currentMinute);
    if (Number.isFinite(parsedMinute)) {
      const normalized = ((Math.floor(parsedMinute) % 1440) + 1440) % 1440;
      hour = Math.floor(normalized / 60);
    }
  }

  if (hour !== null && !Number.isNaN(hour)) {
    if (hour >= 5 && hour <= 7) return 'dawn';
    if (hour >= 8 && hour <= 16) return 'day';
    if (hour >= 17 && hour <= 19) return 'dusk';
    return 'night';
  }

  if (!text) return 'neutral';
  const lower = text.toLowerCase();
  if (/\b(dawn|sunrise|early morning)\b/.test(lower)) return 'dawn';
  if (/\b(morning|noon|midday|afternoon|daytime)\b/.test(lower)) return 'day';
  if (/\b(dusk|sunset|evening|twilight)\b/.test(lower)) return 'dusk';
  if (/\b(night|midnight|late night)\b/.test(lower)) return 'night';

  return 'neutral';
}

// Gentle atmospheric overlays (0.10-0.22 opacity) so artwork remains crisp.
export const TIME_OF_DAY_GRADES = {
  dawn: 'linear-gradient(180deg, oklch(0.74 0.11 35 / 0.14) 0%, oklch(0.68 0.08 260 / 0.10) 100%)',
  day: 'linear-gradient(180deg, oklch(0.88 0.04 95 / 0.10) 0%, transparent 65%)',
  dusk: 'linear-gradient(180deg, oklch(0.55 0.14 25 / 0.16) 0%, oklch(0.32 0.11 290 / 0.18) 100%)',
  night: 'linear-gradient(180deg, oklch(0.16 0.05 260 / 0.22) 0%, oklch(0.10 0.04 255 / 0.20) 100%)',
  neutral: 'none',
};
