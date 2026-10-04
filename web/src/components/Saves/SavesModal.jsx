import React, { useState, useEffect, useCallback } from 'react';
import { X, Save, RotateCcw, Trash2, MapPin, Clock, Bookmark } from 'lucide-react';
import { apiCall } from '../../api/client';

const formatSaveDate = (ts) => {
  if (!ts) return '';
  return new Date(ts * 1000).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
};

const SavesModal = ({ isOpen, onClose, user, onSessionLoaded }) => {
  const [saves, setSaves] = useState([]);
  const [loading, setLoading] = useState(false);
  const [slotName, setSlotName] = useState('');
  const [busySlot, setBusySlot] = useState(null);
  const [feedback, setFeedback] = useState(null);

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
      fetchSaves();
    }
  }, [isOpen, fetchSaves]);

  if (!isOpen) return null;

  const handleSave = async (e, targetSlot = null) => {
    if (e) e.preventDefault();
    const nameToSave = (targetSlot || slotName || '').trim();
    if (!nameToSave) return;
    
    if (targetSlot) {
      if (!window.confirm(`Are you sure you want to overwrite save "${targetSlot}"?`)) return;
    }
    
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

  const handleDelete = async (name) => {
    if (!window.confirm(`Are you sure you want to delete save "${name}"?`)) return;
    
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="fixed inset-0 bg-black/80 backdrop-blur-sm" onClick={onClose} />

      <div className="relative w-full max-w-md bg-fantasy-panel border border-fantasy-border rounded-xl shadow-2xl overflow-hidden z-10 flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="p-4 border-b border-fantasy-border bg-black/50 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Bookmark size={18} className="text-fantasy-accent" />
            <div>
              <h3 className="font-rpg font-bold text-base text-fantasy-accent">Chronicle Checkpoints</h3>
              <p className="text-[11px] text-gray-400">Save or restore campaign snapshots ({saves.length}/10 slots)</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 text-gray-400 hover:text-white">
            <X size={18} />
          </button>
        </div>

        {/* Create New Save Form */}
        <form onSubmit={handleSave} className="p-3.5 bg-black/40 border-b border-fantasy-border flex gap-2">
          <input
            type="text"
            maxLength={32}
            value={slotName}
            onChange={(e) => setSlotName(e.target.value)}
            placeholder="New checkpoint name (e.g. Before Boss)..."
            className="flex-1 bg-black/60 border border-fantasy-border rounded px-3 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-fantasy-accent"
          />
          <button
            type="submit"
            disabled={!slotName.trim() || busySlot !== null}
            className="px-3 py-1.5 rounded bg-fantasy-accent text-fantasy-dark font-bold text-xs flex items-center gap-1.5 disabled:opacity-40 transition-colors"
          >
            <Save size={13} />
            <span>Save</span>
          </button>
        </form>

        {/* Feedback Banner */}
        {feedback && (
          <div className={`mx-4 mt-3 p-2.5 rounded border text-xs flex items-center justify-between ${
            feedback.type === 'error'
              ? 'bg-red-950/60 border-red-800 text-red-200'
              : 'bg-emerald-950/60 border-emerald-700 text-emerald-200'
          }`}>
            <span>{feedback.text}</span>
            <button onClick={() => setFeedback(null)} className="text-gray-400 hover:text-white">
              <X size={13} />
            </button>
          </div>
        )}

        {/* Save Slots List */}
        <div className="flex-1 overflow-y-auto custom-scrollbar p-4 space-y-2.5">
          {loading ? (
            <p className="text-center py-8 text-xs text-gray-500 italic">Loading checkpoints...</p>
          ) : saves.length === 0 ? (
            <div className="text-center py-10 text-gray-500 border border-dashed border-fantasy-border/50 rounded-lg">
              <Save size={24} className="mx-auto mb-1.5 opacity-40" />
              <p className="text-xs">No saved checkpoints yet.</p>
              <p className="text-[11px] text-gray-600 mt-1">Create a checkpoint above to snapshot your current timeline.</p>
            </div>
          ) : (
            saves.map((slot) => (
              <div
                key={slot.id || slot.slot_name}
                className="bg-black/50 border border-fantasy-border/70 rounded-lg p-3 space-y-2"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <span className="font-bold text-xs text-fantasy-accent block truncate">{slot.slot_name}</span>
                    <span className="text-xs font-semibold text-gray-200 block truncate">{slot.scene_title || 'Adventure'}</span>
                  </div>
                  <span className="text-[10px] font-mono text-gray-500 flex items-center gap-1 shrink-0">
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
                  <p className="text-[11px] text-gray-500 line-clamp-2 italic">"{slot.narrative_snippet}"</p>
                )}

                <div className="flex items-center justify-end gap-1.5 pt-1 border-t border-white/5">
                  <button
                    type="button"
                    onClick={(e) => handleSave(e, slot.slot_name)}
                    disabled={busySlot !== null}
                    className="px-2 py-1 rounded bg-black/60 hover:bg-neutral-800 text-gray-300 border border-fantasy-border text-[10px] font-semibold uppercase flex items-center gap-1"
                    title="Overwrite this slot"
                  >
                    <Save size={11} /> Overwrite
                  </button>
                  <button
                    type="button"
                    onClick={() => handleLoad(slot.slot_name)}
                    disabled={busySlot !== null}
                    className="px-2.5 py-1 rounded bg-fantasy-accent/20 hover:bg-fantasy-accent/30 text-fantasy-accent border border-fantasy-accent/50 text-[10px] font-bold uppercase flex items-center gap-1"
                  >
                    <RotateCcw size={11} /> Restore
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(slot.slot_name)}
                    disabled={busySlot !== null}
                    className="p-1 text-gray-500 hover:text-red-400 transition-colors"
                    title="Delete Checkpoint"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

export default SavesModal;
