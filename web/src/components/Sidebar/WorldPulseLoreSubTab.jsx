import React, { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Globe, Sparkles, Compass, Clock, MapPin, CheckCircle2, Radio } from 'lucide-react';
import { formatCleanLocation, cleanProseLocations } from '../../utils/locationFormat';

const computeRemainingTimeLabel = (item, currentDay, currentMinute, t) => {
  const expDay = Number(item?.expires_day ?? currentDay ?? 1);
  const expMin = Number(item?.expires_minute ?? currentMinute ?? 480);
  const nowTotal = (Number(currentDay || 1) * 1440) + Number(currentMinute ?? 480);
  const expTotal = (expDay * 1440) + expMin;
  const diffMins = Math.max(0, expTotal - nowTotal);
  const totalHours = Math.max(1, Math.ceil(diffMins / 60));
  const days = Math.floor(totalHours / 24);
  const hours = totalHours % 24;
  if (days > 0) {
    return t('codex.worldPulseTimeDaysHours', { days, hours, defaultValue: '{{days}}d {{hours}}h left' });
  }
  return t('codex.worldPulseTimeHoursOnly', { hours: totalHours, defaultValue: '{{hours}}h left' });
};

const WorldPulseLoreSubTab = ({
  worldPulse,
  filteredLore = [],
  searchQuery = '',
  busyRumorId = null,
  onTrackRumor,
  isStreaming = false,
  processingTurn = false,
  session,
}) => {
  const { t } = useTranslation();
  const [pulseFilter, setPulseFilter] = useState('all'); // 'all' | 'events' | 'rumors' | 'lore'

  const effectivePulse = worldPulse || session?.world_pulse || {};
  const currentDay = Number(effectivePulse.current_day ?? session?.current_day ?? 1);
  const currentMinute = Number(effectivePulse.current_minute ?? session?.current_minute ?? 480);
  const canTrackRumor = effectivePulse.can_track_rumor !== false;
  const canTrackMinor = effectivePulse.can_track_minor_bounty !== false;
  const trackedCount = Number(effectivePulse.tracked_rumor_count || 0);
  const maxTracked = Number(effectivePulse.max_tracked_rumors || 2);

  const q = String(searchQuery || '').trim().toLowerCase();

  const macroEvents = useMemo(() => {
    const raw = Array.isArray(effectivePulse.active_macro_events) ? effectivePulse.active_macro_events : [];
    return raw.filter((ev) => {
      if (!q) return true;
      return (
        String(ev.title || '').toLowerCase().includes(q) ||
        String(ev.description || '').toLowerCase().includes(q) ||
        String(ev.location_name || '').toLowerCase().includes(q)
      );
    });
  }, [effectivePulse.active_macro_events, q]);

  const minorEvents = useMemo(() => {
    const raw = Array.isArray(effectivePulse.active_minor_events) ? effectivePulse.active_minor_events : [];
    return raw.filter((ev) => {
      if (!q) return true;
      return (
        String(ev.title || '').toLowerCase().includes(q) ||
        String(ev.description || '').toLowerCase().includes(q) ||
        String(ev.location_name || '').toLowerCase().includes(q)
      );
    });
  }, [effectivePulse.active_minor_events, q]);

  const discoveredRumors = useMemo(() => {
    const raw = Array.isArray(effectivePulse.active_rumors) ? effectivePulse.active_rumors : [];
    return raw
      .filter((rm) => Boolean(rm?.is_discovered))
      .filter((rm) => {
        if (!q) return true;
        return (
          String(rm.title || '').toLowerCase().includes(q) ||
          String(rm.description || '').toLowerCase().includes(q) ||
          String(rm.location_name || '').toLowerCase().includes(q)
        );
      });
  }, [effectivePulse.active_rumors, q]);

  const untrackedActiveRumorsCount = useMemo(
    () => discoveredRumors.filter((r) => r.status === 'active' && !r.linked_quest_id).length,
    [discoveredRumors]
  );

  const showEvents = pulseFilter === 'all' || pulseFilter === 'events';
  const showRumors = pulseFilter === 'all' || pulseFilter === 'rumors';
  const showLore = pulseFilter === 'all' || pulseFilter === 'lore';

  const hasVisibleContent =
    (showEvents && (macroEvents.length > 0 || minorEvents.length > 0)) ||
    (showRumors && discoveredRumors.length > 0) ||
    (showLore && filteredLore.length > 0);

  const filterPills = [
    { id: 'all', label: t('codex.worldPulseFilterAll', 'All') },
    { id: 'events', label: `${t('codex.worldPulseFilterEvents', 'Events')} (${macroEvents.length + minorEvents.length})` },
    { id: 'rumors', label: `${t('codex.worldPulseFilterRumors', 'Rumors')} (${discoveredRumors.length})` },
    { id: 'lore', label: `${t('codex.worldPulseFilterLore', 'Lore')} (${filteredLore.length})` },
  ];

  return (
    <div className="space-y-3">
      {/* Non-intrusive World Pulse status banner suppressed during active turn streaming */}
      {!isStreaming && !processingTurn && untrackedActiveRumorsCount > 0 && canTrackRumor && (
        <div
          role="status"
          aria-live="polite"
          className="flex items-center justify-between gap-2 px-2.5 py-2 rounded-lg bg-amber-950/35 border border-amber-700/40 text-amber-200 text-[11px]"
        >
          <div className="flex items-center gap-1.5">
            <Radio size={13} className="text-amber-400 shrink-0" />
            <span>
              {t('codex.worldPulseBannerAlert', {
                count: untrackedActiveRumorsCount,
                defaultValue: '{{count}} whispered lead(s) available to investigate.',
              })}
            </span>
          </div>
          <span className="font-mono text-[10px] text-amber-300/90 shrink-0">
            {trackedCount}/{maxTracked}
          </span>
        </div>
      )}

      {/* Filter Pills */}
      <div className="flex flex-wrap items-center gap-1.5">
        {filterPills.map((pill) => {
          const isActive = pulseFilter === pill.id;
          return (
            <button
              key={pill.id}
              type="button"
              aria-pressed={isActive}
              onClick={() => setPulseFilter(pill.id)}
              className={`px-2.5 py-1 rounded-md text-[11px] font-semibold border transition-colors cursor-pointer ${
                isActive
                  ? 'bg-fantasy-accent/20 text-fantasy-accent border-fantasy-accent/60'
                  : 'bg-black/40 text-gray-400 border-fantasy-border/60 hover:text-gray-200 hover:border-fantasy-border'
              }`}
            >
              {pill.label}
            </button>
          );
        })}
      </div>

      {!hasVisibleContent ? (
        <div className="text-center py-8 text-gray-500 border border-dashed border-fantasy-border/50 rounded-md">
          <Globe size={24} className="mx-auto mb-1.5 opacity-40" />
          <p className="text-xs">
            {pulseFilter === 'lore'
              ? t('codex.no_lore', 'No world details documented yet.')
              : t('codex.worldPulseEmptyFiltered', 'No active events, rumors, or lore match this filter.')}
          </p>
        </div>
      ) : (
        <div className="space-y-2.5">
          {/* 1. Macro World Events */}
          {showEvents &&
            macroEvents.map((ev) => {
              const isAftermath = ev.status === 'resolved_aftermath';
              const timeLabel = computeRemainingTimeLabel(ev, currentDay, currentMinute, t);
              return (
                <div
                  key={ev.event_key || ev.id}
                  className="bg-indigo-950/25 border border-indigo-700/40 rounded-lg p-3 space-y-1.5"
                >
                  <div className="flex justify-between items-start gap-2">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <Sparkles size={13} className="text-indigo-300 shrink-0" />
                      <h5 className="font-semibold text-xs text-gray-100">{ev.title}</h5>
                    </div>
                    <span
                      className={`text-[9px] px-1.5 py-0.5 rounded uppercase font-bold border shrink-0 ${
                        isAftermath
                          ? 'bg-emerald-950/50 text-emerald-300 border-emerald-700/50'
                          : 'bg-indigo-950/60 text-indigo-200 border-indigo-600/50'
                      }`}
                    >
                      {isAftermath
                        ? t('codex.worldPulseAftermathBadge', 'Aftermath Buzz')
                        : t('codex.worldPulseMacroBadge', 'World Event')}
                    </span>
                  </div>

                  {ev.description && (
                    <p className="text-[11px] text-gray-300 leading-snug">
                      {cleanProseLocations(ev.description)}
                    </p>
                  )}

                  <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-[10px] text-gray-400">
                    <span className="flex items-center gap-1 font-mono text-indigo-300/90">
                      <Clock size={10} />
                      <span>{timeLabel}</span>
                    </span>
                    {ev.location_name && (
                      <span className="flex items-center gap-1 text-gray-400">
                        <MapPin size={10} className="text-indigo-300" />
                        <span>{formatCleanLocation(ev.location_name)}</span>
                      </span>
                    )}
                  </div>
                </div>
              );
            })}

          {/* 1b. Minor Mundane Incidents & Local Chatter */}
          {showEvents &&
            minorEvents.map((ev) => {
              const isAftermath = ev.status === 'resolved_aftermath';
              const isTracked = Boolean(ev.linked_quest_id);
              const isBusy = busyRumorId === ev.event_key;
              const canSpawnBounty = Boolean(ev.metadata?.can_spawn_bounty);
              const timeLabel = computeRemainingTimeLabel(ev, currentDay, currentMinute, t);
              const trackDisabled = Boolean(busyRumorId) || isTracked || isAftermath || !canTrackMinor;

              return (
                <div
                  key={ev.event_key || ev.id}
                  className="bg-teal-950/20 border border-teal-700/40 rounded-lg p-3 space-y-1.5"
                >
                  <div className="flex justify-between items-start gap-2">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <Radio size={13} className="text-teal-300 shrink-0" />
                      <h5 className="font-semibold text-xs text-gray-100">{ev.title}</h5>
                    </div>
                    <span
                      className={`text-[9px] px-1.5 py-0.5 rounded uppercase font-bold border shrink-0 ${
                        isAftermath
                          ? 'bg-emerald-950/50 text-emerald-300 border-emerald-700/50'
                          : 'bg-teal-950/60 text-teal-200 border-teal-600/50'
                      }`}
                    >
                      {isAftermath
                        ? t('codex.worldPulseAftermathBadge', 'Aftermath Buzz')
                        : t('codex.worldPulseMinorBadge', 'Local Chatter')}
                    </span>
                  </div>

                  {ev.description && (
                    <p className="text-[11px] text-gray-300 leading-snug">
                      {cleanProseLocations(ev.description)}
                    </p>
                  )}

                  <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-[10px] text-gray-400">
                    <div className="flex items-center gap-2">
                      <span className="flex items-center gap-1 font-mono text-teal-300/90">
                        <Clock size={10} />
                        <span>{timeLabel}</span>
                      </span>
                      {ev.location_name && (
                        <span className="flex items-center gap-1">
                          <MapPin size={10} className="text-teal-300" />
                          <span>{formatCleanLocation(ev.location_name)}</span>
                        </span>
                      )}
                    </div>

                    {canSpawnBounty && !isAftermath && (
                      isTracked ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-950/50 text-emerald-300 border border-emerald-700/50 font-semibold">
                          <CheckCircle2 size={11} />
                          <span>{t('codex.worldPulseTrackedBadge', 'Investigating')}</span>
                        </span>
                      ) : (
                        <button
                          type="button"
                          disabled={trackDisabled}
                          onClick={() => onTrackRumor && onTrackRumor(ev.event_key)}
                          className={`px-2.5 py-1 rounded font-semibold border transition-colors ${
                            trackDisabled
                              ? 'bg-black/40 text-gray-500 border-neutral-800 cursor-not-allowed'
                              : 'bg-teal-900/40 hover:bg-teal-800/50 text-teal-200 border-teal-600/60 cursor-pointer'
                          }`}
                        >
                          {isBusy ? t('codex.worldPulseTrackingBusy', 'Tracking...') : t('codex.worldPulseLookIntoIt', 'Look Into It')}
                          <span className="sr-only"> {ev.title}</span>
                        </button>
                      )
                    )}
                  </div>
                </div>
              );
            })}

          {/* 2. Discovered Rumors */}
          {showRumors &&
            discoveredRumors.map((rm) => {
              const isAftermath = rm.status === 'resolved_aftermath';
              const isTracked = Boolean(rm.linked_quest_id);
              const isBusy = busyRumorId === rm.event_key;
              const timeLabel = computeRemainingTimeLabel(rm, currentDay, currentMinute, t);
              const trackDisabled = Boolean(busyRumorId) || isTracked || isAftermath || !canTrackRumor;

              return (
                <div
                  key={rm.event_key || rm.id}
                  className="bg-amber-950/20 border border-amber-700/40 rounded-lg p-3 space-y-2"
                >
                  <div className="flex justify-between items-start gap-2">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <Compass size={13} className="text-amber-300 shrink-0" />
                      <h5 className="font-semibold text-xs text-gray-100">{rm.title}</h5>
                    </div>
                    <span
                      className={`text-[9px] px-1.5 py-0.5 rounded uppercase font-bold border shrink-0 ${
                        isAftermath
                          ? 'bg-emerald-950/50 text-emerald-300 border-emerald-700/50'
                          : 'bg-amber-950/60 text-amber-200 border-amber-700/50'
                      }`}
                    >
                      {isAftermath
                        ? t('codex.worldPulseAftermathBadge', 'Aftermath Buzz')
                        : t('codex.worldPulseRumorBadge', 'Rumor')}
                    </span>
                  </div>

                  {rm.description && (
                    <p className="text-[11px] text-gray-300 leading-snug">
                      {cleanProseLocations(rm.description)}
                    </p>
                  )}

                  <div className="flex flex-wrap items-center justify-between gap-2 pt-1.5 border-t border-amber-800/25 text-[10px]">
                    <div className="flex flex-wrap items-center gap-2 text-gray-400">
                      <span className="flex items-center gap-1 font-mono text-amber-300/90">
                        <Clock size={10} />
                        <span>{timeLabel}</span>
                      </span>
                      {rm.location_name && (
                        <span className="flex items-center gap-1">
                          <MapPin size={10} className="text-amber-300" />
                          <span>{formatCleanLocation(rm.location_name)}</span>
                        </span>
                      )}
                    </div>

                    {!isAftermath && (
                      isTracked ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-950/50 text-emerald-300 border border-emerald-700/50 font-semibold">
                          <CheckCircle2 size={11} />
                          <span>{t('codex.worldPulseTrackedBadge', 'Investigating')}</span>
                        </span>
                      ) : (
                        <button
                          type="button"
                          disabled={trackDisabled}
                          onClick={() => onTrackRumor && onTrackRumor(rm.event_key)}
                          className={`px-2.5 py-1 rounded font-semibold border transition-colors ${
                            trackDisabled
                              ? 'bg-black/40 text-gray-500 border-neutral-800 cursor-not-allowed'
                              : 'bg-amber-900/40 hover:bg-amber-800/50 text-amber-200 border-amber-600/60 cursor-pointer'
                          }`}
                        >
                          {isBusy
                            ? t('codex.worldPulseTrackingBusy', 'Tracking...')
                            : !canTrackRumor
                              ? `${t('codex.worldPulseCapReached', 'Leads Full')} (${trackedCount}/${maxTracked})`
                              : t('codex.worldPulseTrackLead', 'Track Lead')}
                          <span className="sr-only"> {rm.title}</span>
                        </button>
                      )
                    )}
                  </div>
                </div>
              );
            })}

          {/* 3. Documented World Lore */}
          {showLore &&
            filteredLore.map((ent, idx) => (
              <div
                key={ent.id || idx}
                className="bg-black/50 border border-fantasy-border/60 rounded-lg p-3 space-y-1.5"
              >
                <div className="flex justify-between items-start gap-1">
                  <h5 className="font-semibold text-xs text-gray-200">{ent.name}</h5>
                  <span className="text-[9px] px-1.5 py-0.2 bg-black/60 text-gray-400 rounded uppercase font-bold border border-fantasy-border">
                    {ent.entity_type || 'Lore'}
                  </span>
                </div>

                {ent.description && (
                  <p className="text-[11px] text-gray-400 leading-snug">
                    {cleanProseLocations(ent.description)}
                  </p>
                )}

                {ent.location && (
                  <span className="text-[10px] text-gray-500 flex items-center gap-1">
                    <MapPin size={10} />
                    <span>{formatCleanLocation(ent.location)}</span>
                  </span>
                )}
              </div>
            ))}
        </div>
      )}
    </div>
  );
};

export default WorldPulseLoreSubTab;
