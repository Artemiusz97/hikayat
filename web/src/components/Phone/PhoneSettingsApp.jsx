import { useState, useMemo } from 'react';
import {
  Camera,
  Check,
  Clock,
  Image as ImageIcon,
  Layers,
  Moon,
  Settings,
  Shuffle,
  Sparkles,
  Sun,
} from 'lucide-react';
import { resolveScenarioBackdrop, resolveTimeOfDayPhase, TIME_OF_DAY_GRADES } from '../../theme/backgrounds';
import {
  AUTO_SCENARIO_WALLPAPER_ID,
  FOCAL_OBJECT_CLASS,
  IPHONE_DEFAULT_WALLPAPER_ID,
  SCENARIO_PHONE_WALLPAPERS,
  extractNpcPhotoWallpapers,
  extractSessionSceneWallpapers,
  getBuiltinWallpaperEntry,
} from './phoneWallpapers';

const PhoneSettingsApp = ({
  displayTime,
  session,
  mediaGallery = [],
  phonePrefs,
  setPhonePref,
  setSessionPhoneWallpaper,
  clockFormat,
  setClockFormat,
  activeWallpaper,
  onShuffleCarousel,
  t,
}) => {
  const [wpTab, setWpTab] = useState('builtin'); // 'builtin' | 'npc' | 'scenes'

  const sessionId = session?.id != null ? String(session.id) : null;
  const activeOverride = sessionId ? phonePrefs?.sessionWallpapers?.[sessionId] : null;
  const matchedScenarioId = resolveScenarioBackdrop(session);

  const npcWallpapers = useMemo(
    () => extractNpcPhotoWallpapers(mediaGallery, { includeIntimate: true }),
    [mediaGallery]
  );
  const sceneWallpapers = useMemo(
    () => extractSessionSceneWallpapers(session),
    [session]
  );
  const allCustomPoolItems = useMemo(
    () => [
      getBuiltinWallpaperEntry(IPHONE_DEFAULT_WALLPAPER_ID),
      ...SCENARIO_PHONE_WALLPAPERS.map((w) => getBuiltinWallpaperEntry(w.id)),
      ...extractNpcPhotoWallpapers(mediaGallery, {
        includeIntimate: Boolean(phonePrefs?.includeIntimateInCarousel),
      }),
      ...sceneWallpapers,
    ],
    [mediaGallery, phonePrefs?.includeIntimateInCarousel, sceneWallpapers]
  );

  const timePhase = resolveTimeOfDayPhase(displayTime, session?.current_minute);
  const timeGrade = TIME_OF_DAY_GRADES[timePhase] || 'none';
  const dimAlpha = Math.max(0, Math.min(0.7, (phonePrefs?.wallpaperDim ?? 25) / 100));
  const focalCls = FOCAL_OBJECT_CLASS[phonePrefs?.wallpaperFocal || 'center'] || 'object-center';
  const isGlass = phonePrefs?.uiStyle === 'glass';

  const handleSelectBuiltin = (wpId) => {
    if (sessionId && activeOverride) {
      setSessionPhoneWallpaper(sessionId, null);
    }
    setPhonePref('wallpaperId', wpId);
    if (phonePrefs?.carouselEnabled) {
      setPhonePref('carouselEnabled', false);
    }
  };

  const handleSelectSessionMedia = (entry) => {
    if (!sessionId || !entry) return;
    setSessionPhoneWallpaper(sessionId, {
      type: entry.type,
      id: entry.id,
      url: entry.url,
      label: entry.label,
    });
    if (phonePrefs?.carouselEnabled) {
      setPhonePref('carouselEnabled', false);
    }
  };

  const toggleCustomPoolId = (itemKey) => {
    const curr = Array.isArray(phonePrefs?.carouselCustomIds) ? phonePrefs.carouselCustomIds : [];
    const next = curr.includes(itemKey) ? curr.filter((k) => k !== itemKey) : [...curr, itemKey];
    setPhonePref('carouselCustomIds', next);
  };

  return (
    <div className="space-y-4 pb-3">
      {/* Header */}
      <div className="flex items-center justify-between pb-1.5 border-b border-neutral-800/80">
        <h4 className="font-bold text-sm text-gray-100 flex items-center gap-1.5">
          <Settings size={15} className="text-sky-400" />
          <span>{t('phone.apps.settings', 'Settings')}</span>
        </h4>
        <span className="text-[10px] font-mono text-gray-400 truncate max-w-[140px]">
          {activeWallpaper?.label || t('phone.wallpapers.iphone_default', 'Aurora Silk')}
        </span>
      </div>

      {/* Live Mini Phone Preview */}
      <div className="rounded-2xl border border-neutral-800 bg-neutral-900/70 p-2.5 space-y-2">
        <div className="flex items-center justify-between px-0.5">
          <span className="text-[10px] uppercase font-bold tracking-wider text-gray-400">
            {t('phone.settings.live_preview', 'Live Preview')}
          </span>
          <span className="text-[10px] font-mono text-sky-400">
            {isGlass
              ? t('phone.settings.style_glass', 'Frosted Glass')
              : t('phone.settings.style_classic', 'Classic Dark')}
          </span>
        </div>

        <div
          data-phone-style={phonePrefs?.uiStyle || 'classic'}
          className="relative h-36 rounded-xl overflow-hidden border border-neutral-800 flex flex-col justify-between p-2.5 select-none"
        >
          {activeWallpaper?.url ? (
            <img
              src={activeWallpaper.url}
              alt=""
              className={`absolute inset-0 w-full h-full object-cover ${focalCls} pointer-events-none`}
            />
          ) : (
            <div className="absolute inset-0 overflow-hidden pointer-events-none">
              <div className="w-full h-full hk-phone-wp-iphone" />
            </div>
          )}

          {phonePrefs?.dynamicTimeTint && timeGrade !== 'none' && (
            <div
              className="absolute inset-0 pointer-events-none"
              style={{ backgroundImage: timeGrade }}
            />
          )}
          <div
            className="absolute inset-0 pointer-events-none"
            style={{ backgroundColor: `rgba(0, 0, 0, ${dimAlpha})` }}
          />

          <div className="relative z-10 flex flex-col items-center pt-0.5">
            <span
              className={`text-2xl leading-none hk-phone-home-text tabular-nums ${
                phonePrefs?.clockStyle === 'serif'
                  ? 'font-rpg font-semibold tracking-wide'
                  : 'font-sans font-light tracking-tight'
              }`}
            >
              {displayTime}
            </span>
          </div>

          <div
            className={`relative z-10 rounded-xl px-2.5 py-1.5 flex items-center justify-between border ${
              isGlass ? 'hk-phone-chrome' : 'hk-phone-notif-classic border'
            }`}
          >
            <div className="flex items-center gap-1.5 min-w-0">
              <Sparkles size={12} className="text-sky-400 shrink-0" />
              <span
                className={`text-[10px] font-semibold truncate ${
                  isGlass ? 'text-gray-100' : 'hk-phone-home-text'
                }`}
              >
                {t('phone.settings.preview_sample', 'Theme & Wallpaper Active')}
              </span>
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-400/90" />
              <span className="w-2.5 h-2.5 rounded-full bg-pink-400/90" />
              <span className="w-2.5 h-2.5 rounded-full bg-violet-400/90" />
            </div>
          </div>
        </div>
      </div>

      {/* Smartphone UI Style */}
      <div className="bg-neutral-900/70 border border-neutral-800 rounded-2xl p-2.5 space-y-2">
        <div className="flex items-center gap-1.5 text-xs font-bold text-gray-200">
          <Layers size={13} className="text-sky-400" />
          <span>{t('phone.settings.ui_style', 'Smartphone UI Style')}</span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {[
            {
              id: 'classic',
              label: t('phone.settings.style_classic', 'Classic Dark'),
              desc: t('phone.settings.style_classic_desc', 'OLED apps, Home wallpaper'),
            },
            {
              id: 'glass',
              label: t('phone.settings.style_glass', 'Frosted Glass'),
              desc: t('phone.settings.style_glass_desc', 'Matches game acrylic theme'),
            },
          ].map((opt) => {
            const active = (phonePrefs?.uiStyle || 'classic') === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                onClick={() => setPhonePref('uiStyle', opt.id)}
                className={`text-left p-2.5 rounded-xl border transition-all cursor-pointer ${
                  active
                    ? 'bg-sky-600/25 border-sky-400/70 text-gray-100 ring-1 ring-sky-400/30'
                    : 'bg-neutral-950/70 border-neutral-800 text-gray-300 hover:border-neutral-700'
                }`}
              >
                <div className="flex items-center justify-between gap-1">
                  <span className="text-xs font-bold">{opt.label}</span>
                  {active && <Check size={12} className="text-sky-400 shrink-0" />}
                </div>
                <span className="text-[10px] text-gray-400 block mt-0.5 leading-snug">
                  {opt.desc}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Wallpaper Picker */}
      <div className="bg-neutral-900/70 border border-neutral-800 rounded-2xl p-2.5 space-y-2.5">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5 text-xs font-bold text-gray-200">
            <ImageIcon size={13} className="text-pink-400" />
            <span>{t('phone.settings.wallpaper_picker', 'Wallpaper')}</span>
          </div>
          {phonePrefs?.carouselEnabled && (
            <span className="text-[9px] font-bold px-2 py-0.5 rounded-full bg-pink-500/20 text-pink-300 border border-pink-500/40">
              {t('phone.settings.carousel_active_badge', 'Carousel Active')}
            </span>
          )}
        </div>

        {/* Sub-tabs */}
        <div className="grid grid-cols-3 gap-1 bg-neutral-950/80 p-1 rounded-xl border border-neutral-800">
          {[
            { id: 'builtin', label: t('phone.settings.tab_builtin', 'Built-in') },
            {
              id: 'npc',
              label: t('phone.settings.tab_npc', 'NPC ({{count}})', { count: npcWallpapers.length }),
            },
            {
              id: 'scenes',
              label: t('phone.settings.tab_scenes', 'Scenes ({{count}})', {
                count: sceneWallpapers.length,
              }),
            },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setWpTab(tab.id)}
              className={`py-1 px-1.5 rounded-lg text-[10px] font-bold transition-colors cursor-pointer truncate ${
                wpTab === tab.id
                  ? 'bg-pink-600/30 text-pink-200 border border-pink-500/50'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {wpTab === 'builtin' && (
          <div className="space-y-2">
            {/* Special quick choices: iPhone Default & Auto (Match Scenario) */}
            <div className="grid grid-cols-2 gap-2">
              {[
                {
                  id: IPHONE_DEFAULT_WALLPAPER_ID,
                  title: t('phone.wallpapers.iphone_default', 'Aurora Silk'),
                  sub: t('phone.wallpapers.iphone_default_sub', 'iPhone-style Default'),
                  previewCls: 'hk-phone-wp-iphone',
                  url: null,
                },
                {
                  id: AUTO_SCENARIO_WALLPAPER_ID,
                  title: t('phone.wallpapers.auto_scenario', 'Match Scenario'),
                  sub: t('phone.wallpapers.auto_scenario_sub', 'Auto-Follow World'),
                  previewCls: '',
                  url: getBuiltinWallpaperEntry(matchedScenarioId).url,
                },
              ].map((sp) => {
                const selected =
                  !activeOverride &&
                  !phonePrefs?.carouselEnabled &&
                  (phonePrefs?.wallpaperId || IPHONE_DEFAULT_WALLPAPER_ID) === sp.id;
                return (
                  <button
                    key={sp.id}
                    type="button"
                    onClick={() => handleSelectBuiltin(sp.id)}
                    className={`relative h-20 rounded-xl overflow-hidden border text-left p-2 flex flex-col justify-end cursor-pointer transition-all ${
                      selected
                        ? 'border-pink-400 ring-2 ring-pink-500/40'
                        : 'border-neutral-800 hover:border-neutral-600'
                    }`}
                  >
                    {sp.url ? (
                      <img
                        src={sp.url}
                        alt=""
                        className="absolute inset-0 w-full h-full object-cover pointer-events-none"
                      />
                    ) : (
                      <div className="absolute inset-0 overflow-hidden pointer-events-none">
                        <div className={`w-full h-full ${sp.previewCls}`} />
                      </div>
                    )}
                    <div className="absolute inset-0 hk-phone-thumb-scrim pointer-events-none" />
                    {selected && (
                      <span className="absolute top-1.5 right-1.5 w-4 h-4 rounded-full bg-pink-500 hk-phone-icon-glyph flex items-center justify-center">
                        <Check size={10} />
                      </span>
                    )}
                    <span className="relative z-10 text-[11px] font-bold hk-phone-home-text leading-tight">
                      {sp.title}
                    </span>
                    <span className="relative z-10 text-[9px] hk-phone-home-subtext leading-tight">
                      {sp.sub}
                    </span>
                  </button>
                );
              })}
            </div>

            {/* 11 Portrait Scenario Wallpapers */}
            <div className="grid grid-cols-3 gap-2">
              {SCENARIO_PHONE_WALLPAPERS.map((wp) => {
                const selected =
                  !activeOverride &&
                  !phonePrefs?.carouselEnabled &&
                  phonePrefs?.wallpaperId === wp.id;
                return (
                  <button
                    key={wp.id}
                    type="button"
                    onClick={() => handleSelectBuiltin(wp.id)}
                    className={`relative h-28 rounded-xl overflow-hidden border text-left p-1.5 flex flex-col justify-end cursor-pointer transition-all ${
                      selected
                        ? 'border-pink-400 ring-2 ring-pink-500/40'
                        : 'border-neutral-800 hover:border-neutral-600'
                    }`}
                  >
                    <img
                      src={wp.url}
                      alt={t(wp.labelKey, wp.defaultLabel)}
                      loading="lazy"
                      className="absolute inset-0 w-full h-full object-cover pointer-events-none"
                    />
                    <div className="absolute inset-0 hk-phone-thumb-scrim pointer-events-none" />
                    {selected && (
                      <span className="absolute top-1.5 right-1.5 w-4 h-4 rounded-full bg-pink-500 hk-phone-icon-glyph flex items-center justify-center">
                        <Check size={10} />
                      </span>
                    )}
                    <span className="relative z-10 text-[10px] font-bold hk-phone-home-text leading-tight line-clamp-2">
                      {t(wp.labelKey, wp.defaultLabel)}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {wpTab === 'npc' && (
          npcWallpapers.length === 0 ? (
            <div className="text-center py-6 px-3 border border-dashed border-neutral-800 rounded-xl space-y-1.5">
              <Camera size={22} className="mx-auto text-pink-400 opacity-50" />
              <p className="text-[11px] font-medium text-gray-300">
                {t('phone.settings.no_npc_photos', 'No generated NPC photos yet.')}
              </p>
              <p className="text-[10px] text-gray-500 leading-relaxed">
                {t(
                  'phone.settings.no_npc_photos_hint',
                  'Receive photos in DMs or generate them in Photo Vault to set them as your wallpaper.'
                )}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-2">
              {npcWallpapers.map((wp) => {
                const selected =
                  activeOverride?.type === 'npc_photo' &&
                  (String(activeOverride.id) === String(wp.id) || activeOverride.url === wp.url);
                return (
                  <button
                    key={wp.key}
                    type="button"
                    onClick={() => handleSelectSessionMedia(wp)}
                    className={`relative h-28 rounded-xl overflow-hidden border text-left p-1.5 flex flex-col justify-end cursor-pointer transition-all ${
                      selected
                        ? 'border-pink-400 ring-2 ring-pink-500/40'
                        : 'border-neutral-800 hover:border-neutral-600'
                    }`}
                  >
                    <img
                      src={wp.url}
                      alt={wp.label}
                      loading="lazy"
                      className="absolute inset-0 w-full h-full object-cover object-top pointer-events-none"
                    />
                    <div className="absolute inset-0 hk-phone-thumb-scrim pointer-events-none" />
                    {wp.isIntimate && (
                      <span className="absolute top-1 left-1 text-[8px] px-1 bg-red-950/85 text-red-300 rounded border border-red-700 font-bold">
                        18+
                      </span>
                    )}
                    {selected && (
                      <span className="absolute top-1.5 right-1.5 w-4 h-4 rounded-full bg-pink-500 hk-phone-icon-glyph flex items-center justify-center">
                        <Check size={10} />
                      </span>
                    )}
                    <span className="relative z-10 text-[10px] font-bold hk-phone-home-text leading-tight truncate">
                      {wp.label}
                    </span>
                  </button>
                );
              })}
            </div>
          )
        )}

        {wpTab === 'scenes' && (
          sceneWallpapers.length === 0 ? (
            <div className="text-center py-6 px-3 border border-dashed border-neutral-800 rounded-xl space-y-1.5">
              <ImageIcon size={22} className="mx-auto text-sky-400 opacity-50" />
              <p className="text-[11px] font-medium text-gray-300">
                {t('phone.settings.no_scene_images', 'No generated campaign scenes yet.')}
              </p>
              <p className="text-[10px] text-gray-500 leading-relaxed">
                {t(
                  'phone.settings.no_scene_images_hint',
                  'Turn illustrations generated during this campaign will appear here automatically.'
                )}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              {sceneWallpapers.map((wp) => {
                const selected =
                  activeOverride?.type === 'scene' && activeOverride.url === wp.url;
                return (
                  <button
                    key={wp.key}
                    type="button"
                    onClick={() => handleSelectSessionMedia(wp)}
                    className={`relative h-24 rounded-xl overflow-hidden border text-left p-2 flex flex-col justify-end cursor-pointer transition-all ${
                      selected
                        ? 'border-pink-400 ring-2 ring-pink-500/40'
                        : 'border-neutral-800 hover:border-neutral-600'
                    }`}
                  >
                    <img
                      src={wp.url}
                      alt={wp.label}
                      loading="lazy"
                      className={`absolute inset-0 w-full h-full object-cover ${focalCls} pointer-events-none`}
                    />
                    <div className="absolute inset-0 hk-phone-thumb-scrim pointer-events-none" />
                    {selected && (
                      <span className="absolute top-1.5 right-1.5 w-4 h-4 rounded-full bg-pink-500 hk-phone-icon-glyph flex items-center justify-center">
                        <Check size={10} />
                      </span>
                    )}
                    <span className="relative z-10 text-[10px] font-bold hk-phone-home-text leading-tight line-clamp-2">
                      {wp.label}
                    </span>
                  </button>
                );
              })}
            </div>
          )
        )}
      </div>

      {/* Wallpaper Carousel Mode */}
      <div className="bg-neutral-900/70 border border-neutral-800 rounded-2xl p-2.5 space-y-2.5">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 text-xs font-bold text-gray-200">
              <Shuffle size={13} className="text-emerald-400 shrink-0" />
              <span>{t('phone.settings.carousel_title', 'Wallpaper Carousel')}</span>
            </div>
            <p className="text-[10px] text-gray-400 mt-0.5">
              {t('phone.settings.carousel_desc', 'Auto-switch every time you open the phone')}
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={Boolean(phonePrefs?.carouselEnabled)}
            onClick={() => setPhonePref('carouselEnabled', !phonePrefs?.carouselEnabled)}
            className={`w-10 h-6 rounded-full transition-colors p-0.5 shrink-0 cursor-pointer flex items-center ${
              phonePrefs?.carouselEnabled ? 'bg-emerald-500 justify-end' : 'bg-neutral-700 justify-start'
            }`}
          >
            <span className="w-5 h-5 rounded-full bg-white shadow" />
          </button>
        </div>

        {phonePrefs?.carouselEnabled && (
          <div className="space-y-2.5 pt-1 border-t border-neutral-800/80">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] font-semibold text-gray-300">
                {t('phone.settings.carousel_pool', 'Rotation Pool')}
              </span>
              <button
                type="button"
                onClick={onShuffleCarousel}
                className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-emerald-600/25 hover:bg-emerald-600/40 text-emerald-300 border border-emerald-500/40 text-[10px] font-bold cursor-pointer transition-colors"
              >
                <Shuffle size={11} />
                <span>{t('phone.settings.next_wallpaper', 'Next Wallpaper')}</span>
              </button>
            </div>

            <div className="grid grid-cols-2 gap-1.5">
              {[
                { id: 'all_builtin', label: t('phone.settings.pool_all_builtin', 'All Built-in') },
                {
                  id: 'scenario_and_photos',
                  label: t('phone.settings.pool_scenario_photos', 'Scenario + Photos'),
                },
                { id: 'photos_only', label: t('phone.settings.pool_photos_only', 'Generated Photos') },
                { id: 'custom', label: t('phone.settings.pool_custom', 'Custom Picks') },
              ].map((pool) => (
                <button
                  key={pool.id}
                  type="button"
                  onClick={() => setPhonePref('carouselPool', pool.id)}
                  className={`py-1.5 px-2 rounded-lg text-[10px] font-bold border transition-colors cursor-pointer truncate ${
                    (phonePrefs?.carouselPool || 'all_builtin') === pool.id
                      ? 'bg-emerald-600/25 text-emerald-200 border-emerald-500/50'
                      : 'bg-neutral-950/70 text-gray-400 border-neutral-800 hover:text-gray-200'
                  }`}
                >
                  {pool.label}
                </button>
              ))}
            </div>

            {phonePrefs?.carouselPool === 'custom' && (
              <div className="space-y-1.5">
                <span className="text-[10px] text-gray-400 block">
                  {t('phone.settings.custom_pool_hint', 'Choose wallpapers in rotation:')}
                </span>
                <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto custom-scrollbar pr-0.5">
                  {allCustomPoolItems.map((item) => {
                    const checked = (phonePrefs?.carouselCustomIds || []).includes(item.key);
                    return (
                      <button
                        key={item.key}
                        type="button"
                        onClick={() => toggleCustomPoolId(item.key)}
                        className={`px-2 py-1 rounded-lg text-[10px] font-medium border flex items-center gap-1 cursor-pointer transition-colors ${
                          checked
                            ? 'bg-emerald-600/25 text-emerald-200 border-emerald-500/50'
                            : 'bg-neutral-950/60 text-gray-400 border-neutral-800 hover:text-gray-200'
                        }`}
                      >
                        {checked && <Check size={10} className="shrink-0" />}
                        <span className="truncate max-w-[115px]">
                          {item.labelKey ? t(item.labelKey, item.label) : item.label}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            <label className="flex items-center justify-between gap-2 pt-1 cursor-pointer">
              <span className="text-[10px] text-gray-300">
                {t('phone.settings.include_intimate', 'Include 18+ intimate photos in carousel')}
              </span>
              <input
                type="checkbox"
                checked={Boolean(phonePrefs?.includeIntimateInCarousel)}
                onChange={(e) => setPhonePref('includeIntimateInCarousel', e.target.checked)}
                className="rounded accent-pink-500 cursor-pointer"
              />
            </label>
          </div>
        )}
      </div>

      {/* Readability, Framing & Clock */}
      <div className="bg-neutral-900/70 border border-neutral-800 rounded-2xl p-2.5 space-y-3">
        <div className="flex items-center gap-1.5 text-xs font-bold text-gray-200">
          <Sun size={13} className="text-amber-400" />
          <span>{t('phone.settings.display_clock', 'Display & Clock')}</span>
        </div>

        {/* Dimming Slider */}
        <div className="space-y-1">
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-gray-300 font-medium">
              {t('phone.settings.wallpaper_dim', 'Wallpaper Dimming')}
            </span>
            <span className="font-mono tabular-nums text-amber-300 font-bold">
              {phonePrefs?.wallpaperDim ?? 25}%
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={70}
            step={5}
            value={phonePrefs?.wallpaperDim ?? 25}
            onChange={(e) => setPhonePref('wallpaperDim', Number(e.target.value))}
            className="w-full accent-pink-500 cursor-pointer"
          />
        </div>

        {/* Framing Toggle */}
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] text-gray-300 font-medium">
            {t('phone.settings.framing', 'Wallpaper Framing')}
          </span>
          <div className="flex bg-neutral-950/80 p-0.5 rounded-lg border border-neutral-800 gap-0.5">
            {[
              { id: 'top', label: t('phone.settings.focal_top', 'Top') },
              { id: 'center', label: t('phone.settings.focal_center', 'Center') },
              { id: 'bottom', label: t('phone.settings.focal_bottom', 'Bottom') },
            ].map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => setPhonePref('wallpaperFocal', f.id)}
                className={`px-2 py-0.5 rounded-md text-[10px] font-bold cursor-pointer transition-colors ${
                  (phonePrefs?.wallpaperFocal || 'center') === f.id
                    ? 'bg-pink-600/30 text-pink-200'
                    : 'text-gray-400 hover:text-gray-200'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {/* Blur Inside Apps */}
        <label className="flex items-center justify-between gap-2 cursor-pointer">
          <span className="text-[11px] text-gray-300 font-medium">
            {t('phone.settings.blur_in_apps', 'Blur wallpaper inside apps')}
          </span>
          <input
            type="checkbox"
            checked={phonePrefs?.blurInApps !== false}
            onChange={(e) => setPhonePref('blurInApps', e.target.checked)}
            className="rounded accent-pink-500 cursor-pointer"
          />
        </label>

        {/* Dynamic Time-of-Day Tint */}
        <label className="flex items-center justify-between gap-2 cursor-pointer">
          <span className="text-[11px] text-gray-300 font-medium flex items-center gap-1.5">
            <Moon size={12} className="text-indigo-400" />
            <span>{t('phone.settings.dynamic_tint', 'Dynamic day/night tint')}</span>
          </span>
          <input
            type="checkbox"
            checked={Boolean(phonePrefs?.dynamicTimeTint)}
            onChange={(e) => setPhonePref('dynamicTimeTint', e.target.checked)}
            className="rounded accent-indigo-500 cursor-pointer"
          />
        </label>

        {/* Clock Style & Format */}
        <div className="grid grid-cols-2 gap-2 pt-1 border-t border-neutral-800/80">
          <div className="space-y-1">
            <span className="text-[10px] text-gray-400 block">
              {t('phone.settings.clock_style', 'Clock Style')}
            </span>
            <div className="flex bg-neutral-950/80 p-0.5 rounded-lg border border-neutral-800 gap-0.5">
              {[
                { id: 'modern', label: t('phone.settings.clock_modern', 'Modern') },
                { id: 'serif', label: t('phone.settings.clock_serif', 'RPG Serif') },
              ].map((cs) => (
                <button
                  key={cs.id}
                  type="button"
                  onClick={() => setPhonePref('clockStyle', cs.id)}
                  className={`flex-1 py-1 rounded-md text-[10px] font-bold cursor-pointer transition-colors ${
                    (phonePrefs?.clockStyle || 'modern') === cs.id
                      ? 'bg-sky-600/30 text-sky-200'
                      : 'text-gray-400 hover:text-gray-200'
                  }`}
                >
                  {cs.label}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-1">
            <span className="text-[10px] text-gray-400 flex items-center gap-1">
              <Clock size={10} />
              <span>{t('phone.settings.clock_format', 'Clock Format')}</span>
            </span>
            <div className="flex bg-neutral-950/80 p-0.5 rounded-lg border border-neutral-800 gap-0.5">
              {['12h', '24h'].map((fmt) => (
                <button
                  key={fmt}
                  type="button"
                  onClick={() => setClockFormat(fmt)}
                  className={`flex-1 py-1 rounded-md text-[10px] font-bold uppercase cursor-pointer transition-colors ${
                    clockFormat === fmt
                      ? 'bg-sky-600/30 text-sky-200'
                      : 'text-gray-400 hover:text-gray-200'
                  }`}
                >
                  {fmt}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PhoneSettingsApp;
