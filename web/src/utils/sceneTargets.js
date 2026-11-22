/**
 * Shared helpers for normalizing scene actors, filtering anomalous entities,
 * and grouping identical unequipped inventory items into stackable rows.
 */

export const normalizeActorName = (entry) => {
  if (!entry) return '';
  if (typeof entry === 'string') return entry.trim();
  if (typeof entry === 'object') {
    return String(entry.name || entry.npc_name || entry.label || entry.username || '').trim();
  }
  return '';
};

export const isAnomalousNpc = (entry) => {
  if (!entry || typeof entry !== 'object') return false;
  const npcType = String(entry.npc_type || '').trim().toLowerCase();
  const socialRoleType = String(entry.social_role_type || '').trim().toLowerCase();
  const anomTag = String(
    entry.anomalous_npc_tag || entry.basic_info?.anomalous_npc_tag || ''
  )
    .trim()
    .toLowerCase();
  return Boolean(
    entry.is_anomalous_entity ||
      entry.is_anomalous ||
      entry.anomalous ||
      npcType === 'anomaly' ||
      socialRoleType === 'anomaly' ||
      anomTag === 'anomaly_entity'
  );
};

export const groupInventoryItems = (items = []) => {
  if (!Array.isArray(items) || items.length === 0) return [];
  const map = new Map();
  for (const it of items) {
    if (!it || typeof it !== 'object') continue;
    const qty = Math.max(1, Number(it.count ?? 1) || 1);
    const key = `${it.name || ''}::${it.item_type || it.type || ''}::${it.effect || ''}`;
    if (map.has(key)) {
      const existing = map.get(key);
      existing.count += qty;
      existing.groupedIds.push(it.id);
    } else {
      map.set(key, {
        ...it,
        count: qty,
        groupedIds: [it.id],
      });
    }
  }
  return Array.from(map.values());
};
