import React, { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import HistoryCard, { formatNarrative, getOutcomeTierTheme } from './HistoryCard';
import SceneImageCard from './SceneImageCard';
import { Feather, Sparkles, Swords, Skull, Heart } from 'lucide-react';

const StoryFeed = ({
  history,
  currentScene,
  isStreaming,
  streamingNarrative,
  streamingState,
  selectedCombatTarget,
  onSelectCombatTarget,
  processing,
  pendingAction,
  onRerollImage = null,
  rerollingImage = false
}) => {
  const { t } = useTranslation();
  const scrollContainerRef = useRef(null);
  const feedEndRef = useRef(null);

  // Auto-scroll when new history arrives or when streaming text updates
  useEffect(() => {
    if (isStreaming && scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
    } else {
      feedEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [history?.length, currentScene?.narrative, streamingNarrative, streamingState?.outcomeText, streamingState?.nextText, isStreaming, processing]);

  const rawMonsters = currentScene?.nearby_enemies || currentScene?.monsters || [];
  const activeMonsters = Array.isArray(rawMonsters)
    ? rawMonsters.filter((m) => m && m.name)
    : [];
  const conversationLock = currentScene?.conversation_lock;

  const histList = Array.isArray(history) ? history : [];
  const lastHist = histList.length > 0 ? histList[histList.length - 1] : null;
  const lastHistNextNar = (
    lastHist?.next_narrative ||
    lastHist?.outcome_narrative ||
    (lastHist?.type === 'scene' ? lastHist?.narrative : '') ||
    ''
  ).trim();
  const currentNar = (currentScene?.narrative || '').trim();
  const isCurrentSceneAlreadyInHistory = Boolean(
    currentNar && (
      (lastHistNextNar && lastHistNextNar === currentNar) ||
      (lastHist?.outcome_narrative && String(lastHist.outcome_narrative).trim() === currentNar)
    )
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
      className="h-full w-full overflow-y-auto custom-scrollbar px-3 md:px-8 pt-3 md:pt-5 pb-3 md:pb-4 scroll-smooth relative z-10"
    >
      <div className="max-w-4xl mx-auto relative">

        {/* Render full chronological story history (Opening Scene + Turn Results + Scene Narrations) */}
        {histList.map((entry, idx) => {
          const prevTitle = idx > 0
            ? (histList[idx - 1]?.scene_title || histList[idx - 1]?.outcome?.scene_title || '')
            : '';
          const isLast = idx === histList.length - 1;
          const imgUrl = entry?.scene_image_url || (isLast && isCurrentSceneAlreadyInHistory ? currentScene?.scene_image_url : null);
          return (
            <HistoryCard
              key={idx}
              entry={entry}
              prevSceneTitle={prevTitle}
              sceneImageUrl={imgUrl}
              isLatest={isLast}
              imageGenMode={currentScene?.image_gen_enabled ?? 1}
              onRerollImage={onRerollImage}
              isRerollingImage={rerollingImage}
            />
          );
        })}

        {/* Render current active scene narrative if not already part of the last history entry (e.g. Opening Scene on Turn 0) */}
        {currentScene && currentNar && !isCurrentSceneAlreadyInHistory && (
          <div className="mb-6 md:mb-8">
            <h2 className="font-rpg text-xl md:text-2xl text-fantasy-accent mb-3 md:mb-4 border-b border-fantasy-accent/30 pb-1.5 md:pb-2">
              {currentScene.scene_title || 'Adventure'}
            </h2>
            <SceneImageCard
              imageUrl={currentScene.scene_image_url}
              title={currentScene.scene_title}
              isLatest={true}
              imageGenMode={currentScene?.image_gen_enabled ?? 1}
              onReroll={onRerollImage}
              isRerolling={rerollingImage}
            />
            <div className="text-gray-100 font-serif text-[13.5px] sm:text-sm md:text-lg tracking-wide">
              {formatNarrative(currentNar)}
            </div>
          </div>
        )}

        {/* Turn Processing Banner (when an action is submitted and backend LLM is generating) */}
        {processing && !isStreaming && (
          <div className="mb-6 md:mb-8 animate-fadeIn">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2.5 pt-2 border-t border-white/10">
              <div className="flex items-center gap-2 min-w-0 text-xs text-amber-300 font-medium">
                <span className="text-fantasy-accent not-italic font-mono text-[11px]">▸</span>
                <span className="truncate">
                  {pendingAction?.label || pendingAction?.direct_choice?.label || pendingAction?.direct_choice?.text || pendingAction?.custom_action_text || t('feed.resolving_action', 'Resolving Action...')}
                </span>
                <span className="inline-flex items-center gap-1 text-[10px] font-mono not-italic text-amber-400/90 px-1.5 py-0.5 rounded bg-amber-500/10 border border-amber-500/20">
                  <Sparkles size={10} className="animate-spin" />
                  {t('feed.resolving', 'Resolving')}
                </span>
              </div>
            </div>
            <div className="border-l-2 border-amber-500/60 pl-4 py-3 bg-amber-950/20 rounded-r-lg flex items-center gap-3 text-sm text-amber-200/90">
              <div className="w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin shrink-0" />
              <div className="flex flex-col">
                <span className="font-semibold text-xs tracking-wider uppercase text-amber-300">
                  {t('feed.chronicler_resolving', 'The Chronicler is resolving your choice...')}
                </span>
                <span className="text-[11px] text-gray-400 mt-0.5">
                  {t('feed.calculating_outcomes', 'Calculating outcomes, dice checks, and world reactions...')}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Seamless Real-Time Streaming Turn (shows action check badge + colored outcome_narrative + next_narrative live) */}
        {isStreaming && (
          <div className="mb-6 md:mb-8 animate-fadeIn">
            {/* Subtle Action & Skill Check Result Divider */}
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2.5 pt-2 border-t border-white/10">
              <div className="flex items-center gap-2 min-w-0 text-xs text-gray-400 italic">
                <span className="text-fantasy-accent not-italic font-mono text-[11px]">▸</span>
                <span className="truncate">{streamAction?.label || t('feed.resolving_action', 'Resolving Action...')}</span>
                <span className="inline-flex items-center gap-1 text-[10px] font-mono not-italic text-amber-400/90 px-1.5 py-0.5 rounded bg-amber-500/10 border border-amber-500/20">
                  <Feather size={10} className="animate-bounce" />
                  {t('feed.live', 'Live')}
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
                  <div className={`border-l-2 ${streamTheme.accentBorderClass} pl-3.5 md:pl-4 py-0.5 font-serif text-[13.5px] sm:text-sm md:text-lg tracking-wide ${streamTheme.textClass}`}>
                    {formatNarrative(streamOutcomeText || streamingNarrative)}
                    {!streamNextText && (
                      <span className="inline-block w-2 h-4 ml-1 bg-fantasy-accent animate-pulse align-middle" />
                    )}
                  </div>
                )}

                {/* Live Main Scene Narration (seamless continuation) */}
                {streamNextText && (
                  <div className="mt-4 md:mt-5 text-gray-100 font-serif text-[13.5px] sm:text-sm md:text-lg tracking-wide">
                    {formatNarrative(streamNextText)}
                    <span className="inline-block w-2 h-4 ml-1 bg-fantasy-accent animate-pulse align-middle" />
                  </div>
                )}
              </div>
            ) : (
              <div className={`border-l-2 ${streamTheme.accentBorderClass} pl-4 py-2 flex items-center gap-2 text-sm text-gray-400 italic`}>
                <Sparkles size={14} className="text-amber-400 animate-spin" />
                <span>{t('feed.chronicler_weaving', 'The Chronicler is weaving your fate...')}</span>
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
                <span>{t('feed.active_combat', 'Active Combat Encounter')}</span>
              </div>
              <div className="flex items-center gap-1.5 flex-wrap">
                {currentScene?.construct_status && (
                  <span className="text-[10.5px] font-mono px-2 py-0.5 rounded bg-cyan-950/70 text-cyan-200 border border-cyan-600/50">
                    🤖 {t('awakened.construct_active', {
                      name: currentScene.construct_status.name,
                      hp: currentScene.construct_status.hp,
                      max_hp: currentScene.construct_status.max_hp,
                      defaultValue: `Construct: ${currentScene.construct_status.name} (${currentScene.construct_status.hp}/${currentScene.construct_status.max_hp} HP)`,
                    })}
                    {currentScene.construct_status.windup_skill ? ` • ⚙️ ${currentScene.construct_status.windup_skill}` : ''}
                  </span>
                )}
                <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-red-900/50 text-red-200 border border-red-700/50">
                  {t('feed.hostiles_active', { active: activeMonsters.filter((m) => (m.hp ?? 1) > 0).length, total: activeMonsters.length, defaultValue: `${activeMonsters.filter((m) => (m.hp ?? 1) > 0).length} / ${activeMonsters.length} Hostiles Active` })}
                </span>
              </div>
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
                      <div className="flex items-center gap-1.5 min-w-0 flex-wrap">
                        <Skull size={13} className={isDefeated ? 'text-gray-500' : isSelectedTarget ? 'text-amber-400 shrink-0' : 'text-red-400 shrink-0'} />
                        <span className={`text-xs font-bold truncate ${isDefeated ? 'line-through text-gray-400' : 'text-gray-100'}`}>
                          {monster.name}
                        </span>
                        {isSelectedTarget && (
                          <span className="text-[9px] px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300 border border-amber-500/50 font-bold uppercase shrink-0">
                            🎯 {t('feed.target', 'Target')}
                          </span>
                        )}
                        {!isDefeated && monster.aggro_target_name && (
                          <span
                            className={`text-[9px] px-1.5 py-0.2 rounded font-bold shrink-0 border ${
                              monster.aggro_mode === 'taunted'
                                ? 'bg-amber-950/80 text-amber-200 border-amber-500/60'
                                : 'bg-rose-950/70 text-rose-200 border-rose-700/50'
                            }`}
                          >
                            {monster.aggro_mode === 'taunted'
                              ? `🔒 ${t('combat.taunted_label', 'Taunted')}: ${monster.aggro_target_name}`
                              : `🎯 ${t('combat.aggro_label', 'Aggro')}: ${monster.aggro_target_name}`}
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

                    {/* Qualitative Boss Charging Telegraph & Stagger Progress */}
                    {!isDefeated && monster.telegraphed_skill && typeof monster.telegraphed_skill === 'object' && (() => {
                      const skillLabel =
                        monster.telegraphed_skill.skill_name ||
                        monster.telegraphed_skill.telegraphed_label ||
                        monster.telegraphed_skill.name ||
                        'Signature Attack';
                      const staggerPct = Math.max(0, Math.min(100, Number(monster.stagger_pct || 0)));
                      const isBreaking = staggerPct >= 65;
                      const staggerLabel = isBreaking
                        ? t('combat.stagger_breaking', 'Breaking!')
                        : t('combat.stagger_label', 'Stagger');
                      return (
                        <div className="mt-2 p-2 rounded border border-amber-500/60 bg-amber-950/50 space-y-1">
                          <div className="flex items-center justify-between gap-2 text-[10px] font-mono">
                            <span className="font-bold text-amber-200 truncate">
                              ⚠️ {t('combat.charging_skill', 'CHARGING')}: {skillLabel}
                            </span>
                            <span className={`font-bold shrink-0 ${isBreaking ? 'text-rose-300 motion-safe:animate-pulse' : 'text-amber-300'}`}>
                              {staggerLabel} ({staggerPct}%)
                            </span>
                          </div>
                          <div
                            role="progressbar"
                            aria-label={`${t('combat.stagger_label', 'Stagger')} — ${skillLabel}`}
                            aria-valuemin={0}
                            aria-valuemax={100}
                            aria-valuenow={staggerPct}
                            className="h-1.5 w-full bg-black/80 rounded-full overflow-hidden border border-amber-800/60"
                          >
                            <div
                              className={`h-full transition-all duration-500 ${isBreaking ? 'bg-rose-500' : 'bg-amber-400'}`}
                              style={{ width: `${staggerPct}%` }}
                            />
                          </div>
                        </div>
                      );
                    })()}

                    {/* Anomalous Stability / Poise Bar & Weakness Pills */}
                    {Number(monster.max_stability || 0) > 0 && !isDefeated && (() => {
                      const maxStab = Math.max(1, Number(monster.max_stability));
                      const curStab = Math.max(0, Number(monster.stability ?? maxStab));
                      const stabPct = Math.min(100, Math.round((curStab / maxStab) * 100));
                      const isBreached = Boolean(monster.is_breached);
                      const breachTurns = Number(monster.breached_turns_left || 1);
                      const weakList = Array.isArray(monster.display_weaknesses)
                        ? monster.display_weaknesses
                        : (Array.isArray(monster.revealed_weaknesses) ? monster.revealed_weaknesses : (Array.isArray(monster.weaknesses) ? monster.weaknesses : []));
                      return (
                        <div className="mt-2 pt-1.5 border-t border-red-900/40 space-y-1.5">
                          {isBreached ? (
                            <div className="px-2 py-0.5 rounded bg-fuchsia-950/80 border border-fuchsia-400 text-fuchsia-200 text-[10px] font-mono font-bold uppercase tracking-wider text-center animate-pulse">
                              💥 {t('awakened.breached_badge', { turns: breachTurns, defaultValue: `ANOMALY BREACHED! [${breachTurns}T]` })}
                            </div>
                          ) : (
                            <div className="space-y-0.5">
                              <div className="flex justify-between items-center text-[9.5px] font-mono">
                                <span className="text-cyan-300">💠 {t('awakened.stability_label', 'Poise')}</span>
                                <span className="text-cyan-100 font-semibold">{curStab} / {maxStab}</span>
                              </div>
                              <div className="h-1.5 w-full bg-black/80 rounded-full overflow-hidden border border-cyan-900/60">
                                <div className="h-full bg-cyan-400 transition-all duration-500" style={{ width: `${stabPct}%` }} />
                              </div>
                            </div>
                          )}
                          {weakList.length > 0 && (
                            <div className="flex items-center gap-1 flex-wrap">
                              <span className="text-[9px] font-mono uppercase text-gray-400">{t('awakened.weakness_label', 'Weak')}:</span>
                              {weakList.map((wk, wIdx) => (
                                <span
                                  key={`${wk}-${wIdx}`}
                                  className={`text-[9px] font-mono font-bold uppercase px-1.5 py-0.2 rounded border ${
                                    wk === '?'
                                      ? 'bg-purple-950/70 text-purple-200 border-purple-500/60'
                                      : 'bg-cyan-950/60 text-cyan-200 border-cyan-700/50'
                                  }`}
                                >
                                  {wk}
                                </span>
                              ))}
                            </div>
                          )}
                          {monster.tether_vessel_name && (
                            <div className={`px-2 py-0.5 rounded border text-[9.5px] font-mono font-bold flex items-center justify-between gap-1 ${
                              monster.tether_sealed
                                ? 'bg-emerald-950/70 border-emerald-600/60 text-emerald-200'
                                : 'bg-amber-950/70 border-amber-600/60 text-amber-200'
                            }`}>
                              <span>
                                {monster.tether_sealed
                                  ? `⛓️ ${t('codex.tether_sealed', 'Tether Sealed')}`
                                  : `🏺 ${t('codex.bound_vessel', 'Bound Vessel')}: ${monster.tether_vessel_name}`}
                              </span>
                            </div>
                          )}
                        </div>
                      );
                    })()}

                    {/* Monster Status Effects */}
                    {statuses.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {statuses.map((st, sIdx) => {
                          const isObj = typeof st === 'object' && st !== null;
                          const baseName = isObj ? (st.name || 'Condition') : String(st || 'Condition');
                          const stacks = isObj ? Math.max(1, Number(st.intensity_stacks || st.stacks || 1)) : 1;
                          const remDur = isObj ? Number(st.remaining_duration ?? st.duration ?? 0) : 0;
                          const durUnit = isObj && st.duration_type === 'minutes' ? 'm' : 't';
                          return (
                            <span
                              key={sIdx}
                              className="text-[9px] px-1.5 py-0.5 rounded bg-amber-950/70 text-amber-300 border border-amber-700/50 font-medium font-mono"
                            >
                              {baseName}
                              {stacks > 1 ? ` x${stacks}` : ''}
                              {remDur > 0 ? ` (${remDur}${durUnit})` : ''}
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
                <span>{t('feed.locked_in_conversation', { npc: conversationLock, defaultValue: `Locked in Conversation: ${conversationLock}` })}</span>
                {currentScene?.active_dialogue_mood?.mood_key && (
                  <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border font-semibold normal-case ${
                    currentScene.active_dialogue_mood.mood_key === 'Engaged'
                      ? 'bg-emerald-950/80 text-emerald-300 border-emerald-700/60'
                      : currentScene.active_dialogue_mood.mood_key === 'Guarded'
                      ? 'bg-amber-950/80 text-amber-300 border-amber-700/60'
                      : currentScene.active_dialogue_mood.mood_key === 'Upset'
                      ? 'bg-rose-950/80 text-rose-300 border-rose-700/60'
                      : 'bg-slate-900/80 text-slate-300 border-slate-700/60'
                  }`}>
                    {t('social.mood_prefix', 'Mood')}: {t(`social.moods.${currentScene.active_dialogue_mood.mood_key}`, currentScene.active_dialogue_mood.mood_label || currentScene.active_dialogue_mood.mood_key)}
                  </span>
                )}
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
