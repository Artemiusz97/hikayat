import { useState, useEffect, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import {
  X,
  Zap,
  BookOpen,
  Sliders,
  Check,
  ShieldAlert,
  Image as ImageIcon,
  Activity,
  RefreshCw,
  Terminal,
  HeartPulse,
  Skull,
  Globe,
  Monitor,
  Sparkles,
  Contrast,
  Layers,
  Clock,
  Type,
} from 'lucide-react';
import { apiCall } from '../../api/client';
import { AVAILABLE_LANGUAGES } from '../../i18n';
import {
  DEFAULT_ACRYLIC_OPACITY,
  MAX_ACRYLIC_OPACITY,
  MIN_ACRYLIC_OPACITY,
  DEFAULT_TEXT_SCALE,
  MAX_TEXT_SCALE,
  MIN_TEXT_SCALE,
  TEXT_SCALE_STEP,
  useUiPreferences,
} from '../../theme/UiPreferencesProvider';
import {
  NARRATION_FONT_PRESETS,
  THEME_DEFAULT_FONT_ID,
  UI_FONT_PRESETS,
  resolveFontSelection,
} from '../../utils/fonts';
import { AcrylicModal, CollapsibleSection, MotionButton } from '../Common/MotionPrimitives';

const SettingsModal = ({
  isOpen,
  onClose,
  settingsHook,
  user,
  session,
  onSessionUpdated,
  onRefreshCharacter,
  onRefreshCodex,
}) => {
  const { t, i18n } = useTranslation();
  const {
    acrylicMode,
    setAcrylicMode,
    acrylicOpacity,
    setAcrylicOpacity,
    textScale,
    setTextScale,
    illustratedBackdrops,
    setIllustratedBackdrops,
    readingMode,
    setReadingMode,
    clockFormat,
    setClockFormat,
    uiFont,
    setUiFont,
    narrationFont,
    setNarrationFont,
    customFonts,
    customFontsLoading,
    refreshCustomFonts,
    ambientSceneBackdrop,
    setAmbientSceneBackdrop,
  } = useUiPreferences();

  const [activeTab, setActiveTab] = useState('preferences'); // 'preferences' | 'interface' | 'narration' | 'language' | 'telemetry'
  const settingsTabRefs = useRef({});
  const [telemetry, setTelemetry] = useState(null);
  const [debugStatMode, setDebugStatMode] = useState('off');
  const [debugCheckMode, setDebugCheckMode] = useState('off');
  const [debugRevealAll, setDebugRevealAll] = useState(0);
  const [loadingTelemetry, setLoadingTelemetry] = useState(false);
  const [debugNotice, setDebugNotice] = useState(null);
  const debugTimerRef = useRef(null);
  useEffect(() => () => {
    if (debugTimerRef.current) clearTimeout(debugTimerRef.current);
  }, []);

  const loadDiagnostics = useCallback(async () => {
    setLoadingTelemetry(true);
    try {
      if (user?.user_id) {
        const data = await apiCall(`/api/debug/${user.user_id}`);
        setTelemetry(data.telemetry || null);
        setDebugStatMode(data.debug_stat_mode || 'off');
        setDebugCheckMode(data.debug_check_mode || 'off');
        setDebugRevealAll(data.debug_reveal_all_info ? 1 : 0);
      } else {
        const data = await apiCall('/api/settings/debug/telemetry');
        setTelemetry(data.telemetry || null);
      }
    } catch {
      // ignore
    } finally {
      setLoadingTelemetry(false);
    }
  }, [user?.user_id]);

  useEffect(() => {
    if (isOpen && activeTab === 'telemetry') {
      loadDiagnostics();
    }
  }, [isOpen, activeTab, loadDiagnostics]);

  useEffect(() => {
    if (isOpen && activeTab === 'interface') {
      refreshCustomFonts();
    }
  }, [isOpen, activeTab, refreshCustomFonts]);

  const {
    settings = {},
    saving = false,
    updateSettings = () => {},
  } = settingsHook || {};

  const handleToggleStreaming = () => {
    const currentVal = settings.stream_narrative ?? 1;
    updateSettings({ stream_narrative: currentVal === 1 ? 0 : 1 });
  };

  const handleVerbosityChange = (val) => {
    const rawVerb = (settings.verbosity || '').toLowerCase();
    if (!settings.narrative_pacing && (rawVerb === 'concise' || rawVerb === 'direct')) {
      updateSettings({ verbosity: val, narrative_pacing: 'concise' });
    } else {
      updateSettings({ verbosity: val });
    }
  };

  const handlePacingChange = (val) => {
    updateSettings({ narrative_pacing: val });
  };

  const handleDialogueModeChange = (val) => {
    updateSettings({ dialogue_mode: val });
  };

  const handleResultDisplayChange = (val) => {
    updateSettings({ result_display: val });
  };

  const handleTogglePercentages = () => {
    const currentVal = settings.show_percentages ?? 1;
    updateSettings({ show_percentages: currentVal === 1 ? 0 : 1 });
  };

  const handleDebugUpdate = async (payload, label) => {
    if (!user?.user_id) return;
    try {
      const res = await apiCall(`/api/debug/${user.user_id}`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      setDebugStatMode(res.debug_stat_mode || 'off');
      setDebugCheckMode(res.debug_check_mode || 'off');
      if (res.debug_reveal_all_info !== undefined) {
        setDebugRevealAll(res.debug_reveal_all_info ? 1 : 0);
      }
      setDebugNotice(label || 'Sandbox updated');
      if (payload.action && onRefreshCharacter) {
        onRefreshCharacter();
      }
      if (res.session && onSessionUpdated) {
        onSessionUpdated(res.session);
      }
      if (
        (payload.debug_reveal_all_info !== undefined || payload.action === 'reset_all') &&
        onRefreshCodex
      ) {
        onRefreshCodex();
      }
      if (debugTimerRef.current) clearTimeout(debugTimerRef.current);
      debugTimerRef.current = setTimeout(() => setDebugNotice(null), 2500);
    } catch {
      // ignore
    }
  };

  const isStreamingOn = (settings.stream_narrative ?? 1) === 1;
  const isShowPercentagesOn = (settings.show_percentages ?? 1) === 1;
  const circuitBreakers = Object.entries(telemetry?.circuit_breakers || {});

  return (
    <AcrylicModal
      isOpen={isOpen}
      onClose={onClose}
      label={t('settings.modal_title', 'Settings')}
      maxWidthClass="max-w-3xl"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3.5 border-b border-fantasy-border/35 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <Sliders className="text-fantasy-accent shrink-0" size={18} />
          <h2 className="font-rpg font-bold text-lg text-gray-100 truncate">
            {t('settings.modal_title', 'Settings')}
          </h2>
        </div>
        <MotionButton
          onClick={onClose}
          aria-label={t('common.close', 'Close')}
          className="hk-icon-btn h-8 min-w-8"
        >
          <X size={18} />
        </MotionButton>
      </div>

      {/* Sub-Navigation Tabs */}
      <div
        role="tablist"
        aria-label={t('settings.modal_title', 'Settings')}
        className="flex items-center flex-nowrap overflow-x-auto custom-scrollbar border-b border-fantasy-border/35 px-4 py-2 gap-1.5 shrink-0"
      >
        {[
          { id: 'preferences', icon: Sliders, label: t('settings.tab_preferences', 'Preferences') },
          { id: 'interface', icon: Monitor, label: t('settings.tab_interface', 'Interface') },
          { id: 'narration', icon: BookOpen, label: t('settings.tab_narration', 'Narration') },
          { id: 'language', icon: Globe, label: t('settings.tab_language', t('settings.language', 'Language')) },
          { id: 'telemetry', icon: Activity, label: t('settings.tab_telemetry', 'Telemetry & Sandbox') },
        ].map((tab, idx, arr) => {
          const Icon = tab.icon;
          const active = activeTab === tab.id;
          return (
            <MotionButton
              key={tab.id}
              ref={(el) => {
                settingsTabRefs.current[tab.id] = el;
              }}
              role="tab"
              aria-selected={active}
              tabIndex={active ? 0 : -1}
              onClick={() => setActiveTab(tab.id)}
              onKeyDown={(e) => {
                let nextIdx = null;
                if (e.key === 'ArrowRight') nextIdx = (idx + 1) % arr.length;
                else if (e.key === 'ArrowLeft') nextIdx = (idx - 1 + arr.length) % arr.length;
                else if (e.key === 'Home') nextIdx = 0;
                else if (e.key === 'End') nextIdx = arr.length - 1;
                if (nextIdx !== null) {
                  e.preventDefault();
                  const nextId = arr[nextIdx].id;
                  setActiveTab(nextId);
                  settingsTabRefs.current[nextId]?.focus();
                }
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold uppercase tracking-wide flex items-center gap-1.5 whitespace-nowrap shrink-0 transition-colors ${
                active
                  ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-500/10'
              }`}
            >
              <Icon size={13} className="shrink-0" />
              <span>{tab.label}</span>
            </MotionButton>
          );
        })}
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 px-4 sm:px-5 py-2 overflow-y-auto overscroll-contain custom-scrollbar">
        {activeTab === 'preferences' && (
          <div>
            {/* Section 1: Real-Time Narrative Streaming */}
            <div className="hk-flat-section">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <Zap size={16} className={isStreamingOn ? 'text-amber-400' : 'text-gray-500'} />
                    <span className="font-semibold text-gray-200 text-sm">
                      {t('settings.streaming', 'Real-Time Narrative Streaming')}
                    </span>
                    {isStreamingOn && (
                      <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40">
                        {t('settings.live', 'Live')}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-400 leading-relaxed">
                    {t(
                      'settings.streaming_desc',
                      "Stream the Chronicler's narrative token-by-token in real time over WebSockets as it is conceived."
                    )}
                  </p>
                </div>

                <button
                  type="button"
                  role="switch"
                  aria-checked={isStreamingOn}
                  aria-label={t('settings.streaming', 'Real-Time Narrative Streaming')}
                  onClick={handleToggleStreaming}
                  disabled={saving}
                  className={`hk-toggle ${isStreamingOn ? 'is-on' : ''}`}
                />
              </div>

              <div className="mt-2.5 flex items-center gap-2 text-[11px] text-gray-400">
                <span className="w-1.5 h-1.5 rounded-full bg-gray-500 shrink-0" />
                <span>
                  {isStreamingOn
                    ? t('settings.streaming_live_hint', 'Tokens will flow smoothly in typewriter cadence.')
                    : t('settings.streaming_batch_hint', 'Batch mode: full scene is delivered all at once.')}
                </span>
              </div>
            </div>

            {/* Section 1B: AI Scene Illustrations (3 Modes: Auto, On-Demand, Disabled) */}
            <div className="hk-flat-section space-y-2">
              <div className="flex items-center gap-2">
                <ImageIcon
                  size={16}
                  className={(settings.image_gen_enabled ?? 0) > 0 ? 'text-purple-400' : 'text-gray-500'}
                />
                <span className="font-semibold text-gray-200 text-sm">
                  {t('settings.image_gen', 'AI Scene Illustrations')}
                </span>
                {(settings.image_gen_enabled ?? 0) === 1 && (
                  <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/40">
                    {t('settings.image_mode_auto_badge', 'Auto')}
                  </span>
                )}
                {(settings.image_gen_enabled ?? 0) === 2 && (
                  <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40">
                    {t('settings.image_mode_on_demand_badge', 'On-Demand')}
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-400 leading-relaxed">
                {t('settings.image_gen_desc', 'Generate high-fidelity visual novel illustrations for active scenes.')}
              </p>
              <div className="grid grid-cols-3 gap-2 pt-1">
                {[
                  { id: 1, label: t('settings.image_mode_auto_label', '⚡ Auto'), desc: t('settings.image_mode_auto_desc', 'Every turn') },
                  { id: 2, label: t('settings.image_mode_on_demand_label', '✨ On-Demand'), desc: t('settings.image_mode_on_demand_desc', 'Manual click') },
                  { id: 0, label: t('settings.image_mode_disabled_label', '🚫 Disabled'), desc: t('settings.image_mode_disabled_desc', 'Off') },
                ].map((mode) => {
                  const isSelected = (settings.image_gen_enabled ?? 0) === mode.id;
                  return (
                    <MotionButton
                      key={mode.id}
                      onClick={() => updateSettings({ image_gen_enabled: mode.id })}
                      disabled={saving}
                      className={`p-2 rounded-xl text-left transition-all border ${
                        isSelected
                          ? 'bg-purple-500/20 border-purple-500/80 text-purple-200'
                          : 'bg-gray-500/10 border-fantasy-border/40 text-gray-300 hover:text-gray-100 hover:border-fantasy-border'
                      }`}
                    >
                      <div className="text-xs font-semibold">{mode.label}</div>
                      <div className="text-[10px] text-gray-400 mt-0.5">{mode.desc}</div>
                    </MotionButton>
                  );
                })}
              </div>
            </div>

            {/* Section 2: Reading Mode & Time Display */}
            <div className="hk-flat-section space-y-4">
              {/* Narration Reading Mode */}
              <div className="space-y-2.5">
                <div>
                  <label className="text-xs font-semibold text-gray-300 uppercase tracking-wider flex items-center gap-1.5">
                    <BookOpen size={14} className="text-fantasy-accent shrink-0" />
                    <span>{t('settings.reading_mode_label', 'Narration Reading Mode')}</span>
                  </label>
                  <p className="text-[11px] text-gray-400 mt-1">
                    {t('settings.reading_mode_desc', 'Show only the current scene with a Turn History button, or a continuous scrolling log.')}
                  </p>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {[
                    {
                      id: 'continuous',
                      label: t('settings.reading_mode_continuous', 'Continuous Feed'),
                      desc: t('settings.reading_mode_continuous_desc', 'Classic scrolling chronicle'),
                    },
                    {
                      id: 'scene',
                      label: t('settings.reading_mode_scene', 'Current Scene'),
                      desc: t('settings.reading_mode_scene_desc', 'Clean focus + Turn History'),
                    },
                  ].map((opt) => {
                    const isSelected = readingMode === opt.id;
                    return (
                      <MotionButton
                        key={opt.id}
                        onClick={() => setReadingMode(opt.id)}
                        aria-pressed={isSelected}
                        className={`flex flex-col p-2.5 rounded-xl border text-left transition-all ${
                          isSelected
                            ? 'bg-fantasy-accent/15 border-fantasy-accent text-fantasy-accent'
                            : 'bg-gray-500/10 border-fantasy-border/40 text-gray-300 hover:border-fantasy-border hover:text-gray-100'
                        }`}
                      >
                        <div className="flex items-center justify-between text-xs font-bold mb-1 w-full gap-2">
                          <span>{opt.label}</span>
                          {isSelected && <Check size={12} className="shrink-0" />}
                        </div>
                        <span className="text-[10px] opacity-75 leading-tight">{opt.desc}</span>
                      </MotionButton>
                    );
                  })}
                </div>
              </div>

              {/* 12-Hour / 24-Hour Clock Format */}
              <div className="space-y-2.5 pt-3 border-t border-fantasy-border/25">
                <div>
                  <label className="text-xs font-semibold text-gray-300 uppercase tracking-wider flex items-center gap-1.5">
                    <Clock size={14} className="text-fantasy-accent shrink-0" />
                    <span>{t('settings.clock_format', 'Clock Format')}</span>
                  </label>
                  <p className="text-[11px] text-gray-400 mt-1">
                    {t('settings.clock_format_desc', 'Switch between 12-hour (AM/PM) and 24-hour time display.')}
                  </p>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { id: '12h', label: t('settings.clock_format_12h', '12-Hour (AM/PM)'), sample: '7:45 AM' },
                    { id: '24h', label: t('settings.clock_format_24h', '24-Hour'), sample: '07:45' },
                  ].map((opt) => {
                    const isSelected = clockFormat === opt.id;
                    return (
                      <MotionButton
                        key={opt.id}
                        onClick={() => setClockFormat(opt.id)}
                        aria-pressed={isSelected}
                        className={`flex flex-col p-2.5 rounded-xl border text-left transition-all ${
                          isSelected
                            ? 'bg-fantasy-accent/15 border-fantasy-accent text-fantasy-accent'
                            : 'bg-gray-500/10 border-fantasy-border/40 text-gray-300 hover:border-fantasy-border hover:text-gray-100'
                        }`}
                      >
                        <div className="flex items-center justify-between text-xs font-bold mb-1 w-full gap-2">
                          <span>{opt.label}</span>
                          {isSelected && <Check size={12} className="shrink-0" />}
                        </div>
                        <span className="text-[10px] font-mono opacity-75 tabular-nums leading-tight">{opt.sample}</span>
                      </MotionButton>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Section 3: Result Display & Show Percentages */}
            <div className="hk-flat-section space-y-3">
              <label className="text-xs font-semibold text-gray-300 uppercase tracking-wider flex items-center gap-1.5">
                <ShieldAlert size={14} className="text-fantasy-accent" />
                {t('settings.outcome_format', 'Outcome Format & Odds')}
              </label>
              <div className="grid grid-cols-2 gap-2">
                {[
                  { id: 'detailed', label: t('settings.detailed_breakdown', 'Detailed Breakdown'), desc: t('settings.detailed_breakdown_desc', 'Full stat breakdowns, modifiers & mechanics') },
                  { id: 'compact', label: t('settings.streamlined', 'Streamlined'), desc: t('settings.streamlined_desc', 'Clean summary badges only') },
                ].map((r) => {
                  const isSelected = (settings.result_display || 'detailed') === r.id;
                  return (
                    <MotionButton
                      key={r.id}
                      onClick={() => handleResultDisplayChange(r.id)}
                      className={`flex flex-col p-2.5 rounded-xl border text-left transition-all ${
                        isSelected
                          ? 'bg-fantasy-accent/15 border-fantasy-accent text-fantasy-accent'
                          : 'bg-gray-500/10 border-fantasy-border/40 text-gray-300 hover:border-fantasy-border hover:text-gray-100'
                      }`}
                    >
                      <div className="flex items-center justify-between text-xs font-bold mb-1 w-full">
                        <span>{r.label}</span>
                        {isSelected && <Check size={12} />}
                      </div>
                      <span className="text-[10px] opacity-75 leading-tight">{r.desc}</span>
                    </MotionButton>
                  );
                })}
              </div>

              <div className="flex items-center justify-between gap-4 pt-1">
                <div>
                  <span className="text-xs font-semibold text-gray-200 block">
                    {t('settings.show_percentages', 'Show Skill Check Percentages')}
                  </span>
                  <span className="text-[11px] text-gray-400">
                    {t('settings.show_percentages_desc', 'Display exact success chance (%) on action choices and check outcomes')}
                  </span>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={isShowPercentagesOn}
                  aria-label={t('settings.show_percentages', 'Show Skill Check Percentages')}
                  onClick={handleTogglePercentages}
                  disabled={saving}
                  className={`hk-toggle ${isShowPercentagesOn ? 'is-on' : ''}`}
                />
              </div>
            </div>

          </div>
        )}

        {activeTab === 'interface' && (
          <div>
            {/* Section 0: Display & Atmosphere */}
            <div className="hk-flat-section space-y-3.5">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <Sparkles size={16} className="text-fantasy-accent shrink-0" />
                  <span className="font-semibold text-gray-100 text-sm">
                    {t('settings.display_atmosphere', 'Display & Atmosphere')}
                  </span>
                </div>
                <p className="text-xs text-gray-400 leading-relaxed">
                  {t('settings.acrylic_mode_desc', 'Control frosted glass translucency across floating HUD windows.')}
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                {[
                  { id: 'full', icon: Sparkles, label: t('theme.acrylic_full', 'Full Acrylic') },
                  { id: 'focused', icon: Layers, label: t('theme.acrylic_focused', 'Translucent') },
                  { id: 'solid', icon: Contrast, label: t('theme.acrylic_solid', 'Solid') },
                ].map((m) => {
                  const Icon = m.icon;
                  const isSelected = acrylicMode === m.id;
                  return (
                    <MotionButton
                      key={m.id}
                      onClick={() => setAcrylicMode(m.id)}
                      aria-pressed={isSelected}
                      className={`p-2.5 rounded-xl text-left transition-all border flex items-center gap-2 ${
                        isSelected
                          ? 'bg-fantasy-accent/15 border-fantasy-accent text-fantasy-accent'
                          : 'bg-gray-500/10 border-fantasy-border/40 text-gray-300 hover:border-fantasy-border hover:text-gray-100'
                      }`}
                    >
                      <Icon size={14} className="shrink-0" />
                      <span className="text-xs font-semibold truncate">{m.label}</span>
                    </MotionButton>
                  );
                })}
              </div>

              {/* Translucency / Window Opacity Slider (auto-hidden in Solid mode) */}
              <CollapsibleSection isOpen={acrylicMode !== 'solid'}>
                <div className="space-y-2 pt-1">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <span className="text-xs font-semibold text-gray-200 block">
                        {t('settings.acrylic_opacity', 'Window Opacity')}
                      </span>
                      <span className="text-[11px] text-gray-400 block">
                        {t('settings.acrylic_opacity_desc', 'Adjust frosted glass opacity from nearly transparent to nearly solid.')}
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {acrylicOpacity !== DEFAULT_ACRYLIC_OPACITY && (
                        <button
                          type="button"
                          onClick={() => {
                            if (acrylicMode === 'solid') setAcrylicMode('full');
                            setAcrylicOpacity(DEFAULT_ACRYLIC_OPACITY);
                          }}
                          className="text-[10px] font-semibold px-2 py-0.5 rounded-md border border-fantasy-border/50 text-gray-300 hover:text-fantasy-accent hover:border-fantasy-accent/50 transition-colors"
                        >
                          {t('settings.reset_default', 'Reset')}
                        </button>
                      )}
                      <span className="hk-chip hk-chip-accent font-mono tabular-nums">
                        {acrylicOpacity}%
                      </span>
                    </div>
                  </div>
                  <input
                    type="range"
                    min={MIN_ACRYLIC_OPACITY}
                    max={MAX_ACRYLIC_OPACITY}
                    step={1}
                    value={acrylicOpacity}
                    aria-label={t('settings.acrylic_opacity', 'Window Opacity')}
                    onChange={(e) => {
                      const next = Number(e.target.value);
                      if (acrylicMode === 'solid') setAcrylicMode('full');
                      setAcrylicOpacity(next);
                    }}
                    className="w-full h-1.5 rounded-full bg-gray-500/25 accent-fantasy-accent cursor-pointer"
                  />
                  <div className="grid grid-cols-3 items-center text-[10px] text-gray-400 font-medium">
                    <span className="text-left">{t('settings.acrylic_transparent', 'Transparent')}</span>
                    <span className="text-center">{t('settings.text_size_default', 'Default')}</span>
                    <span className="text-right">{t('settings.acrylic_solid', 'Solid')}</span>
                  </div>
                </div>
              </CollapsibleSection>

              {/* Text Size Scale Slider */}
              <div className="space-y-2 pt-1 border-t border-fantasy-border/25">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <span className="text-xs font-semibold text-gray-200 flex items-center gap-1.5">
                      <Type size={13} className="text-fantasy-accent shrink-0" />
                      <span>{t('settings.text_size', 'Text Size')}</span>
                    </span>
                    <span className="text-[11px] text-gray-400 block mt-0.5">
                      {t('settings.text_size_desc', 'Scale interface and narration text size. Panels and controls rescale automatically to prevent clipping.')}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {textScale !== DEFAULT_TEXT_SCALE && (
                      <button
                        type="button"
                        onClick={() => setTextScale(DEFAULT_TEXT_SCALE)}
                        className="text-[10px] font-semibold px-2 py-0.5 rounded-md border border-fantasy-border/50 text-gray-300 hover:text-fantasy-accent hover:border-fantasy-accent/50 transition-colors"
                      >
                        {t('settings.reset_default', 'Reset')}
                      </button>
                    )}
                    <span className="hk-chip hk-chip-accent font-mono tabular-nums">
                      {textScale}%
                    </span>
                  </div>
                </div>
                <input
                  type="range"
                  min={MIN_TEXT_SCALE}
                  max={MAX_TEXT_SCALE}
                  step={TEXT_SCALE_STEP}
                  value={textScale}
                  aria-label={t('settings.text_size', 'Text Size')}
                  onChange={(e) => setTextScale(Number(e.target.value))}
                  className="w-full h-1.5 rounded-full bg-gray-500/25 accent-fantasy-accent cursor-pointer"
                />
                <div className="grid grid-cols-3 items-center text-[10px] text-gray-400 font-medium">
                  <span className="text-left">{t('settings.text_size_smaller', 'Smaller')}</span>
                  <span className="text-center">{t('settings.text_size_default', 'Default')}</span>
                  <span className="text-right">{t('settings.text_size_larger', 'Larger')}</span>
                </div>
              </div>

              {/* Illustrated Backdrops vs Pattern Background Toggle */}
              <div className="flex items-center justify-between gap-4 pt-1">
                <div className="min-w-0">
                  <span className="text-xs font-semibold text-gray-200 block">
                    {t('settings.illustrated_backdrops', 'Illustrated Backdrops')}
                  </span>
                  <span className="text-[11px] text-gray-400 block">
                    {t('settings.illustrated_backdrops_desc', 'Show full-screen scenario artwork. Turn off for a clean pattern background that highlights frosted glass.')}
                  </span>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={illustratedBackdrops}
                  aria-label={t('settings.illustrated_backdrops', 'Illustrated Backdrops')}
                  onClick={() => setIllustratedBackdrops(!illustratedBackdrops)}
                  className={`hk-toggle ${illustratedBackdrops ? 'is-on' : ''}`}
                />
              </div>

              <div className={`flex items-center justify-between gap-4 pt-1 transition-opacity ${illustratedBackdrops ? '' : 'opacity-50'}`}>
                <div className="min-w-0">
                  <span className="text-xs font-semibold text-gray-200 block">
                    {t('settings.ambient_backdrop', 'Ambient Scene Backdrop')}
                  </span>
                  <span className="text-[11px] text-gray-400 block">
                    {t('settings.ambient_backdrop_desc', 'Softly blend live AI-generated scene illustrations into the full-screen background.')}
                  </span>
                </div>
                <button
                  type="button"
                  role="switch"
                  disabled={!illustratedBackdrops}
                  aria-checked={ambientSceneBackdrop}
                  aria-label={t('settings.ambient_backdrop', 'Ambient Scene Backdrop')}
                  onClick={() => setAmbientSceneBackdrop(!ambientSceneBackdrop)}
                  className={`hk-toggle ${ambientSceneBackdrop ? 'is-on' : ''} disabled:cursor-not-allowed`}
                />
              </div>
            </div>

            {/* Section 2: Typography & Custom Fonts */}
            {(() => {
              const uiResolved = resolveFontSelection(uiFont, 'ui', customFonts);
              const narrationResolved = resolveFontSelection(narrationFont, 'narration', customFonts);
              const hasFontOverride =
                uiFont !== THEME_DEFAULT_FONT_ID || narrationFont !== THEME_DEFAULT_FONT_ID;

              return (
                <div className="hk-flat-section space-y-3.5">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="space-y-1 min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <Type size={16} className="text-fantasy-accent shrink-0" />
                        <span className="font-semibold text-gray-100 text-sm">
                          {t('settings.fonts_title', 'Fonts')}
                        </span>
                      </div>
                      <p className="text-xs text-gray-400 leading-relaxed">
                        {t(
                          'settings.fonts_desc',
                          'Customize interface and story narration fonts independently, or drop .ttf/.otf/.woff/.woff2 files into custom_fonts/.'
                        )}
                      </p>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {hasFontOverride && (
                        <button
                          type="button"
                          onClick={() => {
                            setUiFont(THEME_DEFAULT_FONT_ID);
                            setNarrationFont(THEME_DEFAULT_FONT_ID);
                          }}
                          className="text-[10px] font-semibold px-2.5 py-1 rounded-lg border border-fantasy-border/50 text-gray-300 hover:text-fantasy-accent hover:border-fantasy-accent/50 transition-colors"
                        >
                          {t('settings.reset_default', 'Reset')}
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={refreshCustomFonts}
                        disabled={customFontsLoading}
                        className="inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-lg border border-fantasy-border/50 bg-gray-500/10 text-gray-200 hover:text-fantasy-accent hover:border-fantasy-accent/50 transition-colors disabled:opacity-50"
                      >
                        <RefreshCw
                          size={12}
                          className={customFontsLoading ? 'animate-spin' : ''}
                        />
                        <span>{t('settings.fonts_refresh', 'Refresh')}</span>
                      </button>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div className="space-y-1.5 min-w-0">
                      <label
                        htmlFor="hk-ui-font-select"
                        className="text-xs font-semibold text-gray-200 block"
                      >
                        {t('settings.font_interface', 'Interface Font')}
                      </label>
                      <select
                        id="hk-ui-font-select"
                        value={uiResolved.valid ? uiFont : THEME_DEFAULT_FONT_ID}
                        onChange={(e) => setUiFont(e.target.value)}
                        className="hk-input text-xs bg-fantasy-panel text-gray-100"
                      >
                        <optgroup label={t('settings.fonts_builtin', 'Built-in Presets')}>
                          {UI_FONT_PRESETS.map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.labelKey ? t(p.labelKey, p.defaultLabel) : p.label}
                            </option>
                          ))}
                        </optgroup>
                        {customFonts.length > 0 && (
                          <optgroup
                            label={t('settings.fonts_custom_group', 'Custom Fonts (custom_fonts/)')}
                          >
                            {customFonts.map((cf) => (
                              <option key={cf.id} value={cf.id}>
                                {cf.label}
                              </option>
                            ))}
                          </optgroup>
                        )}
                      </select>
                    </div>

                    <div className="space-y-1.5 min-w-0">
                      <label
                        htmlFor="hk-narration-font-select"
                        className="text-xs font-semibold text-gray-200 block"
                      >
                        {t('settings.font_narration', 'Narration Font')}
                      </label>
                      <select
                        id="hk-narration-font-select"
                        value={
                          narrationResolved.valid ? narrationFont : THEME_DEFAULT_FONT_ID
                        }
                        onChange={(e) => setNarrationFont(e.target.value)}
                        className="hk-input text-xs bg-fantasy-panel text-gray-100"
                      >
                        <optgroup label={t('settings.fonts_builtin', 'Built-in Presets')}>
                          {NARRATION_FONT_PRESETS.map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.labelKey ? t(p.labelKey, p.defaultLabel) : p.label}
                            </option>
                          ))}
                        </optgroup>
                        {customFonts.length > 0 && (
                          <optgroup
                            label={t('settings.fonts_custom_group', 'Custom Fonts (custom_fonts/)')}
                          >
                            {customFonts.map((cf) => (
                              <option key={cf.id} value={cf.id}>
                                {cf.label}
                              </option>
                            ))}
                          </optgroup>
                        )}
                      </select>
                    </div>
                  </div>

                  <div className="text-[11px] text-gray-400">
                    {customFonts.length > 0 ? (
                      <span className="text-fantasy-accent font-medium">
                        {t('settings.fonts_custom_loaded', {
                          count: customFonts.length,
                          defaultValue: `${customFonts.length} custom font(s) loaded from custom_fonts/`,
                        })}
                      </span>
                    ) : (
                      <span>
                        {t(
                          'settings.fonts_empty_hint',
                          'Drop .ttf, .otf, .woff, or .woff2 files into the custom_fonts/ folder, then click Refresh.'
                        )}
                      </span>
                    )}
                  </div>

                  {/* Live Typography Preview */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                    <div
                      className="p-3 rounded-xl border border-fantasy-border/40 bg-black/25 space-y-1 min-w-0"
                      style={{ fontFamily: uiResolved.stack || 'var(--font-sans)' }}
                    >
                      <div className="text-[10px] font-semibold uppercase tracking-wider text-fantasy-accent">
                        {t('settings.font_preview_ui', 'Interface Preview')}
                      </div>
                      <div className="text-xs text-gray-100 font-semibold">
                        HP 300/300 • MP 75/75 • Turn 12
                      </div>
                      <div className="text-[11px] text-gray-400">
                        {t(
                          'settings.font_preview_ui_sample',
                          'Menus, buttons, stats, and action pills use this font.'
                        )}
                      </div>
                    </div>

                    <div
                      className="p-3 rounded-xl border border-fantasy-border/40 bg-black/25 space-y-1 min-w-0"
                      style={{
                        fontFamily:
                          narrationResolved.stack ||
                          "ui-serif, Georgia, Cambria, 'Times New Roman', Times, serif",
                      }}
                    >
                      <div
                        className="text-[10px] font-semibold uppercase tracking-wider text-fantasy-accent"
                        style={{ fontFamily: uiResolved.stack || 'var(--font-sans)' }}
                      >
                        {t('settings.font_preview_narration', 'Narration Preview')}
                      </div>
                      <p className="text-sm text-gray-100 leading-relaxed">
                        {t(
                          'settings.font_preview_narration_sample',
                          'Lantern light flickers across the wet cobblestones as an unspoken promise lingers in the rain.'
                        )}{' '}
                        <strong>Bold</strong> · <em>Italic</em>
                      </p>
                    </div>
                  </div>
                </div>
              );
            })()}

            {/* Section 4: Combat UI Toggles */}
            <div className="hk-flat-section space-y-3">
              <label className="text-xs font-semibold text-gray-300 uppercase tracking-wider flex items-center gap-1.5">
                <Activity size={14} className="text-fantasy-accent" />
                {t('settings.combat_interface', 'Combat Interface')}
              </label>
              <div className="flex items-center justify-between gap-4">
                <div>
                  <span className="text-xs font-semibold text-gray-200 block">
                    {t('settings.show_enemy_hp', 'Show Enemy Health Bars')}
                  </span>
                  <span className="text-[11px] text-gray-400">
                    {t('settings.show_enemy_hp_desc', 'Display exact HP values and visual bars for enemies')}
                  </span>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={(settings.show_enemy_hp ?? 1) === 1}
                  aria-label={t('settings.show_enemy_hp', 'Show Enemy Health Bars')}
                  onClick={() => updateSettings({ show_enemy_hp: (settings.show_enemy_hp ?? 1) === 1 ? 0 : 1 })}
                  disabled={saving}
                  className={`hk-toggle ${(settings.show_enemy_hp ?? 1) === 1 ? 'is-on' : ''}`}
                />
              </div>
              <div className="flex items-center justify-between gap-4">
                <div>
                  <span className="text-xs font-semibold text-gray-200 block">
                    {t('settings.show_enemy_intent', 'Show Combat Intent')}
                  </span>
                  <span className="text-[11px] text-gray-400">
                    {t('settings.show_enemy_intent_desc', 'Display what actions enemies are planning')}
                  </span>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={(settings.show_enemy_intent ?? 1) === 1}
                  aria-label={t('settings.show_enemy_intent', 'Show Combat Intent')}
                  onClick={() => updateSettings({ show_enemy_intent: (settings.show_enemy_intent ?? 1) === 1 ? 0 : 1 })}
                  disabled={saving}
                  className={`hk-toggle ${(settings.show_enemy_intent ?? 1) === 1 ? 'is-on' : ''}`}
                />
              </div>
            </div>
          </div>
        )}

        {activeTab === 'narration' && (() => {
          const rawVerb = (settings.verbosity || 'vivid').toLowerCase();
          const activeStyle = rawVerb === 'concise' || rawVerb === 'direct' ? 'normal' : rawVerb;
          const activePacing =
            settings.narrative_pacing || (rawVerb === 'concise' || rawVerb === 'direct' ? 'concise' : 'balanced');
          const activeDialogue = settings.dialogue_mode || 'adaptive';
          return (
            <div>
              {/* Section 1: Narrative Style (6 Options) */}
              <div className="hk-flat-section space-y-2.5">
                <label className="text-xs font-semibold text-gray-300 uppercase tracking-wider flex items-center gap-1.5">
                  <BookOpen size={14} className="text-fantasy-accent" />
                  {t('settings.narrative_style', 'Narrative Style')}
                </label>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {[
                    { id: 'vivid', label: t('settings.style_vivid_label', '✨ Vivid'), desc: t('settings.style_vivid_desc', 'Deep sensory prose') },
                    { id: 'normal', label: t('settings.style_normal_label', '⚖️ Standard'), desc: t('settings.style_normal_desc', 'Clear modern prose') },
                    { id: 'noir', label: t('settings.style_noir_label', '🕵️ Noir'), desc: t('settings.style_noir_desc', 'Cynical detective pulp') },
                    { id: 'witty', label: t('settings.style_witty_label', '🎩 Witty'), desc: t('settings.style_witty_desc', 'Dry deadpan satire') },
                    { id: 'shakespearean', label: t('settings.style_shakespearean_label', '🎭 Shakespearean'), desc: t('settings.style_shakespearean_desc', 'Ornate dramatic flourish') },
                    { id: 'brainrot', label: t('settings.style_brainrot_label', '🧠 Brainrot'), desc: t('settings.style_brainrot_desc', 'Gen Z / Alpha meme slang') },
                  ].map((v) => {
                    const isSelected = activeStyle === v.id;
                    return (
                      <MotionButton
                        key={v.id}
                        onClick={() => handleVerbosityChange(v.id)}
                        className={`flex flex-col p-2.5 rounded-xl border text-left transition-all ${
                          isSelected
                            ? 'bg-fantasy-accent/15 border-fantasy-accent text-fantasy-accent'
                            : 'bg-gray-500/10 border-fantasy-border/40 text-gray-300 hover:border-fantasy-border hover:text-gray-100'
                        }`}
                      >
                        <div className="flex items-center justify-between text-xs font-bold mb-1 w-full">
                          <span>{v.label}</span>
                          {isSelected && <Check size={12} />}
                        </div>
                        <span className="text-[10px] opacity-75 leading-tight">{v.desc}</span>
                      </MotionButton>
                    );
                  })}
                </div>
              </div>

              {/* Section 2: Narrative Pacing (3 Options) */}
              <div className="hk-flat-section space-y-2.5">
                <label className="text-xs font-semibold text-gray-300 uppercase tracking-wider flex items-center gap-1.5">
                  <Zap size={14} className="text-fantasy-accent" />
                  {t('settings.narrative_pacing', 'Narrative Pacing')}
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { id: 'concise', label: t('settings.pacing_concise_label', '⚡ Concise'), desc: t('settings.pacing_concise_desc', '1 short paragraph') },
                    { id: 'balanced', label: t('settings.pacing_balanced_label', '⚖️ Balanced'), desc: t('settings.pacing_balanced_desc', 'Standard 2-3 paras') },
                    { id: 'novelistic', label: t('settings.pacing_novelistic_label', '📖 Novelistic'), desc: t('settings.pacing_novelistic_desc', 'Slow-burn detail') },
                  ].map((p) => {
                    const isSelected = activePacing === p.id;
                    return (
                      <MotionButton
                        key={p.id}
                        onClick={() => handlePacingChange(p.id)}
                        className={`flex flex-col p-2.5 rounded-xl border text-left transition-all ${
                          isSelected
                            ? 'bg-fantasy-accent/15 border-fantasy-accent text-fantasy-accent'
                            : 'bg-gray-500/10 border-fantasy-border/40 text-gray-300 hover:border-fantasy-border hover:text-gray-100'
                        }`}
                      >
                        <div className="flex items-center justify-between text-xs font-bold mb-1 w-full">
                          <span>{p.label}</span>
                          {isSelected && <Check size={12} />}
                        </div>
                        <span className="text-[10px] opacity-75 leading-tight">{p.desc}</span>
                      </MotionButton>
                    );
                  })}
                </div>
              </div>

              {/* Section 3: Dialogue Style (6 Options) */}
              <div className="hk-flat-section space-y-2.5">
                <label className="text-xs font-semibold text-gray-300 uppercase tracking-wider flex items-center gap-1.5">
                  <Sliders size={14} className="text-fantasy-accent" />
                  {t('settings.dialogue_mode', 'Dialogue Style')}
                </label>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {[
                    { id: 'off', label: t('settings.dialogue_off_label', '🔇 Off'), desc: t('settings.dialogue_off_desc', 'Pure narration only') },
                    { id: 'minimal', label: t('settings.dialogue_minimal_label', '💬 Minimal'), desc: t('settings.dialogue_minimal_desc', 'Brief spoken lines') },
                    { id: 'balanced', label: t('settings.dialogue_balanced_label', '⚖️ Balanced'), desc: t('settings.dialogue_balanced_desc', 'Natural conversation') },
                    { id: 'adaptive', label: t('settings.dialogue_adaptive_label', '🧠 Adaptive'), desc: t('settings.dialogue_adaptive_desc', 'Context-driven banter') },
                    { id: 'rich', label: t('settings.dialogue_rich_label', '🎭 Rich'), desc: t('settings.dialogue_rich_desc', 'Novel-style banter') },
                    { id: 'script', label: t('settings.dialogue_script_label', '🎬 Script'), desc: t('settings.dialogue_script_desc', 'Stage-play lines') },
                  ].map((d) => {
                    const isSelected = activeDialogue === d.id;
                    return (
                      <MotionButton
                        key={d.id}
                        onClick={() => handleDialogueModeChange(d.id)}
                        className={`flex flex-col p-2.5 rounded-xl border text-left transition-all ${
                          isSelected
                            ? 'bg-fantasy-accent/15 border-fantasy-accent text-fantasy-accent'
                            : 'bg-gray-500/10 border-fantasy-border/40 text-gray-300 hover:border-fantasy-border hover:text-gray-100'
                        }`}
                      >
                        <div className="flex items-center justify-between text-xs font-bold mb-1 w-full">
                          <span>{d.label}</span>
                          {isSelected && <Check size={12} />}
                        </div>
                        <span className="text-[10px] opacity-75 leading-tight">{d.desc}</span>
                      </MotionButton>
                    );
                  })}
                </div>
              </div>
            </div>
          );
        })()}

        {activeTab === 'language' && (
          <div>
            {/* Section 0A: Interface Language (UI & System) */}
            <div className="hk-flat-section space-y-3">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <Monitor size={16} className="text-fantasy-accent" />
                  <span className="font-semibold text-gray-200 text-sm">{t('settings.ui_language')}</span>
                </div>
                <p className="text-xs text-gray-400 leading-relaxed">{t('settings.ui_language_desc')}</p>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
                {AVAILABLE_LANGUAGES.map((lang) => {
                  const activeCode = (settings.ui_language || i18n.language || 'en').split('-')[0].toLowerCase();
                  const isSelected = activeCode === lang.code;
                  return (
                    <MotionButton
                      key={lang.code}
                      onClick={() => {
                        i18n.changeLanguage(lang.code);
                        localStorage.setItem('hikayat_ui_language', lang.code);
                        localStorage.setItem('hikayat_language', lang.code);
                        updateSettings({ ui_language: lang.code });
                      }}
                      disabled={saving}
                      className={`px-3 py-2 rounded-xl text-xs font-medium border flex items-center justify-center gap-2 transition-all ${
                        isSelected
                          ? 'bg-fantasy-accent/20 border-fantasy-accent text-fantasy-accent font-bold'
                          : 'bg-gray-500/10 border-fantasy-border/40 text-gray-300 hover:border-fantasy-border hover:text-gray-100'
                      }`}
                    >
                      <span className="text-sm">{lang.flag}</span>
                      <span>{lang.label}</span>
                    </MotionButton>
                  );
                })}
              </div>
            </div>

            {/* Section 0B: Game & Story Language (Narration & Mechanics) */}
            <div className="hk-flat-section space-y-3">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <Sparkles size={16} className="text-amber-400" />
                  <span className="font-semibold text-gray-200 text-sm">{t('settings.narration_language')}</span>
                </div>
                <p className="text-xs text-gray-400 leading-relaxed">{t('settings.narration_language_desc')}</p>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
                {AVAILABLE_LANGUAGES.map((lang) => {
                  const activeCode = (settings.narration_language || settings.language || 'en').split('-')[0].toLowerCase();
                  const isSelected = activeCode === lang.code;
                  return (
                    <MotionButton
                      key={lang.code}
                      onClick={() => {
                        updateSettings({ narration_language: lang.code, language: lang.code });
                      }}
                      disabled={saving}
                      className={`px-3 py-2 rounded-xl text-xs font-medium border flex items-center justify-center gap-2 transition-all ${
                        isSelected
                          ? 'bg-amber-500/20 border-amber-500/60 text-amber-300 font-bold'
                          : 'bg-gray-500/10 border-fantasy-border/40 text-gray-300 hover:border-fantasy-border hover:text-gray-100'
                      }`}
                    >
                      <span className="text-sm">{lang.flag}</span>
                      <span>{lang.label}</span>
                    </MotionButton>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'telemetry' && (
          <div>
            {/* Live LLM Telemetry & Circuit Breakers */}
            <div className="hk-flat-section space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-wider text-fantasy-accent flex items-center gap-1.5">
                  <Activity size={14} />
                  <span>{t('settings.telemetry_title', 'LLM Gateway Telemetry & Circuit Breakers')}</span>
                </h3>
                <button
                  type="button"
                  onClick={loadDiagnostics}
                  disabled={loadingTelemetry}
                  className="text-xs text-gray-400 hover:text-fantasy-accent flex items-center gap-1"
                >
                  <RefreshCw size={12} className={loadingTelemetry ? 'animate-spin' : ''} />
                  <span>{t('settings.refresh', 'Refresh')}</span>
                </button>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
                <div className="bg-gray-500/10 border border-fantasy-border/40 rounded-xl p-2">
                  <div className="text-[10px] text-gray-400 uppercase">{t('settings.total_calls', 'Total Calls')}</div>
                  <div className="font-mono text-sm font-bold text-gray-100">{telemetry?.total_calls ?? 0}</div>
                </div>
                <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-xl p-2">
                  <div className="text-[10px] text-emerald-400 uppercase">{t('settings.succeeded', 'Succeeded')}</div>
                  <div className="font-mono text-sm font-bold text-emerald-300">{telemetry?.successful_calls ?? 0}</div>
                </div>
                <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-2">
                  <div className="text-[10px] text-red-400 uppercase">{t('settings.failed', 'Failed')}</div>
                  <div className="font-mono text-sm font-bold text-red-300">{telemetry?.failed_calls ?? 0}</div>
                </div>
                <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-2">
                  <div className="text-[10px] text-amber-400 uppercase">{t('settings.failovers', 'Failovers')}</div>
                  <div className="font-mono text-sm font-bold text-amber-300">{telemetry?.fallback_activations ?? 0}</div>
                </div>
              </div>

              <div className="space-y-1.5 pt-2">
                <div className="text-[10px] uppercase tracking-wider text-gray-400 font-semibold">
                  {t('settings.circuit_breakers', 'Endpoint Circuit Breakers')}
                </div>
                {circuitBreakers.length === 0 ? (
                  <div className="text-xs text-emerald-400 font-mono bg-emerald-500/10 border border-emerald-500/30 rounded-xl p-2">
                    {t('settings.circuit_all_healthy', '🟢 All LLM endpoints healthy (Circuit CLOSED)')}
                  </div>
                ) : (
                  circuitBreakers.map(([modelKey, cb]) => (
                    <div
                      key={modelKey}
                      className="flex items-center justify-between gap-2 bg-gray-500/10 border border-fantasy-border/40 rounded-xl px-2.5 py-1.5 text-xs font-mono"
                    >
                      <span className="text-gray-300 truncate min-w-0">{modelKey}</span>
                      {cb.is_open ? (
                        <span className="text-red-300 bg-red-950/70 border border-red-800 px-2 py-0.5 rounded text-[10px] shrink-0">
                          🔴 {t('settings.circuit_open', 'OPEN')} ({cb.cooldown_remaining_s}s)
                        </span>
                      ) : (
                        <span className="text-emerald-300 bg-emerald-950/60 border border-emerald-800/60 px-2 py-0.5 rounded text-[10px] shrink-0">
                          🟢 {t('settings.circuit_closed', 'CLOSED')}
                        </span>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Developer Sandbox Controls */}
            {user?.user_id && (
              <div className="hk-flat-section space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-amber-400 flex items-center gap-1.5">
                    <Terminal size={14} />
                    <span>{t('settings.sandbox_overrides', 'Developer Sandbox Overrides')}</span>
                  </h3>
                  {debugNotice && (
                    <span className="text-[10px] font-mono text-emerald-400">{debugNotice}</span>
                  )}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[10px] uppercase tracking-wider text-gray-400 mb-1">
                      {t('settings.skill_check_override', 'Skill Check Override')}
                    </label>
                    <select
                      value={debugCheckMode}
                      onChange={(e) =>
                        handleDebugUpdate(
                          { debug_check_mode: e.target.value },
                          t('settings.notice_check_updated', 'Skill check mode updated')
                        )
                      }
                      className="w-full bg-fantasy-dark/70 border border-fantasy-border/60 p-2 rounded-lg text-xs text-gray-100"
                    >
                      <option value="off">{t('settings.odds_normal', 'Normal (Standard Odds)')}</option>
                      <option value="always_success">{t('settings.odds_always_succeed', 'Always Succeed (100%)')}</option>
                      <option value="always_fail">{t('settings.odds_always_fail', 'Always Fail (0%)')}</option>
                      <option value="always_crit_success">{t('settings.odds_force_crit_success', 'Force Critical Success')}</option>
                      <option value="always_crit_fail">{t('settings.odds_force_crit_failure', 'Force Critical Failure')}</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-[10px] uppercase tracking-wider text-gray-400 mb-1">
                      {t('settings.stat_override', 'Stat Override')}
                    </label>
                    <select
                      value={debugStatMode}
                      onChange={(e) =>
                        handleDebugUpdate(
                          { debug_stat_mode: e.target.value },
                          t('settings.notice_stat_updated', 'Stat mode updated')
                        )
                      }
                      className="w-full bg-fantasy-dark/70 border border-fantasy-border/60 p-2 rounded-lg text-xs text-gray-100"
                    >
                      <option value="off">{t('settings.stats_normal', 'Normal Character Stats')}</option>
                      <option value="max">{t('settings.stats_god_mode', 'God Mode (All Stats 10)')}</option>
                      <option value="min">{t('settings.stats_weakened', 'Weakened (All Stats 1)')}</option>
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2 pt-2">
                  <MotionButton
                    onClick={() =>
                      handleDebugUpdate(
                        { action: 'full_heal' },
                        t('settings.notice_full_heal', 'Character fully restored!')
                      )
                    }
                    className="py-1.5 px-3 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/40 text-emerald-300 text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors"
                  >
                    <HeartPulse size={13} />
                    <span>{t('settings.full_heal', 'Full Heal HP/MP')}</span>
                  </MotionButton>
                  <MotionButton
                    onClick={() =>
                      handleDebugUpdate(
                        { action: 'hp_to_1' },
                        t('settings.notice_hp_to_1', 'HP set to 1!')
                      )
                    }
                    className="py-1.5 px-3 rounded-lg bg-red-500/15 hover:bg-red-500/25 border border-red-500/40 text-red-300 text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors"
                  >
                    <Skull size={13} />
                    <span>{t('settings.set_hp_one', 'Set HP to 1')}</span>
                  </MotionButton>
                  <MotionButton
                    onClick={() =>
                      handleDebugUpdate(
                        { debug_reveal_all_info: debugRevealAll ? 0 : 1 },
                        debugRevealAll
                          ? t('settings.notice_npc_locked', 'NPC Info Lock Restored')
                          : t('settings.notice_npc_revealed', 'All NPC Info Revealed!')
                      )
                    }
                    className={`py-1.5 px-3 rounded-lg border text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors ${
                      debugRevealAll
                        ? 'bg-purple-500/25 border-purple-500 text-purple-200'
                        : 'bg-purple-500/15 hover:bg-purple-500/25 border-purple-500/40 text-purple-300'
                    }`}
                  >
                    <span>
                      {debugRevealAll
                        ? t('settings.npc_info_revealed', '👁️ NPC Info: Revealed')
                        : t('settings.reveal_all_npc_info', '👁️ Reveal All NPC Info')}
                    </span>
                  </MotionButton>
                  <MotionButton
                    onClick={() =>
                      handleDebugUpdate(
                        { action: 'force_enemy', session_id: session?.id },
                        t('settings.notice_enemy_spawned', 'Dummy enemy spawned!')
                      )
                    }
                    className="py-1.5 px-3 rounded-lg bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/40 text-amber-300 text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors"
                  >
                    <span>{t('settings.force_enemy', '👹 Force Enemy (Spawn Dummy)')}</span>
                  </MotionButton>
                  <MotionButton
                    onClick={() =>
                      handleDebugUpdate(
                        {
                          action: 'reset_all',
                          debug_stat_mode: 'off',
                          debug_check_mode: 'off',
                          debug_reveal_all_info: 0,
                        },
                        t('settings.notice_sandbox_reset', 'All sandbox overrides reset!')
                      )
                    }
                    className="col-span-2 py-1.5 px-3 rounded-lg bg-gray-500/15 hover:bg-gray-500/25 border border-fantasy-border/40 text-gray-200 text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors"
                  >
                    <span>{t('settings.reset_overrides', '🔄 Reset All Overrides')}</span>
                  </MotionButton>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-fantasy-border/35 flex justify-end shrink-0">
        <MotionButton
          onClick={onClose}
          className="px-4 py-1.5 bg-fantasy-accent hover:bg-fantasy-accent/90 text-fantasy-dark font-bold text-xs uppercase tracking-wider rounded-lg transition-colors"
        >
          {t('settings.done', 'Done')}
        </MotionButton>
      </div>
    </AcrylicModal>
  );
};

export default SettingsModal;
