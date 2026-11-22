import React from 'react';
import { MapPin, Search, Sparkles, User, Zap } from 'lucide-react';
import { cleanProseLocations, formatCleanLocation } from '../../../utils/locationFormat';

const CATEGORY_META = {
  physical: { icon: '🔍', label: 'Physical', color: 'text-amber-300 bg-amber-950/50 border-amber-700/50' },
  testimonial: { icon: '🗣️', label: 'Testimonial', color: 'text-cyan-300 bg-cyan-950/50 border-cyan-700/50' },
  digital: { icon: '💾', label: 'Digital', color: 'text-purple-300 bg-purple-950/50 border-purple-700/50' },
  document: { icon: '📄', label: 'Document', color: 'text-blue-300 bg-blue-950/50 border-blue-700/50' },
  deduction: { icon: '⚡', label: 'Breakthrough', color: 'text-emerald-300 bg-emerald-950/60 border-emerald-600/60' },
};

const CaseboardTab = ({
  clues = [],
  suspects = [],
  selectedSuspect,
  onSelectSuspect,
  clueAId,
  setClueAId,
  clueBId,
  setClueBId,
  onSynthesizeDeduction,
  onAccuseSuspect,
  busyAction,
  t,
}) => {
  const unconsumedEvidence = clues.filter((c) => c && !c.is_consumed && c.category !== 'deduction');
  const canDeduceSingle = unconsumedEvidence.length >= 1;
  const canPairTwo = unconsumedEvidence.length >= 2;
  const filteredClues = clues.filter((c) => {
    if (selectedSuspect === '__all__') return true;
    return (c.linked_npc || '').trim().toLowerCase() === selectedSuspect.toLowerCase();
  });

  return (
    <div className="space-y-3">
      {/* Deduction Synthesizer */}
      {canDeduceSingle && (
        <div className="bg-purple-950/15 border border-purple-700/45 rounded-xl p-3 space-y-2.5">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-bold text-purple-300 uppercase tracking-wider flex items-center gap-1.5">
              <Zap size={13} className="text-amber-400 shrink-0" />
              <span>{t('quests.deduction_synthesizer', 'Deduction Synthesizer (+50 XP)')}</span>
            </span>
            <span className="text-[10.5px] font-mono text-gray-400 shrink-0">
              {canPairTwo ? t('quests.pair_leads', 'Pair 2 Leads') : t('quests.single_lead', 'Single Lead')}
            </span>
          </div>

          <div className="grid grid-cols-1 gap-1.5">
            <select
              value={clueAId}
              onChange={(e) => setClueAId(e.target.value)}
              className="w-full bg-black/70 border border-fantasy-border rounded-lg px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-purple-500"
            >
              <option value="">{t('quests.select_evidence_a', 'Select Primary Evidence A...')}</option>
              {unconsumedEvidence
                .filter((c) => !clueBId || String(c.id) !== String(clueBId))
                .map((c, idx) => (
                  <option key={c.id || idx} value={c.id}>
                    {c.title || (c.lead_text || c.clue_text || '').slice(0, 50)}
                  </option>
                ))}
            </select>

            {canPairTwo && (
              <select
                value={clueBId}
                onChange={(e) => setClueBId(e.target.value)}
                className="w-full bg-black/70 border border-fantasy-border rounded-lg px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-purple-500"
              >
                <option value="">{t('quests.select_evidence_b', 'Select Corroborating Evidence B...')}</option>
                {unconsumedEvidence
                  .filter((c) => !clueAId || String(c.id) !== String(clueAId))
                  .map((c, idx) => (
                    <option key={c.id || idx} value={c.id}>
                      {c.title || (c.lead_text || c.clue_text || '').slice(0, 50)}
                    </option>
                  ))}
              </select>
            )}
          </div>

          {clueAId && (
            <div className="text-[11px] text-purple-200 border-l-2 border-purple-400 bg-purple-950/30 rounded-r px-2.5 py-1.5 leading-snug">
              {clueBId
                ? `🧩 ${t('quests.logic_caseboard_hint', 'Deterministic Logic Caseboard — Corroborating pairs unlock Climax / Twist')}`
                : `🔮 ${t('quests.single_clue_hint', 'Single-Clue Folklore Recognition — Verified Codex knowledge can identify entities immediately')}`}
            </div>
          )}

          <button
            type="button"
            disabled={!clueAId || Boolean(busyAction)}
            onClick={onSynthesizeDeduction}
            className={`w-full py-1.5 px-3 rounded-lg text-xs font-bold flex items-center justify-center gap-1.5 border transition-all ${
              clueAId
                ? 'bg-purple-600/30 hover:bg-purple-600/45 text-purple-200 border-purple-500/60'
                : 'bg-black/40 text-gray-500 border-neutral-800 cursor-not-allowed'
            }`}
          >
            <Sparkles size={12} />
            <span>
              {busyAction === 'deduce'
                ? t('quests.cross_referencing', 'Cross-Referencing...')
                : clueBId
                  ? t('quests.synthesize_breakthrough', '🧩 Synthesize Breakthrough')
                  : t('quests.deduce_single_clue', '🔮 Deduce with Single Clue')}
            </span>
          </button>
        </div>
      )}

      {/* Flat Suspect Filter Strip */}
      {suspects.length > 0 && (
        <div className="space-y-2 pb-2.5 border-b border-white/[0.08]">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[10.5px] font-bold uppercase tracking-wider text-gray-400">
              {t('quests.filter_suspect', 'Filter Suspect:')}
            </span>
            <select
              value={selectedSuspect}
              onChange={(e) => onSelectSuspect(e.target.value)}
              className="bg-black/60 border border-fantasy-border rounded-lg px-2 py-1 text-xs text-gray-200 focus:outline-none"
            >
              <option value="__all__">All Evidence ({clues.length})</option>
              {suspects.map((s) => (
                <option key={s} value={s}>
                  👤 {s}
                </option>
              ))}
            </select>
          </div>
          {selectedSuspect !== '__all__' && (
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                disabled={Boolean(busyAction)}
                onClick={() => onAccuseSuspect('private')}
                className="flex-1 py-1.5 px-2 rounded-lg bg-cyan-950/50 hover:bg-cyan-900/60 text-cyan-200 border border-cyan-700/50 text-[11px] font-bold transition-colors"
              >
                🗣️ {t('quests.confront_privately', 'Confront Privately')}
              </button>
              <button
                type="button"
                disabled={Boolean(busyAction)}
                onClick={() => onAccuseSuspect('formal')}
                className="flex-1 py-1.5 px-2 rounded-lg bg-red-950/60 hover:bg-red-900/70 text-red-200 border border-red-700/60 text-[11px] font-bold transition-colors"
              >
                ⚖️ {t('quests.accuse_publicly', 'Accuse Publicly')}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Evidence Cards */}
      {filteredClues.length === 0 ? (
        <div className="text-center py-8 px-4 text-gray-400 border border-dashed border-fantasy-border/50 rounded-xl space-y-1.5">
          <Search size={24} className="mx-auto opacity-50 text-cyan-400" />
          <p className="text-xs text-gray-300">{t('quests.no_leads', 'No investigation leads recorded yet.')}</p>
          <p className="text-[11px] text-gray-400">
            {t('quests.gather_evidence_desc', 'Inspect scenes, question witnesses, or scour NetWire rumors to gather evidence.')}
          </p>
        </div>
      ) : (
        <div className="space-y-2.5">
          {filteredClues.map((c, idx) => {
            const isObj = typeof c === 'object' && c !== null;
            const catKey = isObj ? c.category || 'physical' : 'physical';
            const cat = CATEGORY_META[catKey] || CATEGORY_META.physical;
            const title = isObj ? c.title || 'Evidence Lead' : 'Discovered Clue';
            const body = isObj ? c.lead_text || c.clue_text || c.text : String(c);
            const isVerified = isObj && Boolean(c.is_verified);

            return (
              <div
                key={(isObj && c.id) || idx}
                className={`p-3 rounded-xl border space-y-2 transition-all ${
                  isVerified
                    ? 'bg-emerald-950/20 border-emerald-700/50'
                    : 'bg-black/30 border-fantasy-border/55'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className={`text-[9.5px] px-1.5 py-0.5 rounded border font-bold uppercase ${cat.color}`}>
                      {cat.icon} {t(`quests.clue_types.${catKey}`, cat.label)}
                    </span>
                    {isObj && c.clue_tier === 'key_clue' && (
                      <span className="text-[9.5px] px-1.5 py-0.5 rounded bg-amber-950/70 text-amber-300 border border-amber-600/50 font-bold uppercase">
                        🔑 {t('quests.clue_tier_key', 'Key Clue')}
                      </span>
                    )}
                    {isObj && c.clue_tier === 'corroborating' && c.category !== 'deduction' && (
                      <span className="text-[9.5px] px-1.5 py-0.5 rounded bg-cyan-950/70 text-cyan-300 border border-cyan-600/50 font-bold uppercase">
                        🧩 {t('quests.clue_tier_corroborating', 'Corroborating')}
                      </span>
                    )}
                    {isVerified && (
                      <span className="text-[9.5px] px-1.5 py-0.5 rounded bg-emerald-950/80 text-emerald-300 border border-emerald-600/50 font-bold uppercase">
                        ✓ {t('quests.verified_badge', 'Verified')}
                      </span>
                    )}
                  </div>

                  {isObj && c.id && !c.is_consumed && c.category !== 'deduction' && canDeduceSingle && (
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        type="button"
                        onClick={() => {
                          const cid = String(c.id);
                          if (String(clueAId) === cid) {
                            setClueAId('');
                          } else {
                            setClueAId(cid);
                            if (String(clueBId) === cid) setClueBId('');
                          }
                        }}
                        className={`text-[10px] px-1.5 py-0.5 rounded font-mono border ${
                          String(clueAId) === String(c.id)
                            ? 'bg-purple-600 text-white border-purple-400'
                            : 'bg-black/60 text-gray-300 border-fantasy-border hover:text-white'
                        }`}
                      >
                        {t('quests.lead_a', 'Lead A')}
                      </button>
                      {canPairTwo && (
                        <button
                          type="button"
                          onClick={() => {
                            const cid = String(c.id);
                            if (String(clueBId) === cid) {
                              setClueBId('');
                            } else {
                              setClueBId(cid);
                              if (String(clueAId) === cid) setClueAId('');
                            }
                          }}
                          className={`text-[10px] px-1.5 py-0.5 rounded font-mono border ${
                            String(clueBId) === String(c.id)
                              ? 'bg-purple-600 text-white border-purple-400'
                              : 'bg-black/60 text-gray-300 border-fantasy-border hover:text-white'
                          }`}
                        >
                          {t('quests.lead_b', 'Lead B')}
                        </button>
                      )}
                    </div>
                  )}
                </div>

                <h5 className="font-bold text-[13px] text-gray-100 leading-snug">{cleanProseLocations(title)}</h5>
                <p className="text-[12px] text-gray-200 leading-[1.45] hk-quest-prose">{cleanProseLocations(body)}</p>

                {isObj && (c.linked_npc || c.source_location) && (
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-1.5 text-[11px] text-gray-400 border-t border-white/[0.06]">
                    {c.linked_npc && (
                      <span className="inline-flex items-center gap-1 text-amber-300">
                        <User size={11} className="shrink-0" />
                        <span>
                          {String(t('quests.suspect', 'Suspect:')).replace(/^👤\s*/, '')}{' '}
                          <strong>{c.linked_npc}</strong>
                        </span>
                      </span>
                    )}
                    {c.source_location && (
                      <span className="inline-flex items-center gap-1 text-gray-300 break-words">
                        <MapPin size={11} className="text-amber-400 shrink-0" />
                        <span>{formatCleanLocation(c.source_location)}</span>
                      </span>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default CaseboardTab;
