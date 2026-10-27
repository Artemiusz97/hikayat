/**
 * Clean, grammatically natural location formatting helpers for Quests, Codex,
 * Smartphone, and World Map badges (while leaving Scene & World's tiered display intact).
 */

export const dedupeLocationStutter = (text) => {
  if (!text) return '';
  let res = String(text);
  // 1. 'WordA-WordB WordA ...' -> 'WordA-WordB ...' (e.g. 'Neon-Mirage Neon Shopping Arcade' -> 'Neon-Mirage Shopping Arcade')
  res = res.replace(/\b([A-Za-z]{3,})(-[A-Za-z0-9]+)\s+\1\b/gi, '$1$2');
  // 2. 'WordA-WordB WordB ...' -> 'WordA-WordB ...' (e.g. 'Ouka-Central Central Transit' -> 'Ouka-Central Transit')
  res = res.replace(/\b([A-Za-z0-9]+-([A-Za-z]{3,}))\s+\2\b/gi, '$1');
  // 3. 'WordA WordA ...' -> 'WordA ...'
  res = res.replace(/\b([A-Za-z]{3,})\s+\1\b/gi, '$1');
  return res;
};

export const parseCleanLocationParts = (rawLoc) => {
  if (!rawLoc) {
    return { zone: '', facility: '', subRoom: '', primary: '', secondary: '' };
  }
  const cleanRaw = dedupeLocationStutter(String(rawLoc).trim());
  const parts = cleanRaw
    .split(/\s*(?:➔|->|✖)\s*/)
    .map(p => dedupeLocationStutter(p.trim()))
    .filter(Boolean);

  while (parts.length > 1 && parts[parts.length - 1].toLowerCase() === 'main area') {
    parts.pop();
  }

  if (parts.length === 0) {
    return { zone: '', facility: '', subRoom: '', primary: cleanRaw, secondary: '' };
  }

  if (parts.length === 1) {
    return { zone: parts[0], facility: parts[0], subRoom: '', primary: parts[0], secondary: '' };
  }

  if (parts.length === 2) {
    const [zone, facility] = parts;
    if (facility.toLowerCase() === zone.toLowerCase() || facility.toLowerCase().includes(zone.toLowerCase())) {
      return { zone, facility, subRoom: '', primary: facility, secondary: '' };
    }
    return { zone, facility, subRoom: '', primary: facility, secondary: zone };
  }

  const zone = parts[0];
  const facility = parts[1];
  const subRoom = parts[parts.length - 1];
  if (subRoom.toLowerCase() === facility.toLowerCase()) {
    const sameZone = facility.toLowerCase() === zone.toLowerCase() || facility.toLowerCase().includes(zone.toLowerCase());
    return { zone, facility, subRoom: '', primary: facility, secondary: sameZone ? '' : zone };
  }
  return {
    zone,
    facility,
    subRoom,
    primary: `${subRoom} · ${facility}`,
    secondary: zone && !facility.toLowerCase().includes(zone.toLowerCase()) ? zone : '',
  };
};

export const formatCleanLocation = (rawLoc, { includeZone = true, style = 'badge' } = {}) => {
  if (!rawLoc) return '';
  const { zone, facility, subRoom, primary, secondary } = parseCleanLocationParts(rawLoc);
  if (!primary) return '';

  if (style === 'short' || !includeZone) {
    return subRoom ? `${subRoom} (${facility})` : facility || primary;
  }

  if (style === 'prose') {
    if (subRoom) {
      return secondary ? `${subRoom} at ${facility} in ${secondary}` : `${subRoom} at ${facility}`;
    }
    return secondary ? `${facility} in ${secondary}` : facility || primary;
  }

  // Default 'badge' style: Facility first, Zone in parentheses so truncation never hides the facility name
  return secondary ? `${primary} (${secondary})` : primary;
};

const PROSE_LOC_SEG = `[A-Z0-9][A-Za-z0-9.\\-'’:]*(?:\\s+(?:(?:of|the|&)\\s+)?[A-Z0-9][A-Za-z0-9.\\-'’:]*){0,7}`;
const PROSE_TIERED_ARROW_RE = new RegExp(
  `(${PROSE_LOC_SEG})\\s*(?:➔|->)\\s*(${PROSE_LOC_SEG})(?:\\s*(?:➔|->)\\s*(${PROSE_LOC_SEG}))?`,
  'g'
);

export const cleanProseLocations = (text, { includeZone = true } = {}) => {
  if (!text) return '';
  const deduped = dedupeLocationStutter(String(text));
  if (!deduped.includes('➔') && !deduped.includes('->')) {
    return deduped;
  }

  return deduped.replace(PROSE_TIERED_ARROW_RE, (_match, seg1, seg2, seg3) => {
    let s1 = (seg1 || '').trim();
    let s2 = (seg2 || '').trim();
    let s3 = (seg3 || '').trim();

    let trailingPunct = '';
    const lastSeg = s3 || s2;
    if (lastSeg.endsWith('.') && !/\b[A-Z]\.[A-Z]\.$/.test(lastSeg)) {
      trailingPunct = '.';
      if (s3) {
        s3 = s3.slice(0, -1).trimEnd();
      } else {
        s2 = s2.slice(0, -1).trimEnd();
      }
    }

    const combined = [s1, s2, s3].filter(Boolean).join(' ➔ ');
    const formatted = formatCleanLocation(combined, { includeZone, style: 'prose' });
    return `${formatted}${trailingPunct}`;
  });
};
