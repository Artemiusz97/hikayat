import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ArrowLeft,
  BookOpen,
  BookUser,
  Briefcase,
  Heart,
  ShieldAlert,
  User,
  X,
} from 'lucide-react';
import { StatusEffectBadge } from './CharacterSheet';
import { getRelationshipTier } from './CodexPanel';
import NpcDossierBody, {
  defaultBulletRenderer as renderBulletPoints,
  isRedundantAgentTierGrade,
  resolveAffiliations,
  resolveAgeGroupLabel,
} from './NpcDossierBody';
import {
  formatGender,
  formatRace,
  formatTitle,
} from '../../utils/npcDemographics';
import { isAnomalousNpc, normalizeActorName } from '../../utils/sceneTargets';
import { findLinkedPersonInRoster, matchesNpcIdentity } from '../../utils/npcProfile';
import { MotionButton } from '../Common/MotionPrimitives';

const NpcProfileSideCard = ({
  profile,
  session,
  codexHook,
  onClose,
  onBack = null,
  onOpenInRoster,
  onInspectLinkedNpc = null,
  isSheet = false,
}) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState('persona');
  const scrollRef = useRef(null);

  const npc = profile?.npc || null;
  const npcKey = npc?.id || npc?.npc_id || npc?.name || 'npc';

  useEffect(() => {
    setActiveTab('persona');
    if (scrollRef.current) {
      scrollRef.current.scrollTop = 0;
    }
  }, [npcKey]);

  const personalContacts = useMemo(
    () => (codexHook?.contacts || []).filter((c) => c && !c.is_dispatch_channel),
    [codexHook?.contacts]
  );

  const partyNpcNames = useMemo(
    () => new Set((session?.party_npcs || []).map((p) => String(p?.name || '').toLowerCase())),
    [session?.party_npcs]
  );

  if (!profile || !npc) return null;

  const { sourceKind, rosterTarget, isTalking } = profile;
  const basic = npc.basic_info || {};
  const score = npc.relationship_score ?? npc.affinity_score ?? npc.affinity ?? 0;
  const isBlocked = Boolean(npc.is_blocked_contact || score <= -50);
  const isRomantic = npc.track === 'romantic' || npc.relations?.track === 'romantic';
  const tier = getRelationshipTier(score, isRomantic ? 'romantic' : 'platonic', t);
  const isInParty = partyNpcNames.has(String(npc.name || '').toLowerCase());
  const anomTag = npc.anomalous_npc_tag || basic.anomalous_npc_tag || null;
  const isSpecialAgent = anomTag === 'special_agent';
  const isCivilianTag = anomTag === 'civilian';
  const isDeceased = Boolean(
    npc.deceased ||
      basic.deceased ||
      String(npc.disposition || '').toLowerCase() === 'dead'
  );
  const isDebugRevealed = Boolean(npc.debug_revealed);

  const activeStatusEffects = (Array.isArray(npc.status_effects) ? npc.status_effects : []).filter(
    (s) => {
      const str = typeof s === 'string' ? s.trim() : (s?.name || '').trim();
      const low = str.toLowerCase();
      return (
        str &&
        !['[]', '{}', '""', "''", 'none', 'null', 'present', 'absent', 'nearby'].includes(low)
      );
    }
  );

  const roleSubtitle =
    npc.public_role ||
    basic.public_role ||
    basic.role ||
    basic.occupation ||
    npc.role ||
    (basic.faction ? `${basic.faction} Member` : '');

  const findLinkedPerson = (itemOrName) =>
    findLinkedPersonInRoster(itemOrName, personalContacts, codexHook?.lorebook?.entities || [], {
      acquaintances: codexHook?.acquaintances || [],
      sceneNpcs: session?.current_npcs || [],
    });

  const handleJumpToPerson = (matchObj) => {
    if (!matchObj?.entry) return;
    const targetName = normalizeActorName(matchObj.entry) || matchObj.entry.name;
    if (!targetName) return;

    const presentInScene = (session?.current_npcs || []).some(
      (entry) => !isAnomalousNpc(entry) && matchesNpcIdentity(entry, targetName)
    );
    if (presentInScene && onInspectLinkedNpc) {
      onInspectLinkedNpc(targetName);
      return;
    }

    const nextRoster = matchObj.isSavedContact
      ? 'contacts'
      : matchObj.isAcquaintance
        ? 'acquaintances'
        : 'codex';
    onOpenInRoster?.(targetName, nextRoster);
  };

  const rosterIsContacts = rosterTarget === 'contacts' || rosterTarget === 'acquaintances';
  const rosterLabel = rosterIsContacts
    ? t('scene.open_in_contacts', 'Open in Contacts')
    : t('scene.open_in_codex', 'Open in Codex');
  const RosterIcon = rosterIsContacts ? BookUser : BookOpen;

  const { isStudent, club, faction } = resolveAffiliations(npc, basic);
  const ageLabel = resolveAgeGroupLabel(npc, basic, isStudent, t);
  const genderInfo = formatGender(basic.gender || npc.gender, t);
  const raceLabel = formatRace(basic.race || npc.race, t);

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-3.5 py-2.5 border-b border-fantasy-border/25 flex items-start justify-between gap-2 shrink-0">
        <div className="flex items-start gap-2 min-w-0 flex-1">
          {isSheet && onBack && (
            <MotionButton
              onClick={onBack}
              className="hk-icon-btn h-7 min-w-7 shrink-0 mt-0.5 text-gray-300 hover:text-white"
              aria-label={t('common.back', 'Back')}
              title={t('common.back', 'Back')}
            >
              <ArrowLeft size={15} />
            </MotionButton>
          )}
          <div
            className={`w-8 h-8 rounded-full flex items-center justify-center border font-bold text-xs shrink-0 mt-0.5 ${
              isBlocked
                ? 'bg-red-950/60 border-red-700/70 text-red-300'
                : isRomantic
                  ? 'bg-pink-950/40 border-pink-700/60 text-pink-300'
                  : 'bg-fantasy-dark border-fantasy-accent/40 text-fantasy-accent'
            }`}
          >
            {isBlocked ? (
              <ShieldAlert size={14} />
            ) : isRomantic ? (
              <Heart size={14} />
            ) : (
              <User size={14} />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5 flex-wrap">
              <h2
                className={`font-bold text-sm leading-tight truncate ${
                  isDeceased ? 'line-through text-gray-400' : 'text-gray-100'
                }`}
              >
                {npc.name}
              </h2>
              {sourceKind === 'acquaintance' && (
                <span className="text-[9.5px] px-1.5 py-0.5 rounded bg-slate-800/90 text-slate-300 border border-slate-600/60 font-semibold">
                  {t('contacts.acquaintance_badge', 'Acquaintance')}
                </span>
              )}
              {sourceKind === 'scene' && (
                <span className="text-[9.5px] px-1.5 py-0.5 rounded bg-emerald-950/70 text-emerald-300 border border-emerald-700/50 font-semibold">
                  {t('scene.scene_only_npc_badge', 'Just Met')}
                </span>
              )}
              {isBlocked && (
                <span className="text-[9px] px-1.5 py-0.5 bg-red-950/80 text-red-300 rounded font-bold uppercase border border-red-700/60">
                  🚫 {t('contacts.blocked_badge', 'Blocked')}
                </span>
              )}
              {isSpecialAgent && (
                <span className="text-[9px] px-1.5 py-0.5 bg-cyan-950/70 text-cyan-300 rounded font-bold uppercase border border-cyan-700/50">
                  ⚡ {t('codex.special_agent', 'Special Agent')}
                </span>
              )}
              {isCivilianTag && (
                <span className="text-[9px] px-1.5 py-0.5 bg-slate-900/80 text-slate-300 rounded font-semibold uppercase border border-slate-700/60">
                  {t('codex.civilian', 'Civilian')}
                </span>
              )}
              {isTalking && (
                <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded bg-purple-500/25 text-purple-200 font-bold">
                  {t('scene.talking', 'Talking')}
                </span>
              )}
              {npc.dialogue_mood?.mood_key && (
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
                    npc.dialogue_mood.mood_label || npc.dialogue_mood.mood_key
                  )}
                </span>
              )}
              {isDeceased && (
                <span className="text-[9px] px-1.5 py-0.5 bg-rose-950/80 text-rose-300 rounded font-bold uppercase border border-rose-700/60">
                  💀 {t('codex.deceased', 'Deceased')}
                </span>
              )}
              {isInParty && (
                <span className="text-[9px] px-1.5 py-0.5 bg-purple-950/60 text-purple-300 rounded font-bold uppercase border border-purple-800/40">
                  {t('codex.in_party', 'In Party')}
                </span>
              )}
              {isRomantic && (
                <span className="text-[9px] px-1 py-0.5 bg-pink-950/60 text-pink-300 rounded font-bold uppercase border border-pink-800/40">
                  {t('codex.romantic', 'Romantic')}
                </span>
              )}
              {npc.clothing_status && (
                <span className="text-[8.5px] font-mono px-1 py-0.5 rounded bg-black/60 text-gray-300 border border-neutral-700/60 leading-tight">
                  {npc.clothing_status}
                </span>
              )}
            </div>

            {(roleSubtitle || npc.workplace_label || npc.current_activity) && (
              <div className="flex flex-wrap items-center gap-1.5 mt-0.5 text-[11px] text-gray-400">
                {roleSubtitle && <span className="truncate">{roleSubtitle}</span>}
                {npc.workplace_label && (
                  <span className="inline-flex items-center gap-1 text-emerald-300/85 truncate">
                    <Briefcase size={10} className="shrink-0" />
                    <span>{npc.workplace_label}</span>
                  </span>
                )}
                {npc.current_activity && (
                  <span className="hk-chip text-[9.5px] bg-amber-500/15 text-amber-200">
                    🎯 {npc.current_activity}
                  </span>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          {onOpenInRoster && (
            <MotionButton
              onClick={() => onOpenInRoster(npc.name, rosterTarget)}
              className="hk-icon-btn h-7 px-2 text-[11px] font-semibold text-fantasy-accent hover:text-white gap-1"
              title={rosterLabel}
              aria-label={rosterLabel}
            >
              <RosterIcon size={13} className="shrink-0" />
              <span className="hidden sm:inline">{rosterLabel}</span>
            </MotionButton>
          )}
          {!isSheet && onClose && (
            <MotionButton
              onClick={onClose}
              className="hk-icon-btn h-7 min-w-7 text-gray-400 hover:text-white"
              aria-label={t('common.close', 'Close')}
              title={t('common.close', 'Close')}
            >
              <X size={15} />
            </MotionButton>
          )}
        </div>
      </div>

      {/* Scrollable Profile Body */}
      <div
        ref={scrollRef}
        className="flex-1 min-h-0 overflow-y-auto overscroll-contain [scrollbar-gutter:stable] custom-scrollbar p-3.5 space-y-2.5"
      >
        {/* Active Status Effects */}
        {activeStatusEffects.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {activeStatusEffects.map((eff, i) => (
              <StatusEffectBadge key={i} effect={eff} />
            ))}
          </div>
        )}

        {/* Relationship Tier + Affinity Meter */}
        <div className="space-y-1">
          <div className="flex items-center justify-between text-xs">
            <span className={`font-bold ${tier.color}`}>{tier.label}</span>
            <span className="font-mono text-[11px] font-semibold text-gray-300 tabular-nums">
              {score > 0 ? `+${score}` : score}
            </span>
          </div>
          <div className="h-1.5 w-full bg-black/80 rounded-full overflow-hidden border border-fantasy-border/40">
            <div
              className={`h-full ${tier.bg} transition-all duration-300`}
              style={{
                width: `${Math.max(5, Math.min(100, ((score + 100) / 400) * 100))}%`,
              }}
            />
          </div>
        </div>

        {/* Summary Identity Chips */}
        {(() => {
          const rawGrade = basic.grade || npc.grade;
          const showGradeChip = Boolean(rawGrade) && !isRedundantAgentTierGrade(rawGrade, isSpecialAgent);
          const hasAnyChip = Boolean(
            showGradeChip ||
              ageLabel ||
              club ||
              faction ||
              raceLabel ||
              genderInfo ||
              basic.age ||
              npc.age ||
              isDebugRevealed
          );
          if (!hasAnyChip) return null;
          return (
            <div className="flex flex-wrap items-center gap-1 text-[11px]">
              {showGradeChip && (
                <span className="px-1.5 py-0.5 rounded bg-purple-950/40 text-purple-300 border border-purple-800/40 text-[10.5px]">
                  {formatTitle(rawGrade)}
                </span>
              )}
              {ageLabel && (
                <span className="px-1.5 py-0.5 rounded bg-amber-950/40 text-amber-300 border border-amber-800/40 text-[10.5px]">
                  {ageLabel}
                </span>
              )}
              {club && (
                <span className="px-1.5 py-0.5 rounded bg-cyan-950/40 text-cyan-300 border border-cyan-800/40 text-[10.5px]">
                  Club: {formatTitle(club)}
                </span>
              )}
              {faction && (
                <span className="px-1.5 py-0.5 rounded bg-slate-900/60 text-slate-300 border border-slate-700/50 text-[10.5px]">
                  Faction: {formatTitle(faction)}
                </span>
              )}
              {raceLabel && (
                <span className="px-1.5 py-0.5 rounded bg-black/60 text-gray-300 border border-fantasy-border/40 text-[10.5px]">
                  {raceLabel}
                </span>
              )}
              {genderInfo && (
                <span className="px-1.5 py-0.5 rounded bg-black/60 text-gray-300 border border-fantasy-border/40 text-[10.5px]">
                  {genderInfo.symbol ? `${genderInfo.symbol} ` : ''}
                  {genderInfo.label}
                </span>
              )}
              {(basic.age || npc.age) && (
                <span className="px-1.5 py-0.5 rounded bg-black/60 text-gray-300 border border-fantasy-border/40 text-[10.5px]">
                  Age {basic.age || npc.age}
                </span>
              )}
              {isDebugRevealed && (
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-purple-950/80 text-purple-300 border border-purple-700/60 font-mono">
                  {t('codex.debug_revealed_badge', 'DEBUG: Full Profile Revealed')}
                </span>
              )}
            </div>
          );
        })()}

        {/* Full Read-Only 4-Tab Dossier */}
        <NpcDossierBody
          npc={npc}
          npcKey={npcKey}
          session={session}
          t={t}
          isBlocked={isBlocked}
          isDeceased={isDeceased}
          isInParty={isInParty}
          isSpecialAgent={isSpecialAgent}
          isCivilianTag={isCivilianTag}
          isDebugRevealed={isDebugRevealed}
          sourceKind={sourceKind}
          activeTab={activeTab}
          onTabChange={setActiveTab}
          topSlot={null}
          renderBulletPoints={renderBulletPoints}
          findLinkedPerson={findLinkedPerson}
          onJumpToPerson={handleJumpToPerson}
        />
      </div>
    </div>
  );
};

export default NpcProfileSideCard;
