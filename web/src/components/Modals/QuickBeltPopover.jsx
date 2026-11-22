import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  Check,
  FlaskConical,
  Loader2,
  Package,
  Sparkles,
  Swords,
  User,
  Users,
  X,
  Zap,
} from 'lucide-react';
import { AcrylicModal, MotionButton } from '../Common/MotionPrimitives';
import {
  getAllowedUseActions,
  isHostileConsumable,
  isUsableConsumable,
} from '../../utils/consumables';
import { groupInventoryItems, isAnomalousNpc, normalizeActorName } from '../../utils/sceneTargets';

const buildUseStoryText = (item, target) => {
  const itemName = item?.name || 'item';
  if (!target || target.type === 'self') {
    return `Use ${itemName} on myself.`;
  }
  if (target.type === 'monster') {
    return `Use ${itemName} against ${target.label || target.name}.`;
  }
  return `Use ${itemName} on ${target.label || target.name}.`;
};

const QuickBeltPopover = ({
  isOpen,
  onClose,
  items = null,
  inventoryHook = null,
  onQuickUse = null,
  onAction = null,
  onRefreshCharacter = null,
  session = null,
  character = null,
  currentUserId = null,
  presentNpcs = [],
  combatEnemies = [],
  inCombat = false,
  processing = false,
  isStealthActive = false,
  initialTarget = null,
  onClearInitialTarget = null,
}) => {
  const { t } = useTranslation();
  const [selectedTargetKey, setSelectedTargetKey] = useState('self:self');
  const [busyItemId, setBusyItemId] = useState(null);
  const [feedback, setFeedback] = useState(null);

  const inventoryItems = useMemo(() => {
    if (Array.isArray(items)) return items;
    if (Array.isArray(inventoryHook?.items)) return inventoryHook.items;
    return [];
  }, [items, inventoryHook?.items]);

  const usableItems = useMemo(
    () => groupInventoryItems(inventoryItems.filter((it) => isUsableConsumable(it))),
    [inventoryItems]
  );

  const targetGroups = useMemo(() => {
    const selfTarget = {
      key: 'self:self',
      type: 'self',
      name: 'self',
      label: character?.name || t('inventory.target_yourself', 'Yourself'),
      userId: currentUserId ?? null,
      hp: character?.hp,
      maxHp: character?.max_hp,
      mp: character?.mp,
      maxMp: character?.max_mp,
    };

    const partyTargets = [];
    const seenPartyNpc = new Set();

    const rawPartyMembers = Array.isArray(session?.party_members) ? session.party_members : [];
    rawPartyMembers.forEach((member) => {
      if (!member) return;
      if (currentUserId !== null && currentUserId !== undefined && String(member.user_id) === String(currentUserId)) {
        return;
      }
      const mName = String(member.name || member.char_name || member.username || `Adventurer ${member.user_id}`).trim();
      partyTargets.push({
        key: `player:${member.user_id}`,
        type: 'player',
        name: mName,
        label: mName,
        userId: member.user_id,
        hp: member.hp,
        maxHp: member.max_hp,
        mp: member.mp,
        maxMp: member.max_mp,
      });
    });

    const rawPartyNpcs = Array.isArray(session?.party_npcs) ? session.party_npcs : [];
    rawPartyNpcs.forEach((entry) => {
      if (isAnomalousNpc(entry)) return;
      const npcName = normalizeActorName(entry);
      if (!npcName || seenPartyNpc.has(npcName.toLowerCase())) return;
      seenPartyNpc.add(npcName.toLowerCase());
      partyTargets.push({
        key: `companion:${npcName.toLowerCase()}`,
        type: 'companion',
        name: npcName,
        label: npcName,
        userId: null,
      });
    });

    const npcTargets = [];
    const seenNpcs = new Set();
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
      if (seenPartyNpc.has(lower) || seenNpcs.has(lower)) return;
      seenNpcs.add(lower);
      npcTargets.push({
        key: `npc:${lower}`,
        type: 'npc',
        name: npcName,
        label: npcName,
        userId: null,
      });
    });

    const enemyTargets = [];
    if (inCombat) {
      const seenEnemies = new Set();
      const rawEnemies =
        Array.isArray(combatEnemies) && combatEnemies.length > 0
          ? combatEnemies
          : Array.isArray(session?.combat_state?.enemies)
            ? session.combat_state.enemies
            : [];

      rawEnemies.forEach((enemy, idx) => {
        if (!enemy || typeof enemy !== 'object') return;
        const hp = Number(enemy.hp ?? enemy.max_hp ?? 1);
        if (enemy.defeated || hp <= 0) return;
        const eName = String(enemy.name || `Enemy ${idx + 1}`).trim();
        const keyLower = eName.toLowerCase();
        if (!eName || seenEnemies.has(keyLower)) return;
        seenEnemies.add(keyLower);
        enemyTargets.push({
          key: `monster:${keyLower}`,
          type: 'monster',
          name: eName,
          label: eName,
          userId: null,
          hp: enemy.hp,
          maxHp: enemy.max_hp,
        });
      });
    }

    return {
      selfTarget,
      partyTargets,
      npcTargets,
      enemyTargets,
      allTargets: [selfTarget, ...partyTargets, ...npcTargets, ...enemyTargets],
    };
  }, [
    character?.name,
    character?.hp,
    character?.max_hp,
    character?.mp,
    character?.max_mp,
    currentUserId,
    session?.party_members,
    session?.party_npcs,
    session?.current_npcs,
    session?.combat_state?.enemies,
    presentNpcs,
    combatEnemies,
    inCombat,
    t,
  ]);

  useEffect(() => {
    if (!isOpen) return;
    setFeedback(null);
    setBusyItemId(null);

    if (initialTarget && (initialTarget.name || initialTarget.userId || initialTarget.type)) {
      const reqType = String(initialTarget.type || '').toLowerCase();
      const reqName = String(initialTarget.name || '').trim().toLowerCase();
      const reqUid = initialTarget.userId !== undefined && initialTarget.userId !== null
        ? String(initialTarget.userId)
        : null;

      const matched =
        targetGroups.allTargets.find((tgt) => {
          if (reqUid && tgt.userId !== null && String(tgt.userId) === reqUid && tgt.type === 'player') {
            return true;
          }
          if (reqType && tgt.type === reqType && reqName && tgt.name.toLowerCase() === reqName) {
            return true;
          }
          return false;
        }) ||
        targetGroups.allTargets.find((tgt) => reqName && tgt.name.toLowerCase() === reqName);

      if (matched) {
        setSelectedTargetKey(matched.key);
        return;
      }
    }

    setSelectedTargetKey((prev) => {
      if (targetGroups.allTargets.some((tgt) => tgt.key === prev)) return prev;
      return 'self:self';
    });
  }, [isOpen, initialTarget, targetGroups.allTargets]);

  const selectedTarget = useMemo(
    () => targetGroups.allTargets.find((tgt) => tgt.key === selectedTargetKey) || targetGroups.selfTarget,
    [targetGroups, selectedTargetKey]
  );

  const handleClose = () => {
    setFeedback(null);
    setBusyItemId(null);
    onClearInitialTarget?.();
    onClose?.();
  };

  const handleQuickUseClick = async (item) => {
    if (busyItemId || processing) return;
    const execQuickUse =
      onQuickUse ||
      (inventoryHook?.useItem
        ? (itemId, tgtType, tgtName, tgtUserId) =>
            inventoryHook.useItem(itemId, session?.id ?? null, tgtType, tgtName, tgtUserId)
        : null);
    if (!execQuickUse) return;

    setBusyItemId(item.id);
    setFeedback(null);
    try {
      const res = await execQuickUse(
        item.id,
        selectedTarget.type,
        selectedTarget.name,
        selectedTarget.userId ?? null
      );
      if (onRefreshCharacter) {
        await onRefreshCharacter();
      }
      setFeedback({
        ok: true,
        text: res?.message || t('quickbelt.used_success', 'Used {{item}}.', { item: item.name }),
      });
    } catch (err) {
      setFeedback({
        ok: false,
        text: err?.message || t('quickbelt.use_failed', 'Could not use item.'),
      });
    } finally {
      setBusyItemId(null);
    }
  };

  const handleStoryUseClick = (item, mode) => {
    if (busyItemId || processing || !onAction) return;
    handleClose();
    onAction({
      choice_index: null,
      intent: 'use_item',
      item_id: item.id,
      target_type: selectedTarget.type,
      target_name: selectedTarget.name,
      target_npc:
        selectedTarget.type === 'npc' || selectedTarget.type === 'companion'
          ? selectedTarget.name
          : null,
      target_user_id: selectedTarget.userId ?? null,
      use_mode: mode,
      combat_target: selectedTarget.type === 'monster' ? selectedTarget.name : null,
      is_stealth: Boolean(isStealthActive),
      stance: isStealthActive ? 'stealth' : null,
      custom_action_text: buildUseStoryText(item, selectedTarget),
    });
  };

  const renderTargetChip = (tgt) => {
    const active = selectedTarget?.key === tgt.key;
    const hasHp = tgt.hp !== undefined && tgt.hp !== null && tgt.maxHp !== undefined && tgt.maxHp !== null;
    const hasMp = tgt.mp !== undefined && tgt.mp !== null && tgt.maxMp !== undefined && tgt.maxMp !== null;
    return (
      <button
        key={tgt.key}
        type="button"
        onClick={() => setSelectedTargetKey(tgt.key)}
        className={`px-2.5 py-1.5 rounded-xl border text-left transition-colors flex items-center gap-1.5 text-xs ${
          active
            ? 'bg-fantasy-accent/20 border-fantasy-accent text-fantasy-accent font-semibold'
            : 'bg-white/5 border-fantasy-border/35 text-gray-200 hover:bg-white/10'
        }`}
      >
        <span className="truncate max-w-[140px]">{tgt.label}</span>
        {hasHp && (
          <span className="text-[10px] font-mono text-rose-300/90 shrink-0">
            {tgt.hp}/{tgt.maxHp}
          </span>
        )}
        {hasMp && (
          <span className="text-[10px] font-mono text-sky-300/90 shrink-0">
            • {tgt.mp}/{tgt.maxMp}
          </span>
        )}
      </button>
    );
  };

  return (
    <AcrylicModal
      isOpen={isOpen}
      onClose={handleClose}
      label={t('quickbelt.title', 'Use Item')}
      maxWidthClass="max-w-lg"
      className="p-4 sm:p-5 space-y-4 max-h-[85dvh] flex flex-col overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 border-b border-fantasy-border/35 pb-3 shrink-0">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <FlaskConical size={17} className="text-emerald-300 shrink-0" />
            <h3 className="font-rpg font-bold text-fantasy-accent text-base leading-none">
              {t('quickbelt.title', 'Use Item')}
            </h3>
          </div>
          <p className="text-xs text-gray-400 mt-1">
            {t(
              'quickbelt.subtitle',
              'Choose a recipient and apply a consumable or throwable.'
            )}
          </p>
        </div>
        <button
          type="button"
          onClick={handleClose}
          className="p-1.5 rounded-lg text-gray-400 hover:text-gray-100 hover:bg-white/10 transition-colors"
          aria-label={t('common.close', 'Close')}
        >
          <X size={16} />
        </button>
      </div>

      {/* Combat turn notice */}
      {inCombat && (
        <div className="shrink-0 rounded-xl px-3 py-2 bg-rose-500/15 border border-rose-400/35 text-xs text-rose-200 flex items-center gap-2">
          <Swords size={14} className="shrink-0 text-rose-300" />
          <span>
            {t(
              'quickbelt.combat_turn_note',
              'Combat active: using a consumable consumes your turn.'
            )}
          </span>
        </div>
      )}

      {/* Feedback banner */}
      {feedback && (
        <div
          className={`shrink-0 rounded-xl px-3 py-2 border text-xs flex items-center gap-2 ${
            feedback.ok
              ? 'bg-emerald-500/15 border-emerald-400/40 text-emerald-200'
              : 'bg-rose-500/15 border-rose-400/40 text-rose-200'
          }`}
        >
          {feedback.ok ? <Check size={14} className="shrink-0" /> : <AlertTriangle size={14} className="shrink-0" />}
          <span>{feedback.text}</span>
        </div>
      )}

      {/* Target selector groups */}
      <div className="shrink-0 space-y-2.5 bg-black/25 border border-fantasy-border/25 rounded-xl p-3">
        <div className="text-[11px] font-bold uppercase tracking-wider text-gray-300 flex items-center gap-1.5">
          <User size={12} className="text-fantasy-accent" />
          <span>{t('inventory.target', 'Target:')}</span>
        </div>

        {/* Self */}
        <div className="flex flex-wrap gap-1.5">
          {renderTargetChip(targetGroups.selfTarget)}
        </div>

        {/* Party Members (Co-op Players + Companions) */}
        {targetGroups.partyTargets.length > 0 && (
          <div className="space-y-1">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-cyan-300/90 flex items-center gap-1">
              <Users size={11} />
              <span>{t('quickbelt.group_party', 'Party Members')}</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {targetGroups.partyTargets.map(renderTargetChip)}
            </div>
          </div>
        )}

        {/* Present NPCs */}
        {targetGroups.npcTargets.length > 0 && (
          <div className="space-y-1">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-amber-300/90">
              {t('quickbelt.group_npcs', 'Present NPCs')}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {targetGroups.npcTargets.map(renderTargetChip)}
            </div>
          </div>
        )}

        {/* Enemies (Combat only) */}
        {inCombat && targetGroups.enemyTargets.length > 0 && (
          <div className="space-y-1">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-rose-300/90 flex items-center gap-1">
              <Swords size={11} />
              <span>{t('quickbelt.group_enemies', 'Enemies')}</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {targetGroups.enemyTargets.map(renderTargetChip)}
            </div>
          </div>
        )}
      </div>

      {/* Usable items list */}
      <div className="flex-1 min-h-0 overflow-y-auto space-y-2 pr-1">
        {usableItems.length === 0 ? (
          <div className="text-center py-8 text-gray-400 space-y-1.5">
            <Package size={24} className="mx-auto opacity-45" />
            <p className="text-xs">{t('quickbelt.empty', 'No quick-usable items in pack')}</p>
          </div>
        ) : (
          usableItems.map((item) => {
            const { canQuickUse, canTurnUse, mode } = getAllowedUseActions({
              item,
              targetType: selectedTarget.type,
              inCombat,
            });
            const hostile = isHostileConsumable(item);
            const showHostileWarn = hostile && selectedTarget.type === 'npc';
            const cleanEffect =
              item.clean_effect !== undefined
                ? item.clean_effect
                : item.effect && !String(item.effect).startsWith('[')
                  ? item.effect
                  : '';
            const isBusy = busyItemId === item.id;

            return (
              <div
                key={item.id}
                className="rounded-xl p-3 bg-gray-500/10 border border-fantasy-border/30 space-y-2"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-xs font-bold text-gray-100 truncate">
                        {item.name}
                      </span>
                      {Number(item.count || 1) > 1 && (
                        <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/35">
                          x{item.count}
                        </span>
                      )}
                      {hostile && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-400/40 font-semibold">
                          {t('quickbelt.hostile_tag', 'Hostile / Covert')}
                        </span>
                      )}
                    </div>
                    {cleanEffect && (
                      <p className="text-[11px] text-gray-300 mt-0.5 leading-snug">
                        {cleanEffect}
                      </p>
                    )}
                  </div>
                </div>

                {showHostileWarn && (
                  <div className="rounded-lg px-2.5 py-1.5 bg-amber-500/15 border border-amber-400/35 text-[11px] text-amber-200 flex items-center gap-1.5">
                    <AlertTriangle size={12} className="shrink-0 text-amber-300" />
                    <span>
                      {t(
                        'quickbelt.hostile_warning',
                        'Covert/hostile item: triggers an AGI/CHA check on NPCs; failure damages affinity & spikes detection.'
                      )}
                    </span>
                  </div>
                )}

                <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
                  {canQuickUse && (
                    <MotionButton
                      type="button"
                      disabled={Boolean(busyItemId) || processing}
                      onClick={() => handleQuickUseClick(item)}
                      className="px-3 py-1.5 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-400/45 text-emerald-200 text-xs font-semibold flex items-center gap-1.5 disabled:opacity-40"
                    >
                      {isBusy ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : (
                        <Zap size={12} />
                      )}
                      <span>{t('quickbelt.quick_use', 'Quick Use (0 Turns)')}</span>
                    </MotionButton>
                  )}
                  {canTurnUse && (
                    <MotionButton
                      type="button"
                      disabled={Boolean(busyItemId) || processing || !onAction}
                      onClick={() => handleStoryUseClick(item, mode)}
                      className="px-3 py-1.5 rounded-lg bg-fantasy-accent/20 hover:bg-fantasy-accent/30 border border-fantasy-accent/50 text-fantasy-accent text-xs font-semibold flex items-center gap-1.5 disabled:opacity-40"
                    >
                      <Sparkles size={12} />
                      <span>{t('quickbelt.use_in_story', 'Use in Story (1 Turn)')}</span>
                    </MotionButton>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </AcrylicModal>
  );
};

export default QuickBeltPopover;
