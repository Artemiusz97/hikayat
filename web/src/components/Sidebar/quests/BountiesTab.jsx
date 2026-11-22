import {
  ChevronDown,
  ChevronRight,
  Coins,
  MapPin,
  PlusCircle,
  RefreshCw,
  ShieldAlert,
} from 'lucide-react';
import { cleanProseLocations, formatCleanLocation, formatFullLocationPath } from '../../../utils/locationFormat';
import { formatScenarioCurrency, getScenarioCurrency } from '../../../utils/currency';

const BountiesTab = ({
  noticeBoardLabel,
  availableBounties = [],
  expandedBounties = {},
  onToggleBounty,
  onGenerateBoard,
  onBountyContract,
  busyAction,
  scenario = 'fantasy',
  t,
}) => {
  const currencyMeta = getScenarioCurrency(scenario);
  const currencyLabel = t(`currency.${currencyMeta.key}`, currencyMeta.name);
  return (
    <div className="space-y-3">
      {/* Flat Top Header */}
      <div className="flex items-center justify-between gap-2 pb-2.5 border-b border-white/[0.08]">
        <div className="min-w-0">
          <h4 className="font-bold text-xs text-gray-100">{noticeBoardLabel}</h4>
          <p className="text-[11px] text-gray-400">
            {t('quests.side_contracts_desc', {
              currency: currencyLabel,
              defaultValue: `Accept local side contracts for extra ${currencyLabel} & XP.`,
            })}
          </p>
        </div>
        <button
          type="button"
          disabled={Boolean(busyAction)}
          onClick={() => onGenerateBoard(true)}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-fantasy-accent/20 hover:bg-fantasy-accent/30 text-fantasy-accent border border-fantasy-accent/40 text-[11px] font-bold transition-all shrink-0"
        >
          <RefreshCw size={12} className={busyAction === 'generate_board' ? 'animate-spin' : ''} />
          <span>
            {availableBounties.length === 0
              ? t('quests.post_bounties', 'Post Bounties')
              : t('quests.refresh_board', 'Refresh Board')}
          </span>
        </button>
      </div>

      {availableBounties.length === 0 ? (
        <div className="text-center py-8 px-4 text-gray-400 border border-dashed border-fantasy-border/50 rounded-xl space-y-2">
          <ShieldAlert size={24} className="mx-auto opacity-50 text-amber-400" />
          <p className="text-xs text-gray-300">
            {t('quests.no_bounties', 'No unclaimed postings on the board right now.')}
          </p>
          <p className="text-[11px] text-gray-400">
            {t('quests.post_bounties_tip', 'Click "Post Bounties" above to generate fresh local contracts!')}
          </p>
        </div>
      ) : (
        <div className="space-y-2.5">
          {availableBounties.map((b, idx) => {
            const bId = b.quest_id || `bounty-${idx}`;
            const isExpanded = expandedBounties[bId] ?? false;
            const isLocked = b.anomalous_eligible === false;
            return (
              <div
                key={bId}
                className={`bg-gray-500/5 border rounded-xl overflow-hidden transition-colors ${
                  isLocked
                    ? 'border-rose-500/35 opacity-85'
                    : 'border-fantasy-border/35 hover:border-amber-500/45'
                }`}
              >
                <button
                  type="button"
                  onClick={() => onToggleBounty(bId)}
                  aria-expanded={isExpanded}
                  className="w-full px-3 py-2.5 flex justify-between items-start gap-2 text-left cursor-pointer group"
                  title={isExpanded ? 'Tap to collapse' : 'Tap to view details & accept'}
                >
                  <div className="min-w-0 flex-1 space-y-1">
                    <h5 className="font-bold text-[13px] text-gray-100 leading-snug group-hover:text-amber-300 transition-colors">
                      {cleanProseLocations(b.title)}
                    </h5>
                    {!isExpanded && (
                      <p className="text-[11px] text-gray-400 truncate">
                        {b.target_location
                          ? formatCleanLocation(b.target_location)
                          : cleanProseLocations(b.objective || b.description)}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-1 shrink-0 mt-0.5">
                    {isLocked && (
                      <span
                        className="text-[9.5px] px-1.5 py-0.5 bg-rose-950/70 text-rose-300 rounded font-bold uppercase border border-rose-700/60"
                        title={b.anomalous_lock_reason || t('phone.bounties.locked_faction_btn', '🔒 Board Restricted')}
                      >
                        🔒
                      </span>
                    )}
                    <span className="text-[9.5px] px-1.5 py-0.5 bg-amber-950/60 text-amber-300 rounded font-bold uppercase border border-amber-800/50">
                      {b.quest_type || 'Contract'}
                    </span>
                    <span className="text-gray-400 group-hover:text-amber-300">
                      {isExpanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                    </span>
                  </div>
                </button>

                {isExpanded && (
                  <div className="px-3 py-2.5 border-t border-white/[0.06] space-y-2.5">
                    <p className="text-[12px] text-gray-200 leading-[1.45] hk-quest-prose">
                      {cleanProseLocations(b.objective || b.description)}
                    </p>

                    {b.target_location && (
                      <div
                        className="flex items-start gap-1.5 text-[11.5px] text-amber-200 leading-snug"
                        title={formatFullLocationPath(b.target_location)}
                      >
                        <MapPin size={13} className="text-amber-400 shrink-0 mt-0.5" />
                        <span className="break-words">
                          <strong>{formatCleanLocation(b.target_location)}</strong>
                          {b.target_npc ? ` · ${b.target_npc}` : ''}
                        </span>
                      </div>
                    )}

                    {isLocked && b.anomalous_lock_reason && (
                      <div className="border-l-2 border-rose-500 bg-rose-950/30 rounded-r-lg px-2.5 py-1.5 text-[11px] text-rose-200 leading-snug">
                        🔒 {b.anomalous_lock_reason}
                      </div>
                    )}

                    <div className="flex items-center justify-between gap-2 flex-wrap pt-2 border-t border-white/[0.06]">
                      <div className="flex items-center gap-2.5 text-[11px] font-mono tabular-nums">
                        {b.reward_gold ? (
                          <span className="text-amber-300">
                            +{formatScenarioCurrency(b.reward_gold, scenario)}
                          </span>
                        ) : null}
                        {b.reward_xp ? <span className="text-purple-300">+{b.reward_xp} XP</span> : null}
                        {b.reward_item ? <span className="text-cyan-300">🎁 {b.reward_item}</span> : null}
                      </div>

                      <div className="flex items-center gap-1.5 flex-wrap">
                        <button
                          type="button"
                          disabled={Boolean(busyAction) || isLocked}
                          onClick={() => onBountyContract(b.quest_id, 'accept', false)}
                          title={
                            isLocked
                              ? b.anomalous_lock_reason || t('phone.bounties.locked_faction_btn', '🔒 Board Restricted')
                              : undefined
                          }
                          className={`flex items-center gap-1 px-2.5 py-1 rounded border text-[11px] font-bold transition-colors ${
                            isLocked
                              ? 'bg-neutral-900/60 text-gray-500 border-neutral-700/50 opacity-50 cursor-not-allowed'
                              : 'bg-emerald-950/60 hover:bg-emerald-900/70 text-emerald-300 border-emerald-700/60 cursor-pointer'
                          }`}
                        >
                          <PlusCircle size={12} />
                          <span>
                            {isLocked
                              ? t('phone.bounties.locked_faction_btn', '🔒 Board Restricted')
                              : t('quests.accept', 'Accept')}
                          </span>
                        </button>
                        {!isLocked && (
                          <button
                            type="button"
                            disabled={Boolean(busyAction)}
                            onClick={() => onBountyContract(b.quest_id, 'accept', true)}
                            className="flex items-center gap-1 px-2 py-1 rounded bg-amber-950/60 hover:bg-amber-900/70 text-amber-200 border border-amber-700/60 text-[10.5px] font-bold transition-colors cursor-pointer"
                            title={t('quests.haggle_advance_tooltip', {
                              currency: currencyLabel,
                              defaultValue: `Attempt a CHA check to haggle an upfront ${currencyLabel} advance`,
                            })}
                          >
                            <Coins size={11} />
                            <span>{t('quests.accept_advance', 'Accept + Advance (CHA)')}</span>
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default BountiesTab;
