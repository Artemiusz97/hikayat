import { isAnomalousNpc, normalizeActorName } from './sceneTargets.js';

export const normalizeNpcKey = (value) => {
  if (!value) return '';
  if (typeof value === 'string') return value.trim().toLowerCase();
  if (typeof value === 'object') {
    const actor = normalizeActorName(value);
    if (actor) return actor.toLowerCase();
    const fallback = value.id ?? value.npc_id ?? value.npc_key ?? '';
    return String(fallback).trim().toLowerCase();
  }
  return String(value).trim().toLowerCase();
};

export const matchesNpcIdentity = (entry, targetNameOrKey) => {
  const needle = normalizeNpcKey(targetNameOrKey);
  if (!needle || !entry) return false;
  if (typeof entry === 'string') {
    return entry.trim().toLowerCase() === needle;
  }
  const slug = needle.replace(/\s+/g, '_');
  const candidates = [
    entry.name,
    entry.npc_name,
    entry.id,
    entry.npc_id,
    entry.npc_key,
  ];
  for (const cand of candidates) {
    if (cand === undefined || cand === null) continue;
    const norm = String(cand).trim().toLowerCase();
    if (!norm) continue;
    if (norm === needle || norm === slug || norm.replace(/\s+/g, '_') === slug) {
      return true;
    }
  }
  return false;
};

export const resolveDialoguePartnerSet = (session) => {
  let list = [];
  if (Array.isArray(session?.dialogue_partners)) {
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
  return new Set(
    list
      .map((n) => String(n || '').toLowerCase().trim())
      .filter(Boolean)
  );
};

export const unwrapDebugProfile = (raw) => {
  if (!raw || typeof raw !== 'object') return {};
  if (!raw.debug_revealed || !raw.debug_profile) return raw;
  return {
    ...raw,
    ...raw.debug_profile,
    appearance: {
      ...(raw.appearance || {}),
      ...(raw.debug_profile.appearance || {}),
    },
    basic_info: {
      ...(raw.basic_info || {}),
      ...(raw.debug_profile.basic_info || {}),
    },
  };
};

export const findLinkedPersonInRoster = (
  itemOrName,
  contactsList = [],
  loreEntities = [],
  { acquaintances = [], sceneNpcs = [] } = {}
) => {
  if (!itemOrName) return null;
  const rawName =
    typeof itemOrName === 'string'
      ? itemOrName.split('(')[0].trim()
      : String(itemOrName.name || itemOrName.title || '').split('(')[0].trim();
  const rawNpcId =
    typeof itemOrName === 'object' ? String(itemOrName.npc_id ?? itemOrName.id ?? itemOrName.npc_key ?? '').trim().toLowerCase() : '';
  const matchEntry = (candidate) => {
    if (!candidate) return false;
    return (rawName && matchesNpcIdentity(candidate, rawName)) || (rawNpcId && matchesNpcIdentity(candidate, rawNpcId));
  };
  if (!rawName && !rawNpcId) return null;

  const personal = (Array.isArray(contactsList) ? contactsList : []).filter((c) => c && !c.is_dispatch_channel);
  const inContacts = personal.find(matchEntry);
  if (inContacts) return { entry: inContacts, isSavedContact: true, kind: 'contact' };

  const acqList = Array.isArray(acquaintances) ? acquaintances : [];
  const inAcq = acqList.find(matchEntry);
  if (inAcq) return { entry: inAcq, isSavedContact: false, isAcquaintance: true, kind: 'acquaintance' };

  const lorePersons = (Array.isArray(loreEntities) ? loreEntities : []).filter(
    (e) => e && e.entity_type === 'person' && e.is_discovered !== false
  );
  const inWorld = lorePersons.find(matchEntry);
  if (inWorld) return { entry: inWorld, isSavedContact: false, kind: 'codex' };

  const sceneList = Array.isArray(sceneNpcs) ? sceneNpcs : [];
  const inScene = sceneList.find((entry) => !isAnomalousNpc(entry) && matchEntry(entry));
  if (inScene) {
    const sceneEntry = typeof inScene === 'string' ? { name: inScene } : inScene;
    return { entry: sceneEntry, isSavedContact: false, kind: 'scene' };
  }
  return null;
};

/**
 * Resolves a scene NPC name against live session state, saved Contacts,
 * Acquaintances, and Codex person lorebook entities for unified dossier display.
 */
export function resolveSceneNpcProfile(npcName, session, codex) {
  const cleanTarget = normalizeActorName(npcName);
  if (!cleanTarget) return null;

  const rawCurrentNpcs = Array.isArray(session?.current_npcs) ? session.current_npcs : [];
  const rawSceneMatch = rawCurrentNpcs.find((entry) => matchesNpcIdentity(entry, cleanTarget)) || null;
  const sceneNpc =
    rawSceneMatch && typeof rawSceneMatch === 'string'
      ? { name: rawSceneMatch }
      : rawSceneMatch && typeof rawSceneMatch === 'object'
        ? rawSceneMatch
        : null;

  const personalContacts = (Array.isArray(codex?.contacts) ? codex.contacts : []).filter(
    (c) => c && !c.is_dispatch_channel
  );
  const acquaintances = Array.isArray(codex?.acquaintances) ? codex.acquaintances : [];
  const lorePersons = (Array.isArray(codex?.lorebook?.entities) ? codex.lorebook.entities : []).filter(
    (e) => e && e.entity_type === 'person'
  );

  const contactMatch = personalContacts.find((c) => matchesNpcIdentity(c, cleanTarget)) || null;
  const acquaintanceMatch =
    !contactMatch ? acquaintances.find((a) => matchesNpcIdentity(a, cleanTarget)) || null : null;
  const loreMatch =
    !contactMatch && !acquaintanceMatch
      ? lorePersons.find((p) => matchesNpcIdentity(p, cleanTarget)) || null
      : null;

  const sourceKind = contactMatch
    ? 'contact'
    : acquaintanceMatch
      ? 'acquaintance'
      : loreMatch
        ? 'codex'
        : 'scene';

  const rosterTarget =
    sourceKind === 'contact'
      ? 'contacts'
      : sourceKind === 'acquaintance'
        ? 'acquaintances'
        : 'codex';

  const unwrappedBase = unwrapDebugProfile(contactMatch || acquaintanceMatch || loreMatch || {});
  const unwrappedScene = sceneNpc ? unwrapDebugProfile(sceneNpc) : null;

  const baseBasic = unwrappedBase.basic_info || {};
  const sceneBasic = unwrappedScene?.basic_info || {};
  const mergedBasicInfo = {
    ...baseBasic,
    ...Object.fromEntries(
      Object.entries(sceneBasic).filter(([, v]) => v !== undefined && v !== null && v !== '')
    ),
  };
  for (const field of [
    'role',
    'public_role',
    'occupation',
    'gender',
    'race',
    'age_group',
    'age',
    'grade',
    'club',
    'faction',
    'affiliation',
    'description',
    'mannerisms',
  ]) {
    if (!mergedBasicInfo[field] && unwrappedScene?.[field]) {
      mergedBasicInfo[field] = unwrappedScene[field];
    }
  }

  const mergedAppearance = {
    ...(unwrappedBase.appearance || {}),
    ...(unwrappedScene?.appearance || {}),
  };

  const liveClothing =
    unwrappedScene?.clothing_status ||
    unwrappedScene?.clothing ||
    unwrappedScene?.attire_summary ||
    unwrappedBase.clothing_status ||
    null;

  const liveActivity =
    unwrappedScene?.current_activity ||
    unwrappedScene?.activity ||
    unwrappedScene?.status_line ||
    unwrappedScene?.activity_tag ||
    unwrappedBase.current_activity ||
    null;

  const liveStatusEffects =
    Array.isArray(unwrappedScene?.status_effects) && unwrappedScene.status_effects.length > 0
      ? unwrappedScene.status_effects
      : unwrappedBase.status_effects || [];

  const resolvedScore =
    unwrappedBase.relationship_score ??
    unwrappedBase.affinity_score ??
    unwrappedBase.affinity ??
    unwrappedScene?.relationship_score ??
    unwrappedScene?.affinity_score ??
    unwrappedScene?.affinity ??
    0;

  const resolvedName =
    unwrappedBase.name ||
    unwrappedScene?.name ||
    unwrappedScene?.npc_name ||
    cleanTarget;

  const partnerSet = resolveDialoguePartnerSet(session);
  const isTalking = partnerSet.has(normalizeNpcKey(resolvedName));

  const mergedNpc = {
    ...unwrappedScene,
    ...unwrappedBase,
    id: unwrappedBase.id || unwrappedScene?.id || unwrappedScene?.npc_id || resolvedName,
    npc_id: unwrappedBase.npc_id || unwrappedScene?.npc_id || null,
    name: resolvedName,
    basic_info: mergedBasicInfo,
    appearance: mergedAppearance,
    relationship_score: resolvedScore,
    affinity: unwrappedBase.affinity ?? unwrappedScene?.affinity ?? resolvedScore,
    affinity_score: unwrappedBase.affinity_score ?? resolvedScore,
    clothing_status: liveClothing,
    dialogue_mood: unwrappedScene?.dialogue_mood || unwrappedBase.dialogue_mood || null,
    current_activity: liveActivity,
    activity_tag: unwrappedScene?.activity_tag || unwrappedBase.activity_tag || null,
    status_effects: liveStatusEffects,
    anomalous_npc_tag:
      unwrappedBase.anomalous_npc_tag ||
      unwrappedScene?.anomalous_npc_tag ||
      mergedBasicInfo.anomalous_npc_tag ||
      null,
    debug_revealed: Boolean(unwrappedBase.debug_revealed || unwrappedScene?.debug_revealed),
  };

  return {
    npc: mergedNpc,
    sourceKind,
    rosterTarget,
    isPresentInScene: Boolean(sceneNpc),
    isTalking,
    sceneNpc,
  };
}
