import React, { useState } from 'react';
import { Gift, User, Package, X, Check, Loader2 } from 'lucide-react';

const GiveGiftModal = ({
  isOpen,
  onClose,
  session,
  inventoryHook,
  onAction,
  processing
}) => {
  const [selectedNpc, setSelectedNpc] = useState('');
  const [selectedItemId, setSelectedItemId] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  if (!isOpen) return null;

  const npcs = (session?.current_npcs || []).map((n) =>
    typeof n === 'string' ? n : n?.name
  ).filter(Boolean);

  const items = (inventoryHook?.items || []).filter((item) => {
    // Exclude basic key items that shouldn't be gifted away accidentally
    const type = String(item.type || item.item_type || '').toLowerCase();
    return !type.includes('key');
  });

  // Default to first NPC if none selected
  const activeNpc = selectedNpc || (npcs.length > 0 ? npcs[0] : '');

  const selectedItem = items.find((i) => i.id === selectedItemId);

  const handleGive = async () => {
    if (!activeNpc || !selectedItem || submitting || processing) return;
    setSubmitting(true);
    try {
      await onAction({
        custom_action_text: `I offer ${selectedItem.name} as a gift to ${activeNpc}.`,
        intent: 'gift_offer',
        target_npc: activeNpc,
        item_id: selectedItem.id
      });
      onClose();
    } catch (err) {
      console.error('Failed to give gift:', err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 bg-black/70 backdrop-blur-sm animate-in fade-in duration-150">
      <div className="fixed inset-0" onClick={onClose} />
      <div className="relative w-full max-w-md bg-fantasy-panel border border-fantasy-border/90 rounded-xl shadow-2xl p-4 space-y-3.5 z-10">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-fantasy-border/60 pb-2.5">
          <div className="flex items-center gap-2">
            <span className="text-lg">🎁</span>
            <div>
              <h3 className="font-rpg font-bold text-fantasy-accent text-sm leading-none">
                Give Gift / Item
              </h3>
              <p className="text-[10px] text-gray-400 mt-0.5">
                Offer an item to an NPC in your current scene to deepen rapport and affinity
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 text-gray-400 hover:text-gray-200 rounded hover:bg-white/10 transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Step 1: Select Recipient */}
        <div className="space-y-1.5">
          <label className="text-[11px] font-bold uppercase tracking-wider text-gray-300 flex items-center gap-1.5">
            <User size={13} className="text-amber-400" />
            <span>Select Recipient</span>
          </label>
          <div className="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto custom-scrollbar">
            {npcs.length === 0 ? (
              <span className="text-xs text-gray-400 italic">No NPCs present in this scene.</span>
            ) : (
              npcs.map((npc) => (
                <button
                  key={npc}
                  type="button"
                  onClick={() => setSelectedNpc(npc)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-semibold border transition-all ${
                    activeNpc === npc
                      ? 'bg-amber-500/25 border-amber-400 text-amber-200 shadow-sm'
                      : 'bg-black/40 border-fantasy-border text-gray-300 hover:border-gray-500'
                  }`}
                >
                  {npc}
                </button>
              ))
            )}
          </div>
        </div>

        {/* Step 2: Select Item from Inventory */}
        <div className="space-y-1.5">
          <label className="text-[11px] font-bold uppercase tracking-wider text-gray-300 flex items-center gap-1.5">
            <Package size={13} className="text-amber-400" />
            <span>Select Item to Gift</span>
          </label>
          <div className="max-h-48 overflow-y-auto custom-scrollbar space-y-1 pr-1 border border-fantasy-border/60 rounded-lg p-1.5 bg-black/40">
            {items.length === 0 ? (
              <div className="p-4 text-center text-gray-400 text-xs">
                Your inventory is currently empty.
              </div>
            ) : (
              items.map((item) => {
                const isSelected = selectedItemId === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setSelectedItemId(item.id)}
                    className={`w-full flex items-center justify-between p-2 rounded-md text-left transition-all ${
                      isSelected
                        ? 'bg-amber-950/60 border border-amber-400 text-amber-100 ring-1 ring-amber-400/50'
                        : 'bg-black/30 border border-transparent hover:border-fantasy-border text-gray-300 hover:text-white'
                    }`}
                  >
                    <div className="min-w-0">
                      <div className="text-xs font-bold truncate">{item.name}</div>
                      {item.type && (
                        <div className="text-[10px] text-gray-400 font-mono capitalize">
                          {item.type}
                        </div>
                      )}
                    </div>
                    {isSelected && <Check size={14} className="text-amber-400 shrink-0 ml-1.5" />}
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-between pt-2 border-t border-fantasy-border/60">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold text-gray-400 hover:text-white hover:bg-white/5 transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!activeNpc || !selectedItem || submitting || processing}
            onClick={handleGive}
            className="px-4 py-1.5 rounded-lg bg-fantasy-accent text-fantasy-dark font-bold text-xs hover:bg-fantasy-accent-hover transition-all flex items-center gap-1.5 shadow-md disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {submitting ? (
              <>
                <Loader2 size={13} className="animate-spin text-fantasy-dark" />
                <span>Offering Gift...</span>
              </>
            ) : (
              <>
                <Gift size={13} />
                <span>Give to {activeNpc || 'NPC'}</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

export default GiveGiftModal;
