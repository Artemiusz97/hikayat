import React, { useRef, useState } from 'react';
import AnchoredPopover from './AnchoredPopover';
import { Palette, Check, Wand2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useTheme } from '../../theme/ThemeProvider';
import { THEMES, THEME_IDS } from '../../theme/themes';

const Swatch = ({ colors, size = 'md' }) => (
  <span
    aria-hidden="true"
    className={`hk-swatch ${size === 'sm' ? 'w-5 h-5' : 'w-full aspect-[16/8]'}`}
    style={{ '--s1': colors[0], '--s2': colors[1], '--s3': colors[2] }}
  />
);

/** Full theme picker (used inside Settings and the header popover). */
export const ThemeGrid = ({ compact = false, onPicked }) => {
  const { t } = useTranslation();
  const { mode, setMode, activeTheme, scenarioTheme } = useTheme();
  const isAuto = mode === 'auto';
  const scenarioLabel = t(THEMES[scenarioTheme].labelKey, THEMES[scenarioTheme].label);

  return (
    <div className="space-y-3">
      <button
        type="button"
        role="switch"
        aria-checked={isAuto}
        onClick={(e) => setMode(isAuto ? activeTheme : 'auto', e)}
        className={`w-full flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left ${
          isAuto ? 'border-fantasy-accent/60 bg-fantasy-accent/10' : 'border-fantasy-border bg-black/20 hover:border-fantasy-accent/40'
        }`}
      >
        <span className={`grid place-items-center w-8 h-8 rounded-md ${isAuto ? 'bg-fantasy-accent text-black' : 'bg-black/30 text-gray-400'}`}>
          <Wand2 size={16} />
        </span>
        <span className="flex-1 min-w-0">
          <span className="block text-sm font-semibold text-gray-100">{t('theme.auto', 'Match scenario')}</span>
          <span className="block text-xs text-gray-400 truncate">
            {isAuto
              ? t('theme.auto_active', { name: scenarioLabel, defaultValue: `Following the realm · ${scenarioLabel}` })
              : t('theme.auto_desc', 'Adapts colours to the realm you are playing')}
          </span>
        </span>
        <span className={`hk-toggle ${isAuto ? 'is-on' : ''}`} aria-hidden="true" />
      </button>

      <div className={`grid gap-2 ${compact ? 'grid-cols-3' : 'grid-cols-2 sm:grid-cols-3'}`}>
        {THEME_IDS.map((id) => {
          const th = THEMES[id];
          const selected = !isAuto && mode === id;
          const showing = activeTheme === id;
          return (
            <button
              key={id}
              type="button"
              onClick={(e) => {
                setMode(id, e);
                onPicked?.(id);
              }}
              aria-pressed={selected}
              className={`group relative flex flex-col gap-1.5 rounded-lg border p-1.5 text-left ${
                selected
                  ? 'border-fantasy-accent ring-2 ring-fantasy-accent/30'
                  : showing
                    ? 'border-fantasy-accent/50'
                    : 'border-fantasy-border hover:border-gray-500'
              }`}
            >
              <Swatch colors={th.swatch} />
              <span className="flex items-center gap-1 px-0.5 pb-0.5 text-[11px] font-medium text-gray-200 truncate">
                {!compact && <span aria-hidden="true">{th.emoji}</span>}
                <span className="truncate">{t(th.labelKey, th.label)}</span>
              </span>
              {selected && (
                <span className="absolute top-2.5 right-2.5 grid place-items-center w-5 h-5 rounded-full bg-fantasy-accent text-black shadow">
                  <Check size={12} strokeWidth={3} />
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
};


/** Compact header button + viewport-aware popover. */
const ThemeSwitcher = ({ align = 'end', compact = false, className = '' }) => {
  const { t } = useTranslation();
  const { activeTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const btnRef = useRef(null);

  return (
    <div className={`relative ${className}`}>
      <button
        ref={btnRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="dialog"
        title={t('theme.title', 'Theme')}
        aria-label={t('theme.title', 'Theme')}
        className="hk-icon-btn"
      >
        {!compact && <Palette size={16} />}
        <Swatch colors={THEMES[activeTheme].swatch} size="sm" />
      </button>
      <AnchoredPopover
        anchorRef={btnRef}
        open={open}
        onClose={() => setOpen(false)}
        width={336}
        align={align}
        label={t('theme.title', 'Theme')}
        className="p-3"
      >
        <div className="mb-2.5 px-0.5 text-xs font-semibold text-gray-400">{t('theme.title', 'Theme')}</div>
        <ThemeGrid compact />
      </AnchoredPopover>
    </div>
  );
};

export default ThemeSwitcher;