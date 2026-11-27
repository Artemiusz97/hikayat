import { resolveScenarioBackdrop } from '../../theme/backgrounds.js';

export const IPHONE_DEFAULT_WALLPAPER_ID = 'iphone_default';
export const AUTO_SCENARIO_WALLPAPER_ID = 'auto_scenario';

export const FOCAL_OBJECT_CLASS = {
  top: 'object-top',
  center: 'object-center',
  bottom: 'object-bottom',
};

export function isImageGenModeActive(modeVal) {
  return ['1', '2', 'auto', 'on_demand', 'true'].includes(
    String(modeVal ?? '0').trim().toLowerCase()
  );
}

export const SCENARIO_PHONE_WALLPAPERS = [
  {
    id: 'fantasy',
    labelKey: 'phone.wallpapers.fantasy',
    defaultLabel: 'Realms of Myth',
    url: '/phone-wallpapers/fantasy.webp',
    swatch: ['#0d1326', '#224f7c', '#7ce7ff'],
  },
  {
    id: 'dark_fantasy',
    labelKey: 'phone.wallpapers.dark_fantasy',
    defaultLabel: 'Ashen Crowns',
    url: '/phone-wallpapers/dark_fantasy.webp',
    swatch: ['#0f1216', '#2c353d', '#d14b5a'],
  },
  {
    id: 'isekai_fantasy',
    labelKey: 'phone.wallpapers.isekai_fantasy',
    defaultLabel: 'Sky Guild',
    url: '/phone-wallpapers/isekai_fantasy.webp',
    swatch: ['#1d2152', '#47509c', '#f5b064'],
  },
  {
    id: 'sci_fi',
    labelKey: 'phone.wallpapers.sci_fi',
    defaultLabel: 'Outer Rim',
    url: '/phone-wallpapers/sci_fi.webp',
    swatch: ['#070b14', '#163554', '#5fe1ff'],
  },
  {
    id: 'cyberpunk',
    labelKey: 'phone.wallpapers.cyberpunk',
    defaultLabel: 'Neon Chrome',
    url: '/phone-wallpapers/cyberpunk.webp',
    swatch: ['#150f29', '#31235b', '#00e5ff'],
  },
  {
    id: 'steampunk',
    labelKey: 'phone.wallpapers.steampunk',
    defaultLabel: 'Brass & Aether',
    url: '/phone-wallpapers/steampunk.webp',
    swatch: ['#141b2e', '#4f4338', '#f59e42'],
  },
  {
    id: 'high_school_drama',
    labelKey: 'phone.wallpapers.high_school_drama',
    defaultLabel: 'Rooftop Dusk',
    url: '/phone-wallpapers/high_school_drama.webp',
    swatch: ['#172542', '#644f6e', '#f59f7a'],
  },
  {
    id: 'slice_of_life',
    labelKey: 'phone.wallpapers.slice_of_life',
    defaultLabel: 'Evening Café',
    url: '/phone-wallpapers/slice_of_life.webp',
    swatch: ['#101f3d', '#3e4259', '#f2a455'],
  },
  {
    id: 'nuclear_post_apocalypse',
    labelKey: 'phone.wallpapers.nuclear_post_apocalypse',
    defaultLabel: 'Fallout Aurora',
    url: '/phone-wallpapers/nuclear_post_apocalypse.webp',
    swatch: ['#0c1211', '#214236', '#67e89b'],
  },
  {
    id: 'anomalous_incursions',
    labelKey: 'phone.wallpapers.anomalous_incursions',
    defaultLabel: 'Metro Rift',
    url: '/phone-wallpapers/anomalous_incursions.webp',
    swatch: ['#091220', '#2b1e3f', '#f43f5e'],
  },
  {
    id: 'anomalous_high_school',
    labelKey: 'phone.wallpapers.anomalous_high_school',
    defaultLabel: 'Anomalous High',
    url: '/phone-wallpapers/anomalous_high_school.webp',
    swatch: ['#0a0f1f', '#351c45', '#ec4899'],
  },
];

const SCENARIO_WALLPAPER_MAP = Object.fromEntries(
  SCENARIO_PHONE_WALLPAPERS.map((entry) => [entry.id, entry])
);

export function getBuiltinWallpaperEntry(id) {
  if (id && SCENARIO_WALLPAPER_MAP[id]) {
    const item = SCENARIO_WALLPAPER_MAP[id];
    return {
      key: item.id,
      type: 'scenario',
      id: item.id,
      url: item.url,
      labelKey: item.labelKey,
      label: item.defaultLabel,
      swatch: item.swatch,
    };
  }
  return {
    key: IPHONE_DEFAULT_WALLPAPER_ID,
    type: 'css',
    id: IPHONE_DEFAULT_WALLPAPER_ID,
    url: null,
    labelKey: 'phone.wallpapers.iphone_default',
    label: 'Aurora Silk (Default)',
    swatch: ['#080c1e', '#1e2761', '#7c3aed'],
  };
}

export function isIntimateMediaItem(item) {
  const mType = String(item?.media_type || '').toLowerCase();
  const name = String(item?.name || '').toLowerCase();
  return mType.includes('nsfw') || mType.includes('intimate') || name.includes('🔞');
}

export function isVideoMediaItem(item) {
  const mType = String(item?.media_type || '').toLowerCase();
  return mType.includes('video');
}

export function extractNpcPhotoWallpapers(mediaGallery = [], { includeIntimate = false } = {}) {
  const seen = new Set();
  const list = [];
  for (const m of mediaGallery || []) {
    if (!m || !m.image_url) continue;
    if (isVideoMediaItem(m)) continue;
    const intimate = isIntimateMediaItem(m);
    if (intimate && !includeIntimate) continue;
    const itemId = m.id ?? m.image_url;
    const key = `npc:${itemId}`;
    if (seen.has(key)) continue;
    seen.add(key);
    list.push({
      key,
      type: 'npc_photo',
      id: m.id ?? null,
      url: m.image_url,
      label: m.contact_name || m.name || 'Contact Photo',
      caption: m.caption || '',
      isIntimate: intimate,
    });
  }
  return list;
}

export function extractSessionSceneWallpapers(session) {
  const seen = new Set();
  const list = [];
  const history = Array.isArray(session?.history) ? session.history : [];
  history.forEach((entry, idx) => {
    const url = entry?.scene_image_url;
    if (!url || typeof url !== 'string' || seen.has(url)) return;
    seen.add(url);
    list.push({
      key: `scene:${url}`,
      type: 'scene',
      id: url,
      url,
      label: entry.scene_title || `Scene #${idx + 1}`,
      orientation: entry.scene_image_orientation || 'wide',
    });
  });
  const topUrl = session?.scene_image_url;
  if (topUrl && typeof topUrl === 'string' && !seen.has(topUrl)) {
    seen.add(topUrl);
    list.push({
      key: `scene:${topUrl}`,
      type: 'scene',
      id: topUrl,
      url: topUrl,
      label: session?.scene_title || 'Current Scene',
      orientation: 'wide',
    });
  }
  return list;
}

export function buildCarouselCandidates({
  poolMode = 'all_builtin',
  customIds = [],
  session = null,
  mediaGallery = [],
  includeIntimate = false,
} = {}) {
  const defaultEntry = getBuiltinWallpaperEntry(IPHONE_DEFAULT_WALLPAPER_ID);
  const allBuiltin = [
    defaultEntry,
    ...SCENARIO_PHONE_WALLPAPERS.map((wp) => getBuiltinWallpaperEntry(wp.id)),
  ];
  const npcPhotos = extractNpcPhotoWallpapers(mediaGallery, { includeIntimate });
  const scenePhotos = extractSessionSceneWallpapers(session);
  const allPhotos = [...npcPhotos, ...scenePhotos];

  if (poolMode === 'photos_only') {
    return allPhotos;
  }
  if (poolMode === 'scenario_and_photos') {
    const scenarioId = resolveScenarioBackdrop(session);
    const scenarioEntry =
      scenarioId && SCENARIO_WALLPAPER_MAP[scenarioId]
        ? getBuiltinWallpaperEntry(scenarioId)
        : defaultEntry;
    const base =
      scenarioEntry.key === defaultEntry.key ? [defaultEntry] : [scenarioEntry, defaultEntry];
    return [...base, ...allPhotos];
  }
  if (poolMode === 'custom') {
    const allowed = new Set(Array.isArray(customIds) ? customIds.map(String) : []);
    const universe = [...allBuiltin, ...allPhotos];
    return universe.filter((item) => allowed.has(item.key));
  }
  return allBuiltin;
}

export function pickNextCarouselWallpaper(candidates = [], previousKey = null) {
  if (!Array.isArray(candidates) || candidates.length === 0) return null;
  if (candidates.length === 1) return candidates[0];
  const pool = candidates.filter((c) => c.key !== previousKey);
  const effective = pool.length > 0 ? pool : candidates;
  const idx = Math.floor(Math.random() * effective.length);
  return effective[idx] || effective[0];
}

export function resolveFallbackWallpaper({ phonePrefs, session }) {
  const wpId = phonePrefs?.wallpaperId || IPHONE_DEFAULT_WALLPAPER_ID;
  if (wpId === AUTO_SCENARIO_WALLPAPER_ID) {
    const resolved = resolveScenarioBackdrop(session);
    if (resolved && SCENARIO_WALLPAPER_MAP[resolved]) {
      return getBuiltinWallpaperEntry(resolved);
    }
    return getBuiltinWallpaperEntry(IPHONE_DEFAULT_WALLPAPER_ID);
  }
  return getBuiltinWallpaperEntry(wpId);
}

export function resolveActivePhoneWallpaper({
  phonePrefs,
  session = null,
  mediaGallery = [],
  activeCarouselEntry = null,
} = {}) {
  if (phonePrefs?.carouselEnabled && activeCarouselEntry) {
    const validCandidates = buildCarouselCandidates({
      poolMode: phonePrefs?.carouselPool || 'all_builtin',
      customIds: phonePrefs?.carouselCustomIds || [],
      session,
      mediaGallery,
      includeIntimate: Boolean(phonePrefs?.includeIntimateInCarousel),
    });
    const validMatch = validCandidates.find(
      (c) =>
        c.key === activeCarouselEntry.key ||
        (activeCarouselEntry.type === 'npc_photo' &&
          c.type === 'npc_photo' &&
          ((activeCarouselEntry.id != null && String(c.id) === String(activeCarouselEntry.id)) ||
            (activeCarouselEntry.url && c.url === activeCarouselEntry.url))) ||
        (activeCarouselEntry.type === 'scene' &&
          c.type === 'scene' &&
          c.url === activeCarouselEntry.url)
    );
    if (validMatch) {
      return validMatch;
    }
    if (validCandidates.length > 0) {
      return validCandidates[0];
    }
  }

  const sidKey = session?.id != null ? String(session.id) : null;
  const sessionOverride = sidKey ? phonePrefs?.sessionWallpapers?.[sidKey] : null;
  if (sessionOverride && typeof sessionOverride === 'object') {
    if (sessionOverride.type === 'npc_photo') {
      const match = (mediaGallery || []).find(
        (m) =>
          m?.image_url &&
          !isVideoMediaItem(m) &&
          ((sessionOverride.id != null && String(m.id) === String(sessionOverride.id)) ||
            (sessionOverride.url && m.image_url === sessionOverride.url))
      );
      if (match) {
        return {
          key: `npc:${match.id ?? match.image_url}`,
          type: 'npc_photo',
          id: match.id ?? sessionOverride.id ?? null,
          url: match.image_url,
          label: match.contact_name || match.name || sessionOverride.label || 'Photo',
          isIntimate: isIntimateMediaItem(match),
        };
      }
    } else if (sessionOverride.type === 'scene' && sessionOverride.url) {
      const scenes = extractSessionSceneWallpapers(session);
      const match = scenes.find((s) => s.url === sessionOverride.url);
      if (match) return match;
      return {
        key: `scene:${sessionOverride.url}`,
        type: 'scene',
        id: sessionOverride.url,
        url: sessionOverride.url,
        label: sessionOverride.label || 'Scene Wallpaper',
      };
    }
  }

  return resolveFallbackWallpaper({ phonePrefs, session });
}
