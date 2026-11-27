import { Fragment, useId, useRef } from 'react';
import { Scroll } from 'lucide-react';
import KnownRoutineCard from './KnownRoutineCard';
import KnownWardrobeCard from './KnownWardrobeCard';
import IntimateDossierPanel from './IntimateDossierPanel';
import OperativeCombatDossierCard from './OperativeCombatDossierCard';
import { formatAgeCategory, formatPhysique, formatRace, formatStature, formatTitle } from '../../utils/npcDemographics';
import {
  HEIGHT_PREFERENCE_KEYS,
  formatAssetTexture,
  formatBodyPreferenceLabel,
  isFemaleGender,
  isMaleGender,
  normalizeAssetTextureClient,
  stripTextureFromSizeClient,
} from '../../utils/anatomyOptions';

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

export const isRedundantAgentTierGrade = (gradeVal, isSpecialAgent) => {
  if (!isSpecialAgent || !gradeVal) return false;
  return /\btier\b|\boperative\b|\bagent\b/i.test(String(gradeVal));
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
  sourceKind: _sourceKind = 'contact',
  activeTab = 'persona',
  onTabChange,
  topSlot = null,
  renderBulletPoints = defaultBulletRenderer,
  findLinkedPerson = null,
  renderLinkedPerson = null,
  onJumpToPerson = null,
}) => {
  const tabRefs = useRef({});
  const tabIdPrefix = useId();
  const basic = npc?.basic_info || {};
  const appearance = npc?.appearance || {};
  const familyTree = npc?.family_tree || {};
  const relations = npc?.relations || {};
  const score = npc?.relationship_score ?? npc?.affinity_score ?? npc?.affinity ?? 0;
  const infoLevel = npc?.info_level ?? 0;
  const skillMod = npc?.skill_modifier ?? Math.floor(Math.max(0, score) / 20);
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

  const rawGender = String(basic.gender || npc?.gender || appearance.gender || '').trim();
  const isMale = isMaleGender(rawGender);
  const isFemale = isFemaleGender(rawGender);
  const isNsfwScenario = Boolean(
    session?.is_nsfw ||
    npc?.is_nsfw ||
    (session?.scenario && String(session.scenario).toLowerCase().includes('nsfw')) ||
    (Array.isArray(session?.scenario_tags) && session.scenario_tags.includes('nsfw'))
  );
  const visibleTabs = isNsfwScenario ? DOSSIER_TABS : DOSSIER_TABS.filter((tb) => tb.id !== 'intimate');
  const effectiveActiveTab = visibleTabs.some((tb) => tb.id === activeTab) ? activeTab : visibleTabs[0].id;

  const handleDossierTabKeyDown = (e) => {
    const idx = visibleTabs.findIndex(tb => tb.id === effectiveActiveTab);
    if (idx === -1) return;
    let nextIdx = idx;
    if (e.key === 'ArrowRight') nextIdx = (idx + 1) % visibleTabs.length;
    else if (e.key === 'ArrowLeft') nextIdx = (idx - 1 + visibleTabs.length) % visibleTabs.length;
    else if (e.key === 'Home') nextIdx = 0;
    else if (e.key === 'End') nextIdx = visibleTabs.length - 1;
    else return;
    e.preventDefault();
    const nextTab = visibleTabs[nextIdx];
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

  return (
    <div className="space-y-3 pt-2.5 border-t border-fantasy-border/40 text-xs text-gray-300">
      {isBlocked && (
        <div className="p-2.5 rounded-lg border border-red-800/60 bg-red-950/35 text-red-200 text-[11px] leading-snug">
          🚫 {t('phone.blocked_notice', 'This contact has blocked your number due to hostility. Reconcile with them in person first.')}
        </div>
      )}

      {topSlot}

      {/* Dossier Folder Tabs */}
      <div className="hk-dossier-tabs-wrap">
        <div
          role="tablist"
          aria-label={`${npc?.name || 'NPC'} dossier sections`}
          onKeyDown={handleDossierTabKeyDown}
          className={`grid ${visibleTabs.length === 4 ? 'grid-cols-4' : 'grid-cols-3'} border-b border-fantasy-border/70 pt-1.5 px-1 bg-black/60 rounded-t-lg gap-1 items-end select-none`}
        >
          {visibleTabs.map(tb => {
            const isActive = effectiveActiveTab === tb.id;
            const shortLbl = t(tb.shortKey, tb.shortLabel);
            const fullLbl = t(tb.fullKey, tb.fullLabel);
            return (
              <button
                key={tb.id}
                id={`${tabIdPrefix}-tab-${tb.id}`}
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
                className={`hk-dossier-tab min-w-0 py-2 px-1 text-xs font-bold transition-all flex items-center justify-center gap-1 rounded-t-md relative cursor-pointer border-t border-x ${
                  isActive
                    ? 'bg-black/40 text-fantasy-accent border-fantasy-border/70 border-b-black/40 -mb-px z-10 shadow-sm'
                    : 'bg-black/25 text-gray-400 hover:text-gray-200 hover:bg-black/40 border-transparent border-b border-b-fantasy-border/70'
                }`}
              >
                <span className="text-xs shrink-0">{tb.icon}</span>
                <span className="truncate text-[11px] font-semibold">
                  <span className="hk-dossier-tab-full">{fullLbl}</span>
                  <span className="hk-dossier-tab-short">{shortLbl}</span>
                </span>
              </button>
            );
          })}
        </div>

        {/* Folder Panel Content Body */}
        <div
          role="tabpanel"
          aria-labelledby={`${tabIdPrefix}-tab-${effectiveActiveTab}`}
          className="bg-black/40 border-x border-b border-fantasy-border/70 rounded-b-lg p-3 text-xs -mt-px space-y-3"
        >
          {/* SUBTAB 1: PERSONA */}
          {effectiveActiveTab === 'persona' && (() => {
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

            const buildParts = [stature ? formatStature(stature, t) : null, physique ? formatPhysique(physique, t) : null].filter(Boolean);
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

            return (
              <div className="space-y-2.5">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-xs px-2 py-0.5 rounded bg-fantasy-accent/15 text-fantasy-accent border border-fantasy-accent/30 font-mono font-medium">
                    {t('contacts.info_level_badge', 'Info Level: {{level}}/3', { level: infoLevel })}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded bg-emerald-950/50 text-emerald-300 border border-emerald-700/40 font-mono font-medium">
                    {t('contacts.skill_modifier_badge', 'Skill Modifier: +{{mod}}', { mod: skillMod })}
                  </span>
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
                          {isNsfwScenario && (isFemale || Boolean(appearance.breast_size)) && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-pink-950/40 border border-pink-800/50 text-pink-300">
                              <span className="text-pink-400 font-medium">{t('contacts.breast_size', '🔞 Breast Size:')}</span>
                              <strong className="text-pink-100 font-medium">
                                {formatTitle(appearance.breast_size || 'Modest B-Cup')}
                              </strong>
                              {(() => {
                                if (!(npc?.intimate_dossier_revealed || npc?.debug_revealed) || !appearance.asset_texture) return null;
                                const normT = normalizeAssetTextureClient(appearance.asset_texture, false);
                                const bStr = String(appearance.breast_size || '');
                                if (normT && stripTextureFromSizeClient(bStr, false) !== bStr) return null;
                                return (
                                  <span className="text-pink-200 text-[10px] italic font-normal">
                                    ({formatAssetTexture(appearance.asset_texture, false, t)})
                                  </span>
                                );
                              })()}
                            </span>
                          )}
                          {isNsfwScenario && canShowMaleSize && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-purple-950/40 border border-purple-800/50 text-purple-300">
                              <span className="text-purple-400 font-medium">{t('contacts.penis_size', '🔞 Penis Size:')}</span>
                              <strong className="text-purple-100 font-medium">
                                {formatTitle(appearance.penis_size)}
                              </strong>
                              {(() => {
                                if (!(npc?.intimate_dossier_revealed || npc?.debug_revealed) || !appearance.asset_texture) return null;
                                const normT = normalizeAssetTextureClient(appearance.asset_texture, true);
                                const pStr = String(appearance.penis_size || '');
                                if (normT && stripTextureFromSizeClient(pStr, true) !== pStr) return null;
                                return (
                                  <span className="text-purple-200 text-[10px] italic font-normal">
                                    ({formatAssetTexture(appearance.asset_texture, true, t)})
                                  </span>
                                );
                              })()}
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

              {(Array.isArray(appearance.body_likes) || Array.isArray(appearance.body_dislikes)) && (() => {
                const heightLikes = (appearance.body_likes || []).filter((k) => HEIGHT_PREFERENCE_KEYS.includes(String(k || '').toLowerCase()));
                const heightDislikes = (appearance.body_dislikes || []).filter((k) => HEIGHT_PREFERENCE_KEYS.includes(String(k || '').toLowerCase()));
                if (heightLikes.length === 0 && heightDislikes.length === 0) return null;
                return (
                  <div>
                    <span className="text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1">
                      📏 {t('contacts.height_preference_label', 'Height Preference')}
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {heightLikes.map((k, idx) => (
                        <span
                          key={`hl-${idx}`}
                          className="text-xs px-2 py-0.5 rounded border bg-cyan-950/40 text-cyan-300 border-cyan-800/40"
                        >
                          {t('contacts.body_likes_prefix', 'Likes')}: {formatBodyPreferenceLabel(k, t)}
                        </span>
                      ))}
                      {heightDislikes.map((k, idx) => (
                        <span
                          key={`hd-${idx}`}
                          className="text-xs px-2 py-0.5 rounded border bg-red-950/40 text-red-300 border-red-800/40"
                        >
                          {t('contacts.body_dislikes_prefix', 'Dislikes')}: {formatBodyPreferenceLabel(k, t)}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })()}
            </div>
          );
        })()}

        {/* SUBTAB 2: SHARED HISTORY */}
        {effectiveActiveTab === 'history' && (() => {
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
        {effectiveActiveTab === 'relations' && (() => {
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
            </div>
          );
        })()}

        {/* SUBTAB 4: INTIMATE & HISTORY */}
        {isNsfwScenario && effectiveActiveTab === 'intimate' && (
          <IntimateDossierPanel
            npc={npc}
            t={t}
            infoLevel={infoLevel}
            isDebugRevealed={isDebugRevealed}
            renderBulletPoints={renderBulletPoints}
            isNsfw={isNsfwScenario}
            romanticKeywords={ROMANTIC_KEYWORDS}
          />
        )}
        </div>
      </div>

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
  );
};

export default NpcDossierBody;
