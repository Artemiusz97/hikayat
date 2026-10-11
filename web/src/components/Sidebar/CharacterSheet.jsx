import React, { useState, useEffect } from 'react';
import { Shield, Heart, Zap, User, Coins, Sparkles, Plus, AlertCircle, BookOpen, X } from 'lucide-react';
import { apiCall } from '../../api/client';

const StatBar = ({ label, current, max, color, icon: Icon, extraText }) => {
  const safeCurrent = Math.max(0, current || 0);
  const safeMax = Math.max(1, max || 1);
  const pct = Math.min(100, Math.round((safeCurrent / safeMax) * 100));

  return (
    <div className="mb-1.5">
      <div className="flex justify-between items-end mb-0.5">
        <div className="flex items-center gap-1.5 text-[11px] font-bold text-gray-300 uppercase tracking-wider">
          <Icon size={12} className={color.text} />
          <span>{label}</span>
        </div>
        <div className="flex items-center gap-1.5">
          {extraText && <span className="text-[9px] text-gray-500">{extraText}</span>}
          <span className="text-[11px] font-mono text-gray-300 font-semibold">{safeCurrent} / {safeMax}</span>
        </div>
      </div>
      <div className="h-1.5 w-full bg-black/70 rounded-full overflow-hidden border border-fantasy-border/60">
        <div 
          className={`h-full ${color.bg} transition-all duration-500 ease-out`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
};

const StatusEffectBadge = ({ effect }) => {
  const effName = typeof effect === 'string' ? effect : (effect.name || 'Effect');
  const duration = typeof effect === 'object' && effect.duration !== undefined ? effect.duration : null;
  
  const lower = effName.toLowerCase();
  const isNegative = ['bleed', 'poison', 'burn', 'stun', 'prone', 'weaken', 'wound', 'curse', 'drain', 'freeze'].some(k => lower.includes(k));
  const isPositive = ['shield', 'buff', 'bless', 'haste', 'regen', 'focus', 'inspire', 'guard'].some(k => lower.includes(k));

  const badgeColor = isNegative 
    ? 'bg-red-950/60 text-red-300 border-red-800/60' 
    : isPositive 
      ? 'bg-emerald-950/60 text-emerald-300 border-emerald-800/60' 
      : 'bg-amber-950/60 text-amber-300 border-amber-800/60';

  return (
    <span 
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium border ${badgeColor}`}
      title={duration !== null ? `${effName} (${duration} turns remaining)` : effName}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse"></span>
      {effName}
      {duration !== null && <span className="opacity-70 text-[9px] font-mono font-bold">({duration}t)</span>}
    </span>
  );
};

const CharacterSheet = ({ character, onAllocateStat, onCastSpell, processingTurn }) => {
  const [allocating, setAllocating] = useState(null);
  const [showAppearanceModal, setShowAppearanceModal] = useState(false);
  const [editBSize, setEditBSize] = useState(character?.appearance?.breast_size || character?.breast_size || 'average');
  const [editPSize, setEditPSize] = useState(character?.appearance?.penis_size || character?.penis_size || 'average');
  const [editTexture, setEditTexture] = useState(character?.appearance?.asset_texture || character?.asset_texture || '');
  const [savingApp, setSavingApp] = useState(false);

  useEffect(() => {
    if (character) {
      setEditBSize(character.appearance?.breast_size || character.breast_size || 'average');
      setEditPSize(character.appearance?.penis_size || character.penis_size || 'average');
      setEditTexture(character.appearance?.asset_texture || character.asset_texture || '');
    }
  }, [character?.id, showAppearanceModal]);

  const charGender = (character?.gender || '').toLowerCase();
  const isMale = ['male', 'man', 'boy', 'lord', 'he', 'him', 'his'].some(kw => charGender.includes(kw)) && !['female', 'woman', 'girl', 'lady', 'she', 'her'].some(kw => charGender.includes(kw));
  const isNsfw = String(character?.scenario || '').includes('nsfw') || Boolean(character?.appearance?.breast_size || character?.appearance?.penis_size);

  const handleSaveAppearance = async () => {
    setSavingApp(true);
    try {
      const res = await apiCall('/api/character/appearance', {
        method: 'POST',
        body: JSON.stringify({
          user_id: character.user_id,
          character_id: character.id,
          breast_size: editBSize,
          penis_size: editPSize,
          asset_texture: editTexture,
        }),
      });
      if (res?.character) {
        if (!character.appearance) character.appearance = {};
        character.appearance.breast_size = editBSize;
        character.appearance.penis_size = editPSize;
        character.appearance.asset_texture = editTexture;
      }
      setShowAppearanceModal(false);
    } catch (err) {
      console.error('Failed to update appearance:', err);
    } finally {
      setSavingApp(false);
    }
  };

  if (!character) return null;

  const pendingPoints = character.pending_stat_points || 0;
  const tempHp = Number(character.temp_hp || character.combat_attributes?.temp_hp || 0);
  const isNonCombat = Boolean(character.is_non_combat || character.combat_attributes?.is_non_combat);
  const ca = character.combat_attributes || {};

  const handleAllocate = async (stat) => {
    if (!onAllocateStat || allocating) return;
    setAllocating(stat);
    try {
      await onAllocateStat(stat);
    } catch (err) {
      console.error("Allocation failed:", err);
    } finally {
      setAllocating(null);
    }
  };

  // Status effects parsing
  let statusList = [];
  if (Array.isArray(character.status_effects)) {
    statusList = character.status_effects;
  } else if (typeof character.status_effects === 'string' && character.status_effects.trim()) {
    try {
      statusList = JSON.parse(character.status_effects);
    } catch {
      statusList = character.status_effects.split(',').map(s => s.trim()).filter(Boolean);
    }
  }

  // Core 7 attributes
  const coreStats = [
    { key: 'str_', label: 'STR', name: 'STR', val: character.str_ ?? 1, desc: 'Attack & Inventory' },
    { key: 'agi', label: 'AGI', name: 'AGI', val: character.agi ?? 1, desc: 'Speed & Evasion' },
    { key: 'int_', label: 'INT', name: 'INT', val: character.int_ ?? 1, desc: 'Magic & Lore' },
    { key: 'end_', label: 'END', name: 'END', val: character.end_ ?? 1, desc: 'Health & Defense' },
    { key: 'per_', label: 'PER', name: 'PER', val: character.per_ ?? 1, desc: 'Perception & Crit' },
    { key: 'cha', label: 'CHA', name: 'CHA', val: character.cha ?? 1, desc: 'Social & Romance' },
    { key: 'luk', label: 'LUK', name: 'LUK', val: character.luk ?? 1, desc: 'Fortune & Loot' },
  ];

  const combatGrid = [
    { label: 'ATK', val: ca.attack_power ?? ca.atk ?? 0 },
    { label: 'MATK', val: ca.magic_attack ?? ca.matk ?? ca.spell_power ?? 0 },
    { label: 'DEF', val: ca.defense ?? ca.def ?? 0 },
    { label: 'MDEF', val: ca.magic_defense ?? ca.mdef ?? ca.magic_resist ?? 0 },
    { label: 'Crit%', val: `${ca.crit_chance ?? ca.crit_pct ?? ca.crit ?? 0}%` },
    { label: 'EVA%', val: `${ca.evasion_chance ?? ca.evasion_pct ?? ca.evasion ?? ca.eva ?? 0}%` },
    { label: 'Block%', val: `${ca.block_chance ?? ca.block_pct ?? ca.block ?? 0}%` },
  ];

  const nextLevelXp = Math.max(100, (character.level || 1) * 100);

  return (
    <div className="bg-black/30 rounded-lg border border-fantasy-border p-2.5 sm:p-3 space-y-2.5">
      
      {/* Hero Header */}
      <div className="flex items-start justify-between border-b border-fantasy-border pb-2.5 gap-2">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-10 h-10 bg-fantasy-dark border border-fantasy-accent/40 rounded-full flex items-center justify-center shadow-inner shadow-black shrink-0">
            <User size={20} className="text-fantasy-accent" />
          </div>
          <div className="min-w-0">
            <h2 className="font-rpg font-bold text-base text-gray-100 leading-tight tracking-wide truncate">{character.name}</h2>
            <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
              <span className="text-[11px] text-fantasy-accent font-semibold uppercase tracking-wider">
                Lv.{character.level || 1} {character.char_class || character.class_name || 'Adventurer'}
              </span>
              {character.scenario && (
                <span className="text-[10px] px-1.5 py-0.2 bg-fantasy-border/60 text-gray-300 rounded font-medium">
                  {character.scenario_display_name || character.scenario}
                </span>
              )}
            </div>
            <div className="flex items-center gap-1 mt-1 flex-wrap text-[10px] text-gray-300">
              {character.race && (
                <span className="px-1.5 py-0.2 rounded bg-black/50 border border-fantasy-border/60">{character.race}</span>
              )}
              {character.gender && (
                <span className="px-1.5 py-0.2 rounded bg-black/50 border border-fantasy-border/60">{character.gender}</span>
              )}
              <span className="px-1.5 py-0.2 rounded bg-black/50 border border-fantasy-border/60 font-mono text-[9px]">
                📅 {character.days_adventured ?? 1}d
              </span>
              {isNsfw && !isMale && (
                <button
                  type="button"
                  onClick={() => setShowAppearanceModal(true)}
                  className="px-1.5 py-0.2 rounded bg-pink-950/60 hover:bg-pink-900/80 border border-pink-700/60 text-pink-300 font-medium text-[9px] flex items-center gap-1 transition-colors"
                  title="Click to customize breast size & tactile flavor"
                >
                  <span>🔞 Breast Size: {character.appearance?.breast_size || character.breast_size || 'Modest'}</span>
                  {(character.appearance?.asset_texture || character.asset_texture) && (
                    <span className="text-pink-200/70 italic">({character.appearance?.asset_texture || character.asset_texture})</span>
                  )}
                </button>
              )}
              {isNsfw && isMale && (
                <button
                  type="button"
                  onClick={() => setShowAppearanceModal(true)}
                  className="px-1.5 py-0.2 rounded bg-purple-950/60 hover:bg-purple-900/80 border border-purple-700/60 text-purple-300 font-medium text-[9px] flex items-center gap-1 transition-colors"
                  title="Click to customize penis size & tactile flavor"
                >
                  <span>🔞 Penis Size: {character.appearance?.penis_size || character.penis_size || 'Average'}</span>
                  {(character.appearance?.asset_texture || character.asset_texture) && (
                    <span className="text-purple-200/70 italic">({character.appearance?.asset_texture || character.asset_texture})</span>
                  )}
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Currency Display */}
        <div className="flex items-center gap-1 bg-black/50 border border-amber-900/40 px-2 py-1 rounded text-amber-300 font-mono text-xs sm:text-sm shrink-0">
          <Coins size={13} className="text-amber-400" />
          <span className="font-bold">{character.gold !== undefined ? character.gold : 0}</span>
          <span className="text-[10px] text-amber-500 font-bold">G</span>
        </div>
      </div>

      {/* Roleplay Mode Notice */}
      {isNonCombat && (
        <div className="bg-cyan-950/30 border border-cyan-800/50 px-2.5 py-1.5 rounded text-[11px] text-cyan-200 flex items-center gap-1.5">
          <Sparkles size={13} className="text-cyan-400 shrink-0" />
          <span><strong>Social / Roleplay Scenario:</strong> Attributes scale social influence and stamina.</span>
        </div>
      )}

      {/* Vitals (HP, Temp Shield & MP) */}
      <div className="space-y-1 bg-black/40 p-2.5 rounded-md border border-fantasy-border/40">
        {tempHp > 0 && (
          <div className="flex justify-end mb-0.5">
            <span className="text-[9px] font-mono font-bold px-1.5 py-0.2 rounded bg-cyan-950/80 text-cyan-300 border border-cyan-600/60 flex items-center gap-1">
              <Shield size={9} /> +{tempHp} Shield
            </span>
          </div>
        )}
        <StatBar 
          label="HP" current={character.hp} max={character.max_hp} 
          icon={Heart} color={{ text: 'text-health', bg: 'bg-health' }} 
          extraText={tempHp > 0 ? `+${tempHp} Shield` : null}
        />
        <StatBar 
          label="MP" current={character.mp} max={character.max_mp} 
          icon={Zap} color={{ text: 'text-mana', bg: 'bg-mana' }} 
        />
        {/* XP Bar */}
        <div className="pt-1 border-t border-fantasy-border/30">
          <div className="flex justify-between items-center text-[11px] text-gray-300 mb-0.5">
            <span className="uppercase font-semibold tracking-wider text-gray-400 text-[10px]">Experience</span>
            <span className="font-mono text-[10px]">{character.xp || 0} / {nextLevelXp} XP</span>
          </div>
          <div className="h-1.5 w-full bg-black/80 rounded-full overflow-hidden border border-fantasy-border/40">
            <div 
              className="h-full bg-purple-500 transition-all duration-500 ease-out"
              style={{ width: `${Math.min(100, Math.round(((character.xp || 0) / nextLevelXp) * 100))}%` }}
            />
          </div>
        </div>
      </div>

      {/* Active Status Effects */}
      {statusList && statusList.length > 0 && (
        <div className="bg-black/40 p-2 rounded-md border border-fantasy-border/40">
          <div className="text-[10px] uppercase font-bold text-gray-400 mb-1 flex items-center gap-1">
            <AlertCircle size={12} className="text-amber-400" />
            <span>Active Conditions</span>
          </div>
          <div className="flex flex-wrap gap-1">
            {statusList.map((eff, idx) => (
              <StatusEffectBadge key={idx} effect={eff} />
            ))}
          </div>
        </div>
      )}

      {/* Pending Stat Points Alert */}
      {pendingPoints > 0 && (
        <div className="bg-amber-950/40 border border-amber-600/50 p-2 rounded-md flex items-center justify-between text-xs text-amber-200 animate-pulse">
          <div className="flex items-center gap-1.5">
            <Sparkles size={13} className="text-amber-400" />
            <span className="font-medium text-[11px]"><strong>{pendingPoints}</strong> unspent point{pendingPoints > 1 ? 's' : ''}!</span>
          </div>
          <span className="text-[10px] uppercase font-bold text-amber-400 tracking-wider">Allocate Below</span>
        </div>
      )}

      {/* Core Attributes Grid */}
      <div>
        <div className="text-[11px] uppercase font-bold text-gray-300 tracking-wider mb-1.5 flex justify-between items-center">
          <span>S.P.E.C.I.A.L. Attributes</span>
          <span className="text-[10px] text-gray-400 font-mono">
            Slots: {character.used_inventory_slots ?? 0}/{character.inventory_capacity ?? 10}
          </span>
        </div>
        <div className="grid grid-cols-4 gap-1 text-center text-xs">
          {coreStats.map(st => (
            <div 
              key={st.key}
              className="bg-black/50 p-1.5 sm:p-2 rounded border border-fantasy-border/60 hover:border-fantasy-border transition-colors flex flex-col justify-between relative group"
            >
              <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">{st.label}</div>
              <div className="font-mono text-sm font-bold text-gray-100 my-0.5">{st.val}</div>
              
              {/* Stat Allocation Plus Button */}
              {pendingPoints > 0 && (
                <button
                  onClick={() => handleAllocate(st.name)}
                  disabled={allocating !== null}
                  className="mt-0.5 flex items-center justify-center gap-0.5 w-full py-0.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 rounded text-[9px] font-bold transition-all disabled:opacity-50"
                  title={`Add +1 to ${st.label}`}
                >
                  <Plus size={9} />
                  <span>Add</span>
                </button>
              )}
            </div>
          ))}
          {/* Capacity stat tile */}
          <div className="bg-black/50 p-1.5 sm:p-2 rounded border border-fantasy-border/60 flex flex-col justify-between">
            <div className="text-[10px] font-bold text-gray-500 uppercase tracking-wider">Slots</div>
            <div className="font-mono text-[11px] text-gray-300 my-auto">
              {character.used_inventory_slots ?? 0}/{character.inventory_capacity ?? 10}
            </div>
          </div>
        </div>
      </div>

      {/* Derived Combat Attributes Grid */}
      <div className="pt-1.5 border-t border-fantasy-border/40">
        <div className="text-[10px] uppercase font-bold text-gray-400 tracking-wider mb-1.5">
          <span>Combat & Tactical Stats</span>
        </div>
        <div className="grid grid-cols-4 sm:grid-cols-7 gap-1 text-center">
          {combatGrid.map((cg) => (
            <div key={cg.label} className="bg-black/40 border border-fantasy-border/50 rounded p-1">
              <div className="text-[9px] font-bold text-gray-400 uppercase">{cg.label}</div>
              <div className="text-[11px] font-mono font-bold text-gray-200 mt-0.5">{cg.val}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Learned Spells / Grimoire */}
      {Array.isArray(character.learned_spells) && character.learned_spells.length > 0 && (
        <div className="pt-2 border-t border-fantasy-border/40">
          <div className="text-xs uppercase font-bold text-indigo-300 tracking-wider mb-2 flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <BookOpen size={14} className="text-indigo-400" />
              <span>Grimoire ({character.learned_spells.length})</span>
            </span>
            <span className="text-xs text-gray-400 font-mono">Learned Spells</span>
          </div>
          <div className="space-y-1.5 max-h-56 overflow-y-auto custom-scrollbar pr-1">
            {character.learned_spells.map((sp, idx) => {
              const mpCost = Number(sp.mp_cost || 0);
              const canAffordMp = (character.mp ?? 0) >= mpCost;
              return (
                <div
                  key={sp.id || idx}
                  className="bg-black/50 border border-indigo-900/50 rounded p-2.5 flex flex-col gap-1.5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-indigo-200 truncate">{sp.name}</span>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {sp.tier_name && (
                        <span className="text-[9px] uppercase px-1.5 py-0.5 rounded bg-indigo-950/80 text-indigo-300 border border-indigo-800/60">
                          {sp.tier_name}
                        </span>
                      )}
                      {onCastSpell ? (
                        <button
                          type="button"
                          disabled={!canAffordMp || processingTurn}
                          onClick={() => onCastSpell(sp)}
                          title={canAffordMp ? `Cast ${sp.name} (${mpCost} MP)` : `Requires ${mpCost} MP`}
                          className="px-2 py-0.5 rounded bg-indigo-600/30 hover:bg-indigo-500/40 text-indigo-200 border border-indigo-500/50 text-[10px] font-mono font-bold flex items-center gap-1 disabled:opacity-40 transition-colors"
                        >
                          <Zap size={10} className="text-blue-300" />
                          <span>Cast ({mpCost} MP)</span>
                        </button>
                      ) : (
                        <span className="text-[10px] font-mono text-blue-400 flex items-center gap-0.5">
                          <Zap size={10} /> {mpCost} MP
                        </span>
                      )}
                    </div>
                  </div>
                  {sp.description && (
                    <p className="text-xs text-gray-300 leading-relaxed">{sp.description}</p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Intimate Physical Anatomy Live Customization Modal */}
      {showAppearanceModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="relative w-full max-w-md bg-fantasy-panel border border-fantasy-border rounded-xl shadow-2xl overflow-hidden p-5 space-y-4">
            <div className="flex items-center justify-between border-b border-fantasy-border/60 pb-3">
              <div className="flex items-center gap-2">
                <span className="text-lg">🔞</span>
                <div>
                  <h3 className="font-rpg font-bold text-sm text-fantasy-accent">
                    Customize Physical Anatomy
                  </h3>
                  <p className="text-[10px] text-gray-400">
                    Live update your character's assets &amp; tactile textures
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowAppearanceModal(false)}
                className="text-gray-400 hover:text-white p-1"
              >
                <X size={16} />
              </button>
            </div>

            <div className="space-y-3.5 text-xs">
              <div>
                <label className="block text-[11px] uppercase tracking-wider font-bold text-pink-300 mb-1">
                  Breast Size Tier
                </label>
                <select
                  value={editBSize}
                  onChange={(e) => setEditBSize(e.target.value)}
                  className="w-full bg-fantasy-dark border border-fantasy-border p-2 rounded text-xs text-gray-100"
                >
                  <option value="flat">Flat (AA-Cup / Barely There)</option>
                  <option value="small">Petite / Modest (A-B Cup)</option>
                  <option value="average">Proportional (C-Cup)</option>
                  <option value="large">Voluptuous / Full (D-DD Cup)</option>
                  <option value="huge">Bountiful / Massive (E+ Cup)</option>
                </select>
              </div>

              <div>
                <label className="block text-[11px] uppercase tracking-wider font-bold text-purple-300 mb-1">
                  Penis Size Tier
                </label>
                <select
                  value={editPSize}
                  onChange={(e) => setEditPSize(e.target.value)}
                  className="w-full bg-fantasy-dark border border-fantasy-border p-2 rounded text-xs text-gray-100"
                >
                  <option value="small">Petite / Modest (Compact)</option>
                  <option value="average">Proportional (Average)</option>
                  <option value="large">Well-Endowed / Formidable (Large)</option>
                  <option value="huge">Massive / Heavy (Huge)</option>
                </select>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="block text-[11px] uppercase tracking-wider font-bold text-gray-300">
                    Tactile Texture / Feature
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
                      const pool = isMale ? malePool : femalePool;
                      setEditTexture(pool[Math.floor(Math.random() * pool.length)]);
                    }}
                    className="text-[10px] text-pink-400 hover:text-pink-300 flex items-center gap-1 font-semibold"
                  >
                    <Sparkles size={11} /> Roll Feature
                  </button>
                </div>
                <select
                  value={editTexture}
                  onChange={(e) => setEditTexture(e.target.value)}
                  className="w-full bg-fantasy-dark border border-fantasy-border p-2 rounded text-xs text-gray-100"
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
                  <option value="Silky Warm with Smooth Micro-Scales">Silky Warm with Smooth Micro-Scales</option>
                  <option value="Downy Feather-Lined">Downy Feather-Lined</option>
                  <option value="Veined & Firm">Veined &amp; Firm (Male)</option>
                  <option value="Smooth & Heavy">Smooth &amp; Heavy (Male)</option>
                  <option value="Toned & Athletic">Toned &amp; Athletic (Male)</option>
                  <option value="Warm & Pulsing">Warm &amp; Pulsing (Male)</option>
                  <option value="Dense & Formidable">Dense &amp; Formidable (Male)</option>
                  <option value="Soft Fur-Ringed Base">Soft Fur-Ringed Base (Male Beastfolk)</option>
                  <option value="Sturdy Draconic Build">Sturdy Draconic Build (Male Draconic)</option>
                </select>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-fantasy-border/60">
              <button
                type="button"
                onClick={() => setShowAppearanceModal(false)}
                className="px-3 py-1.5 rounded border border-fantasy-border text-xs text-gray-300 hover:text-white"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveAppearance}
                disabled={savingApp}
                className="px-4 py-1.5 rounded bg-fantasy-accent hover:bg-amber-400 text-black font-bold text-xs uppercase disabled:opacity-50 transition-colors"
              >
                {savingApp ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};

export default CharacterSheet;

