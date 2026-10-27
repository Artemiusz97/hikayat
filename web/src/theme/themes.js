// Hikayat theme registry.
//
// Plain ES module with zero dependencies so it can be imported both by the
// React app (metadata, scenario resolution) and by `tailwind.config.js`
// (which compiles every theme into `[data-theme="..."]` CSS variable blocks).
//
// Colours are expressed as OKLCH triplets ("L C H") so a whole tonal ramp can
// be generated from a single hue + chroma, and so Tailwind's `/opacity`
// modifiers keep working via `oklch(var(--x) / <alpha-value>)`.

export const SHADES = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950];

// Lightness ladders used to generate ramps (dark scheme orientation).
const NEUTRAL_L = { 50: 0.985, 100: 0.962, 200: 0.918, 300: 0.86, 400: 0.72, 500: 0.585, 600: 0.475, 700: 0.385, 800: 0.295, 900: 0.225, 950: 0.155 };
const NEUTRAL_C = { 50: 0.3, 100: 0.4, 200: 0.55, 300: 0.7, 400: 0.9, 500: 1, 600: 1, 700: 1, 800: 1, 900: 1, 950: 1 };
const ACCENT_L = { 50: 0.985, 100: 0.96, 200: 0.925, 300: 0.88, 400: 0.825, 500: 0.765, 600: 0.665, 700: 0.555, 800: 0.47, 900: 0.405, 950: 0.27 };
const ACCENT_C = { 50: 0.02, 100: 0.05, 200: 0.09, 300: 0.13, 400: 0.155, 500: 0.165, 600: 0.155, 700: 0.135, 800: 0.115, 900: 0.095, 950: 0.065 };

const f = (n) => Number(n.toFixed(4));

/**
 * Theme definitions.
 *  - scheme: 'dark' | 'light' (light schemes invert every tonal ramp so
 *    existing `text-gray-200` / `bg-black/40` classes stay legible).
 *  - neutral: [hue, chroma] used to tint the gray/neutral ramp.
 *  - accent:  [hue, chromaFactor] used to build the amber/accent ramp.
 *  - surface: explicit OKLCH triplets for structural tokens.
 */
export const THEMES = {
  ember: {
    labelKey: 'theme.names.ember', label: 'Ember', emoji: '🔥', scheme: 'dark',
    neutral: [70, 0.012], accent: [78, 1],
    surface: { bg: '0.155 0.008 70', deep: '0.125 0.006 70', panel: '0.19 0.01 70', border: '0.3 0.014 70', accent: '0.77 0.115 80', accentHover: '0.84 0.115 86', ink: '0.1 0.004 70', paper: '0.99 0.004 80', shadow: '0.05 0.01 70' },
    alpha: { panel: 0.9, bg: 1 },
    font: { display: "'Cinzel', serif", sans: "'Inter', system-ui, sans-serif" },
    swatch: ['#1b1712', '#c9a25e', '#2f2a22'],
  },
  nebula: {
    labelKey: 'theme.names.nebula', label: 'Nebula', emoji: '🌌', scheme: 'dark',
    neutral: [275, 0.022], accent: [210, 0.95],
    surface: { bg: '0.145 0.025 278', deep: '0.115 0.022 278', panel: '0.185 0.03 278', border: '0.31 0.045 278', accent: '0.8 0.12 210', accentHover: '0.87 0.1 205', ink: '0.09 0.02 278', paper: '0.99 0.01 240', shadow: '0.05 0.03 278' },
    alpha: { panel: 0.88, bg: 1 },
    font: { display: "'Space Grotesk', 'Inter', sans-serif", sans: "'Inter', system-ui, sans-serif" },
    swatch: ['#121428', '#4fd2f0', '#2a2d52'],
  },
  neon: {
    labelKey: 'theme.names.neon', label: 'Neon', emoji: '🌃', scheme: 'dark',
    neutral: [300, 0.02], accent: [345, 1.35],
    surface: { bg: '0.13 0.02 300', deep: '0.095 0.018 300', panel: '0.17 0.03 300', border: '0.32 0.07 320', accent: '0.72 0.24 345', accentHover: '0.79 0.2 350', ink: '0.07 0.02 300', paper: '0.99 0.01 330', shadow: '0.04 0.04 320' },
    alpha: { panel: 0.88, bg: 1 },
    font: { display: "'Space Grotesk', 'Inter', sans-serif", sans: "'Inter', system-ui, sans-serif" },
    swatch: ['#140c1c', '#ff3fa4', '#00e5ff'],
  },
  brass: {
    labelKey: 'theme.names.brass', label: 'Brass', emoji: '⚙️', scheme: 'dark',
    neutral: [58, 0.02], accent: [55, 1],
    surface: { bg: '0.17 0.015 55', deep: '0.14 0.012 55', panel: '0.21 0.02 55', border: '0.34 0.03 58', accent: '0.71 0.12 55', accentHover: '0.78 0.12 62', ink: '0.11 0.01 55', paper: '0.98 0.015 75', shadow: '0.06 0.02 55' },
    alpha: { panel: 0.92, bg: 1 },
    font: { display: "'Cinzel', serif", sans: "'Inter', system-ui, sans-serif" },
    swatch: ['#231a13', '#c98b4f', '#3d2f22'],
  },
  crimson: {
    labelKey: 'theme.names.crimson', label: 'Crimson', emoji: '🩸', scheme: 'dark',
    neutral: [20, 0.012], accent: [25, 1.15],
    surface: { bg: '0.135 0.012 20', deep: '0.105 0.01 20', panel: '0.175 0.016 20', border: '0.29 0.035 20', accent: '0.64 0.19 25', accentHover: '0.7 0.18 28', ink: '0.08 0.01 20', paper: '0.985 0.01 20', shadow: '0.04 0.02 20' },
    alpha: { panel: 0.92, bg: 1 },
    font: { display: "'Cinzel', serif", sans: "'Inter', system-ui, sans-serif" },
    swatch: ['#170d0e', '#d6453d', '#33191a'],
  },
  containment: {
    labelKey: 'theme.names.containment', label: 'Containment', emoji: '🧿', scheme: 'dark',
    neutral: [255, 0.016], accent: [295, 1.05],
    surface: { bg: '0.15 0.012 255', deep: '0.12 0.01 255', panel: '0.19 0.016 255', border: '0.3 0.022 255', accent: '0.73 0.16 295', accentHover: '0.8 0.14 295', ink: '0.09 0.01 255', paper: '0.99 0.008 260', shadow: '0.05 0.015 255' },
    alpha: { panel: 0.9, bg: 1 },
    font: { display: "'Space Grotesk', 'Inter', sans-serif", sans: "'Inter', system-ui, sans-serif" },
    swatch: ['#13171d', '#a77bf3', '#262c36'],
  },
  wasteland: {
    labelKey: 'theme.names.wasteland', label: 'Wasteland', emoji: '☢️', scheme: 'dark',
    neutral: [95, 0.02], accent: [115, 1.05],
    surface: { bg: '0.165 0.015 95', deep: '0.135 0.012 95', panel: '0.205 0.02 95', border: '0.33 0.03 95', accent: '0.8 0.16 118', accentHover: '0.86 0.15 120', ink: '0.1 0.01 95', paper: '0.985 0.02 110', shadow: '0.05 0.015 95' },
    alpha: { panel: 0.92, bg: 1 },
    font: { display: "'Space Grotesk', 'Inter', sans-serif", sans: "'Inter', system-ui, sans-serif" },
    swatch: ['#1c1b12', '#b5d34a', '#33331f'],
  },
  daylight: {
    labelKey: 'theme.names.daylight', label: 'Daylight', emoji: '🌤️', scheme: 'light',
    neutral: [45, 0.014], accent: [28, 1.05],
    surface: { bg: '0.975 0.007 70', deep: '0.955 0.01 70', panel: '0.995 0.004 70', border: '0.905 0.012 60', accent: '0.65 0.16 28', accentHover: '0.59 0.17 28', ink: '0.995 0.003 70', paper: '0.22 0.012 45', shadow: '0.45 0.03 45' },
    alpha: { panel: 0.92, bg: 1 },
    font: { display: "'Inter', system-ui, sans-serif", sans: "'Inter', system-ui, sans-serif" },
    swatch: ['#faf6f0', '#e8674d', '#2f2a26'],
  },
  aero: {
    labelKey: 'theme.names.aero', label: 'Frutiger Aero', emoji: '🫧', scheme: 'light', manualOnly: true,
    neutral: [235, 0.03], accent: [228, 1.05],
    surface: { bg: '0.95 0.025 225', deep: '0.92 0.035 222', panel: '0.99 0.012 220', border: '0.86 0.045 225', accent: '0.66 0.15 238', accentHover: '0.6 0.16 245', ink: '0.995 0.006 220', paper: '0.27 0.05 245', shadow: '0.45 0.08 240' },
    alpha: { panel: 0.62, bg: 0.72 },
    font: { display: "'Segoe UI Variable Display', 'Segoe UI', 'Frutiger', 'Myriad Pro', system-ui, sans-serif", sans: "'Segoe UI Variable Text', 'Segoe UI', 'Frutiger', 'Myriad Pro', system-ui, sans-serif" },
    swatch: ['#bfe9ff', '#2a9df4', '#7ed957'],
  },
  midas: {
    labelKey: 'theme.names.midas', label: 'Pimped Out', emoji: '💰', scheme: 'dark', manualOnly: true,
    neutral: [85, 0.04], accent: [86, 1.25],
    surface: { bg: '0.13 0.012 80', deep: '0.1 0.01 80', panel: '0.17 0.02 82', border: '0.5 0.1 85', accent: '0.83 0.155 88', accentHover: '0.9 0.14 94', ink: '0.08 0.01 80', paper: '0.99 0.03 95', shadow: '0.05 0.02 80' },
    alpha: { panel: 0.88, bg: 1 },
    font: { display: "'Cinzel', serif", sans: "'Inter', system-ui, sans-serif" },
    swatch: ['#16120a', '#ffd34d', '#fff2b0'],
  },
};

export const DEFAULT_THEME = 'ember';
export const THEME_IDS = Object.keys(THEMES);

/** Build the CSS custom property map for a single theme. */
export function buildThemeVars(id) {
  const t = THEMES[id];
  const light = t.scheme === 'light';
  const vars = {};
  const [nh, nc] = t.neutral;
  const [ah, af] = t.accent;
  for (const s of SHADES) {
    // Light schemes mirror the ramp so "light text" classes become dark text.
    const src = light ? 1000 - s : s;
    vars[`--g-${s}`] = `${f(NEUTRAL_L[src])} ${f(nc * NEUTRAL_C[src])} ${nh}`;
    vars[`--a-${s}`] = `${f(ACCENT_L[src] - (light ? 0.04 : 0))} ${f(ACCENT_C[src] * af)} ${ah}`;
  }
  const sf = t.surface;
  Object.assign(vars, {
    '--bg': sf.bg,
    '--bg-deep': sf.deep,
    '--panel': sf.panel,
    '--border': sf.border,
    '--accent': sf.accent,
    '--accent-hover': sf.accentHover,
    // `black`/`white` swap in light schemes: overlays become frosted, and
    // text on accent buttons stays legible.
    '--black': sf.ink,
    '--white': sf.paper,
    '--shadow': sf.shadow,
    '--panel-a': String(t.alpha.panel),
    '--bg-a': String(t.alpha.bg),
    '--font-display': t.font.display,
    '--font-sans': t.font.sans,
    'color-scheme': t.scheme,
  });
  return vars;
}

// Scenario → theme resolution. Ordered by specificity: the first matching
// rule wins, so hybrid scenarios (e.g. urban fantasy + horror) land on the
// most distinctive palette.
const TAG_RULES = [
  ['cyberpunk', 'neon'],
  ['space', 'nebula'],
  ['steampunk', 'brass'],
  ['post_apocalypse', 'wasteland'],
  ['urban_fantasy', 'containment'],
  ['grimdark', 'crimson'],
  ['horror', 'crimson'],
  ['gore', 'crimson'],
  ['high_school', 'daylight'],
  ['slice_of_life', 'daylight'],
  ['isekai', 'ember'],
  ['fantasy', 'ember'],
];

const KEYWORD_RULES = [
  [/cyber|neon|chrome/i, 'neon'],
  [/sci[_\s-]?fi|space|outer rim|star/i, 'nebula'],
  [/steam|brass|aether/i, 'brass'],
  [/apocalyp|fallout|wasteland|nuclear/i, 'wasteland'],
  [/anomal|incursion|urban/i, 'containment'],
  [/dark[_\s-]?fantasy|grimdark|cursed|horror|gore/i, 'crimson'],
  [/high[_\s-]?school|slice[_\s-]?of[_\s-]?life|latte|rooftop/i, 'daylight'],
  [/fantasy|isekai|myth|magic/i, 'ember'],
];

/** Pick the best theme for a session/scenario-like object. */
export function resolveScenarioTheme(source) {
  if (!source) return DEFAULT_THEME;
  const asList = (v) => (Array.isArray(v) ? v : typeof v === 'string' && v ? v.split(/[\s,|]+/) : []);
  const tags = asList(source.scenario_tags)
    .concat(asList(source.tags))
    .map((x) => String(x).toLowerCase().trim());
  for (const [tag, theme] of TAG_RULES) {
    if (tags.includes(tag)) return theme;
  }
  const hay = [source.scenario, source.scenario_key, source.key, source.scenario_display_name, source.display_name]
    .filter(Boolean)
    .join(' ');
  for (const [re, theme] of KEYWORD_RULES) {
    if (re.test(hay)) return theme;
  }
  return DEFAULT_THEME;
}
