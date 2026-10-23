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

  const inCombat = Boolean(
    session?.in_combat ||
    session?.combat_state?.in_combat ||
    (session?.nearby_enemies && session.nearby_enemies.length > 0) ||
    (session?.monsters && session.monsters.length > 0)
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
      if (stealthState.combat_vanished) {
        await onAction({
          custom_action_text: "I strike from the shadows with a surprise flanking backstab!",
          choice_type: "MELEE_SLASHING_PIERCING",
          action_category: "attack",
          attack_type: "pierce",
          stat: "AGI",
          stance: "stealth",
          is_stealth: true
        });
      } else {
        await onAction({
          custom_action_text: "I slip into the shadows and attempt to vanish from enemy sight.",
          choice_type: "STEALTH_VANISH",
          action_category: "tactics",
          stat: "AGI",
          stance: "stealth",
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

  return (
    <div className="space-y-1.5 select-none">
      {/* Dock Title & Stance Header */}
      <div className="flex items-center justify-between px-1">
        <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-gray-400 flex items-center gap-1">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
          <span>Tactical Field Actions</span>
        </span>
        {isStealthActive && (
          <span className={`text-[9.5px] font-mono font-extrabold uppercase px-1.5 py-0.2 rounded border ${
            alertLevel === 'detected'
              ? 'bg-red-950 border-red-500 text-red-300 animate-pulse'
              : alertLevel === 'searching'
              ? 'bg-amber-950 border-amber-500 text-amber-300 animate-pulse'
              : alertLevel === 'suspicious'
              ? 'bg-yellow-950 border-yellow-500 text-yellow-300'
              : 'bg-violet-950 border-violet-500 text-violet-300 animate-pulse'
          }`}>
            🥷 {detectionMeter > 0 ? `${alertLevel.toUpperCase()} (${detectionMeter}%)` : 'Stealth Mode ON'}
          </span>
        )}
      </div>

      {/* 8-Button Matrix (2 columns × 4 rows) */}
      <div className="grid grid-cols-2 gap-1.5">
        
        {/* 1. Stealth Stance Toggle */}
        <button
          type="button"
          disabled={processing}
          onClick={handleStealthClick}
          title={
            inCombat
              ? "Attempt to vanish into shadows (AGI check vs Enemy PER)"
              : isStealthActive
              ? "Drop out of Stealth Mode"
              : "Enter Stealth Stance (Covert Actions)"
          }
          className={`flex items-center justify-between p-2 rounded-lg border transition-all disabled:opacity-50 text-left ${
            isStealthActive
              ? alertLevel === 'searching'
                ? 'bg-gradient-to-r from-amber-950/80 to-yellow-900/60 border-amber-500 text-amber-100 ring-2 ring-amber-500/40 shadow-[0_0_12px_rgba(245,158,11,0.3)]'
                : alertLevel === 'suspicious'
                ? 'bg-gradient-to-r from-yellow-950/80 to-amber-900/60 border-yellow-500 text-yellow-100 ring-2 ring-yellow-500/40 shadow-[0_0_12px_rgba(234,179,8,0.3)]'
                : 'bg-gradient-to-r from-violet-950/80 to-purple-900/60 border-violet-400 text-violet-100 ring-2 ring-violet-500/40 shadow-[0_0_12px_rgba(168,85,247,0.3)]'
              : 'bg-black/55 border-fantasy-border/80 hover:border-violet-500/60 text-gray-300 hover:text-white'
          }`}
        >
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="text-sm shrink-0">🥷</span>
            <span className="text-xs font-bold truncate">
              {inCombat ? (stealthState.combat_vanished ? 'Backstab' : 'Hide / Ambush') : (isStealthActive ? 'Sneaking' : 'Stealth')}
            </span>
          </div>
          <span className={`text-[9px] font-mono font-bold px-1 rounded uppercase ${
            inCombat && stealthState.combat_vanished
              ? 'bg-violet-900 text-violet-200 border border-violet-400/50'
              : !isStealthActive
              ? 'bg-black/60 text-gray-400'
              : alertLevel === 'detected'
              ? 'bg-red-800 text-red-100 animate-pulse'
              : alertLevel === 'searching'
              ? 'bg-amber-800 text-amber-100 animate-pulse'
              : alertLevel === 'suspicious'
              ? 'bg-yellow-800 text-yellow-100'
              : 'bg-violet-800 text-violet-100'
          }`}>
            {inCombat && stealthState.combat_vanished
              ? 'VANISHED'
              : !isStealthActive
              ? 'OFF'
              : detectionMeter > 0
              ? `${alertLevel.slice(0, 4).toUpperCase()} ${detectionMeter}%`
              : 'HIDDEN'}
          </span>
        </button>

        {/* 2. Throw / Distract */}
        <button
          type="button"
          disabled={processing}
          onClick={handleThrow}
          title={inCombat ? "Throw weapon/projectile at active target" : "Throw a distraction to divert attention"}
          className="flex items-center justify-between p-2 rounded-lg bg-black/55 border border-fantasy-border/80 hover:border-amber-500/60 hover:bg-neutral-900/60 text-gray-300 hover:text-white transition-all disabled:opacity-50 text-left"
        >
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="text-sm shrink-0">🎯</span>
            <span className="text-xs font-bold truncate">
              {inCombat ? 'Throw Attack' : 'Distract'}
            </span>
          </div>
          <span className="text-[9px] font-mono font-bold text-gray-400 uppercase bg-black/60 px-1 rounded">
            AGI
          </span>
        </button>

        {/* 3. Quick Use (Consumable Belt) */}
        <button
          type="button"
          disabled={processing}
          onClick={onOpenQuickBelt}
          title="Open Quick Consumable Belt (Potions, Food, Buffs)"
          className="flex items-center justify-between p-2 rounded-lg bg-black/55 border border-fantasy-border/80 hover:border-emerald-500/60 hover:bg-neutral-900/60 text-gray-300 hover:text-white transition-all disabled:opacity-50 text-left"
        >
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="text-sm shrink-0">🧪</span>
            <span className="text-xs font-bold truncate">Quick Use</span>
          </div>
          {usableItems.length > 0 && (
            <span className="text-[9px] font-mono font-bold px-1 rounded bg-emerald-950/80 border border-emerald-600/60 text-emerald-300">
              {usableItems.length}
            </span>
          )}
        </button>

        {/* 4. Give Gift to NPC */}
        <button
          type="button"
          disabled={processing || inCombat || npcs.length === 0}
          onClick={onOpenGiveGift}
          title={
            inCombat
              ? "Cannot give gifts during combat"
              : npcs.length === 0
                ? "No NPCs present in this scene to give gifts to"
                : "Give an item/gift to a nearby NPC"
          }
          className={`flex items-center justify-between p-2 rounded-lg border transition-all text-left ${
            inCombat || npcs.length === 0
              ? 'bg-black/30 border-fantasy-border/40 text-gray-500 cursor-not-allowed opacity-60'
              : 'bg-black/55 border-fantasy-border/80 hover:border-pink-500/60 hover:bg-neutral-900/60 text-gray-300 hover:text-white'
          }`}
        >
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="text-sm shrink-0">🎁</span>
            <span className="text-xs font-bold truncate">Give Gift</span>
          </div>
          {npcs.length > 0 && !inCombat && (
            <span className="text-[9px] font-mono font-bold px-1 rounded bg-pink-950/80 border border-pink-700/60 text-pink-300">
              {npcs.length} NPC{npcs.length > 1 ? 's' : ''}
            </span>
          )}
        </button>

        {/* 5. Take / Loot */}
        <button
          type="button"
          disabled={processing}
          onClick={handleTakeLoot}
          title={inCombat ? "Scavenge ground for weapons/supplies" : "Search immediate area for items, loot, and clues"}
          className="flex items-center justify-between p-2 rounded-lg bg-black/55 border border-fantasy-border/80 hover:border-amber-500/60 hover:bg-neutral-900/60 text-gray-300 hover:text-white transition-all disabled:opacity-50 text-left"
        >
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="text-sm shrink-0">🔍</span>
            <span className="text-xs font-bold truncate">
              {inCombat ? 'Scavenge' : 'Take / Loot'}
            </span>
          </div>
          <span className="text-[9px] font-mono font-bold text-gray-400 uppercase bg-black/60 px-1 rounded">
            Loot
          </span>
        </button>

        {/* 6. Examine / Scout */}
        <button
          type="button"
          disabled={processing}
          onClick={handleExamineScout}
          title={inCombat ? "Assess threat and enemy positioning" : "Carefully scout surroundings and search for clues"}
          className="flex items-center justify-between p-2 rounded-lg bg-black/55 border border-fantasy-border/80 hover:border-cyan-500/60 hover:bg-neutral-900/60 text-gray-300 hover:text-white transition-all disabled:opacity-50 text-left"
        >
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="text-sm shrink-0">👁️</span>
            <span className="text-xs font-bold truncate">
              {inCombat ? 'Assess' : 'Examine'}
            </span>
          </div>
          <span className="text-[9px] font-mono font-bold text-gray-400 uppercase bg-black/60 px-1 rounded">
            PER
          </span>
        </button>

        {/* 7. Rest / Time Skip (Genshin Clock Dial) */}
        <button
          type="button"
          disabled={processing || inCombat}
          onClick={onOpenTimeSkip}
          title={inCombat ? "Cannot rest during combat" : "Open Chronos Dial to advance time and rest"}
          className={`flex items-center justify-between p-2 rounded-lg border transition-all text-left ${
            inCombat
              ? 'bg-black/30 border-fantasy-border/40 text-gray-500 cursor-not-allowed opacity-60'
              : 'bg-black/55 border-fantasy-border/80 hover:border-amber-500/60 hover:bg-neutral-900/60 text-gray-300 hover:text-white'
          }`}
        >
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="text-sm shrink-0">⏳</span>
            <span className="text-xs font-bold truncate">Time Skip</span>
          </div>
          <span className="text-[9px] font-mono font-bold text-amber-400/90 uppercase bg-black/60 px-1 rounded">
            Rest
          </span>
        </button>

        {/* 8. Smartphone OS Launcher */}
        <button
          type="button"
          disabled={processing}
          onClick={() => (phoneOpen && onClosePhone ? onClosePhone() : onOpenPhone())}
          title={phoneOpen ? "Close Smartphone Window" : `Open ${phoneHook?.branding?.device_name || 'Smartphone'}`}
          className={`flex items-center justify-between p-2 rounded-lg border transition-all text-left ${
            phoneOpen
              ? 'bg-pink-950/80 border-pink-500 text-pink-100 ring-2 ring-pink-500/40 shadow-sm'
              : 'bg-black/55 border-fantasy-border/80 hover:border-pink-500/70 hover:bg-neutral-900/60 text-gray-200 hover:text-pink-300'
          }`}
        >
          <div className="flex items-center gap-1.5 min-w-0">
            <Smartphone size={15} className={phoneOpen ? "text-pink-300 animate-pulse" : "text-pink-400"} />
            <span className="text-xs font-bold truncate">
              {phoneHook?.branding?.device_name || 'Smartphone'}
            </span>
          </div>
          {hasPhoneNotifications && (
            <span className="w-2 h-2 rounded-full bg-pink-400 animate-pulse shadow-[0_0_8px_rgba(244,114,182,0.8)]" />
          )}
        </button>

      </div>
    </div>
  );
};

export default TacticalActionDock;
