import { useState, useEffect, useId, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Sparkles, Heart, Zap, Package, RotateCcw } from 'lucide-react';
import { AcrylicModal, MotionButton } from '../Common/MotionPrimitives';
import {
  STATURE_OPTIONS,
  getAllowedPhysiqueOptions,
  healPhysiqueForSelection,
  rollClientBuild,
} from '../../utils/anatomyOptions';

const STAT_KEYS = [
  { key: 'str', code: 'STR', label: 'Strength', emoji: '💪' },
  { key: 'per', code: 'PER', label: 'Perception', emoji: '👁️' },
  { key: 'end', code: 'END', label: 'Endurance', emoji: '🛡️' },
  { key: 'cha', code: 'CHA', label: 'Charisma', emoji: '🗣️' },
  { key: 'int', code: 'INT', label: 'Intelligence', emoji: '🧠' },
  { key: 'agi', code: 'AGI', label: 'Agility', emoji: '🏹' },
  { key: 'luk', code: 'LUK', label: 'Luck', emoji: '🍀' },
];

const GENDER_OPTIONS = [
  { value: 'Male', labelKey: 'creator.gender_male', fallback: 'Male' },
  { value: 'Female', labelKey: 'creator.gender_female', fallback: 'Female' },
];

const RACE_OPTIONS = [
  { value: 'Human', labelKey: 'creator.race_human', fallback: 'Human' },
  { value: 'Elf', labelKey: 'creator.race_elf', fallback: 'Elf' },
  { value: 'Dwarf', labelKey: 'creator.race_dwarf', fallback: 'Dwarf' },
  { value: 'Beastfolk / Anthro', labelKey: 'creator.race_beastfolk', fallback: 'Beastfolk / Anthro' },
  { value: 'Cyborg', labelKey: 'creator.race_cyborg', fallback: 'Cyborg' },
];

const DEFAULT_STATS = { str: 1, per: 1, end: 1, cha: 1, int: 1, agi: 1, luk: 1 };

const CharacterCreatorModal = ({ isOpen, onClose, onCreateCharacter }) => {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const [name, setName] = useState('');
  const [gender, setGender] = useState('Male');
  const [customGender, setCustomGender] = useState('');
  const [race, setRace] = useState('Human');
  const [customRace, setCustomRace] = useState('');
  const [raceDescription, setRaceDescription] = useState('');
  const [stature, setStature] = useState('');
  const [physique, setPhysique] = useState('');

  const { t } = useTranslation();
  const creatorResId = useId();
  const [previewMediumSynergy, setPreviewMediumSynergy] = useState('');

  const [stats, setStats] = useState({ ...DEFAULT_STATS });
  const [focusedStat, setFocusedStat] = useState('STR');

  const resetForm = useCallback(() => {
    setSubmitting(false);
    setError(null);
    setName('');
    setGender('Male');
    setCustomGender('');
    setRace('Human');
    setCustomRace('');
    setRaceDescription('');
    setStature('');
    setPhysique('');
    setPreviewMediumSynergy('');
    setStats({ ...DEFAULT_STATS });
    setFocusedStat('STR');
  }, []);

  useEffect(() => {
    if (!isOpen) {
      resetForm();
    }
  }, [isOpen, resetForm]);

  const maxTotalPoints = 12;
  const totalAllocated = Object.values(stats).reduce((acc, v) => acc + Number(v || 1), 0);
  const pointsRemaining = maxTotalPoints - totalAllocated;

  const derivedHp = 200 + stats.end * 100;
  const derivedMp = 50 + stats.end * 25;
  const derivedCap = 30 + stats.str * 3;

  const effectiveGender = gender === '__custom__' ? customGender.trim() || 'Non-binary' : gender;
  const effectiveRace = race === '__custom__' ? customRace.trim() || 'Human' : race;
  const allowedPhysiques = getAllowedPhysiqueOptions(effectiveGender, stature, effectiveRace);

  useEffect(() => {
    if (!physique) return;
    const healed = healPhysiqueForSelection(physique, effectiveGender, stature, effectiveRace);
    if (healed !== physique) {
      setPhysique(healed);
    }
  }, [physique, effectiveGender, stature, effectiveRace]);

  const handleResetStats = () => setStats({ ...DEFAULT_STATS });

  const adjustStat = (key, delta) => {
    setStats((prev) => {
      const curr = prev[key] ?? 1;
      const next = curr + delta;
      if (next < 1 || next > 10) return prev;
      if (delta > 0 && pointsRemaining <= 0) return prev;
      return { ...prev, [key]: next };
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!name.trim()) {
      setError(t('creator.err_name_required', 'Please enter a character name.'));
      return;
    }
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await onCreateCharacter({
        name: name.trim(),
        gender: effectiveGender,
        race: effectiveRace,
        race_description: raceDescription.trim(),
        ...(stature ? { stature } : {}),
        ...(physique ? { physique } : {}),
        str: stats.str,
        per: stats.per,
        end: stats.end,
        cha: stats.cha,
        int: stats.int,
        agi: stats.agi,
        luk: stats.luk,
      });

      resetForm();
      onClose();
    } catch (err) {
      setError(err.message || t('creator.err_create_failed', 'Character creation failed'));
    } finally {
      setSubmitting(false);
    }
  };

  const statEffects = {
    STR: t('creator.stat_effects.STR', 'Strength determines physical power, carry capacity, and melee damage.'),
    PER: t('creator.stat_effects.PER', 'Perception affects accuracy, observation skills, and detecting hidden objects.'),
    END: t('creator.stat_effects.END', 'Endurance governs health points (HP), stamina, and resistance to damage/poison.'),
    CHA: t('creator.stat_effects.CHA', 'Charisma improves social interactions, persuasion, and trading prices.'),
    INT: t('creator.stat_effects.INT', 'Intelligence affects magical ability, hacking, learning speed, and skill points.'),
    AGI: t('creator.stat_effects.AGI', 'Agility improves evasion, stealth, initiative in combat, and movement speed.'),
    LUK: t('creator.stat_effects.LUK', 'Luck influences critical hit chance, finding rare loot, and random encounters.'),
  };

  return (
    <AcrylicModal
      isOpen={isOpen}
      onClose={onClose}
      label={t('creator.title', 'Character Creation Studio')}
      maxWidthClass="max-w-4xl"
      zIndexClass="z-[60]"
    >
        {/* Header */}
        <div className="px-4 py-3.5 border-b border-fantasy-border/35 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="p-2 rounded-xl bg-fantasy-accent/15 border border-fantasy-accent/40 text-fantasy-accent shrink-0">
              <Sparkles size={18} />
            </div>
            <div className="min-w-0">
              <h2 className="font-rpg font-bold text-lg text-fantasy-accent truncate">
                {t('creator.title', 'Character Creation Studio')}
              </h2>
              <p className="text-xs text-gray-400 truncate">
                {t('creator.subtitle', "Define your hero's basic identity and allocate S.P.E.C.I.A.L. stats.")}
              </p>
            </div>
          </div>

          <MotionButton onClick={onClose} aria-label={t('common.close', 'Close')} className="hk-icon-btn h-8 min-w-8 shrink-0">
            <X size={18} />
          </MotionButton>
        </div>

        {error && (
          <div className="mx-5 mt-3 p-2.5 rounded-xl bg-red-500/15 border border-red-500/40 text-red-200 text-xs flex items-center justify-between shrink-0">
            <span>{error}</span>
            <button type="button" onClick={() => setError(null)} className="text-gray-400 hover:text-white">
              <X size={13} />
            </button>
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex-1 min-h-0 overflow-y-auto overscroll-contain custom-scrollbar px-5 py-3">
          <section className="hk-flat-section space-y-4">
            <div className="flex items-center justify-between border-b border-fantasy-border/35 pb-2.5">
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded bg-fantasy-accent/20 border border-fantasy-accent/50 text-fantasy-accent text-[10px] font-bold uppercase tracking-wider">
                  {t('creator.section_1', 'Section 1')}
                </span>
                <h3 className="text-xs uppercase tracking-wider font-bold text-gray-100">
                  {t('creator.identity_heading', 'Basic Character Identity & S.P.E.C.I.A.L. Allocation')}
                </h3>
              </div>
              <span className="text-[11px] text-gray-400 hidden sm:inline">
                {t('creator.persist_hint', 'Core identity & attributes persist across scenarios')}
              </span>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
              {/* Left Side: Name, Gender, Race */}
              <div className="lg:col-span-5 flex flex-col justify-between space-y-4">
                <div className="space-y-3.5">
                  <div>
                    <label className="block text-[11px] uppercase tracking-wider font-bold text-gray-400 mb-1">
                      {t('creator.hero_name', 'Hero Name')}
                    </label>
                    <input
                      type="text"
                      placeholder={t('creator.name_placeholder', 'e.g. Alistair, Lyra, Kael...')}
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      maxLength={40}
                      className="w-full bg-fantasy-dark border border-fantasy-border p-2.5 rounded text-sm text-gray-100 focus:outline-none focus:border-fantasy-accent"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[11px] uppercase tracking-wider font-bold text-gray-400 mb-1">
                        {t('creator.gender', 'Gender')}
                      </label>
                      <select
                        value={gender}
                        onChange={(e) => setGender(e.target.value)}
                        className="w-full bg-fantasy-dark border border-fantasy-border p-2 rounded text-sm text-gray-100 focus:outline-none focus:border-fantasy-accent"
                      >
                        {GENDER_OPTIONS.map((g) => (
                          <option key={g.value} value={g.value}>
                            {t(g.labelKey, g.fallback)}
                          </option>
                        ))}
                        <option value="__custom__">{t('creator.custom_option', 'Custom...')}</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-[11px] uppercase tracking-wider font-bold text-gray-400 mb-1">
                        {t('creator.race_label', 'Race / Species')}
                      </label>
                      <select
                        value={race}
                        onChange={(e) => setRace(e.target.value)}
                        className="w-full bg-fantasy-dark border border-fantasy-border p-2 rounded text-sm text-gray-100 focus:outline-none focus:border-fantasy-accent"
                      >
                        {RACE_OPTIONS.map((r) => (
                          <option key={r.value} value={r.value}>
                            {t(r.labelKey, r.fallback)}
                          </option>
                        ))}
                        <option value="__custom__">{t('creator.custom_race_option', 'Custom Race...')}</option>
                      </select>
                    </div>
                  </div>

                  {(gender === '__custom__' || race === '__custom__') && (
                    <div className="space-y-2 pt-2 border-t border-fantasy-border/40">
                      {gender === '__custom__' && (
                        <input
                          type="text"
                          placeholder={t('creator.custom_gender_placeholder', 'Custom gender identity...')}
                          value={customGender}
                          onChange={(e) => setCustomGender(e.target.value)}
                          className="w-full bg-fantasy-dark border border-fantasy-border p-2 rounded text-xs text-gray-100"
                        />
                      )}
                      {race === '__custom__' && (
                        <div className="grid grid-cols-1 gap-2">
                          <input
                            type="text"
                            placeholder={t('creator.custom_race_placeholder', 'Custom race/species name...')}
                            value={customRace}
                            onChange={(e) => setCustomRace(e.target.value)}
                            className="w-full bg-fantasy-dark border border-fantasy-border p-2 rounded text-xs text-gray-100"
                          />
                          <input
                            type="text"
                            placeholder={t('creator.custom_traits_placeholder', 'Optional physical/species traits...')}
                            value={raceDescription}
                            onChange={(e) => setRaceDescription(e.target.value)}
                            className="w-full bg-fantasy-dark border border-fantasy-border p-2 rounded text-xs text-gray-100"
                          />
                        </div>
                      )}
                    </div>
                  )}

                  {/* Optional Height & Physique Build Controls */}
                  <div className="pt-2 border-t border-fantasy-border/40 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] uppercase tracking-wider font-bold text-gray-400">
                        📐 {t('build.build_label', 'Physical Build')}
                      </span>
                      <button
                        type="button"
                        onClick={() => {
                          const rolled = rollClientBuild(effectiveRace, effectiveGender);
                          setStature(rolled.stature);
                          setPhysique(rolled.physique);
                        }}
                        className="text-[11px] text-fantasy-accent hover:text-amber-300 font-semibold transition-colors"
                      >
                        🎲 {t('build.roll_build', 'Roll Build')}
                      </button>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-[10px] uppercase tracking-wider font-semibold text-gray-400 mb-1">
                          {t('build.height_label', 'Height')}
                        </label>
                        <select
                          value={stature}
                          onChange={(e) => {
                            const nextStature = e.target.value;
                            setStature(nextStature);
                            if (physique) {
                              setPhysique(healPhysiqueForSelection(physique, effectiveGender, nextStature, effectiveRace));
                            }
                          }}
                          className="w-full bg-fantasy-dark border border-fantasy-border p-2 rounded text-xs text-gray-100 focus:outline-none focus:border-fantasy-accent"
                        >
                          <option value="">{t('build.auto_roll', 'Auto-Roll')}</option>
                          {STATURE_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {t(opt.i18nKey, opt.fallback)}{opt.rangeHint ? ` ${opt.rangeHint}` : ''}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-[10px] uppercase tracking-wider font-semibold text-gray-400 mb-1">
                          {t('build.physique_label', 'Physique')}
                        </label>
                        <select
                          value={physique}
                          onChange={(e) => setPhysique(e.target.value)}
                          className="w-full bg-fantasy-dark border border-fantasy-border p-2 rounded text-xs text-gray-100 focus:outline-none focus:border-fantasy-accent"
                        >
                          <option value="">{t('build.auto_roll', 'Auto-Roll')}</option>
                          {allowedPhysiques.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {t(opt.i18nKey, opt.fallback)}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Live Derived Vitals Preview */}
                <div className="space-y-1.5">
                  <span className="block text-[10px] uppercase tracking-wider font-bold text-gray-400">
                    {t('creator.derived_vitals', 'Derived Starting Vitals')}
                  </span>
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div className="bg-gray-500/10 border border-red-500/30 rounded-xl p-2">
                      <div className="text-[10px] uppercase text-gray-400 flex items-center justify-center gap-1">
                        <Heart size={11} className="text-red-400" /> {t('creator.max_hp', 'Max HP')}
                      </div>
                      <div className="text-sm font-bold font-mono tabular-nums text-red-300 mt-0.5">{derivedHp}</div>
                    </div>
                    <div className="bg-gray-500/10 border border-blue-500/30 rounded-xl p-2">
                      <div className="text-[10px] uppercase text-gray-400 flex items-center justify-center gap-1">
                        <Zap size={11} className="text-blue-400" /> {t('creator.max_mp', 'Max MP')}
                      </div>
                      <div className="text-sm font-bold font-mono tabular-nums text-blue-300 mt-0.5">{derivedMp}</div>
                    </div>
                    <div className="bg-gray-500/10 border border-amber-500/30 rounded-xl p-2">
                      <div className="text-[10px] uppercase text-gray-400 flex items-center justify-center gap-1">
                        <Package size={11} className="text-amber-400" /> {t('creator.pack_slots', 'Pack Slots')}
                      </div>
                      <div className="text-sm font-bold font-mono tabular-nums text-amber-300 mt-0.5">{derivedCap}</div>
                    </div>
                  </div>
                </div>

                <p className="pt-2 border-t border-fantasy-border/35 text-[10px] text-gray-400 leading-relaxed">
                  {t('creator.anatomy_deferred_hint', '🔞 Intimate anatomy is configured when you embark on an NSFW scenario, then remembered for future NSFW adventures.')}
                </p>
              </div>

              {/* Right Side: S.P.E.C.I.A.L. Point-Buy */}
              <div className="lg:col-span-7 lg:border-l lg:border-fantasy-border/35 lg:pl-5 flex flex-col justify-between space-y-3">
                <div>
                  <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                    <div>
                      <h4 className="text-xs uppercase tracking-wider font-bold text-fantasy-accent">
                        {t('creator.point_buy_title', 'S.P.E.C.I.A.L. Point-Buy')}
                      </h4>
                      <p className="text-[11px] text-gray-400">
                        {t('creator.point_buy_sub', {
                          max: maxTotalPoints,
                          defaultValue: `Base 1 per stat • 5 bonus points (${maxTotalPoints} total)`,
                        })}
                      </p>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={handleResetStats}
                        className="py-1 px-2 rounded bg-black/50 hover:bg-black/80 border border-fantasy-border text-gray-300 text-xs flex items-center gap-1 transition-colors"
                      >
                        <RotateCcw size={12} />
                        <span>{t('creator.reset', 'Reset')}</span>
                      </button>
                      <span
                        className={`px-2.5 py-1 rounded text-xs font-mono tabular-nums font-bold border ${
                          pointsRemaining > 0
                            ? 'bg-amber-500/20 border-amber-500/50 text-amber-300'
                            : 'bg-emerald-950/60 border-emerald-700/50 text-emerald-300'
                        }`}
                      >
                        {t('creator.pts_left', { count: pointsRemaining, defaultValue: `${pointsRemaining} pts left` })}
                      </span>
                    </div>
                  </div>

                  <div className="mb-2.5 flex items-center justify-between gap-2 bg-cyan-950/15 border border-cyan-900/40 rounded px-2.5 py-1.5">
                    <label htmlFor={`${creatorResId}-med-syn`} className="text-[10px] font-bold uppercase tracking-wider text-cyan-300">
                      🧬 {t('creator.medium_synergy_preview', 'Medium Synergy Preview')}:
                    </label>
                    <select
                      id={`${creatorResId}-med-syn`}
                      value={previewMediumSynergy}
                      onChange={(e) => setPreviewMediumSynergy(e.target.value)}
                      className="bg-fantasy-dark border border-cyan-800/50 rounded px-2 py-0.5 text-[11px] text-gray-200"
                    >
                      <option value="">{t('creator.all_realms', 'All Realms (No Filter)')}</option>
                      <option value="direct_manifestation">{t('awakened.mediums.direct_manifestation', 'Direct Manifestation (INT / CHA)')}</option>
                      <option value="ordnance_imbuement">{t('awakened.mediums.ordnance_imbuement', 'Ordnance Imbuement (PER / STR / AGI)')}</option>
                      <option value="somatic_overdrive">{t('awakened.mediums.somatic_overdrive', 'Somatic Overdrive (STR / AGI / END)')}</option>
                      <option value="autonomous_construct">{t('awakened.mediums.autonomous_construct', 'Autonomous Construct (INT / PER + END HP)')}</option>
                    </select>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                    {STAT_KEYS.map((s) => {
                      const val = stats[s.key] ?? 1;
                      const isFocused = focusedStat === s.code;
                      const synLookup = {
                        direct_manifestation: ['INT', 'CHA'],
                        ordnance_imbuement: ['PER', 'STR', 'AGI'],
                        somatic_overdrive: ['STR', 'AGI', 'END'],
                        autonomous_construct: ['INT', 'PER', 'END'],
                      };
                      const hasMedSyn = Boolean(previewMediumSynergy && (synLookup[previewMediumSynergy] || []).includes(s.code));
                      return (
                        <div
                          key={s.key}
                          onClick={() => setFocusedStat(s.code)}
                          className={`flex items-center justify-between p-2 rounded border cursor-pointer transition-colors ${
                            isFocused
                              ? 'bg-black/70 border-fantasy-accent/60'
                              : 'bg-black/30 border-fantasy-border/50 hover:border-gray-600'
                          }`}
                        >
                          <div className="flex items-center gap-1.5 min-w-0">
                            <span className="text-sm shrink-0">{s.emoji}</span>
                            <div className="truncate">
                              <span className="text-xs font-bold text-gray-200">{s.code}</span>
                              <span className="text-[11px] text-gray-400 ml-1 truncate">
                                {t(`creator.stat_labels.${s.key}`, s.label)}
                              </span>
                              {hasMedSyn && (
                                <span className="ml-1 text-[9px] px-1 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-mono uppercase">
                                  ⚡
                                </span>
                              )}
                            </div>
                          </div>

                          <div className="flex items-center gap-1.5 shrink-0">
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                adjustStat(s.key, -1);
                              }}
                              disabled={val <= 1}
                              className="w-6 h-6 rounded bg-fantasy-dark border border-fantasy-border text-gray-200 hover:border-fantasy-accent disabled:opacity-30 text-xs font-bold flex items-center justify-center"
                            >
                              -
                            </button>
                            <span className="w-5 text-center font-mono tabular-nums text-sm font-bold text-fantasy-accent">
                              {val}
                            </span>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                adjustStat(s.key, 1);
                              }}
                              disabled={pointsRemaining <= 0 || val >= 10}
                              className="w-6 h-6 rounded bg-fantasy-dark border border-fantasy-border text-gray-200 hover:border-fantasy-accent disabled:opacity-30 text-xs font-bold flex items-center justify-center"
                            >
                              +
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Focused Stat Tooltip */}
                <div className="p-2.5 rounded-xl bg-gray-500/10 border border-fantasy-border/35 text-[11px] text-gray-300 leading-relaxed min-h-[40px]">
                  <strong className="text-fantasy-accent">{focusedStat}:</strong>{' '}
                  {statEffects[focusedStat]}
                </div>
              </div>
            </div>
          </section>
        </form>

        {/* Footer Submit */}
        <div className="px-4 py-3 border-t border-fantasy-border/35 flex flex-wrap items-center justify-between gap-3 shrink-0">
          <span className="text-xs text-gray-400">
            {pointsRemaining > 0
              ? t('creator.unspent_points_hint', {
                  count: pointsRemaining,
                  defaultValue: `${pointsRemaining} unspent point(s) will be saved for later allocation.`,
                })
              : t('creator.all_points_allocated', 'All starting attribute points allocated!')}
          </span>
          <div className="flex items-center gap-2.5">
            <MotionButton
              onClick={onClose}
              className="px-4 py-2 rounded-lg border border-fantasy-border/60 text-xs text-gray-300 hover:text-white hover:bg-gray-500/10"
            >
              {t('common.cancel', 'Cancel')}
            </MotionButton>
            <MotionButton
              type="submit"
              onClick={handleSubmit}
              disabled={submitting || !name.trim()}
              className="px-5 py-2 rounded-lg bg-fantasy-accent hover:bg-amber-400 text-black font-bold text-xs uppercase tracking-wider disabled:opacity-40 transition-colors"
            >
              {submitting
                ? t('creator.forging_hero', 'Forging Hero...')
                : t('creator.forge_hero', 'Forge Hero')}
            </MotionButton>
          </div>
        </div>
    </AcrylicModal>
  );
};

export default CharacterCreatorModal;
