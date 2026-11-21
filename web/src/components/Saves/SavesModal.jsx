import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Save, RotateCcw, Trash2, MapPin, Clock, Bookmark } from 'lucide-react';
import { apiCall } from '../../api/client';
import { AcrylicModal, MotionButton } from '../Common/MotionPrimitives';
import ConfirmDialog from '../Common/ConfirmDialog';
import { formatSaveDate } from '../../utils/timeFormat';

const SavesModal = ({ isOpen, onClose, user, onSessionLoaded }) => {
  const { t } = useTranslation();
  const [saves, setSaves] = useState([]);
  const [loading, setLoading] = useState(false);
  const [slotName, setSlotName] = useState('');
  const [busySlot, setBusySlot] = useState(null);
  const [feedback, setFeedback] = useState(null);
  const [confirmState, setConfirmState] = useState(null); // { mode: 'overwrite' | 'delete', slotName }

  const fetchSaves = useCallback(async () => {
    if (!user?.user_id) return;
    setLoading(true);
    try {
      const data = await apiCall(`/api/saves/${user.user_id}`);
      setSaves(data.saves || []);
    } catch (err) {
      setFeedback({ type: 'error', text: err.message || 'Failed to load save slots' });
    } finally {
      setLoading(false);
    }
  }, [user?.user_id]);

  useEffect(() => {
    if (isOpen) {
      setFeedback(null);
      setConfirmState(null);
      fetchSaves();
    }
  }, [isOpen, fetchSaves]);

  const executeSave = async (nameToSave) => {
    if (!nameToSave) return;
    setBusySlot(`save:${nameToSave}`);
    setFeedback(null);
    try {
      const res = await apiCall('/api/saves/save', {
        method: 'POST',
        body: JSON.stringify({
          user_id: user.user_id,
          slot_name: nameToSave,
          overwrite: true
        })
      });
      setSlotName('');
      setFeedback({ type: 'success', text: `Checkpoint "${res.slot_name}" saved!` });
      await fetchSaves();
    } catch (err) {
      setFeedback({ type: 'error', text: err.message || 'Could not save checkpoint' });
    } finally {
      setBusySlot(null);
    }
  };

  const handleSave = async (e, targetSlot = null) => {
    if (e) e.preventDefault();
    const nameToSave = (targetSlot || slotName || '').trim();
    if (!nameToSave) return;

    if (targetSlot) {
      setConfirmState({ mode: 'overwrite', slotName: targetSlot });
      return;
    }

    await executeSave(nameToSave);
  };

  const handleLoad = async (name) => {
    setBusySlot(`load:${name}`);
    setFeedback(null);
    try {
      const res = await apiCall('/api/saves/load', {
        method: 'POST',
        body: JSON.stringify({
          user_id: user.user_id,
          slot_name: name
        })
      });
      if (onSessionLoaded && res.session) {
        onSessionLoaded(res.session);
      }
      onClose();
    } catch (err) {
      setFeedback({ type: 'error', text: err.message || 'Failed to restore checkpoint' });
    } finally {
      setBusySlot(null);
    }
  };

  const executeDelete = async (name) => {
    if (!name) return;
    setBusySlot(`del:${name}`);
    setFeedback(null);
    try {
      await apiCall(`/api/saves/${user.user_id}/${encodeURIComponent(name)}`, {
        method: 'DELETE'
      });
      setFeedback({ type: 'success', text: `Deleted slot "${name}".` });
      await fetchSaves();
    } catch (err) {
      setFeedback({ type: 'error', text: err.message || 'Failed to delete slot' });
    } finally {
      setBusySlot(null);
    }
  };

  const handleDelete = (name) => {
    setConfirmState({ mode: 'delete', slotName: name });
  };

  const handleConfirmAction = async () => {
    if (!confirmState) return;
    const { mode, slotName: target } = confirmState;
    if (mode === 'overwrite') {
      await executeSave(target);
    } else if (mode === 'delete') {
      await executeDelete(target);
    }
    setConfirmState(null);
  };

  return (
    <AcrylicModal
      isOpen={isOpen}
      onClose={onClose}
      label={t('saves.title', 'Saves')}
      maxWidthClass="max-w-md"
    >
      {/* Header */}
      <div className="px-4 py-3.5 border-b border-fantasy-border/35 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <Bookmark size={18} className="text-fantasy-accent shrink-0" />
          <div className="min-w-0">
            <h3 className="font-rpg font-bold text-base text-fantasy-accent truncate">{t('saves.title')}</h3>
            <p className="text-[11px] text-gray-400">{t('saves.subtitle', { count: saves.length })}</p>
          </div>
        </div>
        <MotionButton onClick={onClose} aria-label={t('common.close', 'Close')} className="hk-icon-btn h-8 min-w-8 shrink-0">
          <X size={18} />
        </MotionButton>
      </div>

      {/* Create New Save Form */}
      <form onSubmit={handleSave} className="px-4 py-3 border-b border-fantasy-border/35 flex gap-2 shrink-0">
        <input
          type="text"
          maxLength={32}
          value={slotName}
          onChange={(e) => setSlotName(e.target.value)}
          placeholder={t('saves.name_placeholder')}
          className="flex-1 min-w-0 bg-fantasy-dark/70 border border-fantasy-border/60 rounded-lg px-3 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-fantasy-accent"
        />
        <MotionButton
          type="submit"
          disabled={!slotName.trim() || busySlot !== null}
          className="px-3 py-1.5 rounded-lg bg-fantasy-accent text-fantasy-dark font-bold text-xs flex items-center gap-1.5 disabled:opacity-40 transition-colors shrink-0"
        >
          <Save size={13} />
          <span>{t('saves.save')}</span>
        </MotionButton>
      </form>

      {/* Feedback Banner */}
      {feedback && (
        <div className={`mx-4 mt-3 p-2.5 rounded-xl border text-xs flex items-center justify-between shrink-0 ${
          feedback.type === 'error'
            ? 'bg-red-500/15 border-red-500/40 text-red-200'
            : 'bg-emerald-500/15 border-emerald-500/40 text-emerald-200'
        }`}>
          <span>{feedback.text}</span>
          <button type="button" onClick={() => setFeedback(null)} className="text-gray-400 hover:text-white">
            <X size={13} />
          </button>
        </div>
      )}

      {/* Save Slots List */}
      <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain custom-scrollbar px-4 py-2">
        {loading ? (
          <p className="text-center py-8 text-xs text-gray-400 italic">{t('saves.loading')}</p>
        ) : saves.length === 0 ? (
          <div className="text-center py-10 text-gray-400">
            <Save size={24} className="mx-auto mb-1.5 opacity-40" />
            <p className="text-xs">{t('saves.no_saves')}</p>
            <p className="text-[11px] text-gray-500 mt-1">{t('saves.hint')}</p>
          </div>
        ) : (
          <div className="divide-y divide-fantasy-border/30">
            {saves.map((slot) => (
              <div
                key={slot.id || slot.slot_name}
                className="py-3 space-y-2"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <span className="font-bold text-xs text-fantasy-accent block truncate">{slot.slot_name}</span>
                    <span className="text-xs font-semibold text-gray-200 block truncate">{slot.scene_title || 'Adventure'}</span>
                  </div>
                  <span className="text-[10px] font-mono text-gray-400 flex items-center gap-1 shrink-0">
                    <Clock size={10} /> {formatSaveDate(slot.saved_at)}
                  </span>
                </div>

                {slot.current_location && (
                  <div className="text-[11px] text-gray-400 flex items-center gap-1 truncate">
                    <MapPin size={11} className="text-amber-400 shrink-0" />
                    <span className="truncate">{slot.current_location}</span>
                  </div>
                )}

                {slot.narrative_snippet && (
                  <p className="text-[11px] text-gray-400 line-clamp-2 italic">"{slot.narrative_snippet}"</p>
                )}

                <div className="flex items-center justify-end gap-1.5 pt-1">
                  <MotionButton
                    onClick={(e) => handleSave(e, slot.slot_name)}
                    disabled={busySlot !== null}
                    className="px-2 py-1 rounded-lg bg-gray-500/15 hover:bg-gray-500/25 text-gray-200 border border-fantasy-border/40 text-[10px] font-semibold uppercase flex items-center gap-1"
                    title={t('saves.overwrite_tooltip', 'Overwrite this slot')}
                  >
                    <Save size={11} /> {t('saves.overwrite')}
                  </MotionButton>
                  <MotionButton
                    onClick={() => handleLoad(slot.slot_name)}
                    disabled={busySlot !== null}
                    className="px-2.5 py-1 rounded-lg bg-fantasy-accent/20 hover:bg-fantasy-accent/30 text-fantasy-accent border border-fantasy-accent/50 text-[10px] font-bold uppercase flex items-center gap-1"
                  >
                    <RotateCcw size={11} /> {t('saves.restore')}
                  </MotionButton>
                  <MotionButton
                    onClick={() => handleDelete(slot.slot_name)}
                    disabled={busySlot !== null}
                    className="p-1 text-gray-400 hover:text-red-400 transition-colors"
                    title={t('saves.delete_tooltip', 'Delete Checkpoint')}
                  >
                    <Trash2 size={13} />
                  </MotionButton>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <ConfirmDialog
        isOpen={Boolean(confirmState)}
        onClose={() => setConfirmState(null)}
        onConfirm={handleConfirmAction}
        busy={busySlot !== null}
        tone={confirmState?.mode === 'overwrite' ? 'accent' : 'danger'}
        title={
          confirmState?.mode === 'overwrite'
            ? t('saves.confirm_overwrite_title', 'Overwrite Checkpoint?')
            : t('saves.confirm_delete_title', 'Delete Checkpoint?')
        }
        message={
          confirmState?.mode === 'overwrite'
            ? t('saves.confirm_overwrite_msg', {
                slot: confirmState?.slotName || '',
                defaultValue: `Overwrite saved checkpoint "${confirmState?.slotName || ''}" with your current progress?`,
              })
            : t('saves.confirm_delete_msg', {
                slot: confirmState?.slotName || '',
                defaultValue: `Permanently delete saved checkpoint "${confirmState?.slotName || ''}"?`,
              })
        }
        confirmLabel={
          confirmState?.mode === 'overwrite'
            ? t('saves.overwrite', 'Overwrite')
            : t('saves.delete', 'Delete')
        }
      />
    </AcrylicModal>
  );
};

export default SavesModal;
