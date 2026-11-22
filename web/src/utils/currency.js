export const getScenarioCurrency = (scenarioKey) => {
  const key = String(scenarioKey || 'fantasy').trim().toLowerCase();

  if (key.includes('anomalous') || key.includes('sci_fi') || key.includes('scifi')) {
    return {
      key: 'credits',
      name: 'Credits',
      symbol: '₵',
      placement: 'prefix',
      icon: 'credit',
    };
  }

  if (key.includes('high_school') || key.includes('highschool')) {
    return {
      key: 'yen',
      name: 'Yen',
      symbol: '¥',
      placement: 'prefix',
      icon: 'yen',
    };
  }

  if (key.includes('slice_of_life')) {
    return {
      key: 'dollars',
      name: 'Cash',
      symbol: '$',
      placement: 'prefix',
      icon: 'dollar',
    };
  }

  if (key.includes('cyberpunk')) {
    return {
      key: 'eddies',
      name: 'Eurodollars',
      symbol: '€$',
      placement: 'suffix',
      icon: 'cyber',
    };
  }

  if (key.includes('steampunk')) {
    return {
      key: 'sovereigns',
      name: 'Sovereigns',
      symbol: '£',
      placement: 'prefix',
      icon: 'pound',
    };
  }

  if (key.includes('post_apocalypse') || key.includes('postapoc')) {
    return {
      key: 'caps',
      name: 'Caps',
      symbol: 'Caps',
      placement: 'suffix',
      icon: 'caps',
    };
  }

  if (key.includes('dark_fantasy')) {
    return {
      key: 'crowns',
      name: 'Crowns',
      symbol: 'Crowns',
      placement: 'suffix',
      icon: 'crown',
    };
  }

  return {
    key: 'gold',
    name: 'Gold',
    symbol: 'G',
    placement: 'suffix',
    icon: 'coins',
  };
};

export const formatScenarioCurrency = (amount, scenarioKey) => {
  const cur = getScenarioCurrency(scenarioKey);
  const formatted = Number(amount || 0).toLocaleString();
  if (cur.placement === 'prefix') {
    return `${cur.symbol}${formatted}`;
  }
  return `${formatted} ${cur.symbol}`;
};
