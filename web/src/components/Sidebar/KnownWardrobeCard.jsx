import React from 'react';

/**
 * Fog-of-War masked Known Wardrobe dossier card rendered inside ContactsPanel's Persona subtab.
 * Displays co-located "Currently Wearing" pill strictly when present in scene alongside NPC,
 * plus discovered Main/Duty, Casual, Sleepwear, and contextual activity kits.
 */
export default function KnownWardrobeCard({ npc, showDebug = false, t }) {
  const kw =
    showDebug && npc?.debug_profile?.known_wardrobe
      ? npc.debug_profile.known_wardrobe
      : npc?.known_wardrobe;

  if (!kw || typeof kw !== 'object') {
    return null;
  }

  const presets = kw.presets || {};
  const activityKits = kw.activity_kits || {};
  const currentlyWearing = kw.is_colocated ? kw.currently_wearing : null;

  const coreRows = [
    { key: 'duty', label: t('social.wardrobe_duty', 'Main / Duty'), entry: presets.duty },
    { key: 'casual', label: t('social.wardrobe_casual', 'Casual'), entry: presets.casual },
    { key: 'sleepwear', label: t('social.wardrobe_sleepwear', 'Sleepwear'), entry: presets.sleepwear },
  ];

  const anyKnown =
    Boolean(currentlyWearing?.summary) ||
    coreRows.some((r) => Boolean(r.entry?.known && r.entry?.summary && r.entry.summary !== '???'));

  const kitList = Object.entries(activityKits).filter(
    ([, v]) => v && (v.known || showDebug) && v.summary
  );

  return (
    <div className="bg-black/40 p-2.5 rounded-lg border border-fantasy-border/40 text-xs space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-bold text-gray-400 uppercase tracking-wider">
          👔 {t('social.wardrobe_header', 'Known Wardrobe')}
        </span>
        {currentlyWearing?.summary && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-950/70 text-emerald-300 border border-emerald-700/50 font-medium truncate max-w-[65%]">
            {t('social.currently_wearing', 'Currently Wearing')}: {currentlyWearing.summary}
          </span>
        )}
      </div>

      <div className="space-y-1 text-gray-300">
        {coreRows.map(({ key, label, entry }) => {
          const isKnown = Boolean((entry?.known || showDebug) && entry?.summary && entry.summary !== '???');
          return (
            <div key={key} className="flex items-start justify-between gap-2 leading-snug">
              <span className="text-gray-400 font-medium shrink-0">{label}:</span>
              <span className="text-right">
                {isKnown ? (
                  <span className="text-gray-200">{entry.summary}</span>
                ) : (
                  <span className="text-gray-500 italic border-b border-dashed border-gray-600">???</span>
                )}
                {entry?.has_gift && (
                  <span className="ml-1.5 text-[10px] px-1 py-0.2 rounded bg-amber-950/70 text-amber-300 border border-amber-700/50">
                    🎁 {t('social.wardrobe_gifted', 'Gifted')}
                  </span>
                )}
              </span>
            </div>
          );
        })}
      </div>

      {kitList.length > 0 && (
        <div className="pt-1 border-t border-fantasy-border/20 flex flex-wrap gap-1">
          {kitList.map(([kitKey, kitVal]) => (
            <span
              key={kitKey}
              className="text-[10px] px-1.5 py-0.5 rounded bg-slate-900/80 text-slate-300 border border-slate-700/50"
              title={kitVal.summary}
            >
              {kitKey.replace('activity:', '').replace('_', ' ')}: {kitVal.summary}
            </span>
          ))}
        </div>
      )}

      {!anyKnown && !showDebug && (
        <div className="text-[11px] text-gray-500 italic">
          {t('social.wardrobe_unlock_hint', 'Meet them at work, off-duty, or at home to witness their outfits.')}
        </div>
      )}
    </div>
  );
}
