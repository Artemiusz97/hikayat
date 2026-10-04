import React, { useEffect, useRef } from 'react';
import HistoryCard, { formatNarrative, getOutcomeTierTheme } from './HistoryCard';
import { Feather, Sparkles, Swords, Skull, Heart } from 'lucide-react';

const StoryFeed = ({
  history,
  currentScene,
  isStreaming,
  streamingNarrative,
  streamingState,
  selectedCombatTarget,
  onSelectCombatTarget
}) => {
  const scrollContainerRef = useRef(null);
  const feedEndRef = useRef(null);

  // Auto-scroll when new history arrives or when streaming text updates
  useEffect(() => {
    if (isStreaming && scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
    } else {
      feedEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [history?.length, currentScene?.narrative, streamingNarrative, streamingState?.outcomeText, streamingState?.nextText, isStreaming]);

  const rawMonsters = currentScene?.nearby_enemies || currentScene?.monsters || [];
  const activeMonsters = Array.isArray(rawMonsters)
    ? rawMonsters.filter((m) => m && m.name)
    : [];
  const conversationLock = currentScene?.conversation_lock;

  const histList = Array.isArray(history) ? history : [];
  const lastHist = histList.length > 0 ? histList[histList.length - 1] : null;
  const lastHistNextNar = (
    lastHist?.next_narrative ||
    (lastHist?.type === 'scene' ? lastHist?.narrative : '') ||
    ''
  ).trim();
  const currentNar = (currentScene?.narrative || '').trim();
  const isCurrentSceneAlreadyInHistory = Boolean(
    lastHistNextNar && currentNar && lastHistNextNar === currentNar
  );

  const streamAction = streamingState?.action || null;
  const streamOutcomeText = streamingState?.outcomeText || '';
  const streamNextText = streamingState?.nextText || '';
  const streamTheme = getOutcomeTierTheme(
    streamAction?.tier || streamAction?.check?.tier,
    streamAction?.check?.tier_label || streamAction?.tier_label,
    streamAction?.stat
  );
  const streamStat = streamAction?.stat;
  const streamStatPrefix = streamStat && streamStat !== 'NONE' && streamStat !== 'FREE' ? `${streamStat} • ` : '';
  const streamTierLabel = (
    streamAction?.check?.tier_label ||
    streamAction?.tier_label ||
    streamTheme.defaultLabel
  ).toUpperCase();
  const streamChance = streamAction?.check?.chance ?? streamAction?.rate ?? null;
  const streamChanceSuffix =
    streamChance !== null && streamChance !== undefined && streamStat !== 'NONE' && streamStat !== 'FREE'
      ? ` (${Math.round(Number(streamChance))}%)`
      : '';

  return (
    <div
      ref={scrollContainerRef}
      className="h-full w-full overflow-y-auto custom-scrollbar px-4 md:px-8 pt-5 pb-4 scroll-smooth relative z-10"
    >
      <div className="max-w-4xl mx-auto relative">

        {/* Render full chronological story history (Opening Scene + Turn Results + Scene Narrations) */}
        {histList.map((entry, idx) => {
          const prevTitle = idx > 0
            ? (histList[idx - 1]?.scene_title || histList[idx - 1]?.outcome?.scene_title || '')
            : '';
          const isLast = idx === histList.length - 1;
          const imgUrl = isLast && isCurrentSceneAlreadyInHistory ? currentScene?.scene_image_url : null;
          return (
            <HistoryCard
              key={idx}
              entry={entry}
              prevSceneTitle={prevTitle}
              sceneImageUrl={imgUrl}
            />
          );
        })}

        {/* Render current active scene narrative if not already part of the last history entry (e.g. Opening Scene on Turn 0) */}
        {currentScene && currentNar && !isCurrentSceneAlreadyInHistory && (
          <div className="mb-8">
            <h2 className="font-rpg text-2xl text-fantasy-accent mb-4 border-b border-fantasy-accent/30 pb-2">
              {currentScene.scene_title || 'Adventure'}
            </h2>
            {currentScene.scene_image_url && (
              <div className="mb-5 rounded-lg overflow-hidden border border-fantasy-border/80 shadow-lg bg-black/40">
                <img
                  src={currentScene.scene_image_url}
                  alt={currentScene.scene_title || 'Scene Illustration'}
                  className="w-full max-h-96 object-cover"
                />
              </div>
            )}
            <div className="text-gray-100 font-serif md:text-lg tracking-wide">
              {formatNarrative(currentNar)}
            </div>
          </div>
        )}

        {/* Seamless Real-Time Streaming Turn (shows action check badge + colored outcome_narrative + next_narrative live) */}
        {isStreaming && (
          <div className="mb-8 animate-fadeIn">
            {/* Subtle Action & Skill Check Result Divider */}
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2.5 pt-2 border-t border-white/10">
              <div className="flex items-center gap-2 min-w-0 text-xs text-gray-400 italic">
                <span className="text-fantasy-accent not-italic font-mono text-[11px]">▸</span>
                <span className="truncate">{streamAction?.label || 'Resolving Action...'}</span>
                <span className="inline-flex items-center gap-1 text-[10px] font-mono not-italic text-amber-400/90 px-1.5 py-0.5 rounded bg-amber-500/10 border border-amber-500/20">
                  <Feather size={10} className="animate-bounce" />
                  Live
                </span>
              </div>

              {streamAction && (
                <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full border text-[10px] font-mono font-bold uppercase tracking-wider shrink-0 ${streamTheme.badgeClass}`}>
                  <span>{streamTheme.icon}</span>
                  <span>{streamStatPrefix}{streamTierLabel}{streamChanceSuffix}</span>
                </span>
              )}
            </div>

            {streamOutcomeText || streamNextText || streamingNarrative ? (
              <div>
                {/* Live Result Narration (colored by outcome tier) */}
                {(streamOutcomeText || (!streamNextText && streamingNarrative)) && (
                  <div className={`border-l-2 ${streamTheme.accentBorderClass} pl-4 py-0.5 font-serif md:text-lg tracking-wide ${streamTheme.textClass}`}>
                    {formatNarrative(streamOutcomeText || streamingNarrative)}
                    {!streamNextText && (
                      <span className="inline-block w-2 h-4 ml-1 bg-fantasy-accent animate-pulse align-middle" />
                    )}
                  </div>
                )}

                {/* Live Main Scene Narration (seamless continuation) */}
                {streamNextText && (
                  <div className="mt-5 text-gray-100 font-serif md:text-lg tracking-wide">
                    {formatNarrative(streamNextText)}
                    <span className="inline-block w-2 h-4 ml-1 bg-fantasy-accent animate-pulse align-middle" />
                  </div>
                )}
              </div>
            ) : (
              <div className={`border-l-2 ${streamTheme.accentBorderClass} pl-4 py-2 flex items-center gap-2 text-sm text-gray-400 italic`}>
                <Sparkles size={14} className="text-amber-400 animate-spin" />
                <span>The Chronicler is weaving your fate...</span>
              </div>
            )}
          </div>
        )}

        {/* Live Active Combat Encounter HUD */}
        {activeMonsters.length > 0 && (
          <div className="mt-6 mb-4 bg-red-950/35 border border-red-700/60 rounded-xl p-4 shadow-lg backdrop-blur-sm">
            <div className="flex items-center justify-between border-b border-red-800/50 pb-2.5 mb-3">
              <div className="flex items-center gap-2 text-red-300 font-rpg font-bold text-sm uppercase tracking-wider">
                <Swords size={16} className="text-red-400 animate-pulse" />
                <span>Active Combat Encounter</span>
              </div>
              <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-red-900/50 text-red-200 border border-red-700/50">
                {activeMonsters.filter((m) => (m.hp ?? 1) > 0).length} / {activeMonsters.length} Hostiles Active
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              {activeMonsters.map((monster, mIdx) => {
                const maxHp = Math.max(1, Number(monster.max_hp || monster.hp || 100));
                const hp = Math.max(0, Number(monster.hp !== undefined ? monster.hp : maxHp));
                const pct = Math.min(100, Math.round((hp / maxHp) * 100));
                const isDefeated = hp <= 0;
                const isSelectedTarget = !isDefeated && selectedCombatTarget === monster.name;
                const statuses = Array.isArray(monster.status_effects) ? monster.status_effects : [];

                return (
                  <div
                    key={`${monster.name}-${mIdx}`}
                    onClick={() => {
                      if (!isDefeated && onSelectCombatTarget) {
                        onSelectCombatTarget(monster.name);
                      }
                    }}
                    className={`p-3 rounded-lg border transition-all ${
                      isDefeated
                        ? 'bg-black/40 border-neutral-800 opacity-50'
                        : isSelectedTarget
                          ? 'bg-red-950/70 border-amber-400 ring-1 ring-amber-400/60 cursor-pointer shadow-md'
                          : 'bg-black/60 border-red-800/60 hover:border-red-500 cursor-pointer'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <Skull size={13} className={isDefeated ? 'text-gray-500' : isSelectedTarget ? 'text-amber-400 shrink-0' : 'text-red-400 shrink-0'} />
                        <span className={`text-xs font-bold truncate ${isDefeated ? 'line-through text-gray-400' : 'text-gray-100'}`}>
                          {monster.name}
                        </span>
                        {isSelectedTarget && (
                          <span className="text-[9px] px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300 border border-amber-500/50 font-bold uppercase shrink-0">
                            🎯 Target
                          </span>
                        )}
                      </div>
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-red-950/80 text-red-300 border border-red-800/50 shrink-0">
                        Lv.{monster.level || 1}
                      </span>
                    </div>

                    {/* Monster HP Bar */}
                    <div className="space-y-1">
                      <div className="flex justify-between items-center text-[10px] font-mono">
                        <span className="text-red-300 flex items-center gap-1">
                          <Heart size={10} className="text-red-400" /> HP
                        </span>
                        <span className="text-gray-300 font-semibold">
                          {hp} / {maxHp} ({pct}%)
                        </span>
                      </div>
                      <div className="h-2 w-full bg-black/80 rounded-full overflow-hidden border border-red-900/50">
                        <div
                          className={`h-full transition-all duration-500 ${
                            pct > 50 ? 'bg-red-500' : pct > 25 ? 'bg-amber-500' : 'bg-rose-600'
                          }`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>

                    {/* Monster Status Effects */}
                    {statuses.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {statuses.map((st, sIdx) => {
                          const label = typeof st === 'string' ? st : (st.name || 'Condition');
                          return (
                            <span
                              key={sIdx}
                              className="text-[9px] px-1.5 py-0.5 rounded bg-amber-950/70 text-amber-300 border border-amber-700/50 font-medium"
                            >
                              {label}
                            </span>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Conversation Lock Bar */}
        {conversationLock && (
          <div className="mt-6 mb-4 bg-purple-950/40 border border-purple-700/60 rounded-xl p-4 shadow-lg backdrop-blur-sm">
            <div className="flex items-center justify-between border-b border-purple-800/50 pb-2.5 mb-3">
              <div className="flex items-center gap-2 text-purple-300 font-rpg font-bold text-sm uppercase tracking-wider">
                <Heart size={16} className="text-purple-400" />
                <span>Locked in Conversation: {conversationLock}</span>
              </div>
            </div>
            <div className="flex gap-2">
              <button className="flex-1 py-2 bg-purple-900/60 hover:bg-purple-800/60 border border-purple-600/50 rounded-lg text-xs font-bold text-purple-200">
                Talk
              </button>
              <button className="flex-1 py-2 bg-black/60 hover:bg-neutral-800/60 border border-neutral-600/50 rounded-lg text-xs font-bold text-gray-300">
                Profile
              </button>
              <button className="flex-1 py-2 bg-black/60 hover:bg-red-900/40 border border-red-800/50 rounded-lg text-xs font-bold text-red-300">
                Leave
              </button>
            </div>
          </div>
        )}

        <div ref={feedEndRef} className="h-4" />
      </div>
    </div>
  );
};

export default StoryFeed;
