import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { apiCall } from '../api/client';
import {
  THEME_DEFAULT_FONT_ID,
  applyFontVariables,
  syncCustomFontFaces,
} from '../utils/fonts';

const STORAGE_KEY = 'hikayat_ui_prefs_v1';
export const PREFS_VERSION = 2;

export const ACRYLIC_MODES = ['full', 'focused', 'solid'];
export const READING_MODES = ['scene', 'continuous'];
export const CLOCK_FORMATS = ['12h', '24h'];
export const DEFAULT_CLOCK_FORMAT = '24h';
export const PHONE_UI_STYLES = ['classic', 'glass'];
export const PHONE_CAROUSEL_POOLS = ['all_builtin', 'scenario_and_photos', 'photos_only', 'custom'];
export const PHONE_WALLPAPER_FOCALS = ['top', 'center', 'bottom'];
export const PHONE_CLOCK_STYLES = ['modern', 'serif'];
export const MIN_WALLPAPER_DIM = 0;
export const MAX_WALLPAPER_DIM = 70;
export const DEFAULT_WALLPAPER_DIM = 25;
const MAX_STORED_SESSION_WALLPAPERS = 30;
export const MIN_ACRYLIC_OPACITY = 5;
export const MAX_ACRYLIC_OPACITY = 95;
export const DEFAULT_ACRYLIC_OPACITY = 50;
export const MIN_TEXT_SCALE = 70;
export const MAX_TEXT_SCALE = 130;
export const DEFAULT_TEXT_SCALE = 100;
export const TEXT_SCALE_STEP = 5;

const clampOpacity = (value) => {
  const num = Number(value);
  if (!Number.isFinite(num)) return DEFAULT_ACRYLIC_OPACITY;
  return Math.min(MAX_ACRYLIC_OPACITY, Math.max(MIN_ACRYLIC_OPACITY, Math.round(num)));
};

const clampTextScale = (value) => {
  const num = Number(value);
  if (!Number.isFinite(num)) return DEFAULT_TEXT_SCALE;
  return Math.min(MAX_TEXT_SCALE, Math.max(MIN_TEXT_SCALE, Math.round(num)));
};

const clampWallpaperDim = (value) => {
  const num = Number(value);
  if (!Number.isFinite(num)) return DEFAULT_WALLPAPER_DIM;
  return Math.min(MAX_WALLPAPER_DIM, Math.max(MIN_WALLPAPER_DIM, Math.round(num)));
};

const sanitizeSessionWallpapers = (rawMap) => {
  if (!rawMap || typeof rawMap !== 'object') return {};
  const entries = Object.entries(rawMap)
    .filter(
      ([sid, val]) =>
        sid &&
        val &&
        typeof val === 'object' &&
        (val.type === 'npc_photo' || val.type === 'scene') &&
        typeof val.url === 'string' &&
        val.url.trim()
    )
    .slice(-MAX_STORED_SESSION_WALLPAPERS);
  return Object.fromEntries(entries);
};

export const DEFAULT_PHONE_PREFS = {
  uiStyle: 'classic',
  wallpaperId: 'iphone_default',
  sessionWallpapers: {},
  carouselEnabled: false,
  carouselPool: 'all_builtin',
  carouselCustomIds: [],
  includeIntimateInCarousel: false,
  wallpaperDim: DEFAULT_WALLPAPER_DIM,
  blurInApps: true,
  dynamicTimeTint: false,
  wallpaperFocal: 'center',
  clockStyle: 'modern',
};

const DEFAULT_HUD = {
  leftPanel: null, // null | 'utility' | 'map'
  actionBarCollapsed: false,
  actionsDockCollapsed: false,
  npcsCollapsed: false,
  outcomeCollapsed: false,
  epistemicCollapsed: false,
};

const DEFAULT_PREFS = {
  acrylicMode: 'full',
  acrylicOpacity: DEFAULT_ACRYLIC_OPACITY,
  textScale: DEFAULT_TEXT_SCALE,
  illustratedBackdrops: true,
  readingMode: 'continuous',
  clockFormat: DEFAULT_CLOCK_FORMAT,
  uiFont: THEME_DEFAULT_FONT_ID,
  narrationFont: THEME_DEFAULT_FONT_ID,
  ambientSceneBackdrop: false,
  hud: DEFAULT_HUD,
  phone: DEFAULT_PHONE_PREFS,
};

export const readStoredPrefs = () => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_PREFS;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return DEFAULT_PREFS;

    const storedVersion = Number(parsed.version) || 1;
    const acrylicMode = ACRYLIC_MODES.includes(parsed.acrylicMode)
      ? parsed.acrylicMode
      : DEFAULT_PREFS.acrylicMode;
    const acrylicOpacity =
      parsed.acrylicOpacity === undefined || parsed.acrylicOpacity === null
        ? DEFAULT_ACRYLIC_OPACITY
        : clampOpacity(parsed.acrylicOpacity);
    const textScale =
      parsed.textScale === undefined || parsed.textScale === null
        ? DEFAULT_TEXT_SCALE
        : clampTextScale(parsed.textScale);
    const illustratedBackdrops =
      typeof parsed.illustratedBackdrops === 'boolean'
        ? parsed.illustratedBackdrops
        : DEFAULT_PREFS.illustratedBackdrops;
    const rawReadingMode = READING_MODES.includes(parsed.readingMode)
      ? parsed.readingMode
      : DEFAULT_PREFS.readingMode;
    const readingMode =
      storedVersion < PREFS_VERSION && rawReadingMode === 'scene'
        ? 'continuous'
        : rawReadingMode;
    const clockFormat = CLOCK_FORMATS.includes(parsed.clockFormat)
      ? parsed.clockFormat
      : DEFAULT_PREFS.clockFormat;
    const uiFont =
      typeof parsed.uiFont === 'string' && parsed.uiFont.trim()
        ? parsed.uiFont.trim()
        : DEFAULT_PREFS.uiFont;
    const narrationFont =
      typeof parsed.narrationFont === 'string' && parsed.narrationFont.trim()
        ? parsed.narrationFont.trim()
        : DEFAULT_PREFS.narrationFont;
    const ambientSceneBackdrop =
      typeof parsed.ambientSceneBackdrop === 'boolean'
        ? parsed.ambientSceneBackdrop
        : DEFAULT_PREFS.ambientSceneBackdrop;

    const rawHud = parsed.hud && typeof parsed.hud === 'object' ? parsed.hud : {};
    const leftPanel =
      rawHud.leftPanel === 'utility' || rawHud.leftPanel === 'map'
        ? rawHud.leftPanel
        : null;

    const rawPhone = parsed.phone && typeof parsed.phone === 'object' ? parsed.phone : {};
    const phone = {
      uiStyle: PHONE_UI_STYLES.includes(rawPhone.uiStyle)
        ? rawPhone.uiStyle
        : DEFAULT_PHONE_PREFS.uiStyle,
      wallpaperId:
        typeof rawPhone.wallpaperId === 'string' && rawPhone.wallpaperId.trim()
          ? rawPhone.wallpaperId.trim()
          : DEFAULT_PHONE_PREFS.wallpaperId,
      sessionWallpapers: sanitizeSessionWallpapers(rawPhone.sessionWallpapers),
      carouselEnabled: Boolean(rawPhone.carouselEnabled),
      carouselPool: PHONE_CAROUSEL_POOLS.includes(rawPhone.carouselPool)
        ? rawPhone.carouselPool
        : DEFAULT_PHONE_PREFS.carouselPool,
      carouselCustomIds: Array.isArray(rawPhone.carouselCustomIds)
        ? rawPhone.carouselCustomIds.map((x) => String(x)).filter(Boolean).slice(0, 60)
        : [],
      includeIntimateInCarousel: Boolean(rawPhone.includeIntimateInCarousel),
      wallpaperDim:
        rawPhone.wallpaperDim === undefined || rawPhone.wallpaperDim === null
          ? DEFAULT_WALLPAPER_DIM
          : clampWallpaperDim(rawPhone.wallpaperDim),
      blurInApps:
        typeof rawPhone.blurInApps === 'boolean'
          ? rawPhone.blurInApps
          : DEFAULT_PHONE_PREFS.blurInApps,
      dynamicTimeTint: Boolean(rawPhone.dynamicTimeTint),
      wallpaperFocal: PHONE_WALLPAPER_FOCALS.includes(rawPhone.wallpaperFocal)
        ? rawPhone.wallpaperFocal
        : DEFAULT_PHONE_PREFS.wallpaperFocal,
      clockStyle: PHONE_CLOCK_STYLES.includes(rawPhone.clockStyle)
        ? rawPhone.clockStyle
        : DEFAULT_PHONE_PREFS.clockStyle,
    };

    return {
      acrylicMode,
      acrylicOpacity,
      textScale,
      illustratedBackdrops,
      readingMode,
      clockFormat,
      uiFont,
      narrationFont,
      ambientSceneBackdrop,
      hud: {
        leftPanel,
        actionBarCollapsed: Boolean(rawHud.actionBarCollapsed),
        actionsDockCollapsed: Boolean(rawHud.actionsDockCollapsed),
        npcsCollapsed: Boolean(rawHud.npcsCollapsed),
        outcomeCollapsed: Boolean(rawHud.outcomeCollapsed),
        epistemicCollapsed: Boolean(rawHud.epistemicCollapsed),
      },
      phone,
    };
  } catch {
    return DEFAULT_PREFS;
  }
};

const UiPreferencesContext = createContext(null);

export const UiPreferencesProvider = ({ children }) => {
  const [prefs, setPrefs] = useState(readStoredPrefs);
  const [customFonts, setCustomFonts] = useState([]);
  const [customFontsLoaded, setCustomFontsLoaded] = useState(false);
  const [customFontsLoading, setCustomFontsLoading] = useState(false);

  const refreshCustomFonts = useCallback(async () => {
    setCustomFontsLoading(true);
    try {
      const data = await apiCall('/api/fonts', { cache: 'no-store' });
      const list = Array.isArray(data?.fonts) ? data.fonts : [];
      setCustomFonts(list);
      syncCustomFontFaces(list);
      setCustomFontsLoaded(true);
    } catch {
      // ignore fetch failures (e.g. offline / server starting)
    } finally {
      setCustomFontsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshCustomFonts();
  }, [refreshCustomFonts]);

  useEffect(() => {
    document.documentElement.dataset.acrylic = prefs.acrylicMode;
    document.documentElement.style.setProperty(
      '--acrylic-alpha',
      (prefs.acrylicOpacity / 100).toFixed(2)
    );
    document.documentElement.style.setProperty(
      '--ui-text-scale',
      (prefs.textScale / 100).toFixed(2)
    );
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ ...prefs, version: PREFS_VERSION })
      );
    } catch {
      // ignore storage failures (private mode / quota)
    }
  }, [prefs]);

  useEffect(() => {
    applyFontVariables(prefs.uiFont, prefs.narrationFont, customFonts);
    if (customFontsLoaded) {
      const validIds = new Set(customFonts.map((f) => f?.id).filter(Boolean));
      const needsUiReset =
        typeof prefs.uiFont === 'string' &&
        prefs.uiFont.startsWith('custom:') &&
        !validIds.has(prefs.uiFont);
      const needsNarrationReset =
        typeof prefs.narrationFont === 'string' &&
        prefs.narrationFont.startsWith('custom:') &&
        !validIds.has(prefs.narrationFont);
      if (needsUiReset || needsNarrationReset) {
        setPrefs((prev) => ({
          ...prev,
          uiFont: needsUiReset ? THEME_DEFAULT_FONT_ID : prev.uiFont,
          narrationFont: needsNarrationReset ? THEME_DEFAULT_FONT_ID : prev.narrationFont,
        }));
      }
    }
  }, [prefs.uiFont, prefs.narrationFont, customFonts, customFontsLoaded]);

  const setAcrylicMode = useCallback((mode) => {
    if (!ACRYLIC_MODES.includes(mode)) return;
    setPrefs((prev) =>
      prev.acrylicMode === mode ? prev : { ...prev, acrylicMode: mode }
    );
  }, []);

  const cycleAcrylicMode = useCallback(() => {
    setPrefs((prev) => {
      const idx = ACRYLIC_MODES.indexOf(prev.acrylicMode);
      const next = ACRYLIC_MODES[(idx + 1) % ACRYLIC_MODES.length];
      return { ...prev, acrylicMode: next };
    });
  }, []);

  const setAcrylicOpacity = useCallback((opacity) => {
    const next = clampOpacity(opacity);
    setPrefs((prev) =>
      prev.acrylicOpacity === next ? prev : { ...prev, acrylicOpacity: next }
    );
  }, []);

  const setIllustratedBackdrops = useCallback((enabled) => {
    const next = Boolean(enabled);
    setPrefs((prev) =>
      prev.illustratedBackdrops === next
        ? prev
        : { ...prev, illustratedBackdrops: next }
    );
  }, []);

  const setReadingMode = useCallback((mode) => {
    if (!READING_MODES.includes(mode)) return;
    setPrefs((prev) =>
      prev.readingMode === mode ? prev : { ...prev, readingMode: mode }
    );
  }, []);

  const setClockFormat = useCallback((format) => {
    if (!CLOCK_FORMATS.includes(format)) return;
    setPrefs((prev) =>
      prev.clockFormat === format ? prev : { ...prev, clockFormat: format }
    );
  }, []);

  const setTextScale = useCallback((scale) => {
    const next = clampTextScale(scale);
    setPrefs((prev) =>
      prev.textScale === next ? prev : { ...prev, textScale: next }
    );
  }, []);

  const setUiFont = useCallback((fontId) => {
    const next =
      typeof fontId === 'string' && fontId.trim()
        ? fontId.trim()
        : THEME_DEFAULT_FONT_ID;
    setPrefs((prev) => (prev.uiFont === next ? prev : { ...prev, uiFont: next }));
  }, []);

  const setNarrationFont = useCallback((fontId) => {
    const next =
      typeof fontId === 'string' && fontId.trim()
        ? fontId.trim()
        : THEME_DEFAULT_FONT_ID;
    setPrefs((prev) =>
      prev.narrationFont === next ? prev : { ...prev, narrationFont: next }
    );
  }, []);

  const setAmbientSceneBackdrop = useCallback((enabled) => {
    const next = Boolean(enabled);
    setPrefs((prev) =>
      prev.ambientSceneBackdrop === next
        ? prev
        : { ...prev, ambientSceneBackdrop: next }
    );
  }, []);

  const setHudField = useCallback((key, value) => {
    if (!(key in DEFAULT_HUD)) return;
    setPrefs((prev) => ({
      ...prev,
      hud: { ...prev.hud, [key]: value },
    }));
  }, []);

  const toggleHudField = useCallback((key) => {
    if (!(key in DEFAULT_HUD) || key === 'leftPanel') return;
    setPrefs((prev) => ({
      ...prev,
      hud: { ...prev.hud, [key]: !prev.hud[key] },
    }));
  }, []);

  const toggleLeftPanel = useCallback((panel) => {
    if (panel !== 'utility' && panel !== 'map' && panel !== null) return;
    setPrefs((prev) => ({
      ...prev,
      hud: {
        ...prev.hud,
        leftPanel: prev.hud.leftPanel === panel ? null : panel,
      },
    }));
  }, []);

  const setPhonePref = useCallback((key, value) => {
    if (!(key in DEFAULT_PHONE_PREFS)) return;
    let nextVal = value;
    if (key === 'uiStyle' && !PHONE_UI_STYLES.includes(value)) return;
    if (key === 'carouselPool' && !PHONE_CAROUSEL_POOLS.includes(value)) return;
    if (key === 'wallpaperFocal' && !PHONE_WALLPAPER_FOCALS.includes(value)) return;
    if (key === 'clockStyle' && !PHONE_CLOCK_STYLES.includes(value)) return;
    if (key === 'wallpaperDim') nextVal = clampWallpaperDim(value);
    if (key === 'carouselEnabled' || key === 'includeIntimateInCarousel' || key === 'blurInApps' || key === 'dynamicTimeTint') {
      nextVal = Boolean(value);
    }
    if (key === 'carouselCustomIds') {
      nextVal = Array.isArray(value) ? value.map(String).filter(Boolean).slice(0, 60) : [];
    }
    if (key === 'wallpaperId') {
      nextVal = typeof value === 'string' && value.trim() ? value.trim() : DEFAULT_PHONE_PREFS.wallpaperId;
    }
    setPrefs((prev) => ({
      ...prev,
      phone: {
        ...prev.phone,
        [key]: nextVal,
      },
    }));
  }, []);

  const setSessionPhoneWallpaper = useCallback((sessionId, wallpaperEntryOrNull) => {
    if (sessionId == null || sessionId === '') return;
    const sidKey = String(sessionId);
    setPrefs((prev) => {
      const currentMap = { ...(prev.phone?.sessionWallpapers || {}) };
      if (!wallpaperEntryOrNull || typeof wallpaperEntryOrNull !== 'object' || !wallpaperEntryOrNull.url) {
        if (!(sidKey in currentMap)) return prev;
        delete currentMap[sidKey];
      } else {
        delete currentMap[sidKey];
        currentMap[sidKey] = {
          type: wallpaperEntryOrNull.type === 'scene' ? 'scene' : 'npc_photo',
          id: wallpaperEntryOrNull.id ?? null,
          url: String(wallpaperEntryOrNull.url),
          label: String(wallpaperEntryOrNull.label || ''),
        };
      }
      const trimmed = sanitizeSessionWallpapers(currentMap);
      return {
        ...prev,
        phone: {
          ...prev.phone,
          sessionWallpapers: trimmed,
        },
      };
    });
  }, []);

  const value = useMemo(
    () => ({
      acrylicMode: prefs.acrylicMode,
      setAcrylicMode,
      cycleAcrylicMode,
      acrylicOpacity: prefs.acrylicOpacity,
      setAcrylicOpacity,
      textScale: prefs.textScale,
      setTextScale,
      uiFont: prefs.uiFont,
      setUiFont,
      narrationFont: prefs.narrationFont,
      setNarrationFont,
      customFonts,
      customFontsLoading,
      refreshCustomFonts,
      illustratedBackdrops: prefs.illustratedBackdrops,
      setIllustratedBackdrops,
      readingMode: prefs.readingMode,
      setReadingMode,
      clockFormat: prefs.clockFormat,
      setClockFormat,
      ambientSceneBackdrop: prefs.ambientSceneBackdrop,
      setAmbientSceneBackdrop,
      hud: prefs.hud,
      setHudField,
      toggleHudField,
      toggleLeftPanel,
      phonePrefs: prefs.phone,
      setPhonePref,
      setSessionPhoneWallpaper,
    }),
    [
      prefs,
      customFonts,
      customFontsLoading,
      refreshCustomFonts,
      setAcrylicMode,
      cycleAcrylicMode,
      setAcrylicOpacity,
      setTextScale,
      setUiFont,
      setNarrationFont,
      setIllustratedBackdrops,
      setReadingMode,
      setClockFormat,
      setAmbientSceneBackdrop,
      setHudField,
      toggleHudField,
      toggleLeftPanel,
      setPhonePref,
      setSessionPhoneWallpaper,
    ]
  );

  return (
    <UiPreferencesContext.Provider value={value}>
      {children}
    </UiPreferencesContext.Provider>
  );
};

export const useUiPreferences = () => {
  const ctx = useContext(UiPreferencesContext);
  if (!ctx) {
    throw new Error('useUiPreferences must be used inside <UiPreferencesProvider>');
  }
  return ctx;
};
