import { useState, useCallback, useEffect } from 'react';
import { apiCall } from '../api/client';

export const useAuth = () => {
  const [user, setUser] = useState(null);
  const [character, setCharacter] = useState(null);
  const [characters, setCharacters] = useState([]);
  const [loading, setLoading] = useState(true);

  // Re-hydrate from localStorage on mount
  useEffect(() => {
    const storedUser = localStorage.getItem('cf_user');
    if (storedUser) {
      try {
        const parsed = JSON.parse(storedUser);
        const resolvedId = parsed.user_id != null ? String(parsed.user_id) : null;
        const resolvedName = parsed.username || parsed.display_name || (resolvedId ? `User-${resolvedId.slice(-4)}` : 'Guest');
        setUser({
          ...parsed,
          user_id: resolvedId,
          username: resolvedName,
          display_name: resolvedName
        });
      } catch (e) {
        localStorage.removeItem('cf_user');
      }
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (user) {
      fetchCharacters();
      fetchActiveCharacter();
    }
  }, [user]);

  const loginGuest = async (displayName) => {
    const cleanName = (displayName || '').trim();
    const data = await apiCall('/api/auth/guest', {
      method: 'POST',
      body: JSON.stringify({ guest_name: cleanName, display_name: cleanName })
    });
    const userObj = {
      ...data,
      user_id: data.user_id_str || String(data.user_id),
      username: data.username || data.display_name || cleanName || 'Guest',
      display_name: data.display_name || data.username || cleanName || 'Guest'
    };
    localStorage.setItem('cf_user', JSON.stringify(userObj));
    setUser(userObj);
  };

  const loginDiscord = async (discordId) => {
    const cleanId = (discordId || '').trim();
    const data = await apiCall('/api/auth/discord', {
      method: 'POST',
      body: JSON.stringify({ user_id_or_name: cleanId, discord_id: cleanId })
    });
    const userObj = {
      ...data,
      user_id: data.user_id_str || String(data.user_id),
      username: data.username || data.display_name || cleanId || 'Discord User',
      display_name: data.display_name || data.username || cleanId || 'Discord User'
    };
    localStorage.setItem('cf_user', JSON.stringify(userObj));
    setUser(userObj);
  };

  const logout = () => {
    localStorage.removeItem('cf_user');
    setUser(null);
    setCharacter(null);
    setCharacters([]);
  };

  const fetchCharacters = async () => {
    if (!user) return;
    try {
      const data = await apiCall(`/api/characters/${user.user_id}`);
      const roster = data.characters || [];
      // Keep characters stably ordered by creation ID so their positions never jump when switching
      setCharacters([...roster].sort((a, b) => (a.id || 0) - (b.id || 0)));
    } catch (e) {
      console.warn("Failed to fetch characters roster");
    }
  };

  const fetchActiveCharacter = async () => {
    if (!user) return;
    try {
      const data = await apiCall(`/api/character/${user.user_id}`);
      if (data && data.character) {
        const canonicalId = data.character.user_id_str || String(data.character.user_id);
        if (user && user.user_id !== canonicalId) {
          const updatedUser = { ...user, user_id: canonicalId, user_id_str: canonicalId };
          localStorage.setItem('cf_user', JSON.stringify(updatedUser));
          setUser(updatedUser);
        }
        setCharacter({
          ...data.character,
          user_id: canonicalId,
          combat_attributes: data.combat_attributes,
          inventory_capacity: data.inventory_capacity,
          used_inventory_slots: data.used_inventory_slots,
          learned_spells: data.learned_spells,
          equipment: data.equipment,
          stat_names: data.stat_names,
          stat_effects: data.stat_effects
        });
      } else {
        setCharacter(data);
      }
    } catch (e) {
      setCharacter(null);
    }
  };

  const allocateStatPoint = async (stat) => {
    if (!user) return;
    const res = await apiCall('/api/character/allocate', {
      method: 'POST',
      body: JSON.stringify({ user_id: user.user_id, stat })
    });
    await fetchActiveCharacter();
    return res;
  };

  const createCharacter = async (nameOrPayload, class_name) => {
    const payload = typeof nameOrPayload === 'object' && nameOrPayload !== null
      ? { user_id: user.user_id, ...nameOrPayload }
      : { user_id: user.user_id, name: nameOrPayload, char_class: class_name || 'Warrior' };
    const res = await apiCall('/api/character/create', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    await fetchCharacters();
    await fetchActiveCharacter();
    return res;
  };
  
  const switchCharacter = async (charId) => {
    await apiCall('/api/character/switch', {
      method: 'POST',
      body: JSON.stringify({ user_id: user.user_id, character_id: charId })
    });
    await fetchCharacters();
    await fetchActiveCharacter();
  };

  const deleteCharacter = async (characterId) => {
    if (!user || !characterId) return null;
    const res = await apiCall(`/api/character/${user.user_id}/${characterId}`, {
      method: 'DELETE'
    });
    await fetchCharacters();
    await fetchActiveCharacter();
    return res;
  };

  const regenerateStarterGear = async () => {
    if (!user) return null;
    const res = await apiCall('/api/character/regenerate-gear', {
      method: 'POST',
      body: JSON.stringify({ user_id: user.user_id })
    });
    await fetchActiveCharacter();
    return res;
  };

  return {
    user,
    character,
    characters,
    loading,
    loginGuest,
    loginDiscord,
    logout,
    createCharacter,
    switchCharacter,
    deleteCharacter,
    regenerateStarterGear,
    allocateStatPoint,
    refreshCharacter: fetchActiveCharacter
  };
};
