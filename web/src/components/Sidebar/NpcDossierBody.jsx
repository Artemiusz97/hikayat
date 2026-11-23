import { Fragment, useRef } from 'react';
import { Lock, Scroll, Sparkles } from 'lucide-react';
import KnownRoutineCard from './KnownRoutineCard';
import KnownWardrobeCard from './KnownWardrobeCard';
import { formatAgeCategory, formatGender, formatRace, formatTitle } from '../../utils/npcDemographics';

export const DOSSIER_TABS = [
  { id: 'persona', icon: '👤', shortKey: 'contacts.tab_persona_short', shortLabel: 'Persona', fullKey: 'contacts.tab_persona', fullLabel: 'Persona' },
  { id: 'history', icon: '📜', shortKey: 'contacts.tab_history_short', shortLabel: 'History', fullKey: 'contacts.tab_history', fullLabel: 'Shared History' },
  { id: 'relations', icon: '🌳', shortKey: 'contacts.tab_relations_short', shortLabel: 'Relations', fullKey: 'contacts.tab_relations', fullLabel: 'Relations & Family' },
  { id: 'intimate', icon: '🔥', shortKey: 'contacts.tab_intimacy_short', shortLabel: 'Intimacy', fullKey: 'contacts.tab_intimacy', fullLabel: 'Intimate Dossier' },
];

export const isStudentNpc = (npc, basic = {}) => {
  if (npc?.is_student !== undefined) return Boolean(npc.is_student);
  const gradeStr = String(basic?.grade || npc?.grade || '').trim().toLowerCase();
  const srtStr = String(npc?.social_role_type || basic?.social_role_type || '').trim().toLowerCase();
  if (['citizen', 'adult', 'faculty', 'staff', 'civilian'].includes(gradeStr)) return false;
  if (['adult_service', 'faculty_staff'].includes(srtStr)) return false;
  if (['freshman', 'sophomore', 'junior', 'senior', 'student', 'classmate'].some(k => gradeStr.includes(k))) return true;
  if (srtStr === 'student_peer') return true;
  return false;
};

export const formatPersonEntity = (item) => {
  if (!item) return '';
  if (typeof item === 'string') return item;
  const name = item.name || item.title || 'Unknown';
  const role = item.role || item.closeness || item.type || item.grade || item.relationship_type || '';
  return role ? `${name} (${role})` : name;
};

const isEmptyAffil = (v) =>
  !v || ['none', 'unaffiliated', 'unknown', 'general'].includes(String(v).trim().toLowerCase());

// Club (school-only) and faction/agency are separate axes: student agents carry both.
export const resolveAffiliations = (npc, basic = {}) => {
  const isStudent = isStudentNpc(npc, basic);
  const club = isStudent && !isEmptyAffil(basic.club || npc?.club) ? String(basic.club || npc.club) : '';
  const rawFaction =
    npc?.faction_affiliation ||
    npc?.faction_name ||
    basic.faction_name ||
    basic.faction ||
    basic.affiliation ||
    npc?.affiliation ||
    '';
  const faction =
    !isEmptyAffil(rawFaction) && String(rawFaction).trim().toLowerCase() !== club.trim().toLowerCase()
      ? String(rawFaction)
      : '';
  return { isStudent, club, faction };
};

// Age group badge label, e.g. "Teen · Student", "Teen", "Adult".
export const resolveAgeGroupLabel = (npc, basic = {}, isStudent = false, t = null) => {
  const agInfo = formatAgeCategory(npc?.age_group || basic.age_group, t);
  if (!agInfo) return '';
  if (agInfo.key === 'teen' && isStudent) {
    const studentText = typeof t === 'function' ? t('scene.student_tag', 'Student') : 'Student';
    return `${agInfo.label} · ${studentText}`;
  }
  return agInfo.label;
};

const formatTraitLikeText = (item) => {
  if (!item) return '';
  if (typeof item === 'string') return item;
  return item.trait || item.preference || item.dislike || item.name || item.label || '';
};

const ROMANTIC_KEYWORDS = [
  'kiss', 'confess', 'date', 'intercourse', 'oral', 'manual', 'anal', 'virgin',
  'intimate', 'bedroom', 'made love', 'make love', 'slept together',
  'affectionate', 'tender', 'romantic', 'romance', 'caress', 'embrace', 'cuddle',
  'passionate', 'passion',
];

export const defaultBulletRenderer = (lines, t = null) => {
  if (!lines || !lines.length) return null;
  const unknownLabel = typeof t === 'function' ? t('common.unknown', 'Unknown') : 'Unknown';
  return (
    <div className="space-y-1">
      {lines.map((line, idx) => {
        let clean = String(line).replace(/^[•\-*]\s*/, '').trim();
        clean = clean.replace(/\bNude\s*\/\s*Beige\b/gi, 'Beige / Skin-Tone');
        const match = clean.match(/^\*\*([^*]+)\*\*:\s*(.*)$/) || clean.match(/^([^:]+):\s*(.*)$/);
        if (match) {
          const [, label, val] = match;
          const isUnknown = /^\*?unknown\*?$/i.test(val.trim());
          return (
            <div key={idx} className="leading-relaxed text-gray-300 text-xs">
              • <strong className="text-gray-100">{label}</strong>:{' '}
              {isUnknown ? (
                <span className="text-gray-500 italic">{unknownLabel}</span>
              ) : (
                <span>{val}</span>
              )}
            </div>
          );
        }
        return (
          <div key={idx} className="leading-relaxed text-gray-300 text-xs">
            • {clean}
          </div>
        );
      })}
    </div>
  );
};

const NpcDossierBody = ({
  npc,
  npcKey,
  session,
  t,
  isBlocked = false,
  isDeceased = false,
  isInParty = false,
  isSpecialAgent = false,
  isCivilianTag = false,
  isDebugRevealed = false,
  sourceKind = 'contact',
  activeTab = 'persona',
  onTabChange,
  topSlot = null,
  renderBulletPoints = defaultBulletRenderer,
  findLinkedPerson = null,
  renderLinkedPerson = null,
  onJumpToPerson = null,
}) => {
  const tabRefs = useRef({});
  const basic = npc?.basic_info || {};
  const appearance = npc?.appearance || {};
  const familyTree = npc?.family_tree || {};
  const relations = npc?.relations || {};
  const score = npc?.relationship_score ?? npc?.affinity_score ?? npc?.affinity ?? 0;
  const infoLevel = npc?.info_level ?? 0;
  const skillMod = npc?.skill_modifier ?? Math.floor(Math.max(0, score) / 20);
  const memories = npc?.intimate_memories || [];
  const traits = npc?.unlocked_traits || npc?.traits || [];
  const maskedSlot = t('social.masked_slot', '???');

  const rawDislikes = npc?.dislikes || basic.dislikes || [];
  const dislikes = rawDislikes
    .map(d => (typeof d === 'string' ? d : (d.dislike || d.name || '')))
    .filter(Boolean);
  const dislikeLowerSet = new Set(dislikes.map(d => d.toLowerCase().trim()));
  const dislikePrefixes = [
    'dislike', 'dislikes', 'hate', 'hates', 'fear', 'fears',
    'avoid', 'avoids', 'detest', 'detests', 'loathe', 'loathes',
    'resent', 'resents', 'resist', 'resists', 'disdain', 'disdains',
    'repulsed', 'repulses', 'averse',
  ];
  const rawPreferences = npc?.preferences || npc?.likes || [];
  const preferences = rawPreferences
    .map(p => (typeof p === 'string' ? p : (p.preference || p.name || '')))
    .filter(p => {
      if (!p) return false;
      const pLow = p.toLowerCase().trim();
      if (dislikeLowerSet.has(pLow)) return false;
      const firstWord = pLow.split(/\s+/)[0];
      if (dislikePrefixes.includes(firstWord)) return false;
      return true;
    });

  const rawGender = String(basic.gender || npc?.gender || appearance.gender || 'female').toLowerCase();
  const isMale =
    ['male', 'man', 'boy', 'lord', 'he', 'him', 'his'].some(kw => rawGender.includes(kw)) &&
    !['female', 'woman'].some(kw => rawGender.includes(kw));
  const isNsfwScenario = Boolean(
    session?.is_nsfw ||
    npc?.is_nsfw ||
    (session?.scenario && String(session.scenario).toLowerCase().includes('nsfw')) ||
    (Array.isArray(session?.scenario_tags) && session.scenario_tags.includes('nsfw'))
  );
  const isCombatDossierUnlocked =
    score >= 100 || isInParty || isDebugRevealed || Boolean(npc?.same_faction_colleague);

  const handleDossierTabKeyDown = (e) => {
    const idx = DOSSIER_TABS.findIndex(tb => tb.id === activeTab);
    if (idx === -1) return;
    let nextIdx = idx;
    if (e.key === 'ArrowRight') nextIdx = (idx + 1) % DOSSIER_TABS.length;
    else if (e.key === 'ArrowLeft') nextIdx = (idx - 1 + DOSSIER_TABS.length) % DOSSIER_TABS.length;
    else if (e.key === 'Home') nextIdx = 0;
    else if (e.key === 'End') nextIdx = DOSSIER_TABS.length - 1;
    else return;
    e.preventDefault();
    const nextTab = DOSSIER_TABS[nextIdx];
    onTabChange?.(nextTab.id);
    tabRefs.current[`${npcKey}:${nextTab.id}`]?.focus();
  };

  const fallbackRenderLinkedPerson = (item, textClassName = '') => {
    if (!item) return null;
    if (typeof item === 'object' && item.locked) {
      return <span className="text-gray-500 italic">{item.message}</span>;
    }
    const label = formatPersonEntity(item);
    const matchObj = findLinkedPerson ? findLinkedPerson(item) : null;
    if (!matchObj || !onJumpToPerson) {
      return <span className={textClassName}>{label}</span>;
    }
    const rawName = typeof item === 'string' ? label : (item.name || item.title || label);
    const roleSuffix =
      typeof item === 'object'
        ? (item.role || item.closeness || item.type || item.grade || item.relationship_type || '')
        : '';
    return (
      <span className={textClassName}>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onJumpToPerson(matchObj);
          }}
          className="underline decoration-dotted underline-offset-2 hover:text-fantasy-accent transition-colors cursor-pointer font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fantasy-accent rounded-xs"
        >
          {rawName}
        </button>
        {roleSuffix ? ` (${roleSuffix})` : ''}
      </span>
    );
  };

  const linkPerson = renderLinkedPerson || fallbackRenderLinkedPerson;

  const isDmLocked = npc?.can_dm === false;
  const affForAge = resolveAffiliations(npc, basic);
  const ageGroupBadge = resolveAgeGroupLabel(npc, basic, affForAge.isStudent, t);

  return (
    <div className="space-y-3 pt-2.5 border-t border-fantasy-border/40 text-xs text-gray-300">
      {isBlocked && (
        <div className="p-2.5 rounded-lg border border-red-800/60 bg-red-950/35 text-red-200 text-[11px] leading-snug">
          🚫 {t('phone.blocked_notice', 'This contact has blocked your number due to hostility. Reconcile with them in person first.')}
        </div>
      )}

      {sourceKind === 'acquaintance' && (
        <div className="p-2 rounded bg-fantasy-accent/10 border border-fantasy-accent/30 text-[11px] text-amber-100/90 leading-snug flex items-start gap-1.5">
          <Sparkles size={12} className="text-fantasy-accent shrink-0 mt-0.5" />
          <span>
            {t(
              'contacts.promotion_hint',
              'Promote to Saved Contacts by reaching +15 Affinity, -10 Rivalry, exchanging numbers in person, forming a quest link, or recruiting them into your party.'
            )}
          </span>
        </div>
      )}

      {sourceKind === 'acquaintance' && isDmLocked && (
        <div className="p-2 rounded bg-neutral-900/70 border border-neutral-700/60 text-[11px] text-gray-400 leading-snug flex items-start gap-1.5">
          <Lock size={12} className="text-gray-400 shrink-0 mt-0.5" />
          <span>
            {t(
              'contacts.dm_locked_tooltip',
              'Direct Messaging is locked. Ask for their number in person or connect via PeerPulse first; Affinity alone does not unlock DMs.'
            )}
          </span>
        </div>
      )}

      {topSlot}

      {/* Anomalous Incursions: Operative Combat Dossier */}
      {isSpecialAgent && (() => {
        const agentTier = npc.agent_tier || basic.agent_tier || 1;
        const rankTitle = npc.rank_title || basic.rank_title || `Tier ${agentTier} Operative`;
        const agentClass = npc.agent_class || basic.agent_class || basic.role || 'Special Agent';
        const cMaxHp = npc.combat_max_hp ?? 130;
        const cHp = npc.combat_hp ?? cMaxHp;
        const cMaxMp = npc.combat_max_mp ?? 60;
        const cMp = npc.combat_mp ?? cMaxMp;
        const wName = npc.weapon_profile?.name || '';
        const abilities = (
          isDebugRevealed
            ? (npc.debug_innate_ability_details || npc.innate_ability_details)
            : npc.innate_ability_details
        ) || [];

        return (
          <div className="bg-cyan-950/20 border border-cyan-800/50 rounded-lg p-2.5 space-y-2">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <span className="text-[11px] font-bold text-cyan-300 uppercase tracking-wider flex items-center gap-1">
                <span>⚡</span>
                <span>{t('codex.operative_dossier', 'Operative Combat Dossier')}</span>
              </span>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-cyan-950/70 text-cyan-200 border border-cyan-700/50 font-semibold">
                Tier {agentTier} • {rankTitle}
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-1.5 text-[10.5px]">
              <span className="px-1.5 py-0.5 rounded bg-black/60 text-gray-200 border border-fantasy-border/50">
                Class: <strong className="text-white">{agentClass}</strong>
              </span>
              <span className="px-1.5 py-0.5 rounded bg-red-950/40 text-red-300 border border-red-800/40 font-mono">
                ❤️ {cHp}/{cMaxHp} HP
              </span>
              <span className="px-1.5 py-0.5 rounded bg-blue-950/40 text-blue-300 border border-blue-800/40 font-mono">
                💧 {cMp}/{cMaxMp} MP
              </span>
              {wName && (
                <span className="px-1.5 py-0.5 rounded bg-amber-950/35 text-amber-200 border border-amber-800/40">
                  ⚔️ {wName}
                </span>
              )}
            </div>

            {isCombatDossierUnlocked && abilities.length > 0 ? (
              <div className="space-y-1 pt-1 border-t border-cyan-900/40">
                <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block">
                  {t('codex.innate_abilities', 'Innate Special Abilities')}
                </span>
                <div className="grid grid-cols-1 gap-1">
                  {abilities.map((ab, abIdx) => (
                    <div
                      key={ab.id || abIdx}
                      className={`p-1.5 rounded border text-[10.5px] leading-snug ${
                        ab.is_ultimate
                          ? 'bg-purple-950/35 border-purple-700/50 text-purple-100'
                          : 'bg-black/50 border-fantasy-border/40 text-gray-300'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-1.5">
                        <span className="font-semibold text-gray-100 flex items-center gap-1">
                          <span>{ab.emoji || '✨'}</span>
                          <span>{ab.name}</span>
                          {ab.is_ultimate && (
                            <span className="text-[8.5px] px-1 py-0.5 rounded bg-purple-900/80 text-purple-200 border border-purple-600/50 font-mono uppercase">
                              Ultimate
                            </span>
                          )}
                        </span>
                        <span className="text-[9.5px] font-mono text-cyan-300 shrink-0">
                          {ab.is_ultimate ? '3 Pips • 0 MP' : `${ab.mp_cost ?? 10} MP`}
                        </span>
                      </div>
                      {ab.desc && <p className="text-[10px] text-gray-400 mt-0.5">{ab.desc}</p>}
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-[10px] text-gray-400 italic pt-1 border-t border-cyan-900/40">
                🔒 {t('codex.abilities_locked_note', 'Reach Friend standing (100+ Affinity) or recruit into your party to reveal innate abilities.')}
              </p>
            )}
          </div>
        );
      })()}

      {isCivilianTag && (
        <div
          className={`p-2.5 rounded-lg border space-y-1 ${
            isDeceased
              ? 'bg-rose-950/25 border-rose-800/50 text-rose-200'
              : 'bg-slate-950/60 border-slate-700/60 text-slate-300'
          }`}
        >
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <span className="text-[11px] font-bold uppercase tracking-wider flex items-center gap-1">
              <span>{isDeceased ? '💀' : '👤'}</span>
              <span>{t('codex.civilian_classification', 'Civilian Classification')}</span>
            </span>
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-black/50 text-gray-300 border border-slate-700/50">
              100 HP • 0 MP (Unawakened)
            </span>
          </div>
          <p className="text-[10.5px] text-gray-400 leading-snug">
            {isDeceased
              ? t('codex.civilian_deceased_note', 'Perished permanently during an anomalous incursion due to lacking innate mana protection.')
              : t('codex.civilian_party_note', 'Mundane citizen with no mana or special abilities. Eligible as a Contact, but cannot be recruited into your field party.')}
          </p>
        </div>
      )}

      {/* Dossier Folder Tabs */}
      <div
        role="tablist"
        aria-label={`${npc?.name || 'NPC'} dossier sections`}
        onKeyDown={handleDossierTabKeyDown}
        className="grid grid-cols-4 border-b border-fantasy-border/70 pt-1.5 px-1 bg-black/60 rounded-t-lg gap-1 items-end select-none"
      >
        {DOSSIER_TABS.map(tb => {
          const isActive = activeTab === tb.id;
          const shortLbl = t(tb.shortKey, tb.shortLabel);
          const fullLbl = t(tb.fullKey, tb.fullLabel);
          return (
            <button
              key={tb.id}
              ref={(el) => {
                tabRefs.current[`${npcKey}:${tb.id}`] = el;
              }}
              type="button"
              role="tab"
              aria-selected={isActive}
              tabIndex={isActive ? 0 : -1}
              title={fullLbl}
              onClick={(e) => {
                e.stopPropagation();
                onTabChange?.(tb.id);
              }}
              className={`min-w-0 py-2 px-1 text-xs font-bold transition-all flex items-center justify-center gap-1 rounded-t-md relative cursor-pointer ${
                isActive
                  ? 'bg-black/40 text-fantasy-accent border-t-2 border-t-fantasy-accent border-x border-fantasy-border/70 border-b-black/40 -mb-px z-10 shadow-sm'
                  : 'bg-black/25 text-gray-400 hover:text-gray-200 hover:bg-black/40 border-t border-x border-transparent border-b border-b-fantasy-border/70'
              }`}
            >
              <span className="text-xs shrink-0">{tb.icon}</span>
              <span className="truncate text-[11px] font-semibold">
                <span className="hidden xl:inline">{fullLbl}</span>
                <span className="xl:hidden">{shortLbl}</span>
              </span>
            </button>
          );
        })}
      </div>

      {/* Folder Panel Content Body */}
      <div role="tabpanel" className="bg-black/40 border-x border-b border-fantasy-border/70 rounded-b-lg p-3 text-xs -mt-px space-y-3">
        {/* SUBTAB 1: PERSONA */}
        {activeTab === 'persona' && (() => {
          const eyeColor = appearance.eye_color || appearance.eyes;
          const hairColor = appearance.hair_color;
          const hairLength = appearance.hair_length;
          const hairStyle = appearance.hair_style;
          const coatColor =
            appearance.coat_color ||
            appearance.fur_color ||
            appearance.scale_color ||
            appearance.feather_color ||
            appearance.coat;
          const skinColor = appearance.skin_color || appearance.skin;
          const skinType = appearance.skin_type;
          const stature = appearance.stature || appearance.height;
          const physique = appearance.physique;
          const distinctiveFeatures = appearance.distinctive_features || appearance.features || appearance.marks;
          const outfitStyle = appearance.outfit_style || appearance.outfit || appearance.clothing;
          const mannerisms = basic.mannerisms || appearance.mannerisms || npc?.mannerisms;

          const hairParts = [hairLength ? formatTitle(hairLength) : null, hairStyle ? formatTitle(hairStyle) : null]
            .filter(Boolean)
            .join(', ');
          const hairDesc = hairParts
            ? (hairColor ? `${hairParts} • ${formatTitle(hairColor)}` : hairParts)
            : (hairColor ? formatTitle(hairColor) : '');

          let coatOrSkin = '';
          if (coatColor) {
            coatOrSkin = formatTitle(coatColor) + (skinType ? ` (${formatTitle(skinType)})` : '');
          } else if (skinColor) {
            coatOrSkin = formatTitle(skinColor) + (skinType ? ` (${formatTitle(skinType)})` : '');
          } else if (skinType) {
            coatOrSkin = formatTitle(skinType);
          }

          const buildParts = [stature ? formatTitle(stature) : null, physique ? formatTitle(physique) : null].filter(Boolean);
          const buildDesc = buildParts.join(' • ');
          const featuresDesc = distinctiveFeatures ? formatTitle(distinctiveFeatures) : '';
          const outfitDesc = !npc?.known_wardrobe && outfitStyle ? formatTitle(outfitStyle) : '';

          const canShowMaleSize =
            isMale &&
            (infoLevel >= 3 || isDebugRevealed) &&
            Boolean(appearance.penis_size) &&
            appearance.penis_size.toLowerCase() !== 'unknown';
          const hasPhysicalAttributes = Boolean(
            eyeColor ||
            hairDesc ||
            coatOrSkin ||
            buildDesc ||
            featuresDesc ||
            outfitDesc ||
            (isNsfwScenario && (isMale ? canShowMaleSize : (appearance.breast_size || !isMale)))
          );
          const { club, faction } = resolveAffiliations(npc, basic);

          return (
            <div className="space-y-2.5">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-xs px-2 py-0.5 rounded bg-fantasy-accent/15 text-fantasy-accent border border-fantasy-accent/30 font-mono font-medium">
                  {t('contacts.info_level_badge', 'Info Level: {{level}}/3', { level: infoLevel })}
                </span>
                <span className="text-xs px-2 py-0.5 rounded bg-emerald-950/50 text-emerald-300 border border-emerald-700/40 font-mono font-medium">
                  {t('contacts.skill_modifier_badge', 'Skill Modifier: +{{mod}}', { mod: skillMod })}
                </span>
                {(basic.race || npc?.race) && (
                  <span className="text-xs px-2 py-0.5 rounded bg-black/60 text-gray-300 border border-fantasy-border/50">
                    {formatRace(basic.race || npc?.race, t)}
                  </span>
                )}
                {(basic.gender || npc?.gender) && (() => {
                  const rawG = basic.gender || npc?.gender;
                  const gInfo = formatGender(rawG, t);
                  return (
                    <span className="text-xs px-2 py-0.5 rounded bg-black/60 text-gray-300 border border-fantasy-border/50">
                      {gInfo ? `${gInfo.symbol ? `${gInfo.symbol} ` : ''}${gInfo.label}` : formatTitle(rawG)}
                    </span>
                  );
                })()}
                {(basic.age || npc?.age) && (
                  <span className="text-xs px-2 py-0.5 rounded bg-black/60 text-gray-300 border border-fantasy-border/50">
                    {t('contacts.age_prefix', 'Age {{age}}', { age: basic.age || npc?.age })}
                  </span>
                )}
                {(basic.grade || npc?.grade) && (
                  <span className="text-xs px-2 py-0.5 rounded bg-purple-950/40 text-purple-300 border border-purple-800/40">
                    {formatTitle(basic.grade || npc?.grade)}
                  </span>
                )}
                {ageGroupBadge && (
                  <span className="text-xs px-2 py-0.5 rounded bg-amber-950/40 text-amber-300 border border-amber-800/40">
                    {ageGroupBadge}
                  </span>
                )}
                {club && (
                  <span className="text-xs px-2 py-0.5 rounded bg-cyan-950/40 text-cyan-300 border border-cyan-800/40">
                    {t('contacts.club_prefix', 'Club:')} {formatTitle(club)}
                  </span>
                )}
                {faction && (
                  <span className="text-xs px-2 py-0.5 rounded bg-slate-900/60 text-slate-300 border border-slate-700/50">
                    {t('contacts.faction_prefix', 'Faction:')} {formatTitle(faction)}
                  </span>
                )}
              </div>

              {hasPhysicalAttributes && (() => {
                const hasVitals = Boolean(
                  eyeColor || buildDesc || (isNsfwScenario && (isMale ? canShowMaleSize : (appearance.breast_size || !isMale)))
                );
                const hasDetails = Boolean(hairDesc || coatOrSkin || featuresDesc || outfitDesc);

                return (
                  <div className="bg-black/40 p-2.5 rounded-lg border border-fantasy-border/40 text-xs space-y-2.5">
                    <span className="text-xs font-bold text-gray-400 uppercase tracking-wider block flex items-center gap-1.5">
                      {t('contacts.physical_appearance', '✨ Physical Appearance')}
                    </span>

                    {hasVitals && (
                      <div className={`flex flex-wrap items-center gap-1.5 ${hasDetails ? 'pb-2 border-b border-fantasy-border/25' : ''}`}>
                        {eyeColor && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-black/60 border border-fantasy-border/50 text-gray-300">
                            <span className="text-gray-400">{t('contacts.eyes', '👁️ Eyes:')}</span>
                            <strong className="text-gray-100 font-medium">{formatTitle(eyeColor)}</strong>
                          </span>
                        )}
                        {buildDesc && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-black/60 border border-fantasy-border/50 text-gray-300">
                            <span className="text-gray-400">{t('contacts.build', '📏 Build:')}</span>
                            <strong className="text-gray-100 font-medium">{buildDesc}</strong>
                          </span>
                        )}
                        {isNsfwScenario && !isMale && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-pink-950/40 border border-pink-800/50 text-pink-300">
                            <span className="text-pink-400 font-medium">{t('contacts.breast_size', '🔞 Breast Size:')}</span>
                            <strong className="text-pink-100 font-medium">
                              {formatTitle(appearance.breast_size || 'Modest B-Cup')}
                            </strong>
                            {Boolean(npc?.intimate_dossier_revealed || npc?.debug_revealed) && appearance.asset_texture && (
                              <span className="text-pink-200 text-[10px] italic font-normal">({appearance.asset_texture})</span>
                            )}
                          </span>
                        )}
                        {isNsfwScenario && canShowMaleSize && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-purple-950/40 border border-purple-800/50 text-purple-300">
                            <span className="text-purple-400 font-medium">{t('contacts.penis_size', '🔞 Penis Size:')}</span>
                            <strong className="text-purple-100 font-medium">
                              {formatTitle(appearance.penis_size)}
                            </strong>
                            {Boolean(npc?.intimate_dossier_revealed || npc?.debug_revealed) && appearance.asset_texture && (
                              <span className="text-purple-200 text-[10px] italic font-normal">({appearance.asset_texture})</span>
                            )}
                          </span>
                        )}
                      </div>
                    )}

                    {hasDetails && (
                      <div className="space-y-1.5 text-gray-300">
                        {hairDesc && (
                          <div className="leading-snug">
                            <span className="text-gray-400 font-medium">{t('contacts.hair', '💇 Hair:')} </span>
                            <strong className="text-gray-200 font-medium">{hairDesc}</strong>
                          </div>
                        )}
                        {coatOrSkin && (
                          <div className="leading-snug">
                            <span className="text-gray-400 font-medium">{t('contacts.coat_skin', '🐾 Coat / Skin:')} </span>
                            <strong className="text-gray-200 font-medium">{coatOrSkin}</strong>
                          </div>
                        )}
                        {featuresDesc && (
                          <div className="leading-snug">
                            <span className="text-gray-400 font-medium">{t('contacts.features', '✨ Features:')} </span>
                            <strong className="text-gray-200 font-medium">{featuresDesc}</strong>
                          </div>
                        )}
                        {outfitDesc && (
                          <div className="leading-snug">
                            <span className="text-gray-400 font-medium">{t('contacts.outfit', '👔 Outfit:')} </span>
                            <span className="text-gray-300">{outfitDesc}</span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })()}

              {mannerisms && (
                <div className="bg-black/40 p-2.5 rounded-lg border border-fantasy-border/40 text-xs text-gray-300 leading-relaxed">
                  <span className="text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1">
                    {t('contacts.mannerisms', '🎭 Mannerisms')}
                  </span>
                  {mannerisms}
                </div>
              )}

              {(basic.description || appearance.summary || npc?.description) && (
                <div className="bg-black/40 p-2.5 rounded-lg border border-fantasy-border/40 text-xs text-gray-300 leading-relaxed">
                  <span className="text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1">
                    {t('contacts.background_notes', '📖 Background & Notes')}
                  </span>
                  {basic.description || appearance.summary || npc?.description}
                </div>
              )}

              <KnownWardrobeCard npc={npc} showDebug={isDebugRevealed} t={t} />

              <KnownRoutineCard npc={npc} t={t} />

              {traits.length > 0 && (
                <div>
                  <span className="text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1">
                    {t('contacts.known_traits', 'Known Traits')}
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {traits.map((tr, idx) => {
                      const text = formatTraitLikeText(tr) || maskedSlot;
                      const isMasked = text === maskedSlot || text.includes('???');
                      return (
                        <span
                          key={idx}
                          className={`text-xs px-2 py-0.5 rounded border ${
                            isMasked
                              ? 'bg-black/40 text-gray-500 border-dashed border-neutral-700 font-mono'
                              : 'bg-black/60 text-gray-300 border-fantasy-border'
                          }`}
                        >
                          {text}
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}

              {preferences.length > 0 && (
                <div>
                  <span className="text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1">
                    {t('contacts.likes_preferences', 'Likes & Preferences')}
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {preferences.map((p, idx) => {
                      const text = formatTraitLikeText(p) || maskedSlot;
                      const isMasked = text === maskedSlot || text.includes('???');
                      return (
                        <span
                          key={idx}
                          className={`text-xs px-2 py-0.5 rounded border ${
                            isMasked
                              ? 'bg-black/40 text-gray-500 border-dashed border-neutral-700 font-mono'
                              : 'bg-cyan-950/40 text-cyan-300 border-cyan-800/40'
                          }`}
                        >
                          {text}
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}

              {dislikes.length > 0 && (
                <div>
                  <span className="text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1">
                    {t('contacts.dislikes_pet_peeves', 'Dislikes & Pet Peeves')}
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {dislikes.map((d, idx) => {
                      const text = formatTraitLikeText(d) || maskedSlot;
                      const isMasked = text === maskedSlot || text.includes('???');
                      return (
                        <span
                          key={idx}
                          className={`text-xs px-2 py-0.5 rounded border ${
                            isMasked
                              ? 'bg-black/40 text-gray-500 border-dashed border-neutral-700 font-mono'
                              : 'bg-red-950/40 text-red-300 border-red-800/40'
                          }`}
                        >
                          {text}
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          );
        })()}

        {/* SUBTAB 2: SHARED HISTORY */}
        {activeTab === 'history' && (() => {
          const recentMemories = Array.isArray(npc?.recent_memories)
            ? npc.recent_memories
            : (Array.isArray(npc?.rel_history) ? npc.rel_history : []);

          return (
            <div className="space-y-3">
              <div className="flex items-center justify-between border-b border-fantasy-border/30 pb-2">
                <span className="text-xs font-bold text-amber-400 uppercase tracking-wider flex items-center gap-1.5">
                  <Scroll size={13} />
                  <span>{t('contacts.recent_history', 'Recent Shared Interactions & History')}</span>
                </span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-black/60 text-gray-400 border border-fantasy-border/40 font-mono">
                  {recentMemories.length} {recentMemories.length === 1 ? t('contacts.event_singular', 'Event') : t('contacts.event_plural', 'Events')}
                </span>
              </div>

              {recentMemories.length === 0 ? (
                <div className="py-6 text-center text-gray-500 italic">
                  {t('contacts.no_shared_history', 'No shared interactions recorded yet. Spend time with {{name}} to build your shared history.', { name: npc?.name || t('contacts.this_character', 'this character') })}
                </div>
              ) : (
                <div className="space-y-2">
                  {recentMemories.map((mem, idx) => {
                    const text = typeof mem === 'string' ? mem : (mem?.memory_fact || mem?.summary || mem?.event || mem?.text || '');
                    if (!text) return null;
                    return (
                      <div
                        key={idx}
                        className="flex items-start gap-2.5 p-2 rounded bg-black/50 border border-fantasy-border/30 hover:border-amber-500/40 transition-colors"
                      >
                        <span className="mt-0.5 text-amber-400 font-mono text-[10px] bg-amber-950/40 px-1.5 py-0.5 rounded border border-amber-800/40 shrink-0">
                          #{recentMemories.length - idx}
                        </span>
                        <div className="text-gray-200 leading-relaxed text-xs">
                          {text}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })()}

        {/* SUBTAB 3: RELATIONS & FAMILY */}
        {activeTab === 'relations' && (() => {
          const disRel = npc?.disclosed_relations || {};
          const romData = disRel.romance || relations.romance || {};
          const famData = disRel.family || {};
          const friendsList = disRel.friends?.members || relations.friends || [];
          const rivalsList = disRel.rivals?.members || relations.rivals || [];

          return (
            <div className="space-y-3">
              <div>
                <span className="text-xs font-bold text-fantasy-accent uppercase tracking-wider block mb-1.5 flex items-center gap-1.5">
                  {t('contacts.immediate_family_tree', '👨‍👩‍👧‍👦 Immediate Family Tree')}
                </span>
                {famData.members && famData.members.length > 0 ? (
                  <div className="space-y-1.5">
                    {famData.members.map((mem, i) => {
                      const rel = mem.relation || 'Relative';
                      const rEmoji = rel.includes('Father') ? '👨' : rel.includes('Mother') ? '👩' : rel.includes('Brother') ? '👦' : rel.includes('Sister') ? '👧' : '👤';
                      const statusDot = (mem.status || 'Alive').toLowerCase() === 'alive' ? '🟢' : '💀';
                      const isParent = rel.includes('Father') || rel.includes('Mother') || rel.includes('Parent');
                      const matchedFam = findLinkedPerson ? findLinkedPerson(mem) : null;
                      return (
                        <div key={i} className="text-gray-300 leading-snug">
                          • {rEmoji} <strong>{rel}</strong>:{' '}
                          {matchedFam && onJumpToPerson ? (
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                onJumpToPerson(matchedFam);
                              }}
                              className="underline decoration-dotted underline-offset-2 hover:text-fantasy-accent transition-colors cursor-pointer font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fantasy-accent rounded-xs"
                            >
                              {mem.name}
                            </button>
                          ) : (
                            <span>{mem.name}</span>
                          )}{' '}
                          {mem.race ? `(${formatRace(mem.race, t)})` : ''} — {statusDot}{' '}
                          {!isParent && (mem.occupation || mem.grade) ? (
                            <span className="italic text-gray-400">— {mem.occupation || mem.grade}</span>
                          ) : mem.occupation ? (
                            <span className="italic text-gray-400">— {mem.occupation}</span>
                          ) : (
                            ''
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : famData.locked_message ? (
                  <p className="text-gray-400 italic text-xs leading-relaxed">{famData.locked_message}</p>
                ) : familyTree.parents?.length > 0 || familyTree.siblings?.length > 0 || (Array.isArray(familyTree) && familyTree.length > 0) ? (
                  <div className="space-y-1.5">
                    {Array.isArray(familyTree) ? (
                      familyTree.map((mem, i) => (
                        <div key={i} className="text-gray-300 leading-snug">
                          • <strong>{linkPerson(mem.name || mem)}</strong> {mem.relation ? `(${mem.relation})` : ''} {mem.occupation ? `— ${mem.occupation}` : ''}
                        </div>
                      ))
                    ) : (
                      <>
                        {familyTree.parents?.map((p, i) => (
                          <div key={`p-${i}`} className="text-gray-300 leading-snug">
                            • Parent: <strong>{linkPerson(typeof p === 'string' ? p : p.name)}</strong> {p.occupation ? `(${p.occupation})` : ''} {p.status ? `[${p.status}]` : ''}
                          </div>
                        ))}
                        {familyTree.siblings?.map((s, i) => (
                          <div key={`s-${i}`} className="text-gray-300 leading-snug">
                            • Sibling: <strong>{linkPerson(typeof s === 'string' ? s : s.name)}</strong> {s.occupation || s.grade ? `(${s.occupation || s.grade})` : ''} {s.status ? `[${s.status}]` : ''}
                          </div>
                        ))}
                      </>
                    )}
                  </div>
                ) : (
                  <p className="text-gray-500 italic text-xs">{t('contacts.no_family', 'No family records uncovered yet.')}</p>
                )}
              </div>

              <div className="pt-2 border-t border-fantasy-border/30 space-y-1.5">
                <span className="text-xs font-bold text-pink-400 uppercase tracking-wider block">
                  {t('contacts.romantic_standing', '💖 Romantic Standing')}
                </span>
                <div className="space-y-1 leading-relaxed">
                  <div>
                    • <strong className="text-gray-200">{t('contacts.current_status', 'Current Status')}</strong>:{' '}
                    {romData.current_partner ? (
                      <span className="text-pink-300 font-semibold">
                        💖 {linkPerson(romData.current_partner, 'text-pink-300 font-semibold')}
                      </span>
                    ) : (
                      <span className="text-gray-300 font-medium">
                        {romData.status || (relations.current_partner ? t('contacts.in_relationship', 'In a Relationship') : t('contacts.single', 'Single'))}
                      </span>
                    )}
                  </div>

                  {romData.secret_partner && (
                    <div>
                      • <strong className="text-gray-200">{t('contacts.secret_affair', 'Secret Affair')}</strong>:{' '}
                      {romData.secret_partner.locked ? (
                        <span className="text-gray-500 italic">{romData.secret_partner.message}</span>
                      ) : (
                        <span className="text-rose-400 font-semibold">
                          🤫 {linkPerson(romData.secret_partner, 'text-rose-400 font-semibold')}
                        </span>
                      )}
                    </div>
                  )}

                  <div>
                    • <strong className="text-gray-200">{t('contacts.past_ex_partners', 'Past Ex-Partner(s)')}</strong>:{' '}
                    {romData.ex_partners && romData.ex_partners.length > 0 ? (
                      <span className="text-gray-300">
                        💔{' '}
                        {romData.ex_partners.map((p, idx) => (
                          <Fragment key={idx}>
                            {idx > 0 ? ', ' : ''}
                            {linkPerson(p)}
                          </Fragment>
                        ))}
                      </span>
                    ) : romData.revealed || infoLevel >= 2 || isDebugRevealed ? (
                      <span className="text-gray-400 italic">{t('contacts.no_ex_partners', 'None (No prior romantic partners)')}</span>
                    ) : (
                      <span className="text-gray-500 italic">{t('contacts.locked_info_level', '🔒 Locked (Requires Info Level 2+)')}</span>
                    )}
                  </div>
                </div>
              </div>

              <div className="pt-2 border-t border-fantasy-border/30 space-y-1.5">
                <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider block">
                  {t('contacts.friends_header', '🤝 Friends')}
                </span>
                {friendsList.length > 0 ? (
                  <div className="space-y-1">
                    {friendsList.map((f, i) => (
                      <div key={i} className="text-cyan-300 font-medium">
                        • 🤝 {linkPerson(f, 'text-cyan-300 font-medium')}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-gray-500 italic text-xs">{t('contacts.no_friends', 'No close friends recorded.')}</p>
                )}
              </div>

              <div className="pt-2 border-t border-fantasy-border/30 space-y-1.5">
                <span className="text-xs font-bold text-amber-400 uppercase tracking-wider block">
                  {t('contacts.rivals_header', '⚔️ Rivals')}
                </span>
                {rivalsList.length > 0 ? (
                  <div className="space-y-1">
                    {rivalsList.map((r, i) => (
                      <div key={i} className="text-amber-300 font-medium">
                        • ⚔️ {linkPerson(r, 'text-amber-300 font-medium')}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-gray-500 italic text-xs">{t('contacts.no_rivals', 'No known rivals recorded.')}</p>
                )}
              </div>

              <div className="text-[11px] text-gray-500 font-mono pt-1.5 border-t border-fantasy-border/20">
                {t('contacts.disclosure_footer_relations', 'Information Disclosure Level: {{level}}/3 • Social Graph & Lineage Dossier', { level: infoLevel })}{isDebugRevealed ? ' • [🛠️ DEBUG: Revealed]' : ''}
              </div>
            </div>
          );
        })()}

        {/* SUBTAB 4: INTIMATE & HISTORY */}
        {activeTab === 'intimate' && (() => {
          const intSec = npc?.intimate_sections || {};
          const hasSections = Boolean(intSec.anatomy && intSec.dynamic);

          const rawGen = (basic.gender || npc?.gender || '').toLowerCase();
          const isMaleNpc =
            ['male', 'man', 'boy', 'lord', 'he', 'him', 'his'].some(kw => rawGen.includes(kw)) &&
            !['female', 'woman', 'girl', 'lady'].some(kw => rawGen.includes(kw));
          const bSize = appearance.breast_size || 'Modest B-Cup';
          const bTitle = bSize.charAt(0).toUpperCase() + bSize.slice(1);
          const pSize = appearance.penis_size || 'Average';
          const pTitle = pSize.charAt(0).toUpperCase() + pSize.slice(1);
          const sizeDisplay = isMaleNpc ? ((infoLevel >= 3 || isDebugRevealed) ? pTitle : 'Unknown') : bTitle;

          const iExpDisp =
            appearance.experience && appearance.experience.toLowerCase() !== 'unknown'
              ? appearance.experience
              : (infoLevel >= 3 || isDebugRevealed
                  ? (appearance.intercourse_experience === 'virgin' ? 'Virgin' : 'Non-Virgin')
                  : 'Unknown');
          const oExpDisp = infoLevel >= 3 || isDebugRevealed ? (appearance.oral_experience || 'Inexperienced') : 'Unknown';
          const mExpDisp = infoLevel >= 3 || isDebugRevealed ? (appearance.manual_experience || 'Inexperienced') : 'Unknown';
          const aExpDisp = infoLevel >= 3 || isDebugRevealed ? (appearance.anal_experience || 'Inexperienced') : 'Unknown';

          const underObj = typeof appearance.undergarments === 'object' && appearance.undergarments !== null ? appearance.undergarments : {};
          const rawBra =
            underObj.bra ||
            appearance.bra ||
            (typeof appearance.undergarments === 'string' && appearance.undergarments.includes('Bra:')
              ? appearance.undergarments.split('•')[0]?.replace('Bra:', '').trim()
              : '');
          const rawUnd =
            underObj.underwear ||
            appearance.underwear ||
            (typeof appearance.undergarments === 'string' && appearance.undergarments.includes('Underwear:')
              ? appearance.undergarments.split('•')[1]?.replace('Underwear:', '').trim()
              : (typeof appearance.undergarments === 'string' ? appearance.undergarments : ''));
          const braVal = rawBra ? rawBra.replace(/\bNude\s*\/\s*Beige\b/gi, 'Beige / Skin-Tone') : '';
          const undVal = rawUnd ? rawUnd.replace(/\bNude\s*\/\s*Beige\b/gi, 'Beige / Skin-Tone') : '';

          const isIntimateRevealed = npc?.intimate_dossier_revealed !== false && (infoLevel >= 3 || isDebugRevealed);
          const isHistoryUnlocked = isIntimateRevealed || Boolean(npc?.history_revealed) || isDebugRevealed;
          const hasHistoryEntries = Boolean(
            npc?.past_intimate_history || (npc?.past_intimate_entries && npc.past_intimate_entries.length > 0)
          );
          const isRomanticMilestone = (m) => {
            if (!m) return false;
            const s = String(typeof m === 'string' ? m : (m.summary || m.event || '')).toLowerCase();
            if (s.startsWith('past history:')) return false;
            if (s.includes('[romance]') || s.includes('[intimate]')) return true;
            return ROMANTIC_KEYWORDS.some(kw => s.includes(kw));
          };
          const sharedMilestones =
            npc?.shared_romantic_milestones && npc.shared_romantic_milestones.length > 0
              ? npc.shared_romantic_milestones
              : memories.filter(isRomanticMilestone);

          return (
            <div className="space-y-3">
              <div>
                <span className="text-xs font-bold text-pink-400 uppercase tracking-wider block mb-1.5 flex items-center gap-1.5">
                  {t('contacts.anatomy_experience', '🔞 Anatomy & Experience')}
                </span>
                {hasSections && intSec.anatomy ? (
                  renderBulletPoints(
                    intSec.anatomy.map(line => {
                      if (!isMaleNpc && /breast size.*unknown/i.test(line) && bTitle) {
                        return `• **Breast Size**: ${bTitle}`;
                      }
                      return line;
                    }),
                    t
                  )
                ) : (
                  <div className="space-y-1 text-gray-300 leading-relaxed">
                    <div>
                      • <strong className="text-gray-100">{isMaleNpc ? t('contacts.penis_size_plain', 'Penis Size') : t('contacts.breast_size_plain', 'Breast Size')}</strong>: {sizeDisplay}
                    </div>
                    {appearance.asset_texture && (
                      <div>
                        • <strong className="text-gray-100">{t('contacts.tactile_feature', 'Tactile Feature')}</strong>:{' '}
                        <span className="text-pink-300 font-medium">{appearance.asset_texture}</span>
                      </div>
                    )}
                    <div>• <strong className="text-gray-100">{t('contacts.intercourse', 'Intercourse')}</strong>: {iExpDisp}</div>
                    <div>• <strong className="text-gray-100">{t('contacts.oral_intimacy', 'Oral Intimacy')}</strong>: {oExpDisp}</div>
                    <div>• <strong className="text-gray-100">{t('contacts.manual_intimacy', 'Manual Intimacy')}</strong>: {mExpDisp}</div>
                    <div>• <strong className="text-gray-100">{t('contacts.anal_intimacy', 'Anal Intimacy')}</strong>: {aExpDisp}</div>
                  </div>
                )}
              </div>

              <div className="pt-2 border-t border-fantasy-border/30">
                <span className="text-xs font-bold text-purple-400 uppercase tracking-wider block mb-1.5 flex items-center gap-1.5">
                  {t('contacts.demeanor_dynamic', '🎭 Demeanor & Dynamic')}
                </span>
                {hasSections && intSec.dynamic ? (
                  renderBulletPoints(intSec.dynamic, t)
                ) : (
                  <div className="space-y-1 text-gray-300 leading-relaxed">
                    <div>
                      • <strong className="text-gray-100">{t('contacts.demeanor', 'Demeanor')}</strong>:{' '}
                      {(infoLevel >= 3 || isDebugRevealed) && appearance.intimate_demeanor
                        ? appearance.intimate_demeanor
                        : <span className="text-gray-500 italic">{t('common.unknown', 'Unknown')}</span>}
                    </div>
                    <div>
                      • <strong className="text-gray-100">{t('contacts.dynamic', 'Dynamic')}</strong>:{' '}
                      {(infoLevel >= 3 || isDebugRevealed) && appearance.intimate_dynamic
                        ? appearance.intimate_dynamic
                        : <span className="text-gray-500 italic">{t('common.unknown', 'Unknown')}</span>}
                    </div>
                    <div>
                      • <strong className="text-gray-100">{t('contacts.openness', 'Openness')}</strong>:{' '}
                      {(infoLevel >= 3 || isDebugRevealed) && (appearance.erotic_openness || appearance.openness)
                        ? (appearance.erotic_openness || appearance.openness)
                        : <span className="text-gray-500 italic">{t('common.unknown', 'Unknown')}</span>}
                    </div>
                  </div>
                )}
              </div>

              <div className="pt-2 border-t border-fantasy-border/30">
                <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider block mb-1.5 flex items-center gap-1.5">
                  {t('contacts.undergarments_header', '🩲 Undergarments')}
                </span>
                {hasSections && intSec.undergarments ? (
                  renderBulletPoints(intSec.undergarments, t)
                ) : (
                  <div className="space-y-1 text-gray-300 leading-relaxed">
                    {!isMaleNpc && (
                      <div>
                        • <strong className="text-gray-100">{t('contacts.bra', 'Bra')}</strong>:{' '}
                        {(infoLevel >= 3 || isDebugRevealed) && braVal
                          ? braVal
                          : <span className="text-gray-500 italic">{t('common.unknown', 'Unknown')}</span>}
                      </div>
                    )}
                    <div>
                      • <strong className="text-gray-100">{t('contacts.underwear', 'Underwear')}</strong>:{' '}
                      {(infoLevel >= 3 || isDebugRevealed) && undVal
                        ? undVal
                        : <span className="text-gray-500 italic">{t('common.unknown', 'Unknown')}</span>}
                    </div>
                  </div>
                )}
              </div>

              <div className="pt-2 border-t border-fantasy-border/30">
                <span className="text-xs font-bold text-pink-400 uppercase tracking-wider block mb-1.5 flex items-center gap-1.5">
                  {t('contacts.sensitive_spots_header', '🌸 Sensitive Spots')}
                </span>
                {hasSections && (intSec.sensitive_spots || intSec.sensitivities) ? (
                  renderBulletPoints(
                    intSec.sensitive_spots || (Array.isArray(intSec.sensitivities) ? intSec.sensitivities.filter(s => typeof s === 'string' && s.toLowerCase().includes('sensitive spot')) : []),
                    t
                  )
                ) : (
                  <div className="space-y-1 text-gray-300 leading-relaxed">
                    <div>
                      • <strong className="text-gray-100">{t('contacts.sensitive_spots', 'Sensitive Spots')}</strong>:{' '}
                      {(infoLevel >= 3 || isDebugRevealed) && appearance.sensitive_spots
                        ? appearance.sensitive_spots
                        : <span className="text-gray-500 italic">{t('common.unknown', 'Unknown')}</span>}
                    </div>
                  </div>
                )}
              </div>

              <div className="pt-2 border-t border-fantasy-border/30">
                <span className="text-xs font-bold text-amber-400 uppercase tracking-wider block mb-1.5 flex items-center gap-1.5">
                  {t('contacts.desires_turnoffs_header', '🔥 Desires & Turn-Offs')}
                </span>
                {hasSections && (intSec.desires_and_turn_offs || intSec.sensitivities) ? (
                  renderBulletPoints(
                    intSec.desires_and_turn_offs || (Array.isArray(intSec.sensitivities) ? intSec.sensitivities.filter(s => typeof s === 'string' && !s.toLowerCase().includes('sensitive spot')) : []),
                    t
                  )
                ) : (
                  <div className="space-y-1 text-gray-300 leading-relaxed">
                    <div>
                      • <strong className="text-gray-100">{t('contacts.desires_kinks', 'Desires & Kinks')}</strong>:{' '}
                      {(infoLevel >= 3 || isDebugRevealed) && (appearance.desires_and_kinks || appearance.turn_ons)
                        ? (Array.isArray(appearance.desires_and_kinks || appearance.turn_ons)
                            ? (appearance.desires_and_kinks || appearance.turn_ons).join(', ')
                            : (appearance.desires_and_kinks || appearance.turn_ons))
                        : <span className="text-gray-500 italic">{t('common.unknown', 'Unknown')}</span>}
                    </div>
                    <div>
                      • <strong className="text-red-300">{t('contacts.turn_offs', 'Turn-Offs')}</strong>:{' '}
                      {(infoLevel >= 3 || isDebugRevealed) && appearance.turn_offs
                        ? (Array.isArray(appearance.turn_offs) ? appearance.turn_offs.join(', ') : appearance.turn_offs)
                        : <span className="text-gray-500 italic">{t('common.unknown', 'Unknown')}</span>}
                    </div>
                  </div>
                )}
              </div>

              <div className="pt-2 border-t border-fantasy-border/30">
                <span className="text-xs font-bold text-rose-400 uppercase tracking-wider block mb-1.5 flex items-center gap-1.5">
                  {t('contacts.act_preferences_header', '❤️ Act & Position Preferences')}
                </span>
                {hasSections && intSec.act_preferences ? (
                  renderBulletPoints(intSec.act_preferences, t)
                ) : (
                  <div className="space-y-1 text-gray-300 leading-relaxed">
                    <div>
                      • <strong className="text-gray-100">{t('contacts.preferred_likes', 'Preferred / Likes')}</strong>:{' '}
                      {(infoLevel >= 3 || isDebugRevealed) && (appearance.favorite_acts || appearance.act_likes)
                        ? (Array.isArray(appearance.favorite_acts) ? appearance.favorite_acts.join(', ') : (appearance.act_likes || 'None'))
                        : <span className="text-gray-500 italic">{t('common.unknown', 'Unknown')}</span>}
                    </div>
                    <div>
                      • <strong className="text-gray-100">{t('contacts.aversions_dislikes', 'Aversions / Dislikes')}</strong>:{' '}
                      {(infoLevel >= 3 || isDebugRevealed) && (appearance.disliked_acts || appearance.act_dislikes)
                        ? (Array.isArray(appearance.disliked_acts) ? appearance.disliked_acts.join(', ') : (appearance.act_dislikes || 'None'))
                        : <span className="text-gray-500 italic">{t('common.unknown', 'Unknown')}</span>}
                    </div>
                  </div>
                )}
              </div>

              <div className="pt-2 border-t border-fantasy-border/30 space-y-1">
                <span className="text-xs font-bold text-gray-300 uppercase tracking-wider block mb-0.5">
                  {t('contacts.past_intimate_history', 'Past Intimate History')}
                </span>
                {!isHistoryUnlocked ? (
                  <p className="text-gray-500 italic text-xs leading-relaxed">
                    {t('contacts.locked_intimate_history', '🔒 Locked — Requires Confidant / Soulmate standing (Info Level 3/3) to uncover.')}
                  </p>
                ) : hasHistoryEntries ? (
                  npc.past_intimate_entries && npc.past_intimate_entries.length > 0 ? (
                    <div className="space-y-1">
                      {npc.past_intimate_entries.map((h, i) => (
                        <p key={i} className="text-gray-300 italic text-xs leading-relaxed">• {h}</p>
                      ))}
                    </div>
                  ) : Array.isArray(npc.past_intimate_history) ? (
                    <div className="space-y-1">
                      {npc.past_intimate_history.map((h, i) => (
                        <p key={i} className="text-gray-300 italic text-xs leading-relaxed">• {h}</p>
                      ))}
                    </div>
                  ) : (
                    <p className="text-gray-300 italic text-xs leading-relaxed">• {npc.past_intimate_history}</p>
                  )
                ) : (
                  <p className="text-gray-400 italic text-xs leading-relaxed">
                    {t('contacts.virgin_history', '• Virgin (No prior intimate history before meeting you)')}
                  </p>
                )}
              </div>

              <div className="pt-2 border-t border-fantasy-border/30">
                <span className="text-xs font-bold text-pink-400 uppercase tracking-wider flex items-center gap-1.5 mb-1.5">
                  <Sparkles size={12} />
                  <span>{t('contacts.romantic_milestones', 'Shared Romantic Milestones')}</span>
                </span>
                {sharedMilestones.length > 0 ? (
                  <div className="space-y-1.5 bg-black/50 p-2.5 rounded-lg border border-pink-900/40">
                    {sharedMilestones.map((m, idx) => (
                      <p key={idx} className="text-xs text-pink-200/90 leading-relaxed italic">
                        • {typeof m === 'string' ? m : (m.summary || m.event)}
                      </p>
                    ))}
                  </div>
                ) : (
                  <p className="text-gray-500 italic text-xs leading-relaxed">
                    {t('contacts.no_romantic_milestones', 'No romantic milestones shared with this character yet.')}
                  </p>
                )}
              </div>

              <div className="text-[11px] text-gray-500 font-mono pt-1.5 border-t border-fantasy-border/20">
                {t('contacts.disclosure_footer_intimate', 'Information Disclosure Level: {{level}}/3 • Intimate Dossier', { level: infoLevel })}{isDebugRevealed ? ' • [🛠️ DEBUG: Revealed]' : ''}
              </div>
            </div>
          );
        })()}
      </div>
    </div>
  );
};

export default NpcDossierBody;
