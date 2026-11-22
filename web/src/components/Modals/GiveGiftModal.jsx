import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  Backpack,
  Check,
  Gift,
  KeyRound,
  Loader2,
  Package,
  User,
  Users,
  X,
} from 'lucide-react';
import { AcrylicModal, MotionButton } from '../Common/MotionPrimitives';
import { isKeyQuestItem } from '../../utils/consumables';
import { groupInventoryItems, isAnomalousNpc, normalizeActorName } from '../../utils/sceneTargets';

const GiveGiftModal = ({
  isOpen,
  onClose,
  items = null,
  inventory = null,
  inventoryHook = null,
  session = null,
  presentNpcs = [],
  currentUserId = null,
  onAction = null,
  processing = false,
  initialTarget = null,
  onClearInitialTarget = null,
}) => {
  const { t } = useTranslation();
  const [selectedRecipientKey, setSelectedRecipientKey] = useState(null);
  const [selectedItemId, setSelectedItemId] = useState(null);
  const [questConfirmed, setQuestConfirmed] = useState(false);

  const inventoryItems = useMemo(() => {
    const raw = Array.isArray(items)
      ? items
      : Array.isArray(inventory)
        ? inventory
        : Array.isArray(inventory?.items)
          ? inventory.items
          : Array.isArray(inventoryHook?.items)
            ? inventoryHook.items
            : [];
    return groupInventoryItems(
      raw.filter((item) => item && !item.equipped && !item.is_pact_locked)
    );
  }, [items, inventory, inventoryHook?.items]);

  const recipientGroups = useMemo(() => {
    const partyRecipients = [];
    const npcRecipients = [];
    const seenPartyNpc = new Set();
    const seenNpc = new Set();

    const partyMembers = Array.isArray(session?.party_members) ? session.party_members : [];
    partyMembers.forEach((member) => {
      if (!member) return;
      if (currentUserId !== null && currentUserId !== undefined && String(member.user_id) === String(currentUserId)) {
        return;
      }
      const mName = String(member.name || member.char_name || member.username || `Adventurer ${member.user_id}`).trim();
      const usedSlots = Math.max(0, Number(member.used_slots ?? 0) || 0);
      const capacity = Math.max(1, Number(member.capacity ?? 20) || 20);
      partyRecipients.push({
        key: `player:${member.user_id}`,
        type: 'player',
        name: mName,
        label: mName,
        userId: member.user_id,
        usedSlots,
        capacity,
      });
    });

    const partyNpcs = Array.isArray(session?.party_npcs) ? session.party_npcs : [];
    partyNpcs.forEach((entry) => {
      if (isAnomalousNpc(entry)) return;
      const npcName = normalizeActorName(entry);
      if (!npcName) return;
      const lower = npcName.toLowerCase();
      if (seenPartyNpc.has(lower)) return;
      seenPartyNpc.add(lower);
      partyRecipients.push({
        key: `companion:${lower}`,
        type: 'companion',
        name: npcName,
        label: npcName,
        userId: null,
      });
    });

    const rawNpcs =
      Array.isArray(presentNpcs) && presentNpcs.length > 0
        ? presentNpcs
        : Array.isArray(session?.current_npcs)
          ? session.current_npcs
          : [];

    rawNpcs.forEach((entry) => {
      if (isAnomalousNpc(entry)) return;
      const npcName = normalizeActorName(entry);
      if (!npcName) return;
      const lower = npcName.toLowerCase();
      if (seenPartyNpc.has(lower) || seenNpc.has(lower)) return;
      seenNpc.add(lower);
      npcRecipients.push({
        key: `npc:${lower}`,
        type: 'npc',
        name: npcName,
        label: npcName,
        userId: null,
      });
    });

    return {
      partyRecipients,
      npcRecipients,
      allRecipients: [...partyRecipients, ...npcRecipients],
    };
  }, [session?.party_members, session?.party_npcs, session?.current_npcs, presentNpcs, currentUserId]);

  useEffect(() => {
    if (!isOpen) return;
    setQuestConfirmed(false);

    if (initialTarget && (initialTarget.name || initialTarget.userId || initialTarget.type)) {
      const reqType = String(initialTarget.type || '').toLowerCase();
      const reqName = String(initialTarget.name || '').trim().toLowerCase();
      const reqUid =
        initialTarget.userId !== undefined && initialTarget.userId !== null
          ? String(initialTarget.userId)
          : null;

      const matched =
        recipientGroups.allRecipients.find((rec) => {
          if (reqUid && rec.userId !== null && String(rec.userId) === reqUid && rec.type === 'player') {
            return true;
          }
          if (reqType && rec.type === reqType && reqName && rec.name.toLowerCase() === reqName) {
            return true;
          }
          return false;
        }) ||
        recipientGroups.allRecipients.find((rec) => reqName && rec.name.toLowerCase() === reqName);

      if (matched) {
        setSelectedRecipientKey(matched.key);
      } else {
        setSelectedRecipientKey(recipientGroups.allRecipients[0]?.key || null);
      }
    } else {
      setSelectedRecipientKey((prev) => {
        if (prev && recipientGroups.allRecipients.some((rec) => rec.key === prev)) return prev;
        return recipientGroups.allRecipients[0]?.key || null;
      });
    }

    setSelectedItemId((prev) => {
      if (prev && inventoryItems.some((it) => it.id === prev)) return prev;
      return inventoryItems[0]?.id ?? null;
    });
  }, [isOpen, initialTarget, recipientGroups.allRecipients, inventoryItems]);

  const selectedRecipient = useMemo(
    () =>
      recipientGroups.allRecipients.find((rec) => rec.key === selectedRecipientKey) ||
      recipientGroups.allRecipients[0] ||
      null,
    [recipientGroups.allRecipients, selectedRecipientKey]
  );

  const selectedItem = useMemo(
    () => inventoryItems.find((it) => it.id === selectedItemId) || null,
    [inventoryItems, selectedItemId]
  );

  const selectedSlotCost = useMemo(() => {
    if (!selectedItem) return 1;
    return selectedItem.slot_cost !== undefined && selectedItem.slot_cost !== null
      ? Number(selectedItem.slot_cost)
      : 1;
  }, [selectedItem]);

  const isSelectedQuestItem = useMemo(
    () => Boolean(selectedItem && isKeyQuestItem(selectedItem)),
    [selectedItem]
  );

  const isTargetBackpackFull = useMemo(() => {
    if (!selectedRecipient || selectedRecipient.type !== 'player' || !selectedItem) return false;
    if (selectedSlotCost <= 0) return false;
    return selectedRecipient.usedSlots + selectedSlotCost > selectedRecipient.capacity;
  }, [selectedRecipient, selectedItem, selectedSlotCost]);

  const handleClose = () => {
    setQuestConfirmed(false);
    onClearInitialTarget?.();
    onClose?.();
  };

  const handleSubmit = () => {
    if (!selectedRecipient || !selectedItem || processing || !onAction) return;
    if (isTargetBackpackFull) return;
    if (isSelectedQuestItem && !questConfirmed) return;

    const actionText =
      selectedRecipient.type === 'player'
        ? `Give ${selectedItem.name} to ${selectedRecipient.label}.`
        : `Offer and give ${selectedItem.name} to ${selectedRecipient.label}.`;

    handleClose();
    onAction({
      choice_index: null,
      intent: 'gift_offer',
      item_id: selectedItem.id,
      target_type: selectedRecipient.type,
      target_name: selectedRecipient.name,
      target_npc:
        selectedRecipient.type === 'npc' || selectedRecipient.type === 'companion'
          ? selectedRecipient.name
          : null,
      target_user_id: selectedRecipient.userId ?? null,
      custom_action_text: actionText,
    });
  };

  const renderRecipientChip = (rec) => {
    const active = selectedRecipient?.key === rec.key;
    return (
      <button
        key={rec.key}
        type="button"
        onClick={() => setSelectedRecipientKey(rec.key)}
        className={`px-2.5 py-1.5 rounded-xl border text-xs flex items-center gap-1.5 transition-colors ${
          active
            ? 'bg-amber-500/20 border-amber-400 text-amber-200 font-semibold'
            : 'bg-white/5 border-fantasy-border/35 text-gray-200 hover:bg-white/10'
        }`}
      >
        <span className="truncate max-w-[140px]">{rec.label}</span>
        {rec.type === 'player' && (
          <span
            className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
              rec.usedSlots >= rec.capacity
                ? 'bg-rose-500/25 text-rose-200 border border-rose-400/40'
                : 'bg-cyan-500/20 text-cyan-200 border border-cyan-400/35'
            }`}
          >
            {rec.usedSlots}/{rec.capacity}
          </span>
        )}
        {rec.type === 'companion' && (
          <span className="text-[10px] text-cyan-300/90">
            • {t('gift.companion_tag', 'Companion')}
          </span>
        )}
      </button>
    );
  };

  const canSubmit = Boolean(
    selectedRecipient &&
      selectedItem &&
      !processing &&
      !isTargetBackpackFull &&
      (!isSelectedQuestItem || questConfirmed)
  );

  return (
    <AcrylicModal
      isOpen={isOpen}
      onClose={handleClose}
      label={t('gift.title', 'Give Gift / Item')}
      maxWidthClass="max-w-lg"
      className="p-4 sm:p-5 space-y-4 max-h-[85dvh] flex flex-col overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 border-b border-fantasy-border/35 pb-3 shrink-0">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Gift size={17} className="text-amber-300 shrink-0" />
            <h3 className="font-rpg font-bold text-fantasy-accent text-base leading-none">
              {t('gift.title', 'Give Gift / Item')}
            </h3>
          </div>
          <p className="text-xs text-gray-400 mt-1">
            {t(
              'gift.subtitle',
              'Transfer or gift an item directly without consuming its effect (1 turn).'
            )}
          </p>
        </div>
        <button
          type="button"
          onClick={handleClose}
          className="p-1.5 rounded-lg text-gray-400 hover:text-gray-100 hover:bg-white/10 transition-colors"
          aria-label={t('gift.cancel', 'Cancel')}
        >
          <X size={16} />
        </button>
      </div>

      {/* Recipient selector */}
      <div className="shrink-0 space-y-2.5 bg-black/25 border border-fantasy-border/25 rounded-xl p-3">
        <div className="text-[11px] font-bold uppercase tracking-wider text-gray-300 flex items-center gap-1.5">
          <User size={12} className="text-amber-300" />
          <span>{t('gift.select_recipient', 'Select Recipient')}</span>
        </div>

        {recipientGroups.allRecipients.length === 0 ? (
          <p className="text-xs text-gray-400 italic">
            {t('gift.no_npcs', 'No party members or NPCs present in this scene.')}
          </p>
        ) : (
          <div className="space-y-2">
            {recipientGroups.partyRecipients.length > 0 && (
              <div className="space-y-1">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-cyan-300/90 flex items-center gap-1">
                  <Users size={11} />
                  <span>{t('gift.group_party', 'Party Members')}</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {recipientGroups.partyRecipients.map(renderRecipientChip)}
                </div>
              </div>
            )}

            {recipientGroups.npcRecipients.length > 0 && (
              <div className="space-y-1">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-amber-300/90">
                  {t('gift.group_npcs', 'Present NPCs')}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {recipientGroups.npcRecipients.map(renderRecipientChip)}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Item selector */}
      <div className="flex-1 min-h-0 flex flex-col space-y-2 overflow-hidden">
        <div className="text-[11px] font-bold uppercase tracking-wider text-gray-300 flex items-center gap-1.5 shrink-0">
          <Package size={12} className="text-fantasy-accent" />
          <span>{t('gift.select_item', 'Select Item to Gift')}</span>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto space-y-1.5 pr-1">
          {inventoryItems.length === 0 ? (
            <p className="text-xs text-gray-400 italic py-4 text-center">
              {t('gift.inventory_empty', 'Your inventory has no unequipped items available.')}
            </p>
          ) : (
            inventoryItems.map((item) => {
              const active = selectedItem?.id === item.id;
              const isQuest = isKeyQuestItem(item);
              const cleanEffect =
                item.clean_effect !== undefined
                  ? item.clean_effect
                  : item.effect && !String(item.effect).startsWith('[')
                    ? item.effect
                    : '';

              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    setSelectedItemId(item.id);
                    setQuestConfirmed(false);
                  }}
                  className={`w-full text-left rounded-xl p-2.5 border transition-colors ${
                    active
                      ? 'bg-fantasy-accent/15 border-fantasy-accent text-gray-100'
                      : 'bg-gray-500/10 border-fantasy-border/25 text-gray-300 hover:bg-gray-500/20'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5 min-w-0 flex-wrap">
                      <span className="text-xs font-semibold truncate">{item.name}</span>
                      {Number(item.count || 1) > 1 && (
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/10 text-gray-200">
                          x{item.count}
                        </span>
                      )}
                      {isQuest && (
                        <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-400/45">
                          <KeyRound size={10} />
                          <span>{t('inventory.key_item', 'Key Item')}</span>
                        </span>
                      )}
                    </div>
                    {active && <Check size={14} className="text-fantasy-accent shrink-0" />}
                  </div>
                  {cleanEffect && (
                    <p className="text-[11px] text-gray-400 mt-0.5 truncate">{cleanEffect}</p>
                  )}
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* Warnings: Full Backpack or Quest Item Confirmation */}
      {isTargetBackpackFull && selectedRecipient && (
        <div className="shrink-0 rounded-xl px-3 py-2 bg-rose-500/15 border border-rose-400/40 text-xs text-rose-200 flex items-center gap-2">
          <Backpack size={14} className="shrink-0 text-rose-300" />
          <span>
            {t(
              'gift.backpack_full',
              "{{name}}'s backpack is full ({{used}}/{{cap}} slots). Transfer blocked.",
              {
                name: selectedRecipient.label,
                used: selectedRecipient.usedSlots,
                cap: selectedRecipient.capacity,
              }
            )}
          </span>
        </div>
      )}

      {isSelectedQuestItem && !isTargetBackpackFull && (
        <label className="shrink-0 rounded-xl px-3 py-2 bg-amber-500/15 border border-amber-400/40 text-xs text-amber-200 flex items-start gap-2 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={questConfirmed}
            onChange={(e) => setQuestConfirmed(e.target.checked)}
            className="mt-0.5 accent-amber-400"
          />
          <span className="leading-snug flex items-center gap-1.5">
            <AlertTriangle size={13} className="shrink-0 text-amber-300 inline" />
            <span>
              {t(
                'gift.confirm_quest_item',
                'This is a Key/Quest Item. Confirm you want to hand it over.'
              )}
            </span>
          </span>
        </label>
      )}

      {/* Footer */}
      <div className="shrink-0 flex items-center justify-end gap-2 pt-2 border-t border-fantasy-border/30">
        <button
          type="button"
          onClick={handleClose}
          className="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 border border-fantasy-border/35 text-xs text-gray-300"
        >
          {t('gift.cancel', 'Cancel')}
        </button>
        <MotionButton
          type="button"
          disabled={!canSubmit}
          onClick={handleSubmit}
          className="px-3.5 py-1.5 rounded-lg bg-amber-500/25 hover:bg-amber-500/35 border border-amber-400/55 text-amber-200 text-xs font-semibold flex items-center gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {processing ? <Loader2 size={13} className="animate-spin" /> : <Gift size={13} />}
          <span>
            {processing
              ? t('gift.offering', 'Offering Gift...')
              : selectedRecipient
                ? t('gift.give_to', 'Give to {{name}}', { name: selectedRecipient.label })
                : t('gift.title', 'Give Gift / Item')}
          </span>
        </MotionButton>
      </div>
    </AcrylicModal>
  );
};

export default GiveGiftModal;
