import { Fragment, useId } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Heart,
  Lock,
  MapPin,
  Smartphone,
  User,
  UserMinus,
  Users,
} from 'lucide-react';
import { StatusEffectBadge } from './CharacterSheet';
import KnownRoutineCard from './KnownRoutineCard';
import KnownWardrobeCard from './KnownWardrobeCard';
import OperativeCombatDossierCard from './OperativeCombatDossierCard';
import { defaultBulletRenderer, isRedundantAgentTierGrade } from './NpcDossierBody';
import IntimateDossierPanel from './IntimateDossierPanel';
import { formatCleanLocation } from '../../utils/locationFormat';
import {
  HEIGHT_PREFERENCE_KEYS,
  formatFusedRear,
  formatBodyPreferenceLabel,
  isFeralRearExcluded,
  isMaleGender,
  stripRearTextureFromSizeClient,
} from '../../utils/anatomyOptions';
import {
  formatAgeCategory,
  formatGender,
  formatPhysique,
  formatRace,
  formatStature,
  formatTitle,
} from '../../utils/npcDemographics';

export const getStandingBadgeClass = (standing) => {
  const s = String(standing || '').toLowerCase();
  if (['freshman', 'sophomore', 'junior', 'senior'].includes(s)) {
    return 'bg-purple-950/40 text-purple-300 border-purple-800/40';
  }
  if (s === 'faculty') {
    return 'bg-amber-950/40 text-amber-300 border-amber-800/40';
  }
  if (s === 'staff') {
    return 'bg-emerald-950/40 text-emerald-300 border-emerald-800/40';
  }
  if (s === 'citizen') {
    return 'bg-slate-900/60 text-slate-300 border-slate-700/50';
  }
  if (s === 'youth peer') {
    return 'bg-teal-950/40 text-teal-300 border-teal-800/40';
  }
  return 'bg-purple-950/40 text-purple-300 border-purple-800/40';
};

export const getRelationshipTier = (score, track = 'platonic', t = null) => {
  const isRom = String(track || '').toLowerCase() === 'romantic';
  let tierKey = 'stranger';
  let fallback = 'Stranger';
  let color = 'text-gray-400';
  let bg = 'bg-gray-500';

  if (score >= 250) {
    if (isRom) {
      tierKey = 'soulmate';
      fallback = 'Soulmate / Eternal Bond';
      color = 'text-pink-400';
      bg = 'bg-pink-500';
    } else {
      tierKey = 'sworn_lifelong_ally';
      fallback = 'Sworn Lifelong Ally';
      color = 'text-purple-400';
      bg = 'bg-purple-500';
    }
  } else if (score >= 200) {
    if (isRom) {
      tierKey = 'devoted_lovers';
      fallback = 'Devoted Lovers';
      color = 'text-pink-400';
      bg = 'bg-pink-500';
    } else {
      tierKey = 'confidant';
      fallback = 'Confidant';
      color = 'text-purple-400';
      bg = 'bg-purple-500';
    }
  } else if (score >= 150) {
    if (isRom) {
      tierKey = 'dating_partner';
      fallback = 'Dating / Confessed Partners';
      color = 'text-pink-400';
      bg = 'bg-pink-500';
    } else {
      tierKey = 'close_friend';
      fallback = 'Close Friend';
      color = 'text-blue-400';
      bg = 'bg-blue-500';
    }
  } else if (score >= 100) {
    if (isRom) {
      tierKey = 'mutual_attraction';
      fallback = 'Mutual Attraction / Crush';
      color = 'text-pink-300';
      bg = 'bg-pink-400';
    } else {
      tierKey = 'friend';
      fallback = 'Friend';
      color = 'text-emerald-400';
      bg = 'bg-emerald-500';
    }
  } else if (score >= 50) {
    tierKey = 'acquaintance';
    fallback = 'Acquaintance';
    color = 'text-cyan-400';
    bg = 'bg-cyan-500';
  } else if (score >= 0) {
    tierKey = 'stranger';
    fallback = 'Stranger';
    color = 'text-gray-400';
    bg = 'bg-gray-500';
  } else if (score >= -10) {
    tierKey = 'unfriendly';
    fallback = 'Unfriendly';
    color = 'text-amber-400';
    bg = 'bg-amber-500';
  } else if (score >= -30) {
    tierKey = 'distrusted';
    fallback = 'Distrusted';
    color = 'text-amber-500';
    bg = 'bg-amber-600';
  } else if (score >= -50) {
    tierKey = 'adversary';
    fallback = 'Adversary';
    color = 'text-orange-500';
    bg = 'bg-orange-600';
  } else if (score >= -70) {
    tierKey = 'hostile';
    fallback = 'Hostile';
    color = 'text-red-500';
    bg = 'bg-red-600';
  } else if (score >= -90) {
    tierKey = 'bitter_nemesis';
    fallback = 'Bitter Nemesis';
    color = 'text-red-600';
    bg = 'bg-red-700';
  } else {
    tierKey = 'mortal_foe';
    fallback = 'Mortal Foe';
    color = 'text-rose-600';
    bg = 'bg-rose-700';
  }

  const label = t ? t(`codex.tiers.${tierKey}`, fallback) : fallback;
  return { label, color, bg };
};

const DEBUG_DOSSIER_TABS = [
  { id: 'persona', icon: '👤', shortLabel: 'Persona', fullLabel: 'Persona & Appearance' },
  { id: 'history', icon: '📜', shortLabel: 'History', fullLabel: 'Shared History' },
  { id: 'relations', icon: '🌳', shortLabel: 'Relations', fullLabel: 'Relations & Family' },
  { id: 'intimate', icon: '🔥', shortLabel: 'Intimacy', fullLabel: 'Intimate Dossier' },
];

const DISLIKE_PREFIXES = [
  'dislike', 'dislikes', 'hate', 'hates', 'fear', 'fears', 'avoid', 'avoids',
  'detest', 'detests', 'loathe', 'loathes', 'resent', 'resents', 'resist', 'resists',
  'disdain', 'disdains', 'repulsed', 'repulses', 'averse',
];

const CodexCharactersTab = ({
  filteredContacts,
  session,
  partyNpcNames,
  expandedNpc,
  onToggleNpc,
  highlightedNpcKey,
  cardRefs,
  debugDossierTab,
  onChangeDebugDossierTab,
  companionBusy,
  onToggleCompanion,
  onJumpToSavedContact,
  renderLinkedPerson,
  renderBulletPoints = defaultBulletRenderer,
  t,
}) => {
  const codexTabIdPrefix = useId();

  if (filteredContacts.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500 border border-dashed border-fantasy-border/50 rounded-md">
        <Users size={24} className="mx-auto mb-1.5 opacity-40" />
        <p className="text-xs">{t('codex.no_characters', 'No characters discovered in the world yet.')}</p>
        <p className="text-[10px] text-gray-500 mt-1">{t('codex.empty_archives', 'Explore locations and meet characters in the story to reveal them here.')}</p>
      </div>
    );
  }

  return filteredContacts.map((rawNpc, npcIdx) => {
    const npcToggleKey = rawNpc.id || rawNpc.name;
    const isDebugRevealed = Boolean(rawNpc.debug_revealed);
    const npc = (isDebugRevealed && rawNpc.debug_profile)
      ? {
          ...rawNpc,
          ...rawNpc.debug_profile,
          appearance: { ...(rawNpc.appearance || {}), ...(rawNpc.debug_profile.appearance || {}) },
          basic_info: { ...(rawNpc.basic_info || {}), ...(rawNpc.debug_profile.basic_info || {}) },
        }
      : rawNpc;
    const score = npc.relationship_score || npc.affinity || 0;
    const isRomantic = (npc.track === 'romantic') || (npc.relations?.track === 'romantic');
    const tier = getRelationshipTier(score, isRomantic ? 'romantic' : 'platonic', t);
    const isExpanded = expandedNpc === npcToggleKey;
    const isInParty = partyNpcNames.has((npc.name || '').toLowerCase());
    const basic = npc.basic_info || {};
    const anomTag = npc.anomalous_npc_tag || basic.anomalous_npc_tag || null;
    const isSpecialAgent = anomTag === 'special_agent';
    const isCivilianTag = anomTag === 'civilian';
    const isDeceased = Boolean(
      npc.deceased ||
      basic.deceased ||
      String(npc.disposition || '').toLowerCase() === 'dead'
    );
    const traits = npc.unlocked_traits || [];
    const rawDislikes = npc.dislikes || basic.dislikes || [];
    const dislikes = rawDislikes.map(d => typeof d === 'string' ? d : (d.dislike || d.name || ''));
    const rawPreferences = npc.preferences || npc.likes || [];
    const dislikeLowerSet = new Set(dislikes.map(d => d.toLowerCase().trim()));
    const preferences = rawPreferences
      .map(p => typeof p === 'string' ? p : (p.preference || p.name || ''))
      .filter(p => {
        if (!p) return false;
        const pLow = p.toLowerCase().trim();
        if (dislikeLowerSet.has(pLow)) return false;
        const firstWord = pLow.split(/\s+/)[0];
        if (DISLIKE_PREFIXES.includes(firstWord)) return false;
        return true;
      });
    const appearance = npc.appearance || {};
    const familyTree = npc.family_tree || {};
    const relations = npc.relations || {};
    const infoLevel = npc.info_level ?? 0;
    const rawGender = String(basic.gender || npc.gender || appearance.gender || 'female').trim();
    const isMale = isMaleGender(rawGender);
    const feralRearExcluded = isFeralRearExcluded(basic.race || npc.race || appearance.race);
    const isNsfwScenario = Boolean(
      session?.is_nsfw ||
      npc?.is_nsfw ||
      (session?.scenario && String(session.scenario).toLowerCase().includes('nsfw')) ||
      (Array.isArray(session?.scenario_tags) && session.scenario_tags.includes('nsfw'))
    );

    const isSavedContact = Boolean(npc.is_contact);
    const hasRoutine = Boolean(npc.known_routine || npc.known_schedule || npc.schedule_summary);
    const hasWardrobe = Boolean(npc.known_wardrobe || (isDebugRevealed && npc.debug_profile?.known_wardrobe));
    const hasOperational = Boolean(isInParty || isSpecialAgent || isCivilianTag);
    const hasExpandableDetails = Boolean(hasOperational || isDebugRevealed || hasWardrobe || hasRoutine);

    return (
      <div
        key={npc.id || npc.name}
        ref={(el) => {
          cardRefs.current[npcToggleKey] = el;
          if (npc.name) cardRefs.current[String(npc.name).toLowerCase()] = el;
        }}
        className={`bg-black/50 border rounded-lg p-2.5 space-y-1.5 transition-all ${
          highlightedNpcKey === npcToggleKey
            ? 'border-fantasy-accent ring-2 ring-fantasy-accent/60 shadow-lg shadow-fantasy-accent/20'
            : 'border-fantasy-border/60 hover:border-fantasy-border'
        }`}
      >
        <div className="flex items-start justify-between gap-2 select-none">
          <div className="flex items-center gap-2 min-w-0">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center border font-bold text-xs shrink-0 ${
              isRomantic
                ? 'bg-pink-950/40 border-pink-700/60 text-pink-300'
                : 'bg-fantasy-dark border-fantasy-accent/40 text-fantasy-accent'
            }`}>
              {isRomantic ? <Heart size={14} /> : <User size={14} />}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className={`font-bold text-xs sm:text-sm ${isDeceased ? 'line-through text-gray-400' : 'text-gray-100'}`}>{npc.name}</span>
                {isSavedContact && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (onJumpToSavedContact) onJumpToSavedContact(npc.name);
                    }}
                    title={t('codex.open_in_contacts', 'Open Full Dossier in Contacts')}
                    className="text-[9px] px-1.5 py-0.5 bg-emerald-950/75 hover:bg-emerald-900/80 text-emerald-300 rounded font-bold uppercase border border-emerald-700/60 inline-flex items-center gap-1 cursor-pointer transition-colors"
                  >
                    <Smartphone size={9} />
                    <span>{t('codex.saved_contact', 'Saved Contact')}</span>
                  </button>
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
              <span className="text-[11px] text-gray-400 font-medium block truncate max-w-56">
                {npc.public_role || basic.public_role || basic.role || basic.occupation || npc.standing || basic.standing || (basic.faction ? `${basic.faction} Member` : ((session?.scenario || '').toLowerCase().includes('school') ? 'Student' : 'Encountered'))}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-1.5 text-right shrink-0">
            <div>
              <span className={`text-[11px] font-bold block ${tier.color}`}>
                {tier.label}
              </span>
              <span className="font-mono text-[10px] font-semibold text-gray-300">
                {score > 0 ? `+${score}` : score}
              </span>
            </div>
          </div>
        </div>

        {Array.isArray(npc.status_effects) && npc.status_effects.filter(s => {
          const str = typeof s === 'string' ? s.trim() : (s?.name || '').trim();
          return str && !['[]', '{}', '""', "''", 'none', 'null'].includes(str.toLowerCase());
        }).length > 0 && (
          <div className="flex flex-wrap gap-1 pt-0.5">
            {npc.status_effects
              .filter(s => {
                const str = typeof s === 'string' ? s.trim() : (s?.name || '').trim();
                return str && !['[]', '{}', '""', "''", 'none', 'null'].includes(str.toLowerCase());
              })
              .map((eff, i) => (
                <StatusEffectBadge key={i} effect={eff} />
              ))}
          </div>
        )}

        <div className="h-1.5 w-full bg-black/80 rounded-full overflow-hidden border border-fantasy-border/40">
          <div
            className={`h-full ${tier.bg} transition-all duration-300`}
            style={{ width: `${Math.max(5, Math.min(100, ((score + 100) / 400) * 100))}%` }}
          />
        </div>

        <div className="pt-1.5 space-y-1.5 text-[11px]">
          <div className="flex flex-wrap items-center gap-1">
            {(() => {
              const standingVal = npc.standing || basic.standing || basic.grade || npc.grade;
              if (!standingVal || isRedundantAgentTierGrade(standingVal, isSpecialAgent)) return null;
              return (
                <span className={`px-1.5 py-0.5 rounded text-[10.5px] border ${getStandingBadgeClass(standingVal)}`}>
                  {formatTitle(standingVal)}
                </span>
              );
            })()}
            {(basic.club || npc.club) && (
              <span className="px-1.5 py-0.5 rounded bg-cyan-950/40 text-cyan-300 border border-cyan-800/40 text-[10.5px]">
                Club: {formatTitle(basic.club || npc.club)}
              </span>
            )}
            {npc.faction_affiliation && (
              <span className="px-1.5 py-0.5 rounded bg-slate-900/60 text-slate-300 border border-slate-700/50 text-[10.5px]">
                Faction: {formatTitle(npc.faction_affiliation)}
              </span>
            )}
            {(npc.age_group || basic.age_group) && (() => {
              const agInfo = formatAgeCategory(npc.age_group || basic.age_group, t);
              if (!agInfo) return null;
              const label = agInfo.key === 'teen' && npc.is_student
                ? `${agInfo.label} · ${t('scene.student_tag', 'Student')}`
                : agInfo.label;
              return (
                <span className={`px-1.5 py-0.5 rounded text-[10.5px] border ${agInfo.pillClass}`}>
                  {label}
                </span>
              );
            })()}
            {(basic.race || npc.race) && (
              <span className="px-1.5 py-0.5 rounded bg-black/60 text-gray-300 border border-fantasy-border/40 text-[10.5px]">
                {formatRace(basic.race || npc.race, t)}
              </span>
            )}
            {(basic.gender || npc.gender) && (() => {
              const gInfo = formatGender(basic.gender || npc.gender, t);
              return (
                <span className="px-1.5 py-0.5 rounded bg-black/60 text-gray-300 border border-fantasy-border/40 text-[10.5px]">
                  {gInfo ? `${gInfo.symbol ? `${gInfo.symbol} ` : ''}${gInfo.label}` : formatTitle(basic.gender || npc.gender)}
                </span>
              );
            })()}
            {(basic.age || npc.age) && (
              <span className="px-1.5 py-0.5 rounded bg-black/60 text-gray-300 border border-fantasy-border/40 text-[10.5px]">
                Age {basic.age || npc.age}
              </span>
            )}
            {!isDebugRevealed && (basic.mannerisms || npc.mannerisms) && (
              <span className="px-1.5 py-0.5 rounded bg-amber-950/30 text-amber-300/90 border border-amber-800/30 text-[10.5px] truncate max-w-full">
                🎭 {basic.mannerisms || npc.mannerisms}
              </span>
            )}
            {(basic.location || npc.location) && (
              <span className="px-1.5 py-0.5 rounded bg-black/60 text-gray-400 border border-fantasy-border/30 text-[10.5px] flex items-center gap-1">
                <MapPin size={9} className="text-fantasy-accent" />
                <span>{formatCleanLocation(basic.location || npc.location)}</span>
              </span>
            )}
          </div>

          {(() => {
            const eyeColor = appearance.eye_color || appearance.eyes;
            const hairColor = appearance.hair_color;
            const stature = appearance.stature || appearance.height;
            const physique = appearance.physique;
            const coatColor = appearance.coat_color || appearance.fur_color || appearance.scale_color || appearance.skin_color;
            const outfitStyle = appearance.outfit_style || appearance.clothing;
            const hasAnyApp = Boolean(eyeColor || hairColor || stature || physique || coatColor || (!hasWardrobe && outfitStyle));
            if (!hasAnyApp) return null;
            return (
              <div className="text-[10.5px] text-gray-400 bg-black/30 p-1.5 rounded border border-fantasy-border/30 flex flex-wrap gap-x-2 gap-y-0.5">
                {(stature || physique) && <span>📐 <strong>{t('codex.build', 'Build:')}</strong> {[formatStature(stature, t), formatPhysique(physique, t)].filter(Boolean).join(' • ')}</span>}
                {eyeColor && <span>👁️ <strong>{t('codex.eyes', 'Eyes:')}</strong> {formatTitle(eyeColor)}</span>}
                {hairColor && <span>💇 <strong>{t('codex.hair', 'Hair:')}</strong> {formatTitle(hairColor)}</span>}
                {coatColor && <span>✨ <strong>{t('codex.skin_coat', 'Skin/Coat:')}</strong> {formatTitle(coatColor)}</span>}
                {!hasWardrobe && outfitStyle && <span>👔 <strong>{t('codex.outfit', 'Outfit:')}</strong> {formatTitle(outfitStyle)}</span>}
                {isNsfwScenario && (isMale ? ((infoLevel >= 3 || isDebugRevealed) && appearance.penis_size && appearance.penis_size.toLowerCase() !== 'unknown') : appearance.breast_size) && (
                  <span className="text-pink-400/90 font-medium">
                    🔞 {isMale ? `Size: ${appearance.penis_size}` : `Bust: ${appearance.breast_size}`}
                  </span>
                )}
                {isNsfwScenario && !feralRearExcluded && appearance.rear_size && (
                  <span className="text-pink-400/90 font-medium">
                    🍑 {t('contacts.rear_size_plain', 'Rear')}:{' '}
                    {(infoLevel >= 3 || isDebugRevealed)
                      ? (formatFusedRear(appearance.rear_size, appearance.rear_texture, t).label || formatTitle(appearance.rear_size))
                      : (formatFusedRear(stripRearTextureFromSizeClient(appearance.rear_size), '', t).sizeOnly || stripRearTextureFromSizeClient(appearance.rear_size))}
                  </span>
                )}
              </div>
            );
          })()}

          <div className="flex items-center justify-between pt-1 border-t border-fantasy-border/30 gap-2 flex-wrap">
            {isSavedContact && onJumpToSavedContact ? (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onJumpToSavedContact(npc.name);
                }}
                className="flex items-center gap-1.5 py-1 px-2.5 rounded text-[11px] font-bold border bg-emerald-950/50 hover:bg-emerald-900/60 border-emerald-700/60 text-emerald-300 transition-all cursor-pointer select-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-400"
              >
                <Smartphone size={12} />
                <span>{t('codex.open_in_contacts', 'Open in Contacts')}</span>
                <ChevronRight size={12} />
              </button>
            ) : isDebugRevealed ? (
              <span className="text-[9px] px-1.5 py-0.5 rounded bg-purple-950/80 text-purple-300 border border-purple-700/60 font-mono">
                {t('codex.debug_revealed_badge', 'DEBUG: Full Profile Revealed')}
              </span>
            ) : (
              <span className="text-[10px] text-gray-500 italic flex items-center gap-1">
                <Lock size={10} className="text-amber-400/70 shrink-0" />
                <span>{t('codex.unlock_contact_hint', 'Unlock as a Contact to view personal dossier')}</span>
              </span>
            )}

            <div className="flex items-center gap-1.5">
              {isSavedContact && isDebugRevealed && (
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-purple-950/80 text-purple-300 border border-purple-700/60 font-mono">
                  {t('codex.debug_revealed_badge', 'DEBUG: Full Profile Revealed')}
                </span>
              )}
              {hasExpandableDetails && (
                <button
                  type="button"
                  aria-expanded={isExpanded}
                  onClick={(e) => {
                    e.stopPropagation();
                    onToggleNpc(isExpanded ? null : npcToggleKey);
                  }}
                  className="flex items-center gap-1 py-1 px-2 rounded text-[10.5px] font-semibold border bg-black/50 hover:bg-black/70 border-fantasy-border/60 text-gray-300 transition-all cursor-pointer select-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fantasy-accent"
                >
                  {isExpanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
                  <span>
                    {isDebugRevealed
                      ? t('codex.full_debug_dossier', 'Full Debug Dossier')
                      : t('codex.details', 'Details')}
                  </span>
                </button>
              )}
            </div>
          </div>
        </div>

        {isExpanded && hasExpandableDetails && (
          <div className="space-y-3 pt-2.5 border-t border-fantasy-border/40 text-xs text-gray-300">
            {isInParty && (
              <div className="flex items-center justify-between bg-black/40 p-2.5 rounded-lg border border-fantasy-border/40">
                <span className="text-xs text-gray-300">
                  {t('codex.in_party_desc', 'Currently traveling in your party.')}
                </span>
                <button
                  disabled={companionBusy === npc.name}
                  onClick={(e) => {
                    e.stopPropagation();
                    onToggleCompanion(npc.name, true);
                  }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-bold border transition-all shrink-0 bg-red-950/50 border-red-800/60 text-red-300 hover:bg-red-900/60 cursor-pointer"
                >
                  <UserMinus size={13} />
                  <span>{companionBusy === npc.name ? '...' : t('codex.dismiss', 'Dismiss')}</span>
                </button>
              </div>
            )}

            {isDebugRevealed && (
              <div className="hk-dossier-tabs-wrap pt-1" style={{ '--hk-tab-accent': '#c084fc' }}>
                <div
                  role="tablist"
                  aria-label={`${npc.name} debug dossier sections`}
                  className="grid grid-cols-4 border-b border-purple-700/60 pt-1.5 px-1 bg-purple-950/30 rounded-t-lg gap-1 items-end select-none"
                >
                  {DEBUG_DOSSIER_TABS.map(tb => {
                    const isActive = debugDossierTab === tb.id;
                    return (
                      <button
                        key={tb.id}
                        id={`${codexTabIdPrefix}-${npcIdx}-tab-${tb.id}`}
                        type="button"
                        role="tab"
                        aria-selected={isActive}
                        title={tb.fullLabel}
                        onClick={(e) => { e.stopPropagation(); onChangeDebugDossierTab(tb.id); }}
                        className={`hk-dossier-tab min-w-0 py-1.5 px-1 text-xs font-bold transition-all flex items-center justify-center gap-1 rounded-t-md relative cursor-pointer border-t border-x ${
                          isActive
                            ? 'bg-black/60 text-purple-200 border-purple-700/60 border-b-black/60 -mb-px z-10'
                            : 'bg-black/25 text-gray-400 hover:text-gray-200 hover:bg-black/40 border-transparent border-b border-b-purple-700/60'
                        }`}
                      >
                        <span className="text-xs shrink-0">{tb.icon}</span>
                        <span className="truncate text-[10.5px] font-semibold">
                          <span className="hk-dossier-tab-full">{tb.fullLabel}</span>
                          <span className="hk-dossier-tab-short">{tb.shortLabel}</span>
                        </span>
                      </button>
                    );
                  })}
                </div>

                <div
                  role="tabpanel"
                  aria-labelledby={`${codexTabIdPrefix}-${npcIdx}-tab-${debugDossierTab}`}
                  className="bg-black/50 border-x border-b border-purple-700/60 rounded-b-lg p-3 text-xs -mt-px space-y-3"
                >
                  {debugDossierTab === 'persona' && (
                    <div className="space-y-2.5">
                      {(npc.archetype_trope || basic.archetype_trope) && (
                        <div className="text-[11px] text-purple-300">
                          <strong className="text-purple-200">{t('codex.archetype_trope', 'Archetype / Trope:')}</strong> {npc.archetype_trope || basic.archetype_trope}
                        </div>
                      )}
                      {(basic.description || appearance.summary || npc.description) && (
                        <div className="bg-black/40 p-2 rounded border border-fantasy-border/40 text-gray-300 leading-relaxed">
                          <span className="text-[10.5px] font-bold text-gray-400 uppercase tracking-wider block mb-0.5">
                            📖 Background & Notes
                          </span>
                          {basic.description || appearance.summary || npc.description}
                        </div>
                      )}
                      {(basic.mannerisms || appearance.mannerisms || npc.mannerisms) && (
                        <div className="bg-black/40 p-2 rounded border border-fantasy-border/40 text-gray-300 leading-relaxed">
                          <span className="text-[10.5px] font-bold text-gray-400 uppercase tracking-wider block mb-0.5">
                            🎭 Mannerisms
                          </span>
                          {basic.mannerisms || appearance.mannerisms || npc.mannerisms}
                        </div>
                      )}
                      {traits.length > 0 && (
                        <div>
                          <span className="text-[10.5px] font-bold text-gray-400 uppercase tracking-wider block mb-1">
                            Known Traits
                          </span>
                          <div className="flex flex-wrap gap-1">
                            {traits.map((tr, idx) => (
                              <span key={idx} className="text-[11px] px-2 py-0.5 rounded bg-black/60 text-gray-200 border border-fantasy-border">
                                {typeof tr === 'string' ? tr : (tr.trait || tr.name)}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                      {preferences.length > 0 && (
                        <div>
                          <span className="text-[10.5px] font-bold text-gray-400 uppercase tracking-wider block mb-1">
                            Likes & Preferences
                          </span>
                          <div className="flex flex-wrap gap-1">
                            {preferences.map((p, idx) => (
                              <span key={idx} className="text-[11px] px-2 py-0.5 rounded bg-cyan-950/40 text-cyan-300 border border-cyan-800/40">
                                {p}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                      {dislikes.length > 0 && (
                        <div>
                          <span className="text-[10.5px] font-bold text-gray-400 uppercase tracking-wider block mb-1">
                            Dislikes & Pet Peeves
                          </span>
                          <div className="flex flex-wrap gap-1">
                            {dislikes.map((d, idx) => (
                              <span key={idx} className="text-[11px] px-2 py-0.5 rounded bg-red-950/40 text-red-300 border border-red-800/40">
                                {d}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                      {(Array.isArray(appearance.body_likes) || Array.isArray(appearance.body_dislikes)) && (() => {
                        const heightLikes = (appearance.body_likes || []).filter((k) => HEIGHT_PREFERENCE_KEYS.includes(String(k || '').toLowerCase()));
                        const heightDislikes = (appearance.body_dislikes || []).filter((k) => HEIGHT_PREFERENCE_KEYS.includes(String(k || '').toLowerCase()));
                        if (heightLikes.length === 0 && heightDislikes.length === 0) return null;
                        return (
                          <div>
                            <span className="text-[10.5px] font-bold text-gray-400 uppercase tracking-wider block mb-1">
                              📏 {t('contacts.height_preference_label', 'Height Preference')}
                            </span>
                            <div className="flex flex-wrap gap-1">
                              {heightLikes.map((k, idx) => (
                                <span key={`hl-${idx}`} className="text-[11px] px-2 py-0.5 rounded bg-cyan-950/40 text-cyan-300 border border-cyan-800/40">
                                  {t('contacts.body_likes_prefix', 'Likes')}: {formatBodyPreferenceLabel(k, t)}
                                </span>
                              ))}
                              {heightDislikes.map((k, idx) => (
                                <span key={`hd-${idx}`} className="text-[11px] px-2 py-0.5 rounded bg-red-950/40 text-red-300 border border-red-800/40">
                                  {t('contacts.body_dislikes_prefix', 'Dislikes')}: {formatBodyPreferenceLabel(k, t)}
                                </span>
                              ))}
                            </div>
                          </div>
                        );
                      })()}
                    </div>
                  )}

                  {debugDossierTab === 'history' && (() => {
                    const recentMemories = Array.isArray(npc.recent_memories)
                      ? npc.recent_memories
                      : (Array.isArray(npc.rel_history) ? npc.rel_history : []);
                    return (
                      <div className="space-y-2.5">
                        {(basic.primary_facility || basic.secondary_facility) && (
                          <div className="bg-black/40 p-2 rounded border border-fantasy-border/40 space-y-1 text-[11px]">
                            <span className="font-bold text-amber-400 uppercase tracking-wider block">
                              📍 Schedule & Haunts
                            </span>
                            {basic.primary_facility && <div>• <strong>{t('codex.primary_facility', 'Primary Facility:')}</strong> {basic.primary_facility}</div>}
                            {basic.secondary_facility && <div>• <strong>{t('codex.secondary_hangout', 'Secondary Hangout:')}</strong> {basic.secondary_facility}</div>}
                          </div>
                        )}
                        <div className="space-y-1.5">
                          <span className="text-[10.5px] font-bold text-amber-400 uppercase tracking-wider block">
                            📜 Shared Interactions ({recentMemories.length})
                          </span>
                          {recentMemories.length === 0 ? (
                            <p className="text-gray-500 italic text-[11px]">{t('codex.no_shared_interactions', 'No shared interactions recorded yet.')}</p>
                          ) : (
                            recentMemories.map((mem, idx) => {
                              const text = typeof mem === 'string' ? mem : (mem.memory_fact || mem.summary || JSON.stringify(mem));
                              return (
                                <div key={idx} className="p-2 rounded bg-black/50 border border-fantasy-border/30 text-gray-200 text-[11px]">
                                  • {text}
                                </div>
                              );
                            })
                          )}
                        </div>
                      </div>
                    );
                  })()}

                  {debugDossierTab === 'relations' && (() => {
                    const disRel = npc.disclosed_relations || {};
                    const romData = disRel.romance || relations.romance || {};
                    const famData = disRel.family || {};
                    const friendsList = disRel.friends?.members || relations.friends || [];
                    const rivalsList = disRel.rivals?.members || relations.rivals || [];
                    return (
                      <div className="space-y-2.5 text-[11px]">
                        <div>
                          <span className="font-bold text-fantasy-accent uppercase tracking-wider block mb-1">
                            👨‍👩‍👧‍👦 Immediate Family Tree
                          </span>
                          {famData.members && famData.members.length > 0 ? (
                            <div className="space-y-1">
                              {famData.members.map((mem, i) => (
                                <div key={i} className="text-gray-300">
                                  • <strong>{mem.relation || 'Relative'}:</strong> {renderLinkedPerson(mem)} {mem.race ? `(${formatRace(mem.race, t)})` : ''}
                                </div>
                              ))}
                            </div>
                          ) : Array.isArray(familyTree) && familyTree.length > 0 ? (
                            <div className="space-y-1">
                              {familyTree.map((mem, i) => (
                                <div key={i} className="text-gray-300">
                                  • <strong>{mem.relation || 'Relative'}:</strong> {renderLinkedPerson(mem.name || mem)}
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p className="text-gray-500 italic">{t('codex.no_family_records', 'No family records recorded.')}</p>
                          )}
                        </div>
                        <div className="pt-2 border-t border-fantasy-border/30 space-y-1">
                          <span className="font-bold text-pink-400 uppercase tracking-wider block">
                            💖 Romantic Standing
                          </span>
                          <div>
                            • <strong>{t('codex.current_status', 'Current Status:')}</strong>{' '}
                            {romData.current_partner
                              ? renderLinkedPerson(romData.current_partner, 'text-pink-300 font-semibold')
                              : (romData.status || 'Single')}
                          </div>
                          {romData.ex_partners && romData.ex_partners.length > 0 && (
                            <div>
                              • <strong>{t('codex.past_ex_partners', 'Past Ex-Partner(s):')}</strong>{' '}
                              {romData.ex_partners.map((p, idx) => (
                                <Fragment key={idx}>
                                  {idx > 0 ? ', ' : ''}
                                  {renderLinkedPerson(p)}
                                </Fragment>
                              ))}
                            </div>
                          )}
                        </div>
                        <div className="pt-2 border-t border-fantasy-border/30 space-y-1">
                          <span className="font-bold text-cyan-400 uppercase tracking-wider block">{t('codex.friends_header', '🤝 Friends')}</span>
                          {friendsList.length > 0 ? (
                            friendsList.map((f, i) => <div key={i} className="text-cyan-300">• {renderLinkedPerson(f)}</div>)
                          ) : (
                            <p className="text-gray-500 italic">{t('codex.no_friends', 'No close friends recorded.')}</p>
                          )}
                        </div>
                        <div className="pt-2 border-t border-fantasy-border/30 space-y-1">
                          <span className="font-bold text-amber-400 uppercase tracking-wider block">{t('codex.rivals_header', '⚔️ Rivals')}</span>
                          {rivalsList.length > 0 ? (
                            rivalsList.map((r, i) => <div key={i} className="text-amber-300">• {renderLinkedPerson(r)}</div>)
                          ) : (
                            <p className="text-gray-500 italic">{t('codex.no_rivals', 'No known rivals recorded.')}</p>
                          )}
                        </div>
                      </div>
                    );
                  })()}

                  {debugDossierTab === 'intimate' && (
                    <IntimateDossierPanel
                      npc={npc}
                      t={t}
                      infoLevel={npc.info_level ?? 3}
                      isDebugRevealed={true}
                      renderBulletPoints={renderBulletPoints}
                      isNsfw={true}
                      compact={true}
                    />
                  )}
                </div>
              </div>
            )}

            <OperativeCombatDossierCard
              npc={npc}
              isSpecialAgent={isSpecialAgent}
              isCivilianTag={isCivilianTag}
              isInParty={isInParty}
              isDeceased={isDeceased}
              isDebugRevealed={isDebugRevealed}
              t={t}
            />

            <KnownWardrobeCard npc={npc} showDebug={isDebugRevealed} t={t} />

            <KnownRoutineCard npc={npc} t={t} />
          </div>
        )}
      </div>
    );
  });
};

export default CodexCharactersTab;
