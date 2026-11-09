import React, { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Scroll, Shield, Sparkles, Lock, Eye, CheckCircle2, ChevronDown, ChevronRight,
  Archive, HelpCircle, Compass, AlertTriangle
} from 'lucide-react';
import { formatCleanLocation } from '../../utils/locationFormat';

const STAGE_STYLES = {
  contained: {
    badge: 'bg-emerald-950/70 text-emerald-300 border-emerald-600/60',
    card: 'bg-emerald-950/15 border-emerald-700/50 hover:border-emerald-500/70',
    icon: CheckCircle2,
  },
  verified: {
    badge: 'bg-cyan-950/70 text-cyan-300 border-cyan-600/60',
    card: 'bg-cyan-950/15 border-cyan-700/50 hover:border-cyan-500/70',
    icon: Shield,
  },
  sighted: {
    badge: 'bg-amber-950/70 text-amber-300 border-amber-600/60',
    card: 'bg-amber-950/15 border-amber-700/50 hover:border-amber-500/70',
    icon: Eye,
  },
  undiscovered: {
    badge: 'bg-neutral-900/80 text-gray-500 border-neutral-700/60',
    card: 'bg-black/40 border-neutral-800/80 opacity-80',
    icon: Lock,
  },
};

const formatTag = (val) => {
  if (!val) return '';
  return String(val).replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
};

const EncyclopediaSubTab = ({ encyclopedia, searchQuery = '' }) => {
  const { t } = useTranslation();
  const [viewMode, setViewMode] = useState('folklore'); // 'folklore' | 'field_log'
  const [traditionFilter, setTraditionFilter] = useState('all');
  const [stageFilter, setStageFilter] = useState('all'); // 'all' | 'discovered' | 'contained' | 'undiscovered'
  const [expandedId, setExpandedId] = useState(null);

  const codexEntries = Array.isArray(encyclopedia?.folklore_codex) ? encyclopedia.folklore_codex : [];
  const traditions = Array.isArray(encyclopedia?.traditions) ? encyclopedia.traditions : [];
  const fieldLog = Array.isArray(encyclopedia?.field_log) ? encyclopedia.field_log : [];
  const vaultLog = Array.isArray(encyclopedia?.vault_log) ? encyclopedia.vault_log : [];
  const vaultReqs = Array.isArray(encyclopedia?.vault_requisitions) ? encyclopedia.vault_requisitions : [];

  const totalCount = encyclopedia?.total_folklore_count || codexEntries.length || 50;
  const discoveredCount = encyclopedia?.discovered_count || 0;
  const verifiedCount = encyclopedia?.verified_count || 0;
  const containedCount = encyclopedia?.contained_count || 0;
  const pctDiscovered = totalCount > 0 ? Math.min(100, Math.round((discoveredCount / totalCount) * 100)) : 0;

  const qNorm = String(searchQuery || '').trim().toLowerCase();

  const filteredCodex = useMemo(() => {
    return codexEntries.filter((entry) => {
      if (traditionFilter !== 'all' && entry.tradition_key !== traditionFilter && entry.tradition !== traditionFilter) {
        return false;
      }
      const st = entry.unlock_stage || 'undiscovered';
      if (stageFilter === 'discovered' && st === 'undiscovered') return false;
      if (stageFilter === 'contained' && st !== 'contained') return false;
      if (stageFilter === 'undiscovered' && st !== 'undiscovered') return false;

      if (!qNorm) return true;
      const hay = [
        entry.name,
        entry.subtitle,
        entry.tradition_label,
        entry.hint,
        entry.lore_summary,
        entry.taboo_name,
        entry.primary_element,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return hay.includes(qNorm);
    });
  }, [codexEntries, traditionFilter, stageFilter, qNorm]);

  const filteredFieldLog = useMemo(() => {
    if (!qNorm) return fieldLog;
    return fieldLog.filter((item) => {
      const hay = [item.name, item.public_name, item.location, item.status, item.codex_id]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return hay.includes(qNorm);
    });
  }, [fieldLog, qNorm]);

  const filteredVaultLog = useMemo(() => {
    if (!qNorm) return vaultLog;
    return vaultLog.filter((item) => {
      const hay = [
        item.entity_name,
        item.name,
        item.category_tag,
        item.captured_at,
        item.location,
        item.resolution_method,
        item.resolution_mode,
        item.vault_facility,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return hay.includes(qNorm);
    });
  }, [vaultLog, qNorm]);

  if (!encyclopedia) {
    return (
      <div className="p-4 rounded-lg bg-black/40 border border-fantasy-border/50 text-center text-xs text-gray-400">
        {t('codex.encyclopedia_loading', 'Synchronizing Anomaly & Folklore Archive...')}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Sub-switcher: Folklore Codex vs Field Log & Vault */}
      <div className="flex bg-black/70 p-0.5 rounded-md border border-fantasy-border/60 gap-1">
        <button
          type="button"
          onClick={() => setViewMode('folklore')}
          className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 px-2 rounded text-[11px] font-bold uppercase tracking-wider transition-colors cursor-pointer ${
            viewMode === 'folklore'
              ? 'bg-amber-950/60 text-amber-300 border border-amber-600/50'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          <Scroll size={12} />
          <span>
            {t('codex.folklore_codex', 'Folklore Codex')} [{discoveredCount}/{totalCount}]
          </span>
        </button>

        <button
          type="button"
          onClick={() => setViewMode('field_log')}
          className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 px-2 rounded text-[11px] font-bold uppercase tracking-wider transition-colors cursor-pointer ${
            viewMode === 'field_log'
              ? 'bg-cyan-950/60 text-cyan-300 border border-cyan-600/50'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          <Archive size={12} />
          <span>
            {t('codex.field_log_vault', 'Field Log & Vault')} [{fieldLog.length + vaultLog.length}]
          </span>
        </button>
      </div>

      {viewMode === 'folklore' ? (
        <div className="space-y-2.5">
          {/* Account-Wide Progress Card */}
          <div className="p-2.5 rounded-lg bg-gradient-to-r from-amber-950/30 via-black/60 to-cyan-950/25 border border-amber-700/40 space-y-1.5">
            <div className="flex items-center justify-between text-[11px]">
              <span className="font-bold text-amber-200 uppercase tracking-wider flex items-center gap-1.5">
                <Sparkles size={12} className="text-amber-400" />
                <span>{t('codex.folklore_archive_progress', 'Global Folklore Archive')}</span>
              </span>
              <span className="font-mono text-gray-300">
                <span className="text-amber-300 font-bold">{discoveredCount}</span>/{totalCount} ({pctDiscovered}%)
              </span>
            </div>
            <div className="h-1.5 w-full bg-black/80 rounded-full overflow-hidden border border-amber-900/50">
              <div
                className="h-full bg-gradient-to-r from-amber-500 via-cyan-400 to-emerald-400 transition-all duration-500"
                style={{ width: `${Math.max(discoveredCount > 0 ? 3 : 0, pctDiscovered)}%` }}
              />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 text-[10px] font-mono text-gray-400">
              <span>👁️ {t('codex.sighted', 'Sighted')}: {discoveredCount}</span>
              <span>🛡️ {t('codex.verified', 'Verified')}: {verifiedCount}</span>
              <span>🔒 {t('codex.contained', 'Contained')}: {containedCount}</span>
            </div>
          </div>

          {/* Tradition Filter Pills */}
          <div className="flex flex-wrap gap-1">
            <button
              type="button"
              onClick={() => setTraditionFilter('all')}
              className={`px-2 py-0.5 rounded text-[10px] font-mono border transition-colors cursor-pointer ${
                traditionFilter === 'all'
                  ? 'bg-fantasy-accent/25 text-fantasy-accent border-fantasy-accent/60 font-bold'
                  : 'bg-black/50 text-gray-400 border-neutral-800 hover:text-gray-200'
              }`}
            >
              {t('quests.filter_all', 'All')}
            </button>
            {traditions.map((tr) => (
              <button
                key={tr.key}
                type="button"
                onClick={() => setTraditionFilter(tr.key)}
                className={`px-2 py-0.5 rounded text-[10px] font-mono border transition-colors cursor-pointer ${
                  traditionFilter === tr.key
                    ? 'bg-amber-950/60 text-amber-300 border-amber-600/60 font-bold'
                    : 'bg-black/50 text-gray-400 border-neutral-800 hover:text-gray-200'
                }`}
              >
                {tr.label} ({tr.discovered}/{tr.total})
              </button>
            ))}
          </div>

          {/* Unlock Stage Filter */}
          <div className="flex gap-1 text-[10px] font-mono">
            {[
              { id: 'all', label: t('quests.filter_all', 'All') },
              { id: 'discovered', label: t('codex.discovered', 'Discovered') },
              { id: 'contained', label: t('codex.contained', 'Contained') },
              { id: 'undiscovered', label: t('codex.undiscovered', 'Undiscovered') },
            ].map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => setStageFilter(f.id)}
                className={`flex-1 py-0.5 px-1.5 rounded border transition-colors cursor-pointer ${
                  stageFilter === f.id
                    ? 'bg-cyan-950/60 text-cyan-300 border-cyan-600/60 font-bold'
                    : 'bg-black/40 text-gray-400 border-neutral-800 hover:text-gray-200'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* Codex Entries List */}
          <div className="space-y-2">
            {filteredCodex.length === 0 ? (
              <div className="p-4 rounded-lg bg-black/40 border border-neutral-800 text-center text-xs text-gray-400 italic">
                {t('codex.no_folklore_matches', 'No folklore codex entries match the current filter.')}
              </div>
            ) : (
              filteredCodex.map((entry) => {
                const stage = entry.unlock_stage || 'undiscovered';
                const style = STAGE_STYLES[stage] || STAGE_STYLES.undiscovered;
                const StageIcon = style.icon;
                const isUndiscovered = stage === 'undiscovered';
                const isFullUnlocked = stage === 'verified' || stage === 'contained';
                const isExpanded = !isUndiscovered && expandedId === entry.codex_id;

                if (isUndiscovered) {
                  return (
                    <div
                      key={entry.codex_id}
                      className={`p-2.5 rounded-lg border ${style.card} flex items-center justify-between gap-2`}
                    >
                      <div className="min-w-0 flex-1 space-y-0.5">
                        <div className="flex items-center gap-1.5">
                          <Lock size={11} className="text-gray-500 shrink-0" />
                          <span className="font-mono font-bold text-xs text-gray-400 tracking-widest">???</span>
                          <span className="text-[9.5px] font-mono px-1.5 py-0.2 rounded bg-neutral-900 text-gray-400 border border-neutral-800 truncate">
                            {entry.tradition_label}
                          </span>
                        </div>
                        {entry.hint && (
                          <div className="text-[10.5px] text-gray-500 flex items-center gap-1 truncate">
                            <Compass size={10} className="shrink-0" />
                            <span className="truncate">{entry.hint}</span>
                          </div>
                        )}
                      </div>
                      <span className={`text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border shrink-0 ${style.badge}`}>
                        {t('codex.undiscovered', 'Undiscovered')}
                      </span>
                    </div>
                  );
                }

                return (
                  <div
                    key={entry.codex_id}
                    className={`rounded-lg border transition-all ${style.card}`}
                  >
                    <button
                      type="button"
                      onClick={() => setExpandedId(isExpanded ? null : entry.codex_id)}
                      className="w-full p-2.5 text-left flex items-start justify-between gap-2 cursor-pointer"
                    >
                      <div className="min-w-0 flex-1 space-y-1">
                        <div className="flex items-center flex-wrap gap-1.5">
                          <StageIcon size={12} className="text-amber-300 shrink-0" />
                          <span className="font-rpg font-bold text-xs sm:text-sm text-gray-100">
                            {entry.name}
                          </span>
                          <span className={`text-[9px] font-mono uppercase px-1.5 py-0.2 rounded border font-bold ${style.badge}`}>
                            {t(`codex.${stage}`, formatTag(stage))}
                          </span>
                          {(entry.is_currently_contracted || entry.contracted_ever) && (
                            <span
                              className={`text-[9px] font-mono px-1.5 py-0.2 rounded border font-bold ${
                                entry.is_currently_contracted
                                  ? 'bg-rose-950/85 text-rose-200 border-rose-500/70'
                                  : 'bg-emerald-950/75 text-emerald-200 border-emerald-600/60'
                              }`}
                            >
                              🩸 {entry.is_currently_contracted ? t('contracts.currently_bound', 'Active Pact') : t('contracts.contracted_badge', 'Contracted')}
                            </span>
                          )}
                          {entry.folklore_recognition_active && (
                            <span
                              className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-purple-950/80 text-purple-200 border border-purple-600/60 font-bold"
                              title={t('codex.verification_tooltip', 'Prior verification reduces Stage 1 clue requirement by 1 on future encounters')}
                            >
                              🧠 {t('codex.folklore_recognition', 'Recognition (-1 Clue)')}
                            </span>
                          )}
                        </div>

                        <div className="text-[11px] text-gray-300/90 flex flex-wrap items-center gap-1.5">
                          {entry.subtitle && <span className="italic text-amber-200/90">{entry.subtitle}</span>}
                          <span className="text-gray-500">•</span>
                          <span className="text-[10px] font-mono text-gray-400">{entry.tradition_label}</span>
                          {entry.uniqueness === 'singular' && (
                            <span className="text-[9px] font-mono px-1 rounded bg-rose-950/60 text-rose-300 border border-rose-800/50">
                              {t('codex.singular_legend', 'Singular Legend')}
                            </span>
                          )}
                        </div>

                        {isFullUnlocked && (
                          <div className="flex flex-wrap gap-1 pt-0.5">
                            {entry.has_disguise && (
                              <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-purple-950/60 text-purple-300 border border-purple-800/50">
                                🎭 {t('codex.tag_disguise', 'Disguise')}
                              </span>
                            )}
                            {entry.has_tether && (
                              <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-amber-950/60 text-amber-300 border border-amber-800/50">
                                🏺 {t('codex.tag_vessel_tether', 'Vessel Tether')}
                              </span>
                            )}
                            {entry.has_dialogue_trap && (
                              <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-rose-950/60 text-rose-300 border border-rose-800/50">
                                ❓ {t('codex.tag_riddle_trap', 'Riddle Trap')}
                              </span>
                            )}
                            {entry.has_omen_paradox && (
                              <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-cyan-950/60 text-cyan-300 border border-cyan-800/50">
                                🔊 {t('codex.tag_omen_paradox', 'Omen Paradox')}
                              </span>
                            )}
                            {Array.isArray(entry.appeasement_tags) && entry.appeasement_tags.length > 0 && (
                              <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-800/50">
                                🎁 {t('codex.tag_offerings', 'Offerings')}
                              </span>
                            )}
                          </div>
                        )}
                      </div>

                      <div className="text-gray-400 shrink-0 mt-0.5">
                        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      </div>
                    </button>

                    {isExpanded && (
                      <div className="px-3 pb-3 pt-2 border-t border-white/10 space-y-2.5 text-xs bg-black/40 rounded-b-lg">
                        {/* Appearance & Omen (available from Sighted) */}
                        {entry.appearance && (
                          <div>
                            <div className="text-[10px] font-mono uppercase text-amber-400 font-bold mb-0.5">
                              {t('codex.manifestation_form', 'Manifestation & Form')} ({formatTag(entry.type)} • {entry.form_label || formatTag(entry.form)})
                            </div>
                            <p className="text-gray-200 leading-relaxed text-[11.5px]">{entry.appearance}</p>
                          </div>
                        )}

                        {entry.sensory_omen && (
                          <div className="p-2 rounded bg-amber-950/25 border border-amber-800/40 text-[11px] text-amber-100/90">
                            <span className="font-mono font-bold uppercase text-[10px] text-amber-300 block mb-0.5">
                              {t('codex.sensory_omen', 'Sensory Omen')}
                            </span>
                            {entry.sensory_omen}
                          </div>
                        )}

                        {!isFullUnlocked ? (
                          <div className="p-2 rounded bg-neutral-900/80 border border-neutral-700/60 text-[11px] text-gray-400 flex items-center gap-2">
                            <HelpCircle size={13} className="text-amber-400 shrink-0" />
                            <span>
                              {t('codex.verify_hint', 'Scan in combat, deduce Stage 1 clues, or contain this entity to verify its full folklore classification, elemental chart, and taboo protocol.')}
                            </span>
                          </div>
                        ) : (
                          <>
                            {entry.lore_summary && (
                              <div>
                                <div className="text-[10px] font-mono uppercase text-cyan-300 font-bold mb-0.5">
                                  {t('codex.folklore_archive_dossier', 'Folklore Archive Dossier')}
                                </div>
                                <p className="text-gray-300 leading-relaxed text-[11.5px]">{entry.lore_summary}</p>
                              </div>
                            )}

                            {/* Classification & Elemental Grid */}
                            <div className="grid grid-cols-2 gap-1.5 text-[10.5px] font-mono bg-black/50 p-2 rounded border border-neutral-800">
                              <div>
                                <span className="text-gray-500">{t('codex.behavior_label', 'Behavior')}: </span>
                                <span className="text-gray-200">
                                  {formatTag(entry.disposition)}
                                  {entry.temperament ? ` (${formatTag(entry.temperament)})` : ''}
                                </span>
                              </div>
                              <div>
                                <span className="text-gray-500">{t('codex.mind_body_label', 'Mind / Body')}: </span>
                                <span className="text-gray-200">
                                  {formatTag(entry.sapience)} • {formatTag(entry.physicality)}
                                </span>
                              </div>
                              <div>
                                <span className="text-gray-500">{t('codex.element_label', 'Element')}: </span>
                                <span className="text-amber-300 font-bold uppercase">{entry.primary_element}</span>
                              </div>
                              <div>
                                <span className="text-gray-500">{t('codex.weaknesses_label', 'Weaknesses')}: </span>
                                <span className="text-rose-300 font-bold uppercase">
                                  {(entry.weaknesses || []).join(', ') || t('common.none', 'None')}
                                </span>
                              </div>
                            </div>

                            {/* Taboo & Containment Protocol */}
                            {(entry.taboo_name || entry.containment_protocol) && (
                              <div className="p-2 rounded bg-rose-950/20 border border-rose-800/40 space-y-1 text-[11px]">
                                <div className="font-mono font-bold text-rose-300 flex items-center gap-1 uppercase text-[10px]">
                                  <AlertTriangle size={11} />
                                  <span>{t('codex.taboo_label', 'Taboo')}: {entry.taboo_name || t('codex.classified_rule', 'Classified Rule')}</span>
                                </div>
                                {entry.taboo_rule && <p className="text-rose-100/90">{entry.taboo_rule}</p>}
                                {entry.containment_protocol && (
                                  <p className="text-emerald-200/95 pt-1 border-t border-rose-900/40">
                                    <span className="font-mono font-bold text-emerald-300 uppercase text-[10px]">
                                      {t('codex.protocol_label', 'Protocol')}:{' '}
                                    </span>
                                    {entry.containment_protocol}
                                  </p>
                                )}
                              </div>
                            )}

                            {/* Special Folklore Mechanics Details */}
                            {entry.tether_vessel && (
                              <div className="text-[11px] text-amber-200 bg-amber-950/25 px-2 py-1.5 rounded border border-amber-800/40">
                                <span className="font-mono font-bold uppercase text-[10px] text-amber-300">
                                  🏺 {t('codex.bound_vessel', 'Bound Vessel')}:{' '}
                                </span>
                                {entry.tether_vessel}
                              </div>
                            )}

                            {entry.omen_paradox_rule && (
                              <div className="text-[11px] text-cyan-200 bg-cyan-950/25 px-2 py-1.5 rounded border border-cyan-800/40">
                                <span className="font-mono font-bold uppercase text-[10px] text-cyan-300">
                                  🔊 {t('codex.paradoxical_omen', 'Paradoxical Omen')}:{' '}
                                </span>
                                {entry.omen_paradox_rule}
                              </div>
                            )}

                            {Array.isArray(entry.appeasement_tags) && entry.appeasement_tags.length > 0 && (
                              <div className="flex flex-wrap items-center gap-1 text-[10px] font-mono">
                                <span className="text-emerald-400 font-bold">🎁 {t('codex.offerings_wards', 'Offerings / Wards')}:</span>
                                {entry.appeasement_tags.map((tag) => (
                                  <span
                                    key={tag}
                                    className="px-1.5 py-0.2 rounded bg-emerald-950/60 text-emerald-200 border border-emerald-700/50"
                                  >
                                    {formatTag(tag)}
                                  </span>
                                ))}
                              </div>
                            )}

                            {entry.relic_gear_name && (
                              <div className="text-[10.5px] font-mono text-purple-200 bg-purple-950/30 px-2 py-1 rounded border border-purple-700/40">
                                ⚔️ {t('codex.relic_conversion', 'Canonical Relic Conversion')}: <span className="font-bold">{entry.relic_gear_name}</span>
                              </div>
                            )}
                          </>
                        )}

                        <div className="flex items-center justify-between text-[10px] font-mono text-gray-500 pt-1 border-t border-neutral-800">
                          <span>{t('codex.sightings_count', 'Sightings')}: {entry.sightings_count || 1}</span>
                          <span>{t('codex.contained', 'Contained')}: {entry.contained_count || 0}</span>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      ) : (
        /* Field Log & Containment Vault View */
        <div className="space-y-3">
          {/* Containment Vault Captures */}
          <div className="space-y-1.5">
            <div className="text-[11px] font-mono uppercase tracking-wider text-emerald-300 font-bold flex items-center justify-between">
              <span>🔒 {t('codex.vault_captures_title', 'Containment Vault Captures')}</span>
              <span>{filteredVaultLog.length}</span>
            </div>
            {filteredVaultLog.length === 0 ? (
              <div className="p-3 rounded-lg bg-black/40 border border-neutral-800 text-xs text-gray-400 italic">
                {t('codex.vault_captures_empty', 'No anomalies sealed into the Containment Vault in this campaign yet.')}
              </div>
            ) : (
              filteredVaultLog.map((v, i) => (
                <div
                  key={`${v.incursion_id || v.entity_name || i}-${i}`}
                  className="p-2.5 rounded-lg bg-emerald-950/15 border border-emerald-700/45 space-y-1 text-xs"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-bold text-emerald-200">{v.entity_name || v.name || t('codex.sealed_anomaly', 'Sealed Anomaly')}</span>
                    <span className="text-[9.5px] font-mono uppercase px-1.5 py-0.2 rounded bg-emerald-950/80 text-emerald-300 border border-emerald-600/50 truncate max-w-[55%]">
                      {formatTag(v.resolution_method || v.resolution_mode || 'Vaulted')}
                    </span>
                  </div>
                  {(v.captured_at || v.location) && (
                    <div className="text-[10.5px] text-gray-400 font-mono truncate">
                      📍 {formatCleanLocation(v.captured_at || v.location)}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>

          {vaultReqs.length > 0 && (
            <div className="space-y-1.5">
              <div className="text-[11px] font-mono uppercase tracking-wider text-purple-300 font-bold">
                ⚔️ {t('codex.vault_requisitions_title', 'Active Vault Relic Requisitions')} ({vaultReqs.length})
              </div>
              {vaultReqs.map((req, idx) => (
                <div
                  key={idx}
                  className="p-2 rounded bg-purple-950/20 border border-purple-700/40 text-[11px] text-purple-200 flex items-center justify-between"
                >
                  <span className="font-bold">{req.item_name || req.name || t('codex.anomalous_relic', 'Anomalous Relic')}</span>
                  <span className="font-mono text-[10px] text-purple-300">
                    {req.source_entity || req.metadata?.source_anomaly || req.slot || 'Vault'}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Session Field Sightings Log */}
          <div className="space-y-1.5">
            <div className="text-[11px] font-mono uppercase tracking-wider text-amber-300 font-bold flex items-center justify-between">
              <span>📓 {t('codex.field_sightings_title', 'Session Field Sightings')}</span>
              <span>{filteredFieldLog.length}</span>
            </div>
            {filteredFieldLog.length === 0 ? (
              <div className="p-3 rounded-lg bg-black/40 border border-neutral-800 text-xs text-gray-400 italic">
                {t('codex.field_sightings_empty', 'No field anomaly sightings logged in this session yet.')}
              </div>
            ) : (
              filteredFieldLog.map((log, idx) => (
                <div
                  key={`${log.blueprint_id || log.name || idx}-${idx}`}
                  className="p-2.5 rounded-lg bg-black/50 border border-neutral-800 space-y-1 text-xs"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="font-bold text-gray-100 truncate">
                        {log.is_disguised ? (log.public_name || t('scene.uncanny_stranger', 'Uncanny Stranger')) : (log.name || t('codex.unknown_anomaly', 'Unknown Anomaly'))}
                      </span>
                      {log.codex_id && !log.is_disguised && (
                        <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-amber-950/70 text-amber-300 border border-amber-700/50 shrink-0">
                          {t('codex.folklore_badge', 'Folklore')}
                        </span>
                      )}
                    </div>
                    <span className="text-[9.5px] font-mono uppercase px-1.5 py-0.2 rounded bg-neutral-900 text-gray-300 border border-neutral-700 shrink-0">
                      {formatTag(log.status || 'sighted')}
                    </span>
                  </div>
                  {log.location && (
                    <div className="text-[10.5px] text-gray-400 font-mono truncate">
                      📍 {formatCleanLocation(log.location)}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default EncyclopediaSubTab;
