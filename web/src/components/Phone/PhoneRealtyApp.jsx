import { Home, Key, MapPin, RefreshCw, X } from 'lucide-react';
import { formatScenarioCurrency } from '../../utils/currency';

const PhoneRealtyApp = ({
  realtyData,
  loadingRealty,
  realtyBusy,
  realtyBanner,
  onClearBanner,
  realtySubTab,
  onChangeSubTab,
  selectedSpareKeyNpc,
  onSelectSpareKeyNpc,
  onRefreshRealty,
  onSetPrimaryProperty,
  onManageSpareKey,
  onBuyProperty,
  scenario = 'fantasy',
  t,
}) => {
  return (
    <div className="flex flex-col h-full space-y-2.5 min-h-0">
      {/* Header + Balance / Slot Bonus */}
      <div className="flex items-center justify-between pb-1.5 border-b border-neutral-800/80 shrink-0">
        <div>
          <h4 className="font-bold text-sm text-gray-100 flex items-center gap-1.5">
            <Home size={15} className="text-emerald-400" />
            <span>{t('realty.app_name', 'Realty & Deeds')}</span>
          </h4>
          <p className="text-[10px] text-gray-400">
            {t('realty.app_sub', 'Safehouses & Keys')}
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            disabled={loadingRealty || realtyBusy}
            onClick={onRefreshRealty}
            className="p-1.5 rounded-xl bg-neutral-900 hover:bg-neutral-800 text-gray-300 border border-neutral-800 transition-colors cursor-pointer"
            title={t('realty.refresh', 'Refresh')}
          >
            <RefreshCw size={13} className={loadingRealty ? 'animate-spin text-emerald-400' : ''} />
          </button>
          <span className="text-[10px] font-mono tabular-nums px-2 py-0.5 rounded-full bg-amber-950/60 text-amber-300 border border-amber-700/50 font-semibold">
            {formatScenarioCurrency(realtyData?.gold ?? 0, scenario)}
          </span>
          <span
            className="text-[10px] font-mono tabular-nums px-2 py-0.5 rounded-full bg-emerald-950/60 text-emerald-300 border border-emerald-700/50 font-semibold"
            title={t('realty.slot_bonus_tooltip', 'Safehouse Storage Bonus')}
          >
            +{realtyData?.property_slot_bonus ?? 0} {t('realty.slots_bonus', 'Slots')}
          </span>
        </div>
      </div>

      {/* Banner Feedback */}
      {realtyBanner && (
        <div
          className={`px-2.5 py-1.5 rounded-xl text-[11px] border flex items-center justify-between shrink-0 ${
            realtyBanner.type === 'error'
              ? 'bg-rose-950/50 border-rose-700/50 text-rose-200'
              : 'bg-emerald-950/50 border-emerald-700/50 text-emerald-200'
          }`}
        >
          <span>{realtyBanner.text}</span>
          <button
            type="button"
            onClick={onClearBanner}
            className="text-gray-400 hover:text-gray-200 ml-2 cursor-pointer"
          >
            <X size={12} />
          </button>
        </div>
      )}

      {/* Sub-tabs: My Residences vs Market Deeds */}
      <div className="grid grid-cols-2 gap-1.5 bg-neutral-900/90 p-1 rounded-xl border border-neutral-800 shrink-0">
        <button
          type="button"
          onClick={() => onChangeSubTab('owned')}
          className={`py-1.5 px-2 rounded-lg text-[11px] font-semibold transition-all cursor-pointer ${
            realtySubTab === 'owned'
              ? 'bg-emerald-600/25 text-emerald-200 border border-emerald-500/40 shadow-sm'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          🏠 {t('realty.tab_owned', 'My Residences')} ({(realtyData?.starter_quarters ? 1 : 0) + (realtyData?.owned_properties?.length || 0)})
        </button>
        <button
          type="button"
          onClick={() => onChangeSubTab('market')}
          className={`py-1.5 px-2 rounded-lg text-[11px] font-semibold transition-all cursor-pointer ${
            realtySubTab === 'market'
              ? 'bg-amber-600/25 text-amber-200 border border-amber-500/40 shadow-sm'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          🏷️ {t('realty.tab_market', 'Market Deeds')} ({realtyData?.catalog?.length || 0})
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto space-y-2.5 pr-1 min-h-0">
        {loadingRealty && !realtyData ? (
          <div className="py-10 text-center text-xs text-gray-400">
            {t('realty.loading', 'Loading urban property registry...')}
          </div>
        ) : realtySubTab === 'owned' ? (
          <>
            {/* Starter Quarters Card */}
            {realtyData?.starter_quarters && (() => {
              const sq = realtyData.starter_quarters;
              return (
                <div className="p-3 rounded-xl bg-neutral-900/85 border border-teal-800/50 space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-xs font-bold text-gray-100">{sq.name}</span>
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-teal-950/80 text-teal-300 border border-teal-700/60 uppercase font-bold">
                          {t('realty.badge_starter', 'Starter Quarters')}
                        </span>
                        {Boolean(sq.is_primary) && (
                          <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-950/80 text-emerald-300 border border-emerald-600/60 uppercase font-bold">
                            ★ {t('realty.primary_home', 'Primary Home')}
                          </span>
                        )}
                      </div>
                      <p className="text-[10px] text-gray-400 mt-0.5 flex items-center gap-1">
                        <MapPin size={10} className="text-teal-400 shrink-0" />
                        <span>{sq.zone_name}{sq.room_name ? ` • ${sq.room_name}` : ''}</span>
                      </p>
                    </div>
                    {!sq.is_primary && (
                      <button
                        type="button"
                        disabled={realtyBusy}
                        onClick={() => onSetPrimaryProperty(sq.property_id)}
                        className="px-2 py-1 rounded-lg text-[10px] font-semibold bg-neutral-800 hover:bg-neutral-700 text-emerald-300 border border-emerald-700/40 shrink-0 cursor-pointer disabled:opacity-50"
                      >
                        {t('realty.set_primary', 'Set Primary')}
                      </button>
                    )}
                  </div>
                  {sq.description && (
                    <p className="text-[11px] text-gray-300 leading-relaxed">{sq.description}</p>
                  )}
                  <p className="text-[10px] text-gray-500 italic">
                    {t('realty.starter_spare_key_note', 'Assigned faction quarters relocate on transfer. Purchase a permanent deed to hand out Spare Keys.')}
                  </p>
                </div>
              );
            })()}

            {/* Permanently Owned Deeds */}
            {(realtyData?.owned_properties || []).length === 0 ? (
              <div className="p-4 rounded-xl bg-neutral-900/50 border border-neutral-800 text-center space-y-2">
                <p className="text-xs text-gray-400">
                  {t('realty.no_deeds_owned', 'No permanent property deeds owned yet.')}
                </p>
                <button
                  type="button"
                  onClick={() => onChangeSubTab('market')}
                  className="px-3 py-1.5 rounded-lg text-[11px] font-semibold bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 border border-amber-500/40 cursor-pointer"
                >
                  🏷️ {t('realty.browse_market', 'Browse Market Deeds')}
                </button>
              </div>
            ) : (
              (realtyData?.owned_properties || []).map((prop) => {
                const holders = prop.spare_key_holders || [];
                const holderIds = new Set(holders.map((h) => String(h.npc_id).toLowerCase()));
                const availableContacts = (realtyData?.eligible_spare_key_contacts || []).filter(
                  (c) => !holderIds.has(String(c.npc_id).toLowerCase())
                );
                const selectedCandidate = selectedSpareKeyNpc[prop.property_id];
                const chosenNpc = availableContacts.some((c) => c.npc_id === selectedCandidate)
                  ? selectedCandidate
                  : (availableContacts[0]?.npc_id || '');

                return (
                  <div key={prop.property_id} className="p-3 rounded-xl bg-neutral-900/90 border border-emerald-800/50 space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="text-[10px] font-mono tabular-nums px-1.5 py-0.5 rounded bg-neutral-800 text-amber-300 border border-amber-700/40 font-bold">
                            T{prop.tier}
                          </span>
                          <span className="text-xs font-bold text-gray-100">{prop.name}</span>
                          {Boolean(prop.is_primary) && (
                            <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-950/80 text-emerald-300 border border-emerald-600/60 uppercase font-bold">
                              ★ {t('realty.primary_home', 'Primary Home')}
                            </span>
                          )}
                        </div>
                        <p className="text-[10px] text-gray-400 mt-0.5 flex items-center gap-1">
                          <MapPin size={10} className="text-emerald-400 shrink-0" />
                          <span>{prop.zone_name}</span>
                        </p>
                      </div>
                      {!prop.is_primary && (
                        <button
                          type="button"
                          disabled={realtyBusy}
                          onClick={() => onSetPrimaryProperty(prop.property_id)}
                          className="px-2 py-1 rounded-lg text-[10px] font-semibold bg-neutral-800 hover:bg-neutral-700 text-emerald-300 border border-emerald-700/40 shrink-0 cursor-pointer disabled:opacity-50"
                        >
                          {t('realty.set_primary', 'Set Primary')}
                        </button>
                      )}
                    </div>

                    {/* Perks Pills */}
                    <div className="flex flex-wrap gap-1">
                      {prop.base_slots > 0 && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-800/60 font-mono tabular-nums">
                          +{prop.base_slots} {t('realty.slots_bonus', 'Slots')}
                        </span>
                      )}
                      {Number(prop.rest_multiplier || 1) > 1 && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-sky-950/60 text-sky-300 border border-sky-800/60 font-mono tabular-nums">
                          {prop.rest_multiplier}x Rest
                        </span>
                      )}
                      {Number(prop.cha_invite_dc_mod || 0) < 0 && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-purple-950/60 text-purple-300 border border-purple-800/60 font-mono tabular-nums">
                          {prop.cha_invite_dc_mod} Invite DC
                        </span>
                      )}
                      {Number(prop.hangout_affinity_bonus || 0) > 0 && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-pink-950/60 text-pink-300 border border-pink-800/60 font-mono tabular-nums">
                          +{prop.hangout_affinity_bonus} Affinity
                        </span>
                      )}
                    </div>

                    {prop.description && (
                      <p className="text-[11px] text-gray-300 leading-relaxed">{prop.description}</p>
                    )}

                    {/* Spare Keys Section */}
                    <div className="pt-1.5 border-t border-neutral-800/80 space-y-1.5">
                      <div className="text-[10px] font-semibold text-gray-300 flex items-center gap-1">
                        <Key size={11} className="text-amber-400" />
                        <span>{t('realty.spare_keys_label', 'Spare Key Holders')}</span>
                      </div>
                      {holders.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                          {holders.map((h) => (
                            <span
                              key={h.npc_id}
                              className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-amber-950/50 text-amber-200 border border-amber-700/50"
                            >
                              <span>🔑 {h.name}</span>
                              <button
                                type="button"
                                disabled={realtyBusy}
                                onClick={() => onManageSpareKey(prop.property_id, h.npc_id, true)}
                                className="text-rose-300 hover:text-rose-200 ml-0.5 cursor-pointer"
                                title={t('realty.revoke_key', 'Revoke Key')}
                              >
                                <X size={10} />
                              </button>
                            </span>
                          ))}
                        </div>
                      )}
                      {availableContacts.length > 0 ? (
                        <div className="flex items-center gap-1.5">
                          <select
                            value={chosenNpc}
                            onChange={(e) => onSelectSpareKeyNpc(prop.property_id, e.target.value)}
                            className="flex-1 bg-neutral-950 border border-neutral-800 rounded-lg px-2 py-1 text-[11px] text-gray-200"
                          >
                            {availableContacts.map((c) => (
                              <option key={c.npc_id} value={c.npc_id}>
                                {c.name} ({c.is_romantic ? '♥' : `+${c.relationship_score}`})
                              </option>
                            ))}
                          </select>
                          <button
                            type="button"
                            disabled={realtyBusy || !chosenNpc}
                            onClick={() => onManageSpareKey(prop.property_id, chosenNpc, false)}
                            className="px-2.5 py-1 rounded-lg text-[10px] font-bold bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 border border-amber-500/40 shrink-0 cursor-pointer disabled:opacity-50"
                          >
                            {t('realty.give_spare_key', 'Give Key')}
                          </button>
                        </div>
                      ) : (
                        holders.length === 0 && (
                          <p className="text-[10px] text-gray-500">
                            {t('realty.no_eligible_contacts', 'Reach Affinity 70+ or romance a contact to give them a Spare Key.')}
                          </p>
                        )
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </>
        ) : (
          /* Market Listings Tab */
          (realtyData?.catalog || []).map((item) => {
            const isOwned = Boolean(item.is_owned);
            const canAfford = Boolean(item.can_afford);
            return (
              <div
                key={item.property_id}
                className={`p-3 rounded-xl border space-y-1.5 ${
                  isOwned
                    ? 'bg-emerald-950/20 border-emerald-800/50'
                    : 'bg-neutral-900/90 border-neutral-800'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-[10px] font-mono tabular-nums px-1.5 py-0.5 rounded bg-neutral-800 text-amber-300 border border-amber-700/40 font-bold">
                        T{item.tier}
                      </span>
                      <span className="text-xs font-bold text-gray-100">{item.name}</span>
                    </div>
                    <p className="text-[10px] text-gray-400 mt-0.5 flex items-center gap-1">
                      <MapPin size={10} className="text-amber-400 shrink-0" />
                      <span>{item.zone_name}</span>
                    </p>
                  </div>
                  <button
                    type="button"
                    disabled={isOwned || !canAfford || realtyBusy}
                    onClick={() => onBuyProperty(item.property_id)}
                    className={`px-2.5 py-1 rounded-lg text-[10px] font-bold tabular-nums transition-all shrink-0 ${
                      isOwned
                        ? 'bg-emerald-950/70 text-emerald-300 border border-emerald-700/50 cursor-default'
                        : canAfford
                          ? 'bg-amber-500/25 hover:bg-amber-500/35 text-amber-200 border border-amber-500/50 active:scale-95 cursor-pointer'
                          : 'bg-neutral-950 text-gray-600 border border-neutral-800 cursor-not-allowed'
                    }`}
                  >
                    {isOwned
                      ? `✓ ${t('realty.deed_owned', 'Owned')}`
                      : `${t('realty.buy_deed', 'Buy')} • ${formatScenarioCurrency(item.price, scenario)}`}
                  </button>
                </div>

                <div className="flex flex-wrap gap-1">
                  {item.base_slots > 0 && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-800/60 font-mono tabular-nums">
                      +{item.base_slots} {t('realty.slots_bonus', 'Slots')}
                    </span>
                  )}
                  {Number(item.rest_multiplier || 1) > 1 && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-sky-950/60 text-sky-300 border border-sky-800/60 font-mono tabular-nums">
                      {item.rest_multiplier}x Rest
                    </span>
                  )}
                  {Number(item.cha_invite_dc_mod || 0) < 0 && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-purple-950/60 text-purple-300 border border-purple-800/60 font-mono tabular-nums">
                      {item.cha_invite_dc_mod} Invite DC
                    </span>
                  )}
                  {Number(item.hangout_affinity_bonus || 0) > 0 && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-pink-950/60 text-pink-300 border border-pink-800/60 font-mono tabular-nums">
                      +{item.hangout_affinity_bonus} Affinity
                    </span>
                  )}
                </div>

                {item.description && (
                  <p className="text-[11px] text-gray-400 leading-relaxed">{item.description}</p>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

export default PhoneRealtyApp;
