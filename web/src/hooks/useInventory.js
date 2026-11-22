import { useState, useCallback, useEffect, useRef } from 'react';
import { apiCall } from '../api/client';

export const useInventory = (user) => {
  const [items, setItems] = useState([]);
  const [equipment, setEquipment] = useState({});
  const [capacity, setCapacity] = useState(10);
  const [propertyBonusSlots, setPropertyBonusSlots] = useState(0);
  const [usedSlots, setUsedSlots] = useState(0);
  const [gold, setGold] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const fetchSeqRef = useRef(0);
  const abortRef = useRef(null);

  const fetchInventory = useCallback(async () => {
    if (!user) {
      fetchSeqRef.current += 1;
      if (abortRef.current) {
        try {
          abortRef.current.abort();
        } catch {}
        abortRef.current = null;
      }
      setItems([]);
      setEquipment({});
      setCapacity(10);
      setPropertyBonusSlots(0);
      setUsedSlots(0);
      setGold(0);
      setError(null);
      setLoading(false);
      return;
    }
    if (abortRef.current) {
      try {
        abortRef.current.abort();
      } catch {}
    }
    const seq = ++fetchSeqRef.current;
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      setLoading(true);
      setError(null);
      const data = await apiCall(`/api/inventory/${user.user_id}`, {
        signal: controller.signal,
      });
      if (seq !== fetchSeqRef.current) return;
      setItems(data.items || []);
      setEquipment(data.equipment || {});
      setCapacity(data.capacity || 10);
      setPropertyBonusSlots(data.property_bonus_slots || 0);
      setUsedSlots(data.used_slots || 0);
      setGold(data.gold || 0);
    } catch (err) {
      if (err?.isUserAbort || err?.name === 'AbortError' || seq !== fetchSeqRef.current) return;
      console.error("Failed to fetch inventory:", err);
      setError(err.message || "Failed to load inventory");
    } finally {
      if (seq === fetchSeqRef.current) {
        setLoading(false);
        if (abortRef.current === controller) {
          abortRef.current = null;
        }
      }
    }
  }, [user]);

  useEffect(() => {
    fetchInventory();
    return () => {
      fetchSeqRef.current += 1;
      if (abortRef.current) {
        try {
          abortRef.current.abort();
        } catch {}
        abortRef.current = null;
      }
    };
  }, [fetchInventory]);

  const equipItem = async (itemId, slot) => {
    if (!user) return;
    try {
      await apiCall('/api/inventory/equip', {
        method: 'POST',
        body: JSON.stringify({
          user_id: user.user_id,
          item_id: itemId,
          slot: slot
        })
      });
      await fetchInventory();
    } catch (err) {
      console.error("Failed to equip item:", err);
      throw err;
    }
  };

  const unequipSlot = async (slot) => {
    if (!user) return;
    try {
      await apiCall('/api/inventory/unequip', {
        method: 'POST',
        body: JSON.stringify({
          user_id: user.user_id,
          slot: slot
        })
      });
      await fetchInventory();
    } catch (err) {
      console.error("Failed to unequip slot:", err);
      throw err;
    }
  };

  const dropItem = async (itemId) => {
    if (!user) return;
    try {
      await apiCall('/api/inventory/drop', {
        method: 'POST',
        body: JSON.stringify({
          user_id: user.user_id,
          item_id: itemId
        })
      });
      await fetchInventory();
    } catch (err) {
      console.error("Failed to drop item:", err);
      throw err;
    }
  };

  const useItem = async (
    itemId,
    sessionId = null,
    targetType = 'self',
    targetName = 'self',
    targetUserId = null
  ) => {
    if (!user) return null;
    const res = await apiCall('/api/inventory/use', {
      method: 'POST',
      body: JSON.stringify({
        user_id: user.user_id,
        item_id: itemId,
        target_type: targetType,
        target_name: targetName,
        target_user_id: targetUserId,
        session_id: sessionId
      })
    });
    await fetchInventory();
    return res;
  };

  return {
    items,
    equipment,
    capacity,
    propertyBonusSlots,
    usedSlots,
    gold,
    loading,
    error,
    refreshInventory: fetchInventory,
    equipItem,
    unequipSlot,
    dropItem,
    useItem
  };
};
