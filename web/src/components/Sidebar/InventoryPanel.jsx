import React, { useState, useMemo } from 'react';
import {
  Shield, Sword, Sparkles, Trash2, BookOpen,
  Coins, Camera, Video, Package, Check, X, HardHat, Footprints, Gift, User, Skull, Search, Lock, Globe
} from 'lucide-react';

const SLOT_ICONS = {
  Weapon: Sword,
  Shield: Shield,
  Armor: Shield,
  Head: HardHat,
  Top: Shield,
  Bottom: Shield,
  Gloves: Sparkles,
  Shoes: Footprints,
  'Accessory 1': Sparkles,
  'Accessory 2': Sparkles,
  'Accessory 3': Sparkles,
  'Accessory 4': Sparkles,
};

const getItemCategory = (item) => {
  const type = (item.type || item.item_type || '').toLowerCase();
  const name = (item.name || '').toLowerCase();
  if (type.includes('weapon') || name.includes('sword') || name.includes('blade') || name.includes('bow') || name.includes('staff')) return 'Weapons';
  if (type.includes('armor') || type.includes('shield') || type.includes('helm') || type.includes('boot')) return 'Armor';
  if (
    type.includes('potion') || type.includes('consumable') || type.includes('scroll') ||
    type.includes('food') || type.includes('drink') || type.includes('spellbook') ||
    name.includes('potion') || name.includes('elixir') || name.includes('tonic') ||
    name.includes('draught') || name.includes('spellbook:') || name.includes('grimoire:') || name.includes('tome:')
  ) return 'Usables';
  if (type.includes('digital') || type.includes('photo') || type.includes('video') || name.includes('photo') || name.includes('selfie')) return 'Digital';
  if (type.includes('quest') || type.includes('key') || type.includes('token') || item.is_key_item) return 'Quest';
  return 'Misc';
};

const isItemUsable = (item) => {
  const cat = getItemCategory(item);
  if (cat === 'Usables' || cat === 'Digital' || cat === 'Quest' || cat === 'Misc') return true;
  const eff = (item.clean_effect || item.effect || '').toLowerCase();
  return eff.includes('restore') || eff.includes('heal') || eff.includes('spellbook_json') || eff.includes('consumable');
};

const getInferredValidSlots = (item) => {
  if (Array.isArray(item.valid_slots) && item.valid_slots.length > 0) {
    return item.valid_slots;
  }
  const type = (item.type || item.item_type || '').toLowerCase();
  const name = (item.name || '').toLowerCase();
  if (type.includes('spellbook') || name.startsWith('spellbook:') || name.startsWith('grimoire:') || name.startsWith('tome:')) return [];
  if (type.includes('weapon') || name.includes('sword') || name.includes('dagger') || name.includes('blade') || name.includes('staff') || name.includes('bow')) return ['Weapon'];
  if (type.includes('shield') || name.includes('shield') || name.includes('buckler')) return ['Shield'];
  if (type.includes('helm') || name.includes('hat') || name.includes('hood') || name.includes('helmet')) return ['Head'];
  if (type.includes('boot') || name.includes('shoes') || name.includes('greaves')) return ['Shoes'];
  if (type.includes('glove') || name.includes('gauntlet') || name.includes('bracer')) return ['Gloves'];
  if (type.includes('armor') || name.includes('chest') || name.includes('cuirass') || name.includes('robe') || name.includes('tunic')) return ['Armor'];
  if (type.includes('top') || name.includes('shirt') || name.includes('jacket') || name.includes('dress')) return ['Top'];
  if (type.includes('bottom') || name.includes('pants') || name.includes('skirt') || name.includes('trousers')) return ['Bottom'];
  if (type.includes('ring') || type.includes('accessory') || name.includes('ring') || name.includes('amulet') || name.includes('necklace') || name.includes('pendant')) {
    return ['Accessory 1', 'Accessory 2', 'Accessory 3', 'Accessory 4'];
  }
  return [];
};

const InventoryPanel = ({ inventoryHook, onRefreshCharacter, onRefreshCodex, sessionId, session }) => {
  const {
    items, equipment, capacity, usedSlots, gold,
    loading, equipItem, unequipSlot, dropItem, useItem
  } = inventoryHook;

  const [activeTab, setActiveTab] = useState('backpack');
  const [filterCat, setFilterCat] = useState('All');
  const [actionInProgress, setActionInProgress] = useState(null);
  const [confirmDropId, setConfirmDropId] = useState(null);
  const [targetPickerItemId, setTargetPickerItemId] = useState(null);
  const [slotPickerItemId, setSlotPickerItemId] = useState(null);
  const [inspectedItemId, setInspectedItemId] = useState(null);
  const [useFeedback, setUseFeedback] = useState(null);

  // Extract present NPCs, companions, and nearby enemies for the inline target picker
  const partyCompanions = (session?.party_npcs || []).map(n => (typeof n === 'string' ? n : n?.name)).filter(Boolean);
  const sceneNpcs = (session?.current_npcs || [])
    .map(n => (typeof n === 'string' ? n : n?.name))
    .filter(n => n && !partyCompanions.includes(n));
  const nearbyEnemies = (session?.nearby_enemies || session?.monsters || [])
    .map(e => (typeof e === 'string' ? e : e?.name))
    .filter(Boolean);

  const handleEquip = async (itemId, targetSlot) => {
    setActionInProgress(itemId);
    setSlotPickerItemId(null);
    setUseFeedback(null);
    try {
      await equipItem(itemId, targetSlot);
      if (onRefreshCharacter) onRefreshCharacter();
    } catch (err) {
      setUseFeedback({ type: 'error', text: err.message || 'Failed to equip item' });
    } finally {
      setActionInProgress(null);
    }
  };

  const handleUnequip = async (slot) => {
    setActionInProgress(slot);
    setUseFeedback(null);
    try {
      await unequipSlot(slot);
      if (onRefreshCharacter) onRefreshCharacter();
    } catch (err) {
      setUseFeedback({ type: 'error', text: err.message || 'Failed to unequip slot' });
    } finally {
      setActionInProgress(null);
    }
  };

  const handleUse = async (itemId, targetType = 'self', targetName = 'self') => {
    if (!useItem) return;
    setActionInProgress(itemId);
    setTargetPickerItemId(null);
    setUseFeedback(null);
    try {
      const res = await useItem(itemId, sessionId, targetType, targetName);
      if (res?.message) {
        setUseFeedback({ type: 'success', text: res.message.replace(/\*\*/g, '') });
      }
      if (onRefreshCharacter) onRefreshCharacter();
      if (onRefreshCodex) onRefreshCodex();
    } catch (err) {
      setUseFeedback({ type: 'error', text: err.message || 'Could not use item' });
    } finally {
      setActionInProgress(null);
    }
  };

  const handleDrop = async (itemId) => {
    setActionInProgress(itemId);
    setUseFeedback(null);
    try {
      await dropItem(itemId);
      setConfirmDropId(null);
      if (onRefreshCharacter) onRefreshCharacter();
    } catch (err) {
      setUseFeedback({ type: 'error', text: err.message || 'Failed to drop item' });
    } finally {
      setActionInProgress(null);
    }
  };

  const categories = ['All', 'Weapons', 'Armor', 'Usables', 'Digital', 'Quest', 'Misc'];

  const backpackItems = items.filter(it => !it.equipped);

  // Group duplicate unequipped items by name + item_type + effect
  const groupedItems = useMemo(() => {
    const map = new Map();
    for (const it of backpackItems) {
      const key = `${it.name || ''}::${it.item_type || it.type || ''}::${it.effect || ''}`;
      if (map.has(key)) {
        const existing = map.get(key);
        existing.count += 1;
        existing.groupedIds.push(it.id);
      } else {
        map.set(key, { ...it, count: 1, groupedIds: [it.id] });
      }
    }
    return Array.from(map.values());
  }, [backpackItems]);

  const filteredItems = groupedItems.filter(it => {
    if (filterCat === 'All') return true;
    return getItemCategory(it) === filterCat;
  });

  const encumbrancePct = Math.min(100, Math.round((usedSlots / Math.max(1, capacity)) * 100));
  const isNearFull = encumbrancePct >= 80;
  const isFull = encumbrancePct >= 100;

  return (
    <div className="bg-black/30 rounded-lg border border-fantasy-border p-4 space-y-4">

      {/* Top Bar: Subtabs & Gold */}
      <div className="flex items-center justify-between border-b border-fantasy-border pb-3">
        <div className="flex items-center gap-1 bg-black/60 p-1 rounded-md border border-fantasy-border/60">
          <button
            onClick={() => setActiveTab('backpack')}
            className={`px-3 py-1 rounded text-xs font-semibold uppercase tracking-wider transition-colors ${
              activeTab === 'backpack'
                ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            Backpack ({backpackItems.length})
          </button>
          <button
            onClick={() => setActiveTab('gear')}
            className={`px-3 py-1 rounded text-xs font-semibold uppercase tracking-wider transition-colors ${
              activeTab === 'gear'
                ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            Equipped Gear
          </button>
        </div>

        <div className="flex items-center gap-1.5 bg-black/50 border border-amber-900/40 px-2.5 py-1 rounded text-amber-300 font-mono text-xs">
          <Coins size={13} className="text-amber-400" />
          <span className="font-bold">{gold}</span>
          <span className="text-[10px] text-amber-500/80">G</span>
        </div>
      </div>

      {/* Item Action Feedback Banner */}
      {useFeedback && (
        <div className={`p-2.5 rounded border text-xs flex items-start justify-between gap-2 ${
          useFeedback.type === 'error'
            ? 'bg-red-950/60 border-red-800/70 text-red-200'
            : 'bg-emerald-950/60 border-emerald-700/70 text-emerald-200'
        }`}>
          <span className="leading-relaxed whitespace-pre-line">{useFeedback.text}</span>
          <button onClick={() => setUseFeedback(null)} className="text-gray-400 hover:text-white shrink-0">
            <X size={13} />
          </button>
        </div>
      )}

      {/* Backpack View */}
      {activeTab === 'backpack' && (
        <div className="space-y-3">

          {/* Encumbrance Bar */}
          <div className="bg-black/40 p-2.5 rounded-md border border-fantasy-border/40">
            <div className="flex justify-between items-center text-xs mb-1">
              <span className="text-gray-400 font-medium flex items-center gap-1">
                <Package size={13} className={isFull ? 'text-red-400' : 'text-fantasy-accent'} />
                <span>Inventory Slots</span>
              </span>
              <span className={`font-mono font-bold text-xs ${isFull ? 'text-red-400' : isNearFull ? 'text-amber-400' : 'text-gray-300'}`}>
                {usedSlots} / {capacity}
              </span>
            </div>
            <div className="h-1.5 w-full bg-black/80 rounded-full overflow-hidden border border-fantasy-border/50">
              <div
                className={`h-full transition-all duration-300 ${
                  isFull ? 'bg-red-500' : isNearFull ? 'bg-amber-500' : 'bg-fantasy-accent'
                }`}
                style={{ width: `${encumbrancePct}%` }}
              />
            </div>
          </div>

          {/* Category Filter Pills */}
          <div className="flex flex-wrap gap-1">
            {categories.map(cat => (
              <button
                key={cat}
                onClick={() => setFilterCat(cat)}
                className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                  filterCat === cat
                    ? 'bg-fantasy-border text-fantasy-accent border border-fantasy-accent/50'
                    : 'bg-black/40 text-gray-400 hover:text-gray-200 border border-fantasy-border/30'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>

          {/* Items List */}
          <div className="space-y-1.5 max-h-96 overflow-y-auto custom-scrollbar pr-1">
            {loading && items.length === 0 ? (
              <p className="text-xs text-gray-500 italic text-center py-6">Checking pack...</p>
            ) : filteredItems.length === 0 ? (
              <div className="text-center py-8 text-gray-500 border border-dashed border-fantasy-border/50 rounded-md">
                <Package size={24} className="mx-auto mb-1.5 opacity-40" />
                <p className="text-xs">No items in this category.</p>
              </div>
            ) : (
              filteredItems.map(item => {
                const category = getItemCategory(item);
                const validSlots = getInferredValidSlots(item);
                const usable = isItemUsable(item);
                const isSpellbook = (item.item_type || '').toLowerCase() === 'spellbook' || (item.name || '').toLowerCase().match(/^(spellbook|grimoire|tome):/);
                const isDigital = category === 'Digital';
                const isKeyItem = Boolean(item.is_key_item || category === 'Quest');
                const isDirectOnly = isSpellbook || isDigital;
                const isBusy = actionInProgress === item.id;
                const showTargetPicker = targetPickerItemId === item.id;
                const showSlotPicker = slotPickerItemId === item.id;
                const isInspected = inspectedItemId === item.id;
                const cleanEffect = item.clean_effect !== undefined ? item.clean_effect : (item.effect && !item.effect.startsWith('[') ? item.effect : '');
                const inspectData = item.inspect_data || {};
                const statDeltas = inspectData.stat_deltas || inspectData.comparison || inspectData.vs_equipped || {};

                return (
                  <div
                    key={item.id}
                    className="bg-black/50 border border-fantasy-border/60 hover:border-fantasy-border rounded p-2.5 transition-colors space-y-2"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          {isDigital ? (
                            (item.name || '').toLowerCase().includes('video')
                              ? <Video size={13} className="text-cyan-400 shrink-0" />
                              : <Camera size={13} className="text-pink-400 shrink-0" />
                          ) : isSpellbook ? (
                            <BookOpen size={13} className="text-indigo-400 shrink-0" />
                          ) : category === 'Weapons' ? (
                            <Sword size={13} className="text-amber-400 shrink-0" />
                          ) : category === 'Armor' ? (
                            <Shield size={13} className="text-blue-400 shrink-0" />
                          ) : (
                            <Sparkles size={13} className="text-purple-400 shrink-0" />
                          )}
                          <span className="font-medium text-xs text-gray-200 truncate">{item.name}</span>
                          {item.count > 1 && (
                            <span className="text-[10px] font-mono font-bold px-1.5 py-0.2 bg-fantasy-accent/20 text-fantasy-accent rounded border border-fantasy-accent/40">
                              x{item.count}
                            </span>
                          )}
                          {isKeyItem && (
                            <span className="text-[9px] px-1.5 py-0.2 bg-amber-950/80 text-amber-300 rounded border border-amber-700/60 font-bold flex items-center gap-0.5">
                              🔒 Key Item
                            </span>
                          )}
                          {item.slot_cost === 0 && (
                            <span className="text-[9px] px-1 py-0.2 bg-cyan-950 text-cyan-300 rounded border border-cyan-800">
                              0-Slot
                            </span>
                          )}
                        </div>

                        {cleanEffect && (
                          <p className="text-[11px] text-gray-400 mt-0.5 truncate">{cleanEffect}</p>
                        )}
                      </div>

                      {/* Item Actions */}
                      <div className="flex items-center gap-1 shrink-0">
                        <button
                          type="button"
                          onClick={() => setInspectedItemId(isInspected ? null : item.id)}
                          className={`px-1.5 py-1 rounded text-[10px] font-bold border transition-colors ${
                            isInspected
                              ? 'bg-cyan-950/70 text-cyan-200 border-cyan-600/60'
                              : 'bg-black/60 hover:bg-neutral-800 text-gray-400 hover:text-gray-200 border-fantasy-border/60'
                          }`}
                          title="Inspect Item Details & Stat Comparison"
                        >
                          🔍 Inspect
                        </button>

                        {usable && (
                          <button
                            onClick={() => {
                              if (isDirectOnly) {
                                handleUse(item.id, 'self', 'self');
                              } else {
                                setTargetPickerItemId(showTargetPicker ? null : item.id);
                              }
                            }}
                            disabled={isBusy}
                            className="px-2 py-1 bg-emerald-900/40 hover:bg-emerald-800/60 text-emerald-300 border border-emerald-700/50 rounded text-[10px] font-bold uppercase transition-colors disabled:opacity-50"
                            title={isSpellbook ? 'Study Spellbook' : isDigital ? 'Inspect Media' : 'Use or Gift Item'}
                          >
                            {isBusy ? '...' : isSpellbook ? 'Study' : isDigital ? 'View' : 'Use'}
                          </button>
                        )}

                        {validSlots.length > 0 && (
                          <button
                            onClick={() => {
                              if (validSlots.length === 1) {
                                handleEquip(item.id, validSlots[0]);
                              } else {
                                setSlotPickerItemId(showSlotPicker ? null : item.id);
                              }
                            }}
                            disabled={isBusy}
                            className="px-2 py-1 bg-fantasy-accent/15 hover:bg-fantasy-accent/25 text-fantasy-accent border border-fantasy-accent/40 rounded text-[10px] font-bold uppercase transition-colors disabled:opacity-50"
                            title={validSlots.length === 1 ? `Equip into ${validSlots[0]}` : 'Choose Equipment Slot'}
                          >
                            {isBusy ? '...' : 'Equip'}
                          </button>
                        )}

                        {/* Drop Button / Confirmation (Disabled on Key Items) */}
                        {!isKeyItem && (
                          confirmDropId === item.id ? (
                            <div className="flex items-center gap-0.5">
                              <button
                                onClick={() => handleDrop(item.id)}
                                disabled={isBusy}
                                className="p-1 bg-red-900/60 hover:bg-red-800 text-red-300 rounded"
                                title="Confirm Drop"
                              >
                                <Check size={12} />
                              </button>
                              <button
                                onClick={() => setConfirmDropId(null)}
                                className="p-1 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded"
                                title="Cancel"
                              >
                                <X size={12} />
                              </button>
                            </div>
                          ) : (
                            <button
                              onClick={() => setConfirmDropId(item.id)}
                              className="p-1 text-gray-500 hover:text-red-400 transition-colors"
                              title="Drop Item"
                            >
                              <Trash2 size={12} />
                            </button>
                          )
                        )}
                      </div>
                    </div>

                    {/* Multi-Slot Equip Picker Pills */}
                    {showSlotPicker && validSlots.length > 1 && (
                      <div className="pt-2 border-t border-fantasy-border/50 flex flex-wrap gap-1.5 items-center bg-black/40 p-2 rounded">
                        <span className="text-[10px] uppercase tracking-wider text-gray-400 font-bold mr-1">Equip Slot:</span>
                        {validSlots.map((slotName) => (
                          <button
                            key={slotName}
                            type="button"
                            onClick={() => handleEquip(item.id, slotName)}
                            className="px-2 py-0.5 rounded bg-fantasy-accent/20 hover:bg-fantasy-accent/35 text-fantasy-accent border border-fantasy-accent/50 text-[10px] font-bold transition-colors"
                          >
                            {slotName}
                          </button>
                        ))}
                      </div>
                    )}

                    {/* Inline Inspector Drawer */}
                    {isInspected && (
                      <div className="pt-2 border-t border-fantasy-border/50 bg-black/60 p-2.5 rounded space-y-2 text-[11px]">
                        <div className="flex items-center justify-between text-gray-300">
                          <span className="font-bold text-cyan-300 uppercase text-[10px] tracking-wider">
                            🔍 Item Inspector — {item.item_type || category}
                          </span>
                          {inspectData.slot && (
                            <span className="text-[10px] font-mono text-gray-400">Slot: {inspectData.slot}</span>
                          )}
                        </div>

                        {inspectData.stats_summary ? (
                          <p className="text-gray-200 font-mono text-[11px] bg-black/50 p-1.5 rounded border border-fantasy-border/40">
                            {inspectData.stats_summary}
                          </p>
                        ) : cleanEffect ? (
                          <p className="text-gray-300">{cleanEffect}</p>
                        ) : (
                          <p className="text-gray-500 italic">No additional stat modifiers recorded.</p>
                        )}

                        {isSpellbook && inspectData.arcane_compatible === false && (
                          <div className="p-1.5 rounded bg-amber-950/60 border border-amber-700/60 text-amber-200 text-[10px]">
                            ⚠️ Your class archetype is not naturally attuned to arcane spellcraft (higher INT required).
                          </div>
                        )}

                        {/* 🔄 vs Equipped Stat Delta Comparison Table */}
                        {Object.keys(statDeltas).length > 0 && (
                          <div className="space-y-1 pt-1">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block">
                              🔄 vs Equipped Comparison
                            </span>
                            <div className="grid grid-cols-2 sm:grid-cols-3 gap-1">
                              {Object.entries(statDeltas).map(([statName, deltaVal]) => {
                                const num = Number(deltaVal);
                                if (Number.isNaN(num) || num === 0) return null;
                                const isUp = num > 0;
                                return (
                                  <div
                                    key={statName}
                                    className={`px-2 py-1 rounded border font-mono text-[10px] flex items-center justify-between ${
                                      isUp
                                        ? 'bg-emerald-950/50 border-emerald-700/50 text-emerald-300'
                                        : 'bg-red-950/50 border-red-800/50 text-red-300'
                                    }`}
                                  >
                                    <span className="uppercase">{statName}</span>
                                    <span className="font-bold">
                                      {isUp ? `🔺 +${num}` : `🔻 ${num}`}
                                    </span>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Inline Target Picker Popover */}
                    {showTargetPicker && (
                      <div className="pt-2 border-t border-fantasy-border/50 flex flex-wrap gap-1.5 items-center bg-black/40 p-2 rounded">
                        <span className="text-[10px] uppercase tracking-wider text-gray-400 font-bold mr-1">Target:</span>
                        <button
                          onClick={() => handleUse(item.id, 'self', 'self')}
                          className="flex items-center gap-1 px-2 py-1 rounded bg-emerald-950/60 hover:bg-emerald-900 border border-emerald-700/60 text-emerald-200 text-[10px] font-semibold"
                        >
                          <User size={10} /> Yourself
                        </button>
                        {partyCompanions.map(name => (
                          <button
                            key={`comp-${name}`}
                            onClick={() => handleUse(item.id, 'companion', name)}
                            className="flex items-center gap-1 px-2 py-1 rounded bg-cyan-950/60 hover:bg-cyan-900 border border-cyan-700/60 text-cyan-200 text-[10px] font-semibold"
                          >
                            <Sparkles size={10} /> {name} (Party)
                          </button>
                        ))}
                        {sceneNpcs.map(name => (
                          <button
                            key={`npc-${name}`}
                            onClick={() => handleUse(item.id, 'npc', name)}
                            className="flex items-center gap-1 px-2 py-1 rounded bg-pink-950/60 hover:bg-pink-900 border border-pink-700/60 text-pink-200 text-[10px] font-semibold"
                          >
                            🎁 Give Gift
                          </button>
                        ))}
                        {nearbyEnemies.map(name => (
                          <button
                            key={`enemy-${name}`}
                            onClick={() => handleUse(item.id, 'monster', name)}
                            className="flex items-center gap-1 px-2 py-1 rounded bg-red-950/60 hover:bg-red-900 border border-red-700/60 text-red-200 text-[10px] font-semibold"
                          >
                            <Skull size={10} /> Throw: {name}
                          </button>
                        ))}
                        <button
                          onClick={() => handleUse(item.id, 'ground', 'ground')}
                          className="flex items-center gap-1 px-2 py-1 rounded bg-amber-950/60 hover:bg-amber-900 border border-amber-700/60 text-amber-200 text-[10px] font-semibold"
                        >
                          <Globe size={10} /> 🌐 The Ground / Environment
                        </button>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* Equipped Gear View */}
      {activeTab === 'gear' && (
        <div className="space-y-2">
          {Object.entries(equipment || {}).map(([slot, equippedItem]) => {
            const Icon = SLOT_ICONS[slot] || Shield;
            const isBusy = actionInProgress === slot;
            const eqCleanEffect = equippedItem?.clean_effect !== undefined ? equippedItem.clean_effect : equippedItem?.effect;

            return (
              <div
                key={slot}
                className="bg-black/50 border border-fantasy-border/60 rounded p-2.5 flex items-center justify-between gap-2"
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <div className={`w-8 h-8 rounded border flex items-center justify-center shrink-0 ${
                    equippedItem
                      ? 'bg-fantasy-dark border-fantasy-accent/50 text-fantasy-accent'
                      : 'bg-black/60 border-fantasy-border/40 text-gray-600'
                  }`}>
                    <Icon size={16} />
                  </div>
                  <div className="min-w-0">
                    <span className="text-[10px] uppercase font-bold text-gray-500 tracking-wider block">{slot}</span>
                    {equippedItem ? (
                      <div>
                        <span className="text-xs font-semibold text-gray-200 block truncate">{equippedItem.name}</span>
                        {eqCleanEffect && (
                          <span className="text-[10px] text-gray-400 block truncate">{eqCleanEffect}</span>
                        )}
                      </div>
                    ) : (
                      <span className="text-xs text-gray-600 italic">Empty Slot</span>
                    )}
                  </div>
                </div>

                {equippedItem && (
                  <button
                    onClick={() => handleUnequip(slot)}
                    disabled={isBusy}
                    className="px-2 py-1 bg-black/60 hover:bg-red-950/40 text-gray-400 hover:text-red-300 border border-fantasy-border hover:border-red-800/60 rounded text-[10px] font-bold uppercase transition-colors shrink-0 disabled:opacity-50"
                  >
                    {isBusy ? '...' : 'Unequip'}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

    </div>
  );
};

export default InventoryPanel;
