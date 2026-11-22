import { useState, useEffect, useRef, useId, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Map,
  Compass,
  MapPin,
  Navigation,
  X,
  RefreshCw,
  ArrowRight,
  ArrowLeft,
  Search,
  ChevronDown,
  ChevronRight,
  Crosshair,
  AlertTriangle,
  Maximize2,
} from 'lucide-react';
import { MotionButton, isTopEscapeLayer, registerEscapeLayer } from '../Common/MotionPrimitives';
import { apiCall } from '../../api/client';
import { useMediaQuery } from '../../hooks/useMediaQuery';
import {
  formatCleanLocation,
  formatFullLocationPath,
  cleanProseLocations,
  parseCleanLocationParts,
} from '../../utils/locationFormat';
import { isValidSessionId } from '../../utils/session';

const getFacilityBadgeLabels = (t) => [
  { icon: '📋', label: t('atlas.badge_notice_board', '📋 Notice Board'), color: 'bg-amber-950/45 text-amber-300 border-amber-700/45' },
  { icon: '💾', label: t('atlas.badge_job_terminal', '💾 Job Terminal'), color: 'bg-cyan-950/45 text-cyan-300 border-cyan-700/45' },
  { icon: '📡', label: t('atlas.badge_comm_terminal', '📡 Comm Terminal'), color: 'bg-cyan-950/45 text-cyan-300 border-cyan-700/45' },
  { icon: '📻', label: t('atlas.badge_dispatch_board', '📻 Dispatch Board'), color: 'bg-amber-950/45 text-amber-300 border-amber-700/45' },
  { icon: '🛍️', label: t('atlas.badge_merchant_shop', '🛍️ Merchant Shop'), color: 'bg-purple-950/45 text-purple-300 border-purple-700/45' },
  { icon: '🏛️', label: t('atlas.badge_faction_hq', '🏛️ Faction HQ'), color: 'bg-blue-950/45 text-blue-300 border-blue-700/45' },
  { icon: '🏠', label: t('atlas.badge_home', '🏠 Home'), color: 'bg-emerald-950/45 text-emerald-300 border-emerald-700/45' },
];

const extractZoneFromTarget = (targetStr, zones = []) => {
  if (!targetStr || !zones.length) return null;
  const parts = String(targetStr).split(/\s*(?:➔|->|>)\s*/).map(s => s.trim()).filter(Boolean);
  const candidateZone = parts[0] || '';
  const candidatePlace = parts[1] || parts[0] || '';
  const exactZone = zones.find(z => z.zone_name.toLowerCase() === candidateZone.toLowerCase());
  if (exactZone) return exactZone.zone_name;
  const partialZone = zones.find(
    z => z.zone_name.toLowerCase().includes(candidateZone.toLowerCase()) ||
         candidateZone.toLowerCase().includes(z.zone_name.toLowerCase())
  );
  if (partialZone) return partialZone.zone_name;
  if (candidatePlace) {
    const byPlace = zones.find(z =>
      (z.primary_locations || []).some(p => (p.name || '').toLowerCase() === candidatePlace.toLowerCase())
    );
    if (byPlace) return byPlace.zone_name;
  }
  return null;
};

const inferQuestKind = (kindOrTag = '') => {
  const s = String(kindOrTag || '').toLowerCase();
  if (s === 'climax' || s.includes('⚡') || s.includes('climax')) return 'climax';
  if (s === 'bounty' || s.includes('🎯') || s.includes('bounty') || s.includes('🛡️') || s.includes('👹') || s.includes('💋') || s.includes('🕵')) return 'bounty';
  if (s === 'meetup' || s.includes('💌') || s.includes('meetup')) return 'meetup';
  if (s === 'story' || s.includes('⭐') || s.includes('story') || s.includes('bonus')) return 'story';
  return 'story';
};

const getQuestBadgeMeta = (kindOrTag, t) => {
  const kind = inferQuestKind(kindOrTag);
  if (kind === 'climax') {
    return {
      kind,
      icon: '⚡',
      label: t('atlas.story_climax', 'Story Climax'),
      badgeCls: 'bg-fuchsia-950/75 text-fuchsia-200 border-fuchsia-500/60',
      surfaceCls: 'border-fuchsia-500/55 bg-fuchsia-950/15',
    };
  }
  if (kind === 'bounty') {
    return {
      kind,
      icon: '🎯',
      label: t('atlas.bounty_target', 'Bounty'),
      badgeCls: 'bg-rose-950/75 text-rose-200 border-rose-500/60',
      surfaceCls: 'border-rose-500/55 bg-rose-950/15',
    };
  }
  if (kind === 'meetup') {
    return {
      kind,
      icon: '💌',
      label: t('atlas.meetup_label', 'Meetup'),
      badgeCls: 'bg-sky-950/75 text-sky-200 border-sky-500/60',
      surfaceCls: 'border-sky-500/55 bg-sky-950/15',
    };
  }
  return {
    kind: 'story',
    icon: '⭐',
    label: t('atlas.story_quest', 'Story Quest'),
    badgeCls: 'bg-amber-950/75 text-amber-200 border-amber-500/60',
    surfaceCls: 'border-amber-500/55 bg-amber-950/15',
  };
};

const formatMarkerObjective = (rawMarker) => {
  const cleaned = cleanProseLocations(rawMarker || '');
  const withoutEmoji = cleaned.replace(/^(?:[\p{Extended_Pictographic}\u2600-\u27BF\s]|\uFE0F|\u200D)+/u, '');
  if (/^\[Bonus Lead\]/i.test(withoutEmoji)) {
    return withoutEmoji.replace(/^\[Bonus Lead\]\s*/i, 'Bonus Lead — ');
  }
  return withoutEmoji.replace(/^\[(Story Climax|Story|Bounty|Meetup)\]\s*/i, '');
};

const getNonDefaultAccessBadge = (accessBadge, isCurfewActive, scheduleLocked, t) => {
  if (!accessBadge) return null;
  const isForSale = accessBadge.startsWith('For Sale');
  const isOwnedHome = accessBadge === 'Owned Residence' || accessBadge === 'Starter Quarters';
  const isCurfew = Boolean(isCurfewActive || accessBadge.includes('Curfew'));
  const isClosedOrLocked = Boolean(scheduleLocked || accessBadge.includes('Closed') || accessBadge.includes('Locked'));

  if (!isForSale && !isOwnedHome && !isCurfew && !isClosedOrLocked && !['Unlocked', 'Restricted', 'Private'].includes(accessBadge)) {
    return null; // Omit noisy default "Open" status
  }

  let label = accessBadge;
  let cls = 'bg-black/45 text-gray-300 border-fantasy-border/60';
  if (isForSale) {
    label = `🏷️ ${t('realty.badge_for_sale', 'For Sale')}${accessBadge.includes('—') ? ' — ' + accessBadge.split('—')[1].trim() : ''}`;
    cls = 'bg-amber-950/65 text-amber-200 border-amber-500/60';
  } else if (isOwnedHome) {
    label = `🏠 ${accessBadge === 'Owned Residence' ? t('realty.badge_owned', 'Owned Residence') : t('realty.badge_starter', 'Starter Quarters')}`;
    cls = 'bg-emerald-950/65 text-emerald-200 border-emerald-500/60';
  } else if (accessBadge === 'Unlocked') {
    label = t('atlas.access_unlocked', '🔓 Unlocked');
    cls = 'bg-teal-950/55 text-teal-200 border-teal-700/60';
  } else if (isCurfew || isClosedOrLocked) {
    label = `🔒 ${accessBadge}`;
    cls = 'bg-rose-950/65 text-rose-200 border-rose-700/60';
  } else if (accessBadge === 'Restricted') {
    label = t('atlas.access_restricted', '⛔ Restricted');
    cls = 'bg-orange-950/65 text-orange-200 border-orange-700/60';
  } else if (accessBadge === 'Private') {
    label = t('atlas.access_private', '🏠 Private');
    cls = 'bg-purple-950/65 text-purple-200 border-purple-700/60';
  }
  return { label, cls };
};

const getSubItemsForPlace = (place) => {
  if (Array.isArray(place?.sub_location_details) && place.sub_location_details.length > 0) {
    return place.sub_location_details;
  }
  return Array.isArray(place?.sub_locations) ? place.sub_locations : [];
};

const textMatchesQuery = (text, q) => Boolean(text && String(text).toLowerCase().includes(q));

const placeMatchesSearch = (place, q) => {
  if (!q) return true;
  if (textMatchesQuery(place?.name, q) || textMatchesQuery(place?.archetype, q) || textMatchesQuery(place?.scene_residue, q)) {
    return true;
  }
  if ((place?.quest_markers || []).some(m => textMatchesQuery(m, q))) return true;
  if ((place?.known_npcs_here || []).some(kn => textMatchesQuery(kn?.name, q))) return true;
  return getSubItemsForPlace(place).some(sub => {
    if (typeof sub !== 'object' || sub === null) return textMatchesQuery(sub, q);
    return (
      textMatchesQuery(sub.name || sub.label, q) ||
      (sub.quest_markers || []).some(m => textMatchesQuery(m, q)) ||
      (sub.known_npcs_here || []).some(kn => textMatchesQuery(kn?.name, q))
    );
  });
};

const zoneMatchesSearch = (zone, q) => {
  if (!q) return true;
  if (textMatchesQuery(zone?.zone_name, q) || textMatchesQuery(zone?.theme, q)) return true;
  return (zone?.primary_locations || []).some(p => placeMatchesSearch(p, q));
};

const WorldMapModal = ({
  isOpen,
  onClose,
  session,
  user,
  onTravel,
  initialTargetLocation,
  processingTurn = false,
  mode = 'modal',
  onExpandModal = null,
}) => {
  const { t } = useTranslation();
  const dialogRef = useRef(null);
  const titleId = useId();
  const placeRefs = useRef({});
  const roomRefs = useRef({});
  const isMobile = useMediaQuery('(max-width: 767px)');
  const isDesktopWide = useMediaQuery('(min-width: 1280px)');
  const isDrawer = mode === 'drawer';
  const useTwoColumnDrawer = isDrawer && isDesktopWide;
  const isCompact = isMobile || (isDrawer && !useTwoColumnDrawer);

  const [mapData, setMapData] = useState(null);
  const [selectedZone, setSelectedZone] = useState(null);
  const [leftTab, setLeftTab] = useState('regions');
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedPlaces, setExpandedPlaces] = useState({});
  const [highlightedTarget, setHighlightedTarget] = useState(null);
  const [mobileView, setMobileView] = useState('list');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const abortRef = useRef(null);
  const seqRef = useRef(0);
  const wasOpenRef = useRef(false);
  const lastSessionIdRef = useRef(session?.id ?? null);
  const lastInitialTargetRef = useRef(initialTargetLocation ?? null);
  const lastCurrentZoneRef = useRef(null);
  const searchQueryRef = useRef(searchQuery);

  useEffect(() => {
    searchQueryRef.current = searchQuery;
  }, [searchQuery]);

  const fetchLocations = useCallback(async () => {
    if (!isValidSessionId(session?.id)) return;
    if (abortRef.current) {
      try {
        abortRef.current.abort();
      } catch {}
    }
    const seq = ++seqRef.current;
    const controller = new AbortController();
    abortRef.current = controller;

    const cleanInitialTarget = initialTargetLocation ?? null;
    const isFreshOpenOrSwitch =
      (!wasOpenRef.current && isOpen) ||
      lastSessionIdRef.current !== session?.id ||
      Boolean(cleanInitialTarget && cleanInitialTarget !== lastInitialTargetRef.current);
    wasOpenRef.current = isOpen;
    lastSessionIdRef.current = session?.id;
    lastInitialTargetRef.current = cleanInitialTarget;

    setLoading(true);
    setError(null);
    try {
      const uidParam = user?.user_id ? `?user_id=${user.user_id}` : '';
      const data = await apiCall(`/api/locations/${session.id}${uidParam}`, {
        signal: controller.signal,
      });
      if (seq !== seqRef.current) return;
      setMapData(data);
      const zones = data?.zones || [];
      const matchedInitial = extractZoneFromTarget(initialTargetLocation, zones);
      const currentZone = zones.find(z => z.is_current) || zones[0] || null;
      const currentZoneName = currentZone ? currentZone.zone_name : null;

      if (isFreshOpenOrSwitch) {
        const nextZone = matchedInitial || currentZoneName;
        setSelectedZone(nextZone);
        setExpandedPlaces({});
        setSearchQuery('');
        setLeftTab('regions');

        if (initialTargetLocation) {
          const parsed = parseCleanLocationParts(initialTargetLocation);
          setHighlightedTarget({
            zoneName: nextZone,
            placeName: parsed.facility || '',
            subName: parsed.subRoom || '',
          });
        } else {
          setHighlightedTarget(null);
        }

        if (nextZone) {
          setMobileView('detail');
        } else {
          setMobileView('list');
        }
      } else if (
        currentZoneName &&
        currentZoneName !== lastCurrentZoneRef.current &&
        !searchQueryRef.current.trim()
      ) {
        setSelectedZone(currentZoneName);
      }
      lastCurrentZoneRef.current = currentZoneName;
    } catch (err) {
      if (err?.isUserAbort || err?.name === 'AbortError' || seq !== seqRef.current) return;
      setError(err.message || t('atlas.load_failed', 'Failed to load world map.'));
    } finally {
      if (seq === seqRef.current) {
        setLoading(false);
        if (abortRef.current === controller) {
          abortRef.current = null;
        }
      }
    }
  }, [isOpen, session?.id, user?.user_id, initialTargetLocation, t]);

  // Native <dialog> open/close synchronization (modal mode) or direct fetch (drawer mode)
  useEffect(() => {
    if (!isOpen) {
      wasOpenRef.current = false;
      if (abortRef.current) {
        try {
          abortRef.current.abort();
        } catch {}
        abortRef.current = null;
      }
    }
    if (isDrawer) {
      if (isOpen) {
        fetchLocations();
      }
      return () => {
        if (abortRef.current) {
          try {
            abortRef.current.abort();
          } catch {}
        }
      };
    }
    const dialog = dialogRef.current;
    if (!dialog) return undefined;
    if (isOpen) {
      if (!dialog.open) {
        dialog.showModal();
      }
      fetchLocations();
    } else if (dialog.open) {
      dialog.close();
    }
    return () => {
      if (abortRef.current) {
        try {
          abortRef.current.abort();
        } catch {}
      }
    };
  }, [isDrawer, isOpen, fetchLocations, session?.current_location, session?.turn_count]);

  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (isDrawer || !isOpen) return undefined;
    const token = Symbol('world-map-esc');
    const unregister = registerEscapeLayer(token);
    const onKeyDown = (e) => {
      if (e.key === 'Escape' && !e.defaultPrevented && isTopEscapeLayer(token)) {
        e.preventDefault();
        e.stopPropagation();
        const dialog = dialogRef.current;
        if (dialog?.open) {
          dialog.close();
        } else if (onCloseRef.current) {
          onCloseRef.current();
        }
      }
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => {
      unregister();
      window.removeEventListener('keydown', onKeyDown, true);
    };
  }, [isDrawer, isOpen]);

  // Progressive enhancement fallback for browsers without native <dialog closedby="any">
  useEffect(() => {
    if (isDrawer) return undefined;
    const dialog = dialogRef.current;
    if (!dialog || typeof HTMLDialogElement === 'undefined') return undefined;
    if ('closedBy' in HTMLDialogElement.prototype) return undefined;

    const isOutside = (e) => {
      const r = dialog.getBoundingClientRect();
      return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
    };
    let pressedOutside = false;
    const onPointerDown = (e) => {
      pressedOutside = isOutside(e);
    };
    const onPointerUp = (e) => {
      if (pressedOutside && isOutside(e)) {
        dialog.close();
      }
      pressedOutside = false;
    };
    dialog.addEventListener('pointerdown', onPointerDown);
    dialog.addEventListener('pointerup', onPointerUp);
    return () => {
      dialog.removeEventListener('pointerdown', onPointerDown);
      dialog.removeEventListener('pointerup', onPointerUp);
    };
  }, [isDrawer]);

  const handleDialogClose = () => {
    if (dialogRef.current) {
      dialogRef.current.returnValue = '';
    }
    if (onClose) onClose();
  };

  const zones = useMemo(() => mapData?.zones || [], [mapData?.zones]);
  const canTravel = mapData?.can_travel !== false;
  const travelBlockedReason = mapData?.travel_blocked_reason || '';
  const activeZoneObj = zones.find(z => z.zone_name === selectedZone) || zones[0] || null;

  const activeQuestDestinations = useMemo(() => {
    if (Array.isArray(mapData?.active_quest_destinations)) {
      return mapData.active_quest_destinations;
    }
    return zones.flatMap(z =>
      (z.primary_locations || []).flatMap(p => {
        const subEntries = getSubItemsForPlace(p).flatMap(sub =>
          (typeof sub === 'object' && sub !== null ? (sub.quest_markers || []) : []).map(qm => ({
            zone_name: z.zone_name,
            place_name: p.name,
            sub_name: sub.name,
            value: sub.value || `${z.zone_name} ➔ ${p.name} ➔ ${sub.name}`,
            marker: qm,
            quest_tag: sub.quest_tag || p.quest_tag || '⭐ Story Quest',
            quest_kind: sub.quest_kind || '',
            is_current_place: Boolean(sub.is_current_room),
            is_current_room: Boolean(sub.is_current_room),
            can_travel: p.can_travel !== false,
            travel_tag: sub.travel_tag || p.travel_tag || '',
          }))
        );
        const directMarkers = Array.isArray(p.direct_quest_markers) ? p.direct_quest_markers : (p.quest_markers || []);
        const directEntries = directMarkers.map(qm => ({
          zone_name: z.zone_name,
          place_name: p.name,
          sub_name: '',
          value: p.value || `${z.zone_name} ➔ ${p.name}`,
          marker: qm,
          quest_tag: p.direct_quest_tag || p.quest_tag || '⭐ Story Quest',
          quest_kind: '',
          is_current_place: Boolean(p.is_current_place),
          is_current_room: false,
          can_travel: p.can_travel !== false,
          travel_tag: p.travel_tag || '',
        }));
        return [...subEntries, ...directEntries];
      })
    );
  }, [mapData, zones]);

  const trimmedQuery = searchQuery.trim().toLowerCase();

  const filteredZones = useMemo(
    () => (trimmedQuery ? zones.filter(z => zoneMatchesSearch(z, trimmedQuery)) : zones),
    [zones, trimmedQuery]
  );

  const filteredQuests = useMemo(() => {
    if (!trimmedQuery) return activeQuestDestinations;
    return activeQuestDestinations.filter(qd =>
      textMatchesQuery(qd.zone_name, trimmedQuery) ||
      textMatchesQuery(qd.place_name, trimmedQuery) ||
      textMatchesQuery(qd.sub_name, trimmedQuery) ||
      textMatchesQuery(qd.quest_tag, trimmedQuery) ||
      textMatchesQuery(qd.marker, trimmedQuery)
    );
  }, [activeQuestDestinations, trimmedQuery]);

  const primaryPlaces = useMemo(
    () => activeZoneObj?.primary_locations || [],
    [activeZoneObj?.primary_locations]
  );
  const filteredPlaces = useMemo(() => {
    if (!trimmedQuery) return primaryPlaces;
    const matched = primaryPlaces.filter(p => placeMatchesSearch(p, trimmedQuery));
    if (matched.length > 0) return matched;
    if (textMatchesQuery(activeZoneObj?.zone_name, trimmedQuery) || textMatchesQuery(activeZoneObj?.theme, trimmedQuery)) {
      return primaryPlaces;
    }
    return [];
  }, [primaryPlaces, activeZoneObj, trimmedQuery]);

  useEffect(() => {
    if (!isOpen || !highlightedTarget || !activeZoneObj) return;
    if (highlightedTarget.zoneName && highlightedTarget.zoneName !== activeZoneObj.zone_name) return;

    const rafId = requestAnimationFrame(() => {
      const targetSubKey = highlightedTarget.subName
        ? `${activeZoneObj.zone_name}::${highlightedTarget.placeName}::${highlightedTarget.subName}`.toLowerCase()
        : '';
      const targetPlaceKey = highlightedTarget.placeName
        ? `${activeZoneObj.zone_name}::${highlightedTarget.placeName}`.toLowerCase()
        : '';
      const el = (targetSubKey && roomRefs.current[targetSubKey]) || (targetPlaceKey && placeRefs.current[targetPlaceKey]);
      if (el && typeof el.scrollIntoView === 'function') {
        el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    });
    return () => cancelAnimationFrame(rafId);
  }, [isOpen, highlightedTarget, activeZoneObj, mobileView]);

  const handleTravel = (destValue) => {
    if (!destValue || !onTravel || processingTurn || !canTravel) return;
    onClose();
    Promise.resolve(onTravel(destValue)).catch((err) => {
      console.error('Fast travel failed:', err);
    });
  };

  const handleSelectZone = (zoneName) => {
    setSelectedZone(zoneName);
    setHighlightedTarget(null);
    if (isCompact) {
      setMobileView('detail');
    }
  };

  const handleLocateQuest = (qd) => {
    if (!qd) return;
    setSelectedZone(qd.zone_name);
    if (qd.place_name) {
      const pKey = `${qd.zone_name}::${qd.place_name}`;
      setExpandedPlaces(prev => ({ ...prev, [pKey]: true }));
    }
    setHighlightedTarget({
      zoneName: qd.zone_name,
      placeName: qd.place_name || '',
      subName: qd.sub_name || '',
    });
    if (isCompact) {
      setMobileView('detail');
    }
  };

  const togglePlaceExpanded = (placeKey, currentExpanded) => {
    setExpandedPlaces(prev => ({ ...prev, [placeKey]: !currentExpanded }));
  };

  const rawCurrLoc = session?.current_location || mapData?.current_location || '';
  const cleanCurrLoc = rawCurrLoc
    ? formatCleanLocation(rawCurrLoc, { includeZone: true, style: 'badge' })
    : t('atlas.unknown_area', 'Unknown Area');
  const fullCurrLocTooltip = rawCurrLoc ? formatFullLocationPath(rawCurrLoc) : '';

  const showLeftRail = !isCompact || mobileView === 'list';
  const showRightPane = !isCompact || mobileView === 'detail';

  const facilityBadgeLabels = useMemo(() => getFacilityBadgeLabels(t), [t]);

  const atlasContent = (
        <div className={isDrawer ? 'flex-1 min-h-0 flex flex-col overflow-hidden' : 'hk-acrylic flex-1 min-h-0 flex flex-col overflow-hidden rounded-none md:rounded-2xl border-0 md:border'}>
          {/* Top Modal / Drawer Header */}
          <header className={`hk-atlas-header ${isDrawer ? 'px-3.5 py-2.5' : 'px-4 sm:px-6 py-3.5'} border-b border-fantasy-border/40 flex items-start justify-between gap-2.5 shrink-0`}>
            <div className="flex items-start gap-2.5 min-w-0 flex-1">
              {!isDrawer && (
                <div className="w-10 h-10 rounded-xl bg-fantasy-accent/15 border border-fantasy-accent/40 flex items-center justify-center text-fantasy-accent shrink-0 mt-0.5">
                  <Map size={20} aria-hidden="true" />
                </div>
              )}
              <div className="min-w-0 flex-1 space-y-0.5">
                <div className="flex items-center flex-wrap gap-2">
                  <h2 id={titleId} className={`hk-atlas-heading font-rpg font-bold ${isDrawer ? 'text-sm' : 'text-base sm:text-lg'} text-gray-100 tracking-wide truncate`}>
                    {t('atlas.title', 'World Atlas & Fast-Travel')}
                  </h2>
                  {activeQuestDestinations.length > 0 && (
                    <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-200 border border-amber-500/45">
                      {activeQuestDestinations.length === 1
                        ? t('atlas.active_leads', { count: 1, defaultValue: '⭐ 1 Active Quest Lead' })
                        : t('atlas.active_leads_plural', { count: activeQuestDestinations.length, defaultValue: `⭐ ${activeQuestDestinations.length} Active Quest Leads` })}
                    </span>
                  )}
                </div>
                <p className={`${isDrawer ? 'text-xs' : 'text-sm'} text-gray-300 flex items-start gap-1.5 hk-atlas-prose`} title={fullCurrLocTooltip}>
                  <MapPin size={14} className="text-fantasy-accent shrink-0 mt-0.5" aria-hidden="true" />
                  <span className="min-w-0 truncate">
                    {!isDrawer && <span className="text-gray-400 mr-1.5">{t('atlas.current_position', 'Current Position:')}</span>}
                    <strong className="text-gray-100 font-semibold">{cleanCurrLoc}</strong>
                  </span>
                </p>
              </div>
            </div>

            <div className="flex items-center gap-1 shrink-0">
              <MotionButton
                onClick={fetchLocations}
                disabled={loading}
                className={`hk-icon-btn ${isDrawer ? 'h-8 min-w-8' : 'min-h-[44px] min-w-[44px] md:min-h-[36px] md:min-w-[36px]'}`}
                title={t('atlas.refresh', 'Refresh Atlas')}
                aria-label={t('atlas.refresh', 'Refresh Atlas')}
              >
                <RefreshCw size={15} className={loading ? 'animate-spin text-fantasy-accent' : ''} aria-hidden="true" />
              </MotionButton>
              {isDrawer && onExpandModal && (
                <MotionButton
                  onClick={onExpandModal}
                  className="hk-icon-btn h-8 min-w-8"
                  title={t('nav.expand_atlas', 'Expand Full Atlas')}
                  aria-label={t('nav.expand_atlas', 'Expand Full Atlas')}
                >
                  <Maximize2 size={14} aria-hidden="true" />
                </MotionButton>
              )}
              {isDrawer ? (
                <MotionButton
                  onClick={onClose}
                  className="hk-icon-btn is-danger h-8 min-w-8"
                  title={t('atlas.close_atlas', 'Close World Atlas')}
                  aria-label={t('atlas.close_atlas', 'Close World Atlas')}
                >
                  <X size={16} aria-hidden="true" />
                </MotionButton>
              ) : (
                <form method="dialog">
                  <button
                    type="submit"
                    value="close"
                    autoFocus
                    className="hk-icon-btn is-danger min-h-[44px] min-w-[44px] md:min-h-[36px] md:min-w-[36px]"
                    title={t('atlas.close_atlas', 'Close World Atlas')}
                    aria-label={t('atlas.close_atlas', 'Close World Atlas')}
                  >
                    <X size={18} aria-hidden="true" />
                  </button>
                </form>
              )}
            </div>
          </header>

          {/* Travel Blocked Banner (if player is restrained) */}
          {!canTravel && travelBlockedReason && (
            <div className="px-4 sm:px-6 py-2.5 bg-rose-950/70 border-b border-rose-700/50 text-rose-200 text-sm flex items-center gap-2 shrink-0">
              <AlertTriangle size={16} className="text-rose-300 shrink-0" aria-hidden="true" />
              <span className="hk-atlas-prose">{travelBlockedReason}</span>
            </div>
          )}

          {/* Main Body */}
          {loading && !mapData ? (
            <div className="flex-1 flex flex-col items-center justify-center py-16 px-4 text-gray-300 space-y-3">
              <Compass size={34} className="animate-spin text-fantasy-accent opacity-80" aria-hidden="true" />
              <p className="text-sm text-gray-300">{t('atlas.charting', 'Charting discovered regions and waypoints...')}</p>
            </div>
          ) : error ? (
            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center space-y-3">
              <p className="text-sm text-rose-300 max-w-md hk-atlas-prose">{error}</p>
              <button
                type="button"
                onClick={fetchLocations}
                className="hk-btn hk-btn-ghost min-h-[44px] md:min-h-[36px]"
              >
                <RefreshCw size={15} aria-hidden="true" />
                <span>{t('atlas.refresh', 'Refresh Atlas')}</span>
              </button>
            </div>
          ) : zones.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center p-10 text-center text-gray-400 space-y-2">
              <Map size={36} className="mx-auto opacity-35" aria-hidden="true" />
              <p className="text-base font-semibold text-gray-200">{t('atlas.no_regions_title', 'No Regions Charted Yet')}</p>
              <p className="text-sm max-w-md hk-atlas-prose">{t('atlas.no_regions_desc', 'Explore your surroundings to unlock regions and fast-travel destinations.')}</p>
            </div>
          ) : (
            <div
              className={`flex-1 min-h-0 grid overflow-hidden ${
                useTwoColumnDrawer
                  ? 'grid-cols-[minmax(11.5rem,38%)_minmax(0,1fr)]'
                  : isDrawer
                    ? 'grid-cols-1'
                    : 'grid-cols-1 md:grid-cols-12'
              }`}
            >
              {/* LEFT RAIL: Regions / Quests Tabs + Search + Vertical List */}
              {showLeftRail && (
                <aside
                  className={`${
                    useTwoColumnDrawer
                      ? 'min-w-0 border-r border-fantasy-border/45'
                      : isDrawer
                        ? 'min-w-0'
                        : 'md:col-span-4 min-w-0 border-b md:border-b-0 md:border-r border-fantasy-border/50'
                  } flex flex-col min-h-0 overflow-hidden`}
                >
                  {/* Sticky Rail Controls */}
                  <div className={`${useTwoColumnDrawer ? 'p-2.5 space-y-2' : 'p-3.5 space-y-2.5'} border-b border-fantasy-border/50 shrink-0`}>
                    <div className="hk-segmented" role="tablist">
                      <button
                        type="button"
                        role="tab"
                        aria-selected={leftTab === 'regions'}
                        onClick={() => setLeftTab('regions')}
                        className={useTwoColumnDrawer ? 'min-h-[34px] text-xs px-1.5' : 'min-h-[44px] md:min-h-[36px] text-sm px-2'}
                      >
                        <Compass size={useTwoColumnDrawer ? 13 : 15} aria-hidden="true" />
                        <span className="truncate">{t('atlas.tab_regions', 'Regions')} ({zones.length})</span>
                      </button>
                      <button
                        type="button"
                        role="tab"
                        aria-selected={leftTab === 'quests'}
                        onClick={() => setLeftTab('quests')}
                        className={useTwoColumnDrawer ? 'min-h-[34px] text-xs px-1.5' : 'min-h-[44px] md:min-h-[36px] text-sm px-2'}
                      >
                        <Crosshair size={useTwoColumnDrawer ? 13 : 15} aria-hidden="true" />
                        <span className="truncate">{t('atlas.tab_quests', 'Quests')} ({activeQuestDestinations.length})</span>
                      </button>
                    </div>

                    <div className="relative">
                      <Search
                        size={useTwoColumnDrawer ? 14 : 15}
                        className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none"
                        aria-hidden="true"
                      />
                      <input
                        type="search"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder={t('atlas.search_placeholder', 'Search regions, places, or rooms...')}
                        aria-label={t('atlas.search_placeholder', 'Search regions, places, or rooms...')}
                        className={`hk-input pl-9 pr-9 ${useTwoColumnDrawer ? 'h-9 min-h-[34px] text-xs' : 'min-h-[44px] md:min-h-[38px] text-sm'}`}
                      />
                      {searchQuery && (
                        <button
                          type="button"
                          onClick={() => setSearchQuery('')}
                          className="absolute right-1.5 top-1/2 -translate-y-1/2 hk-icon-btn min-h-[34px] min-w-[34px]"
                          aria-label={t('atlas.clear_search', 'Clear search')}
                          title={t('atlas.clear_search', 'Clear search')}
                        >
                          <X size={14} aria-hidden="true" />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Rail Scroll List */}
                  <div className={`hk-atlas-scroll flex-1 min-h-0 overflow-y-auto custom-scrollbar ${useTwoColumnDrawer ? 'p-2.5 space-y-2' : 'p-3.5 space-y-2.5'}`}>
                    {leftTab === 'regions' ? (
                      filteredZones.length === 0 ? (
                        <div className="p-6 text-center space-y-3 text-gray-400">
                          <p className="text-sm hk-atlas-prose">{t('atlas.no_search_results', 'No matching regions, locations, or rooms found.')}</p>
                          <button
                            type="button"
                            onClick={() => setSearchQuery('')}
                            className="hk-btn hk-btn-ghost min-h-[44px] md:min-h-[36px]"
                          >
                            {t('atlas.clear_search', 'Clear search')}
                          </button>
                        </div>
                      ) : (
                        filteredZones.map((z) => {
                          const isSelected = activeZoneObj?.zone_name === z.zone_name;
                          const questCount = z.quest_count || (z.quest_markers?.length ?? 0);
                          const hasQuest = questCount > 0;
                          const placeCount = z.places_count ?? (z.primary_locations?.length ?? 0);
                          const primaryQuestMeta = hasQuest
                            ? getQuestBadgeMeta(z.quest_markers?.[0]?.quest_tag || z.active_tags?.find(tag => /climax|quest|bounty|meetup/i.test(tag)) || '', t)
                            : null;

                          return (
                            <button
                              key={z.zone_name}
                              type="button"
                              onClick={() => handleSelectZone(z.zone_name)}
                              className={`hk-card hk-card-interactive w-full text-left flex flex-col ${
                                useTwoColumnDrawer ? 'p-2.5 gap-1.5 min-h-[40px]' : 'p-3.5 gap-2 min-h-[44px]'
                              } ${
                                isSelected
                                  ? 'border-fantasy-accent/80 bg-fantasy-accent/10 ring-1 ring-fantasy-accent/40'
                                  : hasQuest
                                    ? 'border-amber-500/45'
                                    : ''
                              }`}
                            >
                              <div className="flex items-start justify-between gap-2 w-full">
                                <div className="flex items-start gap-2 min-w-0 flex-1">
                                  <span className={`${useTwoColumnDrawer ? 'text-sm' : 'text-base'} leading-snug shrink-0`} aria-hidden="true">
                                    {z.is_current ? '🧭' : (z.emoji || '📍')}
                                  </span>
                                  <span className={`${useTwoColumnDrawer ? 'text-[13px]' : 'text-[15px]'} font-semibold text-gray-100 leading-snug break-words`}>
                                    {z.zone_name}
                                  </span>
                                </div>
                                {isCompact && (
                                  <ChevronRight size={18} className="text-gray-400 shrink-0 mt-0.5" aria-hidden="true" />
                                )}
                              </div>

                              <div className="flex items-center flex-wrap gap-2 text-xs">
                                {z.is_current ? (
                                  <span className="px-2 py-0.5 rounded-full bg-emerald-950/70 text-emerald-300 border border-emerald-700/50 font-semibold">
                                    {t('atlas.here', 'Here')}
                                  </span>
                                ) : z.travel_tag ? (
                                  <span className="text-gray-300 font-mono">
                                    ⏱ {z.travel_tag}
                                  </span>
                                ) : null}

                                <span className="text-gray-400">
                                  {placeCount === 1
                                    ? t('atlas.places_count', { count: 1, defaultValue: '1 place' })
                                    : t('atlas.places_count_plural', { count: placeCount, defaultValue: `${placeCount} places` })}
                                </span>

                                {hasQuest && primaryQuestMeta && (
                                  <span className={`px-2 py-0.5 rounded-full border font-semibold ${primaryQuestMeta.badgeCls}`}>
                                    {primaryQuestMeta.icon}{' '}
                                    {questCount === 1
                                      ? t('atlas.region_quest_count', { count: 1, defaultValue: '1 Quest' })
                                      : t('atlas.region_quest_count_plural', { count: questCount, defaultValue: `${questCount} Quests` })}
                                  </span>
                                )}
                              </div>
                            </button>
                          );
                        })
                      )
                    ) : filteredQuests.length === 0 ? (
                      <div className="p-6 text-center space-y-3 text-gray-400">
                        <p className="text-sm hk-atlas-prose">
                          {trimmedQuery
                            ? t('atlas.no_search_results', 'No matching regions, locations, or rooms found.')
                            : t('atlas.no_active_quests', 'No active quest destinations charted yet.')}
                        </p>
                        {trimmedQuery && (
                          <button
                            type="button"
                            onClick={() => setSearchQuery('')}
                            className="hk-btn hk-btn-ghost min-h-[44px] md:min-h-[36px]"
                          >
                            {t('atlas.clear_search', 'Clear search')}
                          </button>
                        )}
                      </div>
                    ) : (
                      filteredQuests.map((qd, idx) => {
                        const badge = getQuestBadgeMeta(qd.quest_kind || qd.quest_tag || qd.marker, t);
                        const isAtTarget = Boolean(qd.is_current_room || (qd.is_current_place && !qd.sub_name));
                        const destHeading = qd.sub_name ? qd.sub_name : qd.place_name;
                        const destContext = qd.sub_name
                          ? `${qd.place_name} · ${qd.zone_name}`
                          : qd.zone_name;

                        return (
                          <div
                            key={`${qd.value}-${idx}`}
                            className={`hk-card p-3.5 space-y-2.5 ${badge.surfaceCls}`}
                          >
                            <div className="flex items-center justify-between gap-2 flex-wrap">
                              <span className={`text-xs font-bold px-2.5 py-0.5 rounded-full border ${badge.badgeCls}`}>
                                {badge.icon} {badge.label}
                              </span>
                              {isAtTarget ? (
                                <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-950/70 text-emerald-300 border border-emerald-700/50 font-semibold">
                                  {t('atlas.here', 'Here')}
                                </span>
                              ) : qd.travel_tag && qd.travel_tag !== 'Here' ? (
                                <span className="text-xs font-mono text-gray-300">
                                  ⏱ {qd.travel_tag}
                                </span>
                              ) : null}
                            </div>

                            <div className="space-y-0.5">
                              <div className="text-[15px] font-semibold text-gray-100 leading-snug break-words">
                                {destHeading}
                              </div>
                              <div className="text-xs text-gray-400 break-words">
                                {destContext}
                              </div>
                            </div>

                            <p className="text-sm text-gray-200 leading-relaxed hk-atlas-prose">
                              {formatMarkerObjective(qd.marker)}
                            </p>

                            <div className="flex flex-wrap items-center gap-2 pt-0.5">
                              <button
                                type="button"
                                onClick={() => handleLocateQuest(qd)}
                                className="hk-btn hk-btn-ghost min-h-[44px] md:min-h-[36px] text-sm px-3"
                              >
                                <MapPin size={14} aria-hidden="true" />
                                <span>{t('atlas.locate', 'Locate')}</span>
                              </button>
                              {!isAtTarget && (
                                <button
                                  type="button"
                                  disabled={processingTurn || !canTravel || qd.can_travel === false}
                                  title={!canTravel ? (travelBlockedReason || t('atlas.travel_blocked', 'Fast travel is currently unavailable.')) : undefined}
                                  onClick={() => handleTravel(qd.value)}
                                  className="hk-btn hk-btn-primary min-h-[44px] md:min-h-[36px] text-sm px-3.5"
                                >
                                  <span>{t('atlas.travel', 'Travel')}</span>
                                  <ArrowRight size={14} aria-hidden="true" />
                                </button>
                              )}
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                </aside>
              )}

              {/* RIGHT PANE: Selected Region Locations & Tier 3 Rooms */}
              {showRightPane && (
                <section className={`${useTwoColumnDrawer || isDrawer ? 'min-w-0' : 'md:col-span-8 min-w-0'} flex flex-col min-h-0 overflow-hidden`}>
                  {activeZoneObj && (
                    <>
                      {/* Compact Drill-Down Sticky Navigation */}
                      {isCompact && (
                        <div className="px-4 py-2 border-b border-fantasy-border/60 bg-fantasy-darker/75 flex items-center justify-between gap-2 shrink-0">
                          <button
                            type="button"
                            onClick={() => setMobileView('list')}
                            className="hk-btn hk-btn-ghost min-h-[44px] px-3 text-sm"
                          >
                            <ArrowLeft size={16} aria-hidden="true" />
                            <span>{t('atlas.back_to_regions', 'Regions')}</span>
                          </button>
                          {activeQuestDestinations.length > 0 && (
                            <button
                              type="button"
                              onClick={() => {
                                setLeftTab('quests');
                                setMobileView('list');
                              }}
                              className="hk-btn hk-btn-ghost min-h-[44px] px-3 text-sm text-amber-300"
                            >
                              <Crosshair size={15} aria-hidden="true" />
                              <span>{t('atlas.tab_quests', 'Quests')} ({activeQuestDestinations.length})</span>
                            </button>
                          )}
                        </div>
                      )}

                      {/* Region Banner Header */}
                      <div className={`${useTwoColumnDrawer ? 'px-3.5 py-2.5' : 'px-4 sm:px-6 py-4'} border-b border-fantasy-border/60 bg-fantasy-darker/40 shrink-0 space-y-1`}>
                        <div className="flex items-start justify-between gap-2 flex-wrap">
                          <h3 className={`hk-atlas-heading font-rpg font-bold ${useTwoColumnDrawer ? 'text-sm sm:text-base' : 'text-base sm:text-lg'} text-gray-100 flex items-center gap-1.5 flex-wrap`}>
                            <span aria-hidden="true">{activeZoneObj.emoji || '🗺️'}</span>
                            <span className="break-words">{activeZoneObj.zone_name}</span>
                          </h3>
                          <span className="text-[11px] font-mono text-fantasy-accent bg-fantasy-accent/10 px-2 py-0.5 rounded-lg border border-fantasy-accent/30 shrink-0">
                            {activeZoneObj.is_current
                              ? t('atlas.current_region', '📍 Current Region')
                              : `🧭 ${activeZoneObj.travel_tag || t('atlas.cross_region_travel', 'Cross-Region Travel')}`}
                          </span>
                        </div>
                        {activeZoneObj.theme && (
                          <p className={`${useTwoColumnDrawer ? 'text-xs' : 'text-sm'} text-gray-400 hk-atlas-prose leading-relaxed`}>
                            {activeZoneObj.theme}
                          </p>
                        )}
                      </div>

                      {/* Primary Locations Vertical List */}
                      <div className={`hk-atlas-scroll flex-1 min-h-0 overflow-y-auto custom-scrollbar ${useTwoColumnDrawer ? 'p-3 space-y-2.5' : 'p-4 sm:p-5 space-y-3.5'}`}>
                        {primaryPlaces.length === 0 ? (
                          <div className="hk-card p-6 text-center space-y-3.5">
                            <p className="text-sm text-gray-300 hk-atlas-prose">
                              {t('atlas.hub_ready', {
                                zone: activeZoneObj.zone_name,
                                defaultValue: `Main hub of ${activeZoneObj.zone_name} is ready for exploration.`,
                              })}
                            </p>
                            <button
                              type="button"
                              disabled={processingTurn || !canTravel}
                              onClick={() => handleTravel(activeZoneObj.zone_name)}
                              className="hk-btn hk-btn-primary min-h-[44px] md:min-h-[38px] text-sm"
                            >
                              <Navigation size={15} aria-hidden="true" />
                              <span>
                                {t('atlas.travel_to_zone', {
                                  zone: activeZoneObj.zone_name,
                                  defaultValue: `Travel to ${activeZoneObj.zone_name}`,
                                })}
                              </span>
                            </button>
                          </div>
                        ) : filteredPlaces.length === 0 ? (
                          <div className="p-8 text-center space-y-3 text-gray-400">
                            <p className="text-sm hk-atlas-prose">{t('atlas.no_search_results', 'No matching regions, locations, or rooms found.')}</p>
                            <button
                              type="button"
                              onClick={() => setSearchQuery('')}
                              className="hk-btn hk-btn-ghost min-h-[44px] md:min-h-[36px]"
                            >
                              {t('atlas.clear_search', 'Clear search')}
                            </button>
                          </div>
                        ) : (
                          filteredPlaces.map((place, idx) => {
                            const placeName = place.name;
                            const placeKey = `${activeZoneObj.zone_name}::${placeName}`;
                            const placeRefKey = placeKey.toLowerCase();
                            const isHere = Boolean(place.is_current_place);
                            const destValue = place.value || `${activeZoneObj.zone_name} ➔ ${placeName}`;
                            const subLocationItems = getSubItemsForPlace(place);

                            const subQuestCount = Number(
                              place.sub_quest_count ??
                                subLocationItems.reduce(
                                  (acc, s) => acc + ((typeof s === 'object' && s !== null && Array.isArray(s.quest_markers)) ? s.quest_markers.length : 0),
                                  0
                                )
                            );
                            const directQuestMarkers = Array.isArray(place.direct_quest_markers)
                              ? place.direct_quest_markers
                              : (subQuestCount > 0 ? [] : (Array.isArray(place.quest_markers) ? place.quest_markers : []));
                            const hasDirectQuest = directQuestMarkers.length > 0;
                            const directQuestMeta = hasDirectQuest
                              ? getQuestBadgeMeta(place.direct_quest_tag || directQuestMarkers[0], t)
                              : null;
                            const subQuestMeta = subQuestCount > 0
                              ? getQuestBadgeMeta((place.sub_quest_tags && place.sub_quest_tags[0]) || place.quest_tag || '', t)
                              : null;

                            const isTargetPlace = Boolean(
                              highlightedTarget &&
                              (!highlightedTarget.zoneName || highlightedTarget.zoneName.toLowerCase() === activeZoneObj.zone_name.toLowerCase()) &&
                              highlightedTarget.placeName &&
                              highlightedTarget.placeName.toLowerCase() === placeName.toLowerCase()
                            );
                            const subMatchesQuery = Boolean(
                              trimmedQuery &&
                              subLocationItems.some(sub =>
                                typeof sub === 'object' && sub !== null
                                  ? textMatchesQuery(sub.name || sub.label, trimmedQuery) ||
                                    (sub.quest_markers || []).some(m => textMatchesQuery(m, trimmedQuery)) ||
                                    (sub.known_npcs_here || []).some(kn => textMatchesQuery(kn?.name, trimmedQuery))
                                  : textMatchesQuery(sub, trimmedQuery)
                              )
                            );
                            const defaultExpanded = Boolean(
                              isHere || subQuestCount > 0 || hasDirectQuest || isTargetPlace || subMatchesQuery
                            );
                            const isExpanded = expandedPlaces[placeKey] !== undefined
                              ? expandedPlaces[placeKey]
                              : defaultExpanded;

                            const rawBadges = String(place.badges || '');
                            const facilityPills = facilityBadgeLabels.filter(fb => rawBadges.includes(fb.icon));
                            const nonDefaultAccess = getNonDefaultAccessBadge(
                              place.access_badge,
                              place.is_curfew_active,
                              place.schedule_locked,
                              t
                            );

                            const cardToneCls = isHere
                              ? 'border-emerald-500/60 bg-emerald-950/15'
                              : hasDirectQuest
                                ? (directQuestMeta?.surfaceCls || 'border-amber-500/60 bg-amber-950/15')
                                : subQuestCount > 0
                                  ? 'border-fantasy-accent/45'
                                  : '';

                            return (
                              <article
                                key={placeName || idx}
                                ref={(el) => {
                                  if (el) placeRefs.current[placeRefKey] = el;
                                }}
                                className={`hk-card ${useTwoColumnDrawer ? 'p-3 space-y-2' : 'p-4 space-y-3'} ${cardToneCls} ${
                                  isTargetPlace && !highlightedTarget?.subName ? 'ring-2 ring-fantasy-accent' : ''
                                }`}
                              >
                                {/* Building Card Header */}
                                <div className={`flex flex-col ${useTwoColumnDrawer ? 'gap-2' : 'sm:flex-row sm:items-start justify-between gap-3'}`}>
                                  <div className="min-w-0 flex-1 space-y-1.5">
                                    <div className="flex items-start flex-wrap gap-1.5">
                                      <span className={`${useTwoColumnDrawer ? 'text-sm' : 'text-base'} leading-snug shrink-0`} aria-hidden="true">
                                        {place.archetype_emoji || place.emoji || '📍'}
                                      </span>
                                      <h4 className={`${useTwoColumnDrawer ? 'text-sm' : 'text-[15px]'} font-semibold text-gray-100 leading-snug break-words`}>
                                        {placeName}
                                      </h4>
                                      {isHere && (
                                        <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-950/75 text-emerald-300 border border-emerald-600/50 font-semibold">
                                          {t('atlas.here', 'Here')}
                                        </span>
                                      )}
                                      {hasDirectQuest && directQuestMeta && (
                                        <span className={`text-xs px-2.5 py-0.5 rounded-full border font-bold ${directQuestMeta.badgeCls}`}>
                                          {directQuestMeta.icon} {directQuestMeta.label}
                                        </span>
                                      )}
                                      {!hasDirectQuest && subQuestCount > 0 && subQuestMeta && (
                                        <span className="text-xs font-semibold text-fantasy-accent flex items-center gap-1">
                                          <span>{subQuestMeta.icon}</span>
                                          <span>
                                            {subQuestCount === 1
                                              ? t('atlas.quests_inside', { count: 1, defaultValue: '1 quest inside' })
                                              : t('atlas.quests_inside_plural', { count: subQuestCount, defaultValue: `${subQuestCount} quests inside` })}
                                          </span>
                                        </span>
                                      )}
                                    </div>

                                    {/* Quiet Secondary Metadata Line */}
                                    <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 text-xs text-gray-400">
                                      {!isHere && place.travel_tag && (
                                        <span className="font-mono text-gray-300">
                                          ⏱ {place.travel_tag}
                                        </span>
                                      )}
                                      {place.archetype && (
                                        <span>{place.archetype}</span>
                                      )}
                                      {place.is_transit_hub && (
                                        <span className="px-2 py-0.5 rounded-full bg-cyan-950/50 text-cyan-200 border border-cyan-800/50 font-medium">
                                          🚀 {t('atlas.transit_hub', 'Transit Hub')}
                                        </span>
                                      )}
                                      {nonDefaultAccess && (
                                        <span className={`px-2 py-0.5 rounded-full border font-medium ${nonDefaultAccess.cls}`}>
                                          {nonDefaultAccess.label}
                                        </span>
                                      )}
                                      {place.anomalous_site_meta?.badge && (() => {
                                        const tone = place.anomalous_site_meta.badge_tone || 'amber';
                                        const pillCls = tone === 'emerald'
                                          ? 'bg-emerald-950/70 text-emerald-200 border-emerald-500/60'
                                          : tone === 'crimson'
                                            ? 'bg-fuchsia-950/70 text-fuchsia-200 border-fuchsia-500/60'
                                            : tone === 'red'
                                              ? 'bg-rose-950/70 text-rose-200 border-rose-500/60'
                                              : tone === 'slate'
                                                ? 'bg-slate-900/75 text-slate-200 border-slate-600/60'
                                                : 'bg-amber-950/70 text-amber-200 border-amber-500/60';
                                        return (
                                          <span
                                            className={`px-2 py-0.5 rounded-full font-semibold border ${pillCls}`}
                                            title={place.anomalous_site_meta.tooltip || ''}
                                          >
                                            {place.anomalous_site_meta.badge}
                                          </span>
                                        );
                                      })()}
                                      {facilityPills.map((fp, fIdx) => (
                                        <span key={fIdx} className={`px-2 py-0.5 rounded-full border font-medium ${fp.color}`}>
                                          {fp.label}
                                        </span>
                                      ))}
                                    </div>

                                    {/* Live Occupancy */}
                                    {(place.known_npcs_here?.length > 0 || place.unmet_activity_count > 0) && (
                                      <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                                        {place.known_npcs_here?.map((kn, knIdx) => (
                                          <span
                                            key={knIdx}
                                            className={`text-xs px-2.5 py-0.5 rounded-full border font-medium inline-flex items-center gap-1 ${
                                              kn.status === 'Rendezvous'
                                                ? 'bg-amber-950/60 text-amber-200 border-amber-500/50'
                                                : 'bg-sky-950/50 text-sky-200 border-sky-700/45'
                                            }`}
                                          >
                                            <span>👤 {kn.name}</span>
                                            {kn.status === 'Rendezvous' && (
                                              <span className="text-amber-300 font-semibold">{t('atlas.meetup', '• Meetup')}</span>
                                            )}
                                          </span>
                                        ))}
                                        {place.unmet_activity_count > 0 && (
                                          <span className="text-xs px-2 py-0.5 rounded-full bg-black/40 text-gray-400 border border-fantasy-border/50 font-mono">
                                            👥 +{place.unmet_activity_count}
                                          </span>
                                        )}
                                      </div>
                                    )}

                                    {/* Persistent Memory Residue */}
                                    {place.scene_residue && (
                                      <p className="text-xs text-gray-400 italic hk-atlas-prose pt-0.5">
                                        💭 {t('atlas.memory_prefix', 'Memory:')} &ldquo;{place.scene_residue}&rdquo;
                                      </p>
                                    )}
                                  </div>

                                  {/* Primary Building Travel Action */}
                                  <div className="shrink-0">
                                    {isHere ? (
                                      <span className="inline-flex items-center px-3 py-1.5 rounded-lg bg-emerald-950/60 text-emerald-300 border border-emerald-700/50 text-xs font-semibold">
                                        {t('atlas.current_location', 'Current Location')}
                                      </span>
                                    ) : (
                                      <button
                                        type="button"
                                        disabled={processingTurn || !canTravel || place.can_travel === false}
                                        title={!canTravel ? (travelBlockedReason || t('atlas.travel_blocked', 'Fast travel is currently unavailable.')) : undefined}
                                        onClick={() => handleTravel(destValue)}
                                        className={`hk-btn ${
                                          useTwoColumnDrawer
                                            ? 'h-8 min-h-[32px] text-xs px-2.5'
                                            : 'min-h-[44px] md:min-h-[36px] text-sm px-3.5'
                                        } ${
                                          hasDirectQuest ? 'hk-btn-primary' : 'hk-btn-ghost border border-fantasy-border/70'
                                        }`}
                                      >
                                        <span>{t('atlas.travel_here', 'Travel Here')}</span>
                                        <ArrowRight size={14} aria-hidden="true" />
                                      </button>
                                    )}
                                  </div>
                                </div>

                                {/* Building-Level Direct Quest Objective Callout (only when not pinned to a specific Tier 3 room) */}
                                {hasDirectQuest && (
                                  <div className="border-l-2 border-amber-400/80 bg-amber-950/30 rounded-r-lg px-3 py-2 space-y-1">
                                    {directQuestMarkers.map((qm, qmIdx) => (
                                      <p key={qmIdx} className="text-sm text-gray-100 leading-snug hk-atlas-prose">
                                        {formatMarkerObjective(qm)}
                                      </p>
                                    ))}
                                  </div>
                                )}

                                {/* Tier 3 Rooms / Wings (Progressive Disclosure + Structured Readable Rows) */}
                                {!place.is_unpurchased_realty && subLocationItems.length > 0 && (
                                  <div className="pt-2 border-t border-fantasy-border/45 space-y-2">
                                    <button
                                      type="button"
                                      onClick={() => togglePlaceExpanded(placeKey, isExpanded)}
                                      aria-expanded={isExpanded}
                                      className="w-full flex items-center justify-between gap-2 text-left py-1.5 px-1 min-h-[40px] md:min-h-[32px] text-xs font-semibold text-gray-300 hover:text-gray-100 transition-colors"
                                    >
                                      <span className="flex items-center gap-1.5">
                                        {isExpanded
                                          ? <ChevronDown size={15} className="text-fantasy-accent shrink-0" aria-hidden="true" />
                                          : <ChevronRight size={15} className="text-gray-400 shrink-0" aria-hidden="true" />}
                                        <span>
                                          {t('atlas.rooms_wings', 'Rooms / Wings:').replace(/[:：]\s*$/, '')} ({subLocationItems.length})
                                        </span>
                                      </span>
                                      {!isExpanded && subQuestCount > 0 && subQuestMeta && (
                                        <span className={`px-2 py-0.5 rounded-full border text-xs font-semibold ${subQuestMeta.badgeCls}`}>
                                          {subQuestMeta.icon} {subQuestCount === 1
                                            ? t('atlas.quests_inside', { count: 1, defaultValue: '1 quest inside' })
                                            : t('atlas.quests_inside_plural', { count: subQuestCount, defaultValue: `${subQuestCount} quests inside` })}
                                        </span>
                                      )}
                                    </button>

                                    {isExpanded && (
                                      <div className="space-y-2">
                                        {subLocationItems.map((sub, sIdx) => {
                                          const isObj = typeof sub === 'object' && sub !== null;
                                          const subName = isObj ? (sub.name || sub.label) : sub;
                                          if (!subName) return null;

                                          const subHere = Boolean(isObj && sub.is_current_room);
                                          const subValue = (isObj && sub.value) ? sub.value : `${activeZoneObj.zone_name} ➔ ${placeName} ➔ ${subName}`;
                                          const subEta = isObj ? (sub.travel_tag || '') : '';
                                          const subBadge = isObj ? String(sub.access_badge || '') : '';
                                          const subLocked = Boolean(
                                            isObj && !sub.is_unlocked && (
                                              subBadge.includes('Closed') ||
                                              subBadge.includes('Locked') ||
                                              subBadge === 'Restricted' ||
                                              subBadge === 'Private'
                                            )
                                          );
                                          const subAccessPill = isObj
                                            ? getNonDefaultAccessBadge(subBadge, false, subLocked, t)
                                            : null;

                                          const subQuestMarkers = isObj && Array.isArray(sub.quest_markers) ? sub.quest_markers : [];
                                          const subQuestTags = isObj && Array.isArray(sub.quest_tags) && sub.quest_tags.length > 0
                                            ? sub.quest_tags
                                            : (isObj && sub.quest_tag ? [sub.quest_tag] : []);
                                          const subHasQuest = subQuestMarkers.length > 0 || subQuestTags.length > 0;
                                          const primarySubQuestMeta = subHasQuest
                                            ? getQuestBadgeMeta((isObj && sub.quest_kind) || subQuestTags[0] || subQuestMarkers[0], t)
                                            : null;

                                          const subTagLabels = isObj ? [
                                            sub.is_faction_hq ? `🏛️ ${t('atlas.sub_tag_hq', 'Club HQ')}` : '',
                                            sub.has_bounty_board ? `📋 ${t('atlas.sub_tag_board', 'Notice Board')}` : '',
                                            sub.has_merchant_shop ? `🛍️ ${t('atlas.sub_tag_shop', 'Merchant / Quartermaster')}` : '',
                                            sub.is_transit_hub ? `🚀 ${t('atlas.sub_tag_transit', 'Transit Hub')}` : '',
                                            sub.is_discreet ? `🤫 ${t('atlas.sub_tag_discreet', 'Discreet')}` : '',
                                          ].filter(Boolean) : [];

                                          const isTargetSub = Boolean(
                                            isTargetPlace &&
                                            highlightedTarget?.subName &&
                                            highlightedTarget.subName.toLowerCase() === subName.toLowerCase()
                                          );
                                          const roomRefKey = `${activeZoneObj.zone_name}::${placeName}::${subName}`.toLowerCase();

                                          const roomToneCls = subHere
                                            ? 'border-emerald-600/60 bg-emerald-950/20'
                                            : subHasQuest
                                              ? (primarySubQuestMeta?.surfaceCls || 'border-amber-500/60 bg-amber-950/20')
                                              : 'border-fantasy-border/55 bg-fantasy-darker/35';

                                          return (
                                            <div
                                              key={`${subName}-${sIdx}`}
                                              ref={(el) => {
                                                if (el) roomRefs.current[roomRefKey] = el;
                                              }}
                                              className={`${useTwoColumnDrawer ? 'p-2.5 gap-2' : 'p-3 sm:flex-row sm:items-center gap-2.5'} rounded-xl border flex flex-col justify-between transition-colors ${roomToneCls} ${
                                                isTargetSub ? 'ring-2 ring-fantasy-accent' : ''
                                              }`}
                                            >
                                              <div className="min-w-0 flex-1 space-y-1.5">
                                                <div className="flex items-start flex-wrap gap-2">
                                                  <span className="text-sm leading-snug shrink-0" aria-hidden="true">
                                                    {subHere ? '📍' : (subLocked ? '🔒' : '↳')}
                                                  </span>
                                                  <span className="text-sm font-semibold text-gray-100 leading-snug break-words">
                                                    {subName}
                                                  </span>
                                                  {subQuestTags.map((qTag, qtIdx) => {
                                                    const tagMeta = getQuestBadgeMeta(qTag, t);
                                                    return (
                                                      <span
                                                        key={qtIdx}
                                                        className={`text-xs px-2.5 py-0.5 rounded-full border font-bold ${tagMeta.badgeCls}`}
                                                      >
                                                        {tagMeta.icon} {tagMeta.label}
                                                      </span>
                                                    );
                                                  })}
                                                </div>

                                                {/* Room Secondary Metadata */}
                                                {( (!subHere && subEta) || subAccessPill || subTagLabels.length > 0 || (isObj && sub.anomalous_site_meta?.badge) || (isObj && sub.known_npcs_here?.length > 0) ) && (
                                                  <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-gray-400">
                                                    {!subHere && subEta && (
                                                      <span className="font-mono text-gray-300">⏱ {subEta}</span>
                                                    )}
                                                    {subAccessPill && (
                                                      <span className={`px-2 py-0.5 rounded-full border font-medium ${subAccessPill.cls}`}>
                                                        {subAccessPill.label}
                                                      </span>
                                                    )}
                                                    {subTagLabels.map((lbl, lIdx) => (
                                                      <span key={lIdx} className="text-gray-300">{lbl}</span>
                                                    ))}
                                                    {isObj && sub.anomalous_site_meta?.badge && (
                                                      <span
                                                        className={`px-2 py-0.5 rounded-full border font-semibold ${
                                                          sub.anomalous_site_meta.badge_tone === 'emerald'
                                                            ? 'bg-emerald-950/70 text-emerald-200 border-emerald-600/60'
                                                            : 'bg-amber-950/70 text-amber-200 border-amber-600/60'
                                                        }`}
                                                        title={sub.anomalous_site_meta.tooltip || ''}
                                                      >
                                                        {sub.anomalous_site_meta.badge}
                                                      </span>
                                                    )}
                                                    {isObj && sub.known_npcs_here?.map((kn, knIdx) => (
                                                      <span
                                                        key={knIdx}
                                                        className={kn.status === 'Rendezvous' ? 'text-amber-300 font-medium' : 'text-sky-300'}
                                                      >
                                                        👤 {kn.name}{kn.status === 'Rendezvous' ? ` ${t('atlas.meetup', '• Meetup')}` : ''}
                                                      </span>
                                                    ))}
                                                  </div>
                                                )}

                                                {/* Tier 3 Pinned Quest / Bounty Objective Text */}
                                                {subQuestMarkers.length > 0 && (
                                                  <div className="space-y-1 pt-0.5">
                                                    {subQuestMarkers.map((qm, qmIdx) => (
                                                      <p key={qmIdx} className="text-sm text-gray-100 leading-snug hk-atlas-prose">
                                                        {formatMarkerObjective(qm)}
                                                      </p>
                                                    ))}
                                                  </div>
                                                )}
                                              </div>

                                              {/* Tier 3 Room Travel Button */}
                                              <div className="shrink-0">
                                                {subHere ? (
                                                  <span className="inline-flex items-center px-2.5 py-1 rounded-lg bg-emerald-950/65 text-emerald-300 border border-emerald-700/50 text-xs font-semibold">
                                                    {t('atlas.here', 'Here')}
                                                  </span>
                                                ) : (
                                                  <button
                                                    type="button"
                                                    disabled={processingTurn || !canTravel || place.can_travel === false}
                                                    title={!canTravel ? (travelBlockedReason || t('atlas.travel_blocked', 'Fast travel is currently unavailable.')) : undefined}
                                                    onClick={() => handleTravel(subValue)}
                                                    className={`hk-btn ${
                                                      useTwoColumnDrawer
                                                        ? 'h-8 min-h-[32px] text-xs px-2.5'
                                                        : 'min-h-[44px] md:min-h-[36px] text-xs sm:text-sm px-3'
                                                    } ${
                                                      subHasQuest ? 'hk-btn-primary' : 'hk-btn-ghost border border-fantasy-border/70'
                                                    }`}
                                                  >
                                                    <span>{t('atlas.travel', 'Travel')}</span>
                                                    <ArrowRight size={13} aria-hidden="true" />
                                                  </button>
                                                )}
                                              </div>
                                            </div>
                                          );
                                        })}
                                      </div>
                                    )}
                                  </div>
                                )}
                              </article>
                            );
                          })
                        )}
                      </div>
                    </>
                  )}
                </section>
              )}
            </div>
          )}
        </div>
  );

  if (isDrawer) {
    return isOpen ? atlasContent : null;
  }

  return (
    <dialog
      ref={dialogRef}
      className="hk-atlas-dialog"
      aria-labelledby={titleId}
      {...{ closedby: 'any' }}
      onClose={handleDialogClose}
    >
      {isOpen && atlasContent}
    </dialog>
  );
};

export default WorldMapModal;
