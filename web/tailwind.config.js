/** @type {import('tailwindcss').Config} */
import plugin from 'tailwindcss/plugin';
import twColors from 'tailwindcss/colors';
import { SHADES, THEME_IDS, DEFAULT_THEME, buildThemeVars } from './src/theme/themes.js';

const hexToRgb = (hex) => {
  const h = hex.replace('#', '');
  const n = parseInt(h.length === 3 ? h.split('').map((c) => c + c).join('') : h, 16);
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`;
};

// Theme-driven OKLCH ramps (gray family -> --g-*, amber/accent -> --a-*).
const oklchRamp = (prefix) =>
  Object.fromEntries(SHADES.map((s) => [s, `oklch(var(--${prefix}-${s}) / <alpha-value>)`]));

// Status hues keep Tailwind defaults but are overridable (light schemes invert them).
const STATUS_HUES = ['red', 'rose', 'pink', 'fuchsia', 'purple', 'violet', 'indigo', 'blue', 'sky', 'cyan', 'teal', 'emerald', 'green', 'lime', 'yellow', 'orange'];
const statusRamp = (hue) =>
  Object.fromEntries(SHADES.map((s) => [s, `rgb(var(--${hue}-${s}, ${hexToRgb(twColors[hue][s])}) / <alpha-value>)`]));

const statusColors = Object.fromEntries(STATUS_HUES.map((h) => [h, statusRamp(h)]));

const themePlugin = plugin(({ addBase }) => {
  const base = {};
  base[':root'] = buildThemeVars(DEFAULT_THEME);
  for (const id of THEME_IDS) {
    base[`[data-theme="${id}"]`] = buildThemeVars(id);
  }
  // Light schemes mirror status hues (text-red-300 -> red-700, bg-red-950 -> red-50).
  const lightStatus = {};
  for (const hue of STATUS_HUES) {
    for (const s of SHADES) {
      lightStatus[`--${hue}-${s}`] = hexToRgb(twColors[hue][1000 - s]);
    }
  }
  base['[data-scheme="light"]'] = lightStatus;
  addBase(base);
});

export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'fantasy-dark': 'oklch(var(--bg) / calc(<alpha-value> * var(--bg-a, 1)))',
        'fantasy-darker': 'oklch(var(--bg-deep) / calc(<alpha-value> * var(--bg-a, 1)))',
        'fantasy-panel': 'oklch(var(--panel) / calc(<alpha-value> * var(--panel-a, 1)))',
        'fantasy-border': 'oklch(var(--border) / <alpha-value>)',
        'fantasy-accent': 'oklch(var(--accent) / <alpha-value>)',
        'fantasy-accent-hover': 'oklch(var(--accent-hover) / <alpha-value>)',
        'health': '#e53935',
        'mana': '#1e88e5',
        'stamina': '#43a047',
        black: 'oklch(var(--black) / <alpha-value>)',
        white: 'oklch(var(--white) / <alpha-value>)',
        gray: oklchRamp('g'),
        neutral: oklchRamp('g'),
        zinc: oklchRamp('g'),
        slate: oklchRamp('g'),
        stone: oklchRamp('g'),
        amber: oklchRamp('a'),
        ...statusColors,
      },
      fontFamily: {
        rpg: 'var(--font-display)',
        sans: 'var(--font-sans)',
      },
      borderRadius: {
        sm: '0.375rem',
        DEFAULT: '0.5rem',
        md: '0.625rem',
        lg: '0.875rem',
        xl: '1.125rem',
        '2xl': '1.5rem',
        '3xl': '2rem',
      },
      boxShadow: {
        sm: '0 1px 2px oklch(var(--shadow) / 0.18)',
        DEFAULT: '0 1px 3px oklch(var(--shadow) / 0.2), 0 1px 2px oklch(var(--shadow) / 0.12)',
        md: '0 4px 12px -2px oklch(var(--shadow) / 0.22), 0 2px 4px -2px oklch(var(--shadow) / 0.14)',
        lg: '0 12px 28px -8px oklch(var(--shadow) / 0.32), 0 4px 10px -4px oklch(var(--shadow) / 0.16)',
        xl: '0 20px 40px -12px oklch(var(--shadow) / 0.38), 0 8px 16px -8px oklch(var(--shadow) / 0.18)',
        '2xl': '0 32px 64px -16px oklch(var(--shadow) / 0.45)',
        inner: 'inset 0 2px 4px oklch(var(--shadow) / 0.12)',
      },
      transitionTimingFunction: {
        DEFAULT: 'cubic-bezier(0.22, 1, 0.36, 1)',
        out: 'cubic-bezier(0.22, 1, 0.36, 1)',
        spring: 'var(--ease-spring)',
      },
      keyframes: {
        fadeIn: { from: { opacity: '0' }, to: { opacity: '1' } },
        rise: { from: { opacity: '0', translate: '0 10px' }, to: { opacity: '1', translate: '0 0' } },
      },
      animation: {
        fadeIn: 'fadeIn 0.25s cubic-bezier(0.22, 1, 0.36, 1) both',
        rise: 'rise 0.45s var(--ease-spring) both',
      },
    },
  },
  plugins: [themePlugin],
}
