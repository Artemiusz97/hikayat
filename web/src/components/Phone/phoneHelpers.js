export const formatTimestamp = (ts, clockFormat = '12h') => {
  if (!ts) return 'Just now';
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    hour12: clockFormat === '12h',
  });
};

export const getAvatarInitial = (name) => {
  if (!name || typeof name !== 'string') return '?';
  const stripped = name
    .replace(/\s*\((?:née|nee)\s+[^)]*\)/i, '')
    .replace(
      /^(?:mr|ms|mrs|miss|mx|dr|prof|professor|coach|nurse|chef|dean|principal|headmaster|headmistress|madam|madame|sensei|officer|capt|captain)\.?\s+/i,
      ''
    )
    .trim();
  return (stripped || name.trim())[0]?.toUpperCase() || '?';
};

const DM_ATTACHMENT_RE_GLOBAL =
  /\[Attached\s+(?:(Bonus)\s+)?(Intimate\s+)?(Photo|Video)\s*:\s*([\s\S]*?)\]/gi;

export const parseDmMediaAttachment = (rawMessage = '') => {
  const raw = String(rawMessage || '');
  const matches = Array.from(raw.matchAll(DM_ATTACHMENT_RE_GLOBAL));
  if (matches.length === 0) {
    return { cleanText: raw, attachment: null, attachments: [] };
  }
  const attachments = matches.map((match) => {
    const isBonus = Boolean(match[1]);
    const isIntimate = Boolean(match[2]);
    const kind = String(match[3] || 'Photo').toLowerCase();
    const isVideo = kind === 'video';
    const caption = String(match[4] || '').trim();
    return {
      mediaType: `${isIntimate ? 'nsfw_' : ''}${isVideo ? 'video' : 'photo'}`,
      caption,
      isVideo,
      isIntimate,
      isBonus,
    };
  });
  const cleanText = raw
    .replace(DM_ATTACHMENT_RE_GLOBAL, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();

  return {
    cleanText,
    attachment: attachments[0] || null,
    attachments,
  };
};

export const matchDmAttachmentToGallery = (
  attachment,
  msgTimestamp,
  contactName,
  mediaGallery = [],
  contactNpcId = ''
) => {
  if (!attachment || !Array.isArray(mediaGallery) || mediaGallery.length === 0) return null;
  const normCap = String(attachment.caption || '').trim().toLowerCase();
  const normContact = String(contactName || '').trim().toLowerCase();
  const normNpcId = String(contactNpcId || '').trim().toLowerCase();

  const contactMatches = (m) => {
    const mNpcId = String(m?.contact_npc_id || '').trim().toLowerCase();
    const mContact = String(m?.contact_name || '').trim().toLowerCase();
    if (!mNpcId && !mContact) return false;
    if (normNpcId && mNpcId) {
      if (mNpcId === normNpcId) return true;
      // Only fall back to contact_name when normNpcId looks like a display name rather than a distinct slug
      if (normNpcId.includes(' ') && normContact && mContact === normContact) return true;
      return false;
    }
    if (normContact && mContact) {
      return mContact === normContact;
    }
    return false;
  };

  const typeMatches = (m) => {
    const mType = String(m?.media_type || '').toLowerCase();
    return Boolean(attachment.isVideo) === mType.includes('video');
  };

  // 1. Caption match scoped to contact AND media type (photo vs video)
  if (normCap) {
    const exactMatch = mediaGallery.find((m) => {
      if (!m || !contactMatches(m) || !typeMatches(m)) return false;
      const mCap = String(m.caption || '').trim().toLowerCase();
      if (!mCap) return false;
      return mCap === normCap || mCap.includes(normCap) || normCap.includes(mCap);
    });
    if (exactMatch) return exactMatch;
  }

  // 2. Fallback to same contact + media type strictly near a valid finite timestamp
  const targetTs = Number(msgTimestamp);
  if (!Number.isFinite(targetTs) || targetTs <= 0) return null;
  let best = null;
  let bestDiff = Infinity;
  for (const m of mediaGallery) {
    if (!m || !contactMatches(m) || !typeMatches(m)) continue;
    const itemTs = Number(m.timestamp);
    if (!Number.isFinite(itemTs) || itemTs <= 0) continue;
    const diff = Math.abs(itemTs - targetTs);
    if (diff <= 60 && diff <= bestDiff) {
      best = m;
      bestDiff = diff;
    }
  }
  return best;
};
