import React, { useState } from 'react';
import { Clock, Lock, MapPin } from 'lucide-react';

const BLOCK_ORDER = [
  { key: 'morning', fallback: 'Morning', icon: '🌅' },
  { key: 'lunch', fallback: 'Lunch', icon: '☀️' },
  { key: 'afternoon', fallback: 'Afternoon', icon: '🌤️' },
  { key: 'evening', fallback: 'Evening', icon: '🌆' },
  { key: 'night', fallback: 'Night', icon: '🌙' },
];

const RESIDENTIAL_FOG_STRINGS = new Set([
  'Residential Area (Unknown)',
  'Dzielnica Mieszkalna (Nieznana)',
  'Kawasan Kediaman (Tidak Diketahui)',
  '住宅区（未知）',
  'Wohnviertel (Unbekannt)',
]);

const isMaskedSlotValue = (val, maskedPlaceholder) => {
  const s = String(val ?? '').trim();
  if (!s) return true;
  if (s === maskedPlaceholder || s === '???') return true;
  return /^\?+$/.test(s);
};

const isResidentialFogValue = (val) => {
  const s = String(val ?? '').trim();
  if (!s) return false;
  if (RESIDENTIAL_FOG_STRINGS.has(s)) return true;
  const low = s.toLowerCase();
  return low.includes('residential area (unknown)') || low.includes('unknown address');
};

const KnownRoutineCard = ({ npc, t }) => {
  const [dayTab, setDayTab] = useState('weekday');
  const routine = npc?.known_routine;
  const legacyText = npc?.known_schedule || npc?.schedule_summary;

  if (!routine && !legacyText) {
    return null;
  }

  if (!routine) {
    const legacyStr = String(legacyText || '');
    const isLegacyMasked = npc?.schedule_revealed === false || legacyStr.includes('???');
    return (
      <div className="bg-black/40 p-2.5 rounded-lg border border-fantasy-border/40 text-xs text-gray-300 leading-relaxed">
        <span className="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center gap-1.5 mb-1">
          <Clock size={12} className="text-fantasy-accent" />
          {t('social.schedule_header', 'Schedule & Routine')}
        </span>
        <span className={isLegacyMasked ? 'font-mono text-gray-500 italic' : 'text-gray-200'}>
          {legacyText}
        </span>
      </div>
    );
  }

  const maskedPlaceholder = t('social.masked_slot', '???');
  const slotsMap = (dayTab === 'weekend' ? routine.weekend : routine.weekday) || {};
  const fullUnlocked = Boolean(routine.full_schedule_unlocked);
  const resUnlocked = Boolean(routine.residence_unlocked);

  return (
    <div className="bg-black/40 p-2.5 rounded-lg border border-fantasy-border/40 text-xs text-gray-300 space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
          <Clock size={12} className="text-fantasy-accent" />
          {t('social.schedule_header', 'Schedule & Routine')}
        </span>
        <div
          role="tablist"
          aria-label={t('social.schedule_header', 'Schedule & Routine')}
          className="inline-flex rounded border border-fantasy-border/60 bg-black/60 p-0.5 text-[10px] font-semibold"
        >
          <button
            type="button"
            role="tab"
            aria-selected={dayTab === 'weekday'}
            onClick={(e) => {
              e.stopPropagation();
              setDayTab('weekday');
            }}
            className={`px-2 py-0.5 rounded transition-colors cursor-pointer ${
              dayTab === 'weekday'
                ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40'
                : 'text-gray-400 hover:text-gray-200 border border-transparent'
            }`}
          >
            {t('social.routine_weekday', 'Weekday')}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={dayTab === 'weekend'}
            onClick={(e) => {
              e.stopPropagation();
              setDayTab('weekend');
            }}
            className={`px-2 py-0.5 rounded transition-colors cursor-pointer ${
              dayTab === 'weekend'
                ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40'
                : 'text-gray-400 hover:text-gray-200 border border-transparent'
            }`}
          >
            {t('social.routine_weekend', 'Weekend')}
          </button>
        </div>
      </div>

      {routine?.current_day_override?.label && (fullUnlocked || Number(routine?.discovered_count || 0) > 0) && (
        <div className="px-2 py-1 rounded bg-amber-950/40 border border-amber-600/35 text-[11px] text-amber-200 flex items-center gap-1.5">
          <span aria-hidden="true">📌</span>
          <span className="font-semibold shrink-0">{t('social.routine_override_today', "Today's Override")}:</span>
          <span className="truncate">{routine.current_day_override.label}</span>
          {routine.current_day_override.slot_tag && (
            <span className="ml-auto px-1.5 py-0.5 rounded bg-amber-900/50 border border-amber-500/40 text-[9px] uppercase font-mono shrink-0">
              {routine.current_day_override.slot_tag}
            </span>
          )}
        </div>
      )}

      <div className="space-y-1">
        {BLOCK_ORDER.map(({ key, fallback, icon }) => {
          const rawVal = slotsMap[key] || maskedPlaceholder;
          const masked = isMaskedSlotValue(rawVal, maskedPlaceholder);
          const resFog = !masked && isResidentialFogValue(rawVal);
          const slotTag = !masked ? routine?.slot_tags?.[key] : null;
          return (
            <div
              key={key}
              className="flex items-center justify-between gap-2 px-2 py-1 rounded bg-black/35 border border-fantasy-border/25"
            >
              <span className="text-[11px] text-gray-400 font-medium shrink-0 flex items-center gap-1">
                <span aria-hidden="true">{icon}</span>
                <span>{t(`social.routine_blocks.${key}`, fallback)}</span>
                {slotTag && (
                  <span className="px-1 py-0.2 rounded bg-fantasy-900/70 border border-fantasy-border/40 text-[9px] uppercase font-mono text-amber-300/90">
                    {slotTag}
                  </span>
                )}
              </span>
              {masked ? (
                <span className="font-mono text-[11px] text-gray-500 italic text-right">
                  {maskedPlaceholder}
                </span>
              ) : resFog ? (
                <span className="inline-flex items-center gap-1 text-[11px] text-amber-300/80 italic text-right">
                  <Lock size={10} className="shrink-0" />
                  <span>{rawVal}</span>
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-[11px] text-gray-200 text-right">
                  <MapPin size={10} className="text-emerald-400/80 shrink-0" />
                  <span>{rawVal}</span>
                </span>
              )}
            </div>
          );
        })}
      </div>

      {!fullUnlocked ? (
        <p className="text-[10px] text-gray-500 italic leading-snug">
          {t(
            'social.routine_unlock_hint',
            'Full weekly routine unlocks at Affinity 40+ or by observing or asking about their schedule.'
          )}
        </p>
      ) : !resUnlocked ? (
        <p className="text-[10px] text-amber-300/70 italic leading-snug flex items-center gap-1">
          <Lock size={10} className="shrink-0" />
          <span>
            {t(
              'social.residence_fog_hint',
              'Private residence unlocks at Friend standing (100+) or when invited home.'
            )}
          </span>
        </p>
      ) : null}
    </div>
  );
};

export default KnownRoutineCard;
