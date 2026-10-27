import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  Eye, EyeOff, Sparkles, Gift, Package, Clock, Smartphone,
  Search, ShieldAlert, Target, Zap, Loader2, ArrowRight
} from 'lucide-react';

const TacticalActionDock = ({
  session,
  inventoryHook,
  phoneHook,
  isStealthActive,
  onToggleStealth,
  onOpenPhone,
  onClosePhone,
  phoneOpen,
  onAction,
  selectedCombatTarget,
  processing,
  onOpenTimeSkip,
  onOpenQuickBelt,
  onOpenGiveGift,
  isMobile = false
}) => {
  const { t } = useTranslation();

  const inCombat = typeof session?.is_in_combat === 'boolean'
    ? session.is_in_combat
    : Boolean(
        session?.in_combat ||
        session?.combat_state?.in_combat ||
        (session?.nearby_enemies || []).some((e) => e && (e.hp ?? 1) > 0) ||
        (session?.monsters || []).some((m) => m && (m.hp ?? 1) > 0)
      );

  const npcs = (session?.current_npcs || []).map((n) =>
    typeof n === 'string' ? n : n?.name
  ).filter(Boolean);

  const usableItems = (inventoryHook?.items || []).filter((item) => {
    const type = String(item.type || item.item_type || '').toLowerCase();
    const name = String(item.name || '').toLowerCase();
    return (
      type.includes('potion') ||
      type.includes('consumable') ||
      type.includes('food') ||
      type.includes('remedy') ||
      name.includes('potion') ||
      name.includes('elixir') ||
      name.includes('snack')
    );
  });

  const hasPhoneNotifications = Boolean(
    phoneHook?.appointments?.length > 0 || phoneHook?.mediaGallery?.length > 0
  );

  const stealthState = session?.stealth_state || {};
  const detectionMeter = typeof stealthState.detection_meter === 'number' ? stealthState.detection_meter : 0;
  const alertLevel = String(stealthState.alert_level || 'unaware').toLowerCase();

  const handleStealthClick = async () => {
    if (processing) return;
    if (inCombat) {
      const activeDeck =
        (selectedCombatTarget && session?.combat_decks_by_target?.[selectedCombatTarget]) ||
        session?.combat_deck ||
        {};
      if (stealthState.combat_vanished) {
        const backstabCard =
          (activeDeck.attacks || []).find(
            (a) => a && (a.stance === 'stealth' || String(a.label || '').toLowerCase().includes('backstab'))
          ) || {
            label: '🗡️ Flanking Backstab',
            choice_type: 'MELEE_SLASHING_PIERCING',
            action_category: 'attack',
            attack_type: 'pierce',
            stat: 'AGI',
            requirement: 0,
            mp_cost: 0,
            stance: 'stealth',
            is_stealth: true
          };
        await onAction({
          label: backstabCard.label,
          direct_choice: { ...backstabCard, stance: 'stealth', is_stealth: true },
          combat_target: selectedCombatTarget,
          stance: 'stealth',
          is_stealth: true
        });
      } else {
        const vanishCard =
          (activeDeck.tactics || []).find((c) => c && c.choice_type === 'STEALTH_VANISH') || {
            label: '💨 Vanish into Shadows',
            choice_type: 'STEALTH_VANISH',
            action_category: 'tactics',
            stat: 'AGI',
            requirement: 8,
            mp_cost: 0,
            stance: 'stealth',
            is_stealth: true
          };
        await onAction({
          label: vanishCard.label,
          direct_choice: { ...vanishCard, stance: 'stealth', is_stealth: true },
          combat_target: selectedCombatTarget,
          stance: 'stealth',
          is_stealth: true
        });
      }
    } else {
      onToggleStealth();
    }
  };

  // Quick Action Handlers
  const handleThrow = async () => {
    if (processing) return;
    if (inCombat) {
      const target = selectedCombatTarget || 'enemy';
      await onAction({
        custom_action_text: `I throw a tactical projectile at ${target}.`,
        combat_target: selectedCombatTarget
      });
    } else {
      await onAction({
        custom_action_text: `I throw a small stone to create a noise distraction and divert attention.`,
        intent: 'stealth_covert'
      });
    }
  };

  const handleTakeLoot = async () => {
    if (processing) return;
    if (inCombat) {
      await onAction({
        custom_action_text: `I quickly scavenge the immediate ground for useful tactical items or weapons.`
      });
    } else {
      await onAction({
        custom_action_text: `I search the immediate area and take any accessible items, valuables, or clues.`,
        intent: 'investigate_clue'
      });
    }
  };

  const handleExamineScout = async () => {
    if (processing) return;
    if (inCombat) {
      const target = selectedCombatTarget || 'the battlefield';
      await onAction({
        custom_action_text: `I carefully observe ${target} to assess weaknesses and threat positioning.`,
        stat: 'PER',
        combat_target: selectedCombatTarget
      });
    } else {
      await onAction({
        custom_action_text: `I carefully examine my surroundings, scouting for hidden details, exits, and hazards.`,
        stat: 'PER',
        intent: 'area_scout'
      });
    }
  };

  const stealthBadge = inCombat && stealthState.combat_vanished
    ? t('stealth_dock.vanished', 'VANISHED')
    : !isStealthActive
    ? null
    : detectionMeter > 0
    ? `${detectionMeter}%`
    : t('stealth_dock.on', 'ON');
  const stealthTone = !isStealthActive && !(inCombat && stealthState.combat_vanished)
    ? ''
    : alertLevel === 'detected'
    ? 'is-danger'
    : alertLevel === 'searching' || alertLevel === 'suspicious'
    ? 'is-warn'
    : 'is-active';

  const deviceName = phoneHook?.branding?.device_name || 'Smartphone';

  const tiles = [
    {
      id: 'stealth',
      emoji: '🥷',
      label: inCombat
        ? (stealthState.combat_vanished ? t('stealth_dock.backstab', 'Backstab') : t('stealth_dock.hide', 'Hide'))
        : (isStealthActive ? t('stealth_dock.sneaking', 'Sneaking') : t('stealth_dock.stealth', 'Stealth')),
      title: inCombat
        ? (stealthState.combat_vanished
            ? t('stealth_dock.tooltip_combat_backstab', 'Strike from the shadows with a guaranteed flanking backstab')
            : t('stealth_dock.tooltip_combat_hide', 'Attempt to vanish into shadows (AGI check vs Enemy PER)'))
        : isStealthActive
        ? t('stealth_dock.tooltip_drop_stealth', 'Drop out of Stealth Mode')
        : t('stealth_dock.tooltip_enter_stealth', 'Enter Stealth Stance (Covert Actions)'),
      onClick: handleStealthClick,
      disabled: processing,
      badge: stealthBadge,
      tone: stealthTone,
      pressed: isStealthActive || Boolean(inCombat && stealthState.combat_vanished),
    },
    {
      id: 'throw',
      emoji: '🎯',
      label: inCombat ? t('stealth_dock.throw', 'Throw') : t('stealth_dock.distract', 'Distract'),
      title: inCombat
        ? t('stealth_dock.tooltip_throw', 'Throw weapon/projectile at active target (AGI)')
        : t('stealth_dock.tooltip_distract', 'Throw a distraction to divert attention (AGI)'),
      onClick: handleThrow,
      disabled: processing,
    },
    {
      id: 'quick',
      emoji: '🧪',
      label: 'Quick Use',
      title: 'Open Quick Consumable Belt (Potions, Food, Buffs)',
      onClick: onOpenQuickBelt,
      disabled: processing,
      badge: usableItems.length > 0 ? usableItems.length : null,
    },
    {
      id: 'gift',
      emoji: '🎁',
      label: 'Gift',
      title: inCombat
        ? 'Cannot give gifts during combat'
        : npcs.length === 0
        ? 'No NPCs present in this scene to give gifts to'
        : 'Give an item/gift to a nearby NPC',
      onClick: onOpenGiveGift,
      disabled: processing || inCombat || npcs.length === 0,
      badge: npcs.length > 0 && !inCombat ? npcs.length : null,
    },
    {
      id: 'loot',
      emoji: '🔍',
      label: inCombat ? 'Scavenge' : 'Loot',
      title: inCombat ? 'Scavenge ground for weapons/supplies' : 'Search immediate area for items, loot, and clues',
      onClick: handleTakeLoot,
      disabled: processing,
    },
    {
      id: 'examine',
      emoji: '👁️',
      label: inCombat ? 'Assess' : 'Examine',
      title: inCombat ? 'Assess threat and enemy positioning (PER)' : 'Carefully scout surroundings and search for clues (PER)',
      onClick: handleExamineScout,
      disabled: processing,
    },
    {
      id: 'time',
      emoji: '⏳',
      label: session?.sleep_context?.can_sleep === false ? 'Wait' : 'Rest',
      title: inCombat ? 'Cannot rest during combat' : 'Open Chronos Dial to advance time and rest',
      onClick: onOpenTimeSkip,
      disabled: processing || inCombat,
    },
    {
      id: 'phone',
      icon: Smartphone,
      label: deviceName,
      title: phoneOpen ? 'Close Smartphone Window' : `Open ${deviceName}`,
      onClick: () => (phoneOpen && onClosePhone ? onClosePhone() : onOpenPhone()),
      disabled: processing,
      dot: hasPhoneNotifications,
      pressed: phoneOpen,
      tone: phoneOpen ? 'is-active' : '',
    },
  ];

  return (
    <div className="select-none space-y-1.5">
      {isStealthActive && (
        <div className={`flex items-center justify-center gap-1.5 rounded-lg px-2 py-1 text-[11px] font-semibold ${
          alertLevel === 'detected'
            ? 'bg-red-500/15 text-red-300'
            : alertLevel === 'searching' || alertLevel === 'suspicious'
            ? 'bg-amber-500/15 text-amber-300'
            : 'bg-violet-500/15 text-violet-300'
        }`}>
          <span>🥷</span>
          <span>{detectionMeter > 0 ? `${alertLevel.charAt(0).toUpperCase()}${alertLevel.slice(1)} · ${detectionMeter}%` : 'Stealth mode on'}</span>
        </div>
      )}
      <div className={`grid grid-cols-4 ${isMobile ? 'gap-1.5' : 'gap-1'}`}>
        {tiles.map((tile) => (
          <button
            key={tile.id}
            type="button"
            onClick={tile.onClick}
            disabled={tile.disabled}
            title={tile.title}
            aria-label={tile.title}
            aria-pressed={tile.pressed ?? undefined}
            className={`hk-dock-tile ${tile.tone || ''}`}
          >
            <span className="relative grid place-items-center h-6">
              {tile.icon ? <tile.icon size={17} /> : <span className="text-base leading-none">{tile.emoji}</span>}
              {tile.dot && <span className="absolute -top-0.5 -right-1.5 w-2 h-2 rounded-full bg-pink-400 animate-pulse" />}
            </span>
            <span className="block w-full truncate text-[10.5px] font-semibold leading-tight">{tile.label}</span>
            {tile.badge != null && <span className="hk-dock-badge">{tile.badge}</span>}
          </button>
        ))}
      </div>
    </div>
  );
};

export default TacticalActionDock;
