import React, { useState } from 'react';
import { Shield, Heart, Zap, User, Coins, Sparkles, Plus, AlertCircle, BookOpen } from 'lucide-react';

const StatBar = ({ label, current, max, color, icon: Icon, extraText }) => {
  const safeCurrent = Math.max(0, current || 0);
  const safeMax = Math.max(1, max || 1);
  const pct = Math.min(100, Math.round((safeCurrent / safeMax) * 100));

  return (
    <div className="mb-2.5">
      <div className="flex justify-between items-end mb-1">
        <div className="flex items-center gap-1.5 text-xs font-bold text-gray-300 uppercase tracking-wider">
          <Icon size={13} className={color.text} />
          <span>{label}</span>
        </div>
        <div className="flex items-center gap-1.5">
          {extraText && <span className="text-[10px] text-gray-500">{extraText}</span>}
          <span className="text-xs font-mono text-gray-300 font-semibold">{safeCurrent} / {safeMax}</span>
        </div>
      </div>
      <div className="h-2 w-full bg-black/70 rounded-full overflow-hidden border border-fantasy-border/60">
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
    <div className="bg-black/30 rounded-lg border border-fantasy-border p-4 mb-4 space-y-4">
      
      {/* Hero Header */}
      <div className="flex items-start justify-between border-b border-fantasy-border pb-3 gap-2">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-12 h-12 bg-fantasy-dark border border-fantasy-accent/40 rounded-full flex items-center justify-center shadow-inner shadow-black shrink-0">
            <User size={24} className="text-fantasy-accent" />
          </div>
          <div className="min-w-0">
            <h2 className="font-rpg font-bold text-lg text-gray-100 leading-tight tracking-wide truncate">{character.name}</h2>
            <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
              <span className="text-xs text-fantasy-accent font-semibold uppercase tracking-wider">
                Lv.{character.level || 1} {character.char_class || character.class_name || 'Adventurer'}
              </span>
              {character.scenario && (
                <span className="text-[10px] px-1.5 py-0.2 bg-fantasy-border/60 text-gray-400 rounded">
                  {character.scenario}
                </span>
              )}
            </div>
            <div className="flex items-center gap-1.5 mt-1 flex-wrap text-[10px] text-gray-400">
              {character.race && (
                <span className="px-1.5 py-0.2 rounded bg-black/50 border border-fantasy-border/60">{character.race}</span>
              )}
              {character.gender && (
                <span className="px-1.5 py-0.2 rounded bg-black/50 border border-fantasy-border/60">{character.gender}</span>
              )}
              <span className="px-1.5 py-0.2 rounded bg-black/50 border border-fantasy-border/60 font-mono">
                📅 {character.days_adventured ?? 1}d Adventured
              </span>
            </div>
          </div>
        </div>

        {/* Currency Display */}
        <div className="flex items-center gap-1.5 bg-black/50 border border-amber-900/40 px-2.5 py-1.5 rounded-md text-amber-300 font-mono text-xs shrink-0">
          <Coins size={14} className="text-amber-400" />
          <span className="font-bold">{character.gold !== undefined ? character.gold : 0}</span>
          <span className="text-[10px] text-amber-500/80">G</span>
        </div>
      </div>

      {/* Roleplay Mode Notice */}
      {isNonCombat && (
        <div className="bg-cyan-950/30 border border-cyan-800/50 px-3 py-1.5 rounded text-[11px] text-cyan-200 flex items-center gap-1.5">
          <Sparkles size={12} className="text-cyan-400 shrink-0" />
          <span><strong>Social / Roleplay Scenario:</strong> Attributes scale social influence, deduction, and daily stamina.</span>
        </div>
      )}

      {/* Vitals (HP, Temp Shield & MP) */}
      <div className="space-y-1 bg-black/40 p-3 rounded-md border border-fantasy-border/40">
        {tempHp > 0 && (
          <div className="flex justify-end mb-1">
            <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-cyan-950/80 text-cyan-300 border border-cyan-600/60 flex items-center gap-1">
              <Shield size={10} /> +{tempHp} Shield
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
          <div className="flex justify-between items-center text-[10px] text-gray-400 mb-1">
            <span className="uppercase font-semibold tracking-wider text-gray-500">Experience</span>
            <span className="font-mono">{character.xp || 0} / {nextLevelXp} XP</span>
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
        <div className="bg-black/40 p-2.5 rounded-md border border-fantasy-border/40">
          <div className="text-[10px] uppercase font-bold text-gray-400 mb-1.5 flex items-center gap-1">
            <AlertCircle size={11} className="text-amber-400" />
            <span>Active Conditions</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {statusList.map((eff, idx) => (
              <StatusEffectBadge key={idx} effect={eff} />
            ))}
          </div>
        </div>
      )}

      {/* Pending Stat Points Alert */}
      {pendingPoints > 0 && (
        <div className="bg-amber-950/40 border border-amber-600/50 p-2.5 rounded-md flex items-center justify-between text-xs text-amber-200 animate-pulse">
          <div className="flex items-center gap-2">
            <Sparkles size={14} className="text-amber-400" />
            <span className="font-medium"><strong>{pendingPoints}</strong> unspent stat point{pendingPoints > 1 ? 's' : ''}!</span>
          </div>
          <span className="text-[10px] uppercase font-bold text-amber-400 tracking-wider">Allocate Below</span>
        </div>
      )}

      {/* Core Attributes Grid */}
      <div>
        <div className="text-[11px] uppercase font-bold text-gray-400 tracking-wider mb-2 flex justify-between items-center">
          <span>S.P.E.C.I.A.L. Attributes</span>
          <span className="text-[10px] text-gray-500 font-mono">
            Slots: {character.used_inventory_slots ?? 0}/{character.inventory_capacity ?? 10}
          </span>
        </div>
        <div className="grid grid-cols-4 gap-1.5 text-center text-xs">
          {coreStats.map(st => (
            <div 
              key={st.key}
              className="bg-black/50 p-2 rounded border border-fantasy-border/60 hover:border-fantasy-border transition-colors flex flex-col justify-between relative group"
            >
              <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">{st.label}</div>
              <div className="font-mono text-base font-semibold text-gray-100 my-0.5">{st.val}</div>
              
              {/* Stat Allocation Plus Button */}
              {pendingPoints > 0 && (
                <button
                  onClick={() => handleAllocate(st.name)}
                  disabled={allocating !== null}
                  className="mt-1 flex items-center justify-center gap-0.5 w-full py-0.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 rounded text-[10px] font-bold transition-all disabled:opacity-50"
                  title={`Add +1 to ${st.label}`}
                >
                  <Plus size={10} />
                  <span>Add</span>
                </button>
              )}
            </div>
          ))}
          {/* Capacity stat tile */}
          <div className="bg-black/50 p-2 rounded border border-fantasy-border/60 flex flex-col justify-between">
            <div className="text-[10px] font-bold text-gray-500 uppercase tracking-wider">Slots</div>
            <div className="font-mono text-xs text-gray-300 my-auto">
              {character.used_inventory_slots ?? 0} / {character.inventory_capacity ?? 10}
            </div>
          </div>
        </div>
      </div>

      {/* Derived Combat Attributes Grid */}
      <div className="pt-2 border-t border-fantasy-border/40">
        <div className="text-[10px] uppercase font-bold text-gray-400 tracking-wider mb-2">
          <span>Combat & Tactical Stats</span>
        </div>
        <div className="grid grid-cols-4 sm:grid-cols-7 gap-1 text-center">
          {combatGrid.map((cg) => (
            <div key={cg.label} className="bg-black/40 border border-fantasy-border/50 rounded p-1.5">
              <div className="text-[9px] font-bold text-gray-500 uppercase">{cg.label}</div>
              <div className="text-xs font-mono font-bold text-gray-200 mt-0.5">{cg.val}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Learned Spells / Grimoire */}
      {Array.isArray(character.learned_spells) && character.learned_spells.length > 0 && (
        <div className="pt-2 border-t border-fantasy-border/40">
          <div className="text-[11px] uppercase font-bold text-indigo-300 tracking-wider mb-2 flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <BookOpen size={13} className="text-indigo-400" />
              <span>Grimoire ({character.learned_spells.length})</span>
            </span>
            <span className="text-[10px] text-gray-500 font-mono">Learned Spells</span>
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
                    <p className="text-[10px] text-gray-400 leading-snug">{sp.description}</p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

    </div>
  );
};

export default CharacterSheet;

