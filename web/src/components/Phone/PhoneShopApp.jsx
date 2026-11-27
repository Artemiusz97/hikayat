import { useEffect, useMemo, useRef, useState } from 'react';
import { RefreshCw, ShieldAlert, ShoppingBag, WifiOff } from 'lucide-react';
import { formatScenarioCurrency } from '../../utils/currency';

const FALLBACK_CATEGORY_LABELS = {
  all: { label: 'All', emoji: '🛒' },
  food: { label: 'Food', emoji: '🍱' },
  drinks: { label: 'Drinks', emoji: '🥤' },
  meds: { label: 'Meds', emoji: '💊' },
  gifts: { label: 'Gifts', emoji: '🎁' },
  clothing: { label: 'Clothing', emoji: '👕' },
  accessories: { label: 'Accessories', emoji: '💍' },
  stationery: { label: 'Stationery', emoji: '📓' },
  apparel: { label: 'Apparel', emoji: '🧥' },
  weapons: { label: 'Weapons', emoji: '🗡️' },
  armor: { label: 'Armor', emoji: '🛡️' },
  arcane: { label: 'Arcane', emoji: '✨' },
  adult: { label: 'Adult', emoji: '🌶️' },
};

const PhoneShopApp = ({
  branding,
  storeMode = 'online_general',
  shopData,
  loadingShop,
  buyingItem,
  shopFeedback,
  onClearFeedback,
  onBuyDeliveryItem,
  inCombat = false,
  commsOffline = false,
  scenario = 'fantasy',
  t,
}) => {
  const effScenario = scenario || shopData?.scenario || 'fantasy';
  const isSchoolMart = storeMode === 'school_mart' || shopData?.store_mode === 'school_mart';
  const combatLocked = Boolean(inCombat || shopData?.in_combat || shopData?.combat_locked);

  const [selectedCategory, setSelectedCategory] = useState('all');
  const tabRefs = useRef({});

  useEffect(() => {
    setSelectedCategory('all');
  }, [storeMode]);

  const inventory = useMemo(() => shopData?.inventory || [], [shopData?.inventory]);

  const categories = useMemo(() => {
    const apiCats = Array.isArray(shopData?.categories) ? shopData.categories : [];
    const seen = new Set(['all']);
    const list = [
      {
        id: 'all',
        label: t('phone.shop.cat_all', 'All'),
        emoji: '🛒',
      },
    ];
    for (const c of apiCats) {
      const id = String(c?.id || c?.key || '').toLowerCase();
      if (!id || seen.has(id)) continue;
      seen.add(id);
      const fallback = FALLBACK_CATEGORY_LABELS[id] || { label: c?.label || id, emoji: '📦' };
      list.push({
        id,
        label: t(`phone.shop.cat_${id}`, c?.label || fallback.label),
        emoji: c?.emoji || fallback.emoji,
      });
    }
    if (list.length === 1 && inventory.length > 0) {
      for (const item of inventory) {
        const id = String(item?.store_category || item?.category || '').toLowerCase();
        if (!id || seen.has(id)) continue;
        seen.add(id);
        const fallback = FALLBACK_CATEGORY_LABELS[id] || { label: id, emoji: '📦' };
        list.push({
          id,
          label: t(`phone.shop.cat_${id}`, fallback.label),
          emoji: fallback.emoji,
        });
      }
    }
    return list;
  }, [shopData?.categories, inventory, t]);

  useEffect(() => {
    if (selectedCategory !== 'all' && !categories.some((c) => c.id === selectedCategory)) {
      setSelectedCategory('all');
    }
  }, [categories, selectedCategory]);

  const filteredInventory = useMemo(() => {
    if (selectedCategory === 'all') return inventory;
    return inventory.filter(
      (item) =>
        String(item?.store_category || item?.category || '').toLowerCase() === selectedCategory
    );
  }, [inventory, selectedCategory]);

  const selectCategory = (catId, moveFocus = false) => {
    setSelectedCategory(catId);
    const el = tabRefs.current[catId];
    if (el) {
      if (moveFocus) el.focus();
      try {
        el.scrollIntoView({ block: 'nearest', inline: 'nearest', container: 'nearest' });
      } catch {
        el.scrollIntoView({ block: 'nearest', inline: 'nearest' });
      }
    }
  };

  const handleTabKeyDown = (e, idx) => {
    if (!categories.length) return;
    let nextIdx = null;
    if (e.key === 'ArrowRight') nextIdx = (idx + 1) % categories.length;
    else if (e.key === 'ArrowLeft') nextIdx = (idx - 1 + categories.length) % categories.length;
    else if (e.key === 'Home') nextIdx = 0;
    else if (e.key === 'End') nextIdx = categories.length - 1;
    if (nextIdx !== null) {
      e.preventDefault();
      selectCategory(categories[nextIdx].id, true);
    }
  };

  const defaultStoreTitle = isSchoolMart
    ? branding.school_shop_app_name || t('phone.apps.school_mart', 'SchoolMart')
    : branding.shop_app_name || t('phone.apps.online_store', 'Online Store');

  return (
    <div className="flex flex-col h-full space-y-2.5 min-h-0">
      <div className="flex items-center justify-between pb-1 border-b border-neutral-800/80 shrink-0 gap-2">
        <h4 className="font-bold text-sm text-gray-100 flex items-center gap-1.5 min-w-0">
          <ShoppingBag
            size={15}
            className={isSchoolMart ? 'text-sky-400 shrink-0' : 'text-amber-400 shrink-0'}
          />
          <span className="truncate">{shopData?.flavor_name || defaultStoreTitle}</span>
        </h4>
        {shopData && (
          <div className="flex items-center gap-1.5 shrink-0">
            {shopData.discount_pct > 0 && (
              <span className="text-[10px] font-mono tabular-nums text-emerald-300 bg-emerald-950/50 px-1.5 py-0.5 rounded-full border border-emerald-700/50 font-bold">
                {isSchoolMart
                  ? t('phone.shop.student_discount_badge', '-{{pct}}% Student', {
                      pct: shopData.discount_pct,
                    })
                  : `-${shopData.discount_pct}% Off`}
              </span>
            )}
            <span className="text-[11px] font-mono tabular-nums text-amber-300 bg-amber-950/40 px-2 py-0.5 rounded-full border border-amber-700/40 font-semibold">
              {formatScenarioCurrency(shopData.gold ?? 0, effScenario)}
            </span>
          </div>
        )}
      </div>

      {shopData?.greeting && (
        <p className="text-[10px] text-gray-400 italic bg-neutral-900/60 px-2.5 py-1.5 rounded-xl border border-neutral-800 shrink-0 line-clamp-2">
          "{shopData.greeting}"
        </p>
      )}

      {commsOffline && (
        <div className="px-2.5 py-1.5 rounded-xl text-[11px] border bg-rose-950/60 border-rose-700/60 text-rose-200 flex items-center gap-1.5 shrink-0">
          <WifiOff size={13} className="text-rose-400 shrink-0" />
          <span>
            {t('phone.no_signal_banner', 'No Signal — Isolated Realm (cached logs remain readable)')}
          </span>
        </div>
      )}

      {combatLocked && (
        <div className="px-2.5 py-1.5 rounded-xl text-[11px] border bg-rose-950/60 border-rose-700/60 text-rose-200 flex items-center gap-1.5 shrink-0">
          <ShieldAlert size={13} className="text-rose-400 shrink-0" />
          <span>
            {shopData?.delivery_blocked_reason ||
              shopData?.combat_lock_reason ||
              t(
                'phone.shop.combat_locked_notice',
                'Courier deliveries suspended during active combat — catalog browsing only.'
              )}
          </span>
        </div>
      )}

      {shopFeedback && (
        <div
          className={`px-2.5 py-1.5 rounded-xl text-xs border flex items-center justify-between shrink-0 ${
            shopFeedback.type === 'error'
              ? 'bg-red-950/60 border-red-800/60 text-red-200'
              : 'bg-emerald-950/60 border-emerald-800/60 text-emerald-200'
          }`}
        >
          <span className="text-[11px]">{shopFeedback.text}</span>
          <button
            type="button"
            onClick={onClearFeedback}
            className="text-[10px] opacity-70 hover:opacity-100 ml-2"
          >
            ✕
          </button>
        </div>
      )}

      {!loadingShop && categories.length > 1 && (
        <div
          role="tablist"
          aria-label={t('phone.shop.categories_aria', 'Store categories')}
          className="hk-tabs-scroller shrink-0"
        >
          {categories.map((cat, idx) => {
            const isSelected = selectedCategory === cat.id;
            return (
              <button
                key={cat.id}
                ref={(el) => {
                  tabRefs.current[cat.id] = el;
                }}
                type="button"
                role="tab"
                id={`phone-shop-tab-${cat.id}`}
                aria-selected={isSelected}
                aria-controls="phone-shop-tabpanel"
                tabIndex={isSelected ? 0 : -1}
                onClick={() => selectCategory(cat.id, false)}
                onKeyDown={(e) => handleTabKeyDown(e, idx)}
                className="hk-shop-tab"
              >
                <span>{cat.emoji}</span>
                <span>{cat.label}</span>
              </button>
            );
          })}
        </div>
      )}

      {loadingShop ? (
        <div className="text-center py-16 text-gray-500 italic space-y-2">
          <RefreshCw
            size={20}
            className={`animate-spin mx-auto ${isSchoolMart ? 'text-sky-400' : 'text-amber-400'}`}
          />
          <p className="text-xs">{t('phone.shop.connecting', 'Connecting to courier network...')}</p>
        </div>
      ) : !shopData || filteredInventory.length === 0 ? (
        <div className="text-center py-14 px-4 text-gray-500 border border-dashed border-neutral-800 rounded-2xl">
          <ShoppingBag size={28} className="mx-auto opacity-30 text-amber-400 mb-1" />
          <p className="text-xs">{t('phone.shop.empty', 'No courier catalog available right now.')}</p>
        </div>
      ) : (
        <div
          id="phone-shop-tabpanel"
          role="tabpanel"
          aria-labelledby={`phone-shop-tab-${selectedCategory}`}
          className="space-y-1.5 overflow-y-auto pr-0.5 flex-1 custom-scrollbar min-h-0"
        >
          {filteredInventory.map((item, idx) => {
            const finalPrice = item.final_price ?? item.price ?? 0;
            const basePrice = item.base_price ?? item.price ?? finalPrice;
            const canAfford = (shopData.gold ?? 0) >= finalPrice;
            const orderDisabled = commsOffline || combatLocked || !canAfford || Boolean(buyingItem);
            const badges = Array.isArray(item.badges) ? item.badges : [];
            return (
              <div
                key={item.name || idx}
                className="flex items-center justify-between gap-2 p-2 bg-neutral-900/80 hover:bg-neutral-900 border border-neutral-800 rounded-xl transition-all"
              >
                <div className="flex items-center gap-2.5 min-w-0 flex-1">
                  <div className="w-8 h-8 rounded-lg bg-neutral-800/80 border border-neutral-700/50 flex items-center justify-center text-base shrink-0">
                    {item.emoji || '📦'}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1 flex-wrap">
                      <span className="font-bold text-[11px] text-gray-200 truncate">{item.name}</span>
                      {item.tier && (
                        <span className="text-[9px] px-1 py-0.5 rounded bg-indigo-950/70 text-indigo-300 border border-indigo-700/50 font-mono shrink-0">
                          T{item.tier}
                        </span>
                      )}
                      {(item.quantity ?? item.stock) != null && (
                        <span className="text-[9px] px-1 py-0.5 rounded bg-neutral-800 text-gray-300 font-mono shrink-0">
                          x{item.quantity ?? item.stock}
                        </span>
                      )}
                      {item.category && (
                        <span className="text-[9px] px-1 py-0.5 rounded bg-neutral-800 text-gray-400 shrink-0 font-mono">
                          {item.category}
                        </span>
                      )}
                    </div>
                    <p className="text-[10px] text-gray-400 truncate leading-tight">
                      {item.description || item.effect || 'Courier delivery item'}
                    </p>
                    {badges.length > 0 && (
                      <div className="flex items-center gap-1 flex-wrap mt-1">
                        {badges.slice(0, 3).map((bText, bIdx) => (
                          <span
                            key={`${item.name}-b-${bIdx}`}
                            className="text-[9px] px-1.5 py-0.5 rounded bg-cyan-950/60 text-cyan-300 border border-cyan-800/50 font-mono"
                          >
                            {bText}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <div className="text-right tabular-nums">
                    {basePrice > finalPrice && (
                      <span className="text-[9px] font-mono text-gray-500 line-through block leading-none">
                        {formatScenarioCurrency(basePrice, effScenario)}
                      </span>
                    )}
                    <span className="text-[11px] font-mono font-bold text-amber-300 leading-tight block">
                      {formatScenarioCurrency(finalPrice, effScenario)}
                    </span>
                  </div>
                  <button
                    type="button"
                    disabled={orderDisabled}
                    onClick={() => onBuyDeliveryItem(item)}
                    title={
                      combatLocked
                        ? t('phone.shop.combat_locked_tip', 'Unavailable during active combat')
                        : undefined
                    }
                    className={`px-2.5 py-1 rounded-lg text-[10px] font-bold transition-all shrink-0 ${
                      !orderDisabled
                        ? isSchoolMart
                          ? 'bg-sky-500/20 hover:bg-sky-500/30 text-sky-200 border border-sky-500/40 active:scale-95 cursor-pointer'
                          : 'bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 border border-amber-500/40 active:scale-95 cursor-pointer'
                        : 'bg-neutral-950 text-gray-600 border border-neutral-800 cursor-not-allowed'
                    }`}
                  >
                    {buyingItem === item.name
                      ? '...'
                      : combatLocked
                        ? t('phone.shop.locked_btn', 'Combat')
                        : canAfford
                          ? t('phone.shop.order_btn', 'Order')
                          : t('phone.shop.funds_btn', 'Funds')}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default PhoneShopApp;
