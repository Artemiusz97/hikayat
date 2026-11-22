import { useState, useEffect, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { X, ShoppingBag, Tag, MessageCircle, Package, Handshake, Ear, CheckCircle2 } from 'lucide-react';
import { apiCall } from '../../api/client';
import CurrencyBadge from '../Common/CurrencyBadge';
import { formatScenarioCurrency } from '../../utils/currency';
import { AcrylicModal, MotionButton } from '../Common/MotionPrimitives';

const MerchantModal = ({ isOpen, onClose, session, user, onTransactionComplete, onRefreshCodex }) => {
  const { t } = useTranslation();
  const [shop, setShop] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('buy'); // 'buy' | 'sell' | 'rumors'
  const [selectedStoreType, setSelectedStoreType] = useState(null);
  const [busyKey, setBusyKey] = useState(null);
  const [feedback, setFeedback] = useState(null);
  const loadSeqRef = useRef(0);
  const loadAbortRef = useRef(null);
  const sellTabStaleRef = useRef(false);

  const scenarioKey = session?.scenario || shop?.scenario || 'fantasy';

  const loadShop = useCallback(async (overrideType = undefined) => {
    if (!session?.id || !user?.user_id) return;
    const seq = ++loadSeqRef.current;
    loadAbortRef.current?.abort();
    const controller = new AbortController();
    loadAbortRef.current = controller;

    setLoading(true);
    try {
      const mType = overrideType !== undefined ? overrideType : selectedStoreType;
      const query = mType
        ? `/api/merchant/${session.id}?user_id=${user.user_id}&merchant_type=${encodeURIComponent(mType)}`
        : `/api/merchant/${session.id}?user_id=${user.user_id}`;
      const data = await apiCall(query, { signal: controller.signal });
      if (seq !== loadSeqRef.current) return;
      setShop(data);
      if (data?.merchant_type) {
        setSelectedStoreType(data.merchant_type);
      }
    } catch (err) {
      if (err?.name === 'AbortError' || err?.isUserAbort || seq !== loadSeqRef.current) return;
      setFeedback({ type: 'error', text: err.message || t('merchant.load_wares_failed', 'Failed to load merchant wares') });
    } finally {
      if (seq === loadSeqRef.current) {
        setLoading(false);
      }
    }
  }, [session?.id, user?.user_id, selectedStoreType, t]);

  useEffect(() => {
    setSelectedStoreType(null);
    setShop(null);
  }, [session?.current_location]);

  useEffect(() => {
    if (isOpen) {
      setFeedback(null);
      setSelectedStoreType(null);
      loadShop('');
    } else {
      loadAbortRef.current?.abort();
      loadSeqRef.current += 1;
    }
    return () => {
      loadAbortRef.current?.abort();
    };
  }, [isOpen, session?.current_location]);

  const handleSwitchStore = async (storeType) => {
    setSelectedStoreType(storeType);
    setFeedback(null);
    await loadShop(storeType);
  };

  const handleBuy = async (itemName) => {
    if (busyKey || !session?.id || !user?.user_id) return;
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
      const formattedPaid = formatScenarioCurrency(res.price_paid, scenarioKey);
      setFeedback({
        type: 'success',
        text: t('merchant.purchased_feedback', {
          name: res.item_name,
          price: formattedPaid,
          defaultValue: `Purchased ${res.item_name} for ${formattedPaid}!`,
        }),
      });
      setShop((prev) =>
        prev
          ? {
              ...prev,
              gold: res.gold ?? prev.gold,
              stock: Array.isArray(res.stock) ? res.stock : prev.stock,
              inventory: Array.isArray(res.stock) ? res.stock : prev.inventory,
            }
          : prev
      );
      sellTabStaleRef.current = true;
      if (activeTab === 'sell') {
        await loadShop(shop?.merchant_type || selectedStoreType);
        sellTabStaleRef.current = false;
      }
      if (onTransactionComplete) onTransactionComplete();
    } catch (err) {
      setFeedback({ type: 'error', text: err.message || t('merchant.purchase_failed', 'Purchase failed') });
    } finally {
      setBusyKey(null);
    }
  };

  const handleSell = async (item) => {
    if (busyKey || !session?.id || !user?.user_id) return;
    setBusyKey(`sell:${item.id}`);
    setFeedback(null);
    try {
      const res = await apiCall('/api/merchant/sell', {
        method: 'POST',
        body: JSON.stringify({
          session_id: session.id,
          user_id: user.user_id,
          item_id: item.id,
          merchant_type: shop?.merchant_type || selectedStoreType
        })
      });
      const formattedEarned = formatScenarioCurrency(res.gold_earned, scenarioKey);
      setFeedback({
        type: 'success',
        text: t('merchant.sold_feedback', {
          name: res.item_name,
          gold: formattedEarned,
          defaultValue: `Sold ${res.item_name} for ${formattedEarned}!`,
        }),
      });
      setShop((prev) =>
        prev
          ? {
              ...prev,
              gold: res.gold ?? prev.gold,
              sellable_items: (prev.sellable_items || []).filter((it) => it.id !== item.id),
            }
          : prev
      );
      if (onTransactionComplete) onTransactionComplete();
    } catch (err) {
      setFeedback({ type: 'error', text: err.message || t('merchant.sale_failed', 'Sale failed') });
    } finally {
      setBusyKey(null);
    }
  };

  const handleHaggle = async () => {
    if (busyKey || !session?.id || !user?.user_id) return;
    setBusyKey('haggle');
    setFeedback(null);
    try {
      const res = await apiCall('/api/merchant/haggle', {
        method: 'POST',
        body: JSON.stringify({
          session_id: session.id,
          user_id: user.user_id,
          merchant_type: shop?.merchant_type || selectedStoreType
        })
      });
      setFeedback({
        type: res.haggle_succeeded ? 'success' : 'error',
        text: res.message || (res.haggle_succeeded ? t('merchant.haggle_success', 'Haggle succeeded!') : t('merchant.haggle_failed', 'Haggle failed.'))
      });
      setShop((prev) =>
        prev
          ? {
              ...prev,
              haggle_attempts: res.haggle_attempts ?? prev.haggle_attempts,
              haggle_attempts_left: res.haggle_attempts_left ?? prev.haggle_attempts_left,
              haggle_discount_pct: res.haggle_discount_pct ?? prev.haggle_discount_pct,
              discount_pct: res.discount_pct ?? prev.discount_pct,
              stock: Array.isArray(res.stock) ? res.stock : prev.stock,
              inventory: Array.isArray(res.stock) ? res.stock : prev.inventory,
            }
          : prev
      );
    } catch (err) {
      setFeedback({ type: 'error', text: err.message || t('merchant.haggle_attempt_failed', 'Haggle attempt failed') });
    } finally {
      setBusyKey(null);
    }
  };

  const handleRevealRumor = async (idx) => {
    if (busyKey || !session?.id || !user?.user_id) return;
    setBusyKey(`rumor:${idx}`);
    setFeedback(null);
    try {
      const res = await apiCall('/api/merchant/rumor', {
        method: 'POST',
        body: JSON.stringify({
          session_id: session.id,
          user_id: user.user_id,
          rumor_index: idx,
          merchant_type: shop?.merchant_type || selectedStoreType
        })
      });
      setFeedback({
        type: res.rumor_succeeded ? 'success' : 'error',
        text: res.message || t('merchant.rumor_investigated', 'Rumor investigated.')
      });
      setShop((prev) =>
        prev
          ? {
              ...prev,
              rumors: Array.isArray(res.rumors) ? res.rumors : prev.rumors,
            }
          : prev
      );
      if (res.rumor_succeeded && onRefreshCodex) {
        onRefreshCodex();
      }
    } catch (err) {
      setFeedback({ type: 'error', text: err.message || t('merchant.rumor_investigate_failed', 'Failed to investigate rumor') });
    } finally {
      setBusyKey(null);
    }
  };

  const haggleLeft = shop?.haggle_attempts_left ?? Math.max(0, 3 - (shop?.haggle_attempts || 0));

  return (
    <AcrylicModal
      isOpen={isOpen}
      onClose={onClose}
      label={shop?.merchant_name || t('merchant.title_fallback', 'Merchant Emporium')}
      maxWidthClass="max-w-2xl"
    >
        {/* Header */}
        <div className="px-4 py-3.5 border-b border-fantasy-border/35 flex items-center justify-between gap-2 shrink-0">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="p-2 rounded-xl bg-amber-500/15 border border-amber-500/40 text-amber-400 shrink-0">
              <ShoppingBag size={18} />
            </div>
            <div className="min-w-0">
              <h3 className="font-rpg font-bold text-base text-fantasy-accent truncate">
                {shop?.merchant_name || t('merchant.title_fallback', 'Merchant Emporium')}
              </h3>
              <p className="text-xs text-gray-400 line-clamp-1">
                {shop?.merchant_description || t('merchant.desc_fallback', 'Browse local wares, trade equipment, or listen for rumors.')}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <CurrencyBadge amount={shop?.gold ?? 0} scenario={scenarioKey} size="sm" />
            <MotionButton onClick={onClose} aria-label={t('common.close', 'Close')} className="hk-icon-btn h-8 min-w-8">
              <X size={18} />
            </MotionButton>
          </div>
        </div>

        {/* Specialist Store Directory Switcher */}
        {Array.isArray(shop?.available_stores) && shop.available_stores.length > 1 && (
          <div className="px-4 py-2 border-b border-fantasy-border/35 flex flex-wrap items-center gap-1.5 shrink-0">
            <span className="text-[10px] uppercase tracking-wider font-bold text-gray-400 mr-1 shrink-0">
              {t('merchant.bazaar_stalls', 'Bazaar Stalls:')}
            </span>
            {shop.available_stores.map((st) => {
              const isSelected = (shop?.merchant_type || selectedStoreType) === st.type;
              return (
                <MotionButton
                  key={st.type}
                  onClick={() => handleSwitchStore(st.type)}
                  disabled={loading}
                  className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold flex items-center gap-1 border transition-colors ${
                    isSelected
                      ? 'bg-amber-500/20 border-amber-500/60 text-amber-300'
                      : 'bg-gray-500/10 border-fantasy-border/40 text-gray-300 hover:text-gray-100 hover:border-fantasy-border'
                  }`}
                >
                  <span>{st.emoji || '🛍️'}</span>
                  <span>{st.title}</span>
                </MotionButton>
              );
            })}
          </div>
        )}

        {/* Sub-Tabs, Haggle Button & Charisma Discount Pill */}
        <div className="px-4 py-2 border-b border-fantasy-border/35 flex flex-wrap items-center justify-between gap-2 shrink-0">
          <div className="flex flex-wrap gap-1">
            {[
              { id: 'buy', label: `${t('merchant.buy_wares', 'Buy Wares')} (${shop?.stock?.length || 0})` },
              { id: 'sell', label: `${t('merchant.sell_pack', 'Sell Pack')} (${shop?.sellable_items?.length || 0})` },
              { id: 'rumors', label: `${t('merchant.rumors', 'Rumors')} (${shop?.rumors?.length || 0})` }
            ].map(tab => (
              <MotionButton
                key={tab.id}
                onClick={() => {
                  setActiveTab(tab.id);
                  if (tab.id === 'sell' && sellTabStaleRef.current) {
                    sellTabStaleRef.current = false;
                    loadShop(shop?.merchant_type || selectedStoreType);
                  }
                }}
                className={`px-3 py-1 rounded-lg text-xs font-semibold uppercase tracking-wider transition-colors ${
                  activeTab === tab.id
                    ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-500/10'
                }`}
              >
                {tab.label}
              </MotionButton>
            ))}
          </div>

          <div className="flex items-center gap-2">
            {shop?.discount_pct > 0 && (
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-lg bg-emerald-500/15 text-emerald-300 border border-emerald-500/40 flex items-center gap-1">
                <Tag size={10} /> {t('merchant.off_discount', { pct: shop.discount_pct, defaultValue: `-${shop.discount_pct}% Off` })}
              </span>
            )}

            <MotionButton
              onClick={handleHaggle}
              disabled={haggleLeft <= 0 || busyKey === 'haggle' || loading}
              title={t('merchant.haggle_title', 'Attempt a Charisma + Luck check for an extra -10% discount')}
              className="px-2.5 py-1 rounded-lg bg-purple-500/15 hover:bg-purple-500/25 text-purple-200 border border-purple-500/45 text-[11px] font-semibold flex items-center gap-1 disabled:opacity-40 transition-colors"
            >
              <Handshake size={12} className="text-purple-300" />
              <span>{busyKey === 'haggle' ? t('merchant.haggling', 'Haggling...') : t('merchant.haggle', { left: haggleLeft, defaultValue: `Haggle (${haggleLeft}/3)` })}</span>
            </MotionButton>
          </div>
        </div>

        {/* Feedback Banner */}
        {feedback && (
          <div className={`mx-4 mt-3 p-2.5 rounded-xl border text-xs flex items-center justify-between shrink-0 ${
            feedback.type === 'error'
              ? 'bg-red-500/15 border-red-500/40 text-red-200'
              : 'bg-emerald-500/15 border-emerald-500/40 text-emerald-200'
          }`}>
            <span>{feedback.text}</span>
            <button type="button" onClick={() => setFeedback(null)} className="text-gray-400 hover:text-white">
              <X size={13} />
            </button>
          </div>
        )}

        {/* Content Body */}
        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain custom-scrollbar px-4 py-2">
          {loading ? (
            <div className="text-center py-12 text-gray-400 text-xs animate-pulse">
              {t('merchant.appraising', 'Appraising merchant stock...')}
            </div>
          ) : activeTab === 'buy' ? (
            (shop?.stock || []).length === 0 ? (
              <div className="text-center py-10 text-gray-400">
                <Package size={24} className="mx-auto mb-1.5 opacity-40" />
                <p className="text-xs">{t('merchant.sold_out', 'The merchant is currently sold out.')}</p>
              </div>
            ) : (
              <div className="divide-y divide-fantasy-border/30">
                {(shop?.stock || []).map((item, idx) => {
                  const price = item.final_price ?? item.price ?? 15;
                  const canAfford = (shop?.gold ?? 0) >= price;
                  const isBuying = busyKey === `buy:${item.name}`;

                  return (
                    <div
                      key={`${item.name}-${idx}`}
                      className="py-3 flex items-center justify-between gap-3"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center flex-wrap gap-2">
                          <span className="font-semibold text-sm text-gray-100 truncate">{item.name}</span>
                          <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-gray-500/15 text-gray-300 border border-fantasy-border/40 font-mono">
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

                      <MotionButton
                        onClick={() => handleBuy(item.name)}
                        disabled={!canAfford || isBuying}
                        className="px-3 py-1.5 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/50 text-xs font-bold font-mono tabular-nums flex items-center gap-1.5 shrink-0 disabled:opacity-40 transition-colors"
                      >
                        <span>{isBuying ? '...' : formatScenarioCurrency(price, scenarioKey)}</span>
                      </MotionButton>
                    </div>
                  );
                })}
              </div>
            )
          ) : activeTab === 'sell' ? (
            (shop?.sellable_items || []).length === 0 ? (
              <div className="text-center py-10 text-gray-400">
                <Package size={24} className="mx-auto mb-1.5 opacity-40" />
                <p className="text-xs">{t('merchant.no_sellable', 'No unequipped sellable items in your pack.')}</p>
              </div>
            ) : (
              <div className="divide-y divide-fantasy-border/30">
                {(shop?.sellable_items || []).map(item => {
                  const isSelling = busyKey === `sell:${item.id}`;
                  return (
                    <div
                      key={item.id}
                      className="py-3 flex items-center justify-between gap-3"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center flex-wrap gap-2">
                          <span className="font-semibold text-sm text-gray-200 truncate">{item.name}</span>
                          <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-gray-500/15 text-gray-300 border border-fantasy-border/40 font-mono">
                            {item.item_type || 'Item'}
                          </span>
                        </div>
                        {item.effect && !item.effect.startsWith('[') && (
                          <p className="text-xs text-gray-400 mt-1 truncate">{item.effect}</p>
                        )}
                      </div>

                      <MotionButton
                        onClick={() => handleSell(item)}
                        disabled={isSelling}
                        className="px-3 py-1.5 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 border border-emerald-500/45 text-xs font-bold font-mono tabular-nums flex items-center gap-1 shrink-0 disabled:opacity-40 transition-colors"
                      >
                        <span>
                          {isSelling
                            ? '...'
                            : t('merchant.sell_action', {
                                price: formatScenarioCurrency(item.sell_price, scenarioKey),
                                defaultValue: `Sell +${formatScenarioCurrency(item.sell_price, scenarioKey)}`,
                              })}
                        </span>
                      </MotionButton>
                    </div>
                  );
                })}
              </div>
            )
          ) : (
            (shop?.rumors || []).length === 0 ? (
              <p className="text-center py-10 text-xs text-gray-400 italic">{t('merchant.no_rumors', 'The merchant has no rumors to share right now.')}</p>
            ) : (
              <div className="divide-y divide-fantasy-border/30">
                {(shop?.rumors || []).map((r, idx) => {
                  const text = typeof r === 'string' ? r : r.text;
                  const revealed = typeof r === 'object' ? Boolean(r.revealed) : false;
                  const succeeded = typeof r === 'object' && r.succeeded !== undefined ? Boolean(r.succeeded) : true;
                  const isAsking = busyKey === `rumor:${idx}`;

                  return (
                    <div
                      key={idx}
                      className="py-3 flex items-center justify-between gap-3"
                    >
                      <div className="flex items-start gap-2.5 min-w-0 flex-1">
                        <MessageCircle size={15} className="text-fantasy-accent shrink-0 mt-0.5" />
                        {revealed ? (
                          <div className="min-w-0">
                            <p className="text-xs text-gray-200 italic leading-relaxed">
                              {succeeded ? `"${text}"` : t('merchant.rumor_inconclusive', 'The merchant mumbled something inconclusive.')}
                            </p>
                            {succeeded && (
                              <span className="inline-flex items-center gap-1 text-[10px] text-emerald-400 mt-1">
                                <CheckCircle2 size={11} /> {t('merchant.logged_to_caseboard', 'Logged to Clue Caseboard')}
                              </span>
                            )}
                          </div>
                        ) : (
                          <div className="min-w-0">
                            <p className="text-xs font-semibold text-gray-300">{t('merchant.rumor_topic', { num: idx + 1, defaultValue: `Rumor Topic #${idx + 1}` })}</p>
                            <p className="text-[11px] text-gray-400">
                              {t('merchant.ask_whispers_hint', 'Ask the merchant about local whispers (CHA skill check).')}
                            </p>
                          </div>
                        )}
                      </div>

                      {!revealed && (
                        <MotionButton
                          onClick={() => handleRevealRumor(idx)}
                          disabled={isAsking}
                          className="px-3 py-1.5 rounded-lg bg-fantasy-accent/20 hover:bg-fantasy-accent/30 text-fantasy-accent border border-fantasy-accent/50 text-xs font-bold flex items-center gap-1.5 shrink-0 disabled:opacity-40 transition-colors"
                        >
                          <Ear size={12} />
                          <span>{isAsking ? t('merchant.asking', 'Asking...') : t('merchant.ask_around', 'Ask Around')}</span>
                        </MotionButton>
                      )}
                    </div>
                  );
                })}
              </div>
            )
          )}
        </div>
    </AcrylicModal>
  );
};

export default MerchantModal;
