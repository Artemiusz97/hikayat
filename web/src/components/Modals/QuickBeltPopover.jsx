import React, { useState } from 'react';
import { Sparkles, Zap, Heart, Shield, X, Package, Loader2 } from 'lucide-react';

const isQuickBeltItem = (item) => {
  if (!item) return false;
  const type = String(item.type || item.item_type || '').toLowerCase();
  const name = String(item.name || '').toLowerCase();
  const eff = String(item.clean_effect || item.effect || '').toLowerCase();

  return (
    type.includes('potion') ||
    type.includes('consumable') ||
    type.includes('scroll') ||
    type.includes('food') ||
    type.includes('drink') ||
    type.includes('remedy') ||
    type.includes('tonic') ||
    name.includes('potion') ||
    name.includes('elixir') ||
    name.includes('tonic') ||
    name.includes('draught') ||
    name.includes('remedy') ||
    name.includes('ration') ||
    name.includes('snack') ||
    name.includes('bread') ||
    name.includes('tea') ||
    eff.includes('heal') ||
    eff.includes('restore') ||
    eff.includes('hp') ||
    eff.includes('mp')
  );
};

const QuickBeltPopover = ({
  isOpen,
  onClose,
  inventoryHook,
  inCombat,
  onAction,
  onRefreshCharacter,
  processing
}) => {
  const [usingId, setUsingId] = useState(null);
  const [feedback, setFeedback] = useState(null);

  if (!isOpen) return null;

  const items = inventoryHook?.items || [];
  const quickItems = items.filter(isQuickBeltItem);

  const handleUse = async (item) => {
    if (!item || usingId || processing) return;
    setUsingId(item.id);
    setFeedback(null);

    try {
      if (inCombat) {
        // In combat: Consuming an item submits a turn action
        await onAction({
          custom_action_text: `I use ${item.name}.`,
          item_id: item.id
        });
        onClose();
      } else {
        // Outside combat: Instant stat restore without advancing story turn
        if (inventoryHook?.useItem) {
          const res = await inventoryHook.useItem(item.id);
          if (onRefreshCharacter) {
            onRefreshCharacter();
          }
          setFeedback({ type: 'success', text: res?.message || `Used ${item.name}` });
          setTimeout(() => {
            setFeedback(null);
          }, 2000);
        }
      }
    } catch (err) {
      setFeedback({ type: 'error', text: err?.message || 'Failed to use item' });
    } finally {
      setUsingId(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 bg-black/60 backdrop-blur-sm animate-in fade-in duration-150">
      <div
        className="fixed inset-0"
        onClick={onClose}
      />
      <div className="relative w-full max-w-sm bg-fantasy-panel border border-fantasy-border/90 rounded-xl shadow-2xl p-3.5 space-y-3 z-10">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-fantasy-border/60 pb-2">
          <div className="flex items-center gap-2">
            <span className="text-base">🧪</span>
            <div>
              <h3 className="font-rpg font-bold text-fantasy-accent text-sm leading-none">
                Quick-Use Belt
              </h3>
              <p className="text-[10px] text-gray-400 mt-0.5">
                {inCombat ? 'Consuming an item takes a combat action' : 'Instant recovery out of combat'}
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

        {/* Feedback Message */}
        {feedback && (
          <div
            className={`p-2 rounded text-xs font-semibold leading-tight ${
              feedback.type === 'error'
                ? 'bg-red-950/80 border border-red-700/80 text-red-200'
                : 'bg-emerald-950/80 border border-emerald-700/80 text-emerald-200'
            }`}
          >
            {feedback.text}
          </div>
        )}

        {/* Item List */}
        <div className="max-h-60 overflow-y-auto custom-scrollbar space-y-1.5 pr-0.5">
          {quickItems.length === 0 ? (
            <div className="p-4 text-center text-gray-400 text-xs flex flex-col items-center gap-1.5">
              <Package size={22} className="text-gray-500 opacity-60" />
              <span>No quick consumables or potions in your backpack.</span>
            </div>
          ) : (
            quickItems.map((item, idx) => {
              const isUsing = usingId === item.id;
              const eff = item.clean_effect || item.effect || '';
              const isHeal = eff.toLowerCase().includes('heal') || eff.toLowerCase().includes('hp');
              const isMp = eff.toLowerCase().includes('mp') || eff.toLowerCase().includes('mana');

              return (
                <div
                  key={item.id || idx}
                  className="flex items-center justify-between p-2 rounded-lg bg-black/50 border border-fantasy-border/70 hover:border-fantasy-accent/60 transition-colors gap-2"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <div className="w-7 h-7 rounded bg-black/60 border border-fantasy-border flex items-center justify-center shrink-0">
                      {isHeal ? (
                        <Heart size={14} className="text-rose-400" />
                      ) : isMp ? (
                        <Zap size={14} className="text-blue-400" />
                      ) : (
                        <Sparkles size={14} className="text-amber-400" />
                      )}
                    </div>
                    <div className="min-w-0">
                      <div className="text-xs font-bold text-gray-200 truncate">
                        {item.name}
                      </div>
                      {eff && (
                        <div className="text-[10px] text-gray-400 truncate font-mono">
                          {eff}
                        </div>
                      )}
                    </div>
                  </div>

                  <button
                    type="button"
                    disabled={isUsing || processing}
                    onClick={() => handleUse(item)}
                    className="shrink-0 px-2.5 py-1 rounded bg-amber-500/20 hover:bg-amber-500/35 border border-amber-500/50 text-amber-300 font-mono text-[11px] font-bold flex items-center gap-1 transition-all disabled:opacity-40"
                  >
                    {isUsing ? (
                      <Loader2 size={12} className="animate-spin text-amber-300" />
                    ) : (
                      <span>Use</span>
                    )}
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};

export default QuickBeltPopover;
