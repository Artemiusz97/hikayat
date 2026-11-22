import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import HistoryCard, {
  formatNarrative,
  getOutcomeTierTheme,
} from './HistoryCard';
import SceneImageCard from './SceneImageCard';
import {
  Feather,
  Heart,
  History,
  Skull,
  Sparkles,
  Square,
  Swords,
} from 'lucide-react';
import { MotionButton } from '../Common/MotionPrimitives';

const StoryFeed = ({
  history,
  currentScene,
  isStreaming,
  isThinking = false,
  cancellingTurn = false,
  streamingNarrative,
  streamingState,
  selectedCombatTarget,
  onSelectCombatTarget,
  showEnemyHp = true,
  showEnemyIntent = true,
  readingMode = 'continuous',
  onOpenHistory = null,
  processing,
  pendingAction,
  onCancelTurn = null,
  onRerollImage = null,
  rerollingImage = false,
}) => {
  const { t } = useTranslation();
  const scrollContainerRef = useRef(null);
  const latestTurnRef = useRef(null);
  const shouldStickToBottomRef = useRef(true);
  const prevSessionIdRef = useRef(currentScene?.id);
  const hasInitialScrolledRef = useRef(false);

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
    currentNar &&
      ((lastHistNextNar && lastHistNextNar === currentNar) ||
        (lastHist?.outcome_narrative &&
          String(lastHist.outcome_narrative).trim() === currentNar))
  );
  const isSceneOnly = readingMode === 'scene';
  const priorTurnCount = isSceneOnly ? Math.max(0, histList.length - 1) : 0;
  const visibleEntries =
    isSceneOnly && histList.length > 0
      ? [{ entry: histList[histList.length - 1], idx: histList.length - 1 }]
      : histList.map((entry, idx) => ({ entry, idx }));
  const isProcessingOrStreaming = Boolean(processing || isStreaming);

  const handleScroll = () => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    shouldStickToBottomRef.current = distanceFromBottom < 120;
  };

  // Scroll to the latest turn on mount, session switch, new turn arrival, or processing banner
  useEffect(() => {
    const isInstant =
      !hasInitialScrolledRef.current ||
      prevSessionIdRef.current !== currentScene?.id;
    prevSessionIdRef.current = currentScene?.id;
    hasInitialScrolledRef.current = true;
    shouldStickToBottomRef.current = true;

    const rafId = requestAnimationFrame(() => {
      const el = scrollContainerRef.current;
      if (!el) return;
      let targetTop;
      if (processing || !latestTurnRef.current) {
        targetTop = el.scrollHeight;
      } else {
        const elRect = el.getBoundingClientRect();
        const latestRect = latestTurnRef.current.getBoundingClientRect();
        if (latestRect.height > el.clientHeight - 32) {
          targetTop = Math.max(0, el.scrollTop + (latestRect.top - elRect.top) - 20);
        } else {
          targetTop = el.scrollHeight;
        }
      }
      if (isInstant) {
        el.scrollTop = targetTop;
      } else {
        el.scrollTo({ top: targetTop, behavior: 'smooth' });
      }
    });

    return () => cancelAnimationFrame(rafId);
  }, [currentScene?.id, histList.length, currentNar, processing, readingMode]);

  // Follow live streamed prose chunks unless the user scrolled up to re-read earlier turns
  useEffect(() => {
    if (
      isStreaming &&
      shouldStickToBottomRef.current &&
      scrollContainerRef.current
    ) {
      scrollContainerRef.current.scrollTop =
        scrollContainerRef.current.scrollHeight;
    }
  }, [
    isStreaming,
    streamingNarrative,
    streamingState?.outcomeText,
    streamingState?.nextText,
  ]);

  const rawMonsters =
    currentScene?.nearby_enemies || currentScene?.monsters || [];
  const activeMonsters = Array.isArray(rawMonsters)
    ? rawMonsters.filter((m) => m && m.name)
    : [];
  const conversationLock = currentScene?.conversation_lock;

  const streamAction = streamingState?.action || null;
  const streamOutcomeText = streamingState?.outcomeText || '';
  const streamNextText = streamingState?.nextText || '';
  const streamTheme = getOutcomeTierTheme(
    streamAction?.tier || streamAction?.check?.tier,
    streamAction?.check?.tier_label || streamAction?.tier_label,
    streamAction?.stat
  );
  const streamStat = streamAction?.stat;
  const streamStatPrefix =
    streamStat && streamStat !== 'NONE' && streamStat !== 'FREE'
      ? `${streamStat} • `
      : '';
  const streamTierLabel = (
    streamAction?.check?.tier_label ||
    streamAction?.tier_label ||
    streamTheme.defaultLabel
  ).toUpperCase();
  const streamChance =
    streamAction?.check?.chance ?? streamAction?.rate ?? null;
  const streamChanceSuffix =
    streamChance !== null &&
    streamChance !== undefined &&
    streamStat !== 'NONE' &&
    streamStat !== 'FREE'
      ? ` (${Math.round(Number(streamChance))}%)`
      : '';

  return (
    <div className="flex flex-col flex-auto min-h-0 max-h-full w-full min-w-0 relative z-10">
      {/* Pinned Active Combat Hostiles Strip */}
      {activeMonsters.length > 0 && (
        <div className="shrink-0 border-b border-red-500/30 bg-red-950/20 px-4 sm:px-6 py-2.5 max-h-[34%] overflow-y-auto overscroll-contain custom-scrollbar">
          <div className="max-w-[70ch] mx-auto space-y-2">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <div className="flex items-center gap-2 text-red-300 font-rpg font-bold text-xs sm:text-sm uppercase tracking-wider">
                <Swords size={15} className="text-red-400 animate-pulse" />
                <span>{t('feed.active_combat', 'Active Combat Encounter')}</span>
              </div>
              <div className="flex items-center gap-1.5 flex-wrap">
                {currentScene?.construct_status && (
                  <span className="hk-chip bg-cyan-500/20 text-cyan-200 font-mono text-[10.5px]">
                    🤖{' '}
                    {t('awakened.construct_active', {
                      name: currentScene.construct_status.name,
                      hp: currentScene.construct_status.hp,
                      max_hp: currentScene.construct_status.max_hp,
                      defaultValue: `Construct: ${currentScene.construct_status.name} (${currentScene.construct_status.hp}/${currentScene.construct_status.max_hp} HP)`,
                    })}
                    {currentScene.construct_status.windup_skill
                      ? ` • ⚙️ ${currentScene.construct_status.windup_skill}`
                      : ''}
                  </span>
                )}
                <span className="hk-chip bg-red-500/25 text-red-200 font-mono text-[10.5px]">
                  {t('feed.hostiles_active', {
                    active: activeMonsters.filter((m) => (m.hp ?? 1) > 0)
                      .length,
                    total: activeMonsters.length,
                    defaultValue: `${
                      activeMonsters.filter((m) => (m.hp ?? 1) > 0).length
                    } / ${activeMonsters.length} Hostiles Active`,
                  })}
                </span>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 divide-y sm:divide-y-0 divide-red-500/20">
              {activeMonsters.map((monster, mIdx) => {
                const maxHp = Math.max(
                  1,
                  Number(monster.max_hp || monster.hp || 100)
                );
                const hp = Math.max(
                  0,
                  Number(monster.hp !== undefined ? monster.hp : maxHp)
                );
                const pct = Math.min(100, Math.round((hp / maxHp) * 100));
                const isDefeated = hp <= 0;
                const isSelectedTarget =
                  !isDefeated && selectedCombatTarget === monster.name;
                const statuses = Array.isArray(monster.status_effects)
                  ? monster.status_effects
                  : [];

                return (
                  <div
                    key={`${monster.name}-${mIdx}`}
                    onClick={() => {
                      if (!isDefeated && onSelectCombatTarget) {
                        onSelectCombatTarget(monster.name);
                      }
                    }}
                    className={`py-2 px-2.5 rounded-lg transition-all ${
                      isDefeated
                        ? 'opacity-45'
                        : isSelectedTarget
                          ? 'bg-red-500/15 ring-1 ring-amber-400/70 cursor-pointer'
                          : 'hover:bg-red-500/10 cursor-pointer'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <div className="flex items-center gap-1.5 min-w-0 flex-wrap">
                        <Skull
                          size={13}
                          className={
                            isDefeated
                              ? 'text-gray-500 shrink-0'
                              : isSelectedTarget
                                ? 'text-amber-400 shrink-0'
                                : 'text-red-400 shrink-0'
                          }
                        />
                        <span
                          className={`text-xs font-bold truncate ${
                            isDefeated
                              ? 'line-through text-gray-400'
                              : 'text-gray-100'
                          }`}
                        >
                          {monster.name}
                        </span>
                        {isSelectedTarget && (
                          <span className="hk-chip bg-amber-500/25 text-amber-200 text-[9px] font-bold uppercase shrink-0">
                            🎯 {t('feed.target', 'Target')}
                          </span>
                        )}
                        {!isDefeated && monster.aggro_target_name && (
                          <span
                            className={`hk-chip text-[9px] font-bold shrink-0 ${
                              monster.aggro_mode === 'taunted'
                                ? 'bg-amber-500/20 text-amber-200'
                                : 'bg-rose-500/20 text-rose-200'
                            }`}
                          >
                            {monster.aggro_mode === 'taunted'
                              ? `🔒 ${t('combat.taunted_label', 'Taunted')}: ${monster.aggro_target_name}`
                              : `🎯 ${t('combat.aggro_label', 'Aggro')}: ${monster.aggro_target_name}`}
                          </span>
                        )}
                      </div>
                      <span className="text-[10px] font-mono tabular-nums text-red-300 shrink-0">
                        Lv.{monster.level || 1}
                      </span>
                    </div>

                    {showEnemyHp && (
                      <div className="space-y-0.5">
                        <div className="flex justify-between items-center text-[10px] font-mono">
                          <span className="text-red-300 flex items-center gap-1">
                            <Heart size={10} className="text-red-400" /> HP
                          </span>
                          <span className="text-gray-300 font-semibold tabular-nums">
                            {hp} / {maxHp} ({pct}%)
                          </span>
                        </div>
                        <div className="h-1.5 w-full bg-gray-500/25 rounded-full overflow-hidden">
                          <div
                            className={`h-full transition-all duration-500 ${
                              pct > 50
                                ? 'bg-red-500'
                                : pct > 25
                                  ? 'bg-amber-500'
                                  : 'bg-rose-600'
                            }`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    )}

                    {showEnemyIntent &&
                      !isDefeated &&
                      monster.telegraphed_skill &&
                      typeof monster.telegraphed_skill === 'object' &&
                      (() => {
                        const skillLabel =
                          monster.telegraphed_skill.skill_name ||
                          monster.telegraphed_skill.telegraphed_label ||
                          monster.telegraphed_skill.name ||
                          'Signature Attack';
                        const staggerPct = Math.max(
                          0,
                          Math.min(100, Number(monster.stagger_pct || 0))
                        );
                        const isBreaking = staggerPct >= 65;
                        const staggerLabel = isBreaking
                          ? t('combat.stagger_breaking', 'Breaking!')
                          : t('combat.stagger_label', 'Stagger');
                        return (
                          <div className="mt-1.5 pl-2 border-l-2 border-amber-400/75 space-y-1">
                            <div className="flex items-center justify-between gap-2 text-[10px] font-mono">
                              <span className="font-bold text-amber-200 truncate">
                                ⚠️ {t('combat.charging_skill', 'CHARGING')}:{' '}
                                {skillLabel}
                              </span>
                              <span
                                className={`font-bold tabular-nums shrink-0 ${
                                  isBreaking
                                    ? 'text-rose-300 motion-safe:animate-pulse'
                                    : 'text-amber-300'
                                }`}
                              >
                                {staggerLabel} ({staggerPct}%)
                              </span>
                            </div>
                            <div
                              role="progressbar"
                              aria-label={`${t(
                                'combat.stagger_label',
                                'Stagger'
                              )} — ${skillLabel}`}
                              aria-valuemin={0}
                              aria-valuemax={100}
                              aria-valuenow={staggerPct}
                              className="h-1 w-full bg-gray-500/25 rounded-full overflow-hidden"
                            >
                              <div
                                className={`h-full transition-all duration-500 ${
                                  isBreaking ? 'bg-rose-500' : 'bg-amber-400'
                                }`}
                                style={{ width: `${staggerPct}%` }}
                              />
                            </div>
                          </div>
                        );
                      })()}

                    {Number(monster.max_stability || 0) > 0 &&
                      !isDefeated &&
                      (() => {
                        const maxStab = Math.max(
                          1,
                          Number(monster.max_stability)
                        );
                        const curStab = Math.max(
                          0,
                          Number(monster.stability ?? maxStab)
                        );
                        const stabPct = Math.min(
                          100,
                          Math.round((curStab / maxStab) * 100)
                        );
                        const isBreached = Boolean(monster.is_breached);
                        const breachTurns = Number(
                          monster.breached_turns_left || 1
                        );
                        const weakList = Array.isArray(
                          monster.display_weaknesses
                        )
                          ? monster.display_weaknesses
                          : Array.isArray(monster.revealed_weaknesses)
                            ? monster.revealed_weaknesses
                            : Array.isArray(monster.weaknesses)
                              ? monster.weaknesses
                              : [];
                        return (
                          <div className="mt-1.5 pt-1 border-t border-red-500/25 space-y-1">
                            {isBreached ? (
                              <div className="px-2 py-0.5 rounded bg-fuchsia-500/20 text-fuchsia-200 text-[10px] font-mono font-bold uppercase tracking-wider text-center animate-pulse">
                                💥{' '}
                                {t('awakened.breached_badge', {
                                  turns: breachTurns,
                                  defaultValue: `ANOMALY BREACHED! [${breachTurns}T]`,
                                })}
                              </div>
                            ) : (
                              <div className="space-y-0.5">
                                <div className="flex justify-between items-center text-[9.5px] font-mono">
                                  <span className="text-cyan-300">
                                    💠 {t('awakened.stability_label', 'Poise')}
                                  </span>
                                  <span className="text-cyan-100 font-semibold tabular-nums">
                                    {curStab} / {maxStab}
                                  </span>
                                </div>
                                <div className="h-1 w-full bg-gray-500/25 rounded-full overflow-hidden">
                                  <div
                                    className="h-full bg-cyan-400 transition-all duration-500"
                                    style={{ width: `${stabPct}%` }}
                                  />
                                </div>
                              </div>
                            )}
                            {weakList.length > 0 && (
                              <div className="flex items-center gap-1 flex-wrap">
                                <span className="text-[9px] font-mono uppercase text-gray-400">
                                  {t('awakened.weakness_label', 'Weak')}:
                                </span>
                                {weakList.map((wk, wIdx) => (
                                  <span
                                    key={`${wk}-${wIdx}`}
                                    className={`text-[9px] font-mono font-bold uppercase px-1.5 py-0.5 rounded ${
                                      wk === '?'
                                        ? 'bg-purple-500/25 text-purple-200'
                                        : 'bg-cyan-500/20 text-cyan-200'
                                    }`}
                                  >
                                    {wk}
                                  </span>
                                ))}
                              </div>
                            )}
                            {monster.tether_vessel_name && (
                              <div
                                className={`text-[9.5px] font-mono font-semibold ${
                                  monster.tether_sealed
                                    ? 'text-emerald-300'
                                    : 'text-amber-300'
                                }`}
                              >
                                {monster.tether_sealed
                                  ? `⛓️ ${t('codex.tether_sealed', 'Tether Sealed')}`
                                  : `🏺 ${t('codex.bound_vessel', 'Bound Vessel')}: ${monster.tether_vessel_name}`}
                              </div>
                            )}
                          </div>
                        );
                      })()}

                    {statuses.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1.5">
                        {statuses.map((st, sIdx) => {
                          const isObj = typeof st === 'object' && st !== null;
                          const baseName = isObj
                            ? st.name || 'Condition'
                            : String(st || 'Condition');
                          const stacks = isObj
                            ? Math.max(
                                1,
                                Number(st.intensity_stacks || st.stacks || 1)
                              )
                            : 1;
                          const remDur = isObj
                            ? Number(st.remaining_duration ?? st.duration ?? 0)
                            : 0;
                          const durUnit =
                            isObj && st.duration_type === 'minutes' ? 'm' : 't';
                          return (
                            <span
                              key={sIdx}
                              className="hk-chip bg-amber-500/20 text-amber-200 font-mono text-[9px]"
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
        </div>
      )}

      {/* Scrollable Prose Region */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="flex-auto min-h-0 overflow-y-auto overscroll-contain [scrollbar-gutter:stable] custom-scrollbar px-5 sm:px-7 py-5"
      >
        <div className="max-w-[70ch] mx-auto relative">
          {priorTurnCount > 0 && onOpenHistory && (
            <div className="mb-3 flex justify-center">
              <button
                type="button"
                onClick={onOpenHistory}
                className="hk-chip inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-gray-500/15 hover:bg-fantasy-accent/15 border border-fantasy-border/40 hover:border-fantasy-accent/50 text-xs text-gray-300 hover:text-fantasy-accent transition-colors cursor-pointer"
              >
                <History size={12} />
                <span>
                  {t('history.view_earlier', {
                    count: priorTurnCount,
                    defaultValue: `View Turn History (${priorTurnCount} earlier)`,
                  })}
                </span>
              </button>
            </div>
          )}

          {/* Render visible history entry(s) */}
          {visibleEntries.map(({ entry, idx }) => {
            const prevTitle =
              idx > 0
                ? histList[idx - 1]?.scene_title ||
                  histList[idx - 1]?.outcome?.scene_title ||
                  ''
                : '';
            const isLast = idx === histList.length - 1;
            const imgUrl =
              entry?.scene_image_url ||
              (isLast && isCurrentSceneAlreadyInHistory
                ? currentScene?.scene_image_url
                : null);
            const isLatestBlock =
              isLast &&
              !isProcessingOrStreaming &&
              (!currentNar || isCurrentSceneAlreadyInHistory);
            return (
              <div key={idx} ref={isLatestBlock ? latestTurnRef : undefined}>
                <HistoryCard
                  entry={entry}
                  prevSceneTitle={prevTitle}
                  sceneImageUrl={imgUrl}
                  isLatest={isLast}
                  imageGenMode={currentScene?.image_gen_enabled ?? 1}
                  onRerollImage={onRerollImage}
                  isRerollingImage={rerollingImage}
                />
              </div>
            );
          })}

          {/* Active opening/unsynced scene narrative */}
          {currentScene && currentNar && !isCurrentSceneAlreadyInHistory && (
            <div
              ref={!isProcessingOrStreaming ? latestTurnRef : undefined}
              className="mb-6 md:mb-8"
            >
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
              <div className="text-gray-100 font-serif text-[14px] sm:text-[0.96875rem] md:text-[1.0625rem] leading-[1.75] tracking-wide">
                {formatNarrative(currentNar)}
              </div>
            </div>
          )}

          {/* Turn Processing Banner */}
          {processing && !isStreaming && (
            <div className="mb-6 md:mb-8 animate-fadeIn">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-2.5 pt-2 border-t border-fantasy-border/30">
                <div className="flex items-center gap-2 min-w-0 text-xs text-amber-300 font-medium">
                  <span className="text-fantasy-accent not-italic font-mono text-[11px]">
                    ▸
                  </span>
                  <span className="truncate">
                    {pendingAction?.label ||
                      pendingAction?.direct_choice?.label ||
                      pendingAction?.direct_choice?.text ||
                      pendingAction?.custom_action_text ||
                      t('feed.resolving_action', 'Resolving Action...')}
                  </span>
                  <span
                    className={`hk-chip font-mono ${
                      isThinking
                        ? 'text-violet-300 bg-violet-500/15 animate-pulse'
                        : 'text-amber-300 bg-amber-500/15'
                    }`}
                  >
                    <Sparkles size={10} className="animate-spin" />
                    {isThinking
                      ? t('feed.thinking', 'Thinking...')
                      : t('feed.resolving', 'Resolving')}
                  </span>
                </div>
                {onCancelTurn &&
                  currentScene?.id !== 'embarking' &&
                  !pendingAction?.isSyncTurnZeroRetry && (
                    <MotionButton
                      onClick={onCancelTurn}
                      disabled={cancellingTurn}
                      className="hk-chip bg-red-500/20 hover:bg-red-500/30 text-red-200 font-mono uppercase tracking-wider shrink-0 cursor-pointer disabled:opacity-50"
                      title={t('feed.cancel_turn', 'Stop')}
                    >
                      <Square size={9} className="fill-current" />
                      <span>
                        {cancellingTurn
                          ? t('feed.cancelling_turn', 'Stopping...')
                          : t('feed.cancel_turn', 'Stop')}
                      </span>
                    </MotionButton>
                  )}
              </div>
              <div className="border-l-2 border-amber-500/60 pl-4 py-2.5 flex items-center gap-3 text-sm text-amber-200/90">
                <div className="w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin shrink-0" />
                <div className="flex flex-col">
                  <span className="font-semibold text-xs tracking-wider uppercase text-amber-300">
                    {isThinking
                      ? t(
                          'feed.chronicler_thinking',
                          'The Chronicler is thinking through your move...'
                        )
                      : t(
                          'feed.chronicler_resolving',
                          'The Chronicler is resolving your choice...'
                        )}
                  </span>
                  <span className="text-[11px] text-gray-400 mt-0.5">
                    {t(
                      'feed.calculating_outcomes',
                      'Calculating outcomes, dice checks, and world reactions...'
                    )}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Real-Time Streaming Turn */}
          {isStreaming && (
            <div className="mb-6 md:mb-8 animate-fadeIn">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-2.5 pt-2 border-t border-fantasy-border/30">
                <div className="flex items-center gap-2 min-w-0 text-xs text-gray-400 italic">
                  <span className="text-fantasy-accent not-italic font-mono text-[11px]">
                    ▸
                  </span>
                  <span className="truncate">
                    {streamAction?.label ||
                      t('feed.resolving_action', 'Resolving Action...')}
                  </span>
                  <span
                    className={`hk-chip font-mono not-italic ${
                      isThinking
                        ? 'text-violet-300 bg-violet-500/15 animate-pulse'
                        : 'text-amber-300 bg-amber-500/15'
                    }`}
                  >
                    <Feather size={10} className="animate-bounce" />
                    {isThinking
                      ? t('feed.thinking', 'Thinking...')
                      : t('feed.live', 'Live')}
                  </span>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  {streamAction && (
                    <span
                      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full border text-[10px] font-mono font-bold uppercase tracking-wider shrink-0 ${streamTheme.badgeClass}`}
                    >
                      <span>{streamTheme.icon}</span>
                      <span>
                        {streamStatPrefix}
                        {streamTierLabel}
                        {streamChanceSuffix}
                      </span>
                    </span>
                  )}
                  {onCancelTurn &&
                    currentScene?.id !== 'embarking' &&
                    !pendingAction?.isSyncTurnZeroRetry && (
                      <MotionButton
                        onClick={onCancelTurn}
                        disabled={cancellingTurn}
                        className="hk-chip bg-red-500/20 hover:bg-red-500/30 text-red-200 font-mono uppercase tracking-wider cursor-pointer disabled:opacity-50"
                        title={t('feed.cancel_turn', 'Stop')}
                      >
                        <Square size={9} className="fill-current" />
                        <span>
                          {cancellingTurn
                            ? t('feed.cancelling_turn', 'Stopping...')
                            : t('feed.cancel_turn', 'Stop')}
                        </span>
                      </MotionButton>
                    )}
                </div>
              </div>

              {streamOutcomeText || streamNextText || streamingNarrative ? (
                <div>
                  {(streamOutcomeText ||
                    (!streamNextText && streamingNarrative)) && (
                    <div
                      className={`border-l-2 ${streamTheme.accentBorderClass} pl-3.5 md:pl-4 py-0.5 font-serif text-[14px] sm:text-[0.96875rem] md:text-[1.0625rem] leading-[1.75] tracking-wide ${streamTheme.textClass}`}
                    >
                      {formatNarrative(
                        streamOutcomeText || streamingNarrative
                      )}
                      {!streamNextText && (
                        <span className="inline-block w-2 h-4 ml-1 bg-fantasy-accent animate-pulse align-middle" />
                      )}
                    </div>
                  )}

                  {streamNextText && (
                    <div className="mt-4 md:mt-5 text-gray-100 font-serif text-[14px] sm:text-[0.96875rem] md:text-[1.0625rem] leading-[1.75] tracking-wide">
                      {formatNarrative(streamNextText)}
                      <span className="inline-block w-2 h-4 ml-1 bg-fantasy-accent animate-pulse align-middle" />
                    </div>
                  )}
                </div>
              ) : (
                <div
                  className={`border-l-2 ${streamTheme.accentBorderClass} pl-4 py-2 flex items-center gap-2 text-sm italic ${
                    isThinking ? 'text-violet-300' : 'text-gray-400'
                  }`}
                >
                  <Sparkles
                    size={14}
                    className={`${
                      isThinking ? 'text-violet-400' : 'text-amber-400'
                    } animate-spin`}
                  />
                  <span>
                    {isThinking
                      ? t(
                          'feed.chronicler_thinking',
                          'The Chronicler is thinking through your move...'
                        )
                      : t(
                          'feed.chronicler_weaving',
                          'The Chronicler is weaving your fate...'
                        )}
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Conversation Lock Indicator */}
          {conversationLock && (
            <div className="mt-5 mb-2 border-t border-b border-purple-500/35 py-2.5 px-1 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-purple-300 font-rpg font-bold text-xs sm:text-sm uppercase tracking-wider">
                <Heart size={15} className="text-purple-400 shrink-0" />
                <span>
                  {t('feed.locked_in_conversation', {
                    npc: conversationLock,
                    defaultValue: `Locked in Conversation: ${conversationLock}`,
                  })}
                </span>
              </div>
              {currentScene?.active_dialogue_mood?.mood_key && (
                <span
                  className={`text-[10px] font-mono px-2 py-0.5 rounded font-semibold ${
                    currentScene.active_dialogue_mood.mood_key === 'Engaged'
                      ? 'bg-emerald-500/20 text-emerald-300'
                      : currentScene.active_dialogue_mood.mood_key === 'Guarded'
                        ? 'bg-amber-500/20 text-amber-300'
                        : currentScene.active_dialogue_mood.mood_key === 'Upset'
                          ? 'bg-rose-500/20 text-rose-300'
                          : 'bg-slate-500/20 text-slate-300'
                  }`}
                >
                  {t('social.mood_prefix', 'Mood')}:{' '}
                  {t(
                    `social.moods.${currentScene.active_dialogue_mood.mood_key}`,
                    currentScene.active_dialogue_mood.mood_label ||
                      currentScene.active_dialogue_mood.mood_key
                  )}
                </span>
              )}
            </div>
          )}

          <div className="h-2" />
        </div>
      </div>
    </div>
  );
};

export default StoryFeed;
