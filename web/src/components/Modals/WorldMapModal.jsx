import React, { useState, useEffect } from 'react';
import { Map, Compass, MapPin, Navigation, Sparkles, X, RefreshCw, ArrowRight, Target } from 'lucide-react';
import { apiCall } from '../../api/client';

const FACILITY_BADGE_LABELS = [
  { icon: '📋', label: '📋 Notice Board', color: 'bg-amber-950/60 text-amber-300 border-amber-700/50' },
  { icon: '💾', label: '💾 Job Terminal', color: 'bg-cyan-950/60 text-cyan-300 border-cyan-700/50' },
  { icon: '📡', label: '📡 Comm Terminal', color: 'bg-cyan-950/60 text-cyan-300 border-cyan-700/50' },
  { icon: '📻', label: '📻 Dispatch Board', color: 'bg-amber-950/60 text-amber-300 border-amber-700/50' },
  { icon: '🛍️', label: '🛍️ Merchant Shop', color: 'bg-purple-950/60 text-purple-300 border-purple-700/50' },
  { icon: '🏛️', label: '🏛️ Faction HQ', color: 'bg-blue-950/60 text-blue-300 border-blue-700/50' },
  { icon: '🏠', label: '🏠 Home', color: 'bg-emerald-950/60 text-emerald-300 border-emerald-700/50' },
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

const WorldMapModal = ({ isOpen, onClose, session, user, onTravel, initialTargetLocation }) => {
  const [mapData, setMapData] = useState(null);
  const [selectedZone, setSelectedZone] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchLocations = async () => {
    if (!session?.id) return;
    setLoading(true);
    setError(null);
    try {
      const uidParam = user?.user_id ? `?user_id=${user.user_id}` : '';
      const data = await apiCall(`/api/locations/${session.id}${uidParam}`);
      setMapData(data);
      const zones = data?.zones || [];
      const matchedInitial = extractZoneFromTarget(initialTargetLocation, zones);
      const currentZone = zones.find(z => z.is_current) || zones[0] || null;
      setSelectedZone(matchedInitial || (currentZone ? currentZone.zone_name : null));
    } catch (err) {
      setError(err.message || 'Failed to load world map.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen && session?.id) {
      fetchLocations();
    }
  }, [isOpen, session?.id, session?.current_location, initialTargetLocation]);

  if (!isOpen) return null;

  const zones = mapData?.zones || [];
  const activeZoneObj = zones.find(z => z.zone_name === selectedZone) || zones[0] || null;
  const primaryPlaces = activeZoneObj?.primary_locations || [];

  // Collect all active quest destinations across all zones
  const activeQuestDestinations = mapData?.active_quest_destinations || zones.flatMap(z =>
    (z.primary_locations || []).flatMap(p =>
      (p.quest_markers || []).map(qm => ({
        zone_name: z.zone_name,
        place_name: p.name,
        value: p.value || `${z.zone_name} ➔ ${p.name}`,
        marker: qm,
        quest_tag: p.quest_tag || '⭐ Quest Objective',
        is_current_place: Boolean(p.is_current_place),
      }))
    )
  );

  const handleTravel = (destValue) => {
    if (!destValue || !onTravel) return;
    onTravel(destValue);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
      <div className="bg-fantasy-panel border border-fantasy-border rounded-xl shadow-2xl w-full max-w-4xl max-h-[88vh] flex flex-col overflow-hidden">
        
        {/* Top Modal Header */}
        <div className="px-5 py-3.5 border-b border-fantasy-border flex items-center justify-between bg-black/50">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-fantasy-accent/15 border border-fantasy-accent/40 flex items-center justify-center text-fantasy-accent">
              <Map size={20} />
            </div>
            <div>
              <h2 className="font-rpg font-bold text-base text-gray-100 tracking-wider uppercase flex items-center gap-2">
                <span>World Atlas & Fast-Travel</span>
                {activeQuestDestinations.length > 0 && (
                  <span className="text-[10px] font-sans font-bold px-2 py-0.5 rounded-full bg-amber-500/25 text-amber-300 border border-amber-500/60">
                    ⭐ {activeQuestDestinations.length} Active Quest Lead{activeQuestDestinations.length > 1 ? 's' : ''}
                  </span>
                )}
              </h2>
              <p className="text-xs text-gray-400 flex items-center gap-1.5 mt-0.5">
                <MapPin size={12} className="text-fantasy-accent shrink-0" />
                <span>Current Position:</span>
                <strong className="text-gray-200">{session?.current_location || 'Unknown Area'}</strong>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={fetchLocations}
              disabled={loading}
              className="p-2 rounded-lg bg-black/50 hover:bg-black/80 text-gray-400 hover:text-gray-200 border border-fantasy-border transition-colors"
              title="Refresh Atlas"
            >
              <RefreshCw size={15} className={loading ? 'animate-spin text-fantasy-accent' : ''} />
            </button>
            <button
              onClick={onClose}
              className="p-2 rounded-lg bg-black/50 hover:bg-red-950/50 text-gray-400 hover:text-red-300 border border-fantasy-border transition-colors"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* High-Visibility Active Quest Destinations Quick-Jump Bar */}
        {activeQuestDestinations.length > 0 && (
          <div className="px-4 py-2.5 bg-gradient-to-r from-amber-950/50 via-black/70 to-amber-950/40 border-b border-amber-600/50 space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold uppercase tracking-wider text-amber-300 flex items-center gap-1.5">
                <Target size={12} className="text-amber-400" />
                <span>Active Quest Destinations — Click to Locate or Fast-Travel</span>
              </span>
            </div>
            <div className="flex gap-2 overflow-x-auto custom-scrollbar pb-1">
              {activeQuestDestinations.map((qd, idx) => {
                const isSelectedZone = activeZoneObj?.zone_name === qd.zone_name;
                return (
                  <div
                    key={`${qd.value}-${idx}`}
                    onClick={() => setSelectedZone(qd.zone_name)}
                    className={`flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg border cursor-pointer transition-all shrink-0 max-w-xs ${
                      isSelectedZone
                        ? 'bg-amber-500/20 border-amber-400 text-amber-100 shadow-sm'
                        : 'bg-black/60 border-amber-700/60 hover:border-amber-500 text-gray-200'
                    }`}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="text-[11px] font-bold text-amber-300 truncate">
                        📍 {qd.zone_name} ➔ {qd.place_name}
                      </div>
                      <div className="text-[10px] text-gray-300 truncate" title={qd.marker}>
                        {qd.marker}
                      </div>
                    </div>
                    {qd.is_current_place ? (
                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-950/80 text-emerald-300 border border-emerald-700/60 font-bold uppercase shrink-0">
                        Here
                      </span>
                    ) : (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleTravel(qd.value);
                        }}
                        className="px-2 py-1 rounded bg-amber-500/25 hover:bg-amber-500/40 text-amber-200 border border-amber-400/60 text-[10px] font-bold shrink-0 flex items-center gap-1 transition-colors"
                      >
                        <span>Travel</span>
                        <ArrowRight size={10} />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Body — 2-Column Interactive Atlas */}
        {loading && !mapData ? (
          <div className="flex-1 flex flex-col items-center justify-center py-20 text-gray-400 space-y-2">
            <Compass size={32} className="animate-spin text-fantasy-accent opacity-70" />
            <p className="text-xs italic">Charting discovered regions and waypoints...</p>
          </div>
        ) : error ? (
          <div className="p-8 text-center text-red-300 text-xs">{error}</div>
        ) : zones.length === 0 ? (
          <div className="p-12 text-center text-gray-500 space-y-2">
            <Map size={32} className="mx-auto opacity-30" />
            <p className="text-sm font-semibold text-gray-400">No Regions Charted Yet</p>
            <p className="text-xs">Explore your surroundings to unlock regions and fast-travel destinations.</p>
          </div>
        ) : (
          <div className="flex-1 grid grid-cols-1 md:grid-cols-12 min-h-[400px] overflow-hidden">
            
            {/* Left Column: Discovered Regions / Zones */}
            <div className="md:col-span-5 border-r border-fantasy-border bg-black/35 flex flex-col overflow-hidden">
              <div className="px-4 py-2.5 border-b border-fantasy-border/60 flex items-center justify-between">
                <span className="text-[11px] font-bold uppercase tracking-wider text-gray-400 flex items-center gap-1.5">
                  <Compass size={13} className="text-fantasy-accent" />
                  <span>Discovered Regions ({zones.length})</span>
                </span>
              </div>

              <div className="flex-1 overflow-y-auto custom-scrollbar p-3 space-y-2">
                {zones.map((z) => {
                  const isSelected = activeZoneObj?.zone_name === z.zone_name;
                  const zoneQuestMarkers = Array.isArray(z.quest_markers) ? z.quest_markers : [];
                  const questTags = (z.active_tags || []).filter(t =>
                    t.includes('Quest') || t.includes('Climax') || t.includes('Bounty') || t.includes('Meetup')
                  );
                  const otherTags = (z.active_tags || []).filter(t => !questTags.includes(t));
                  const questCount = z.quest_count || zoneQuestMarkers.length || questTags.length;
                  const hasQuest = questCount > 0;

                  return (
                    <button
                      key={z.zone_name}
                      onClick={() => setSelectedZone(z.zone_name)}
                      className={`w-full text-left p-3 rounded-lg border transition-all flex flex-col gap-1.5 ${
                        isSelected
                          ? hasQuest
                            ? 'bg-amber-500/20 border-amber-400 text-gray-100 shadow-md ring-1 ring-amber-400/40'
                            : 'bg-fantasy-accent/15 border-fantasy-accent text-gray-100 shadow-md'
                          : hasQuest
                            ? 'bg-amber-950/30 border-amber-500/70 hover:border-amber-400 text-gray-100 shadow-sm'
                            : 'bg-black/50 border-fantasy-border/60 hover:border-fantasy-border text-gray-300'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2 w-full">
                        <div className="flex items-center gap-1.5 min-w-0 flex-wrap">
                          <span className="text-sm shrink-0">{z.is_current ? '🧭' : (z.emoji || '📍')}</span>
                          <span className="font-semibold text-xs truncate">{z.zone_name}</span>
                          {z.is_current && (
                            <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-950/80 text-emerald-300 border border-emerald-700/60 font-bold uppercase shrink-0">
                              Here
                            </span>
                          )}
                        </div>

                        <div className="flex items-center gap-1 shrink-0">
                          {hasQuest && (
                            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-500 text-black shadow-sm flex items-center gap-1">
                              <span>⭐ {questCount} Quest{questCount > 1 ? 's' : ''}</span>
                            </span>
                          )}
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-black/60 text-gray-400 border border-fantasy-border/50">
                            {z.places_count || (z.primary_locations?.length ?? 0)}
                          </span>
                        </div>
                      </div>

                      {z.theme && (
                        <p className="text-[10px] text-gray-400 truncate w-full">
                          {z.theme}
                        </p>
                      )}

                      {/* Quest Target Place Callout on Region Card */}
                      {zoneQuestMarkers.length > 0 && (
                        <div className="w-full space-y-0.5 pt-0.5">
                          {zoneQuestMarkers.map((qm, qIdx) => (
                            <div
                              key={qIdx}
                              className="text-[10px] text-amber-300 bg-amber-950/60 border border-amber-600/50 rounded px-2 py-0.5 truncate font-medium"
                              title={`${qm.place_name}: ${qm.marker}`}
                            >
                              📍 <strong>{qm.place_name}</strong> — {qm.marker}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Regional Tags */}
                      {(questTags.length > 0 || otherTags.length > 0) && (
                        <div className="flex flex-wrap gap-1 pt-0.5">
                          {questTags.map((t, idx) => (
                            <span
                              key={`qt-${idx}`}
                              className="text-[9px] px-1.5 py-0.2 rounded bg-amber-500/25 text-amber-200 border border-amber-500/60 font-bold"
                            >
                              {t}
                            </span>
                          ))}
                          {otherTags.map((t, idx) => (
                            <span
                              key={`ot-${idx}`}
                              className="text-[9px] px-1.5 py-0.2 rounded bg-black/60 text-gray-400 border border-fantasy-border/50"
                            >
                              {t}
                            </span>
                          ))}
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Right Column: Primary Locations in Selected Zone */}
            <div className="md:col-span-7 flex flex-col overflow-hidden bg-black/20">
              {activeZoneObj && (
                <>
                  <div className="px-5 py-3 border-b border-fantasy-border/60 bg-black/40 flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <h3 className="font-rpg font-bold text-sm text-gray-100 flex items-center gap-2 flex-wrap">
                        <span>{activeZoneObj.emoji || '🗺️'}</span>
                        <span>{activeZoneObj.zone_name}</span>
                        {(activeZoneObj.quest_count > 0 || (activeZoneObj.quest_markers && activeZoneObj.quest_markers.length > 0)) && (
                          <span className="text-[10px] font-sans font-bold px-2 py-0.5 rounded-full bg-amber-500/25 text-amber-300 border border-amber-500/60">
                            ⭐ Active Quest Region
                          </span>
                        )}
                      </h3>
                      {activeZoneObj.theme && (
                        <p className="text-[11px] text-gray-400 mt-0.5">{activeZoneObj.theme}</p>
                      )}
                    </div>
                    <span className="text-[10px] font-mono text-fantasy-accent bg-fantasy-accent/10 px-2.5 py-1 rounded border border-fantasy-accent/30 shrink-0">
                      { activeZoneObj.is_current ? '⚡ Same Region (Instant Local)' : '🧭 Cross-Region Travel' }
                    </span>
                  </div>

                  <div className="flex-1 overflow-y-auto custom-scrollbar p-4 space-y-3">
                    {primaryPlaces.length === 0 ? (
                      <div className="bg-black/40 border border-fantasy-border/60 rounded-lg p-5 text-center space-y-3">
                        <p className="text-xs text-gray-400">
                          Main hub of <strong>{activeZoneObj.zone_name}</strong> is ready for exploration.
                        </p>
                        <button
                          onClick={() => handleTravel(`${activeZoneObj.zone_name} ➔ Main Area`)}
                          className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-fantasy-accent/20 hover:bg-fantasy-accent/30 text-fantasy-accent border border-fantasy-accent/50 text-xs font-bold transition-all"
                        >
                          <Navigation size={13} />
                          <span>Travel to {activeZoneObj.zone_name}</span>
                        </button>
                      </div>
                    ) : (
                      primaryPlaces.map((place, idx) => {
                        const isInstant = place.travel_tag === 'Instant Local';
                        const isHere = Boolean(place.is_current_place);
                        const placeName = place.name;
                        const destValue = place.value || `${activeZoneObj.zone_name} ➔ ${placeName}`;
                        const subLocations = Array.isArray(place.sub_locations) ? place.sub_locations : [];
                        const questMarkers = Array.isArray(place.quest_markers) ? place.quest_markers : [];
                        const hasQuest = Boolean(place.quest_tag) || questMarkers.length > 0;
                        const rawBadges = String(place.badges || '');
                        const facilityPills = FACILITY_BADGE_LABELS.filter(fb => rawBadges.includes(fb.icon));

                        return (
                          <div
                            key={placeName || idx}
                            className={`p-3.5 rounded-lg border transition-all space-y-2.5 ${
                              isHere
                                ? 'bg-emerald-950/25 border-emerald-600/70 shadow-md'
                                : hasQuest
                                  ? 'bg-amber-950/25 border-amber-500/80 hover:border-amber-400 shadow-md ring-1 ring-amber-500/30'
                                  : 'bg-black/50 border-fantasy-border/70 hover:border-fantasy-accent/50'
                            }`}
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0 space-y-1.5 flex-1">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <span className="text-base">{place.archetype_emoji || place.emoji || '📍'}</span>
                                  <span className="font-bold text-xs text-gray-100">{placeName}</span>
                                  {hasQuest && (
                                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500 text-black font-extrabold uppercase tracking-wide shadow-sm">
                                      {place.quest_tag || '⭐ Quest Target'}
                                    </span>
                                  )}
                                  <span className={`text-[9px] px-1.5 py-0.5 rounded font-bold uppercase border ${
                                    isInstant
                                      ? 'bg-emerald-950/60 text-emerald-300 border-emerald-800/60'
                                      : 'bg-amber-950/60 text-amber-300 border-amber-800/60'
                                  }`}>
                                    {place.travel_tag || 'Travel'}
                                  </span>
                                  {place.archetype && (
                                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-black/60 text-gray-400 border border-fantasy-border/60">
                                      {place.archetype}
                                    </span>
                                  )}
                                </div>

                                {/* Facility Feature Pills (Notice Board, Merchant, Faction HQ, Home) */}
                                {facilityPills.length > 0 && (
                                  <div className="flex flex-wrap gap-1.5 pt-0.5">
                                    {facilityPills.map((fp, fIdx) => (
                                      <span
                                        key={fIdx}
                                        className={`text-[10px] px-2 py-0.5 rounded border font-semibold ${fp.color}`}
                                      >
                                        {fp.label}
                                      </span>
                                    ))}
                                  </div>
                                )}
                              </div>

                              <div className="shrink-0">
                                {isHere ? (
                                  <span className="px-3 py-1.5 rounded-lg bg-emerald-950/60 text-emerald-300 border border-emerald-700/50 text-[11px] font-bold inline-block">
                                    Current Location
                                  </span>
                                ) : (
                                  <button
                                    onClick={() => handleTravel(destValue)}
                                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all border ${
                                      hasQuest
                                        ? 'bg-amber-500/25 hover:bg-amber-500/40 text-amber-200 border-amber-400/70 shadow-sm'
                                        : 'bg-fantasy-accent/20 hover:bg-fantasy-accent/35 text-fantasy-accent border-fantasy-accent/50'
                                    }`}
                                  >
                                    <span>Travel Here</span>
                                    <ArrowRight size={13} />
                                  </button>
                                )}
                              </div>
                            </div>

                            {/* Prominent Quest Objective Callout Box on Establishment Card */}
                            {questMarkers.length > 0 && (
                              <div className="bg-amber-950/50 border border-amber-500/60 rounded-md p-2.5 space-y-1">
                                <div className="text-[10px] font-bold uppercase tracking-wider text-amber-300 flex items-center gap-1">
                                  <Sparkles size={11} className="text-amber-400 shrink-0" />
                                  <span>Active Quest Objective Here</span>
                                </div>
                                {questMarkers.map((qm, qmIdx) => (
                                  <div key={qmIdx} className="text-xs text-amber-100 font-medium leading-snug">
                                    {qm}
                                  </div>
                                ))}
                              </div>
                            )}

                            {/* 3rd-Tier Sub-Locations Chips */}
                            {subLocations.length > 0 && (
                              <div className="pt-2 border-t border-fantasy-border/40 flex flex-wrap items-center gap-1.5">
                                <span className="text-[10px] font-mono uppercase text-gray-500 mr-1">Sub-Areas:</span>
                                {subLocations.map((sub, sIdx) => {
                                  const subName = typeof sub === 'string' ? sub : (sub.name || sub.label);
                                  if (!subName) return null;
                                  return (
                                    <button
                                      key={`${subName}-${sIdx}`}
                                      type="button"
                                      onClick={() => handleTravel(`${activeZoneObj.zone_name} ➔ ${placeName} ➔ ${subName}`)}
                                      className="px-2 py-0.5 rounded-full bg-black/60 hover:bg-fantasy-accent/25 text-gray-300 hover:text-fantasy-accent border border-fantasy-border/70 hover:border-fantasy-accent/50 text-[10px] font-medium transition-colors flex items-center gap-1"
                                    >
                                      <span>↳ {subName}</span>
                                    </button>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        );
                      })
                    )}
                  </div>
                </>
              )}
            </div>

          </div>
        )}

      </div>
    </div>
  );
};

export default WorldMapModal;
