import React, { useState } from 'react';
import { Send, Lock, Zap, RefreshCw, ChevronDown, ChevronUp } from 'lucide-react';

const STAT_EMOJI = {
  STR: '💪',
  PER: '👁️',
  END: '🛡️',
  CHA: '🗣️',
  INT: '🧠',
  AGI: '🏹',
  LUK: '🍀',
  ITEM: '🎒',
};

const getChoiceQuestIcon = (choice) => {
  if (!choice || typeof choice !== 'object') return null;
  if (choice.quest_icon) return choice.quest_icon;

  const rawLabel = String(choice.label || choice.text || choice.action || '');
  const rawL = rawLabel.toLowerCase();
  const qid = String(choice.quest_id || '').toLowerCase();
  const ctype = String(choice.contract_type || '').toLowerCase();

  // 1. Story Climax
  if (choice.is_climax_action || ctype === 'climax' || rawLabel.includes('⚡') || rawL.includes('[story climax]')) {
    return '⚡';
  }

  // 2. Story Quest Actions
  if (
    rawLabel.includes('⭐') ||
    rawL.includes('[story quest]') ||
    qid.includes('sq-') ||
    ctype.includes('story') ||
    choice.is_story_quest
  ) {
    return '⭐';
  }

  // 3. Bounty / Sub-Quest Actions
  if (
    choice.is_quest_action ||
    ['sub_quest', 'bounty', 'side_bounty', 'waypoint', 'skill_check', 'arrival', 'resource_progress'].includes(ctype) ||
    rawLabel.includes('🎯') ||
    rawL.includes('[bounty]') ||
    qid.includes('bnt-') ||
    qid.includes('qst-')
  ) {
    if (
      ['contract board', 'notice board', 'bounty board', 'bulletin board', 'quest board'].some((b) =>
        rawL.includes(b)
      )
    ) {
      return null;
    }
    return '🎯';
  }

  // 4. Meetup / Phone appointment
  if (rawLabel.includes('💌') || rawL.includes('[meetup]')) {
    return '💌';
  }

  // 5. Social & Character Interaction Archetypes
  if (
    rawLabel.includes('🎭') ||
    rawL.includes('[banter]') ||
    ['playfully tease', 'crack a joke', 'crack a playful', 'lighthearted joke', 'witty banter', 'playful joke'].some(
      (k) => rawL.includes(k)
    )
  ) {
    return '🎭';
  }
  if (
    rawLabel.includes('💖') ||
    rawL.includes('[affection]') ||
    rawL.includes('[flirt]') ||
    ['flirt with', 'compliment ', 'sincere compliment', 'confess feelings', 'affectionate', 'hold hands with'].some(
      (k) => rawL.includes(k)
    )
  ) {
    return '💖';
  }
  if (
    rawLabel.includes('🎲') ||
    rawL.includes('[challenge]') ||
    ['challenge ', 'arm-wrestle', 'friendly wager', 'friendly spar'].some((k) => rawL.includes(k))
  ) {
    return '🎲';
  }
  if (
    rawLabel.includes('💬') ||
    rawL.includes('[inquiry]') ||
    ['inquire about', 'ask about', 'ask if', 'ask her', 'ask him', 'ask them'].some((k) => rawL.includes(k)) ||
    (rawL.includes('ask ') && rawL.includes(' about '))
  ) {
    return '💬';
  }

  return null;
};

const isConversationalExitLabel = (rawL) => {
  return [
    'excuse yourself',
    'step away from',
    'take your leave',
    'end the conversation',
    'end conversation',
    'say goodbye',
    'bid farewell',
    'part ways',
    'wrap up the conversation',
    'polite farewell',
    'nod politely and leave',
  ].some((k) => rawL.includes(k)) || (rawL.startsWith('thank ') && (rawL.includes('look around') || rawL.includes('step away') || rawL.includes('excuse')));
};

const getChoiceSkillEmoji = (choice) => {
  if (!choice || typeof choice !== 'object') return '✨';
  if (choice.skill_emoji) return choice.skill_emoji;

  const stat = String(choice.stat || '').toUpperCase();
  const req = choice.requirement !== undefined ? Number(choice.requirement) : 5;
  const rawLabel = String(choice.label || choice.text || choice.action || '');
  const rawL = rawLabel.toLowerCase();

  if (stat === 'ITEM') return '🎒';

  const isFree = ['NONE', 'FREE', ''].includes(stat) || req <= 0;
  if (isFree) {
    if (
      ['contract board', 'notice board', 'bounty board', 'bulletin board', 'quest board', 'bulletin'].some((k) =>
        rawL.includes(k)
      )
    ) {
      return '📜';
    }
    if (
      ['flirt', 'compliment', 'praise', 'admire', 'cherish', 'confess', 'hug', 'kiss', 'affection', 'fond', 'hold hand'].some(
        (k) => rawL.includes(k)
      )
    ) {
      return '💖';
    }
    if (['joke', 'tease', 'banter', 'laugh', 'playful', 'ribbing', 'witty', 'humor', 'prank'].some((k) => rawL.includes(k))) {
      return '🎭';
    }
    if (isConversationalExitLabel(rawL)) {
      return '🚪';
    }
    if (
      [
        'talk', 'speak', 'discuss', 'ask', 'tell', 'consult', 'comfort', 'inquire',
        'reassure', 'address', 'greet', 'converse', 'propose', 'negotiate', 'chat',
        'whisper', 'confer', 'explain', 'advise', 'gauge', 'interview', 'say to', 'confront',
      ].some((k) => rawL.includes(k))
    ) {
      return '💬';
    }
    if (
      [
        'look around', 'inspect', 'examine', 'observe', 'scan', 'survey', 'view the',
        'look at the', 'check out the', 'read the', 'study the', 'take in the', 'search',
      ].some((k) => rawL.includes(k))
    ) {
      return '🔍';
    }
    if (['camp', 'tent'].some((k) => rawL.includes(k))) return '🏕️';
    if (['tea', 'coffee', 'drink', 'sip', 'tavern', 'snack', 'eat', 'brew', 'cup', 'ale', 'wine', 'hearth'].some((k) => rawL.includes(k))) {
      return '☕';
    }
    if (['rest', 'sit', 'relax', 'breathe', 'sleep', 'sofa', 'bench', 'couch', 'chair', 'nap'].some((k) => rawL.includes(k))) {
      return '🛋️';
    }
    if (['shelf', 'bookshelf', 'desk', 'drawer', 'tinker', 'browse', 'props', 'decor', 'cabinet', 'paperwork', 'documents', 'records'].some((k) => rawL.includes(k))) {
      return '🖐️';
    }
    if (['equipment', 'gear', 'supplies', 'backpack', 'pack', 'prepare', 'sharpen'].some((k) => rawL.includes(k))) {
      return '🎒';
    }
    if (
      [
        'travel', 'head to', 'head toward', 'depart', 'walk to', 'walk toward', 'exit', 'leave',
        'slip out', 'make your way', 'return to', 'step out', 'step into', 'go to', 'move to',
        'journey', 'navigate to',
      ].some((k) => rawL.includes(k)) ||
      /\b(travel|depart|exit|leave|journey|flee)\b/.test(rawL)
    ) {
      return '🚶';
    }
    if (['scout', 'delve', 'forage', 'track', 'trail', 'wilderness', 'ruins', 'woods', 'forest', 'patrol'].some((k) => rawL.includes(k))) {
      return '🧭';
    }
    return '✨';
  }

  return STAT_EMOJI[stat] || '❔';
};

const getChoiceEmoji = (choice) => {
  if (!choice || typeof choice !== 'object') return '✨';
  if (choice.emoji) return choice.emoji;
  const questIcon = getChoiceQuestIcon(choice);
  const skillEmoji = getChoiceSkillEmoji(choice);
  if (questIcon && skillEmoji && questIcon !== skillEmoji) {
    return `${questIcon} ${skillEmoji}`;
  }
  return questIcon || skillEmoji || '✨';
};

const detectMerchantAvailableClient = (session, inCombat) => {
  if (!session || inCombat) return { available: false, label: 'Talk to Merchant' };
  if (typeof session.merchant_available === 'boolean') {
    return {
      available: session.merchant_available,
      label: session.merchant_action_label || 'Visit Market / Shop',
    };
  }
  const merchant = session.merchant || {};
  const loc = String(session.current_location || '').toLowerCase();
  const shopKeywords = [
    'shop', 'store', 'market', 'bazaar', 'emporium', 'café', 'cafe', 'pharmacy',
    'armory', 'blacksmith', 'weaponsmith', 'quartermaster', 'convenience', 'boutique',
    'bakery', 'stall', 'merchant', 'trader', 'noodle bar', 'canteen', 'saloon', 'tavern',
    'inn', 'trading post', 'general store', 'guild shop', 'alchemist', 'herbalist', 'forge',
  ];
  const hasShopLoc = shopKeywords.some((k) => loc.includes(k));
  const isAvailable = Boolean(merchant.available || merchant.active || hasShopLoc);
  const flavorName = merchant.flavor_name;
  let label = 'Talk to Merchant';
  if (hasShopLoc && !flavorName) {
    label = 'Visit Market / Shop';
  } else if (flavorName) {
    label = `Trade with ${flavorName}`;
  }
  return { available: isAvailable, label };
};

const getOddsBadgeClass = (pct) => {
  if (pct > 70) {
    return 'text-emerald-300 bg-emerald-950/60 border-emerald-700/50';
  }
  if (pct < 40) {
    return 'text-rose-300 bg-rose-950/60 border-rose-700/50';
  }
  return 'text-amber-300 bg-amber-950/60 border-amber-700/50';
};

const ActionPanel = ({
  choices,
  session,
  selectedCombatTarget,
  onSelectCombatTarget,
  onAction,
  onRetry,
  onOpenMerchant,
  showPercentages = true,
  processing,
  isStreaming,
  waitingForParty,
  partyStatus
}) => {
  const [customAction, setCustomAction] = useState('');
  const [combatTab, setCombatTab] = useState('attacks'); // 'attacks' | 'spells' | 'tactics' | 'choices'
  const [isCollapsed, setIsCollapsed] = useState(false);
  const isBusy = processing || isStreaming;

  const livingEnemies = (session?.nearby_enemies || session?.monsters || []).filter(
    (e) => e && e.name && (e.hp ?? 1) > 0
  );
  const inCombat = Boolean(session?.is_in_combat || livingEnemies.length > 0);
  const activeTargetObj =
    livingEnemies.find((e) => e.name === selectedCombatTarget) || livingEnemies[0] || null;
  const selectedTargetName = activeTargetObj?.name || selectedCombatTarget || null;

  const { available: merchantAvailable, label: merchantActionLabel } = detectMerchantAvailableClient(
    session,
    inCombat
  );

  const combatDeck = session?.combat_decks_by_target?.[selectedTargetName] || session?.combat_deck || {};
  const deckAttacks = combatDeck.attacks || [
    { label: '⚔️ Standard Strike', stat: 'STR', chance: 75, description: 'Reliable melee/weapon attack.' },
    { label: '💥 Heavy Power Blow', stat: 'STR', chance: 55, description: 'High-impact strike with extra damage.' },
    { label: '🗡️ Precision Vital Strike', stat: 'AGI', chance: 65, description: 'Aim for weak points.' }
  ];
  const deckSpells = combatDeck.spells || [];
  const deckTactics = combatDeck.tactics || [
    { label: '🛡️ Defensive Stance', stat: 'END', chance: 85, description: 'Brace against incoming attacks.' },
    { label: '👁️ Analyze Weakness', stat: 'PER', chance: 75, description: 'Study enemy patterns for tactical advantage.' },
    { label: '💨 Evasive Feint', stat: 'AGI', chance: 70, description: 'Outmaneuver and reposition.' }
  ];
  const fleeChoice = combatDeck.flee || {
    label: '🏃 Flee Battle',
    text: 'Attempt to disengage and flee from combat!',
    stat: 'AGI',
    action_type: 'flee'
  };

  const handleCycleTarget = () => {
    if (livingEnemies.length <= 1 || !onSelectCombatTarget) return;
    const idx = livingEnemies.findIndex((e) => e.name === selectedTargetName);
    const next = livingEnemies[(idx + 1) % livingEnemies.length];
    if (next) onSelectCombatTarget(next.name);
  };

  const handleCustomSubmit = (e) => {
    e.preventDefault();
    if (customAction.trim() && !isBusy && !waitingForParty) {
      const text = customAction.trim();
      onAction({
        custom_action_text: text,
        custom_text: text,
        combat_target: inCombat ? selectedTargetName : null
      });
      setCustomAction('');
    }
  };

  if (waitingForParty) {
    return (
      <div className="shrink-0 w-full bg-fantasy-panel/95 backdrop-blur border-t border-fantasy-border px-4 py-3 shadow-2xl flex items-center justify-center gap-3 z-20">
        <Lock className="text-fantasy-accent animate-pulse shrink-0" size={20} />
        <div className="flex items-center gap-2">
          <h3 className="font-rpg text-base text-gray-200">Waiting for Party</h3>
          <span className="text-xs font-mono px-2 py-0.5 rounded bg-black/50 border border-fantasy-border text-gray-400">
            {partyStatus?.lockedCount} / {partyStatus?.total} Locked In
          </span>
        </div>
      </div>
    );
  }

  const totalChoiceCount = (choices?.length || 0) + (!inCombat && merchantAvailable && onOpenMerchant ? 1 : 0);

  return (
    <div className="shrink-0 w-full bg-fantasy-panel/95 backdrop-blur border-t border-fantasy-border px-3 md:px-5 py-2.5 shadow-2xl z-20">
      <div className="w-full flex flex-col gap-2">

        {!isCollapsed && (
          <>
            {/* Tactical Battle Deck when in combat */}
            {inCombat ? (
              <div className="space-y-1.5">
                {/* Top Combat Bar: Target Pill, Category Tabs, Flee & Retry */}
                <div className="flex flex-wrap items-center justify-between gap-1.5 pb-1.5 border-b border-red-900/50">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {activeTargetObj && (
                      <button
                        type="button"
                        onClick={handleCycleTarget}
                        title="Click to cycle target enemy"
                        className="px-2.5 py-0.5 rounded-full bg-red-950/80 hover:bg-red-900/80 border border-amber-500/60 text-[11px] font-mono font-bold text-amber-200 flex items-center gap-1 transition-colors"
                      >
                        <span>
                          🎯 {activeTargetObj.name} ({activeTargetObj.hp ?? activeTargetObj.max_hp ?? 100}/{activeTargetObj.max_hp ?? 100})
                        </span>
                      </button>
                    )}

                    <div className="flex items-center gap-1 bg-black/60 p-0.5 rounded-lg border border-fantasy-border">
                      {[
                        { id: 'attacks', label: '⚔️ Attack' },
                        { id: 'spells', label: `🔮 Spells${deckSpells.length ? ` (${deckSpells.length})` : ''}` },
                        { id: 'tactics', label: '🧠 Tactics' },
                        { id: 'choices', label: '📜 Scene Choices' }
                      ].map((tab) => (
                        <button
                          key={tab.id}
                          type="button"
                          onClick={() => setCombatTab(tab.id)}
                          className={`px-2 py-0.5 rounded text-[11px] font-bold transition-colors ${
                            combatTab === tab.id
                              ? 'bg-red-900/60 text-amber-300 border border-amber-500/50'
                              : 'text-gray-400 hover:text-gray-200'
                          }`}
                        >
                          {tab.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="flex items-center gap-1.5">
                    {session?.is_fallback_generation && onRetry && (
                      <button
                        type="button"
                        disabled={isBusy}
                        onClick={onRetry}
                        className="px-2 py-0.5 rounded bg-amber-950/70 hover:bg-amber-900 text-amber-200 border border-amber-600/60 text-[11px] font-bold flex items-center gap-1 transition-colors disabled:opacity-50"
                      >
                        <RefreshCw size={11} />
                        <span>Retry</span>
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={isBusy}
                      onClick={() => onAction({ direct_choice: fleeChoice, combat_target: selectedTargetName })}
                      className="px-2.5 py-0.5 rounded bg-neutral-900 hover:bg-red-950/70 text-gray-300 hover:text-red-200 border border-neutral-700 hover:border-red-700 text-[11px] font-bold transition-colors disabled:opacity-50"
                    >
                      🏃 Flee
                    </button>
                  </div>
                </div>

                {/* Active Combat Deck Cards (Compact Horizontal Rows, No Scrollbar) */}
                {combatTab === 'choices' ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 2xl:grid-cols-3 gap-1.5">
                    {(choices || []).map((choice, idx) => {
                      const pct = choice.success_pct !== undefined ? choice.success_pct : choice.chance;
                      const mpCost = choice.mp_cost || 0;
                      const choiceEmoji = getChoiceEmoji(choice);
                      const statName = String(choice.stat || 'FREE').toUpperCase();
                      const displayStat = statName === 'NONE' ? 'FREE' : statName;
                      return (
                        <button
                          key={idx}
                          onClick={() => onAction({ choice_index: idx, direct_choice: choice, combat_target: selectedTargetName })}
                          disabled={isBusy}
                          className="group flex items-center justify-between gap-2.5 px-3 py-1.5 rounded-lg bg-black/50 border border-fantasy-border hover:border-fantasy-accent hover:bg-fantasy-accent/10 transition-all disabled:opacity-50 text-left"
                        >
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-white/5 border border-white/10 text-[10px] font-mono font-bold uppercase text-fantasy-accent shrink-0">
                            <span className="text-xs leading-none">{choiceEmoji}</span>
                            <span>{displayStat}</span>
                          </span>
                          <span className="flex-1 min-w-0 text-xs md:text-[13px] font-medium text-gray-100 group-hover:text-white leading-snug">
                            {choice.label || choice.text}
                          </span>
                          <div className="flex items-center gap-1 shrink-0">
                            {mpCost > 0 && (
                              <span className="text-blue-400 font-mono flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded bg-blue-950/50 border border-blue-800/40">
                                <Zap size={10} /> {mpCost}
                              </span>
                            )}
                            {showPercentages && pct !== undefined && pct !== null && (
                              <span className={`px-1.5 py-0.5 rounded border font-mono text-[10px] font-bold ${getOddsBadgeClass(pct)}`}>
                                {pct}%
                              </span>
                            )}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-1.5">
                    {(combatTab === 'attacks' ? deckAttacks : combatTab === 'spells' ? deckSpells : deckTactics).length === 0 ? (
                      <div className="col-span-full text-center py-2 text-xs text-gray-500 italic">
                        No {combatTab} available right now. Study spellbooks or switch tabs!
                      </div>
                    ) : (
                      (combatTab === 'attacks' ? deckAttacks : combatTab === 'spells' ? deckSpells : deckTactics).map((item, idx) => {
                        const pct = item.success_pct !== undefined ? item.success_pct : item.chance;
                        const mpCost = item.mp_cost || 0;
                        const canAfford = item.can_afford !== false;
                        const itemStat = String(item.stat || 'STR').toUpperCase();
                        const itemEmoji = STAT_EMOJI[itemStat] || getChoiceEmoji(item);
                        return (
                          <button
                            key={idx}
                            type="button"
                            disabled={isBusy || !canAfford}
                            onClick={() => onAction({ direct_choice: item, combat_target: selectedTargetName })}
                            className="group flex items-center justify-between gap-2.5 px-3 py-1.5 rounded-lg bg-black/50 border border-red-900/60 hover:border-amber-400 hover:bg-red-950/30 transition-all disabled:opacity-40 text-left"
                          >
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-red-950/50 border border-red-800/40 text-[10px] font-mono font-bold uppercase text-amber-300 shrink-0">
                              <span className="text-xs leading-none">{itemEmoji}</span>
                              <span>{itemStat}</span>
                            </span>
                            <div className="flex-1 min-w-0">
                              <div className="text-xs md:text-[13px] font-semibold text-gray-100 group-hover:text-white leading-snug truncate">
                                {item.label || item.name || item.text}
                              </div>
                              {item.description && (
                                <div className="text-[10px] text-gray-400 truncate">{item.description}</div>
                              )}
                            </div>
                            <div className="flex items-center gap-1 shrink-0">
                              {mpCost > 0 && (
                                <span className="text-blue-400 font-mono flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded bg-blue-950/50 border border-blue-800/40">
                                  <Zap size={10} /> {mpCost}
                                </span>
                              )}
                              {showPercentages && pct !== undefined && pct !== null && (
                                <span className={`px-1.5 py-0.5 rounded border font-mono text-[10px] font-bold ${getOddsBadgeClass(pct)}`}>
                                  {pct}%
                                </span>
                              )}
                            </div>
                          </button>
                        );
                      })
                    )}
                  </div>
                )}
              </div>
            ) : (
              /* Non-Combat Choices Grid: Full-width compact horizontal rows with zero scrollbars */
              <div className="space-y-1.5">
                {session?.is_fallback_generation && onRetry && (
                  <div className="flex items-center justify-between bg-amber-950/40 border border-amber-700/50 px-3 py-1 rounded text-xs text-amber-200">
                    <span>⚠️ Fallback scene generation was used for this turn.</span>
                    <button
                      type="button"
                      disabled={isBusy}
                      onClick={onRetry}
                      className="px-2 py-0.5 rounded bg-amber-600/30 hover:bg-amber-600/50 text-amber-200 border border-amber-500/50 font-bold text-[11px] flex items-center gap-1 transition-colors"
                    >
                      <RefreshCw size={11} />
                      <span>🔄 Retry Generation</span>
                    </button>
                  </div>
                )}

                <div className="grid grid-cols-1 sm:grid-cols-2 2xl:grid-cols-3 gap-1.5">
                  {(choices || []).map((choice, idx) => {
                    const pct = choice.success_pct !== undefined ? choice.success_pct : choice.chance;
                    const mpCost = choice.mp_cost || 0;
                    const questIcon = getChoiceQuestIcon(choice);
                    const skillEmoji = getChoiceSkillEmoji(choice);
                    const choiceEmoji = getChoiceEmoji(choice);
                    const isQuestHighlighted = Boolean(questIcon && ['⭐', '🎯', '⚡'].includes(questIcon));
                    const rawStat = String(choice.stat || 'NONE').toUpperCase();
                    const isFreeAction = rawStat === 'NONE' || rawStat === 'FREE' || !rawStat;

                    let questBadge = null;
                    if (questIcon === '⚡') {
                      questBadge = {
                        icon: '⚡',
                        label: 'Story Climax',
                        className: 'bg-purple-500/25 border-purple-400/70 text-purple-200 shadow-[0_0_8px_rgba(168,85,247,0.3)]',
                      };
                    } else if (questIcon === '⭐') {
                      questBadge = {
                        icon: '⭐',
                        label: 'Story Quest',
                        className: 'bg-amber-500/25 border-amber-400/80 text-amber-200 shadow-[0_0_8px_rgba(245,158,11,0.3)]',
                      };
                    } else if (questIcon === '🎯') {
                      questBadge = {
                        icon: '🎯',
                        label: 'Bounty',
                        className: 'bg-cyan-500/25 border-cyan-400/70 text-cyan-200 shadow-[0_0_8px_rgba(6,182,212,0.25)]',
                      };
                    } else if (questIcon === '💌') {
                      questBadge = {
                        icon: '💌',
                        label: 'Meetup',
                        className: 'bg-pink-500/25 border-pink-400/70 text-pink-200',
                      };
                    }

                    const rawDisplayLabel = String(choice.label || choice.text || '');
                    const cleanDisplayLabel = rawDisplayLabel
                      .replace(/^(?:[⭐🎯⚡💌🔹\s]+|\s*\[(?:Story Quest|Story Climax|Bounty|Quest|Meetup)\]\s*)+/i, '')
                      .replace(/\s*\((?:STR|PER|END|CHA|INT|AGI|LUK)\)\s*$/i, '')
                      .trim() || rawDisplayLabel;

                    return (
                      <button
                        key={idx}
                        onClick={() => onAction({ choice_index: idx, direct_choice: choice })}
                        disabled={isBusy}
                        className={`group flex items-center justify-between gap-2 px-3 py-1.5 rounded-lg text-left transition-all disabled:opacity-50 ${
                          isQuestHighlighted
                            ? 'bg-amber-950/35 border border-amber-400/75 hover:border-amber-300 hover:bg-amber-900/45 shadow-[0_0_12px_rgba(245,158,11,0.16)]'
                            : 'bg-black/45 border border-fantasy-border hover:border-fantasy-accent hover:bg-fantasy-accent/10'
                        }`}
                      >
                        {/* Left: Quest Marker Badge + Stat Pill */}
                        <div className="flex items-center gap-1.5 shrink-0">
                          {questBadge && (
                            <span
                              className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono font-extrabold uppercase tracking-wider border ${questBadge.className}`}
                            >
                              <span className="text-xs leading-none">{questBadge.icon}</span>
                              <span>{questBadge.label}</span>
                            </span>
                          )}
                          {(!questBadge || !isFreeAction) && (
                            <span
                              className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-wider border ${
                                isQuestHighlighted
                                  ? 'bg-amber-500/15 border-amber-500/40 text-amber-300'
                                  : isFreeAction
                                    ? 'bg-white/5 border-white/10 text-gray-300'
                                    : 'bg-fantasy-accent/10 border-fantasy-accent/30 text-fantasy-accent'
                              }`}
                            >
                              <span className="text-xs leading-none">{questBadge ? skillEmoji : choiceEmoji}</span>
                              {!isFreeAction && <span>{rawStat}</span>}
                            </span>
                          )}
                        </div>

                        {/* Center: Choice Action Text */}
                        <span
                          className={`flex-1 min-w-0 text-xs md:text-[13px] leading-snug ${
                            isQuestHighlighted
                              ? 'font-semibold text-amber-50 group-hover:text-white'
                              : 'font-medium text-gray-100 group-hover:text-white'
                          }`}
                        >
                          {cleanDisplayLabel}
                        </span>

                        {/* Right: MP Cost + Success Odds Badge */}
                        <div className="flex items-center gap-1 shrink-0">
                          {mpCost > 0 && (
                            <span className="text-blue-400 font-mono flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded bg-blue-950/50 border border-blue-800/40">
                              <Zap size={10} /> {mpCost}
                            </span>
                          )}
                          {showPercentages && pct !== undefined && pct !== null && !isFreeAction && (
                            <span className={`px-1.5 py-0.5 rounded border font-mono text-[10px] font-bold ${getOddsBadgeClass(pct)}`}>
                              {pct}%
                            </span>
                          )}
                        </div>
                      </button>
                    );
                  })}

                  {/* Dynamic Merchant / Shop Action Choice when a merchant or shop is available */}
                  {merchantAvailable && onOpenMerchant && (
                    <button
                      type="button"
                      onClick={onOpenMerchant}
                      disabled={isBusy}
                      className="group flex items-center justify-between gap-2.5 px-3 py-1.5 rounded-lg text-left bg-emerald-950/30 border border-emerald-500/50 hover:border-amber-400 hover:bg-emerald-900/40 transition-all disabled:opacity-50"
                    >
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-emerald-500/15 border border-emerald-500/40 text-[10px] font-mono font-bold uppercase tracking-wider text-amber-300 shrink-0">
                        <span className="text-xs leading-none">🛍️</span>
                        <span>SHOP</span>
                      </span>
                      <span className="flex-1 min-w-0 text-xs md:text-[13px] font-semibold text-emerald-100 group-hover:text-white leading-snug">
                        {merchantActionLabel}
                      </span>
                      <span className="px-1.5 py-0.5 rounded bg-emerald-950/70 border border-emerald-600/40 font-mono font-semibold text-emerald-300 uppercase text-[10px] shrink-0">
                        Browse
                      </span>
                    </button>
                  )}
                </div>
              </div>
            )}
          </>
        )}

        {/* Compact Bottom Row: Collapse/Expand Choices Toggle + Custom Action Input */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setIsCollapsed((prev) => !prev)}
            title={isCollapsed ? 'Expand Action Choices' : 'Minimize Action Choices'}
            className="shrink-0 inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-black/60 hover:bg-black/80 border border-fantasy-border hover:border-fantasy-accent/60 text-[11px] font-mono text-gray-300 hover:text-fantasy-accent transition-colors"
          >
            {isCollapsed ? (
              <>
                <ChevronUp size={14} />
                <span>Choices ({totalChoiceCount})</span>
              </>
            ) : (
              <>
                <ChevronDown size={14} />
                <span className="hidden sm:inline">Hide</span>
              </>
            )}
          </button>

          <form onSubmit={handleCustomSubmit} className="relative flex-1 min-w-0">
            <input
              type="text"
              value={customAction}
              onChange={(e) => setCustomAction(e.target.value)}
              disabled={isBusy}
              placeholder={
                isStreaming
                  ? 'The Chronicler is speaking...'
                  : processing
                    ? 'Thinking...'
                    : 'Or type a custom action...'
              }
              className="w-full bg-black/60 border border-fantasy-border rounded-lg py-1.5 pl-3.5 pr-10 text-xs md:text-sm text-gray-200 focus:outline-none focus:border-fantasy-accent transition-colors disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={!customAction.trim() || isBusy}
              className="absolute right-1.5 top-1/2 -translate-y-1/2 p-1.5 rounded-md bg-fantasy-accent text-fantasy-dark hover:bg-fantasy-accent-hover transition-colors disabled:opacity-40 disabled:bg-gray-700"
            >
              <Send size={13} />
            </button>
          </form>
        </div>

      </div>
    </div>
  );
};

export default ActionPanel;
