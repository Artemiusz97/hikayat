import React, { useState } from 'react';
import { X, Sparkles, Heart, Zap, Package, RotateCcw, Check } from 'lucide-react';

const STAT_KEYS = [
  { key: 'str', code: 'STR', label: 'Strength', emoji: '💪' },
  { key: 'per', code: 'PER', label: 'Perception', emoji: '👁️' },
  { key: 'end', code: 'END', label: 'Endurance', emoji: '🛡️' },
  { key: 'cha', code: 'CHA', label: 'Charisma', emoji: '🗣️' },
  { key: 'int', code: 'INT', label: 'Intelligence', emoji: '🧠' },
  { key: 'agi', code: 'AGI', label: 'Agility', emoji: '🏹' },
  { key: 'luk', code: 'LUK', label: 'Luck', emoji: '🍀' },
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

  const [stats, setStats] = useState({ ...DEFAULT_STATS });
  const [focusedStat, setFocusedStat] = useState('STR');

  const maxTotalPoints = 12;
  const totalAllocated = Object.values(stats).reduce((acc, v) => acc + Number(v || 1), 0);
  const pointsRemaining = maxTotalPoints - totalAllocated;

  const derivedHp = 200 + stats.end * 100;
  const derivedMp = 50 + stats.end * 25;
  const derivedCap = 30 + stats.str * 3;

  if (!isOpen) return null;

  const effectiveGender = gender === '__custom__' ? customGender.trim() || 'Non-binary' : gender;
  const effectiveRace = race === '__custom__' ? customRace.trim() || 'Human' : race;

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
      setError('Please enter a character name.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onCreateCharacter({
        name: name.trim(),
        gender: effectiveGender,
        race: effectiveRace,
        race_description: raceDescription.trim(),
        str: stats.str,
        per: stats.per,
        end: stats.end,
        cha: stats.cha,
        int: stats.int,
        agi: stats.agi,
        luk: stats.luk,
      });

      setName('');
      setStats({ ...DEFAULT_STATS });
      onClose();
    } catch (err) {
      setError(err.message || 'Character creation failed');
    } finally {
      setSubmitting(false);
    }
  };

  const statEffects = {
    STR: 'Strength determines physical power, carry capacity, and melee damage.',
    PER: 'Perception affects accuracy, observation skills, and detecting hidden objects.',
    END: 'Endurance governs health points (HP), stamina, and resistance to damage/poison.',
    CHA: 'Charisma improves social interactions, persuasion, and trading prices.',
    INT: 'Intelligence affects magical ability, hacking, learning speed, and skill points.',
    AGI: 'Agility improves evasion, stealth, initiative in combat, and movement speed.',
    LUK: 'Luck influences critical hit chance, finding rare loot, and random encounters.'
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="fixed inset-0 bg-black/80 backdrop-blur-sm" onClick={onClose} />

      <div className="relative w-full max-w-4xl bg-fantasy-panel border border-fantasy-border rounded-xl shadow-2xl overflow-hidden z-10 flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="p-4 border-b border-fantasy-border bg-black/50 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-fantasy-accent/15 border border-fantasy-accent/40 text-fantasy-accent">
              <Sparkles size={18} />
            </div>
            <div>
              <h2 className="font-rpg font-bold text-lg text-fantasy-accent">
                Character Creation Studio
              </h2>
              <p className="text-xs text-gray-400">
                Define your hero's basic identity and allocate S.P.E.C.I.A.L. stats.
              </p>
            </div>
          </div>

          <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-white rounded">
            <X size={18} />
          </button>
        </div>

        {error && (
          <div className="mx-5 mt-3 p-2.5 rounded bg-red-950/70 border border-red-800 text-red-200 text-xs flex items-center justify-between shrink-0">
            <span>{error}</span>
            <button onClick={() => setError(null)} className="text-gray-400 hover:text-white">
              <X size={13} />
            </button>
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto custom-scrollbar p-5 space-y-6">
          <section className="bg-black/30 border border-fantasy-border/80 rounded-lg p-4 space-y-4">
            <div className="flex items-center justify-between border-b border-fantasy-border/50 pb-2.5">
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded bg-fantasy-accent/20 border border-fantasy-accent/50 text-fantasy-accent text-[10px] font-bold uppercase tracking-wider">
                  Section 1
                </span>
                <h3 className="text-xs uppercase tracking-wider font-bold text-gray-100">
                  Basic Character Identity &amp; S.P.E.C.I.A.L. Allocation
                </h3>
              </div>
              <span className="text-[11px] text-gray-400 hidden sm:inline">
                Core identity &amp; attributes persist across scenarios
              </span>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
              {/* Left Side: Name, Gender, Race */}
              <div className="lg:col-span-5 flex flex-col justify-between space-y-4">
                <div className="space-y-3.5">
                  <div>
                    <label className="block text-[11px] uppercase tracking-wider font-bold text-gray-400 mb-1">
                      Hero Name
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. Alistair, Lyra, Kael..."
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      maxLength={40}
                      className="w-full bg-fantasy-dark border border-fantasy-border p-2.5 rounded text-sm text-gray-100 focus:outline-none focus:border-fantasy-accent"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[11px] uppercase tracking-wider font-bold text-gray-400 mb-1">
                        Gender
                      </label>
                      <select
                        value={gender}
                        onChange={(e) => setGender(e.target.value)}
                        className="w-full bg-fantasy-dark border border-fantasy-border p-2 rounded text-sm text-gray-100 focus:outline-none focus:border-fantasy-accent"
                      >
                        {['Male', 'Female'].map((g) => (
                          <option key={g} value={g}>{g}</option>
                        ))}
                        <option value="__custom__">Custom...</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-[11px] uppercase tracking-wider font-bold text-gray-400 mb-1">
                        Race / Species
                      </label>
                      <select
                        value={race}
                        onChange={(e) => setRace(e.target.value)}
                        className="w-full bg-fantasy-dark border border-fantasy-border p-2 rounded text-sm text-gray-100 focus:outline-none focus:border-fantasy-accent"
                      >
                        {['Human', 'Elf', 'Dwarf', 'Beastfolk / Anthro', 'Cyborg'].map((r) => (
                          <option key={r} value={r}>{r}</option>
                        ))}
                        <option value="__custom__">Custom Race...</option>
                      </select>
                    </div>
                  </div>

                  {(gender === '__custom__' || race === '__custom__') && (
                    <div className="space-y-2 pt-2 border-t border-fantasy-border/40">
                      {gender === '__custom__' && (
                        <input
                          type="text"
                          placeholder="Custom gender identity..."
                          value={customGender}
                          onChange={(e) => setCustomGender(e.target.value)}
                          className="w-full bg-fantasy-dark border border-fantasy-border p-2 rounded text-xs text-gray-100"
                        />
                      )}
                      {race === '__custom__' && (
                        <div className="grid grid-cols-1 gap-2">
                          <input
                            type="text"
                            placeholder="Custom race/species name..."
                            value={customRace}
                            onChange={(e) => setCustomRace(e.target.value)}
                            className="w-full bg-fantasy-dark border border-fantasy-border p-2 rounded text-xs text-gray-100"
                          />
                          <input
                            type="text"
                            placeholder="Optional physical/species traits..."
                            value={raceDescription}
                            onChange={(e) => setRaceDescription(e.target.value)}
                            className="w-full bg-fantasy-dark border border-fantasy-border p-2 rounded text-xs text-gray-100"
                          />
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Live Derived Vitals Preview */}
                <div className="space-y-1.5">
                  <span className="block text-[10px] uppercase tracking-wider font-bold text-gray-400">
                    Derived Starting Vitals
                  </span>
                  <div className="bg-black/40 border border-fantasy-border/60 p-3 rounded-lg grid grid-cols-3 gap-2 text-center">
                    <div className="bg-black/40 border border-red-900/40 rounded p-2">
                      <div className="text-[10px] uppercase text-gray-400 flex items-center justify-center gap-1">
                        <Heart size={11} className="text-red-400" /> Max HP
                      </div>
                      <div className="text-sm font-bold font-mono text-red-300 mt-0.5">{derivedHp}</div>
                    </div>
                    <div className="bg-black/40 border border-blue-900/40 rounded p-2">
                      <div className="text-[10px] uppercase text-gray-400 flex items-center justify-center gap-1">
                        <Zap size={11} className="text-blue-400" /> Max MP
                      </div>
                      <div className="text-sm font-bold font-mono text-blue-300 mt-0.5">{derivedMp}</div>
                    </div>
                    <div className="bg-black/40 border border-amber-900/40 rounded p-2">
                      <div className="text-[10px] uppercase text-gray-400 flex items-center justify-center gap-1">
                        <Package size={11} className="text-amber-400" /> Pack Slots
                      </div>
                      <div className="text-sm font-bold font-mono text-amber-300 mt-0.5">{derivedCap}</div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Right Side: S.P.E.C.I.A.L. Point-Buy */}
              <div className="lg:col-span-7 bg-black/40 border border-fantasy-border/70 p-3.5 rounded-lg flex flex-col justify-between space-y-3">
                <div>
                  <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                    <div>
                      <h4 className="text-xs uppercase tracking-wider font-bold text-fantasy-accent">
                        S.P.E.C.I.A.L. Point-Buy
                      </h4>
                      <p className="text-[11px] text-gray-400">
                        Base 1 per stat • 5 bonus points ({maxTotalPoints} total)
                      </p>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={handleResetStats}
                        className="py-1 px-2 rounded bg-black/50 hover:bg-black/80 border border-fantasy-border text-gray-300 text-xs flex items-center gap-1 transition-colors"
                      >
                        <RotateCcw size={12} />
                        <span>Reset</span>
                      </button>
                      <span
                        className={`px-2.5 py-1 rounded text-xs font-mono font-bold border ${
                          pointsRemaining > 0
                            ? 'bg-amber-500/20 border-amber-500/50 text-amber-300'
                            : 'bg-emerald-950/60 border-emerald-700/50 text-emerald-300'
                        }`}
                      >
                        {pointsRemaining} pts left
                      </span>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                    {STAT_KEYS.map((s) => {
                      const val = stats[s.key] ?? 1;
                      const isFocused = focusedStat === s.code;
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
                                {s.label}
                              </span>
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
                            <span className="w-5 text-center font-mono text-sm font-bold text-fantasy-accent">
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
                <div className="p-2 rounded bg-black/50 border border-fantasy-border/60 text-[11px] text-gray-300 leading-relaxed min-h-[40px]">
                  <strong className="text-fantasy-accent">{focusedStat}:</strong>{' '}
                  {statEffects[focusedStat]}
                </div>
              </div>
            </div>
          </section>
        </form>

        {/* Footer Submit */}
        <div className="p-4 border-t border-fantasy-border bg-black/40 flex flex-wrap items-center justify-between gap-3 shrink-0">
          <span className="text-xs text-gray-400">
            {pointsRemaining > 0
              ? `${pointsRemaining} unspent point(s) will be saved for later allocation.`
              : 'All starting attribute points allocated!'}
          </span>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded border border-fantasy-border text-xs text-gray-300 hover:text-white"
            >
              Cancel
            </button>
            <button
              type="submit"
              onClick={handleSubmit}
              disabled={submitting || !name.trim()}
              className="px-5 py-2 rounded bg-fantasy-accent hover:bg-amber-400 text-black font-bold text-xs uppercase tracking-wider disabled:opacity-40 transition-colors"
            >
              {submitting ? 'Forging Hero...' : 'Forge Hero'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CharacterCreatorModal;
