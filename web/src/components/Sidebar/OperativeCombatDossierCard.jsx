import { formatTitle } from '../../utils/npcDemographics';

/**
 * Shared bottom-aligned Combat Dossier (Special Agents) and Civilian Classification card
 * rendered consistently across Scene Side Card, Contacts, Acquaintances, and Known Characters.
 */
export default function OperativeCombatDossierCard({
  npc,
  isSpecialAgent = false,
  isCivilianTag = false,
  isInParty = false,
  isDeceased = false,
  isDebugRevealed = false,
  t,
}) {
  if (!npc || (!isSpecialAgent && !isCivilianTag)) {
    return null;
  }

  const basic = npc.basic_info || {};
  const score = npc.relationship_score ?? npc.affinity_score ?? npc.affinity ?? 0;
  const isCombatDossierUnlocked = Boolean(
    (npc.dossier_stage ?? 1) >= 2 ||
      score >= 15 ||
      isInParty ||
      isDebugRevealed ||
      npc.same_faction_colleague
  );

  if (isSpecialAgent) {
    const agentTier = npc.agent_tier || basic.agent_tier || 1;
    const rankTitle =
      npc.rank_title ||
      basic.rank_title ||
      t('codex.tier_operative_fallback', 'Tier {{tier}} Operative', { tier: agentTier });
    const agentClass =
      npc.agent_class ||
      basic.agent_class ||
      basic.role ||
      t('codex.special_agent_fallback', 'Special Agent');
    const cMaxHp = npc.combat_max_hp ?? 130;
    const cHp = npc.combat_hp ?? cMaxHp;
    const cMaxMp = npc.combat_max_mp ?? 60;
    const cMp = npc.combat_mp ?? cMaxMp;
    const wName = npc.weapon_profile?.name || '';
    const attr = npc.attribute || basic.attribute;
    const archetype = npc.combat_archetype || basic.combat_archetype;
    const medium = isDebugRevealed
      ? (npc.debug_ability_medium || npc.ability_medium)
      : npc.ability_medium;
    const abilities =
      (isDebugRevealed
        ? (npc.debug_innate_ability_details || npc.innate_ability_details)
        : npc.innate_ability_details) || [];

    return (
      <div className="bg-cyan-950/20 border border-cyan-800/50 rounded-lg p-2.5 space-y-2">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <span className="text-[11px] font-bold text-cyan-300 uppercase tracking-wider flex items-center gap-1">
            <span>⚡</span>
            <span>{t('codex.operative_dossier', 'Operative Combat Dossier')}</span>
          </span>
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-cyan-950/70 text-cyan-200 border border-cyan-700/50 font-semibold">
            {t('codex.tier_label', 'Tier')} {agentTier} • {rankTitle}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 text-[10.5px]">
          <span className="px-1.5 py-0.5 rounded bg-black/60 text-gray-200 border border-fantasy-border/50">
            {t('codex.class_label', 'Class')}: <strong className="text-white">{agentClass}</strong>
          </span>
          {attr && (
            <span className="px-1.5 py-0.5 rounded bg-cyan-950/60 text-cyan-200 border border-cyan-700/50 font-semibold">
              🧬 {t(`awakened.attrs.${String(attr).toLowerCase()}`, formatTitle(attr))}
            </span>
          )}
          {archetype && (
            <span className="px-1.5 py-0.5 rounded bg-indigo-950/60 text-indigo-200 border border-indigo-700/50 font-semibold">
              🛡️ {formatTitle(archetype)}
            </span>
          )}
          {isCombatDossierUnlocked && medium && (
            <span className="px-1.5 py-0.5 rounded bg-purple-950/60 text-purple-200 border border-purple-700/50 font-semibold">
              ⚙️ {formatTitle(medium)}
            </span>
          )}
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
                          {t('codex.ultimate_badge', 'Ultimate')}
                        </span>
                      )}
                    </span>
                    <span className="text-[9.5px] font-mono text-cyan-300 shrink-0">
                      {ab.is_ultimate ? t('codex.ultimate_cost_badge', '3 Pips • 0 MP') : `${ab.mp_cost ?? 10} MP`}
                    </span>
                  </div>
                  {ab.desc && <p className="text-[10px] text-gray-400 mt-0.5">{ab.desc}</p>}
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-[10px] text-gray-400 italic pt-1 border-t border-cyan-900/40">
            🔒 {t('awakened.dossier_stage2_locked', 'Stage 2 Classified — Unlocks at Affinity 15+, Party Companion, or Same-Faction Colleague.')}
          </p>
        )}
      </div>
    );
  }

  return (
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
          100 HP • 0 MP ({t('codex.unawakened_tag', 'Unawakened')})
        </span>
      </div>
      <p className="text-[10.5px] text-gray-400 leading-snug">
        {isDeceased
          ? t('codex.civilian_deceased_note', 'Perished permanently during an anomalous incursion due to lacking innate mana protection.')
          : t('codex.civilian_party_note', 'Mundane citizen with no mana or special abilities. Eligible as a Contact, but cannot be recruited into your field party.')}
      </p>
    </div>
  );
}
