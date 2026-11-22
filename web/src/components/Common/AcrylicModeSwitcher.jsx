import { Contrast, Layers, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useUiPreferences } from '../../theme/UiPreferencesProvider';
import { MotionButton } from './MotionPrimitives';

const MODE_META = {
  full: {
    icon: Sparkles,
    labelKey: 'theme.acrylic_full',
    fallback: 'Full Acrylic',
  },
  focused: {
    icon: Layers,
    labelKey: 'theme.acrylic_focused',
    fallback: 'Translucent',
  },
  solid: {
    icon: Contrast,
    labelKey: 'theme.acrylic_solid',
    fallback: 'Solid',
  },
};

const AcrylicModeSwitcher = ({ showLabel = false, className = '' }) => {
  const { t } = useTranslation();
  const { acrylicMode, cycleAcrylicMode } = useUiPreferences();

  const meta = MODE_META[acrylicMode] || MODE_META.full;
  const Icon = meta.icon;
  const titlePrefix = t('theme.acrylic_mode', 'Acrylic Blur');
  const modeLabel = t(meta.labelKey, meta.fallback);
  const fullLabel = `${titlePrefix}: ${modeLabel}`;

  return (
    <MotionButton
      onClick={cycleAcrylicMode}
      title={fullLabel}
      aria-label={fullLabel}
      className={`hk-icon-btn ${acrylicMode !== 'solid' ? 'text-fantasy-accent' : ''} ${showLabel ? '!w-auto !px-2.5' : ''} ${className}`.trim()}
    >
      <Icon size={16} className="shrink-0" />
      {showLabel && (
        <span className="text-xs font-medium truncate">{modeLabel}</span>
      )}
    </MotionButton>
  );
};

export default AcrylicModeSwitcher;
