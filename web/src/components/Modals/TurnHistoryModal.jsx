import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowDown, Coins, Gift, Heart, History, Search, X } from 'lucide-react';
import HistoryCard, { getOutcomeTierTheme } from '../StoryFeed/HistoryCard';
import { extractTurnOutcomes } from '../Sidebar/WorldOutcomeSidebar';
import { AcrylicModal, MotionButton } from '../Common/MotionPrimitives';
import { formatScenarioCurrency } from '../../utils/currency';

const TurnHistoryModal = ({
  isOpen,
  onClose,
  session,
  scenario = null,
  onRerollImage = null,
  rerollingImage = false,
}) => {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');
  const scrollRef = useRef(null);
  const effScenario = scenario || session?.scenario || 'fantasy';

  const rawHistory = session?.history;

  const historyRows = useMemo(() => {
    const entries = Array.isArray(rawHistory) ? rawHistory : [];
    const seenClues = new Set();
    const seenCompletedSubs = new Set();
    let actionCount = 0;

    return entries.map((entry, idx) => {
      const prevTitle =
        idx > 0
          ? rawHistory[idx - 1]?.scene_title ||
            rawHistory[idx - 1]?.outcome?.scene_title ||
            ''
          : '';
      let outcomeSummary = null;
      if (entry && typeof entry === 'object' && entry.type !== 'scene') {
        actionCount += 1;
        outcomeSummary = extractTurnOutcomes(
          entry,
          actionCount,
          seenClues,
          seenCompletedSubs
        );
      }
      const isLast = idx === rawHistory.length - 1;
      const imgUrl =
        entry?.scene_image_url ||
        (isLast ? session?.scene_image_url : null) ||
        null;

      return {
        idx,
        entry,
        prevTitle,
        isLast,
        imgUrl,
        outcomeSummary,
      };
    });
  }, [rawHistory, session?.scene_image_url]);

  const trimmedQuery = query.trim().toLowerCase();
  const filteredRows = useMemo(() => {
    if (!trimmedQuery) return historyRows;
    return historyRows.filter(({ entry, outcomeSummary }) => {
      if (typeof entry === 'string') {
        return entry.toLowerCase().includes(trimmedQuery);
      }
      if (!entry || typeof entry !== 'object') return false;
      const hay = [
        entry.scene_title,
        entry.label,
        entry.summary,
        entry.outcome_narrative,
        entry.next_narrative,
        entry.narrative,
        entry.outcome?.scene_title,
        entry.outcome?.outcome_narrative,
        entry.outcome?.next_narrative,
        outcomeSummary?.label,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return hay.includes(trimmedQuery);
    });
  }, [historyRows, trimmedQuery]);

  const jumpToLatest = () => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    }
  };

  useEffect(() => {
    if (!isOpen) {
      setQuery('');
      return undefined;
    }
    const raf = requestAnimationFrame(() => {
      const el = scrollRef.current;
      if (el && !trimmedQuery) {
        el.scrollTop = el.scrollHeight;
      }
    });
    return () => cancelAnimationFrame(raf);
  }, [isOpen, trimmedQuery]);

  const totalActions = historyRows.filter((r) => r.outcomeSummary).length;

  return (
    <AcrylicModal
      isOpen={isOpen}
      onClose={onClose}
      label={t('history.title', 'Turn History')}
      maxWidthClass="max-w-3xl"
    >
      {/* Header */}
      <div className="px-5 py-3.5 border-b border-fantasy-border/35 flex items-center justify-between gap-3 shrink-0">
        <div className="flex items-center gap-2.5 min-w-0">
          <History size={18} className="text-fantasy-accent shrink-0" />
          <h2 className="hk-display font-bold text-base sm:text-lg text-gray-50 truncate">
            {t('history.title', 'Turn History')}
          </h2>
          <span className="hk-chip tabular-nums shrink-0">
            {totalActions === 1
              ? t('scene.turns_count_one', { count: 1, defaultValue: '1 Turn' })
              : t('scene.turns_count_other', {
                  count: totalActions,
                  defaultValue: `${totalActions} Turns`,
                })}
          </span>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {filteredRows.length > 1 && (
            <MotionButton
              onClick={jumpToLatest}
              className="hk-btn hk-btn-ghost h-8 px-2.5 text-xs"
              title={t('history.jump_latest', 'Jump to Latest')}
            >
              <ArrowDown size={13} />
              <span className="hidden sm:inline">
                {t('history.jump_latest', 'Jump to Latest')}
              </span>
            </MotionButton>
          )}
          <MotionButton
            onClick={onClose}
            className="hk-icon-btn h-8 min-w-8"
            aria-label={t('common.close', 'Close')}
            title={t('common.close', 'Close')}
          >
            <X size={18} />
          </MotionButton>
        </div>
      </div>

      {/* Filter Bar */}
      {historyRows.length > 0 && (
        <div className="px-5 py-2.5 border-b border-fantasy-border/25 shrink-0">
          <div className="relative">
            <Search
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none"
            />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t(
                'history.search_placeholder',
                'Search turns, actions, or scenes...'
              )}
              aria-label={t(
                'history.search_placeholder',
                'Search turns, actions, or scenes...'
              )}
              className="hk-input h-9 pl-9 pr-8 text-xs"
            />
            {query && (
              <MotionButton
                onClick={() => setQuery('')}
                aria-label={t('common.close', 'Close')}
                className="hk-icon-btn h-6 min-w-6 absolute right-1.5 top-1/2 -translate-y-1/2"
              >
                <X size={13} />
              </MotionButton>
            )}
          </div>
        </div>
      )}

      {/* Scrollable Chronicle Body */}
      <div
        ref={scrollRef}
        className="flex-1 min-h-0 overflow-y-auto overscroll-contain [scrollbar-gutter:stable] custom-scrollbar px-5 sm:px-7 py-5"
      >
        <div className="max-w-[68ch] mx-auto">
          {filteredRows.length === 0 ? (
            <div className="py-16 text-center text-sm text-gray-400 space-y-2">
              <History size={28} className="mx-auto opacity-40" />
              <p>
                {t('history.no_turns', 'No past turns recorded yet.')}
              </p>
            </div>
          ) : (
            filteredRows.map(
              ({ idx, entry, prevTitle, isLast, imgUrl, outcomeSummary }) => {
                const hasMechanics =
                  outcomeSummary &&
                  (outcomeSummary.xpGained > 0 ||
                    outcomeSummary.hpDelta !== 0 ||
                    outcomeSummary.mpDelta !== 0 ||
                    outcomeSummary.goldDelta !== 0 ||
                    outcomeSummary.itemsGained.length > 0);
                const theme = outcomeSummary
                  ? getOutcomeTierTheme(
                      outcomeSummary.checkTier,
                      outcomeSummary.tierLabel,
                      outcomeSummary.checkStat
                    )
                  : null;

                return (
                  <div key={idx} className="pb-4">
                    <HistoryCard
                      entry={entry}
                      prevSceneTitle={prevTitle}
                      sceneImageUrl={imgUrl}
                      isLatest={isLast}
                      imageGenMode={session?.image_gen_enabled ?? 1}
                      onRerollImage={onRerollImage}
                      isRerollingImage={rerollingImage}
                    />
                    {hasMechanics && (
                      <div className="flex flex-wrap items-center gap-1.5 -mt-3 mb-4 pl-3.5 text-[10.5px] font-mono">
                        {theme && (
                          <span className="text-gray-400 mr-1">
                            #{outcomeSummary.turnNumber}
                          </span>
                        )}
                        {outcomeSummary.xpGained > 0 && (
                          <span className="hk-chip bg-amber-500/20 text-amber-300">
                            ✨ +{outcomeSummary.xpGained} EXP
                          </span>
                        )}
                        {outcomeSummary.hpDelta !== 0 && (
                          <span
                            className={`hk-chip tabular-nums ${
                              outcomeSummary.hpDelta > 0
                                ? 'bg-emerald-500/20 text-emerald-300'
                                : 'bg-red-500/20 text-red-300'
                            }`}
                          >
                            <Heart size={9} />
                            {outcomeSummary.hpDelta > 0
                              ? `+${outcomeSummary.hpDelta}`
                              : outcomeSummary.hpDelta}{' '}
                            HP
                          </span>
                        )}
                        {outcomeSummary.mpDelta !== 0 && (
                          <span className="hk-chip tabular-nums bg-blue-500/20 text-blue-300">
                            💧{' '}
                            {outcomeSummary.mpDelta > 0
                              ? `+${outcomeSummary.mpDelta}`
                              : outcomeSummary.mpDelta}{' '}
                            MP
                          </span>
                        )}
                        {outcomeSummary.goldDelta !== 0 && (
                          <span className="hk-chip tabular-nums bg-amber-500/20 text-amber-300">
                            <Coins size={9} />
                            {outcomeSummary.goldDelta > 0
                              ? `+${formatScenarioCurrency(outcomeSummary.goldDelta, effScenario)}`
                              : `-${formatScenarioCurrency(Math.abs(outcomeSummary.goldDelta), effScenario)}`}
                          </span>
                        )}
                        {outcomeSummary.itemsGained.map((it, iIdx) => (
                          <span
                            key={`hist-gain-${iIdx}`}
                            className="hk-chip bg-cyan-500/20 text-cyan-200"
                          >
                            <Gift size={9} /> +{it}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                );
              }
            )
          )}
        </div>
      </div>
    </AcrylicModal>
  );
};

export default TurnHistoryModal;
