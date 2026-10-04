import React from 'react';

export const formatNarrative = (text) => {
  if (!text) return null;
  return text.split('\n').map((para, idx) => (
    para.trim() ? <p key={idx} className="mb-3.5 last:mb-0 leading-relaxed">{para}</p> : null
  ));
};

/**
 * Computes visual styling for skill check outcomes:
 * - Critical Success: bright green
 * - Success: dark green
 * - Failure: dark red
 * - Critical Failure: bright red
 * - Free Action (NONE/FREE): neutral warm stone
 */
export const getOutcomeTierTheme = (rawTier, rawTierLabel, rawStat) => {
  const stat = String(rawStat || '').toUpperCase();
  const combined = `${rawTier || ''} ${rawTierLabel || ''}`.toLowerCase();

  const isFree = (stat === 'NONE' || stat === 'FREE') && !combined.includes('fail');
  const isCritSuccess = combined.includes('crit') && (combined.includes('success') || combined.includes('pass'));
  const isCritFail = combined.includes('crit') && combined.includes('fail');
  const isFail = !isCritFail && combined.includes('fail');
  const isSuccess = !isCritSuccess && !isFail && (combined.includes('success') || combined.includes('pass') || !combined.trim());

  if (isFree) {
    return {
      key: 'free',
      badgeClass: 'bg-neutral-900/80 text-stone-300 border-stone-600/50',
      textClass: 'text-stone-300',
      accentBorderClass: 'border-stone-600/50',
      icon: '✨',
      defaultLabel: 'FREE ACTION',
    };
  }
  if (isCritSuccess) {
    return {
      key: 'crit_success',
      badgeClass: 'bg-green-950/80 text-green-300 border-green-400/60 shadow-[0_0_8px_rgba(74,222,128,0.18)]',
      textClass: 'text-[#4ade80]', // Bright green for Critical Success
      accentBorderClass: 'border-green-400/60',
      icon: '🎲',
      defaultLabel: 'CRITICAL SUCCESS',
    };
  }
  if (isCritFail) {
    return {
      key: 'crit_fail',
      badgeClass: 'bg-red-950/90 text-red-300 border-red-500/70 shadow-[0_0_8px_rgba(248,113,113,0.2)]',
      textClass: 'text-[#f87171]', // Bright red for Critical Failure
      accentBorderClass: 'border-red-500/70',
      icon: '🎲',
      defaultLabel: 'CRITICAL FAILURE',
    };
  }
  if (isFail) {
    return {
      key: 'fail',
      badgeClass: 'bg-[#2a1215]/90 text-[#d88282] border-red-900/70',
      textClass: 'text-[#c86464]', // Dark red for Failure
      accentBorderClass: 'border-red-900/70',
      icon: '🎲',
      defaultLabel: 'FAILURE',
    };
  }
  // Standard Success -> Dark green
  return {
    key: 'success',
    badgeClass: 'bg-[#0f291e]/90 text-[#68c496] border-emerald-800/70',
    textClass: 'text-[#3ca370]', // Dark green for Success
    accentBorderClass: 'border-emerald-700/60',
    icon: '🎲',
    defaultLabel: isSuccess ? 'SUCCESS' : 'RESOLVED',
  };
};

const HistoryCard = ({ entry, prevSceneTitle = '', sceneImageUrl = null }) => {
  if (!entry) return null;

  if (typeof entry === 'string') {
    return (
      <div className="mb-6 text-gray-100 font-serif md:text-lg tracking-wide">
        {formatNarrative(entry)}
      </div>
    );
  }

  // Opening or pure scene block
  if (entry.type === 'scene') {
    const sceneText = entry.next_narrative || entry.narrative || '';
    const title = entry.scene_title || '';
    const showTitle = Boolean(title && title !== prevSceneTitle);
    return (
      <div className="mb-7">
        {showTitle && (
          <h2 className="font-rpg text-2xl text-fantasy-accent mb-4 border-b border-fantasy-accent/30 pb-2">
            {title}
          </h2>
        )}
        {sceneImageUrl && (
          <div className="mb-5 rounded-lg overflow-hidden border border-fantasy-border/80 shadow-lg bg-black/40">
            <img
              src={sceneImageUrl}
              alt={title || 'Scene Illustration'}
              className="w-full max-h-96 object-cover"
            />
          </div>
        )}
        <div className="text-gray-100 font-serif md:text-lg tracking-wide">
          {formatNarrative(sceneText)}
        </div>
      </div>
    );
  }

  let outcome = entry.outcome;
  if (typeof outcome === 'string') {
    outcome = { narrative: outcome };
  }

  const rawCheck = entry?.check || outcome?.check || outcome?.skill_check || {};
  const checkTier = entry?.tier || entry?.check_tier || outcome?.check_tier || rawCheck.check_tier || rawCheck.tier || null;
  const tierLabel = entry?.tier_label || outcome?.tier_label || rawCheck.tier_label || checkTier || null;
  const checkChance = entry?.chance ?? outcome?.chance ?? rawCheck.chance ?? rawCheck.success_pct ?? null;
  const checkStat = entry?.stat || outcome?.stat || rawCheck.stat || null;
  const actionLabel = entry?.label || entry?.summary || null;

  const outcomeNarrative = (
    entry?.outcome_narrative ||
    outcome?.outcome_narrative ||
    (!entry?.next_narrative ? (outcome?.narrative || entry?.narrative || '') : '')
  ).trim();

  const nextNarrative = (
    entry?.next_narrative ||
    outcome?.next_narrative ||
    ''
  ).trim();

  const hasDistinctNextNarrative = Boolean(nextNarrative && nextNarrative !== outcomeNarrative);
  const entrySceneTitle = (entry?.scene_title || outcome?.scene_title || '').trim();
  const showSceneTitle = Boolean(entrySceneTitle && entrySceneTitle !== prevSceneTitle);

  const theme = getOutcomeTierTheme(checkTier, tierLabel, checkStat);
  const displayStatPrefix = checkStat && checkStat !== 'NONE' && checkStat !== 'FREE' ? `${checkStat} • ` : '';
  const displayTierText = (tierLabel || theme.defaultLabel).toUpperCase();
  const chanceSuffix =
    checkChance !== null && checkChance !== undefined && checkStat !== 'NONE' && checkStat !== 'FREE'
      ? ` (${Math.round(Number(checkChance))}%)`
      : '';

  return (
    <div className="mb-7">
      {/* Subtle visual clue separating prior scene from the action's result narration */}
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2.5 pt-2 border-t border-white/5">
        <div className="flex items-center gap-2 min-w-0 text-xs text-gray-400/90 italic">
          <span className="text-fantasy-accent/70 not-italic font-mono text-[11px]">▸</span>
          <span className="truncate">{actionLabel || 'Action Resolved'}</span>
        </div>

        <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full border text-[10px] font-mono font-bold uppercase tracking-wider shrink-0 ${theme.badgeClass}`}>
          <span>{theme.icon}</span>
          <span>{displayStatPrefix}{displayTierText}{chanceSuffix}</span>
        </span>
      </div>

      {/* Result Narration (colored by check outcome tier, seamless typography) */}
      {outcomeNarrative && (
        <div className={`border-l-2 ${theme.accentBorderClass} pl-4 py-0.5 font-serif md:text-lg tracking-wide ${theme.textClass}`}>
          {formatNarrative(outcomeNarrative)}
        </div>
      )}

      {/* Main Scene Narration (seamless continuation into the new scene state) */}
      {hasDistinctNextNarrative && (
        <div className="mt-5">
          {showSceneTitle && (
            <h2 className="font-rpg text-xl md:text-2xl text-fantasy-accent mb-3.5 border-b border-fantasy-accent/25 pb-1.5">
              {entrySceneTitle}
            </h2>
          )}
          {sceneImageUrl && (
            <div className="mb-5 rounded-lg overflow-hidden border border-fantasy-border/80 shadow-lg bg-black/40">
              <img
                src={sceneImageUrl}
                alt={entrySceneTitle || 'Scene Illustration'}
                className="w-full max-h-96 object-cover"
              />
            </div>
          )}
          <div className="text-gray-100 font-serif md:text-lg tracking-wide">
            {formatNarrative(nextNarrative)}
          </div>
        </div>
      )}
    </div>
  );
};

export default HistoryCard;
