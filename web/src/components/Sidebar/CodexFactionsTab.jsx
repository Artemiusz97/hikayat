import {
  BedDouble,
  ChevronDown,
  ChevronRight,
  Crown,
  Flag,
  MapPin,
  ShoppingBag,
  Swords,
} from 'lucide-react';
import { formatCleanLocation } from '../../utils/locationFormat';

export const getFactionCategoryBadge = (faction, t) => {
  const tag = faction?.category_tag || {};
  const tagKey = tag.key || (faction?.is_school_club ? 'school_club' : (faction?.category || 'faction'));
  const isSchool = Boolean(faction?.is_school_club || tag.is_school_club || tag.domain === 'school');

  switch (tagKey) {
    case 'student_council':
      return {
        label: t('codex.tag_student_council', 'Student Council'),
        icon: '🏛️',
        style: 'bg-purple-950/70 text-purple-300 border-purple-700/50',
      };
    case 'athletics':
      return {
        label: t('codex.tag_athletics', 'Varsity Athletics'),
        icon: '🏆',
        style: 'bg-amber-950/70 text-amber-300 border-amber-700/50',
      };
    case 'delinquents':
      return {
        label: t('codex.tag_delinquents', 'Campus Rebels'),
        icon: '🔥',
        style: 'bg-red-950/70 text-red-300 border-red-700/50',
      };
    case 'campus_circle':
      return {
        label: t('codex.tag_campus_circle', 'Campus Circle'),
        icon: '✨',
        style: 'bg-pink-950/70 text-pink-300 border-pink-700/50',
      };
    case 'discipline':
      return {
        label: t('codex.tag_discipline', 'Disciplinary Committee'),
        icon: '⚖️',
        style: 'bg-blue-950/70 text-blue-300 border-blue-700/50',
      };
    case 'school_club':
      return {
        label: t('codex.tag_school_club', 'School Club'),
        icon: '🎓',
        style: 'bg-cyan-950/70 text-cyan-300 border-cyan-700/50',
      };
    case 'public_agency':
      return {
        label: t('codex.tag_public_agency', 'Public Agency'),
        icon: '🏢',
        style: 'bg-blue-950/70 text-blue-300 border-blue-700/50',
      };
    case 'private_agency':
      return {
        label: t('codex.tag_private_agency', 'Private Agency'),
        icon: '🛡️',
        style: 'bg-indigo-950/70 text-indigo-300 border-indigo-700/50',
      };
    case 'monastic_order':
      return {
        label: t('codex.tag_monastic_order', 'Monastic Order'),
        icon: '⛩️',
        style: 'bg-amber-950/70 text-amber-300 border-amber-700/50',
      };
    case 'spirit_court':
      return {
        label: t('spirit_realm.spirit_court_badge', 'Spirit Court'),
        icon: '⛩️',
        style: 'bg-amber-950/70 text-amber-200 border-amber-600/60',
      };
    case 'cult':
      return {
        label: t('codex.tag_cult', 'Occult Cult'),
        icon: '👁️',
        style: 'bg-purple-950/70 text-purple-300 border-purple-700/50',
      };
    case 'syndicate':
      return {
        label: t('codex.tag_syndicate', 'Syndicate'),
        icon: '🗡️',
        style: 'bg-slate-900/80 text-slate-300 border-slate-700/60',
      };
    case 'guild':
      return {
        label: t('codex.tag_guild', 'Guild'),
        icon: '⚔️',
        style: 'bg-emerald-950/70 text-emerald-300 border-emerald-700/50',
      };
    case 'order':
      return {
        label: t('codex.tag_order', 'Order'),
        icon: '🛡️',
        style: 'bg-blue-950/70 text-blue-300 border-blue-700/50',
      };
    default:
      if (isSchool) {
        return {
          label: t('codex.tag_school_club', 'School Club'),
          icon: '🎓',
          style: 'bg-cyan-950/70 text-cyan-300 border-cyan-700/50',
        };
      }
      return {
        label: t('codex.tag_faction', 'Faction'),
        icon: '🚩',
        style: 'bg-slate-900/70 text-gray-300 border-slate-700/50',
      };
  }
};

export const getReputationTier = (score, t = null) => {
  let tierKey = 'hostile_rival';
  let fallback = 'Hostile / Rival';
  let color = 'text-red-400';
  let bg = 'bg-red-500';

  if (score >= 81) {
    tierKey = 'exalted'; fallback = 'Exalted'; color = 'text-emerald-300'; bg = 'bg-emerald-400';
  } else if (score >= 51) {
    tierKey = 'honored'; fallback = 'Honored'; color = 'text-emerald-400'; bg = 'bg-emerald-500';
  } else if (score >= 21) {
    tierKey = 'friendly'; fallback = 'Friendly'; color = 'text-blue-400'; bg = 'bg-blue-500';
  } else if (score >= 1) {
    tierKey = 'liked'; fallback = 'Liked'; color = 'text-cyan-400'; bg = 'bg-cyan-500';
  } else if (score >= -10) {
    tierKey = 'neutral'; fallback = 'Neutral'; color = 'text-gray-400'; bg = 'bg-gray-500';
  } else if (score >= -40) {
    tierKey = 'unfavorable'; fallback = 'Unfavorable'; color = 'text-amber-400'; bg = 'bg-amber-500';
  }

  const label = t ? t(`codex.rep_tiers.${tierKey}`, fallback) : fallback;
  return { label, color, bg };
};

const CodexFactionsTab = ({
  factions,
  filteredFactions,
  hasSchoolFactions,
  hasRegularFactions,
  factionDomainFilter,
  onChangeFactionDomainFilter,
  expandedFaction,
  onToggleFaction,
  session,
  agentDossier,
  factionBusy,
  onFactionOp,
  calibId,
  calibCost,
  calAttr,
  setCalAttr,
  calArch,
  setCalArch,
  calMed,
  setCalMed,
  t,
}) => (
  <div className="space-y-2.5">
    {hasSchoolFactions && hasRegularFactions && (
      <div className="flex items-center gap-1.5 pb-1">
        <button
          type="button"
          onClick={() => onChangeFactionDomainFilter('all')}
          className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
            factionDomainFilter === 'all'
              ? 'bg-fantasy-accent text-black font-bold'
              : 'bg-black/50 text-gray-400 hover:text-gray-200 border border-fantasy-border/40'
          }`}
        >
          {t('codex.filter_all_factions', 'All')} ({factions.length})
        </button>
        <button
          type="button"
          onClick={() => onChangeFactionDomainFilter('school')}
          className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors flex items-center gap-1 ${
            factionDomainFilter === 'school'
              ? 'bg-cyan-500 text-black font-bold'
              : 'bg-black/50 text-cyan-400 hover:text-cyan-300 border border-cyan-800/40'
          }`}
        >
          <span>🎓</span>
          <span>{t('codex.filter_school_clubs', 'School Clubs')}</span>
        </button>
        <button
          type="button"
          onClick={() => onChangeFactionDomainFilter('regular')}
          className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors flex items-center gap-1 ${
            factionDomainFilter === 'regular'
              ? 'bg-indigo-500 text-white font-bold'
              : 'bg-black/50 text-indigo-400 hover:text-indigo-300 border border-indigo-800/40'
          }`}
        >
          <span>🏢</span>
          <span>{t('codex.filter_regular_factions', 'Agencies & Factions')}</span>
        </button>
      </div>
    )}

    {filteredFactions.length === 0 ? (
      <div className="text-center py-8 text-gray-500 border border-dashed border-fantasy-border/50 rounded-md">
        <Flag size={24} className="mx-auto mb-1.5 opacity-40" />
        <p className="text-xs">{t('codex.factions_empty', 'No factions discovered yet.')}</p>
      </div>
    ) : (
      filteredFactions.map(faction => {
        const fid = faction.faction_id || faction.name;
        const factionCategoryTag = getFactionCategoryBadge(faction, t);
        const rep = faction.reputation ?? faction.reputation_score ?? 0;
        const repTier = getReputationTier(rep, t);
        const isExpanded = expandedFaction === fid;
        const isMember = Boolean(faction.is_member);
        const playerRank = Number(faction.player_rank || 0);
        const eligibleRank = Number(faction.eligible_rank || 0);
        const isAnomScenario = String(session?.scenario || '').toLowerCase().includes('anomalous');
        const isSpiritCourt = Boolean(
          faction.category === 'spirit_court' ||
          faction.diplomatic_stance === 'spirit_court'
        );
        const isOutlaw = Boolean(faction.is_outlaw || faction.diplomatic_stance === 'outlaw');
        const isAnomMainFaction = isAnomScenario && !faction.is_school_club && !isSpiritCourt;
        const promoTiers = Array.isArray(faction.promotion_tiers) ? faction.promotion_tiers : [];
        const canPromote = !isSpiritCourt && isMember && eligibleRank > playerRank && playerRank < 4;
        const canRest = isSpiritCourt ? rep >= 1 : (isAnomMainFaction ? isMember : rep >= 1);
        const qmBlocked = faction.quartermaster_eligible === false;
        const bountyBlocked = faction.bounty_board_eligible === false;
        const roster = Array.isArray(faction.leadership_roster) ? faction.leadership_roster : [];
        const hierarchy = Array.isArray(faction.hierarchy) ? faction.hierarchy : [];
        const activePerks = Array.isArray(faction.active_perks) ? faction.active_perks : [];
        const rivalFactions = Array.isArray(faction.rival_faction_ids) ? faction.rival_faction_ids : [];

        return (
          <div
            key={fid}
            className="bg-black/50 border border-fantasy-border/60 hover:border-fantasy-border rounded-lg p-3 space-y-2.5 transition-all"
          >
            <div
              onClick={() => onToggleFaction(isExpanded ? null : fid)}
              className="flex justify-between items-start gap-1 cursor-pointer select-none"
            >
              <div className="min-w-0">
                <h4 className="font-semibold text-xs text-gray-200 flex items-center gap-1.5 flex-wrap">
                  <Flag size={13} className="text-fantasy-accent shrink-0" />
                  <span>{faction.name || faction.faction_id}</span>
                  {factionCategoryTag && (
                    <span className={`text-[9.5px] px-1.5 py-0.5 rounded font-medium border flex items-center gap-1 shrink-0 ${factionCategoryTag.style}`}>
                      <span>{factionCategoryTag.icon}</span>
                      <span>{factionCategoryTag.label}</span>
                    </span>
                  )}
                  {isOutlaw && (
                    <span className="text-[9.5px] px-1.5 py-0.5 rounded font-bold border bg-rose-950/70 text-rose-300 border-rose-700/60 shrink-0 uppercase">
                      {t('codex.outlaw_badge', 'Outlaw')}
                    </span>
                  )}
                  {isMember && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40 font-bold uppercase">
                      Rank {playerRank || 1} {faction.player_title ? `• ${faction.player_title}` : t('codex.member', 'Member')}
                    </span>
                  )}
                </h4>
                {(faction.hq_display_name || faction.hq_location_id) && (
                  <span className="text-[10px] text-gray-500 flex items-center gap-1 mt-0.5">
                    <MapPin size={10} />
                    <span>HQ: {faction.hq_display_name || formatCleanLocation(faction.hq_location_id)}</span>
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1 text-right shrink-0">
                <div>
                  <span className={`text-[10px] font-bold block ${repTier.color}`}>
                    {faction.tier?.name || repTier.label}
                  </span>
                  <span className="font-mono text-xs font-semibold text-gray-300">
                    {rep > 0 ? `+${rep}` : rep} Rep
                  </span>
                </div>
                {isExpanded ? <ChevronDown size={14} className="text-gray-500" /> : <ChevronRight size={14} className="text-gray-500" />}
              </div>
            </div>

            {(faction.description || faction.notes) && (
              <p className="text-[11px] text-gray-400 leading-snug">{faction.description || faction.notes}</p>
            )}

            <div className="h-1.5 w-full bg-black/80 rounded-full overflow-hidden border border-fantasy-border/40">
              <div
                className={`h-full ${repTier.bg} transition-all duration-300`}
                style={{ width: `${Math.max(5, Math.min(100, ((rep + 100) / 200) * 100))}%` }}
              />
            </div>

            {isExpanded && (
              <div className="pt-2 border-t border-fantasy-border/40 space-y-3 text-xs">
                {(activePerks.length > 0 || rivalFactions.length > 0) && (
                  <div className="space-y-1.5 bg-black/40 p-2 rounded border border-fantasy-border/40">
                    {activePerks.length > 0 && (
                      <div>
                        <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider block mb-1">
                          ✨ {t('codex.active_faction_perks', 'Active Faction Perks')}
                        </span>
                        <div className="flex flex-wrap gap-1">
                          {activePerks.map((perk, idx) => (
                            <span key={idx} className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-950/50 text-emerald-200 border border-emerald-700/40">
                              {typeof perk === 'string' ? perk : (perk.name || perk.description)}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                    {rivalFactions.length > 0 && (
                      <div>
                        <span className="text-[10px] font-bold text-red-400 uppercase tracking-wider block mb-0.5">
                          ⚔️ {t('codex.rival_factions', 'Rival Factions')}
                        </span>
                        <span className="text-[11px] text-gray-300">{rivalFactions.join(', ')}</span>
                      </div>
                    )}
                  </div>
                )}

                {isAnomMainFaction && promoTiers.length > 0 && (
                  <div className="space-y-1.5 bg-black/40 p-2 rounded border border-fantasy-border/40">
                    <div className="flex items-center justify-between text-[10px] font-bold text-cyan-300 uppercase tracking-wider">
                      <span>🎖️ {t('codex.promotion_ladder', '5-Tier Operative Ladder')}</span>
                      {isMember && (
                        <span className="font-mono text-amber-300">
                          {Number(agentDossier?.promotion_rep || 0)}/100 Rep • T{Number(agentDossier?.promotion_tier || playerRank || 1)}
                        </span>
                      )}
                    </div>
                    <div className="space-y-1">
                      {promoTiers.map((pt) => {
                        const isCurTier = isMember && Number(agentDossier?.promotion_tier || playerRank || 0) === Number(pt.tier);
                        return (
                          <div
                            key={pt.tier}
                            className={`flex items-center justify-between px-1.5 py-1 rounded border text-[10.5px] ${
                              isCurTier
                                ? 'bg-amber-950/35 border-amber-500/50 text-amber-200 font-semibold'
                                : 'bg-black/50 border-fantasy-border/30 text-gray-300'
                            }`}
                          >
                            <span>T{pt.tier} • {pt.title}</span>
                            <span className="font-mono text-[10px] text-gray-500">{pt.min_rep ?? pt.rep_required ?? 0} Rep</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {roster.length > 0 && (
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-[10px] font-bold text-gray-400 uppercase tracking-wider">
                      <span className="flex items-center gap-1">
                        <Crown size={11} className="text-amber-400" />
                        <span>{t('codex.leadership_hierarchy', 'Leadership Hierarchy')}</span>
                      </span>
                      <span className="font-mono text-gray-500">{t('codex.ranks_range', 'Ranks 1–4')}</span>
                    </div>
                    <div className="space-y-1 bg-black/40 p-2 rounded border border-fantasy-border/40">
                      {[...roster].sort((a, b) => (b.rank || 0) - (a.rank || 0)).map((slot) => {
                        const hTier = hierarchy.find(h => h.rank === slot.rank);
                        const reqRep = hTier?.required_rep ?? (slot.rank === 4 ? 85 : slot.rank === 3 ? 60 : slot.rank === 2 ? 30 : 1);
                        const isLeader = slot.rank === 4 || hTier?.is_leader;
                        return (
                          <div
                            key={slot.rank}
                            className={`flex items-center justify-between p-1.5 rounded border text-[11px] ${
                              slot.is_player
                                ? 'bg-amber-950/30 border-amber-600/50 text-amber-200'
                                : 'bg-black/50 border-fantasy-border/30 text-gray-300'
                            }`}
                          >
                            <div className="min-w-0">
                              <div className="flex items-center gap-1.5">
                                <span className="font-mono text-[10px] px-1 rounded bg-black/60 text-fantasy-accent border border-fantasy-border/50">
                                  R{slot.rank}
                                </span>
                                <span className="font-semibold truncate">{slot.title}</span>
                                {isLeader && <Crown size={11} className="text-amber-400 shrink-0" />}
                              </div>
                              <span className="text-[10px] text-gray-400 block mt-0.5">
                                {t('codex.holder', 'Holder')}: <strong className="text-gray-200">{slot.is_vacant ? t('codex.vacant', 'Vacant') : slot.name}</strong>
                                {slot.is_player && (
                                  <span className="ml-1.5 text-[9px] px-1 bg-amber-500/20 text-amber-300 rounded border border-amber-500/40 font-bold uppercase">
                                    You
                                  </span>
                                )}
                              </span>
                            </div>
                            <span className="text-[10px] font-mono text-gray-500 shrink-0">
                              Req +{reqRep}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                <div className="space-y-1.5">
                  <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider block">
                    {t('codex.faction_hq_ops', 'Faction Headquarters Operations')}
                  </span>
                  {isSpiritCourt && (
                    <div className="space-y-1.5 mb-2">
                      <p className="text-[10.5px] text-amber-200/85 bg-amber-950/25 border border-amber-800/40 rounded px-2 py-1.5 leading-snug">
                        ⛩️ {t('spirit_realm.spirit_court_autonomous_note', 'Autonomous Spirit Court — earn standing via deeds, commissions & tokens instead of enlistment.')}
                      </p>
                      {faction.sworn_ally_summon && (
                        <div className={`p-2 rounded border text-[11px] space-y-1 ${
                          faction.sworn_ally_active
                            ? 'bg-emerald-950/35 border-emerald-600/60 text-emerald-100'
                            : 'bg-black/45 border-fantasy-border/40 text-gray-300'
                        }`}>
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-bold text-[10.5px] uppercase tracking-wider flex items-center gap-1">
                              <span>{faction.sworn_ally_summon.emoji || '⛩️'}</span>
                              <span>{t('spirit_realm.sworn_ally_badge', 'Sworn Ally')} (90+)</span>
                            </span>
                            <span className={`text-[9.5px] px-1.5 py-0.5 rounded font-bold uppercase ${
                              faction.sworn_ally_active
                                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                                : 'bg-black/50 text-gray-400 border border-fantasy-border/40'
                            }`}>
                              {faction.sworn_ally_active ? 'Active' : `${Math.max(0, rep)}/90 Rep`}
                            </span>
                          </div>
                          {faction.sworn_ally_active ? (
                            <>
                              <div className="text-[11px]">
                                <strong className="text-amber-300">{t('spirit_realm.sworn_ally_summon_label', '90+ Native Summon')}:</strong>{' '}
                                {faction.sworn_ally_summon.name} ({faction.sworn_ally_summon.duration_turns}T • {faction.sworn_ally_summon.mp_cost} MP)
                              </div>
                              {faction.sworn_ally_stat_bonuses && Object.keys(faction.sworn_ally_stat_bonuses).length > 0 && (
                                <div className="flex flex-wrap items-center gap-1 pt-0.5">
                                  <span className="text-[10px] text-emerald-300 font-semibold mr-1">
                                    {t('spirit_realm.sworn_ally_stat_label', '90+ Sovereign Blessing')}:
                                  </span>
                                  {Object.entries(faction.sworn_ally_stat_bonuses).map(([statK, statV]) => (
                                    <span key={statK} className="text-[9.5px] font-mono px-1.5 py-0.5 rounded bg-black/50 text-emerald-200 border border-emerald-700/40">
                                      +{statV} {statK}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </>
                          ) : (
                            <p className="text-[10px] text-gray-400 leading-snug">
                              {t('spirit_realm.sworn_ally_tier_hint', "Reach +90 standing to unlock this court's stackable Sovereign Blessing & 3-turn combat summon.")}
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                  <div className="grid grid-cols-2 gap-1.5">
                    {!isSpiritCourt && (
                      <button
                        disabled={Boolean(factionBusy)}
                        onClick={() => onFactionOp(faction.faction_id, isMember ? 'leave' : 'join')}
                        className={`flex items-center justify-center gap-1.5 py-1.5 px-2 rounded text-[11px] font-bold border transition-all ${
                          isMember
                            ? 'bg-red-950/40 hover:bg-red-900/50 border-red-800/60 text-red-300'
                            : 'bg-emerald-950/40 hover:bg-emerald-900/50 border-emerald-700/60 text-emerald-300'
                        }`}
                      >
                        <Flag size={12} />
                        <span>{isMember ? t('codex.leave_faction', 'Leave Faction') : t('codex.join_faction', 'Pledge / Join')}</span>
                      </button>
                    )}

                    <button
                      disabled={Boolean(factionBusy) || !canRest}
                      onClick={() => onFactionOp(faction.faction_id, 'rest')}
                      title={
                        canRest
                          ? 'Recover full HP & MP at Faction Safehouse'
                          : isAnomMainFaction
                            ? t('codex.rest_members_only', 'Restricted to enlisted operatives of this HQ')
                            : 'Requires Liked standing (+1 Rep)'
                      }
                      className={`flex items-center justify-center gap-1.5 py-1.5 px-2 rounded text-[11px] font-bold border transition-all ${
                        canRest
                          ? 'bg-cyan-950/40 hover:bg-cyan-900/50 border-cyan-700/60 text-cyan-300'
                          : 'bg-black/40 border-neutral-800 text-gray-600 cursor-not-allowed'
                      }`}
                    >
                      <BedDouble size={12} />
                      <span>{t('codex.safehouse_rest', 'Safehouse Rest')}</span>
                    </button>

                    {!isSpiritCourt && (
                      <button
                        disabled={Boolean(factionBusy) || qmBlocked}
                        onClick={() => onFactionOp(faction.faction_id, 'quartermaster')}
                        title={qmBlocked ? t('codex.qm_locked_tip', 'Locked: Outlaws are blacklisted at Bureau HQ; specialized faction armories are members-only.') : undefined}
                        className={`flex items-center justify-center gap-1.5 py-1.5 px-2 rounded text-[11px] font-bold border transition-all ${
                          qmBlocked
                            ? 'bg-black/40 border-neutral-800 text-gray-600 cursor-not-allowed'
                            : 'bg-amber-950/40 hover:bg-amber-900/50 border-amber-700/60 text-amber-300'
                        }`}
                      >
                        <ShoppingBag size={12} />
                        <span>{qmBlocked ? `🔒 ${t('codex.quartermaster', 'Quartermaster')}` : t('codex.quartermaster', 'Quartermaster')}</span>
                      </button>
                    )}

                    {!isSpiritCourt && (
                      <button
                        disabled={Boolean(factionBusy) || isAnomMainFaction || !canPromote}
                        onClick={() => onFactionOp(faction.faction_id, 'promote')}
                        title={
                          isAnomMainFaction
                            ? t('codex.auto_promote_tip', 'Advances automatically at 20 / 45 / 70 / 90 Rep via Bounties and Dispatches')
                            : !isMember
                              ? 'Join faction first'
                              : canPromote
                                ? `Challenge for Rank ${playerRank + 1}!`
                                : 'Earn more Faction Reputation to unlock the next rank'
                        }
                        className={`flex items-center justify-center gap-1.5 py-1.5 px-2 rounded text-[11px] font-bold border transition-all ${
                          !isAnomMainFaction && canPromote
                            ? 'bg-purple-950/50 hover:bg-purple-900/60 border-purple-600/60 text-purple-200 animate-pulse'
                            : 'bg-black/40 border-neutral-800 text-gray-600 cursor-not-allowed'
                        }`}
                      >
                        <Swords size={12} />
                        <span>
                          {isAnomMainFaction
                            ? t('codex.auto_promote_btn', 'Auto-Promotes (Rep)')
                            : canPromote ? `Promote (R${playerRank + 1})` : 'Promotion Locked'}
                        </span>
                      </button>
                    )}

                    <button
                      disabled={Boolean(factionBusy) || bountyBlocked}
                      onClick={() => onFactionOp(faction.faction_id, 'bounty')}
                      title={bountyBlocked ? t('codex.bounty_locked_tip', 'Locked: Outlaws are blacklisted at Bureau contracts; internal dispatches are members-only.') : undefined}
                      className={`col-span-2 flex items-center justify-center gap-1.5 py-1.5 px-2 rounded text-[11px] font-bold border transition-all ${
                        bountyBlocked
                          ? 'bg-black/40 border-neutral-800 text-gray-600 cursor-not-allowed'
                          : 'bg-indigo-950/40 hover:bg-indigo-900/50 border-indigo-700/60 text-indigo-300'
                      }`}
                    >
                      <span>{bountyBlocked ? `🔒 ${t('codex.faction_bounties', '📋 Faction Bounties')}` : t('codex.faction_bounties', '📋 Faction Bounties')}</span>
                    </button>
                  </div>

                  {isMember && Number(agentDossier?.promotion_tier || playerRank || 0) >= 4 && String(session?.scenario || '').toLowerCase().includes('anomalous') && (
                    <div className="mt-2 p-2.5 rounded-lg bg-cyan-950/20 border border-cyan-800/50 space-y-2">
                      <div>
                        <span className="text-[10.5px] font-bold uppercase tracking-wider text-cyan-300 block">
                          🧬 {t('awakened.calibration_title', 'HQ Telemetry Calibration')}
                        </span>
                        <p id={`${calibId}-${faction.faction_id}-desc`} className="text-[10px] text-gray-400 leading-snug mt-0.5">
                          {t('awakened.calibration_desc', {
                            cost: calibCost,
                            defaultValue: `Tier 4+ Senior Operative privilege: Re-attune your 3-axis Resonance (${calibCost} + 1x Hume Core, max 1/arc).`,
                          })}
                        </p>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-1.5">
                        <div>
                          <label htmlFor={`${calibId}-${faction.faction_id}-attr`} className="block text-[9.5px] uppercase font-bold text-gray-400 mb-0.5">
                            {t('awakened.attribute_label', 'Attribute')}
                          </label>
                          <select
                            id={`${calibId}-${faction.faction_id}-attr`}
                            aria-describedby={`${calibId}-${faction.faction_id}-desc`}
                            value={calAttr}
                            onChange={(e) => setCalAttr(e.target.value)}
                            className="w-full bg-black/70 border border-cyan-800/60 rounded p-1 text-[10.5px] text-gray-200"
                          >
                            {['fire', 'water', 'wind', 'earth', 'ice', 'electric', 'bio', 'physical', 'aether'].map((ak) => (
                              <option key={ak} value={ak}>{t(`awakened.attrs.${ak}`, ak.toUpperCase())}</option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label htmlFor={`${calibId}-${faction.faction_id}-arch`} className="block text-[9.5px] uppercase font-bold text-gray-400 mb-0.5">
                            {t('awakened.archetype_label', 'Archetype')}
                          </label>
                          <select
                            id={`${calibId}-${faction.faction_id}-arch`}
                            aria-describedby={`${calibId}-${faction.faction_id}-desc`}
                            value={calArch}
                            onChange={(e) => setCalArch(e.target.value)}
                            className="w-full bg-black/70 border border-cyan-800/60 rounded p-1 text-[10.5px] text-gray-200"
                          >
                            {['vanguard', 'catalyst', 'breaker', 'warden'].map((rk) => (
                              <option key={rk} value={rk}>{t(`awakened.archetypes.${rk}`, rk.toUpperCase())}</option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label htmlFor={`${calibId}-${faction.faction_id}-med`} className="block text-[9.5px] uppercase font-bold text-gray-400 mb-0.5">
                            {t('awakened.medium_label', 'Medium')}
                          </label>
                          <select
                            id={`${calibId}-${faction.faction_id}-med`}
                            aria-describedby={`${calibId}-${faction.faction_id}-desc`}
                            value={calMed}
                            onChange={(e) => setCalMed(e.target.value)}
                            className="w-full bg-black/70 border border-cyan-800/60 rounded p-1 text-[10.5px] text-gray-200"
                          >
                            {['direct_manifestation', 'ordnance_imbuement', 'somatic_overdrive', 'autonomous_construct'].map((mk) => (
                              <option key={mk} value={mk}>{t(`awakened.mediums.${mk}`, mk)}</option>
                            ))}
                          </select>
                        </div>
                      </div>
                      <button
                        type="button"
                        disabled={Boolean(factionBusy)}
                        onClick={() => onFactionOp(faction.faction_id, 'calibrate', {
                          attribute: calAttr,
                          combat_archetype: calArch,
                          ability_medium: calMed,
                        })}
                        className="w-full py-1.5 px-2 rounded text-[11px] font-bold border bg-cyan-950/60 hover:bg-cyan-900/70 border-cyan-500/60 text-cyan-200 transition-all disabled:opacity-50"
                      >
                        🧬 {t('awakened.calibration_btn', {
                          cost: calibCost,
                          defaultValue: `Calibrate Resonance (${calibCost} + 1x Hume Core)`,
                        })}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        );
      })
    )}
  </div>
);

export default CodexFactionsTab;
