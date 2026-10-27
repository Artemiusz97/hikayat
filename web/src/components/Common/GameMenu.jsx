import React, { useRef, useState } from 'react';
import { MoreHorizontal } from 'lucide-react';
import AnchoredPopover from './AnchoredPopover';

/**
 * Overflow ("more") menu. `items` entries:
 *   { id, label, icon: Component, onClick, tone?: 'default'|'warn'|'danger', active?, hidden?, divider? }
 */
const GameMenu = ({ items = [], label = 'Menu', icon: Icon = MoreHorizontal, width = 232 }) => {
  const [open, setOpen] = useState(false);
  const btnRef = useRef(null);

  const toneClass = (tone, active) => {
    if (active) return 'text-emerald-400';
    if (tone === 'danger') return 'text-red-400 hover:bg-red-500/10';
    if (tone === 'warn') return 'text-amber-400 hover:bg-amber-500/10';
    return 'text-gray-200 hover:bg-gray-500/10';
  };

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={label}
        title={label}
        className="hk-icon-btn"
      >
        <Icon size={18} />
      </button>
      <AnchoredPopover anchorRef={btnRef} open={open} onClose={() => setOpen(false)} width={width} label={label} className="p-1.5">
        <div role="menu" className="flex flex-col">
          {items.filter((it) => it && !it.hidden).map((it) =>
            it.divider ? (
              <div key={it.id} className="my-1 h-px bg-fantasy-border/60" role="separator" />
            ) : (
              <button
                key={it.id}
                type="button"
                role="menuitem"
                onClick={() => {
                  if (!it.keepOpen) setOpen(false);
                  it.onClick?.();
                }}
                className={`flex items-center gap-3 rounded-lg px-3 h-10 text-sm font-medium text-left ${toneClass(it.tone, it.active)}`}
              >
                {it.icon && <it.icon size={16} className="shrink-0 opacity-80" />}
                <span className="truncate">{it.label}</span>
              </button>
            )
          )}
        </div>
      </AnchoredPopover>
    </>
  );
};

export default GameMenu;
