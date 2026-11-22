import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Eye, EyeOff, FlaskConical, Gift, Swords } from 'lucide-react';
import { MotionButton } from '../Common/MotionPrimitives';
import { isUsableConsumable } from '../../utils/consumables';
import { isAnomalousNpc, normalizeActorName } from '../../utils/sceneTargets';

const TacticalActionDock = ({
  session = null,
  inCombat = false,
  disabled = false,
  processing = false,
  isStealthActive = false,
  selectedCombatTarget = null,
  onToggleStealth,
  onAction,
  inventory = [],
  presentNpcs = [],
  currentUserId = null,
  onOpenExamine,
  onOpenQuickBelt,
  onOpenGiveGift,
  compact = false,
}) => {
  const { t } = useTranslation();

  const stealthActorState = useMemo(() => {
    const st = session?.stealth_state || {};
    const actors = st?.actors || {};
    const uidKey = currentUserId !== null && currentUserId !== undefined ? String(currentUserId) : '';
    return (uidKey && actors[uidKey]) || st;
  }, [session?.stealth_state, currentUserId]);

  const detectionPct = Math.max(
    0,
    Math.min(
      100,
      Math.round(
        Number(stealthActorState?.detection_meter ?? session?.stealth_state?.detection_meter ?? 0) || 0
      )
    )
  );

  const isVanished = Boolean(isStealthActive || stealthActorState?.is_hidden || session?.stealth_state?.is_hidden);

  const usableCount = useMemo(() => {
    if (!Array.isArray(inventory)) return 0;
    return inventory.reduce((total, item) => {
      if (!isUsableConsumable(item)) return total;
      const qty = Math.max(1, Number(item?.count ?? 1) || 1);
      return total + qty;
    }, 0);
  }, [inventory]);

  const giftableItemCount = useMemo(() => {
    if (!Array.isArray(inventory)) return 0;
    return inventory.filter((item) => item && !item.equipped && !item.is_pact_locked).length;
  }, [inventory]);

  const recipientCount = useMemo(() => {
    const seenNpc = new Set();
    const npcsSource = Array.isArray(presentNpcs) && presentNpcs.length > 0
      ? presentNpcs
      : Array.isArray(session?.current_npcs)
        ? session.current_npcs
        : [];

    npcsSource.forEach((entry) => {
      if (isAnomalousNpc(entry)) return;
      const name = normalizeActorName(entry);
      if (name) seenNpc.add(name.toLowerCase());
    });

    if (Array.isArray(session?.party_npcs)) {
      session.party_npcs.forEach((entry) => {
        if (isAnomalousNpc(entry)) return;
        const name = normalizeActorName(entry);
        if (name) seenNpc.add(name.toLowerCase());
      });
    }

    const partyMembers = Array.isArray(session?.party_members) ? session.party_members : [];
    let humanRecipients = 0;
    partyMembers.forEach((member) => {
      if (!member) return;
      const uid = member.user_id;
      if (currentUserId !== null && currentUserId !== undefined && String(uid) === String(currentUserId)) {
        return;
      }
      humanRecipients += 1;
    });

    return seenNpc.size + humanRecipients;
  }, [presentNpcs, session?.current_npcs, session?.party_npcs, session?.party_members, currentUserId]);

  const handleStealthClick = () => {
    if (disabled || processing) return;
    if (inCombat) {
      if (isVanished) {
        onAction?.({
          choice_index: null,
          intent: 'stealth_backstab',
          combat_target: selectedCombatTarget || null,
          stance: 'stealth',
          is_stealth: true,
          direct_choice: {
            intent: 'stealth_backstab',
            label: `🗡️ ${t('stealth_dock.backstab', 'Flanking Backstab')}`,
            choice_type: 'MELEE_SLASHING_PIERCING',
            action_category: 'attack',
            attack_type: 'pierce',
            stance: 'stealth',
            is_stealth: true,
          },
        });
      } else {
        onAction?.({
          choice_index: null,
          intent: 'stealth_hide',
          combat_target: selectedCombatTarget || null,
          stance: 'stealth',
          is_stealth: true,
          custom_action_text: 'Attempt to vanish into cover and break line of sight.',
          direct_choice: {
            intent: 'stealth_hide',
            label: `🥷 ${t('stealth_dock.hide', 'Hide')}`,
            choice_type: 'STEALTH_VANISH',
            action_category: 'tactics',
            stance: 'stealth',
            is_stealth: true,
          },
        });
      }
      return;
    }
    onToggleStealth?.();
  };

  const stealthLabel = inCombat
    ? (isVanished ? t('stealth_dock.backstab', 'Backstab') : t('stealth_dock.hide', 'Hide'))
    : (isStealthActive ? t('stealth_dock.sneaking', 'Sneaking') : t('stealth_dock.stealth', 'Stealth'));

  const stealthTooltip = inCombat
    ? (isVanished
        ? t('stealth_dock.tooltip_combat_backstab', 'Strike from the shadows with a guaranteed flanking backstab')
        : t('stealth_dock.tooltip_combat_hide', 'Attempt to vanish into shadows (AGI check vs Enemy PER)'))
    : (isStealthActive
        ? t('stealth_dock.tooltip_drop_stealth', 'Drop out of Stealth Mode')
        : t('stealth_dock.tooltip_enter_stealth', 'Enter Stealth Stance (Covert Actions)'));

  const examineLabel = inCombat
    ? t('stealth_dock.intel', 'Intel')
    : t('stealth_dock.examine', 'Examine');

  const examineTooltip = inCombat
    ? t('stealth_dock.tooltip_intel_zero_turn', 'Inspect live combat stats, status effects, and tactical leads (0 turns)')
    : t('stealth_dock.tooltip_examine_zero_turn', 'Inspect surroundings, people present, and clues without advancing the turn (0 turns)');

  const tilePadding = compact ? 'px-1.5 py-1.5' : 'px-1.5 py-2';
  const tileBaseClass = `relative flex flex-col items-center justify-center gap-1 rounded-xl ${tilePadding} border transition-colors text-center min-w-0 disabled:opacity-40 disabled:cursor-not-allowed`;

  return (
    <div className="grid grid-cols-4 gap-1.5" role="toolbar" aria-label={t('nav.actions_dock', 'Special Actions')}>
      {/* 1. Stealth / Hide / Backstab */}
      <MotionButton
        type="button"
        disabled={disabled || processing}
        onClick={handleStealthClick}
        title={stealthTooltip}
        className={`${tileBaseClass} ${
          inCombat && isVanished
            ? 'bg-rose-500/20 border-rose-400/55 text-rose-200 hover:bg-rose-500/30'
            : isStealthActive
              ? 'bg-emerald-500/20 border-emerald-400/55 text-emerald-200 hover:bg-emerald-500/30'
              : 'bg-white/5 border-fantasy-border/35 text-gray-200 hover:bg-white/10 hover:border-fantasy-accent/50'
        }`}
      >
        {inCombat && isVanished ? (
          <Swords size={15} className="shrink-0 text-rose-300" />
        ) : (
          <EyeOff
            size={15}
            className={`shrink-0 ${isStealthActive ? 'text-emerald-300' : 'text-gray-300'}`}
          />
        )}
        <span className="text-[11px] font-semibold leading-tight truncate w-full">
          {stealthLabel}
        </span>
        {(isStealthActive || (inCombat && isVanished)) && (
          <span
            className={`absolute -top-1.5 -right-1 px-1.5 py-0.5 rounded-full text-[9px] font-bold leading-tight border shadow-sm ${
              detectionPct >= 70
                ? 'bg-rose-600/90 text-white border-rose-300/60'
                : 'bg-emerald-600/90 text-white border-emerald-300/60'
            }`}
          >
            {detectionPct > 0 ? `${detectionPct}%` : t('stealth_dock.on', 'ON')}
          </span>
        )}
      </MotionButton>

      {/* 2. Examine / Intel (0-turn async) */}
      <MotionButton
        type="button"
        disabled={disabled || !session?.id}
        onClick={() => onOpenExamine?.()}
        title={examineTooltip}
        className={`${tileBaseClass} ${
          inCombat
            ? 'bg-sky-500/15 border-sky-400/45 text-sky-200 hover:bg-sky-500/25'
            : 'bg-white/5 border-fantasy-border/35 text-gray-200 hover:bg-white/10 hover:border-fantasy-accent/50'
        }`}
      >
        <Eye size={15} className={`shrink-0 ${inCombat ? 'text-sky-300' : 'text-fantasy-accent'}`} />
        <span className="text-[11px] font-semibold leading-tight truncate w-full">
          {examineLabel}
        </span>
      </MotionButton>

      {/* 3. Use Item */}
      <MotionButton
        type="button"
        disabled={disabled || processing}
        onClick={() => onOpenQuickBelt?.()}
        title={t('stealth_dock.tooltip_use_item', 'Use potions, consumables, or throwables')}
        className={`${tileBaseClass} bg-white/5 border-fantasy-border/35 text-gray-200 hover:bg-white/10 hover:border-emerald-400/50`}
      >
        <FlaskConical size={15} className="shrink-0 text-emerald-300" />
        <span className="text-[11px] font-semibold leading-tight truncate w-full">
          {t('stealth_dock.use_item', 'Use Item')}
        </span>
        {usableCount > 0 && (
          <span className="absolute -top-1.5 -right-1 min-w-[18px] h-[18px] px-1 flex items-center justify-center rounded-full bg-emerald-600/90 text-white text-[9.5px] font-bold border border-emerald-300/50 shadow-sm">
            {usableCount}
          </span>
        )}
      </MotionButton>

      {/* 4. Give / Gift */}
      <MotionButton
        type="button"
        disabled={disabled || processing || inCombat || giftableItemCount === 0 || recipientCount === 0}
        onClick={() => onOpenGiveGift?.()}
        title={
          inCombat
            ? t('gift.disabled_in_combat', 'Cannot offer peaceful gifts during combat')
            : recipientCount === 0
              ? t('gift.no_recipients', 'No nearby allies or NPCs available')
              : giftableItemCount === 0
                ? t('gift.no_items', 'No giftable items in your backpack')
                : t('stealth_dock.tooltip_gift', 'Give or gift an item to a party member or present NPC (1 turn)')
        }
        className={`${tileBaseClass} bg-white/5 border-fantasy-border/35 text-gray-200 hover:bg-white/10 hover:border-amber-400/50`}
      >
        <Gift size={15} className="shrink-0 text-amber-300" />
        <span className="text-[11px] font-semibold leading-tight truncate w-full">
          {t('stealth_dock.gift', 'Gift')}
        </span>
        {recipientCount > 0 && !inCombat && (
          <span className="absolute -top-1.5 -right-1 min-w-[18px] h-[18px] px-1 flex items-center justify-center rounded-full bg-amber-600/90 text-white text-[9.5px] font-bold border border-amber-300/50 shadow-sm">
            {recipientCount}
          </span>
        )}
      </MotionButton>
    </div>
  );
};

export default TacticalActionDock;
