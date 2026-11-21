export const THEME_DEFAULT_FONT_ID = 'theme';

export const UI_FONT_PRESETS = [
  {
    id: 'theme',
    labelKey: 'settings.font_theme_default',
    defaultLabel: 'Theme Default',
    stack: null,
  },
  {
    id: 'preset:inter',
    label: 'Inter',
    stack: "'Inter', ui-sans-serif, system-ui, sans-serif",
  },
  {
    id: 'preset:space-grotesk',
    label: 'Space Grotesk',
    stack: "'Space Grotesk', 'Inter', ui-sans-serif, sans-serif",
  },
  {
    id: 'preset:atkinson',
    label: 'Atkinson Hyperlegible',
    stack: "'Atkinson Hyperlegible', 'Inter', ui-sans-serif, system-ui, sans-serif",
    googleSpec: 'Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400;1,700',
  },
  {
    id: 'preset:plus-jakarta',
    label: 'Plus Jakarta Sans',
    stack: "'Plus Jakarta Sans', 'Inter', ui-sans-serif, system-ui, sans-serif",
    googleSpec: 'Plus+Jakarta+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400',
  },
  {
    id: 'preset:system-sans',
    labelKey: 'settings.font_system_sans',
    defaultLabel: 'System Sans',
    stack: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
  },
  {
    id: 'preset:jetbrains-mono',
    label: 'JetBrains Mono',
    stack: "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace",
    googleSpec: 'JetBrains+Mono:ital,wght@0,400;0,600;0,700;1,400',
  },
];

export const NARRATION_FONT_PRESETS = [
  {
    id: 'theme',
    labelKey: 'settings.font_theme_default',
    defaultLabel: 'Theme Default',
    stack: null,
  },
  {
    id: 'preset:literata',
    label: 'Literata',
    stack: "'Literata', Georgia, Cambria, serif",
    googleSpec: 'Literata:ital,opsz,wght@0,7..72,400..700;1,7..72,400..700',
  },
  {
    id: 'preset:lora',
    label: 'Lora',
    stack: "'Lora', Georgia, Cambria, serif",
    googleSpec: 'Lora:ital,wght@0,400..700;1,400..700',
  },
  {
    id: 'preset:merriweather',
    label: 'Merriweather',
    stack: "'Merriweather', Georgia, Cambria, serif",
    googleSpec: 'Merriweather:ital,wght@0,400;0,700;1,400;1,700',
  },
  {
    id: 'preset:crimson-pro',
    label: 'Crimson Pro',
    stack: "'Crimson Pro', Georgia, Cambria, serif",
    googleSpec: 'Crimson+Pro:ital,wght@0,400..700;1,400..700',
  },
  {
    id: 'preset:atkinson',
    label: 'Atkinson Hyperlegible',
    stack: "'Atkinson Hyperlegible', 'Inter', ui-sans-serif, system-ui, sans-serif",
    googleSpec: 'Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400;1,700',
  },
  {
    id: 'preset:inter',
    label: 'Inter',
    stack: "'Inter', ui-sans-serif, system-ui, sans-serif",
  },
  {
    id: 'preset:jetbrains-mono',
    label: 'JetBrains Mono',
    stack: "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace",
    googleSpec: 'JetBrains+Mono:ital,wght@0,400;0,600;0,700;1,400',
  },
];

const CUSTOM_STYLE_ELEMENT_ID = 'hk-custom-fonts-style';
const SAFE_CSS_FAMILY_RE = /^[A-Za-z0-9_-]+$/;
const ALLOWED_FORMATS = new Set(['woff2', 'woff', 'opentype', 'truetype']);

export const ensureGoogleFontLoaded = (googleSpec) => {
  if (!googleSpec || typeof document === 'undefined') return;
  const selector = `link[data-hk-gfont="${googleSpec}"]`;
  if (document.head.querySelector(selector)) return;
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.setAttribute('data-hk-gfont', googleSpec);
  link.href = `https://fonts.googleapis.com/css2?family=${googleSpec}&display=swap`;
  document.head.appendChild(link);
};

export const syncCustomFontFaces = (customFonts) => {
  if (typeof document === 'undefined') return;
  const list = Array.isArray(customFonts) ? customFonts : [];
  const rules = [];

  for (const fam of list) {
    const cssFamily = String(fam?.css_family || '').trim();
    if (!SAFE_CSS_FAMILY_RE.test(cssFamily)) continue;
    const faces = Array.isArray(fam?.faces) ? fam.faces : [];
    for (const face of faces) {
      const url = String(face?.url || '').trim();
      const fmt = String(face?.format || '').trim();
      if (!url.startsWith('/fonts/') || url.includes("'") || url.includes('"') || !ALLOWED_FORMATS.has(fmt)) {
        continue;
      }
      const weight = Math.min(900, Math.max(100, Number(face?.weight) || 400));
      const style = face?.style === 'italic' ? 'italic' : 'normal';
      rules.push(
        `@font-face {\n` +
          `  font-family: '${cssFamily}';\n` +
          `  src: url('${url}') format('${fmt}');\n` +
          `  font-weight: ${weight};\n` +
          `  font-style: ${style};\n` +
          `  font-display: swap;\n` +
          `}`
      );
    }
  }

  let styleEl = document.getElementById(CUSTOM_STYLE_ELEMENT_ID);
  if (rules.length === 0) {
    if (styleEl) styleEl.textContent = '';
    return;
  }
  if (!styleEl) {
    styleEl = document.createElement('style');
    styleEl.id = CUSTOM_STYLE_ELEMENT_ID;
    document.head.appendChild(styleEl);
  }
  styleEl.textContent = rules.join('\n');
};

export const resolveFontSelection = (fontId, slot = 'ui', customFonts = []) => {
  const id = String(fontId || THEME_DEFAULT_FONT_ID).trim() || THEME_DEFAULT_FONT_ID;
  if (id === THEME_DEFAULT_FONT_ID) {
    return { valid: true, id: THEME_DEFAULT_FONT_ID, stack: null, googleSpec: null };
  }

  const presets = slot === 'narration' ? NARRATION_FONT_PRESETS : UI_FONT_PRESETS;
  const preset = presets.find((p) => p.id === id);
  if (preset) {
    return {
      valid: true,
      id: preset.id,
      stack: preset.stack,
      googleSpec: preset.googleSpec || null,
    };
  }

  if (id.startsWith('custom:')) {
    const fam = (Array.isArray(customFonts) ? customFonts : []).find((f) => f?.id === id);
    if (fam && SAFE_CSS_FAMILY_RE.test(String(fam.css_family || ''))) {
      const fallback =
        slot === 'narration'
          ? "ui-serif, Georgia, Cambria, 'Times New Roman', Times, serif"
          : 'ui-sans-serif, system-ui, sans-serif';
      return {
        valid: true,
        id: fam.id,
        stack: `'${fam.css_family}', ${fallback}`,
        googleSpec: null,
      };
    }
    return { valid: false, id: THEME_DEFAULT_FONT_ID, stack: null, googleSpec: null };
  }

  return { valid: false, id: THEME_DEFAULT_FONT_ID, stack: null, googleSpec: null };
};

export const applyFontVariables = (uiFontId, narrationFontId, customFonts = []) => {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;

  const uiRes = resolveFontSelection(uiFontId, 'ui', customFonts);
  if (uiRes.googleSpec) ensureGoogleFontLoaded(uiRes.googleSpec);
  if (uiRes.stack) {
    root.style.setProperty('--ui-font-sans', uiRes.stack);
  } else {
    root.style.removeProperty('--ui-font-sans');
  }

  const narrRes = resolveFontSelection(narrationFontId, 'narration', customFonts);
  if (narrRes.googleSpec) ensureGoogleFontLoaded(narrRes.googleSpec);
  if (narrRes.stack) {
    root.style.setProperty('--ui-font-narration', narrRes.stack);
  } else {
    root.style.removeProperty('--ui-font-narration');
  }
};
