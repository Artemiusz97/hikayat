import React, { useState, useEffect, useCallback } from 'react';
import { X, ShoppingBag, Coins, Sparkles, Tag, MessageCircle, Package, Handshake, Ear, CheckCircle2 } from 'lucide-react';
import { apiCall } from '../../api/client';

const MerchantModal = ({ isOpen, onClose, session, user, onTransactionComplete, onRefreshCodex }) => {
  const [shop, setShop] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('buy'); // 'buy' | 'sell' | 'rumors'
  const [selectedStoreType, setSelectedStoreType] = useState(null);
  const [busyKey, setBusyKey] = useState(null);
  const [feedback, setFeedback] = useState(null);

  const loadShop = useCallback(async (overrideType = null) => {
    if (!session?.id || !user?.user_id) return;
    setLoading(true);
    try {
      const mType = overrideType || selectedStoreType;
      const query = mType
        ? `/api/merchant/${session.id}?user_id=${user.user_id}&merchant_type=${encodeURIComponent(mType)}`
        : `/api/merchant/${session.id}?user_id=${user.user_id}`;
      const data = await apiCall(query);
      setShop(data);
      if (data?.merchant_type) {
        setSelectedStoreType(data.merchant_type);
      }
    } catch (err) {
      setFeedback({ type: 'error', text: err.message || 'Failed to load merchant wares' });
    } finally {
      setLoading(false);
    }
  }, [session?.id, user?.user_id, selectedStoreType]);

  useEffect(() => {
    if (isOpen) {
      setFeedback(null);
      loadShop();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSwitchStore = async (storeType) => {
    setSelectedStoreType(storeType);
    setFeedback(null);
    await loadShop(storeType);
  };

  const handleBuy = async (itemName) => {
    setBusyKey(`buy:${itemName}`);
    setFeedback(null);
    try {
      const res = await apiCall('/api/merchant/buy', {
        method: 'POST',
        body: JSON.stringify({
          session_id: session.id,
          user_id: user.user_id,
          item_name: itemName,
          merchant_type: shop?.merchant_type || selectedStoreType
        })
      });
      setFeedback({ type: 'success', text: `Purchased ${res.item_name} for ${res.price_paid}G!` });
      await loadShop(shop?.merchant_type || selectedStoreType);
      if (onTransactionComplete) onTransactionComplete();
    } catch (err) {
      setFeedback({ type: 'error', text: err.message || 'Purchase failed' });
    } finally {
      setBusyKey(null);
    }
  };

  const handleSell = async (item) => {
    setBusyKey(`sell:${item.id}`);
    setFeedback(null);
    try {
      const res = await apiCall('/api/merchant/sell', {
        method: 'POST',
        body: JSON.stringify({
          session_id: session.id,
          user_id: user.user_id,
          item_id: item.id
        })
      });
      setFeedback({ type: 'success', text: `Sold ${res.item_name} for ${res.gold_earned}G!` });
      await loadShop(shop?.merchant_type || selectedStoreType);
      if (onTransactionComplete) onTransactionComplete();
    } catch (err) {
      setFeedback({ type: 'error', text: err.message || 'Sale failed' });
    } finally {
      setBusyKey(null);
    }
  };

  const handleHaggle = async () => {
    setBusyKey('haggle');
    setFeedback(null);
    try {
      const res = await apiCall('/api/merchant/haggle', {
        method: 'POST',
        body: JSON.stringify({
          session_id: session.id,
          user_id: user.user_id
        })
      });
      setFeedback({
        type: res.haggle_succeeded ? 'success' : 'error',
        text: res.message || (res.haggle_succeeded ? 'Haggle succeeded!' : 'Haggle failed.')
      });
      await loadShop(shop?.merchant_type || selectedStoreType);
    } catch (err) {
      setFeedback({ type: 'error', text: err.message || 'Haggle attempt failed' });
    } finally {
      setBusyKey(null);
    }
  };

  const handleRevealRumor = async (idx) => {
    setBusyKey(`rumor:${idx}`);
    setFeedback(null);
    try {
      const res = await apiCall('/api/merchant/rumor', {
        method: 'POST',
        body: JSON.stringify({
          session_id: session.id,
          user_id: user.user_id,
          rumor_index: idx
        })
      });
      setFeedback({
        type: res.rumor_succeeded ? 'success' : 'error',
        text: res.message || 'Rumor investigated.'
      });
      await loadShop(shop?.merchant_type || selectedStoreType);
      if (res.rumor_succeeded && onRefreshCodex) {
        onRefreshCodex();
      }
    } catch (err) {
      setFeedback({ type: 'error', text: err.message || 'Failed to investigate rumor' });
    } finally {
      setBusyKey(null);
    }
  };

  const haggleLeft = shop?.haggle_attempts_left ?? Math.max(0, 3 - (shop?.haggle_attempts || 0));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="fixed inset-0 bg-black/80 backdrop-blur-sm" onClick={onClose} />

      <div className="relative w-full max-w-2xl bg-fantasy-panel border border-fantasy-border rounded-xl shadow-2xl overflow-hidden z-10 flex flex-col max-h-[88vh]">
        {/* Header */}
        <div className="p-4 border-b border-fantasy-border bg-black/50 flex items-center justify-between">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="p-2 rounded-lg bg-amber-500/15 border border-amber-500/40 text-amber-400 shrink-0">
              <ShoppingBag size={18} />
            </div>
            <div className="min-w-0">
              <h3 className="font-rpg font-bold text-base text-fantasy-accent truncate">
                {shop?.merchant_name || 'Merchant Emporium'}
              </h3>
              <p className="text-xs text-gray-400 line-clamp-1">
                {shop?.merchant_description || 'Browse local wares, trade equipment, or listen for rumors.'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <div className="flex items-center gap-1 bg-black/60 border border-amber-800/50 px-2.5 py-1 rounded text-amber-300 font-mono text-xs">
              <Coins size={13} className="text-amber-400" />
              <span className="font-bold">{shop?.gold ?? 0}G</span>
            </div>
            <button onClick={onClose} className="p-1 text-gray-400 hover:text-white">
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Specialist Store Directory Switcher */}
        {Array.isArray(shop?.available_stores) && shop.available_stores.length > 1 && (
          <div className="px-4 py-2 bg-black/60 border-b border-fantasy-border/70 flex items-center gap-1.5 overflow-x-auto custom-scrollbar">
            <span className="text-[10px] uppercase tracking-wider font-bold text-gray-500 mr-1 shrink-0">
              Bazaar Stalls:
            </span>
            {shop.available_stores.map((st) => {
              const isSelected = (shop?.merchant_type || selectedStoreType) === st.type;
              return (
                <button
                  key={st.type}
                  onClick={() => handleSwitchStore(st.type)}
                  disabled={loading}
                  className={`px-2.5 py-1 rounded text-[11px] font-semibold flex items-center gap-1 shrink-0 border transition-colors ${
                    isSelected
                      ? 'bg-amber-500/20 border-amber-500/60 text-amber-300'
                      : 'bg-black/40 border-fantasy-border/60 text-gray-400 hover:text-gray-200 hover:border-gray-600'
                  }`}
                >
                  <span>{st.emoji || '🛍️'}</span>
                  <span>{st.title}</span>
                </button>
              );
            })}
          </div>
        )}

        {/* Sub-Tabs, Haggle Button & Charisma Discount Pill */}
        <div className="px-4 py-2 bg-black/40 border-b border-fantasy-border flex flex-wrap items-center justify-between gap-2">
          <div className="flex gap-1">
            {[
              { id: 'buy', label: `Buy Wares (${shop?.stock?.length || 0})` },
              { id: 'sell', label: `Sell Pack (${shop?.sellable_items?.length || 0})` },
              { id: 'rumors', label: `Rumors (${shop?.rumors?.length || 0})` }
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-3 py-1 rounded text-xs font-semibold uppercase tracking-wider transition-colors ${
                  activeTab === tab.id
                    ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40'
                    : 'text-gray-400 hover:text-gray-200'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            {shop?.discount_pct > 0 && (
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950/70 text-emerald-300 border border-emerald-700/50 flex items-center gap-1">
                <Tag size={10} /> -{shop.discount_pct}% Off
              </span>
            )}

            <button
              onClick={handleHaggle}
              disabled={haggleLeft <= 0 || busyKey === 'haggle' || loading}
              title="Attempt a Charisma + Luck check for an extra -10% discount"
              className="px-2.5 py-1 rounded bg-purple-950/60 hover:bg-purple-900/70 text-purple-200 border border-purple-700/60 text-[11px] font-semibold flex items-center gap-1 disabled:opacity-40 transition-colors"
            >
              <Handshake size={12} className="text-purple-300" />
              <span>{busyKey === 'haggle' ? 'Haggling...' : `Haggle (${haggleLeft}/3)`}</span>
            </button>
          </div>
        </div>

        {/* Feedback Banner */}
        {feedback && (
          <div className={`mx-4 mt-3 p-2.5 rounded border text-xs flex items-center justify-between ${
            feedback.type === 'error'
              ? 'bg-red-950/60 border-red-800 text-red-200'
              : 'bg-emerald-950/60 border-emerald-700 text-emerald-200'
          }`}>
            <span>{feedback.text}</span>
            <button onClick={() => setFeedback(null)} className="text-gray-400 hover:text-white">
              <X size={13} />
            </button>
          </div>
        )}

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto custom-scrollbar p-4 space-y-2.5">
          {loading ? (
            <div className="text-center py-12 text-gray-400 text-xs animate-pulse">
              Appraising merchant stock...
            </div>
          ) : activeTab === 'buy' ? (
            (shop?.stock || []).length === 0 ? (
              <div className="text-center py-10 text-gray-500 border border-dashed border-fantasy-border/50 rounded-lg">
                <Package size={24} className="mx-auto mb-1.5 opacity-40" />
                <p className="text-xs">The merchant is currently sold out.</p>
              </div>
            ) : (
              (shop?.stock || []).map((item, idx) => {
                const price = item.final_price ?? item.price ?? 15;
                const canAfford = (shop?.gold ?? 0) >= price;
                const isBuying = busyKey === `buy:${item.name}`;

                return (
                  <div
                    key={`${item.name}-${idx}`}
                    className="bg-black/50 border border-fantasy-border/70 rounded-lg p-3 flex items-center justify-between gap-3"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-sm text-gray-100 truncate">{item.name}</span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-black/70 text-gray-400 border border-fantasy-border font-mono">
                          {item.item_type || 'Item'}
                        </span>
                        {item.quantity > 1 && (
                          <span className="text-[10px] font-mono text-amber-400">x{item.quantity}</span>
                        )}
                      </div>
                      {item.description && (
                        <p className="text-xs text-gray-400 mt-1 leading-snug">{item.description}</p>
                      )}
                    </div>

                    <button
                      onClick={() => handleBuy(item.name)}
                      disabled={!canAfford || isBuying}
                      className="px-3 py-1.5 rounded bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/50 text-xs font-bold font-mono flex items-center gap-1.5 shrink-0 disabled:opacity-40 transition-colors"
                    >
                      <Coins size={12} />
                      <span>{isBuying ? '...' : `${price}G`}</span>
                    </button>
                  </div>
                );
              })
            )
          ) : activeTab === 'sell' ? (
            (shop?.sellable_items || []).length === 0 ? (
              <div className="text-center py-10 text-gray-500 border border-dashed border-fantasy-border/50 rounded-lg">
                <Package size={24} className="mx-auto mb-1.5 opacity-40" />
                <p className="text-xs">No unequipped sellable items in your pack.</p>
              </div>
            ) : (
              (shop?.sellable_items || []).map(item => {
                const isSelling = busyKey === `sell:${item.id}`;
                return (
                  <div
                    key={item.id}
                    className="bg-black/50 border border-fantasy-border/70 rounded-lg p-3 flex items-center justify-between gap-3"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-sm text-gray-200 truncate">{item.name}</span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-black/70 text-gray-400 border border-fantasy-border font-mono">
                          {item.item_type || 'Item'}
                        </span>
                      </div>
                      {item.effect && !item.effect.startsWith('[') && (
                        <p className="text-xs text-gray-400 mt-1 truncate">{item.effect}</p>
                      )}
                    </div>

                    <button
                      onClick={() => handleSell(item)}
                      disabled={isSelling}
                      className="px-3 py-1.5 rounded bg-emerald-900/40 hover:bg-emerald-800/60 text-emerald-300 border border-emerald-700/50 text-xs font-bold font-mono flex items-center gap-1 shrink-0 disabled:opacity-40 transition-colors"
                    >
                      <Coins size={12} />
                      <span>{isSelling ? '...' : `Sell +${item.sell_price}G`}</span>
                    </button>
                  </div>
                );
              })
            )
          ) : (
            (shop?.rumors || []).length === 0 ? (
              <p className="text-center py-10 text-xs text-gray-500 italic">The merchant has no rumors to share right now.</p>
            ) : (
              (shop?.rumors || []).map((r, idx) => {
                const text = typeof r === 'string' ? r : r.text;
                const revealed = typeof r === 'object' ? Boolean(r.revealed) : false;
                const succeeded = typeof r === 'object' && r.succeeded !== undefined ? Boolean(r.succeeded) : true;
                const isAsking = busyKey === `rumor:${idx}`;

                return (
                  <div
                    key={idx}
                    className="bg-black/50 border border-fantasy-border/60 rounded-lg p-3 flex items-center justify-between gap-3"
                  >
                    <div className="flex items-start gap-2.5 min-w-0 flex-1">
                      <MessageCircle size={15} className="text-fantasy-accent shrink-0 mt-0.5" />
                      {revealed ? (
                        <div>
                          <p className="text-xs text-gray-200 italic leading-relaxed">
                            {succeeded ? `"${text}"` : 'The merchant mumbled something inconclusive.'}
                          </p>
                          {succeeded && (
                            <span className="inline-flex items-center gap-1 text-[10px] text-emerald-400 mt-1">
                              <CheckCircle2 size={11} /> Logged to Clue Caseboard
                            </span>
                          )}
                        </div>
                      ) : (
                        <div>
                          <p className="text-xs font-semibold text-gray-300">Rumor Topic #{idx + 1}</p>
                          <p className="text-[11px] text-gray-500">
                            Ask the merchant about local whispers (CHA skill check).
                          </p>
                        </div>
                      )}
                    </div>

                    {!revealed && (
                      <button
                        onClick={() => handleRevealRumor(idx)}
                        disabled={isAsking}
                        className="px-3 py-1.5 rounded bg-fantasy-accent/20 hover:bg-fantasy-accent/30 text-fantasy-accent border border-fantasy-accent/50 text-xs font-bold flex items-center gap-1.5 shrink-0 disabled:opacity-40 transition-colors"
                      >
                        <Ear size={12} />
                        <span>{isAsking ? 'Asking...' : 'Ask Around'}</span>
                      </button>
                    )}
                  </div>
                );
              })
            )
          )}
        </div>
      </div>
    </div>
  );
};

export default MerchantModal;
