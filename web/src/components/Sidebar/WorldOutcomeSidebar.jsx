import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Sparkles,
  Swords,
  ScrollText,
  Heart,
  ShieldAlert,
  Coins,
  Gift,
  ChevronDown,
  History,
  Users,
} from 'lucide-react';
import { getOutcomeTierTheme } from '../StoryFeed/HistoryCard';
import { StatusEffectBadge } from './CharacterSheet';
import { getRelationshipTier } from './CodexPanel';
import { resolveNpcDemographics } from '../../utils/npcDemographics';
import { isAnomalousNpc } from '../../utils/sceneTargets';
import { formatScenarioCurrency } from '../../utils/currency';
import {
  AcrylicPanel,
  CollapsibleSection,
  MotionButton,
} from '../Common/MotionPrimitives';

export const formatSocialFeedbackPill = (pill, t) => {
  if (!pill) return '';
  if (typeof pill === 'string') return pill;
  const key = pill.key || '';
  const detail = pill.detail ? String(pill.detail).trim() : '';
  if (key && typeof t === 'function') {
    const base = t(`social.pills.${key}`, pill.label || key);
    if (detail && !String(base).includes(detail)) {
      return `${base}: ${detail}`;
    }
    return String(base);
  }
  return String(pill.label || detail || key || '');
};

const parseClues = (raw) => {
  if (!raw) return [];
  if (Array.isArray(raw)) {
    return raw
      .map((c) =>
        String(typeof c === 'string' ? c : c?.text || c?.lead || '')
          .replace(/^[\s•*\-\d.)]+/, '')
          .trim()
      )
      .filter(Boolean);
  }
  return String(raw)
    .split(/\r?\n/)
    .map((line) => line.replace(/^[\s•*\-\d.)]+/, '').trim())
    .filter((line) => line.length > 0);
};

const normalizeClue = (str) => {
  return String(str || '')
    .toLowerCase()
    .replace(/[^a-z0-9]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
};

export const extractTurnOutcomes = (
  entry,
  turnNumber,
  seenClues = new Set(),
  seenCompletedSubs = new Set()
) => {
  if (!entry || typeof entry !== 'object' || entry.type === 'scene') return null;

  const outcome =
    typeof entry.outcome === 'object' && entry.outcome ? entry.outcome : {};
  const rawCheck = entry.check || outcome.check || outcome.skill_check || {};
  const checkTier =
    entry.tier ||
    entry.check_tier ||
    outcome.check_tier ||
    rawCheck.check_tier ||
    rawCheck.tier ||
    null;
  const tierLabel =
    entry.tier_label ||
    outcome.tier_label ||
    rawCheck.tier_label ||
    checkTier ||
    null;
  const checkStat = entry.stat || outcome.stat || rawCheck.stat || null;
  const checkChance =
    entry.chance ??
    outcome.chance ??
    rawCheck.chance ??
    rawCheck.success_pct ??
    null;
  const checkRoll = entry.roll ?? outcome.roll ?? rawCheck.roll ?? null;

  const xpGained = Number(entry.xp_gained || outcome.xp_gained || 0);
  const levelsGained = Array.isArray(entry.levels_gained)
    ? entry.levels_gained
    : [];
  const mpSpent = Number(entry.mp_spent || 0);

  const charOutcomes = Array.isArray(entry.character_outcomes)
    ? entry.character_outcomes
    : Array.isArray(outcome.character_outcomes)
      ? outcome.character_outcomes
      : [];

  let hpDelta = 0;
  let mpDelta = mpSpent > 0 ? -mpSpent : 0;
  let goldDelta = Number(
    entry.gold_delta ?? outcome.gold_delta ?? outcome.gold_change ?? 0
  );
  const itemsGained = new Set();
  const itemsLost = new Set();
  const statusEffects = new Set();

  (Array.isArray(entry.items_gained) ? entry.items_gained : []).forEach((it) => {
    const name = typeof it === 'string' ? it : it?.name;
    if (name) itemsGained.add(name);
  });
  (Array.isArray(entry.loot) ? entry.loot : []).forEach((it) => {
    const name = typeof it === 'string' ? it : it?.name;
    if (name) itemsGained.add(name);
  });

  charOutcomes.forEach((co) => {
    if (!co || typeof co !== 'object') return;
    hpDelta += Number(co.hp_change || 0);
    mpDelta += Number(co.mp_change || 0);
    goldDelta += Number(co.gold_change || 0);
    (Array.isArray(co.items_gained) ? co.items_gained : []).forEach((it) => {
      const name = typeof it === 'string' ? it : it?.name;
      if (name) itemsGained.add(name);
    });
    (Array.isArray(co.loot) ? co.loot : []).forEach((it) => {
      const name = typeof it === 'string' ? it : it?.name;
      if (name) itemsGained.add(name);
    });
    (Array.isArray(co.items_lost) ? co.items_lost : []).forEach((it) => {
      const name = typeof it === 'string' ? it : it?.name;
      if (name) itemsLost.add(name);
    });
    (Array.isArray(co.status_effects) ? co.status_effects : []).forEach((st) => {
      const name = String(
        typeof st === 'string' ? st : st?.name || ''
      ).trim();
      if (
        name &&
        !['[]', '{}', '""', "''", 'none', 'null'].includes(name.toLowerCase())
      ) {
        statusEffects.add(name);
      }
    });
  });

  const rawRelUpdates = (
    Array.isArray(entry.relationship_updates)
      ? entry.relationship_updates
      : outcome.relationship_updates || []
  ).filter(
    (r) =>
      r &&
      (typeof r === 'string' ||
        Number(r.delta_score ?? r.delta ?? 0) !== 0 ||
        r.milestone_event)
  );
  const seenRelNames = new Set();
  const relUpdates = [];
  rawRelUpdates.forEach((r) => {
    const rawName =
      typeof r === 'string' ? r : r.npc_name || r.npc || r.name || '';
    const cleanName = String(rawName).trim().toLowerCase();
    if (cleanName) {
      if (!seenRelNames.has(cleanName)) {
        seenRelNames.add(cleanName);
        relUpdates.push(r);
      }
    } else {
      relUpdates.push(r);
    }
  });
  const facUpdates = (
    Array.isArray(entry.faction_updates)
      ? entry.faction_updates
      : outcome.faction_updates || []
  ).filter(
    (f) =>
      f &&
      (typeof f === 'string' || Number(f.delta_score ?? f.delta ?? 0) !== 0)
  );

  const rawQuests = Array.isArray(entry.quest_updates)
    ? entry.quest_updates
    : outcome.quest_updates || [];
  const questUpdates = [];
  rawQuests.forEach((q) => {
    if (!q || typeof q !== 'object') return;

    const allClues = parseClues(q.current_clues);
    const newCluesThisTurn = [];
    allClues.forEach((clue) => {
      const norm = normalizeClue(clue);
      if (norm && !seenClues.has(norm)) {
        seenClues.add(norm);
        newCluesThisTurn.push(clue);
      }
    });

    const rawSubs = Array.isArray(q.completed_sub_quest_ids)
      ? q.completed_sub_quest_ids
      : [];
    const newCompletedSubs = [];
    const qKey = String(q.quest_id || q.title || 'quest')
      .toLowerCase()
      .trim();
    rawSubs.forEach((subId) => {
      const subKey = `${qKey}_sub_${subId}`;
      if (!seenCompletedSubs.has(subKey)) {
        seenCompletedSubs.add(subKey);
        newCompletedSubs.push(subId);
      }
    });

    const hasStatusChange =
      q.status === 'Completed' || q.status === 'Failed';
    const hasCompletedSubs = newCompletedSubs.length > 0;
    const hasNewClues = newCluesThisTurn.length > 0;

    if (hasStatusChange || hasCompletedSubs || hasNewClues) {
      questUpdates.push({
        ...q,
        completed_sub_quest_ids: newCompletedSubs,
        new_clues: newCluesThisTurn,
      });
    }
  });

  const rawCombat =
    entry.combat_log || outcome.combat_log || outcome._combat_log || [];
  const combatLines = Array.isArray(rawCombat)
    ? rawCombat.filter(Boolean).map(String)
    : typeof rawCombat === 'string' && rawCombat.trim()
      ? rawCombat.split('\n').filter(Boolean)
      : [];
  if (entry.enemy_attack_notice) {
    combatLines.push(String(entry.enemy_attack_notice));
  }

  const rawSocialPills =
    entry.social_feedback_pills || outcome.social_feedback_pills || [];
  const socialFeedbackPills = Array.isArray(rawSocialPills)
    ? rawSocialPills.filter(Boolean).map((p) =>
        typeof p === 'string'
          ? { label: p, tone: 'neutral' }
          : {
              key: p.key || '',
              label: p.label || '',
              detail: p.detail || '',
              tone: p.tone || 'neutral',
            }
      )
    : [];
  const intimateUpdate =
    outcome.intimate_update || entry.intimate_update || null;
  const refractoryNotice =
    outcome._refractory_recovered_notice ||
    entry._refractory_recovered_notice ||
    null;

  return {
    turnNumber,
    label: entry.label || entry.summary || 'Action',
    characterName: entry.character_name || 'Hero',
    checkTier,
    tierLabel,
    checkStat,
    checkChance,
    checkRoll,
    xpGained,
    levelsGained,
    hpDelta,
    mpDelta,
    goldDelta,
    itemsGained: Array.from(itemsGained),
    itemsLost: Array.from(itemsLost),
    statusEffects: Array.from(statusEffects),
    relUpdates,
    socialFeedbackPills,
    facUpdates,
    questUpdates,
    combatLines,
    intimateUpdate,
    refractoryNotice,
  };
};

const resolveDialoguePartners = (session) => {
  let list = [];
  if (Array.isArray(session?.dialogue_partners)) {
    list = session.dialogue_partners;
  } else if (session?.dialogue_partner) {
    const dp = session.dialogue_partner;
    if (Array.isArray(dp)) {
      list = dp;
    } else if (typeof dp === 'string') {
      const trimmed = dp.trim();
      if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
        try {
          const parsed = JSON.parse(trimmed);
          list = Array.isArray(parsed) ? parsed : [dp];
        } catch {
          list = [dp];
        }
      } else {
        list = [dp];
      }
    }
  }
  return new Set(
    list
      .map((n) => String(n || '').toLowerCase().trim())
      .filter(Boolean)
  );
};

const computeTurnOutcomesList = (session) => {
  const rawHistory = Array.isArray(session?.history) ? session.history : [];
  let actionCount = 0;
  const turnOutcomes = [];
  const seenClues = new Set();
  const seenCompletedSubs = new Set();

  rawHistory.forEach((entry) => {
    if (entry && typeof entry === 'object' && entry.type !== 'scene') {
      actionCount += 1;
      const parsed = extractTurnOutcomes(
        entry,
        actionCount,
        seenClues,
        seenCompletedSubs
      );
      if (parsed) {
        turnOutcomes.push(parsed);
      }
    }
  });
  turnOutcomes.reverse();
  return turnOutcomes;
};

export const EpistemicWatchStrip = ({
  session,
  collapsed = false,
  onToggleCollapse,
  isSheet = false,
  className = '',
}) => {
  const { t } = useTranslation();
  const ep = session?.epistemic_hud;
  if (!ep || typeof ep !== 'object') return null;

  const risk = String(ep.leak_risk || 'none').toLowerCase();
  const spotted = Array.isArray(ep.spotted_witnesses) ? ep.spotted_witnesses : [];
  const knownW = Array.isArray(ep.known_witnesses) ? ep.known_witnesses : [];
  const alibis = Array.isArray(ep.active_alibis) ? ep.active_alibis : [];
  const secrets = Array.isArray(ep.held_npc_secrets) ? ep.held_npc_secrets : [];
  if (
    risk === 'none' &&
    spotted.length === 0 &&
    knownW.length === 0 &&
    alibis.length === 0 &&
    secrets.length === 0
  ) {
    return null;
  }

  const riskClass =
    risk === 'critical'
      ? 'bg-red-950/90 border-red-400/70 text-red-100 font-semibold'
      : risk === 'high'
        ? 'bg-red-950/80 border-red-500/50 text-red-200'
        : risk === 'moderate' || risk === 'medium'
          ? 'bg-amber-950/80 border-amber-500/50 text-amber-200'
          : 'bg-yellow-950/70 border-yellow-600/40 text-yellow-200';

  const riskLabel =
    risk === 'critical'
      ? t('scene.leak_risk_critical', 'Leak Risk: Critical')
      : risk === 'high'
        ? t('scene.leak_risk_high', 'Leak Risk: High')
        : risk === 'moderate'
          ? t('scene.leak_risk_moderate', 'Leak Risk: Moderate')
          : risk === 'medium'
            ? t('scene.leak_risk_medium', 'Leak Risk: Medium')
            : t('scene.leak_risk_low', 'Leak Risk: Low');

  const content = (
    <div className="px-3 py-2 text-[11px] space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold uppercase tracking-wider text-gray-200 flex items-center gap-1.5 min-w-0 truncate">
          <span aria-hidden="true">🕵️</span>
          <span className="truncate">
            {t('scene.epistemic_watch', 'Epistemic Watch')}
          </span>
        </span>
        <div className="flex items-center gap-1 shrink-0">
          {risk !== 'none' && (
            <span
              className={`px-1.5 py-0.5 rounded border font-mono text-[10px] ${riskClass}`}
            >
              {riskLabel}
            </span>
          )}
          {!isSheet && onToggleCollapse && (
            <MotionButton
              onClick={onToggleCollapse}
              className="hk-icon-btn h-6 min-w-6 text-gray-400 hover:text-gray-100"
              aria-expanded={!collapsed}
              aria-label={
                collapsed
                  ? t('nav.expand', 'Expand')
                  : t('nav.collapse', 'Collapse')
              }
              title={
                collapsed
                  ? t('nav.expand', 'Expand')
                  : t('nav.collapse', 'Collapse')
              }
            >
              <ChevronDown
                size={13}
                className={`transition-transform duration-200 ${collapsed ? '' : 'rotate-180'}`}
              />
            </MotionButton>
          )}
        </div>
      </div>

      <CollapsibleSection isOpen={isSheet || !collapsed}>
        <div className="flex flex-wrap gap-1 pt-0.5 text-[10px] text-gray-300">
          {spotted.length > 0 && (
            <span className="hk-chip bg-rose-500/20 text-rose-200">
              {t('scene.spotted_witnesses', 'Spotted Witnesses')}:{' '}
              {spotted.length}
            </span>
          )}
          {knownW.length > 0 && (
            <span className="hk-chip">
              {t('scene.known_witnesses', 'Known Witnesses')}: {knownW.length}
            </span>
          )}
          {alibis.length > 0 && (
            <span className="hk-chip">
              {t('scene.active_alibis', 'Active Alibis')}: {alibis.length}
            </span>
          )}
          {secrets.length > 0 && (
            <span className="hk-chip bg-purple-500/20 text-purple-200">
              {t('scene.held_secrets', 'Secrets Held')}: {secrets.length}
            </span>
          )}
        </div>
      </CollapsibleSection>
    </div>
  );

  if (isSheet) {
    return (
      <div className={`hk-flat-section border-b border-fantasy-border/35 ${className}`.trim()}>
        {content}
      </div>
    );
  }

  return (
    <AcrylicPanel
      variant="pill"
      origin="right"
      className={`shrink-0 ${className}`.trim()}
    >
      {content}
    </AcrylicPanel>
  );
};

export const PresentNpcsCard = ({
  session,
  onSelectContact,
  onQuickAction,
  collapsed = false,
  onToggleCollapse,
  isSheet = false,
  className = '',
}) => {
  const { t } = useTranslation();
  const npcs = Array.isArray(session?.current_npcs) ? session.current_npcs : [];
  const dialoguePartners = useMemo(
    () => resolveDialoguePartners(session),
    [session]
  );
  const turnOutcomes = useMemo(
    () => computeTurnOutcomesList(session),
    [session]
  );

  const header = (
    <div className="px-3.5 py-2.5 flex items-center justify-between gap-2 shrink-0 border-b border-fantasy-border/25">
      <div className="flex items-center gap-1.5 min-w-0">
        <Users size={14} className="text-fantasy-accent shrink-0" />
        <span className="text-xs font-semibold uppercase tracking-wider text-gray-200 truncate">
          {t('scene.present', 'Present in Scene')}
        </span>
        {session?.crowd_state?.density &&
          session.crowd_state.density !== 'empty' && (
            <span
              className="hk-chip hk-chip-accent text-[10px] shrink-0"
              title={session.crowd_state.flavor || ''}
            >
              {t(
                `scene.crowd_density_${session.crowd_state.density}`,
                session.crowd_state.density
              )}
            </span>
          )}
      </div>
      <div className="flex items-center gap-1 shrink-0">
        <span className="hk-chip tabular-nums">{npcs.length}</span>
        {!isSheet && onToggleCollapse && (
          <MotionButton
            onClick={onToggleCollapse}
            className="hk-icon-btn h-7 min-w-7 text-gray-400 hover:text-gray-100"
            aria-expanded={!collapsed}
            aria-label={
              collapsed
                ? t('nav.expand', 'Expand')
                : t('nav.collapse', 'Collapse')
            }
            title={
              collapsed
                ? t('nav.expand', 'Expand')
                : t('nav.collapse', 'Collapse')
            }
          >
            <ChevronDown
              size={14}
              className={`transition-transform duration-200 ${collapsed ? '' : 'rotate-180'}`}
            />
          </MotionButton>
        )}
      </div>
    </div>
  );

  const listBody = (
    <div className="overflow-y-auto overscroll-contain [scrollbar-gutter:stable] custom-scrollbar px-3 py-1.5 flex-1 min-h-0">
      {npcs.length === 0 ? (
        <p className="py-5 text-center text-xs text-gray-400 italic">
          {t('scene.no_npcs', 'No other characters in the immediate area.')}
        </p>
      ) : (
        <div className="divide-y divide-fantasy-border/25">
          {npcs.map((npc, idx) => {
            const name =
              typeof npc === 'string' ? npc : npc?.name || 'Unknown';
            const isPartner = dialoguePartners.has(name.toLowerCase().trim());
            const clothing =
              typeof npc === 'object' ? npc?.clothing_status : null;
            const anomTag =
              typeof npc === 'object'
                ? npc?.anomalous_npc_tag || npc?.basic_info?.anomalous_npc_tag
                : null;
            const isAnomaly = isAnomalousNpc(npc);
            const statusEffects = (
              typeof npc === 'object' && Array.isArray(npc?.status_effects)
                ? npc.status_effects
                : []
            ).filter((eff) => {
              const str = (
                typeof eff === 'string' ? eff : eff?.name || ''
              ).trim();
              const low = str.toLowerCase();
              return (
                str &&
                str !== '[]' &&
                str !== '{}' &&
                str !== '""' &&
                str !== "''" &&
                low !== 'none' &&
                low !== 'null' &&
                low !== 'present' &&
                low !== 'absent' &&
                low !== 'nearby'
              );
            });

            const score = npc?.relationship_score ?? npc?.affinity ?? 0;
            const isRomantic =
              npc?.track === 'romantic' || npc?.relations?.track === 'romantic';
            const tier = getRelationshipTier(
              score,
              isRomantic ? 'romantic' : 'platonic',
              t
            );

            const physExc = session?.physical_state?.excitement;
            const physActors =
              physExc?.actors && typeof physExc.actors === 'object'
                ? physExc.actors
                : {};
            let actorExc =
              npc?.excitement_meter !== undefined &&
              npc?.excitement_meter !== null
                ? {
                    meter: Number(npc.excitement_meter),
                    status: npc.excitement_status,
                    climaxed: npc.excitement_climaxed,
                    active: npc.excitement_active,
                  }
                : null;

            if (!actorExc && physActors) {
              const cleanN = name.toLowerCase().trim();
              for (const [k, v] of Object.entries(physActors)) {
                const cleanK = String(k || '').toLowerCase().trim();
                if (
                  cleanK &&
                  (cleanK === cleanN ||
                    cleanN.includes(cleanK) ||
                    cleanK.includes(cleanN))
                ) {
                  actorExc = v;
                  break;
                }
              }
            }

            if (!actorExc) {
              const latestTurn = turnOutcomes[0];
              const intUp = latestTurn?.intimateUpdate;
              if (intUp?.active) {
                const cleanN = name.toLowerCase().trim();
                const pMatch = (intUp.partner_meters || []).find((pm) => {
                  const pName = String(pm?.name || '').toLowerCase().trim();
                  return (
                    pName &&
                    (pName === cleanN ||
                      cleanN.includes(pName) ||
                      pName.includes(cleanN))
                  );
                });
                if (pMatch) {
                  actorExc = pMatch;
                } else if (intUp.partner_meter !== undefined && isPartner) {
                  actorExc = {
                    meter: intUp.partner_meter,
                    status: intUp.act_type,
                    climaxed: intUp.simultaneous_partner_climax,
                  };
                }
              }
            }

            const excMeter =
              actorExc?.meter !== undefined && actorExc?.meter !== null
                ? Number(actorExc.meter)
                : null;
            const isExcActive = Boolean(
              actorExc?.active ||
                physExc?.active ||
                (excMeter !== null && excMeter > 0)
            );
            const showExcitement =
              !isAnomaly && isExcActive && excMeter !== null;
            const demographics =
              !isAnomaly && typeof npc === 'object'
                ? resolveNpcDemographics(npc, t)
                : null;
            const isBystanderCompact =
              !isAnomaly &&
              !isPartner &&
              typeof npc === 'object' &&
              npc?.is_spotlight === false;

            if (isBystanderCompact) {
              const roleText = String(
                npc?.role || npc?.basic_info?.role || ''
              ).trim();
              return (
                <div
                  key={`${name}-${idx}`}
                  className="py-2 flex flex-col gap-1 text-[11px] text-gray-300"
                  title={roleText ? `${name} — ${roleText}` : name}
                >
                  <div className="flex items-center justify-between gap-1.5 min-w-0">
                    <div className="flex items-center gap-1.5 min-w-0 flex-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-slate-400 shrink-0" />
                      <span className="font-semibold text-gray-200 truncate">
                        {name}
                      </span>
                      {roleText && (
                        <span className="text-[10px] text-gray-400 truncate">
                          ({roleText})
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      {npc?.activity_tag && (
                        <span className="hk-chip text-[9.5px]">
                          {npc.activity_tag}
                        </span>
                      )}
                      {npc?.telltale_revealed && npc?.visible_tell_text && (
                        <span
                          className="hk-chip bg-purple-500/20 text-purple-200 text-[9.5px]"
                          title={npc.visible_tell_text}
                        >
                          👁️
                        </span>
                      )}
                    </div>
                  </div>
                  {demographics?.hasAny && (
                    <div className="flex flex-wrap items-center gap-1 pl-3 text-[9.5px] leading-tight">
                      {demographics.ageCategory && (
                        <span
                          className={`px-1 py-0.5 rounded border font-medium ${demographics.ageCategory.pillClass}`}
                        >
                          {demographics.ageCategory.label}
                        </span>
                      )}
                      {demographics.genderInfo && (
                        <span
                          className={`inline-flex items-center gap-0.5 px-1 py-0.5 rounded border ${demographics.genderInfo.pillClass}`}
                        >
                          {demographics.genderInfo.symbol && (
                            <span aria-hidden="true">
                              {demographics.genderInfo.symbol}
                            </span>
                          )}
                          <span>{demographics.genderInfo.label}</span>
                        </span>
                      )}
                      {demographics.raceLabel && (
                        <span className="hk-chip text-[9.5px]">
                          {demographics.raceLabel}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              );
            }

            return (
              <div
                key={`${name}-${idx}`}
                className={`py-2.5 flex flex-col gap-1.5 text-xs ${
                  isPartner
                    ? 'border-l-2 border-purple-400 pl-2.5'
                    : isAnomaly
                      ? 'border-l-2 border-amber-400/80 pl-2.5'
                      : ''
                }`}
              >
                {/* Row 1: Dot + Name + Badges + Clothing */}
                <div className="flex items-center justify-between gap-1.5 min-w-0 flex-wrap">
                  <button
                    type="button"
                    onClick={() =>
                      !isAnomaly && onSelectContact && onSelectContact(name)
                    }
                    className={`inline-flex items-center gap-1.5 font-semibold text-left min-w-0 max-w-full transition-colors ${
                      isAnomaly
                        ? 'cursor-default text-amber-100'
                        : isPartner
                          ? 'text-purple-200 hover:text-purple-100'
                          : 'text-gray-100 hover:text-fantasy-accent'
                    }`}
                    title={
                      isAnomaly
                        ? `${name}${npc?.role ? ` — ${npc.role}` : ''}`
                        : onSelectContact
                          ? `View ${name} in Codex`
                          : name
                    }
                  >
                    <span
                      className={`w-2 h-2 rounded-full shrink-0 ${
                        isPartner
                          ? 'bg-purple-400 animate-pulse'
                          : isAnomaly
                            ? 'bg-amber-400 animate-pulse'
                            : 'bg-emerald-400'
                      }`}
                    />
                    <span className="truncate">{name}</span>
                  </button>

                  <div className="flex flex-wrap items-center gap-1 shrink-0">
                    {isAnomaly && (npc?.is_disguised || npc?.uncanny_presence) && (
                      <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-200 font-bold">
                        🎭 {t('scene.uncanny_presence', 'Uncanny Presence')}
                      </span>
                    )}
                    {isAnomaly && !(npc?.is_disguised || npc?.uncanny_presence) && (
                      <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-200 font-bold">
                        👁️ {t('codex.anomaly_entity', 'Anomaly')}
                      </span>
                    )}
                    {!isAnomaly && anomTag === 'special_agent' && (
                      <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded bg-cyan-500/20 text-cyan-200 font-bold">
                        ⚡ {t('codex.special_agent', 'Special Agent')}
                      </span>
                    )}
                    {!isAnomaly && anomTag === 'civilian' && (
                      <span className="hk-chip text-[9px] font-mono uppercase">
                        {t('codex.civilian', 'Civilian')}
                      </span>
                    )}
                    {isPartner && (
                      <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded bg-purple-500/25 text-purple-200 font-bold">
                        {isAnomaly &&
                        (npc?.sapience === 'compulsive' ||
                          npc?.pattern_observable)
                          ? t('scene.observing', 'Observing')
                          : t('scene.talking', 'Talking')}
                      </span>
                    )}
                    {isPartner && npc?.dialogue_mood?.mood_key && (
                      <span
                        className={`text-[9px] font-mono px-1.5 py-0.5 rounded font-semibold ${
                          npc.dialogue_mood.mood_key === 'Engaged'
                            ? 'bg-emerald-500/20 text-emerald-300'
                            : npc.dialogue_mood.mood_key === 'Guarded'
                              ? 'bg-amber-500/20 text-amber-300'
                              : npc.dialogue_mood.mood_key === 'Upset'
                                ? 'bg-rose-500/20 text-rose-300'
                                : 'bg-slate-500/20 text-slate-300'
                        }`}
                      >
                        {t(
                          `social.moods.${npc.dialogue_mood.mood_key}`,
                          npc.dialogue_mood.mood_label ||
                            npc.dialogue_mood.mood_key
                        )}
                      </span>
                    )}
                    {!isAnomaly && clothing && (
                      <span className="hk-chip text-[9.5px] font-mono">
                        {clothing}
                      </span>
                    )}
                  </div>
                </div>

                {/* Row 1.5: Demographics */}
                {!isAnomaly && demographics?.hasAny && (
                  <div className="flex flex-wrap items-center gap-1 text-[10px] leading-tight">
                    {demographics.ageCategory && (
                      <span
                        className={`px-1.5 py-0.5 rounded border font-medium ${demographics.ageCategory.pillClass}`}
                      >
                        {demographics.ageCategory.label}
                      </span>
                    )}
                    {demographics.genderInfo && (
                      <span
                        className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded border ${demographics.genderInfo.pillClass}`}
                      >
                        {demographics.genderInfo.symbol && (
                          <span aria-hidden="true">
                            {demographics.genderInfo.symbol}
                          </span>
                        )}
                        <span>{demographics.genderInfo.label}</span>
                      </span>
                    )}
                    {demographics.raceLabel && (
                      <span className="hk-chip text-[10px]">
                        {demographics.raceLabel}
                      </span>
                    )}
                  </div>
                )}

                {/* Row 2: Anomaly Role OR Affinity Meter */}
                {isAnomaly ? (
                  <div className="flex items-center justify-between gap-1.5 text-[10px] text-amber-200/85">
                    <span className="truncate">
                      {npc?.is_disguised || npc?.uncanny_presence
                        ? npc?.role ||
                          t('scene.uncanny_stranger', 'Uncanny Stranger')
                        : npc?.role || 'Non-Hostile Anomaly'}
                    </span>
                    <span className="hk-chip font-mono text-amber-200 shrink-0">
                      {npc?.is_disguised || npc?.uncanny_presence
                        ? `🎭 ${t('scene.uncanny_presence', 'Uncanny Presence')}`
                        : npc?.dossier_revealed
                          ? `📜 ${t('codex.dossier_revealed', 'Dossier Known')}`
                          : npc?.temperament ||
                            (npc?.talkable
                              ? 'Sapient'
                              : npc?.sapience === 'compulsive'
                                ? 'Compulsive'
                                : 'Observed')}
                    </span>
                  </div>
                ) : (
                  <div className="space-y-1">
                    <div className="flex items-center justify-between text-[10px]">
                      <span className={`font-semibold ${tier.color}`}>
                        {tier.label}
                      </span>
                      <span className="font-mono font-bold text-gray-300 tabular-nums">
                        {score > 0 ? `+${score}` : score}
                      </span>
                    </div>
                    <div className="h-1 w-full bg-gray-500/20 rounded-full overflow-hidden">
                      <div
                        className={`h-full ${tier.bg} transition-all duration-300`}
                        style={{
                          width: `${Math.max(
                            5,
                            Math.min(100, ((score + 100) / 400) * 100)
                          )}%`,
                        }}
                      />
                    </div>
                  </div>
                )}

                {/* Row 3: Excitement Meter */}
                {showExcitement && (
                  <div className="space-y-1">
                    <div className="flex items-center justify-between text-[10px]">
                      <span className="font-semibold text-rose-300 flex items-center gap-1">
                        <span>💋</span>
                        <span>{t('scene.excitement', 'Excitement')}</span>
                        {actorExc?.climaxed && (
                          <span className="text-amber-300 font-bold">💥</span>
                        )}
                        {actorExc?.status && (
                          <span className="text-[9px] font-mono font-normal text-rose-400">
                            ({actorExc.status})
                          </span>
                        )}
                      </span>
                      <span className="font-mono font-bold text-rose-300 tabular-nums">
                        {excMeter}%
                      </span>
                    </div>
                    <div className="h-1 w-full bg-gray-500/20 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-500 bg-gradient-to-r from-rose-500 via-pink-500 to-red-500 ${
                          excMeter >= 80 ? 'animate-pulse' : ''
                        }`}
                        style={{
                          width: `${Math.min(100, Math.max(0, excMeter))}%`,
                        }}
                      />
                    </div>
                  </div>
                )}

                {/* Row 3.5: Activity, Epistemic, Tell & Join Activity */}
                {(npc?.activity_tag ||
                  npc?.epistemic_tag ||
                  (npc?.telltale_revealed && npc?.visible_tell_text) ||
                  (npc?.joinable_activity &&
                    npc?.activity_mode !== 'joined' &&
                    typeof onQuickAction === 'function')) && (
                  <div className="flex flex-wrap items-center gap-1 text-[10px]">
                    {npc?.activity_tag &&
                      (() => {
                        const actMode = String(
                          npc?.activity_mode || ''
                        ).toLowerCase();
                        const actToneClass =
                          actMode === 'joined'
                            ? 'bg-emerald-500/20 text-emerald-200'
                            : actMode === 'waiting'
                              ? 'bg-sky-500/20 text-sky-200'
                              : actMode === 'packing_up'
                                ? 'bg-slate-500/20 text-slate-300'
                                : 'bg-amber-500/15 text-amber-200';
                        return (
                          <span
                            className={`hk-chip ${actToneClass}`}
                            title={t('scene.activity_prefix', 'Doing')}
                          >
                            <span aria-hidden="true">🎯</span>
                            <span>{npc.activity_tag}</span>
                          </span>
                        );
                      })()}
                    {npc?.epistemic_tag && (
                      <span
                        className="hk-chip bg-rose-500/25 text-rose-200 font-semibold"
                        title={t('scene.epistemic_watch', 'Epistemic Watch')}
                      >
                        <span aria-hidden="true">⚠️</span>
                        <span>
                          {npc.epistemic_tag === 'spotted_you'
                            ? t('scene.spotted_you_badge', 'Spotted You!')
                            : npc.epistemic_tag}
                        </span>
                      </span>
                    )}
                    {npc?.telltale_revealed && npc?.visible_tell_text && (
                      <span
                        className="hk-chip bg-purple-500/20 text-purple-200"
                        title={t(
                          'scene.visible_tell_prefix',
                          'Noticeable Tell'
                        )}
                      >
                        <span aria-hidden="true">👁️</span>
                        <span>{npc.visible_tell_text}</span>
                      </span>
                    )}
                    {npc?.joinable_activity &&
                      npc?.activity_mode !== 'joined' &&
                      typeof onQuickAction === 'function' && (
                        <MotionButton
                          onClick={(e) => {
                            e.stopPropagation();
                            onQuickAction({
                              intent: 'join_activity',
                              direct_choice: {
                                intent: 'join_activity',
                                target_npc: npc.name || npc.npc_id || '',
                                activity_key:
                                  npc?.join_activity_seed?.activity_key ||
                                  npc?.activity_key ||
                                  '',
                                label: `${t(
                                  'scene.join_activity_btn',
                                  'Join Activity'
                                )}: ${npc.name || ''}`.trim(),
                              },
                            });
                          }}
                          className="hk-chip hk-chip-accent hover:bg-fantasy-accent/30 cursor-pointer font-semibold"
                        >
                          <span aria-hidden="true">🤝</span>
                          <span>
                            {t('scene.join_activity_btn', 'Join Activity')}
                          </span>
                        </MotionButton>
                      )}
                  </div>
                )}

                {/* Row 4: Status Effects */}
                {statusEffects && statusEffects.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {statusEffects.map((eff, eIdx) => (
                      <StatusEffectBadge key={eIdx} effect={eff} />
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );

  if (isSheet) {
    return (
      <div className={`flex flex-col min-h-0 flex-1 ${className}`.trim()}>
        {header}
        {listBody}
      </div>
    );
  }

  return (
    <AcrylicPanel
      variant="panel"
      origin="right"
      className={`flex flex-col min-h-0 overflow-hidden ${className}`.trim()}
    >
      {header}
      <CollapsibleSection
        isOpen={!collapsed}
        className="min-h-0 flex-1 flex flex-col"
      >
        {listBody}
      </CollapsibleSection>
    </AcrylicPanel>
  );
};

const OutcomeDetailsBlock = ({ item, session }) => {
  const { t } = useTranslation();
  const theme = getOutcomeTierTheme(
    item.checkTier,
    item.tierLabel,
    item.checkStat
  );
  const statPrefix =
    item.checkStat && item.checkStat !== 'NONE' && item.checkStat !== 'FREE'
      ? `${item.checkStat} • `
      : '';
  const tierText = (item.tierLabel || theme.defaultLabel).toUpperCase();
  const chanceText =
    item.checkChance !== null &&
    item.checkChance !== undefined &&
    item.checkStat !== 'NONE' &&
    item.checkStat !== 'FREE'
      ? ` (${Math.round(Number(item.checkChance))}%)`
      : '';

  return (
    <div className="space-y-2.5 text-xs">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <span className="text-[10.5px] font-mono uppercase tracking-wider text-fantasy-accent font-bold">
          {t('scene.turn_number', {
            number: item.turnNumber,
            defaultValue: `Turn #${item.turnNumber}`,
          })}
        </span>
        <span
          className={`inline-flex items-center gap-1 rounded-full border font-mono font-bold uppercase px-2 py-0.5 text-[10px] ${theme.badgeClass}`}
        >
          <span>{theme.icon}</span>
          <span>
            {statPrefix}
            {tierText}
            {chanceText}
          </span>
        </span>
      </div>

      <div className="font-semibold text-gray-100 leading-snug pl-2.5 border-l-2 border-fantasy-accent">
        {item.label}
      </div>

      {/* Mechanical Delta Pills */}
      <div className="flex flex-wrap gap-1">
        {item.xpGained > 0 && (
          <span className="hk-chip bg-amber-500/20 text-amber-300 font-mono">
            ✨ +{item.xpGained} EXP
          </span>
        )}
        {item.levelsGained.length > 0 && (
          <span className="hk-chip bg-yellow-500/25 text-yellow-200 font-mono font-bold animate-pulse">
            🎉 {t('outcomes.level_up', 'LEVEL UP')} (Lv.
            {item.levelsGained[item.levelsGained.length - 1]})
          </span>
        )}
        {item.hpDelta !== 0 && (
          <span
            className={`hk-chip font-mono ${
              item.hpDelta > 0
                ? 'bg-emerald-500/20 text-emerald-300'
                : 'bg-red-500/25 text-red-300'
            }`}
          >
            <Heart size={10} />
            {item.hpDelta > 0 ? `+${item.hpDelta}` : item.hpDelta} HP
          </span>
        )}
        {item.mpDelta !== 0 && (
          <span
            className={`hk-chip font-mono ${
              item.mpDelta > 0
                ? 'bg-blue-500/20 text-blue-300'
                : 'bg-indigo-500/20 text-indigo-300'
            }`}
          >
            💧 {item.mpDelta > 0 ? `+${item.mpDelta}` : item.mpDelta} MP
          </span>
        )}
        {item.goldDelta !== 0 && (
          <span
            className={`hk-chip font-mono tabular-nums ${
              item.goldDelta > 0
                ? 'bg-amber-500/20 text-amber-300'
                : 'bg-orange-500/20 text-orange-300'
            }`}
          >
            <Coins size={10} />
            {item.goldDelta > 0
              ? `+${formatScenarioCurrency(item.goldDelta, session?.scenario)}`
              : `-${formatScenarioCurrency(Math.abs(item.goldDelta), session?.scenario)}`}
          </span>
        )}
        {item.itemsGained.map((it, iIdx) => (
          <span
            key={`gain-${iIdx}`}
            className="hk-chip bg-cyan-500/20 text-cyan-200"
          >
            <Gift size={10} /> +{it}
          </span>
        ))}
        {item.itemsLost.map((it, iIdx) => (
          <span
            key={`lost-${iIdx}`}
            className="hk-chip line-through text-gray-400"
          >
            -{it}
          </span>
        ))}
        {item.statusEffects.map((st, sIdx) => (
          <span
            key={`st-${sIdx}`}
            className="hk-chip bg-rose-500/20 text-rose-200"
          >
            <ShieldAlert size={10} /> {st}
          </span>
        ))}
        {item.relUpdates.map((ru, rIdx) => {
          const label =
            typeof ru === 'string'
              ? ru
              : `${ru.npc_name || ru.npc || ru.name || 'NPC'}: ${
                  (ru.delta_score ?? ru.delta ?? 0) > 0
                    ? `+${ru.delta_score ?? ru.delta}`
                    : (ru.delta_score ?? ru.delta ?? '')
                }`;
          return (
            <span
              key={`rel-${rIdx}`}
              className="hk-chip bg-pink-500/20 text-pink-200"
            >
              💕 {label}
            </span>
          );
        })}
        {(item.socialFeedbackPills || []).map((pill, pIdx) => {
          const pillText = formatSocialFeedbackPill(pill, t);
          if (!pillText) return null;
          return (
            <span
              key={`soc-pill-${pIdx}`}
              className="hk-chip bg-indigo-500/20 text-indigo-200"
            >
              💬 {pillText}
            </span>
          );
        })}
        {item.facUpdates.map((fu, fIdx) => {
          const label =
            typeof fu === 'string'
              ? fu
              : `${fu.faction_name || fu.faction || fu.name || 'Faction'}: ${
                  (fu.delta_score ?? fu.delta ?? 0) > 0
                    ? `+${fu.delta_score ?? fu.delta}`
                    : (fu.delta_score ?? fu.delta ?? 0)
                } Rep`;
          return (
            <span
              key={`fac-${fIdx}`}
              className="hk-chip bg-purple-500/20 text-purple-200"
            >
              🚩 {label}
            </span>
          );
        })}
      </div>

      {item.refractoryNotice && (
        <div className="pt-2 border-t border-fantasy-border/25 text-emerald-300 flex items-center gap-1.5 font-semibold">
          <span>⚡</span>
          <span>{item.refractoryNotice}</span>
        </div>
      )}

      {item.intimateUpdate && item.intimateUpdate.active && (
        <div className="pt-2 border-t border-fantasy-border/25 space-y-1.5">
          <div className="flex items-center justify-between font-semibold text-pink-300 text-[11px]">
            <span className="flex items-center gap-1">
              <span>💋</span>
              <span>{t('outcomes.intimate_excitement', 'Intimate Excitement & Arousal')}</span>
            </span>
            {item.intimateUpdate.act_type && (
              <span className="hk-chip bg-pink-500/20 text-pink-200 text-[9px] uppercase font-mono">
                {item.intimateUpdate.act_type === 'foreplay_nongenital'
                  ? t('outcomes.foreplay', 'Foreplay')
                  : item.intimateUpdate.act_type.replace(/_/g, ' ')}
              </span>
            )}
          </div>
          <div className="space-y-0.5 text-[10px]">
            <div className="flex justify-between text-pink-100">
              <span>
                {item.characterName} (You){' '}
                {item.intimateUpdate.player_climaxed ? '💥' : ''}
              </span>
              <span className="font-mono text-pink-300 font-bold">
                {item.intimateUpdate.player_meter}%
              </span>
            </div>
            <div className="w-full bg-gray-500/20 rounded-full h-1.5 overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-pink-500 via-rose-500 to-red-500"
                style={{
                  width: `${Math.min(100, item.intimateUpdate.player_meter)}%`,
                }}
              />
            </div>
          </div>
          {(item.intimateUpdate.partner_meters?.length > 0
            ? item.intimateUpdate.partner_meters
            : [
                {
                  name:
                    session?.dialogue_partner ||
                    item.intimateUpdate.partner_name ||
                    'Partner',
                  meter: item.intimateUpdate.partner_meter,
                },
              ]
          ).map((p, pIdx) => (
            <div key={`pm-${pIdx}`} className="space-y-0.5 text-[10px]">
              <div className="flex justify-between text-pink-100">
                <span>
                  {p.name || 'Partner'} {p.climaxed ? '💥' : ''}
                </span>
                <span className="font-mono text-rose-300 font-bold">
                  {p.meter}%
                </span>
              </div>
              <div className="w-full bg-gray-500/20 rounded-full h-1.5 overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-rose-500 via-pink-500 to-red-500"
                  style={{ width: `${Math.min(100, p.meter)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {item.questUpdates.length > 0 && (
        <div className="pt-2 border-t border-fantasy-border/25 space-y-1.5">
          {item.questUpdates.map((q, qIdx) => (
            <div key={`q-${qIdx}`} className="space-y-1">
              <div className="flex items-center justify-between gap-1.5 font-semibold text-emerald-300">
                <span className="truncate">
                  📜 {q.title || q.quest_id || t('outcomes.quest_updated', 'Quest Updated')}
                </span>
                {q.status && (
                  <span className="hk-chip bg-emerald-500/20 text-emerald-200 text-[9px] font-mono uppercase">
                    {q.status}
                  </span>
                )}
              </div>
              {Array.isArray(q.completed_sub_quest_ids) &&
                q.completed_sub_quest_ids.length > 0 && (
                  <div className="text-emerald-200 text-[11px]">
                    ✅ #{q.completed_sub_quest_ids.join(', #')}
                  </div>
                )}
              {Array.isArray(q.new_clues) &&
                q.new_clues.map((clue, cIdx) => (
                  <div
                    key={`clue-${cIdx}`}
                    className="pl-2 border-l-2 border-amber-400/70 text-amber-100 text-[11px] italic"
                  >
                    {clue}
                  </div>
                ))}
            </div>
          ))}
        </div>
      )}

      {item.combatLines.length > 0 && (
        <div className="pt-2 border-t border-fantasy-border/25 space-y-0.5 font-mono text-[11px] text-red-200">
          <div className="flex items-center gap-1.5 text-red-300 font-bold uppercase tracking-wider">
            <Swords size={11} />
            <span>{t('outcomes.combat_log', 'Combat Log')}</span>
          </div>
          {item.combatLines.map((line, lIdx) => (
            <div key={`c-${lIdx}`} className="leading-relaxed text-gray-200">
              • {line}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export const LatestOutcomeCard = ({
  session,
  collapsed = false,
  onToggleCollapse,
  onOpenHistory,
  isSheet = false,
  className = '',
}) => {
  const { t } = useTranslation();
  const turnOutcomes = useMemo(
    () => computeTurnOutcomesList(session),
    [session]
  );
  const latest = turnOutcomes[0] || null;

  const header = (
    <div
      className={`px-3.5 py-2.5 flex items-center justify-between gap-2 shrink-0 ${
        isSheet || !collapsed ? 'border-b border-fantasy-border/25' : ''
      }`}
    >
      <div className="flex items-center gap-1.5 min-w-0">
        <ScrollText size={14} className="text-fantasy-accent shrink-0" />
        <span className="text-xs font-semibold uppercase tracking-wider text-gray-200 truncate">
          {t('scene.outcomes_title', 'Outcomes')}
        </span>
      </div>
      <div className="flex items-center gap-1 shrink-0">
        {onOpenHistory && (
          <MotionButton
            onClick={onOpenHistory}
            className="hk-icon-btn h-7 min-w-7 text-gray-400 hover:text-fantasy-accent"
            title={t('history.view_turns', 'View Turns History')}
            aria-label={t('history.view_turns', 'View Turns History')}
          >
            <History size={14} />
          </MotionButton>
        )}
        {!isSheet && onToggleCollapse && (
          <MotionButton
            onClick={onToggleCollapse}
            className="hk-icon-btn h-7 min-w-7 text-gray-400 hover:text-gray-100"
            aria-expanded={!collapsed}
            aria-label={
              collapsed
                ? t('nav.expand', 'Expand')
                : t('nav.collapse', 'Collapse')
            }
            title={
              collapsed
                ? t('nav.expand', 'Expand')
                : t('nav.collapse', 'Collapse')
            }
          >
            <ChevronDown
              size={14}
              className={`transition-transform duration-200 ${collapsed ? '' : 'rotate-180'}`}
            />
          </MotionButton>
        )}
      </div>
    </div>
  );

  const body = (
    <div className="overflow-y-auto overscroll-contain [scrollbar-gutter:stable] custom-scrollbar px-3.5 py-2.5 flex-1 min-h-0">
      {!latest ? (
        <div className="text-center py-4 px-2 text-xs text-gray-400 space-y-1">
          <Sparkles size={15} className="text-fantasy-accent mx-auto" />
          <p className="font-semibold text-gray-200">
            {t('scene.no_outcomes_title', 'No Turn Outcomes Yet')}
          </p>
          <p className="text-[11px] leading-relaxed">
            {t(
              'scene.no_outcomes_desc',
              'Skill check rolls, EXP gains, combat logs, loot, and newly discovered clues will appear here as your story unfolds.'
            )}
          </p>
        </div>
      ) : (
        <OutcomeDetailsBlock item={latest} session={session} />
      )}
    </div>
  );

  if (isSheet) {
    return (
      <div className={`flex flex-col min-h-0 flex-1 ${className}`.trim()}>
        {header}
        {body}
      </div>
    );
  }

  return (
    <AcrylicPanel
      variant="panel"
      origin="right"
      className={`flex flex-col min-h-0 overflow-hidden ${className}`.trim()}
    >
      {header}
      <CollapsibleSection
        isOpen={!collapsed}
        className="min-h-0 flex-1 flex flex-col"
      >
        {body}
      </CollapsibleSection>
    </AcrylicPanel>
  );
};

const WorldOutcomeSidebar = ({
  session,
  onSelectContact,
  onQuickAction,
  onOpenHistory,
  isMobileDrawer = false,
}) => {
  return (
    <div className="flex flex-col h-full min-h-0 gap-2.5 select-none">
      <EpistemicWatchStrip session={session} isSheet={isMobileDrawer} />
      <PresentNpcsCard
        session={session}
        onSelectContact={onSelectContact}
        onQuickAction={onQuickAction}
        isSheet={isMobileDrawer}
        className="flex-1"
      />
      <LatestOutcomeCard
        session={session}
        onOpenHistory={onOpenHistory}
        isSheet={isMobileDrawer}
        className="flex-1"
      />
    </div>
  );
};

export default WorldOutcomeSidebar;
