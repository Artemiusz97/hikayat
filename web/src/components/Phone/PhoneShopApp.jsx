import { RefreshCw, ShoppingBag } from 'lucide-react';
import { formatScenarioCurrency } from '../../utils/currency';

const PhoneShopApp = ({
  branding,
  shopData,
  loadingShop,
  buyingItem,
  shopFeedback,
  onClearFeedback,
  onBuyDeliveryItem,
  scenario = 'fantasy',
  t,
}) => {
  const effScenario = scenario || shopData?.scenario || 'fantasy';

  return (
    <div className="flex flex-col h-full space-y-2.5 min-h-0">
      <div className="flex items-center justify-between pb-1 border-b border-neutral-800/80 shrink-0">
        <h4 className="font-bold text-sm text-gray-100 flex items-center gap-1.5">
          <ShoppingBag size={15} className="text-amber-400" />
          <span>{shopData?.flavor_name || branding.shop_app_name || 'E-Shop Delivery'}</span>
        </h4>
        {shopData && (
          <div className="flex items-center gap-1.5">
            {shopData.discount_pct > 0 && (
              <span className="text-[10px] font-mono tabular-nums text-emerald-300 bg-emerald-950/50 px-1.5 py-0.5 rounded-full border border-emerald-700/50 font-bold">
                -{shopData.discount_pct}% Off
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

      {loadingShop ? (
        <div className="text-center py-16 text-gray-500 italic space-y-2">
          <RefreshCw size={20} className="animate-spin text-amber-400 mx-auto" />
          <p className="text-xs">{t('phone.shop.connecting', 'Connecting to courier network...')}</p>
        </div>
      ) : !shopData || !shopData.inventory || shopData.inventory.length === 0 ? (
        <div className="text-center py-14 px-4 text-gray-500 border border-dashed border-neutral-800 rounded-2xl">
          <ShoppingBag size={28} className="mx-auto opacity-30 text-amber-400 mb-1" />
          <p className="text-xs">{t('phone.shop.empty', 'No courier catalog available right now.')}</p>
        </div>
      ) : (
        <div className="space-y-1.5 overflow-y-auto pr-0.5 flex-1 custom-scrollbar min-h-0">
          {shopData.inventory.map((item, idx) => {
            const finalPrice = item.final_price ?? item.price ?? 0;
            const basePrice = item.base_price ?? item.price ?? finalPrice;
            const canAfford = (shopData.gold ?? 0) >= finalPrice;
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
                    <div className="flex items-center gap-1.5">
                      <span className="font-bold text-[11px] text-gray-200 truncate">{item.name}</span>
                      {item.category && (
                        <span className="text-[9px] px-1 py-0.5 rounded bg-neutral-800 text-gray-400 shrink-0 font-mono">
                          {item.category}
                        </span>
                      )}
                    </div>
                    <p className="text-[10px] text-gray-400 truncate leading-tight">
                      {item.description || item.effect || 'Courier delivery item'}
                    </p>
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
                    disabled={!canAfford || Boolean(buyingItem)}
                    onClick={() => onBuyDeliveryItem(item)}
                    className={`px-2.5 py-1 rounded-lg text-[10px] font-bold transition-all shrink-0 ${
                      canAfford
                        ? 'bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 border border-amber-500/40 active:scale-95 cursor-pointer'
                        : 'bg-neutral-950 text-gray-600 border border-neutral-800 cursor-not-allowed'
                    }`}
                  >
                    {buyingItem === item.name ? '...' : canAfford ? 'Order' : 'Funds'}
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
