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
  commsOffline = false,
  t,
}) {
  // Online Shop state
  const [shopData, setShopData] = useState(null);
  const [loadingShop, setLoadingShop] = useState(false);
  const [buyingItem, setBuyingItem] = useState(null);
  const [shopFeedback, setShopFeedback] = useState(null);

  // Requests / Bounties state
  const [bountySubTab, setBountySubTab] = useState('available'); // 'available' | 'active'
  const [bountySourceTab, setBountySourceTab] = useState('all'); // 'all' | 'generic' | 'faction'
  const [selectedFactionFilter, setSelectedFactionFilter] = useState('all');
  const [generatingBounties, setGeneratingBounties] = useState(false);
  const [busyBountyId, setBusyBountyId] = useState(null);
  const [bountyActionBanner, setBountyActionBanner] = useState(null);

  const isShopApp = activeApp === 'shop' || activeApp === 'school_shop';
  const storeMode = activeApp === 'school_shop' ? 'school_mart' : 'online_general';
  const boardMode = activeApp === 'school_bounties' ? 'school' : 'general';

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
  const tRef = useRef(t);
  tRef.current = t;
  const shopSeqRef = useRef(0);
  const shopAbortRef = useRef(null);
  const realtySeqRef = useRef(0);
  const realtyAbortRef = useRef(null);
  const autoBountiesAttemptedRef = useRef({ general: false, school: false });

  useEffect(() => {
    const nextSid = session?.id ?? null;
    if (prevSessionIdRef.current === nextSid) return;
    prevSessionIdRef.current = nextSid;
    setShopData(null);
    setShopFeedback(null);
    setBuyingItem(null);
    setGeneratingBounties(false);
    setBusyBountyId(null);
    setBountyActionBanner(null);
    setBountySourceTab('all');
    setSelectedFactionFilter('all');
    setRealtyData(sessionRef.current?.realty?.enabled ? sessionRef.current.realty : null);
    setRealtyBusy(false);
    setRealtyBanner(null);
    setSelectedSpareKeyNpc({});
    autoBountiesAttemptedRef.current = { general: false, school: false };
  }, [session?.id]);

  useEffect(() => {
    setBountySourceTab('all');
    setSelectedFactionFilter('all');
    setBountyActionBanner(null);
  }, [boardMode]);

  useEffect(() => {
    if (!isOpen || !isShopApp || commsOffline || !session?.id || !user?.user_id) {
      if (shopAbortRef.current) {
        try {
          shopAbortRef.current.abort();
        } catch {}
        shopAbortRef.current = null;
      }
      setLoadingShop(false);
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
    setShopData(null);
    setShopFeedback(null);
    apiCall(
      `/api/merchant/${session.id}?user_id=${user.user_id}&is_phone_shop=true&store_mode=${encodeURIComponent(storeMode)}`,
      { signal: controller.signal }
    )
      .then((data) => {
        if (seq === shopSeqRef.current) {
          setShopData(data);
        }
      })
      .catch((err) => {
        if (err?.isUserAbort || err?.name === 'AbortError' || seq !== shopSeqRef.current) return;
        setShopFeedback({
          type: 'error',
          text: err?.message || tRef.current?.('phone.shop_load_failed', 'Failed to load shop catalogue.') || 'Failed to load shop catalogue.',
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
  }, [isOpen, isShopApp, commsOffline, storeMode, session?.id, user?.user_id]);

  const handleBuyDeliveryItem = async (item) => {
    const reqSid = session?.id;
    if (!reqSid || !user?.user_id || buyingItem) return;
    setBuyingItem(item.name);
    setShopFeedback(null);
    try {
      const data = await apiCall('/api/merchant/buy', {
        method: 'POST',
        body: JSON.stringify({
          user_id: user.user_id,
          session_id: reqSid,
          item_name: item.name,
          is_phone_shop: true,
          store_mode: storeMode,
        }),
      });
      if ((sessionRef.current?.id ?? null) !== reqSid) return;
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
      if ((sessionRef.current?.id ?? null) !== reqSid) return;
      setShopFeedback({ type: 'error', text: err.message || 'Order failed.' });
    } finally {
      if ((sessionRef.current?.id ?? null) === reqSid) {
        setBuyingItem(null);
      }
    }
  };

  const handleRefreshBounties = async (factionId = undefined) => {
    const reqSid = session?.id;
    if (!reqSid || generatingBounties || !codexHook?.generateBounties) return;
    setGeneratingBounties(true);
    setBountyActionBanner(null);
    try {
      const targetFaction =
        factionId !== undefined
          ? factionId
          : bountySourceTab !== 'generic' && selectedFactionFilter !== 'all'
            ? selectedFactionFilter
            : null;
      let boardScope = 'general';
      if (boardMode === 'school') {
        boardScope = targetFaction || bountySourceTab === 'faction' ? 'faction' : 'school';
      } else if (targetFaction || bountySourceTab === 'faction') {
        boardScope = 'faction';
      } else if (bountySourceTab === 'generic') {
        boardScope = 'generic';
      }
      await codexHook.generateBounties(true, targetFaction, boardScope);
      if ((sessionRef.current?.id ?? null) !== reqSid) return;
      setBountyActionBanner({
        type: 'ok',
        text: t('phone.bounties.updated_ok', 'Requests updated from bulletin board!'),
      });
      if (onRefreshCodex) onRefreshCodex();
    } catch (err) {
      if ((sessionRef.current?.id ?? null) !== reqSid) return;
      setBountyActionBanner({
        type: 'error',
        text: err.message || t('phone.bounties.refresh_failed', 'Failed to refresh requests.'),
      });
    } finally {
      if ((sessionRef.current?.id ?? null) === reqSid) {
        setGeneratingBounties(false);
      }
    }
  };

  const handleAcceptBounty = async (questId, questTitle) => {
    const reqSid = session?.id;
    if (!reqSid || !codexHook?.bountyAction || busyBountyId) return;
    setBusyBountyId(questId);
    setBountyActionBanner(null);
    try {
      await codexHook.bountyAction(questId, 'accept');
      if ((sessionRef.current?.id ?? null) !== reqSid) return;
      setBountyActionBanner({
        type: 'ok',
        text: `✅ Accepted "${questTitle}" — Moved to Active Tasks!`,
      });
      if (onRefreshCodex) onRefreshCodex();
      if (onRefreshCharacter) onRefreshCharacter();
    } catch (err) {
      if ((sessionRef.current?.id ?? null) !== reqSid) return;
      setBountyActionBanner({ type: 'error', text: err.message || 'Could not accept request.' });
    } finally {
      if ((sessionRef.current?.id ?? null) === reqSid) {
        setBusyBountyId(null);
      }
    }
  };

  const handleAbandonBounty = async (questId, questTitle) => {
    const reqSid = session?.id;
    if (!reqSid || !codexHook?.bountyAction || busyBountyId) return;
    setBusyBountyId(questId);
    setBountyActionBanner(null);
    try {
      await codexHook.bountyAction(questId, 'abandon');
      if ((sessionRef.current?.id ?? null) !== reqSid) return;
      setBountyActionBanner({
        type: 'warn',
        text: `Dropped task "${questTitle}".`,
      });
      if (onRefreshCodex) onRefreshCodex();
      if (onRefreshCharacter) onRefreshCharacter();
    } catch (err) {
      if ((sessionRef.current?.id ?? null) !== reqSid) return;
      setBountyActionBanner({ type: 'error', text: err.message || 'Could not abandon request.' });
    } finally {
      if ((sessionRef.current?.id ?? null) === reqSid) {
        setBusyBountyId(null);
      }
    }
  };

  const isSchoolBountyItem = (b) =>
    Boolean(b?.bounty_scope === 'school' || b?.is_school_bounty);
  const isFactionBountyItem = (b) =>
    Boolean(
      b?.bounty_scope === 'faction' ||
        b?.faction_id ||
        b?.faction_name ||
        (b?.board_source && String(b.board_source).toLowerCase() !== 'general') ||
        String(b?.quest_id || '').startsWith('FBNT-')
    );

  const rawAvailableBounties = codexHook?.availableBounties || [];
  const generalAvailableBounties = rawAvailableBounties.filter((b) => !isSchoolBountyItem(b));
  const schoolAvailableBounties = rawAvailableBounties.filter((b) => isSchoolBountyItem(b));
  const allAvailableBounties =
    boardMode === 'school' ? schoolAvailableBounties : generalAvailableBounties;

  const rawFactions = codexHook?.factions || [];
  const factionsList = rawFactions.filter((f) =>
    boardMode === 'school' ? Boolean(f?.is_school_club) : !f?.is_school_club
  );

  const availableBounties = allAvailableBounties.filter((b) => {
    if (bountySourceTab === 'generic' && isFactionBountyItem(b)) return false;
    if (bountySourceTab === 'faction' && !isFactionBountyItem(b)) return false;
    if (selectedFactionFilter === 'all' || bountySourceTab === 'generic') return true;
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
            q.quest_type.includes('Gig')))) &&
      (boardMode === 'school' ? isSchoolBountyItem(q) : !isSchoolBountyItem(q))
  );

  const codexGenerateBountiesRef = useRef(codexHook?.generateBounties);
  codexGenerateBountiesRef.current = codexHook?.generateBounties;
  const isBountyApp = activeApp === 'bounties' || activeApp === 'school_bounties';

  useEffect(() => {
    if (!isOpen || !isBountyApp || commsOffline) {
      autoBountiesAttemptedRef.current = { general: false, school: false };
      return;
    }
    if (
      allAvailableBounties.length === 0 &&
      !generatingBounties &&
      !autoBountiesAttemptedRef.current[boardMode] &&
      codexGenerateBountiesRef.current
    ) {
      autoBountiesAttemptedRef.current[boardMode] = true;
      const reqSid = sessionRef.current?.id ?? null;
      setGeneratingBounties(true);
      const initialScope = boardMode === 'school' ? 'school' : 'general';
      Promise.resolve(codexGenerateBountiesRef.current(false, null, initialScope))
        .catch(() => {})
        .finally(() => {
          if ((sessionRef.current?.id ?? null) === reqSid) {
            setGeneratingBounties(false);
          }
        });
    }
  }, [isOpen, isBountyApp, commsOffline, boardMode, allAvailableBounties.length, generatingBounties]);

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
    storeMode,
    shopData,
    loadingShop,
    buyingItem,
    shopFeedback,
    setShopFeedback,
    handleBuyDeliveryItem,

    boardMode,
    bountySubTab,
    setBountySubTab,
    bountySourceTab,
    setBountySourceTab,
    selectedFactionFilter,
    setSelectedFactionFilter,
    generatingBounties,
    busyBountyId,
    bountyActionBanner,
    setBountyActionBanner,
    allAvailableBounties,
    generalAvailableBounties,
    schoolAvailableBounties,
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
