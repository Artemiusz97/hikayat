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
