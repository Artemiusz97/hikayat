import { useState, useEffect, useRef, useCallback } from 'react';
import { apiCall } from '../../api/client';

export function usePhoneCommerceControllers({
  isOpen,
  activeApp,
  session,
  user,
  codexHook,
  onRefreshInventory,
  onRefreshCharacter,
  onRefreshCodex,
  t,
}) {
  // Online Shop state
  const [shopData, setShopData] = useState(null);
  const [loadingShop, setLoadingShop] = useState(false);
  const [buyingItem, setBuyingItem] = useState(null);
  const [shopFeedback, setShopFeedback] = useState(null);

  // Requests / Bounties state
  const [bountySubTab, setBountySubTab] = useState('available'); // 'available' | 'active'
  const [selectedFactionFilter, setSelectedFactionFilter] = useState('all');
  const [generatingBounties, setGeneratingBounties] = useState(false);
  const [busyBountyId, setBusyBountyId] = useState(null);
  const [bountyActionBanner, setBountyActionBanner] = useState(null);

  // Realty & Safehouses state
  const [realtyData, setRealtyData] = useState(null);
  const [loadingRealty, setLoadingRealty] = useState(false);
  const [realtySubTab, setRealtySubTab] = useState('owned'); // 'owned' | 'market'
  const [realtyBusy, setRealtyBusy] = useState(false);
  const [realtyBanner, setRealtyBanner] = useState(null);
  const [selectedSpareKeyNpc, setSelectedSpareKeyNpc] = useState({});

  const prevSessionIdRef = useRef(session?.id ?? null);
  const sessionRef = useRef(session);
  sessionRef.current = session;
  const shopSeqRef = useRef(0);
  const shopAbortRef = useRef(null);
  const realtySeqRef = useRef(0);
  const realtyAbortRef = useRef(null);

  useEffect(() => {
    const nextSid = session?.id ?? null;
    if (prevSessionIdRef.current === nextSid) return;
    prevSessionIdRef.current = nextSid;
    setShopData(null);
    setShopFeedback(null);
    setBountyActionBanner(null);
    setSelectedFactionFilter('all');
    setRealtyData(sessionRef.current?.realty?.enabled ? sessionRef.current.realty : null);
    setRealtyBanner(null);
    setSelectedSpareKeyNpc({});
  }, [session?.id]);

  useEffect(() => {
    if (!isOpen || activeApp !== 'shop' || !session?.id || !user?.user_id) {
      if (shopAbortRef.current) {
        try {
          shopAbortRef.current.abort();
        } catch {}
        shopAbortRef.current = null;
      }
      return;
    }
    if (shopAbortRef.current) {
      try {
        shopAbortRef.current.abort();
      } catch {}
    }
    const seq = ++shopSeqRef.current;
    const controller = new AbortController();
    shopAbortRef.current = controller;
    setLoadingShop(true);
    setShopFeedback(null);
    apiCall(`/api/merchant/${session.id}?user_id=${user.user_id}&is_phone_shop=true`, {
      signal: controller.signal,
    })
      .then((data) => {
        if (seq === shopSeqRef.current) {
          setShopData(data);
        }
      })
      .catch((err) => {
        if (err?.isUserAbort || err?.name === 'AbortError' || seq !== shopSeqRef.current) return;
        setShopFeedback({
          type: 'error',
          text: err?.message || t('phone.shop_load_failed', 'Failed to load shop catalogue.'),
        });
      })
      .finally(() => {
        if (seq === shopSeqRef.current) {
          setLoadingShop(false);
          if (shopAbortRef.current === controller) {
            shopAbortRef.current = null;
          }
        }
      });
    return () => {
      try {
        controller.abort();
      } catch {}
    };
  }, [isOpen, activeApp, session?.id, user?.user_id, t]);

  const handleBuyDeliveryItem = async (item) => {
    if (!session?.id || !user?.user_id || buyingItem) return;
    setBuyingItem(item.name);
    setShopFeedback(null);
    try {
      const data = await apiCall('/api/merchant/buy', {
        method: 'POST',
        body: JSON.stringify({
          user_id: user.user_id,
          session_id: session.id,
          item_name: item.name,
          is_phone_shop: true,
        }),
      });
      setShopFeedback({ type: 'ok', text: data.message || `Ordered ${item.name}!` });
      setShopData((prev) =>
        prev
          ? {
              ...prev,
              gold: data.gold ?? prev.gold,
              inventory: Array.isArray(data.stock) ? data.stock : prev.inventory,
              stock: Array.isArray(data.stock) ? data.stock : prev.stock,
            }
          : prev
      );
      if (onRefreshInventory) onRefreshInventory();
      if (onRefreshCharacter) onRefreshCharacter();
    } catch (err) {
      setShopFeedback({ type: 'error', text: err.message || 'Order failed.' });
    } finally {
      setBuyingItem(null);
    }
  };

  const handleRefreshBounties = async (factionId = null) => {
    if (generatingBounties || !codexHook?.generateBounties) return;
    setGeneratingBounties(true);
    setBountyActionBanner(null);
    try {
      const targetFaction =
        factionId !== undefined ? factionId : selectedFactionFilter !== 'all' ? selectedFactionFilter : null;
      await codexHook.generateBounties(true, targetFaction);
      setBountyActionBanner({ type: 'ok', text: 'Requests updated from bulletin board!' });
      if (onRefreshCodex) onRefreshCodex();
    } catch (err) {
      setBountyActionBanner({ type: 'error', text: err.message || 'Failed to refresh requests.' });
    } finally {
      setGeneratingBounties(false);
    }
  };

  const handleAcceptBounty = async (questId, questTitle) => {
    if (!codexHook?.bountyAction || busyBountyId) return;
    setBusyBountyId(questId);
    setBountyActionBanner(null);
    try {
      await codexHook.bountyAction(questId, 'accept');
      setBountyActionBanner({
        type: 'ok',
        text: `✅ Accepted "${questTitle}" — Moved to Active Tasks!`,
      });
      if (onRefreshCodex) onRefreshCodex();
      if (onRefreshCharacter) onRefreshCharacter();
    } catch (err) {
      setBountyActionBanner({ type: 'error', text: err.message || 'Could not accept request.' });
    } finally {
      setBusyBountyId(null);
    }
  };

  const handleAbandonBounty = async (questId, questTitle) => {
    if (!codexHook?.bountyAction || busyBountyId) return;
    setBusyBountyId(questId);
    setBountyActionBanner(null);
    try {
      await codexHook.bountyAction(questId, 'abandon');
      setBountyActionBanner({
        type: 'warn',
        text: `Dropped task "${questTitle}".`,
      });
      if (onRefreshCodex) onRefreshCodex();
      if (onRefreshCharacter) onRefreshCharacter();
    } catch (err) {
      setBountyActionBanner({ type: 'error', text: err.message || 'Could not abandon request.' });
    } finally {
      setBusyBountyId(null);
    }
  };

  const allAvailableBounties = codexHook?.availableBounties || [];
  const factionsList = codexHook?.factions || [];

  const availableBounties = allAvailableBounties.filter((b) => {
    if (selectedFactionFilter === 'all') return true;
    const bFaction = String(b.faction_id || b.faction_name || b.faction || '').toLowerCase();
    const bSource = String(b.board_source || '').toLowerCase();
    const targetF = factionsList.find(
      (f) => f.faction_id === selectedFactionFilter || f.name === selectedFactionFilter
    );
    const targetId = String(targetF?.faction_id || selectedFactionFilter || '').toLowerCase();
    const targetName = String(targetF?.name || '').toLowerCase();
    const targetArch = String(targetF?.archetype_key || '').toLowerCase();
    return (
      (targetArch && bSource === targetArch) ||
      bFaction === targetId ||
      (targetName && bFaction.includes(targetName)) ||
      (b.title && targetName && b.title.toLowerCase().includes(targetName)) ||
      (b.objective && targetName && b.objective.toLowerCase().includes(targetName))
    );
  });

  const activeBounties = (codexHook?.quests || []).filter(
    (q) =>
      q.status === 'Active' &&
      ((q.quest_id && (q.quest_id.startsWith('BNT-') || q.quest_id.startsWith('FBNT-'))) ||
        (q.quest_type &&
          (q.quest_type.includes('Bounty') ||
            q.quest_type.includes('Request') ||
            q.quest_type.includes('Commission') ||
            q.quest_type.includes('Gig'))))
  );

  const autoBountiesAttemptedRef = useRef(false);
  const codexGenerateBountiesRef = useRef(codexHook?.generateBounties);
  codexGenerateBountiesRef.current = codexHook?.generateBounties;

  useEffect(() => {
    if (!isOpen || activeApp !== 'bounties') {
      autoBountiesAttemptedRef.current = false;
      return;
    }
    if (
      allAvailableBounties.length === 0 &&
      !generatingBounties &&
      !autoBountiesAttemptedRef.current &&
      codexGenerateBountiesRef.current
    ) {
      autoBountiesAttemptedRef.current = true;
      setGeneratingBounties(true);
      Promise.resolve(codexGenerateBountiesRef.current())
        .catch(() => {})
        .finally(() => setGeneratingBounties(false));
    }
  }, [isOpen, activeApp, allAvailableBounties.length, generatingBounties]);

  const fetchRealty = useCallback(async () => {
    if (!session?.id) return;
    if (realtyAbortRef.current) {
      try {
        realtyAbortRef.current.abort();
      } catch {}
    }
    const seq = ++realtySeqRef.current;
    const controller = new AbortController();
    realtyAbortRef.current = controller;
    setLoadingRealty(true);
    setRealtyBanner(null);
    try {
      const uidQuery = user?.user_id ? `?user_id=${user.user_id}` : '';
      const data = await apiCall(`/api/realty/${session.id}${uidQuery}`, {
        signal: controller.signal,
      });
      if (seq === realtySeqRef.current) {
        setRealtyData(data);
      }
    } catch (err) {
      if (err?.isUserAbort || err?.name === 'AbortError' || seq !== realtySeqRef.current) return;
      setRealtyBanner({ type: 'error', text: err.message || 'Failed to load Realty listings.' });
    } finally {
      if (seq === realtySeqRef.current) {
        setLoadingRealty(false);
        if (realtyAbortRef.current === controller) {
          realtyAbortRef.current = null;
        }
      }
    }
  }, [session?.id, user?.user_id]);

  useEffect(() => {
    if (isOpen && activeApp === 'realty' && session?.id) {
      fetchRealty();
      return () => {
        if (realtyAbortRef.current) {
          try {
            realtyAbortRef.current.abort();
          } catch {}
        }
      };
    }
    if (realtyAbortRef.current) {
      try {
        realtyAbortRef.current.abort();
      } catch {}
      realtyAbortRef.current = null;
    }
    return undefined;
  }, [isOpen, activeApp, session?.id, fetchRealty]);

  useEffect(() => {
    if (session?.realty && session.realty.enabled) {
      setRealtyData(session.realty);
    }
  }, [session?.realty]);

  const handleBuyProperty = async (propertyId) => {
    if (!session?.id || realtyBusy) return;
    setRealtyBusy(true);
    setRealtyBanner(null);
    try {
      const res = await apiCall(`/api/realty/${session.id}/purchase`, {
        method: 'POST',
        body: JSON.stringify({ user_id: user?.user_id, property_id: propertyId }),
      });
      setRealtyData(res);
      setRealtyBanner({ type: 'success', text: res.message || t('realty.purchased_ok', 'Deed purchased!') });
      if (onRefreshInventory) onRefreshInventory();
      if (onRefreshCharacter) onRefreshCharacter();
      if (onRefreshCodex) onRefreshCodex();
    } catch (err) {
      setRealtyBanner({ type: 'error', text: err.message || t('realty.purchase_failed', 'Purchase failed.') });
    } finally {
      setRealtyBusy(false);
    }
  };

  const handleSetPrimaryProperty = async (propertyId) => {
    if (!session?.id || realtyBusy) return;
    setRealtyBusy(true);
    setRealtyBanner(null);
    try {
      const res = await apiCall(`/api/realty/${session.id}/primary`, {
        method: 'POST',
        body: JSON.stringify({ user_id: user?.user_id, property_id: propertyId }),
      });
      setRealtyData(res);
      setRealtyBanner({ type: 'success', text: res.message || t('realty.primary_updated', 'Primary Home updated.') });
      if (onRefreshCodex) onRefreshCodex();
    } catch (err) {
      setRealtyBanner({ type: 'error', text: err.message || 'Failed to update Primary Home.' });
    } finally {
      setRealtyBusy(false);
    }
  };

  const handleManageSpareKey = async (propertyId, npcId, revoke = false) => {
    if (!session?.id || !npcId || realtyBusy) return;
    setRealtyBusy(true);
    setRealtyBanner(null);
    try {
      const res = await apiCall(`/api/realty/${session.id}/spare-key`, {
        method: 'POST',
        body: JSON.stringify({ user_id: user?.user_id, property_id: propertyId, npc_id: npcId, revoke }),
      });
      setRealtyData(res);
      setRealtyBanner({
        type: 'success',
        text:
          res.message ||
          (revoke ? t('realty.key_revoked', 'Spare key revoked.') : t('realty.key_granted', 'Spare key granted!')),
      });
    } catch (err) {
      setRealtyBanner({ type: 'error', text: err.message || 'Failed to update spare key.' });
    } finally {
      setRealtyBusy(false);
    }
  };

  return {
    shopData,
    loadingShop,
    buyingItem,
    shopFeedback,
    setShopFeedback,
    handleBuyDeliveryItem,

    bountySubTab,
    setBountySubTab,
    selectedFactionFilter,
    setSelectedFactionFilter,
    generatingBounties,
    busyBountyId,
    bountyActionBanner,
    setBountyActionBanner,
    allAvailableBounties,
    factionsList,
    availableBounties,
    activeBounties,
    handleRefreshBounties,
    handleAcceptBounty,
    handleAbandonBounty,

    realtyData,
    loadingRealty,
    realtySubTab,
    setRealtySubTab,
    realtyBusy,
    realtyBanner,
    setRealtyBanner,
    selectedSpareKeyNpc,
    setSelectedSpareKeyNpc,
    fetchRealty,
    handleBuyProperty,
    handleSetPrimaryProperty,
    handleManageSpareKey,
  };
}
