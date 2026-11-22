import { RefreshCw, ShieldAlert } from 'lucide-react';
import { cleanProseLocations } from '../../utils/locationFormat';
import { formatScenarioCurrency } from '../../utils/currency';

const PhoneBountiesApp = ({
  branding,
  generatingBounties,
  onRefreshBounties,
  bountySubTab,
  onChangeBountySubTab,
  allAvailableBounties = [],
  availableBounties = [],
  activeBounties = [],
  factionsList = [],
  selectedFactionFilter,
  onSelectFactionFilter,
  bountyActionBanner,
  onClearBanner,
  onAcceptBounty,
  onAbandonBounty,
  busyBountyId = null,
  scenario = 'fantasy',
  t,
}) => {
  const isBusy = Boolean(busyBountyId);
  return (
    <div className="flex flex-col h-full space-y-2.5 min-h-0">
      {/* Header + Subtitle + Refresh */}
      <div className="flex items-center justify-between pb-1 border-b border-neutral-800/80 shrink-0">
        <div>
          <h4 className="font-bold text-sm text-gray-100 flex items-center gap-1.5">
            <ShieldAlert size={15} className="text-rose-400" />
            <span>{branding.bounty_app_name || branding.bounties_app_name || 'Campus Requests'}</span>
          </h4>
          <p className="text-[10px] text-gray-400">
            {branding.bounty_subtitle || 'Student Bulletin & Faction Gigs'}
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            disabled={generatingBounties}
            onClick={() => onRefreshBounties()}
            className="p-1.5 rounded-xl bg-neutral-900 hover:bg-neutral-800 text-gray-300 border border-neutral-800 transition-colors cursor-pointer"
            title={t('phone.bounties.refresh_title', 'Refresh Bulletin Requests')}
          >
            <RefreshCw size={13} className={generatingBounties ? 'animate-spin text-rose-400' : ''} />
          </button>
          <span className="text-[10px] font-mono tabular-nums px-2 py-0.5 rounded-full bg-rose-950/50 text-rose-300 border border-rose-700/50 font-semibold">
            {availableBounties.length} Available
          </span>
        </div>
      </div>

      {/* Sub-tabs: Available vs Active Tasks */}
      <div className="flex bg-neutral-900 p-1 rounded-xl border border-neutral-800 gap-1 shrink-0">
        <button
          type="button"
          onClick={() => onChangeBountySubTab('available')}
          className={`flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[11px] font-bold transition-colors ${
            bountySubTab === 'available'
              ? 'bg-rose-600/30 text-rose-200 border border-rose-500/50'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          <span>Available Tasks ({availableBounties.length})</span>
        </button>
        <button
          type="button"
          onClick={() => onChangeBountySubTab('active')}
          className={`flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[11px] font-bold transition-colors ${
            bountySubTab === 'active'
              ? 'bg-amber-600/30 text-amber-200 border border-amber-500/50'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          <span>Active Tasks ({activeBounties.length})</span>
        </button>
      </div>

      {/* Faction Filter Navigation Pills */}
      {bountySubTab === 'available' && factionsList.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 pb-0.5 shrink-0">
          <button
            type="button"
            onClick={() => onSelectFactionFilter('all')}
            className={`px-2.5 py-1 rounded-full text-xs font-bold transition-colors shrink-0 border cursor-pointer ${
              selectedFactionFilter === 'all'
                ? 'bg-rose-600/30 text-rose-200 border-rose-500/50'
                : 'bg-neutral-900 text-gray-400 border-neutral-800 hover:text-gray-200'
            }`}
          >
            All ({allAvailableBounties.length})
          </button>
          {factionsList.map((f) => {
            const isLockedBoard = f.bounty_board_eligible === false;
            return (
              <button
                key={f.faction_id || f.name}
                type="button"
                onClick={() => onSelectFactionFilter(f.faction_id || f.name)}
                title={
                  isLockedBoard
                    ? t(
                        'phone.bounties.locked_faction_tip',
                        'Locked: Outlaws are blacklisted at licensed Bureau boards; private internal boards are members-only.'
                      )
                    : undefined
                }
                className={`px-2.5 py-1 rounded-full text-xs font-bold transition-colors shrink-0 border cursor-pointer ${
                  selectedFactionFilter === (f.faction_id || f.name)
                    ? 'bg-purple-600/30 text-purple-200 border-purple-500/50'
                    : isLockedBoard
                      ? 'bg-neutral-950/80 text-gray-500 border-neutral-800/80 hover:text-gray-300'
                      : 'bg-neutral-900 text-gray-400 border-neutral-800 hover:text-gray-200'
                }`}
              >
                {isLockedBoard ? `🔒 ${f.name}` : f.name}
              </button>
            );
          })}
        </div>
      )}

      {/* Feedback / Action Banner */}
      {bountyActionBanner && (
        <div
          className={`p-2.5 rounded-xl text-xs border flex items-center justify-between shrink-0 ${
            bountyActionBanner.type === 'ok'
              ? 'bg-emerald-950/50 border-emerald-700/60 text-emerald-200'
              : bountyActionBanner.type === 'warn'
                ? 'bg-amber-950/50 border-amber-700/60 text-amber-200'
                : 'bg-red-950/50 border-red-800/60 text-red-200'
          }`}
        >
          <p className="text-[11px] leading-snug">{bountyActionBanner.text}</p>
          <button type="button" onClick={onClearBanner} className="text-[10px] opacity-70 ml-2">
            ✕
          </button>
        </div>
      )}

      {/* Content: Available Tab vs Active Tab */}
      <div className="flex-1 overflow-y-auto custom-scrollbar pr-0.5 min-h-0 space-y-2">
        {bountySubTab === 'available' ? (() => {
          const selectedFactionObj =
            selectedFactionFilter !== 'all'
              ? factionsList.find((f) => (f.faction_id || f.name) === selectedFactionFilter)
              : null;
          const isSelectedLocked = Boolean(
            selectedFactionObj && selectedFactionObj.bounty_board_eligible === false
          );
          return availableBounties.length === 0 ? (
            <div className="text-center py-12 px-4 text-gray-500 border border-dashed border-neutral-800 rounded-2xl space-y-3">
              <ShieldAlert size={28} className="mx-auto opacity-30 text-rose-400" />
              <div>
                <p className="text-xs text-gray-300 font-semibold">
                  {isSelectedLocked
                    ? t('phone.bounties.locked_faction_title', 'Access restricted for this faction board')
                    : selectedFactionFilter !== 'all'
                      ? 'No faction tasks currently posted'
                      : 'Bulletin is quiet right now'}
                </p>
                <p className="text-[10px] text-gray-500 mt-0.5">
                  {isSelectedLocked
                    ? t(
                        'phone.bounties.locked_faction_desc',
                        'Outlaw operatives are blacklisted from Bureau contracts; private internal boards are restricted to enlisted members.'
                      )
                    : selectedFactionFilter !== 'all'
                      ? 'Request contracts directly from this faction.'
                      : 'Generate live procedural requests for your campus.'}
                </p>
              </div>
              <button
                type="button"
                disabled={generatingBounties || isSelectedLocked}
                onClick={() => onRefreshBounties(selectedFactionFilter !== 'all' ? selectedFactionFilter : null)}
                className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all border ${
                  isSelectedLocked
                    ? 'bg-neutral-900 text-gray-600 border-neutral-800 cursor-not-allowed'
                    : 'bg-rose-600/30 hover:bg-rose-600/50 text-rose-200 border-rose-500/40 active:scale-95 cursor-pointer'
                }`}
              >
                {isSelectedLocked
                  ? t('phone.bounties.locked_faction_btn', '🔒 Board Restricted')
                  : generatingBounties
                    ? 'Generating...'
                    : selectedFactionFilter !== 'all'
                      ? 'Request Faction Tasks'
                      : 'Generate New Requests'}
              </button>
            </div>
          ) : (
            availableBounties.map((bounty, idx) => {
              const isLocked = bounty.anomalous_eligible === false;
              return (
                <div
                  key={bounty.quest_id || idx}
                  className={`border rounded-xl p-3 space-y-2 ${
                    isLocked
                      ? 'bg-neutral-900/60 border-rose-900/50 opacity-85'
                      : 'bg-neutral-900/80 border-neutral-800'
                  }`}
                >
                  <div className="flex justify-between items-start gap-2">
                    <div className="min-w-0">
                      <span className="font-bold text-xs text-gray-100 block">
                        {cleanProseLocations(bounty.title)}
                      </span>
                      <span className="text-[10px] font-mono text-rose-400 block mt-0.5">
                        {bounty.quest_type || 'Campus Request'}
                        {bounty.target_name ? ` • Target: ${bounty.target_name}` : ''}
                      </span>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      {isLocked && (
                        <span
                          className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-rose-950/70 text-rose-300 border border-rose-700/60"
                          title={
                            bounty.anomalous_lock_reason ||
                            t('phone.bounties.locked_faction_btn', '🔒 Board Restricted')
                          }
                        >
                          🔒
                        </span>
                      )}
                      {bounty.status && (
                        <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-neutral-800 text-gray-400 border border-neutral-700">
                          {bounty.status}
                        </span>
                      )}
                    </div>
                  </div>

                  <p className="text-[11px] text-gray-300 leading-snug">
                    {cleanProseLocations(bounty.objective || bounty.description)}
                  </p>

                  {isLocked && bounty.anomalous_lock_reason && (
                    <div className="bg-rose-950/35 border border-rose-700/50 rounded-lg px-2.5 py-1.5 text-[10px] text-rose-300 leading-snug">
                      🔒 {bounty.anomalous_lock_reason}
                    </div>
                  )}

                  {/* Rewards row */}
                  <div className="flex flex-wrap items-center gap-1.5 text-[10px] font-mono tabular-nums pt-0.5">
                    {bounty.reward_gold > 0 && (
                      <span className="px-1.5 py-0.5 rounded bg-amber-950/40 text-amber-300 border border-amber-800/40">
                        {formatScenarioCurrency(bounty.reward_gold, scenario)}
                      </span>
                    )}
                    {bounty.reward_xp > 0 && (
                      <span className="px-1.5 py-0.5 rounded bg-purple-950/40 text-purple-300 border border-purple-800/40">
                        ⭐ {bounty.reward_xp} XP
                      </span>
                    )}
                    {bounty.reward_item && (
                      <span className="px-1.5 py-0.5 rounded bg-cyan-950/40 text-cyan-300 border border-cyan-800/40 truncate max-w-[150px]">
                        🎁 {bounty.reward_item}
                      </span>
                    )}
                    {bounty.faction_rep_reward > 0 && (
                      <span className="px-1.5 py-0.5 rounded bg-emerald-950/40 text-emerald-300 border border-emerald-800/40">
                        🏆 +{bounty.faction_rep_reward} Rep
                      </span>
                    )}
                  </div>

                  {/* Action: Accept in phone */}
                  <div className="flex justify-end pt-1">
                    <button
                      type="button"
                      disabled={isLocked || isBusy}
                      onClick={() => onAcceptBounty(bounty.quest_id, bounty.title)}
                      title={
                        isLocked
                          ? bounty.anomalous_lock_reason ||
                            t('phone.bounties.locked_faction_btn', '🔒 Board Restricted')
                          : undefined
                      }
                      className={`px-3 py-1 rounded-lg text-[11px] font-bold border transition-all ${
                        isLocked || isBusy
                          ? 'bg-neutral-900/60 text-gray-500 border-neutral-700/60 opacity-50 cursor-not-allowed'
                          : 'bg-rose-600/30 hover:bg-rose-500/40 text-rose-200 border-rose-500/50 active:scale-95 cursor-pointer'
                      }`}
                    >
                      {isLocked
                        ? t('phone.bounties.locked_faction_btn', '🔒 Board Restricted')
                        : busyBountyId === bounty.quest_id
                          ? t('common.loading', 'Loading...')
                          : 'Accept Request'}
                    </button>
                  </div>
                </div>
              );
            })
          );
        })() : (
          /* Active Tasks Tab */
          activeBounties.length === 0 ? (
            <div className="text-center py-12 px-4 text-gray-500 border border-dashed border-neutral-800 rounded-2xl space-y-1">
              <ShieldAlert size={28} className="mx-auto opacity-30 text-gray-500" />
              <p className="text-xs text-gray-300 font-semibold">
                {t('phone.planner.no_active_tasks', 'No active tasks in progress')}
              </p>
              <p className="text-[10px] text-gray-500">
                Switch to the Available tab and accept requests to track them here.
              </p>
            </div>
          ) : (
            activeBounties.map((quest, idx) => (
              <div
                key={quest.quest_id || idx}
                className="bg-neutral-900/90 border border-amber-700/40 rounded-xl p-3 space-y-2"
              >
                <div className="flex justify-between items-start gap-2">
                  <div>
                    <span className="font-bold text-xs text-amber-200 block">
                      {cleanProseLocations(quest.title)}
                    </span>
                    <span className="text-[10px] font-mono text-gray-400 block mt-0.5">
                      {quest.quest_type}
                      {quest.target_name ? ` • Target: ${quest.target_name}` : ''}
                    </span>
                  </div>
                  <span className="text-[9px] font-mono px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40 font-bold shrink-0">
                    ⚡ Active
                  </span>
                </div>

                <p className="text-[11px] text-gray-300 leading-snug">
                  {cleanProseLocations(quest.objective)}
                </p>

                {quest.progress && (
                  <div className="bg-neutral-950/80 p-1.5 rounded-lg border border-neutral-800 text-[10px] font-mono text-cyan-300 flex items-center justify-between">
                    <span>Progress: {quest.progress}</span>
                  </div>
                )}

                <div className="flex items-center justify-between pt-1">
                  <div className="flex items-center gap-1.5 text-[10px] font-mono tabular-nums text-gray-400">
                    {quest.reward_gold > 0 && (
                      <span>{formatScenarioCurrency(quest.reward_gold, scenario)}</span>
                    )}
                    {quest.reward_xp > 0 && <span>⭐ {quest.reward_xp} XP</span>}
                  </div>
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={() => onAbandonBounty(quest.quest_id, quest.title)}
                    className="px-2.5 py-1 rounded-lg text-[10px] font-semibold text-gray-400 hover:text-red-300 hover:bg-red-950/40 border border-neutral-800 hover:border-red-800/60 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Abandon Task
                  </button>
                </div>
              </div>
            ))
          )
        )}
      </div>
    </div>
  );
};

export default PhoneBountiesApp;
