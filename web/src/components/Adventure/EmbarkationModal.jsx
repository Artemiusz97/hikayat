import React, { useState, useEffect, useMemo } from 'react';
import { X, Sparkles, Shield, Sword, RotateCcw, Wand2, Compass, Tag, RefreshCw, Globe, Shirt, Check, Link, Play } from 'lucide-react';
import { apiCall } from '../../api/client';

const STAT_KEYS = [
  { key: 'str', code: 'STR', label: 'Strength' },
  { key: 'per', code: 'PER', label: 'Perception' },
  { key: 'end', code: 'END', label: 'Endurance' },
  { key: 'cha', code: 'CHA', label: 'Charisma' },
  { key: 'int', code: 'INT', label: 'Intelligence' },
  { key: 'agi', code: 'AGI', label: 'Agility' },
  { key: 'luk', code: 'LUK', label: 'Luck' },
];

function computeClassPreset(className = '', classDesc = '') {
  const text = `${className} ${classDesc}`.toLowerCase();
  if (/mage|wizard|sorcerer|warlock|arcan|scholar|psion|netrunner|alchemist|hacker/.test(text)) return { str: 1, per: 2, end: 2, cha: 1, int: 4, agi: 1, luk: 1 };
  if (/rogue|thief|assassin|ranger|scout|sniper|infiltrator|smuggler|delinquent/.test(text)) return { str: 1, per: 3, end: 1, cha: 1, int: 1, agi: 3, luk: 2 };
  if (/bard|diplomat|idol|president|noble|social|merchant|cleric|healer|priest/.test(text)) return { str: 1, per: 1, end: 2, cha: 4, int: 2, agi: 1, luk: 1 };
  if (/paladin|knight|templar|guardian|vanguard|enforcer/.test(text)) return { str: 3, per: 1, end: 3, cha: 2, int: 1, agi: 1, luk: 1 };
  return { str: 3, per: 1, end: 3, cha: 1, int: 1, agi: 2, luk: 1 };
}

const EmbarkationModal = ({ isOpen, onClose, character, onEmbark, scenarios = [], availableTags = [] }) => {
  const [step, setStep] = useState(1);
  const [scenario, setScenario] = useState('fantasy');
  const [customTags, setCustomTags] = useState(['fantasy']);
  const [charClass, setCharClass] = useState(character?.char_class || 'Warrior');
  const [startingWeapon, setStartingWeapon] = useState('Rusty Sword');
  
  const [templates, setTemplates] = useState(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [stats, setStats] = useState({ str: 1, per: 1, end: 1, cha: 1, int: 1, agi: 1, luk: 1 });
  const [regeneratedLoadout, setRegeneratedLoadout] = useState(null);
  const [regeneratingGear, setRegeneratingGear] = useState(false);
  
  const [breastSize, setBreastSize] = useState('average');
  const [penisSize, setPenisSize] = useState('average');
  const [assetTexture, setAssetTexture] = useState('');

  // Step 2 variables
  const [mode, setMode] = useState('solo'); // solo, turn, sync
  const [shareLink, setShareLink] = useState('');
  const [copied, setCopied] = useState(false);

  const isNsfw = useMemo(() => {
    if (scenario === 'nsfw_high_school_drama' || String(scenario).toLowerCase().includes('nsfw')) return true;
    if (scenario === 'custom' && customTags.includes('nsfw')) return true;
    const scenObj = scenarios.find(s => s.key === scenario);
    if (scenObj?.tags?.includes('nsfw')) return true;
    return false;
  }, [scenario, customTags, scenarios]);

  useEffect(() => {
    if (isOpen && character) {
      setStats({
        str: character.str_ ?? character.str ?? 1,
        per: character.per_ ?? character.per ?? 1,
        end: character.end_ ?? character.end ?? 1,
        cha: character.cha ?? 1,
        int: character.int_ ?? character.int ?? 1,
        agi: character.agi ?? 1,
        luk: character.luk ?? 1
      });
      const appObj = character.appearance || {};
      setBreastSize(appObj.breast_size || character.breast_size || 'average');
      setPenisSize(appObj.penis_size || character.penis_size || 'average');
      setAssetTexture(appObj.asset_texture || character.asset_texture || '');
      setStep(1);
      
      // Fetch share link in background
      apiCall('/api/server/public-url').then(res => {
        if (res.url) setShareLink(res.url);
      }).catch(() => {});
    }
  }, [isOpen, character]);

  const tagsParam = useMemo(() => (scenario === 'custom' ? customTags.join(',') : ''), [scenario, customTags]);

  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    const query = scenario === 'custom' 
      ? `/api/class-templates?scenario=custom&tags=${encodeURIComponent(tagsParam || 'fantasy')}`
      : `/api/class-templates?scenario=${encodeURIComponent(scenario || 'fantasy')}`;

    apiCall(query).then(data => {
      setTemplates(data);
      const activeClassesObj = data?.classes || {};
      const classNames = Object.keys(activeClassesObj);
      if (classNames.length > 0 && !classNames.includes(charClass)) {
        setCharClass(classNames[0]);
      }
      setRegeneratedLoadout(null);
    }).finally(() => setLoading(false));
  }, [isOpen, scenario, tagsParam]);

  const activeClassesMap = templates?.classes || {};
  const activeClassInfo = activeClassesMap[charClass] || {};
  
  const weaponsList = useMemo(() => {
    const rawList = (templates?.starting_weapons || []).map(w => typeof w === 'object' ? w.name : w);
    return rawList.length > 0 ? rawList : ['Rusty Sword', 'Oak Staff', 'Hunting Bow', 'Iron Dagger'];
  }, [templates]);

  const displayedLoadout = useMemo(() => {
    if (regeneratedLoadout) return regeneratedLoadout;
    const rawGear = activeClassInfo?.starter_gear || {};
    const loadout = {};
    Object.entries(rawGear).forEach(([slot, entry]) => {
      if (slot === 'Weapon' || !entry) return;
      if (Array.isArray(entry) && entry.length >= 1) {
        loadout[slot] = {
          name: entry[0],
          description: entry[1] ? String(entry[1]) : 'Starter equipment',
        };
      } else if (typeof entry === 'object' && entry.name) {
        loadout[slot] = entry;
      }
    });
    return loadout;
  }, [regeneratedLoadout, activeClassInfo]);

  const maxTotalPoints = 12;
  const totalAllocated = Object.values(stats).reduce((acc, v) => acc + Number(v || 1), 0);
  const pointsRemaining = maxTotalPoints - totalAllocated;

  const handleApplyPreset = () => {
    setStats(computeClassPreset(charClass, activeClassInfo?.description || ''));
  };

  const adjustStat = (key, delta) => {
    setStats((prev) => {
      const next = (prev[key] ?? 1) + delta;
      if (next < 1 || next > 10) return prev;
      if (delta > 0 && pointsRemaining <= 0) return prev;
      return { ...prev, [key]: next };
    });
  };

  const handleRegenerateEquipment = async () => {
    setRegeneratingGear(true);
    try {
      const res = await apiCall('/api/character/preview-gear', {
        method: 'POST',
        body: JSON.stringify({
          char_class: charClass,
          scenario,
          tags: scenario === 'custom' ? customTags : undefined,
          gender: character?.gender || 'Male',
          race: character?.race || 'Human',
          starting_weapon: startingWeapon,
          force_dynamic: true,
        }),
      });
      if (res?.loadout) setRegeneratedLoadout(res.loadout);
    } catch (err) {
      console.error(err);
    } finally {
      setRegeneratingGear(false);
    }
  };

  const toggleCustomTag = (tagKey) => {
    setCustomTags(prev => prev.includes(tagKey) ? prev.filter(t => t !== tagKey) : [...prev, tagKey]);
  };

  const copyLink = () => {
    if (!shareLink) return;
    navigator.clipboard.writeText(shareLink).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const submitEmbark = async () => {
    setSubmitting(true);
    setError(null);
    try {
      if (character?.user_id) {
        try {
          await apiCall('/api/character/appearance', {
            method: 'POST',
            body: JSON.stringify({
              user_id: character.user_id,
              character_id: character.id,
              breast_size: breastSize,
              penis_size: penisSize,
              asset_texture: assetTexture,
            }),
          });
        } catch (syncErr) {
          console.warn('Character appearance background sync failed:', syncErr);
        }
      }

      await onEmbark({
        scenario,
        mode,
        tags: scenario === 'custom' ? customTags : undefined,
        char_class: charClass,
        weapon_name: startingWeapon,
        starter_loadout: displayedLoadout || undefined,
        str_val: stats.str,
        per: stats.per,
        end: stats.end,
        cha: stats.cha,
        int_val: stats.int,
        agi: stats.agi,
        luk: stats.luk,
        breast_size: breastSize,
        penis_size: penisSize,
        asset_texture: assetTexture,
      });
      onClose();
    } catch (err) {
      setError(err.message || 'Embarkation failed');
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="fixed inset-0 bg-black/80 backdrop-blur-sm" onClick={onClose} />

      <div className="relative w-full max-w-4xl bg-fantasy-panel border border-fantasy-border rounded-xl shadow-2xl overflow-hidden z-10 flex flex-col max-h-[90vh]">
        <div className="p-4 border-b border-fantasy-border bg-black/50 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-fantasy-accent/15 border border-fantasy-accent/40 text-fantasy-accent">
              <Compass size={18} />
            </div>
            <div>
              <h2 className="font-rpg font-bold text-lg text-fantasy-accent">Embarkation Wizard</h2>
              <p className="text-xs text-gray-400">Step {step} of 2 • Configure Your Journey</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-white rounded"><X size={18} /></button>
        </div>

        {error && (
          <div className="mx-4 mt-3 p-2 bg-red-900/50 text-red-200 border border-red-700 text-xs rounded">{error}</div>
        )}

        <div className="flex-1 overflow-y-auto custom-scrollbar p-5 space-y-6">
          {step === 1 && (
            <>
              {/* Realm Selection */}
              <section className="bg-black/30 border border-fantasy-border/80 rounded-lg p-4 space-y-3">
                <h3 className="text-xs uppercase tracking-wider font-bold text-gray-100 mb-2">1. Origin Realm</h3>
                <select
                  value={scenario}
                  onChange={(e) => setScenario(e.target.value)}
                  className="w-full bg-fantasy-dark border border-fantasy-border p-2.5 rounded text-sm text-gray-100"
                >
                  {scenarios.map(s => <option key={s.key} value={s.key}>{s.emoji} {s.dropdown_label || s.display_name || s.name}</option>)}
                  <option value="custom">✨ Custom Scenario (Multi-Tag Builder)</option>
                </select>

                {scenario === 'custom' && (
                  <div className="space-y-3 pt-2">
                    <div>
                      <div className="text-[11px] uppercase tracking-wider font-bold text-gray-300 mb-1.5 flex items-center gap-1.5">
                        <span>Genres</span>
                        <span className="text-[10px] text-gray-400 font-normal">(select one or more)</span>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {availableTags
                          .filter(t => t.category === 'genre' || (!t.category && !['grimdark', 'furry', 'nsfw', 'gore', 'non_combat'].includes(t.key || t.id)))
                          .map(tag => {
                            const tKey = tag.key || tag.id;
                            const active = customTags.includes(tKey);
                            return (
                              <button
                                key={tKey}
                                type="button"
                                onClick={() => toggleCustomTag(tKey)}
                                className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
                                  active
                                    ? 'bg-fantasy-accent/25 border-fantasy-accent text-fantasy-accent shadow-sm'
                                    : 'bg-black/50 border-fantasy-border/60 text-gray-400 hover:text-gray-200'
                                }`}
                              >
                                {tag.name || tKey}
                              </button>
                            );
                          })}
                      </div>
                    </div>

                    <div>
                      <div className="text-[11px] uppercase tracking-wider font-bold text-gray-300 mb-1.5 flex items-center gap-1.5">
                        <span>Tone &amp; Modifiers</span>
                        <span className="text-[10px] text-gray-400 font-normal">(optional tone &amp; rule toggles)</span>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {availableTags
                          .filter(t => t.category === 'modifier' || ['grimdark', 'furry', 'nsfw', 'gore', 'non_combat'].includes(t.key || t.id))
                          .map(tag => {
                            const tKey = tag.key || tag.id;
                            const active = customTags.includes(tKey);
                            const icon = tKey === 'nsfw' ? '🔞 ' : (tKey === 'gore' ? '🩸 ' : (tKey === 'furry' ? '🐾 ' : (tKey === 'non_combat' ? '🕊️ ' : (tKey === 'grimdark' ? '💀 ' : '✨ '))));
                            return (
                              <button
                                key={tKey}
                                type="button"
                                onClick={() => toggleCustomTag(tKey)}
                                className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
                                  active
                                    ? 'bg-amber-500/25 border-amber-500 text-amber-300 shadow-sm'
                                    : 'bg-black/50 border-fantasy-border/60 text-gray-400 hover:text-gray-200'
                                }`}
                              >
                                {icon}{tag.name || tKey}
                              </button>
                            );
                          })}
                      </div>
                    </div>
                  </div>
                )}
              </section>

              {/* Class & Stats Reallocation */}
              <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-black/30 border border-fantasy-border/80 rounded-lg p-4 space-y-3">
                   <h3 className="text-xs uppercase tracking-wider font-bold text-gray-100 mb-2">2. Class &amp; Loadout</h3>
                   <select value={charClass} onChange={(e) => setCharClass(e.target.value)} className="w-full bg-fantasy-dark border border-fantasy-border p-2 rounded text-sm text-gray-100">
                     {Object.keys(activeClassesMap).map(cls => <option key={cls} value={cls}>{cls}</option>)}
                   </select>

                   <label className="block text-[11px] uppercase tracking-wider font-bold text-gray-400 mt-2">Starting Weapon</label>
                   <select value={startingWeapon} onChange={(e) => setStartingWeapon(e.target.value)} className="w-full bg-fantasy-dark border border-fantasy-border p-2 rounded text-xs text-gray-100">
                     {weaponsList.map(w => <option key={w} value={w}>{w}</option>)}
                   </select>

                   <div className="mt-3 pt-3 border-t border-fantasy-border/50 space-y-2">
                     <div className="flex items-center justify-between">
                       <span className="text-[11px] uppercase tracking-wider font-bold text-gray-400">
                         Starting Equipment
                       </span>
                       <button
                         type="button"
                         onClick={handleRegenerateEquipment}
                         disabled={regeneratingGear}
                         className="px-2 py-0.5 rounded bg-fantasy-accent/15 hover:bg-fantasy-accent/25 border border-fantasy-accent/50 text-fantasy-accent text-[11px] font-semibold flex items-center gap-1 transition-colors disabled:opacity-50"
                       >
                         <RefreshCw size={11} className={regeneratingGear ? 'animate-spin' : ''} />
                         <span>{regeneratingGear ? 'Rolling...' : 'Regenerate'}</span>
                       </button>
                     </div>

                     <div className="grid grid-cols-2 gap-1.5 max-h-36 overflow-y-auto custom-scrollbar pr-1">
                       {Object.entries(displayedLoadout).map(([slot, item]) => (
                         <div key={slot} className="p-1.5 rounded bg-black/40 border border-fantasy-border/60 flex flex-col justify-between">
                           <span className="text-[9px] uppercase tracking-wider text-gray-400">{slot}</span>
                           <span className="text-[11px] font-bold text-gray-200 truncate" title={item.description || item.name}>{item.name}</span>
                         </div>
                       ))}
                       {Object.keys(displayedLoadout).length === 0 && (
                         <div className="col-span-2 text-center text-[10px] text-gray-500 py-2 italic">
                           Default gear will be forged upon embarkation.
                         </div>
                       )}
                     </div>
                   </div>
                </div>

                {/* Stats Reallocation */}
                <div className="bg-black/30 border border-fantasy-border/80 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-xs uppercase tracking-wider font-bold text-gray-100">3. Free Stats Allocation</h3>
                    <span className="px-2 py-1 bg-black text-fantasy-accent border border-fantasy-border text-[10px] font-mono rounded">{pointsRemaining} pts left</span>
                  </div>
                  
                  <button onClick={handleApplyPreset} className="w-full mb-3 py-1.5 rounded border border-fantasy-accent/50 text-fantasy-accent text-[11px] bg-fantasy-accent/10 hover:bg-fantasy-accent/20 transition-colors">
                    Switch to {charClass} Rec
                  </button>

                  <div className="space-y-1.5">
                    {STAT_KEYS.map(s => (
                      <div key={s.key} className="flex items-center justify-between bg-black/40 border border-fantasy-border/50 p-1.5 rounded">
                        <span className="text-xs font-bold text-gray-300 w-12">{s.code}</span>
                        <div className="flex items-center gap-2">
                           <button onClick={() => adjustStat(s.key, -1)} disabled={stats[s.key] <= 1} className="w-6 h-6 bg-black border border-fantasy-border rounded text-gray-300">-</button>
                           <span className="w-4 text-center font-mono text-sm text-fantasy-accent">{stats[s.key]}</span>
                           <button onClick={() => adjustStat(s.key, 1)} disabled={pointsRemaining <= 0 || stats[s.key] >= 10} className="w-6 h-6 bg-black border border-fantasy-border rounded text-gray-300">+</button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </section>

              {/* Optional / NSFW Intimate Physical Anatomy Customizer */}
              {isNsfw && (
                <section className="bg-pink-950/20 border border-pink-800/60 rounded-lg p-4 space-y-3">
                  <div className="flex items-center justify-between border-b border-pink-900/50 pb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-base">🔞</span>
                      <h3 className="text-xs uppercase tracking-wider font-bold text-pink-300">
                        4. Intimate Anatomy &amp; Dynamic Flavor
                      </h3>
                    </div>
                    <span className="text-[10px] text-pink-400 font-medium">
                      Shapes Narrative Voice &amp; Reactions
                    </span>
                  </div>
                  <p className="text-[11px] text-gray-300 leading-relaxed">
                    Assets influence psychological vulnerability or confidence, tactile sensations, lingerie fit, and partner reactions across romantic encounters.
                  </p>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                    {/* Breast Size Tier */}
                    <div>
                      <label className="block text-[11px] uppercase tracking-wider font-bold text-pink-300 mb-1">
                        Breast Size Tier
                      </label>
                      <select
                        value={breastSize}
                        onChange={(e) => setBreastSize(e.target.value)}
                        className="w-full bg-fantasy-dark border border-pink-900/60 p-2 rounded text-xs text-gray-100 focus:outline-none focus:border-pink-500"
                      >
                        <option value="flat">Flat (AA-Cup / Barely There)</option>
                        <option value="small">Petite / Modest (A-B Cup)</option>
                        <option value="average">Proportional (C-Cup)</option>
                        <option value="large">Voluptuous / Full (D-DD Cup)</option>
                        <option value="huge">Bountiful / Massive (E+ Cup)</option>
                      </select>
                    </div>

                    {/* Penis Size Tier */}
                    <div>
                      <label className="block text-[11px] uppercase tracking-wider font-bold text-purple-300 mb-1">
                        Penis Size Tier
                      </label>
                      <select
                        value={penisSize}
                        onChange={(e) => setPenisSize(e.target.value)}
                        className="w-full bg-fantasy-dark border border-purple-900/60 p-2 rounded text-xs text-gray-100 focus:outline-none focus:border-purple-500"
                      >
                        <option value="small">Petite / Modest (Compact)</option>
                        <option value="average">Proportional (Average)</option>
                        <option value="large">Well-Endowed / Formidable (Large)</option>
                        <option value="huge">Massive / Heavy (Huge)</option>
                      </select>
                    </div>
                  </div>

                  {/* Tactile Texture / Shape Feature */}
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="block text-[11px] uppercase tracking-wider font-bold text-gray-300">
                        Tactile Feature &amp; Texture
                      </label>
                      <button
                        type="button"
                        onClick={() => {
                          const femalePool = [
                            'Perky & High-Set', 'Pillowy Soft & Yielding', 'Firm & Toned', 'Smooth & Supple',
                            'Heavy & Plush', 'Bouncy & Sensitive', 'Tender & Delicate', 'Shapely Teardrop',
                            'Compact & Dense', 'Soft & Downy Chest Fur', 'Silky Fur-Rimmed', 'Downy Feather-Lined',
                            'Silky Warm with Smooth Micro-Scales'
                          ];
                          const malePool = [
                            'Veined & Firm', 'Smooth & Heavy', 'Toned & Athletic', 'Warm & Pulsing',
                            'Slender & Ultra-Sensitive', 'Dense & Formidable', 'Balanced & Firm',
                            'Soft Fur-Ringed Base', 'Sleek Scaled Base & Firm', 'Sturdy Draconic Build'
                          ];
                          const charGen = String(character?.gender || '').toLowerCase();
                          const isM = ['male', 'man', 'boy'].some(kw => charGen.includes(kw)) && !['female', 'woman', 'girl'].some(kw => charGen.includes(kw));
                          const pool = isM ? malePool : femalePool;
                          setAssetTexture(pool[Math.floor(Math.random() * pool.length)]);
                        }}
                        className="text-[10px] text-pink-400 hover:text-pink-300 flex items-center gap-1 font-semibold"
                      >
                        <Sparkles size={11} /> Roll Feature
                      </button>
                    </div>
                    <select
                      value={assetTexture}
                      onChange={(e) => setAssetTexture(e.target.value)}
                      className="w-full bg-fantasy-dark border border-fantasy-border/80 p-2 rounded text-xs text-gray-100"
                    >
                      <option value="">Auto-Assign from Race &amp; Build (Dynamic Roll)</option>
                      <option value="Perky & High-Set">Perky &amp; High-Set</option>
                      <option value="Pillowy Soft & Yielding">Pillowy Soft &amp; Yielding</option>
                      <option value="Firm & Toned">Firm &amp; Toned</option>
                      <option value="Smooth & Supple">Smooth &amp; Supple</option>
                      <option value="Heavy & Plush">Heavy &amp; Plush</option>
                      <option value="Bouncy & Sensitive">Bouncy &amp; Sensitive</option>
                      <option value="Tender & Delicate">Tender &amp; Delicate</option>
                      <option value="Shapely Teardrop">Shapely Teardrop</option>
                      <option value="Compact & Dense">Compact &amp; Dense</option>
                      <option value="Soft & Downy Chest Fur">Soft &amp; Downy Chest Fur (Beastfolk)</option>
                      <option value="Silky Fur-Rimmed">Silky Fur-Rimmed (Beastfolk)</option>
                      <option value="Silky Warm with Smooth Micro-Scales">Silky Warm with Smooth Micro-Scales (Scaly/Draconic)</option>
                      <option value="Downy Feather-Lined">Downy Feather-Lined (Avian/Winged)</option>
                      <option value="Veined & Firm">Veined &amp; Firm (Male)</option>
                      <option value="Smooth & Heavy">Smooth &amp; Heavy (Male)</option>
                      <option value="Toned & Athletic">Toned &amp; Athletic (Male)</option>
                      <option value="Warm & Pulsing">Warm &amp; Pulsing (Male)</option>
                      <option value="Dense & Formidable">Dense &amp; Formidable (Male)</option>
                      <option value="Soft Fur-Ringed Base">Soft Fur-Ringed Base (Male Beastfolk)</option>
                      <option value="Sturdy Draconic Build">Sturdy Draconic Build (Male Draconic)</option>
                    </select>
                  </div>
                </section>
              )}
            </>
          )}

          {step === 2 && (
            <div className="space-y-6">
              <section className="bg-black/30 border border-fantasy-border/80 rounded-lg p-5">
                 <h3 className="text-sm uppercase tracking-wider font-bold text-fantasy-accent mb-4 text-center">Select Adventure Mode</h3>
                 <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                   {[
                     { id: 'solo', name: 'Solo Adventure', desc: 'Play alone, offline or online.' },
                     { id: 'turn', name: 'Multiplayer (Turn-Based)', desc: 'Take turns with friends.' },
                     { id: 'sync', name: 'Multiplayer (Sync)', desc: 'Real-time chaotic actions.' }
                   ].map(m => (
                     <div key={m.id} onClick={() => setMode(m.id)} className={`p-4 rounded-lg border cursor-pointer transition-all ${mode === m.id ? 'bg-fantasy-accent/20 border-fantasy-accent' : 'bg-black/50 border-fantasy-border hover:border-gray-500'}`}>
                       <div className="font-bold text-gray-100">{m.name}</div>
                       <div className="text-[11px] text-gray-400 mt-1">{m.desc}</div>
                     </div>
                   ))}
                 </div>
              </section>

              {mode !== 'solo' && shareLink && (
                <section className="bg-black/30 border border-fantasy-border/80 rounded-lg p-5 text-center">
                  <h4 className="text-xs font-bold text-gray-300 mb-2">Invite Friends (Cross-Device Link)</h4>
                  <p className="text-[11px] text-gray-400 mb-3">Share this public link so anyone can join your adventure!</p>
                  <div className="flex items-center justify-center gap-2">
                    <code className="px-3 py-1.5 bg-black border border-fantasy-border text-fantasy-accent rounded text-sm select-all">
                      {shareLink}
                    </code>
                    <button onClick={copyLink} className="p-1.5 rounded bg-fantasy-dark border border-fantasy-border hover:text-white transition-colors">
                      {copied ? <Check size={16} className="text-green-400" /> : <Link size={16} />}
                    </button>
                  </div>
                </section>
              )}
            </div>
          )}
        </div>

        <div className="p-4 border-t border-fantasy-border bg-black/40 flex justify-between shrink-0">
          {step === 2 ? (
            <button onClick={() => setStep(1)} className="px-4 py-2 border border-fantasy-border text-xs rounded text-gray-300">Back</button>
          ) : (
            <button onClick={onClose} className="px-4 py-2 border border-fantasy-border text-xs rounded text-gray-300">Cancel</button>
          )}

          {step === 1 ? (
             <button onClick={() => setStep(2)} className="px-5 py-2 bg-fantasy-accent text-black font-bold text-xs uppercase rounded hover:bg-amber-400 transition-colors">Next Step</button>
          ) : (
             <button onClick={submitEmbark} disabled={submitting} className="px-5 py-2 bg-fantasy-accent text-black font-bold text-xs uppercase rounded flex items-center gap-2 hover:bg-amber-400 transition-colors">
               <Play size={14} />
               {submitting ? 'Embarking...' : 'Start Adventure'}
             </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default EmbarkationModal;
