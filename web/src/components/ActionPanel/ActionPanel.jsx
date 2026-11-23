import { useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Send, Lock, Zap, RefreshCw, ChevronDown, Smartphone, PenLine, X, Loader2 } from 'lucide-react';
import { apiCall } from '../../api/client';
import { AcrylicPanel, CollapsibleSection, MotionButton } from '../Common/MotionPrimitives';

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

const LOCALIZED_QUEST_BRACKET_RE = /^(?:(?:⭐|🎯|⚡|💌|🔹|🌙|⏳|🤝|\s)+|\s*\[(?:Story Quest(?:\s*\|[^\]\r\n]+)?|Hauptquest(?:\s*\|[^\]\r\n]+)?|Misi Utama(?:\s*\|[^\]\r\n]+)?|Zadanie Główne(?:\s*\|[^\]\r\n]+)?|主线任务(?:\s*\|[^\]\r\n]+)?|Story Climax(?:\s*-\s*[^\]\r\n]+)?|Höhepunkt der Geschichte(?:\s*-\s*[^\]\r\n]+)?|Kemuncak Cerita(?:\s*-\s*[^\]\r\n]+)?|Punkt Kulminacyjny(?:\s*-\s*[^\]\r\n]+)?|剧情高潮(?:\s*-\s*[^\]\r\n]+)?|Bounty(?:\s*\|[^\]\r\n]+)?|Kopfgeld(?:\s*\|[^\]\r\n]+)?|Ganjaran(?:\s*\|[^\]\r\n]+)?|Zlecenie(?:\s*\|[^\]\r\n]+)?|悬赏(?:\s*\|[^\]\r\n]+)?|Quest|Meetup|Treffen|Pertemuan|Spotkanie|碰头|碰面|会面|Main|Side|Optional[^\]\r\n]*)\]\s*)+/i;

const cleanChoiceDisplayLabel = (choice, questIcon) => {
  const rawDisplayLabel = String(choice?.label || choice?.text || '');
  const hasQuestMeta = Boolean(questIcon || choice?.is_quest_action || choice?.is_story_quest || choice?.is_climax_action);
  let stripped = rawDisplayLabel
    .replace(/^(?:🚶|🧭|📍|✨|🔍|💬|🗣️|🎭|💖|🎲|📜|🏕️|☕|🛋️|🖐️|🎒|🚪|⛓️|🛡️|👔|🧩|📱|\s)+/u, '')
    .replace(LOCALIZED_QUEST_BRACKET_RE, '');
  if (hasQuestMeta) {
    stripped = stripped.replace(/^(?:(?:⭐|🎯|⚡|💌|🔹|🌙|⏳|🤝|🚶|🧭|📍|\s)+|\s*\[[^\]\r\n]+\]\s*)+/i, '');
  }
  return stripped.replace(/\s*\((?:STR|PER|END|CHA|INT|AGI|LUK)\)\s*$/i, '').trim() || rawDisplayLabel;
};

const getChoiceQuestBadge = (questIcon, t) => {
  if (questIcon === '⚡') {
    return {
      icon: '⚡',
      label: t('quests.story_climax'),
      className: 'bg-purple-500/25 border-purple-400/70 text-purple-200 shadow-[0_0_8px_rgba(168,85,247,0.3)]',
    };
  }
  if (questIcon === '⭐') {
    return {
      icon: '⭐',
      label: t('quests.story_quest'),
      className: 'bg-amber-500/25 border-amber-400/80 text-amber-200 shadow-[0_0_8px_rgba(245,158,11,0.3)]',
    };
  }
  if (questIcon === '🎯') {
    return {
      icon: '🎯',
      label: t('quests.bounty'),
      className: 'bg-cyan-500/25 border-cyan-400/70 text-cyan-200 shadow-[0_0_8px_rgba(6,182,212,0.25)]',
    };
  }
  if (questIcon === '💌') {
    return {
      icon: '💌',
      label: t('quests.meetup'),
      className: 'bg-pink-500/25 border-pink-400/70 text-pink-200',
    };
  }
  return null;
};

const getChoiceQuestIcon = (choice) => {
  if (!choice || typeof choice !== 'object') return null;
  if (choice.quest_icon) return choice.quest_icon;

  const rawLabel = String(choice.label || choice.text || choice.action || '');
  const rawL = rawLabel.toLowerCase();
  const qid = String(choice.quest_id || '').toLowerCase();
  const ctype = String(choice.contract_type || '').toLowerCase();

  // 1. Story Climax
  if (
    choice.is_climax_action ||
    ctype === 'climax' ||
    rawLabel.includes('⚡') ||
    ['[story climax', '[höhepunkt der geschichte', '[kemuncak cerita', '[punkt kulminacyjny', '[剧情高潮'].some((k) => rawL.includes(k))
  ) {
    return '⚡';
  }

  // 2. Story Quest Actions
  if (
    rawLabel.includes('⭐') ||
    ['[story quest', '[hauptquest', '[misi utama', '[zadanie główne', '[主线任务'].some((k) => rawL.includes(k)) ||
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
    ['[bounty', '[kopfgeld', '[ganjaran', '[zlecenie', '[悬赏'].some((k) => rawL.includes(k)) ||
    ['bnt-', 'qst-', 'clr-', 'farc-', 'lib-', 'nem-', 'rem-', 'rmr-', 'mnr-', 'mand-'].some((px) => qid.includes(px))
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
  if (
    rawLabel.includes('💌') ||
    ['[meetup]', '[treffen]', '[pertemuan]', '[spotkanie]', '[碰头]', '[碰面]', '[会面]'].some((k) => rawL.includes(k))
  ) {
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
    return null;
  }
  if (
    rawLabel.includes('💖') ||
    rawL.includes('[affection]') ||
    rawL.includes('[flirt]') ||
    ['flirt with', 'compliment ', 'sincere compliment', 'confess feelings', 'affectionate', 'hold hands with'].some(
      (k) => rawL.includes(k)
    )
  ) {
    return null;
  }
  if (
    rawLabel.includes('🎲') ||
    rawL.includes('[challenge]') ||
    ['challenge ', 'arm-wrestle', 'friendly wager', 'friendly spar'].some((k) => rawL.includes(k))
  ) {
    return null;
  }
  if (
    rawLabel.includes('💬') ||
    rawL.includes('[inquiry]') ||
    ['inquire about', 'ask about', 'ask if', 'ask her', 'ask him', 'ask them'].some((k) => rawL.includes(k)) ||
    (rawL.includes('ask ') && rawL.includes(' about '))
  ) {
    return null;
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
      return null;
    }
    if (['joke', 'tease', 'banter', 'laugh', 'playful', 'ribbing', 'witty', 'humor', 'prank'].some((k) => rawL.includes(k))) {
      return null;
    }
    if (choice._quest_dialogue_handoff) {
      return '🚶';
    }
    if (
      Boolean(choice.ends_dialogue) ||
      String(choice.intent || '').toLowerCase() === 'dialogue_exit' ||
      isConversationalExitLabel(rawL)
    ) {
      return '🚪';
    }
    if (
      [
        'talk', 'speak', 'discuss', 'ask', 'tell', 'consult', 'comfort', 'inquire',
        'reassure', 'address', 'greet', 'converse', 'propose', 'negotiate', 'chat',
        'whisper', 'confer', 'explain', 'advise', 'gauge', 'interview', 'say to', 'confront',
      ].some((k) => rawL.includes(k))
    ) {
      return null;
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
      String(choice.intent || '').toLowerCase() === 'movement' ||
      [
        'travel', 'head to', 'head toward', 'depart', 'walk to', 'walk toward', 'exit', 'leave',
        'slip out', 'make your way', 'return to', 'step out', 'step into', 'go to', 'move to',
        'journey', 'navigate to',
        'step through', 'head through', 'descend into', 'descend the', 'cross into', 'enter the',
        'venture into', 'slip into',
        'udaj się do', 'idź do', 'podróżuj', 'kieruj się', 'wejdź do', 'wejdź w', 'przejdź do',
        'przejdź przez', 'zejdź do', 'wkrocz do', 'odwiedź',
        'pergi ke', 'menuju ke', 'berjalan ke', 'masuk ke', 'melangkah ke', 'turun ke', 'melintas ke',
        'lawati', 'kembali ke',
        '前往', '去往', '走进', '进入', '动身前往', '返回', '穿过', '深入', '下到',
        'gehe zu', 'gehe nach', 'gehe durch', 'schreite durch', 'reise nach', 'reise zu', 'betrete ',
        'begib dich', 'steige hinab', 'zurückkehren nach',
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
  if (!session || inCombat) {
    return { available: false, label: 'Talk to Merchant', closedVisible: false, closedMessage: '' };
  }
  if (typeof session.merchant_available === 'boolean') {
    return {
      available: session.merchant_available,
      label: session.merchant_action_label || 'Visit Market / Shop',
      closedVisible: Boolean(!session.merchant_available && session.shop_closed_visible),
      closedMessage: String(session.shop_closed_message || ''),
    };
  }
  const merchant = session.merchant || {};
  const loc = String(session.current_location || '').toLowerCase();
  const shopKeywords = [
    'shop', 'store', 'market', 'bazaar', 'emporium', 'café', 'cafe', 'pharmacy',
    'armory', 'blacksmith', 'weaponsmith', 'convenience', 'boutique',
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
  return { available: isAvailable, label, closedVisible: false, closedMessage: '' };
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
  onClosePhone,
  phoneOpen,
  showPercentages = true,
  showEnemyHp = true,
  showEnemyIntent = true,
  processing,
  pendingAction,
  isStreaming,
  waitingForParty,
  partyStatus,
  actionError,
  clearActionError,
  onReloadSession = null,
  onExitToDashboard = null,
  collapsed = undefined,
  onToggleCollapse = null
}) => {
  const { t } = useTranslation();
  const [customAction, setCustomAction] = useState('');
  const [combatTab, setCombatTab] = useState('attacks'); // 'attacks' | 'spells' | 'tactics' | 'choices'
  const combatTabRefs = useRef({});
  const [isChoicesCollapsed, setIsChoicesCollapsed] = useState(false);
  const [isCustomCollapsed, setIsCustomCollapsed] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [reloadError, setReloadError] = useState(null);
  const isCollapsed = collapsed !== undefined ? collapsed : isChoicesCollapsed;
  const handleToggleCollapse = () => {
    if (onToggleCollapse) onToggleCollapse();
    else setIsChoicesCollapsed((prev) => !prev);
  };
  const isBusy = processing || isStreaming || Boolean(phoneOpen);
  const isRetryBusy = processing || Boolean(phoneOpen);

  const isChoicePending = (choice, idx) => {
    if (!processing || !pendingAction) return false;
    if (idx !== undefined && pendingAction.choice_index !== undefined && pendingAction.choice_index === idx) {
      return true;
    }
    const dc = pendingAction.direct_choice;
    if (!dc || !choice) return false;
    if (dc === choice) return true;
    if (dc.label && choice.label && dc.label === choice.label) return true;
    if (dc.name && choice.name && dc.name === choice.name) return true;
    if (dc.text && choice.text && dc.text === choice.text) return true;
    return false;
  };

  const dialoguePartners = new Set(
    (() => {
      let list = [];
      if (Array.isArray(session?.dialogue_partners) && session.dialogue_partners.length > 0) {
        list = session.dialogue_partners;
      } else if (session?.dialogue_partner) {
        const dp = session.dialogue_partner;
        if (Array.isArray(dp)) {
          list = dp;
        } else if (typeof dp === 'string') {
          const trimmed = dp.trim();
          if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
            try {
              const parsed = JSON.parse(trimmed);
              list = Array.isArray(parsed) ? parsed : [dp];
            } catch {
              list = [dp];
            }
          } else {
            list = [dp];
          }
        }
      }
      return list;
    })().map(n => String(n || '').toLowerCase().trim()).filter(Boolean)
  );

  const livingEnemies = (session?.nearby_enemies || session?.monsters || []).filter(
    (e) => e && e.name && (e.hp ?? 1) > 0
  );
  const inCombat = Boolean(session?.is_in_combat || livingEnemies.length > 0);
  const activeTargetObj =
    livingEnemies.find((e) => e.name === selectedCombatTarget || (e.id && String(e.id) === String(selectedCombatTarget))) || livingEnemies[0] || null;
  const selectedTargetName = activeTargetObj?.name || selectedCombatTarget || null;

  const {
    available: merchantAvailable,
    label: merchantActionLabel,
    closedVisible: merchantClosedVisible,
    closedMessage: merchantClosedMessage,
  } = detectMerchantAvailableClient(
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
      <AcrylicPanel variant="panel" origin="bottom" className="shrink-0 w-full min-w-0 px-4 py-3 flex items-center justify-center gap-3 z-20">
        <Lock className="text-fantasy-accent animate-pulse shrink-0" size={20} />
        <div className="flex items-center gap-2 min-w-0 flex-wrap justify-center">
          <h3 className="font-rpg text-base text-gray-200">{t('combat.waiting_party')}</h3>
          <span className="hk-chip font-mono">
            {partyStatus?.lockedCount} / {partyStatus?.total} {t('combat.locked_in')}
          </span>
        </div>
      </AcrylicPanel>
    );
  }

  const renderActivePartnerMoodBar = () => {
    if (inCombat) return null;
    const partnerMoodItems = [];
    const seenMoodNames = new Set();
    const allSceneActors = [
      ...(Array.isArray(session?.current_npcs) ? session.current_npcs : []),
      ...(Array.isArray(session?.party_npcs) ? session.party_npcs : []),
    ];
    allSceneActors.forEach((actor) => {
      if (!actor || typeof actor !== 'object') return;
      const aName = String(actor.name || '').trim();
      const aLow = aName.toLowerCase();
      if (!aName || !dialoguePartners.has(aLow) || seenMoodNames.has(aLow)) return;
      if (actor.dialogue_mood?.mood_key) {
        seenMoodNames.add(aLow);
        partnerMoodItems.push({
          name: aName,
          moodKey: actor.dialogue_mood.mood_key,
          moodLabel: actor.dialogue_mood.mood_label || actor.dialogue_mood.mood_key,
        });
      }
    });
    if (partnerMoodItems.length === 0 && session?.active_dialogue_mood?.mood_key) {
      const fbName = String(session.active_dialogue_mood.npc_name || session?.dialogue_partner || '').trim();
      if (fbName) {
        partnerMoodItems.push({
          name: fbName,
          moodKey: session.active_dialogue_mood.mood_key,
          moodLabel: session.active_dialogue_mood.mood_label || session.active_dialogue_mood.mood_key,
        });
      }
    }
    if (partnerMoodItems.length === 0) return null;
    return (
      <div className="flex items-center flex-wrap gap-1.5 px-2.5 py-1 rounded-lg bg-gray-500/10 border border-fantasy-border/40 text-[11px]">
        <span className="font-mono uppercase tracking-wider text-gray-400 font-semibold">
          💬 {t('social.mood_prefix', 'Mood')}:
        </span>
        {partnerMoodItems.map((pm, pmIdx) => (
          <span
            key={`active-mood-${pmIdx}`}
            className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border font-mono font-semibold leading-tight ${
              pm.moodKey === 'Engaged'
                ? 'bg-emerald-950/85 text-emerald-300 border-emerald-700/60'
                : pm.moodKey === 'Guarded'
                ? 'bg-amber-950/85 text-amber-300 border-amber-700/60'
                : pm.moodKey === 'Upset'
                ? 'bg-rose-950/85 text-rose-300 border-rose-700/60'
                : 'bg-slate-900/85 text-slate-300 border-slate-700/60'
            }`}
          >
            <span className="text-gray-200">{pm.name}:</span>
            <span>{t(`social.moods.${pm.moodKey}`, pm.moodLabel)}</span>
          </span>
        ))}
      </div>
    );
  };

  const renderConversationPauseNotice = () => {
    if (inCombat || !Array.isArray(choices)) return null;
    const pausedExit = choices.find((c) => c && typeof c === 'object' && c._conversation_paused);
    if (!pausedExit) return null;
    const pauseName = String(pausedExit.pause_partner || '').trim();
    return (
      <div
        role="status"
        className="flex items-start gap-1.5 px-2.5 py-1 rounded-lg bg-slate-900/70 border border-slate-600/40 text-[11px] text-slate-300"
      >
        <span aria-hidden="true">⏸️</span>
        <span>
          {pauseName
            ? t('social.conversation_paused', {
                name: pauseName,
                defaultValue: pausedExit.pause_notice || `${pauseName} has run out of small talk for now.`,
              })
            : pausedExit.pause_notice}
        </span>
      </div>
    );
  };

  const totalChoiceCount = (choices?.length || 0) + (!inCombat && merchantAvailable && onOpenMerchant ? 1 : 0);

  const isGameOver = Boolean(session?.status === 'finished' || session?.is_game_over);

  const handleReloadCheckpoint = async () => {
    setReloading(true);
    setReloadError(null);
    try {
      const uid = session?.character?.user_id || session?.host_user_id || session?.user_id;
      if (!uid) {
        setReloadError(t('game_over.no_user', 'User ID not identified.'));
        return;
      }
      const savesRes = await apiCall(`/api/saves/${uid}`);
      const saves = savesRes?.saves || [];
      if (saves.length > 0) {
        saves.sort((a, b) => (b.saved_at || 0) - (a.saved_at || 0));
        const latestSlot = saves[0].slot_name;
        const loadRes = await apiCall('/api/saves/load', {
          method: 'POST',
          body: JSON.stringify({ user_id: uid, slot_name: latestSlot }),
        });
        if (onReloadSession) {
          onReloadSession(loadRes?.session || loadRes?.loaded || null);
        }
      } else {
        setReloadError(t('game_over.no_saves', 'No saved checkpoints found. Please return to dashboard.'));
      }
    } catch (err) {
      setReloadError(err?.message || 'Failed to reload save');
    } finally {
      setReloading(false);
    }
  };

  if (isGameOver) {
    return (
      <AcrylicPanel variant="panel" origin="bottom" className="shrink-0 w-full min-w-0 border-red-500/50 px-4 py-4 md:py-5 z-20 text-center">
        <div className="max-w-md mx-auto flex flex-col items-center gap-3">
          <div className="text-xl sm:text-2xl md:text-3xl font-rpg text-red-500 tracking-wider">
            💀 {t('game_over.title', 'DEFEAT & GAME OVER')}
          </div>
          <p className="text-xs md:text-sm text-gray-300 font-serif italic">
            {session?.epilogue || session?.extra?.epilogue || t('game_over.subtitle', 'The journey has met a grim end. Your courage remains etched in memory.')}
          </p>
          {reloadError && (
            <div className="text-xs text-red-400 bg-red-950/60 px-3 py-1 rounded border border-red-800">
              {reloadError}
            </div>
          )}
          <div className="flex items-center flex-wrap justify-center gap-3 mt-1">
            <MotionButton
              onClick={handleReloadCheckpoint}
              disabled={reloading}
              className="hk-btn bg-red-700 hover:bg-red-600 text-white text-xs md:text-sm disabled:opacity-50"
            >
              {reloading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              <span>{t('game_over.reload_checkpoint', 'Reload Latest Checkpoint')}</span>
            </MotionButton>
            <MotionButton
              onClick={() => {
                if (onExitToDashboard) {
                  onExitToDashboard();
                }
              }}
              className="hk-btn hk-btn-ghost text-xs md:text-sm"
            >
              <span>{t('game_over.return_dashboard', 'Return to Dashboard')}</span>
            </MotionButton>
          </div>
        </div>
      </AcrylicPanel>
    );
  }

  return (
    <AcrylicPanel variant="panel" origin="bottom" className="shrink-0 w-full min-w-0 px-3 sm:px-4 py-2 sm:py-2.5 z-20">
      <div className="w-full min-w-0 flex flex-col gap-1.5 sm:gap-2">

        {/* Smartphone Active Lockout Banner */}
        {phoneOpen && (
          <div className="flex items-center justify-between bg-pink-500/15 border border-pink-500/45 px-3 py-1.5 rounded-lg text-xs text-pink-200">
            <span className="flex items-center gap-1.5 font-semibold">
              <Smartphone size={14} className="text-pink-400 animate-pulse" />
              <span>{t('actions.phone_open')}</span>
            </span>
            {onClosePhone && (
              <MotionButton
                onClick={onClosePhone}
                className="hk-chip bg-pink-500/25 hover:bg-pink-500/40 text-pink-100 text-[11px] font-bold cursor-pointer py-1 h-auto"
              >
                {t('actions.close_phone')}
              </MotionButton>
            )}
          </div>
        )}

        {/* Action Error Banner (visible in both exploration & combat, even when collapsed) */}
        {actionError && (
          <div className="flex items-center justify-between bg-red-950/80 border border-red-700/80 px-3 py-1.5 rounded-lg text-xs text-red-200 shadow-md">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-red-400 font-bold shrink-0">⚠️ Error:</span>
              <span className="truncate">{actionError}</span>
            </div>
            {clearActionError && (
              <button
                type="button"
                onClick={clearActionError}
                className="text-gray-400 hover:text-white text-xs px-2 py-0.5 rounded hover:bg-white/10 shrink-0 ml-2"
              >
                ✕
              </button>
            )}
          </div>
        )}

        <CollapsibleSection isOpen={!isCollapsed}>
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
                        title={t('actions.cycle_target', 'Click to cycle target enemy')}
                        className="px-2.5 py-0.5 rounded-full bg-red-950/80 hover:bg-red-900/80 border border-amber-500/60 text-[11px] font-mono font-bold text-amber-200 flex items-center gap-1 transition-colors"
                      >
                        <span>
                          🎯 {activeTargetObj.name}{showEnemyHp ? ` (${activeTargetObj.hp ?? activeTargetObj.max_hp ?? 100}/${activeTargetObj.max_hp ?? 100})` : ''}
                        </span>
                        {activeTargetObj.tether_vessel_name && (
                          <span className="text-[9.5px] px-1 rounded bg-amber-950/80 border border-amber-600/50 text-amber-300">
                            {activeTargetObj.tether_sealed
                              ? `⛓️ ${t('codex.tether_sealed', 'Tether Sealed')}`
                              : `🏺 ${activeTargetObj.tether_vessel_name}`}
                          </span>
                        )}
                        {showEnemyIntent && activeTargetObj.telegraphed_skill && typeof activeTargetObj.telegraphed_skill === 'object' && (
                          <span className="text-[9.5px] px-1 rounded bg-amber-950/90 border border-amber-500/70 text-amber-200 font-bold">
                            ⚠️ {activeTargetObj.telegraphed_skill.skill_name || activeTargetObj.telegraphed_skill.telegraphed_label || activeTargetObj.telegraphed_skill.name}
                          </span>
                        )}
                      </button>
                    )}

                    {(() => {
                      const isAnomDeck = Boolean(session?.max_ult_pips || String(session?.scenario || '').toLowerCase().includes('anomalous'));
                      const rawPips = session?.ult_pips ?? (typeof session?.player_resonance_pips === 'object' ? Object.values(session?.player_resonance_pips || {})[0] : session?.player_resonance_pips);
                      const ultPips = Math.max(0, Math.min(3, Number(rawPips) || 0));
                      const pipDots = `${'●'.repeat(ultPips)}${'○'.repeat(3 - ultPips)}`;
                      return (
                        <>
                          <div role="tablist" aria-label={t('actions.combat_categories_aria', 'Combat Action Categories')} className="flex items-center gap-1 bg-black/60 p-0.5 rounded-lg border border-fantasy-border">
                            {[
                              { id: 'attacks', label: `⚔️ ${t('combat.attack')}` },
                              {
                                id: 'spells',
                                label: isAnomDeck
                                  ? `🧬 ${t('awakened.abilities_tab', 'Abilities')}${deckSpells.length ? ` (${deckSpells.length})` : ''}`
                                  : `🔮 ${t('combat.magic')}${deckSpells.length ? ` (${deckSpells.length})` : ''}`,
                              },
                              { id: 'tactics', label: `🧠 ${t('combat.tactics')}` },
                              { id: 'choices', label: `📜 ${t('nav.quests')}` },
                            ].map((tab, idx, arr) => {
                              const active = combatTab === tab.id;
                              return (
                                <button
                                  key={tab.id}
                                  ref={(el) => {
                                    combatTabRefs.current[tab.id] = el;
                                  }}
                                  type="button"
                                  role="tab"
                                  aria-selected={active}
                                  tabIndex={active ? 0 : -1}
                                  onClick={() => setCombatTab(tab.id)}
                                  onKeyDown={(e) => {
                                    let nextIdx = null;
                                    if (e.key === 'ArrowRight') nextIdx = (idx + 1) % arr.length;
                                    else if (e.key === 'ArrowLeft') nextIdx = (idx - 1 + arr.length) % arr.length;
                                    else if (e.key === 'Home') nextIdx = 0;
                                    else if (e.key === 'End') nextIdx = arr.length - 1;
                                    if (nextIdx !== null) {
                                      e.preventDefault();
                                      const nextId = arr[nextIdx].id;
                                      setCombatTab(nextId);
                                      combatTabRefs.current[nextId]?.focus();
                                    }
                                  }}
                                  className={`px-2 py-0.5 rounded text-[11px] font-bold transition-colors ${
                                    active
                                      ? 'bg-red-900/60 text-amber-300 border border-amber-500/50'
                                      : 'text-gray-400 hover:text-gray-200'
                                  }`}
                                >
                                  {tab.label}
                                </button>
                              );
                            })}
                          </div>
                          {isAnomDeck && (
                            <span
                              title={t('awakened.ult_pips_label', 'Resonance Pips')}
                              className={`px-2 py-0.5 rounded-full text-[10.5px] font-mono font-bold border ${
                                ultPips >= 3
                                  ? 'bg-purple-950/80 border-purple-400 text-purple-200 animate-pulse'
                                  : 'bg-black/70 border-cyan-800/60 text-cyan-300'
                              }`}
                            >
                              {ultPips >= 3 ? `🌟 ${t('awakened.ult_ready', 'ULT READY')} [${pipDots}]` : `[${pipDots}] ${ultPips}/3`}
                            </span>
                          )}
                        </>
                      );
                    })()}
                  </div>

                  <div className="flex items-center gap-1.5">
                    {onRetry && (
                      <button
                        type="button"
                        disabled={isRetryBusy}
                        onClick={onRetry}
                        title="Re-generate this turn's narration & tactical choices"
                        className={`px-2 py-0.5 rounded text-[11px] font-bold flex items-center gap-1 transition-colors disabled:opacity-50 ${
                          session?.is_fallback_generation || session?.is_truncated_generation
                            ? 'bg-amber-950/80 hover:bg-amber-900 text-amber-200 border border-amber-500/70 animate-pulse'
                            : 'bg-black/60 hover:bg-black/90 text-gray-300 hover:text-amber-200 border border-fantasy-border hover:border-amber-500/50'
                        }`}
                      >
                        <RefreshCw size={11} className={processing ? "animate-spin" : ""} />
                        <span>{t('common.retry')}</span>
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={isBusy}
                      onClick={() => onAction({ direct_choice: fleeChoice, combat_target: selectedTargetName })}
                      className="px-2.5 py-0.5 rounded bg-neutral-900 hover:bg-red-950/70 text-gray-300 hover:text-red-200 border border-neutral-700 hover:border-red-700 text-[11px] font-bold transition-colors disabled:opacity-50"
                    >
                      🏃 {t('combat.flee')}
                    </button>
                  </div>
                </div>

                {/* Active Combat Deck Cards (Compact Horizontal Rows, Scrollable when needed) */}
                {combatTab === 'choices' ? (
                  <div className="hk-choice-grid max-h-[28dvh] sm:max-h-[32dvh] lg:max-h-[36dvh] overflow-y-auto custom-scrollbar pr-0.5">
                    {(choices || []).map((choice, idx) => {
                      const pct = choice.success_pct !== undefined ? choice.success_pct : choice.chance;
                      const mpCost = choice.mp_cost || 0;
                      const questIcon = getChoiceQuestIcon(choice);
                      const questBadge = getChoiceQuestBadge(questIcon, t);
                      const cleanDisplayLabel = cleanChoiceDisplayLabel(choice, questIcon);
                      const skillEmoji = getChoiceSkillEmoji(choice);
                      const choiceEmoji = getChoiceEmoji(choice);
                      const statName = String(choice.stat || 'FREE').toUpperCase();
                      const displayStat = statName === 'NONE' ? 'FREE' : statName;
                      const isPending = isChoicePending(choice, idx);
                      return (
                        <button
                          key={idx}
                          onClick={() => onAction({ choice_index: idx, direct_choice: choice, combat_target: selectedTargetName })}
                          disabled={isBusy}
                          className={`group flex items-center justify-between gap-1.5 md:gap-2 px-2.5 md:px-3 py-1 md:py-1.5 rounded-md md:rounded-lg border transition-all disabled:opacity-50 text-left ${
                            isPending
                              ? 'bg-amber-950/70 border-amber-400 ring-2 ring-amber-400 shadow-[0_0_15px_rgba(245,158,11,0.35)] !opacity-100'
                              : 'bg-black/50 border-fantasy-border hover:border-fantasy-accent hover:bg-fantasy-accent/10'
                          }`}
                        >
                          <div className="flex items-center gap-1 shrink-0">
                            {questBadge && (
                              <span
                                title={questBadge.label}
                                className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[9.5px] md:text-[0.765rem] font-mono font-extrabold uppercase tracking-wider border ${questBadge.className}`}
                              >
                                <span className="text-xs leading-none">{questBadge.icon}</span>
                              </span>
                            )}
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-white/5 border border-white/10 text-[9.5px] md:text-[0.765rem] font-mono font-bold uppercase text-fantasy-accent shrink-0">
                              <span className="text-xs leading-none">{questBadge ? (skillEmoji || '✨') : choiceEmoji}</span>
                              <span>{displayStat}</span>
                            </span>
                          </div>
                          <span className="flex-1 min-w-0 text-xs sm:text-[0.875rem] md:text-sm font-medium text-gray-100 group-hover:text-white leading-snug">
                            {cleanDisplayLabel}
                          </span>
                          <div className="flex items-center gap-1 shrink-0">
                            {isPending && (
                              <span className="inline-flex items-center gap-1 text-[10px] font-mono font-bold text-amber-300 px-1.5 py-0.5 rounded bg-amber-500/20 border border-amber-500/40">
                                <Loader2 size={11} className="animate-spin text-amber-300" />
                                <span>{t('actions.resolving', 'Resolving...')}</span>
                              </span>
                            )}
                            {mpCost > 0 && !isPending && (
                              <span className="text-blue-400 font-mono flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded bg-blue-950/50 border border-blue-800/40">
                                <Zap size={10} /> {mpCost}
                              </span>
                            )}
                            {showPercentages && pct !== undefined && pct !== null && !isPending && (
                              <span className={`px-1.5 py-0.5 rounded border font-mono text-[9.5px] md:text-[0.765rem] font-bold ${getOddsBadgeClass(pct)}`}>
                                {pct}%
                              </span>
                            )}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <div className="hk-choice-grid max-h-[28dvh] sm:max-h-[32dvh] lg:max-h-[36dvh] overflow-y-auto custom-scrollbar pr-0.5">
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
                        const isPending = isChoicePending(item);
                        return (
                          <MotionButton
                            key={idx}
                            disabled={isBusy || !canAfford}
                            onClick={() => onAction({ direct_choice: item, combat_target: selectedTargetName })}
                            className={`group flex items-center justify-between gap-1.5 md:gap-2 px-2.5 md:px-3 py-1.5 rounded-xl border transition-all disabled:opacity-40 text-left ${
                              isPending
                                ? 'bg-amber-950/70 border-amber-400 ring-2 ring-amber-400 shadow-[0_0_15px_rgba(245,158,11,0.35)] !opacity-100'
                                : item.subdue_highlighted
                                  ? 'bg-emerald-950/70 border-emerald-400 ring-1 ring-emerald-400/50 hover:bg-emerald-900/60 text-emerald-100'
                                  : item.is_pact_skill
                                    ? (item.is_lethal_overdraw
                                        ? 'bg-red-950/70 border-red-500 ring-1 ring-red-500/60 hover:bg-red-900/60'
                                        : 'bg-rose-950/55 border-rose-500/80 hover:border-rose-300 hover:bg-rose-900/45')
                                  : (item.is_ultimate && canAfford)
                                    ? 'bg-purple-950/60 border-purple-400 ring-1 ring-purple-400/50 hover:bg-purple-900/50'
                                    : 'bg-gray-500/10 border-red-500/35 hover:border-amber-400 hover:bg-red-500/15'
                            }`}
                          >
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-red-950/50 border border-red-800/40 text-[9.5px] md:text-[0.765rem] font-mono font-bold uppercase text-amber-300 shrink-0">
                              <span className="text-xs leading-none">{itemEmoji}</span>
                              <span>{itemStat}</span>
                            </span>
                            <div className="flex-1 min-w-0">
                              <div className="text-xs sm:text-[0.875rem] md:text-sm font-semibold text-gray-100 group-hover:text-white leading-snug truncate">
                                {item.label || item.name || item.text}
                              </div>
                              {item.description && (
                                <div className="text-[10px] text-gray-400 truncate">{item.description}</div>
                              )}
                            </div>
                            <div className="flex items-center gap-1 shrink-0">
                              {isPending && (
                                <span className="inline-flex items-center gap-1 text-[10px] font-mono font-bold text-amber-300 px-1.5 py-0.5 rounded bg-amber-500/20 border border-amber-500/40">
                                  <Loader2 size={11} className="animate-spin text-amber-300" />
                                  <span>{t('actions.resolving', 'Resolving...')}</span>
                                </span>
                              )}
                              {item.is_pact_skill && !isPending ? (
                                <span className={`font-mono flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded border ${
                                  item.is_lethal_overdraw
                                    ? 'bg-red-950/90 text-red-200 border-red-400 font-bold animate-pulse'
                                    : 'bg-rose-950/80 text-rose-200 border-rose-500/70 font-bold'
                                }`} title={item.is_lethal_overdraw ? t('contracts.lethal_overdraw', 'Lethal Overdraw • Blood Debt') : undefined}>
                                  {item.is_lethal_overdraw ? '⚠️ Debt' : `🩸 ${item.pact_hp_cost || 0} HP`} • 0 MP
                                </span>
                              ) : item.is_ultimate && !isPending ? (
                                <span className={`font-mono flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded border ${
                                  canAfford
                                    ? 'bg-purple-950/80 text-purple-200 border-purple-400/70 font-bold'
                                    : 'bg-neutral-900/80 text-gray-400 border-neutral-700/60'
                                }`}>
                                  🌟 {item.pip_cost || 3} Pips • 0 MP
                                </span>
                              ) : (
                                mpCost > 0 && !isPending && (
                                  <span className="text-blue-400 font-mono flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded bg-blue-950/50 border border-blue-800/40">
                                    <Zap size={10} aria-hidden="true" /> {mpCost}
                                  </span>
                                )
                              )}
                              {showPercentages && pct !== undefined && pct !== null && !isPending && (
                                <span className={`px-1.5 py-0.5 rounded border font-mono text-[9.5px] md:text-[0.765rem] font-bold ${getOddsBadgeClass(pct)}`}>
                                  {pct}%
                                </span>
                              )}
                            </div>
                          </MotionButton>
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
                    <span>⚠️ {t('actions.fallback_warning')}</span>
                    <button
                      type="button"
                      disabled={isRetryBusy}
                      onClick={onRetry}
                      className="px-2 py-0.5 rounded bg-amber-600/30 hover:bg-amber-600/50 text-amber-200 border border-amber-500/50 font-bold text-[11px] flex items-center gap-1 transition-colors"
                    >
                      <RefreshCw size={11} className={processing ? "animate-spin" : ""} />
                      <span>🔄 {t('common.retry')}</span>
                    </button>
                  </div>
                )}

                {renderActivePartnerMoodBar()}
                {renderConversationPauseNotice()}

                {session?.is_truncated_generation && !session?.is_fallback_generation && onRetry && (
                  <div className="flex items-center justify-between bg-amber-950/40 border border-amber-600/50 px-3 py-1 rounded text-xs text-amber-200">
                    <span>⚠️ {t('actions.truncated_warning')}</span>
                    <button
                      type="button"
                      disabled={isRetryBusy}
                      onClick={onRetry}
                      className="px-2 py-0.5 rounded bg-amber-600/30 hover:bg-amber-600/50 text-amber-200 border border-amber-500/50 font-bold text-[11px] flex items-center gap-1 transition-colors"
                    >
                      <RefreshCw size={11} className={processing ? "animate-spin" : ""} />
                      <span>🔄 {t('common.retry')}</span>
                    </button>
                  </div>
                )}

                <div className="hk-choice-grid max-h-[28dvh] sm:max-h-[32dvh] lg:max-h-[36dvh] overflow-y-auto custom-scrollbar pr-0.5">
                  {(choices || []).map((choice, idx) => {
                    const pct = choice.success_pct !== undefined ? choice.success_pct : choice.chance;
                    const mpCost = choice.mp_cost || 0;
                    const questIcon = getChoiceQuestIcon(choice);
                    const skillEmoji = getChoiceSkillEmoji(choice);
                    const choiceEmoji = getChoiceEmoji(choice);
                    const isQuestHighlighted = Boolean(questIcon && ['⭐', '🎯', '⚡'].includes(questIcon));
                    const rawStat = String(choice.stat || 'NONE').toUpperCase();
                    const isFreeAction = rawStat === 'NONE' || rawStat === 'FREE' || !rawStat;

                    const questBadge = getChoiceQuestBadge(questIcon, t);
                    const cleanDisplayLabel = cleanChoiceDisplayLabel(choice, questIcon);

                    const isPending = isChoicePending(choice, idx);

                    return (
                      <MotionButton
                        key={idx}
                        onClick={() => onAction({ choice_index: idx, direct_choice: choice })}
                        disabled={isBusy}
                        className={`group flex items-center justify-between gap-1.5 md:gap-2 px-2.5 md:px-3 py-1.5 rounded-xl text-left transition-all disabled:opacity-50 ${
                          isPending
                            ? 'bg-amber-950/70 border border-amber-400 ring-2 ring-amber-400 shadow-[0_0_15px_rgba(245,158,11,0.35)] !opacity-100'
                            : isQuestHighlighted
                              ? 'bg-amber-500/15 border border-amber-400/65 hover:border-amber-300 hover:bg-amber-500/25 shadow-[0_0_12px_rgba(245,158,11,0.14)]'
                              : 'bg-gray-500/10 border border-fantasy-border/40 hover:border-fantasy-accent hover:bg-fantasy-accent/15'
                        }`}
                      >
                        {/* Left: Quest Marker Badge + Stat Pill */}
                        <div className="flex items-center gap-1 shrink-0">
                          {questBadge && (
                            <span
                              title={questBadge.label}
                              className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[9.5px] md:text-[0.765rem] font-mono font-extrabold uppercase tracking-wider border ${questBadge.className}`}
                            >
                              <span className="text-xs leading-none">{questBadge.icon}</span>
                              <span className="hidden 2xl:inline">{questBadge.label}</span>
                            </span>
                          )}
                          {(!questBadge || !isFreeAction || skillEmoji === '🚶') && (
                            <span
                              className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[9.5px] md:text-[0.765rem] font-mono font-bold uppercase tracking-wider border ${
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
                          className={`flex-1 min-w-0 text-xs sm:text-[0.875rem] md:text-sm leading-snug ${
                            isQuestHighlighted
                              ? 'font-semibold text-amber-50 group-hover:text-white'
                              : 'font-medium text-gray-100 group-hover:text-white'
                          }`}
                        >
                          {cleanDisplayLabel}
                        </span>

                        {/* Right: MP Cost + Success Odds Badge or Resolving Spinner */}
                        <div className="flex items-center gap-1 shrink-0">
                          {isPending && (
                            <span className="inline-flex items-center gap-1 text-[10px] font-mono font-bold text-amber-300 px-1.5 py-0.5 rounded bg-amber-500/20 border border-amber-500/40">
                              <Loader2 size={11} className="animate-spin text-amber-300" />
                              <span>{t('actions.resolving', 'Resolving...')}</span>
                            </span>
                          )}
                          {mpCost > 0 && !isPending && (
                            <span className="text-blue-400 font-mono flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded bg-blue-950/50 border border-blue-800/40">
                              <Zap size={10} /> {mpCost}
                            </span>
                          )}
                          {showPercentages && pct !== undefined && pct !== null && !isFreeAction && !isPending && (
                            <span className={`px-1.5 py-0.5 rounded border font-mono text-[9.5px] md:text-[0.765rem] font-bold ${getOddsBadgeClass(pct)}`}>
                              {pct}%
                            </span>
                          )}
                        </div>
                      </MotionButton>
                    );
                  })}

                  {/* Dynamic Merchant / Shop Action Choice when a merchant or shop is available */}
                  {merchantAvailable && onOpenMerchant && (
                    <button
                      type="button"
                      onClick={onOpenMerchant}
                      disabled={isBusy}
                      className="group flex items-center justify-between gap-1.5 md:gap-2.5 px-2.5 md:px-3 py-1 md:py-1.5 rounded-md md:rounded-lg text-left bg-emerald-950/30 border border-emerald-500/50 hover:border-amber-400 hover:bg-emerald-900/40 transition-all disabled:opacity-50"
                    >
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-emerald-500/15 border border-emerald-500/40 text-[9.5px] md:text-[0.765rem] font-mono font-bold uppercase tracking-wider text-amber-300 shrink-0">
                        <span className="text-xs leading-none">🛍️</span>
                        <span>{t('actions.shop')}</span>
                      </span>
                      <span className="flex-1 min-w-0 text-xs sm:text-[0.875rem] md:text-sm font-semibold text-emerald-100 group-hover:text-white leading-snug">
                        {merchantActionLabel}
                      </span>
                      <span className="px-1.5 py-0.5 rounded bg-emerald-950/70 border border-emerald-600/40 font-mono font-semibold text-emerald-300 uppercase text-[9.5px] md:text-[0.765rem] shrink-0">
                        {t('actions.browse')}
                      </span>
                    </button>
                  )}

                  {/* Disabled Closed-Shop Indicator shown ONLY at real shop venues that are off-shift or shuttered */}
                  {!merchantAvailable && merchantClosedVisible && (
                    <div
                      role="status"
                      aria-disabled="true"
                      title={merchantClosedMessage || t('actions.shop_closed_default')}
                      className="flex items-center justify-between gap-1.5 md:gap-2.5 px-2.5 md:px-3 py-1 md:py-1.5 rounded-md md:rounded-lg text-left bg-zinc-950/60 border border-zinc-700/50 opacity-75 cursor-not-allowed select-none"
                    >
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-zinc-800/80 border border-zinc-600/50 text-[9.5px] md:text-[0.765rem] font-mono font-bold uppercase tracking-wider text-zinc-300 shrink-0">
                        <span className="text-xs leading-none">🔒</span>
                        <span>{t('actions.shop_closed_badge')}</span>
                      </span>
                      <span className="flex-1 min-w-0 text-xs sm:text-[0.875rem] md:text-sm font-medium text-zinc-400 leading-snug truncate">
                        {merchantClosedMessage || t('actions.shop_closed_default')}
                      </span>
                      <span className="px-1.5 py-0.5 rounded bg-zinc-900/90 border border-zinc-700/60 font-mono font-semibold text-zinc-400 uppercase text-[9.5px] md:text-[0.765rem] shrink-0">
                        {t('actions.closed_tag')}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            )}
        </CollapsibleSection>

        {/* Compact Bottom Row: Collapse Choices Toggle + Re-roll Button + Custom Action Input */}
        <div className="flex items-center gap-1.5 sm:gap-2 min-w-0">
          {/* Choices Collapsible Toggle */}
          <MotionButton
            onClick={handleToggleCollapse}
            title={isCollapsed ? 'Expand Action Choices' : 'Minimize Action Choices'}
            aria-expanded={!isCollapsed}
            className="shrink-0 inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-gray-500/10 hover:bg-gray-500/20 border border-fantasy-border/45 hover:border-fantasy-accent/60 text-[11px] font-mono text-gray-200 hover:text-fantasy-accent transition-colors"
          >
            <ChevronDown
              size={13}
              className={`transition-transform duration-200 ${isCollapsed ? '' : 'rotate-180'}`}
            />
            {isCollapsed ? (
              <span>{t('actions.choices')} ({totalChoiceCount})</span>
            ) : (
              <>
                <span className="hidden xs:inline">{t('actions.choices')}</span>
                <span className="xs:hidden">{t('common.hide')}</span>
              </>
            )}
          </MotionButton>

          {/* Re-roll / Retry Narration Button (Always Visible) */}
          {onRetry && (
            <MotionButton
              disabled={isRetryBusy}
              onClick={onRetry}
              title="Re-roll / Re-generate this turn's narrative & choices"
              className={`shrink-0 inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg font-mono text-[11px] font-bold transition-all border disabled:opacity-40 ${
                session?.is_fallback_generation || session?.is_truncated_generation
                  ? 'bg-amber-950/80 border-amber-500 text-amber-200 hover:bg-amber-900 ring-1 ring-amber-500/50 animate-pulse'
                  : 'bg-gray-500/10 hover:bg-gray-500/20 border-fantasy-border/45 hover:border-amber-500/60 text-gray-200 hover:text-amber-300'
              }`}
            >
              <RefreshCw size={11} className={processing ? "animate-spin text-amber-400" : "text-amber-400"} />
              <span className="hidden xs:inline">{t('actions.reroll')}</span>
            </MotionButton>
          )}


          {/* Collapsible Custom Action Section */}
          {isCustomCollapsed ? (
            <MotionButton
              onClick={() => setIsCustomCollapsed(false)}
              title={t('actions.custom_open', 'Open Custom Action Input')}
              className="shrink-0 inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-gray-500/10 hover:bg-gray-500/20 border border-fantasy-border/45 hover:border-fantasy-accent/60 text-[11px] font-mono text-gray-200 hover:text-fantasy-accent transition-colors"
            >
              <PenLine size={12} />
              <span>{t('actions.custom')}</span>
            </MotionButton>
          ) : (
            <div className="relative flex-1 min-w-0 flex items-center gap-1">
              <form onSubmit={handleCustomSubmit} className="relative flex-1 min-w-0">
                <input
                  type="text"
                  value={customAction}
                  onChange={(e) => setCustomAction(e.target.value)}
                  disabled={isBusy}
                  placeholder={
                    phoneOpen
                      ? t('actions.phone_open')
                      : isStreaming
                        ? t('actions.chronicler_speaking')
                        : processing
                          ? t('actions.thinking')
                          : t('actions.custom_placeholder')
                  }
                  className="hk-input h-9 pl-3 pr-9 text-xs sm:text-sm disabled:opacity-50"
                />
                <button
                  type="submit"
                  disabled={!customAction.trim() || isBusy}
                  title={t('actions.custom_submit', 'Submit Custom Action')}
                  className="absolute right-1.5 top-1/2 -translate-y-1/2 p-1.5 rounded-md bg-fantasy-accent text-black hover:bg-fantasy-accent-hover transition-colors disabled:opacity-40 disabled:bg-gray-700"
                >
                  {processing && pendingAction?.custom_action_text ? (
                    <Loader2 size={12} className="animate-spin text-black" />
                  ) : (
                    <Send size={12} />
                  )}
                </button>
              </form>
              <MotionButton
                onClick={() => setIsCustomCollapsed(true)}
                title={t('actions.custom_minimize', 'Minimize Custom Action Input')}
                aria-label={t('actions.custom_minimize', 'Minimize Custom Action Input')}
                className="hk-icon-btn h-8 min-w-8 shrink-0"
              >
                <X size={13} />
              </MotionButton>
            </div>
          )}
        </div>

      </div>
    </AcrylicPanel>
  );
};

export default ActionPanel;
