import { Flame, Heart, Sparkles } from 'lucide-react';
import {
  formatAssetTexture,
  formatBodyPreferenceLabel,
  formatFusedRear,
  isFemaleGender,
  isFeralRearExcluded,
  isMaleGender,
  stripRearTextureFromSizeClient,
} from '../../utils/anatomyOptions';
import { formatTitle } from '../../utils/npcDemographics';

const stripItemTags = (val) =>
  String(val || '')
    .replace(/\s*\((?:Physical|Action)\)\s*/gi, ' ')
    .replace(/\s+,/g, ',')
    .replace(/\s{2,}/g, ' ')
    .trim()
    .replace(/^,+|,+$/g, '')
    .trim();

const DEFAULT_ROMANTIC_KEYWORDS = [
  'kiss', 'confess', 'date', 'intercourse', 'oral', 'manual', 'anal', 'virgin',
  'intimate', 'bedroom', 'made love', 'make love', 'slept together',
  'affectionate', 'tender', 'romantic', 'romance', 'caress', 'embrace', 'cuddle',
  'passionate', 'passion',
];

const FIRST_TRACK_LABELS = {
  intercourse: { key: 'contacts.track_intercourse_short', fallback: 'Intercourse' },
  oral: { key: 'contacts.track_oral_short', fallback: 'Oral' },
  manual: { key: 'contacts.track_manual_short', fallback: 'Manual' },
  anal: { key: 'contacts.track_anal_short', fallback: 'Anal' },
};

const PillList = ({ items = [], pillClass = '', t, renderExtra = null }) => {
  if (!items || items.length === 0) return null;
  const maskedLabel = t('social.masked_slot', '???');
  return (
    <div className="flex flex-wrap gap-1.5 mt-1">
      {items.map((item, idx) => {
        const isObj = typeof item === 'object' && item !== null;
        const isMasked = isObj ? Boolean(item.masked || item.label === '???') : item === '???';
        const label = isObj ? stripItemTags(item.label) : stripItemTags(item);
        if (!label && !isMasked) return null;
        if (isMasked) {
          return (
            <span
              key={`m-${idx}`}
              className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] bg-black/40 text-gray-500 border border-gray-700/40 italic"
            >
              {maskedLabel}
            </span>
          );
        }
        return (
          <span
            key={`${label}-${idx}`}
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] border ${pillClass}`}
          >
            <span>{label}</span>
            {typeof renderExtra === 'function' ? renderExtra(item) : null}
          </span>
        );
      })}
    </div>
  );
};

const IntimateDossierPanel = ({
  npc,
  t,
  infoLevel = 1,
  isDebugRevealed = false,
  renderBulletPoints,
  isNsfw = true,
  compact = false,
  romanticKeywords = DEFAULT_ROMANTIC_KEYWORDS,
}) => {
  if (!isNsfw) return null;
  const basic = npc?.basic_info || {};
  const appearance = npc?.appearance || {};
  const memories = npc?.intimate_memories || [];
  const intSec = npc?.intimate_sections || {};
  const rawStructured = npc?.intimate_structured;
  const structured =
    rawStructured && typeof rawStructured === 'object' && Object.keys(rawStructured).length > 0
      ? rawStructured
      : null;
  const chemistry = npc?.intimate_chemistry || null;
  const sharedStats = npc?.shared_intimacy_stats || null;
  const hasSections = Boolean(intSec.anatomy && intSec.dynamic);

  const rawGen = String(basic.gender || npc?.gender || appearance.gender || '').trim();
  const isMaleNpc = isMaleGender(rawGen);
  const isFemaleNpc = isFemaleGender(rawGen);
  const showBreastFallback = isFemaleNpc || Boolean(appearance.breast_size);
  const npcRace = basic.race || npc?.race || appearance.race || '';
  const feralRearExcluded = isFeralRearExcluded(npcRace);

  const bSize = appearance.breast_size || (isFemaleNpc ? 'Modest B-Cup' : '');
  const bTitle = bSize ? bSize.charAt(0).toUpperCase() + bSize.slice(1) : '';
  const pSize = appearance.penis_size || 'Average';
  const pTitle = pSize.charAt(0).toUpperCase() + pSize.slice(1);
  const sizeDisplay = isMaleNpc
    ? ((infoLevel >= 3 || isDebugRevealed) ? pTitle : t('common.unknown', 'Unknown'))
    : (bTitle || t('common.unknown', 'Unknown'));

  const iExpDisp =
    appearance.experience && appearance.experience.toLowerCase() !== 'unknown'
      ? appearance.experience
      : ((infoLevel >= 3 || isDebugRevealed)
          ? (appearance.intercourse_experience === 'virgin' ? 'Virgin' : 'Non-Virgin')
          : t('common.unknown', 'Unknown'));
  const oExpDisp = (infoLevel >= 3 || isDebugRevealed) ? (appearance.oral_experience || 'Inexperienced') : t('common.unknown', 'Unknown');
  const mExpDisp = (infoLevel >= 3 || isDebugRevealed) ? (appearance.manual_experience || 'Inexperienced') : t('common.unknown', 'Unknown');
  const aExpDisp = (infoLevel >= 3 || isDebugRevealed) ? (appearance.anal_experience || 'Inexperienced') : t('common.unknown', 'Unknown');

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
    return romanticKeywords.some(kw => s.includes(kw));
  };
  const sharedMilestones =
    npc?.shared_romantic_milestones && npc.shared_romantic_milestones.length > 0
      ? npc.shared_romantic_milestones
      : memories.filter(isRomanticMilestone);

  const rawBodyLikes = Array.isArray(appearance.body_likes) ? appearance.body_likes : [];
  const rawBodyDislikes = Array.isArray(appearance.body_dislikes) ? appearance.body_dislikes : [];
  const filterFallbackBodyPrefs = (list) => {
    if (feralRearExcluded) return [];
    if (infoLevel >= 3 || isDebugRevealed) return list;
    if (infoLevel >= 2) {
      return list.filter((k) => ['taller_partner', 'shorter_partner'].includes(String(k || '').trim().toLowerCase()));
    }
    return [];
  };
  const bodyLikes = structured?.body_likes ?? filterFallbackBodyPrefs(rawBodyLikes);
  const bodyDislikes = structured?.body_dislikes ?? filterFallbackBodyPrefs(rawBodyDislikes);

  const hasSharedLedger = Boolean(
    isNsfw &&
    sharedStats &&
    ((Number(sharedStats.shared_encounters) || 0) > 0 ||
      (Number(sharedStats.partner_climaxes) || 0) > 0 ||
      (Array.isArray(sharedStats.firsts_badges) && sharedStats.firsts_badges.length > 0))
  );

  return (
    <div className={compact ? 'space-y-2.5 text-[11px]' : 'space-y-3'}>
      {isNsfw && chemistry?.has_any && (
        <div className="bg-gradient-to-br from-pink-950/40 via-purple-950/30 to-black/50 border border-pink-700/40 rounded-lg p-2.5 space-y-1.5">
          <span className="text-[11px] font-bold text-pink-300 uppercase tracking-wider flex items-center gap-1.5">
            <Sparkles size={12} className="text-pink-400" />
            <span>{t('contacts.chemistry_synergy_header', 'Chemistry & Synergy')}</span>
          </span>
          {chemistry.best_approach && (
            <p className="text-xs text-gray-200 leading-relaxed">{chemistry.best_approach}</p>
          )}
          {Array.isArray(chemistry.body_match) && chemistry.body_match.length > 0 && (
            <div className="flex flex-wrap items-center gap-1 pt-0.5">
              <span className="text-[10px] text-gray-400 mr-1">{t('contacts.chemistry_body_match', 'Physique')}:</span>
              {chemistry.body_match.map((tag, i) => (
                <span key={`bm-${i}`} className="px-1.5 py-0.5 rounded bg-purple-950/60 border border-purple-700/40 text-purple-200 text-[10px]">
                  {tag}
                </span>
              ))}
            </div>
          )}
          {Array.isArray(chemistry.act_alignment) && chemistry.act_alignment.length > 0 && (
            <div className="flex flex-wrap items-center gap-1">
              <span className="text-[10px] text-gray-400 mr-1">{t('contacts.chemistry_act_alignment', 'Synergy')}:</span>
              {chemistry.act_alignment.map((tag, i) => (
                <span key={`aa-${i}`} className="px-1.5 py-0.5 rounded bg-emerald-950/50 border border-emerald-700/40 text-emerald-200 text-[10px]">
                  {tag}
                </span>
              ))}
            </div>
          )}
          {Array.isArray(chemistry.watch_out) && chemistry.watch_out.length > 0 && (
            <div className="flex flex-wrap items-center gap-1">
              <span className="text-[10px] text-gray-400 mr-1">{t('contacts.chemistry_watch_out', 'Avoid')}:</span>
              {chemistry.watch_out.map((tag, i) => (
                <span key={`wo-${i}`} className="px-1.5 py-0.5 rounded bg-red-950/50 border border-red-800/40 text-red-200 text-[10px]">
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

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
                <span className="text-pink-300 font-medium">{formatAssetTexture(appearance.asset_texture, isMaleNpc, t)}</span>
              </div>
            )}
            {!feralRearExcluded && appearance.rear_size && (
              <div>
                • <strong className="text-gray-100">{t('contacts.rear_size_plain', 'Rear')}</strong>:{' '}
                {(infoLevel >= 3 || isDebugRevealed)
                  ? (formatFusedRear(appearance.rear_size, appearance.rear_texture, t).label || formatTitle(appearance.rear_size))
                  : (formatFusedRear(stripRearTextureFromSizeClient(appearance.rear_size), '', t).sizeOnly || stripRearTextureFromSizeClient(appearance.rear_size))}
              </div>
            )}
            {!feralRearExcluded && appearance.rear_texture && (infoLevel >= 3 || isDebugRevealed) && (
              <div>
                • <strong className="text-gray-100">{t('contacts.rear_texture_label', 'Rear Feature')}</strong>:{' '}
                <span className="text-pink-300 font-medium">{formatFusedRear(appearance.rear_size, appearance.rear_texture, t).textureOnly}</span>
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
        {(() => {
          const comfortBadgeMap = {
            warming_up: t('contacts.comfortWarmingUp', 'Warming Up With You'),
            trusting_private: t('contacts.comfortTrustingPrivate', 'Trusting in Private'),
            deeply_bonded: t('contacts.comfortDeeplyBonded', 'Deeply Bonded'),
          };
          const contrastLabelMap = {
            hidden_fire: t('contacts.contrastHiddenFire', 'Hidden Fire'),
            all_talk_tease: t('contacts.contrastAllTalkTease', 'All-Talk Tease'),
          };
          const comfortObj = structured?.with_you_comfort || null;
          const contrastObj = structured?.openness_contrast || null;
          const comfortText = comfortObj?.badge_key ? (comfortBadgeMap[comfortObj.badge_key] || comfortObj.badge_label) : '';
          const contrastText = contrastObj?.archetype ? (contrastLabelMap[contrastObj.archetype] || contrastObj.label) : '';
          const opennessRevealed =
            isDebugRevealed ||
            Boolean(appearance.openness_revealed) ||
            (structured?.openness ? structured.openness.masked === false : infoLevel >= 2);
          const rawOpennessDisplay =
            (structured?.openness && !structured.openness.masked && structured.openness.label) ||
            appearance.erotic_openness ||
            appearance.openness ||
            '';

          const renderStructuredOpennessRow = () => (
            <div className="flex flex-wrap items-center gap-1.5 mt-0.5 text-gray-300 leading-relaxed">
              <span>
                • <strong className="text-gray-100">{t('contacts.openness', 'Openness')}</strong>:{' '}
                {opennessRevealed && rawOpennessDisplay
                  ? rawOpennessDisplay
                  : <span className="text-gray-500 italic">{structured?.openness?.masked ? t('social.masked_slot', '???') : t('common.unknown', 'Unknown')}</span>}
              </span>
              {opennessRevealed && comfortText && (
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] bg-emerald-950/60 text-emerald-200 border border-emerald-500/35">
                  {comfortText}
                </span>
              )}
              {opennessRevealed && contrastText && (
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] bg-fuchsia-950/60 text-fuchsia-200 border border-fuchsia-500/35">
                  {contrastText}
                </span>
              )}
            </div>
          );

          if (hasSections && intSec.dynamic) {
            const baseDynamicLines = structured?.openness
              ? intSec.dynamic.filter((line) => !String(line || '').includes('**Openness**'))
              : intSec.dynamic;
            return (
              <div className="space-y-1">
                {baseDynamicLines.length > 0 && renderBulletPoints(baseDynamicLines, t)}
                {structured?.openness && renderStructuredOpennessRow()}
              </div>
            );
          }

          return (
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
              {renderStructuredOpennessRow()}
            </div>
          );
        })()}
      </div>

      <div className="pt-2 border-t border-fantasy-border/30">
        <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider block mb-1.5 flex items-center gap-1.5">
          {t('contacts.undergarments_header', '🩲 Undergarments')}
        </span>
        {structured?.undergarments ? (
          <div className="space-y-1 text-gray-300 leading-relaxed text-xs">
            {Boolean(structured.undergarments.bra) && (
              <div>
                • <strong className="text-gray-100">{t('contacts.bra', 'Bra')}</strong>:{' '}
                {structured.undergarments.bra_masked
                  ? <span className="text-gray-500 italic">{t('social.masked_slot', '???')}</span>
                  : structured.undergarments.bra}
              </div>
            )}
            <div>
              • <strong className="text-gray-100">{t('contacts.underwear', 'Underwear')}</strong>:{' '}
              {structured.undergarments.underwear_masked
                ? <span className="text-gray-500 italic">{t('social.masked_slot', '???')}</span>
                : structured.undergarments.underwear}
            </div>
          </div>
        ) : hasSections && intSec.undergarments ? (
          renderBulletPoints(intSec.undergarments, t)
        ) : (
          <div className="space-y-1 text-gray-300 leading-relaxed">
            {(showBreastFallback || Boolean(braVal)) && (
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
        {Array.isArray(structured?.sensitive_spots) && structured.sensitive_spots.length > 0 ? (
          <PillList
            items={structured.sensitive_spots}
            pillClass="bg-pink-950/50 text-pink-200 border-pink-700/50"
            t={t}
          />
        ) : hasSections && (intSec.sensitive_spots || intSec.sensitivities) ? (
          renderBulletPoints(
            (intSec.sensitive_spots || (Array.isArray(intSec.sensitivities) ? intSec.sensitivities.filter(s => typeof s === 'string' && s.toLowerCase().includes('sensitive spot')) : [])).map(stripItemTags),
            t
          )
        ) : (
          <div className="text-xs text-gray-300 leading-relaxed">
            • <strong className="text-gray-100">{t('contacts.sensitive_spots', 'Sensitive Spots')}</strong>:{' '}
            {(infoLevel >= 3 || isDebugRevealed) && appearance.sensitive_spots
              ? stripItemTags(appearance.sensitive_spots)
              : <span className="text-gray-500 italic">{t('common.unknown', 'Unknown')}</span>}
          </div>
        )}
      </div>

      <div className="pt-2 border-t border-fantasy-border/30 space-y-2">
        <span className="text-xs font-bold text-amber-400 uppercase tracking-wider block flex items-center gap-1.5">
          {t('contacts.desires_turnoffs_header', '🔥 Desires & Turn-Offs')}
        </span>
        {structured ? (
          <div className="space-y-2 text-xs">
            {Array.isArray(structured.desires) && structured.desires.length > 0 && (
              <div>
                <span className="text-[11px] font-semibold text-gray-200">{t('contacts.desires_label', 'Desires')}</span>
                <PillList
                  items={structured.desires}
                  pillClass="bg-amber-950/40 text-amber-200 border-amber-700/40"
                  t={t}
                />
              </div>
            )}
            {structured.active_kink && (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[11px] font-semibold text-fuchsia-300">{t('contacts.active_kink_label', 'Active Kink')}:</span>
                {structured.active_kink.masked ? (
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] bg-black/40 text-gray-500 border border-gray-700/40 italic">
                    {t('social.masked_slot', '???')}
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-fuchsia-950/60 text-fuchsia-200 border border-fuchsia-500/60 shadow-sm">
                    <Flame size={11} className="text-fuchsia-300" />
                    <span>{stripItemTags(structured.active_kink.label)}</span>
                  </span>
                )}
              </div>
            )}
            {Array.isArray(structured.turn_offs) && structured.turn_offs.length > 0 && (
              <div>
                <span className="text-[11px] font-semibold text-red-300">{t('contacts.turn_offs', 'Turn-Offs')}</span>
                <PillList
                  items={structured.turn_offs}
                  pillClass="bg-red-950/50 text-red-200 border-red-800/50"
                  t={t}
                />
              </div>
            )}
            {!structured.desires?.length && !structured.active_kink && !structured.turn_offs?.length && (infoLevel >= 3 || isDebugRevealed) && (
              <div className="space-y-1 text-gray-300 leading-relaxed text-xs">
                <div>• <strong className="text-gray-100">{t('contacts.desires_label', 'Desires')}</strong>: <span className="text-gray-400">{t('common.none', 'None')}</span></div>
                <div>• <strong className="text-red-300">{t('contacts.turn_offs', 'Turn-Offs')}</strong>: <span className="text-gray-400">{t('common.none', 'None')}</span></div>
              </div>
            )}
          </div>
        ) : hasSections && (intSec.desires_and_turn_offs || intSec.sensitivities) ? (
          renderBulletPoints(
            (intSec.desires_and_turn_offs || (Array.isArray(intSec.sensitivities) ? intSec.sensitivities.filter(s => typeof s === 'string' && !s.toLowerCase().includes('sensitive spot')) : [])).map(stripItemTags),
            t
          )
        ) : (
          <div className="space-y-1 text-gray-300 leading-relaxed text-xs">
            <div>
              • <strong className="text-gray-100">{t('contacts.desires_kinks', 'Desires & Kinks')}</strong>:{' '}
              {(infoLevel >= 3 || isDebugRevealed) && (appearance.desires_and_kinks || appearance.turn_ons)
                ? stripItemTags(
                    Array.isArray(appearance.desires_and_kinks || appearance.turn_ons)
                      ? (appearance.desires_and_kinks || appearance.turn_ons).join(', ')
                      : (appearance.desires_and_kinks || appearance.turn_ons)
                  )
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
        {(bodyLikes.length > 0 || bodyDislikes.length > 0) && (
          <div className="text-xs text-gray-300">
            • <strong className="text-amber-300">{t('contacts.body_preferences_label', 'Body Preferences')}</strong>:{' '}
            {[
              bodyLikes.length
                ? `${t('contacts.body_likes_prefix', 'Likes')}: ${bodyLikes.map(k => formatBodyPreferenceLabel(k, t)).join(', ')}`
                : '',
              bodyDislikes.length
                ? `${t('contacts.body_dislikes_prefix', 'Dislikes')}: ${bodyDislikes.map(k => formatBodyPreferenceLabel(k, t)).join(', ')}`
                : '',
            ].filter(Boolean).join(' • ')}
          </div>
        )}
      </div>

      <div className="pt-2 border-t border-fantasy-border/30 space-y-2">
        <span className="text-xs font-bold text-rose-400 uppercase tracking-wider block flex items-center gap-1.5">
          {t('contacts.act_preferences_header', '❤️ Act & Position Preferences')}
        </span>
        {structured ? (
          <div className="space-y-2 text-xs">
            {Array.isArray(structured.act_likes) && structured.act_likes.length > 0 && (
              <div>
                <span className="text-[11px] font-semibold text-emerald-300">{t('contacts.preferred_likes', 'Preferred / Likes')}</span>
                <PillList
                  items={structured.act_likes}
                  pillClass="bg-emerald-950/40 text-emerald-200 border-emerald-700/40"
                  t={t}
                  renderExtra={(it) => (it?.curious ? (
                    <span className="ml-1 px-1.5 py-0.5 rounded bg-amber-900/60 text-amber-200 border border-amber-600/50 text-[10px] font-medium">
                      {t('contacts.curious_badge', 'Curious')}
                    </span>
                  ) : null)}
                />
              </div>
            )}
            {Array.isArray(structured.act_dislikes) && structured.act_dislikes.length > 0 && (
              <div>
                <span className="text-[11px] font-semibold text-rose-300">{t('contacts.aversions_dislikes', 'Aversions / Dislikes')}</span>
                <PillList
                  items={structured.act_dislikes}
                  pillClass="bg-rose-950/40 text-rose-200 border-rose-700/40"
                  t={t}
                />
              </div>
            )}
            {!structured.act_likes?.length && !structured.act_dislikes?.length && (infoLevel >= 3 || isDebugRevealed) && (
              <div className="space-y-1 text-gray-300 leading-relaxed text-xs">
                <div>• <strong className="text-gray-100">{t('contacts.preferred_likes', 'Preferred / Likes')}</strong>: <span className="text-gray-400">{t('common.none', 'None')}</span></div>
                <div>• <strong className="text-gray-100">{t('contacts.aversions_dislikes', 'Aversions / Dislikes')}</strong>: <span className="text-gray-400">{t('common.none', 'None')}</span></div>
              </div>
            )}
          </div>
        ) : hasSections && intSec.act_preferences ? (
          renderBulletPoints(intSec.act_preferences, t)
        ) : (
          <div className="space-y-1 text-gray-300 leading-relaxed text-xs">
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

      {hasSharedLedger && (
        <div className="pt-2 border-t border-fantasy-border/30">
          <div className="bg-black/45 border border-pink-800/35 rounded-lg p-2.5 space-y-1.5">
            <span className="text-[11px] font-bold text-pink-300 uppercase tracking-wider flex items-center gap-1.5">
              <Heart size={11} className="text-pink-400" />
              <span>{t('contacts.shared_with_you_header', 'Shared With You')}</span>
            </span>
            <div className="flex flex-wrap items-center gap-3 text-xs text-gray-200">
              <span>
                <strong className="text-pink-200">{sharedStats.shared_encounters || 0}</strong>{' '}
                {t('contacts.shared_encounters_label', 'Shared Encounters')}
              </span>
              <span>
                <strong className="text-pink-200">{sharedStats.partner_climaxes || 0}</strong>{' '}
                {t('contacts.partner_climaxes_label', 'Partner Climaxes')}
              </span>
            </div>
            {Array.isArray(sharedStats.firsts_badges) && sharedStats.firsts_badges.length > 0 && (
              <div className="flex flex-wrap gap-1.5 pt-0.5">
                {sharedStats.firsts_badges.map((trk) => {
                  const trkMeta = FIRST_TRACK_LABELS[trk] || { key: '', fallback: trk };
                  const trkLabel = trkMeta.key ? t(trkMeta.key, trkMeta.fallback) : trkMeta.fallback;
                  return (
                    <span
                      key={`ft-${trk}`}
                      className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-pink-950/70 text-pink-200 border border-pink-500/50"
                    >
                      {t('contacts.first_together_badge', 'First {{track}} Together', { track: trkLabel })}
                    </span>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      <div className="pt-2 border-t border-fantasy-border/30 space-y-1">
        <span className="text-xs font-bold text-gray-300 uppercase tracking-wider block mb-0.5">
          {t('contacts.past_intimate_history', 'Past Intimate History')}
        </span>
        {!compact && !isHistoryUnlocked ? (
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

      {!compact && (
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
      )}
    </div>
  );
};

export default IntimateDossierPanel;
