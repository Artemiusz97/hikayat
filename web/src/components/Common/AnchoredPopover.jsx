import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

const MARGIN = 8;

/**
 * Viewport-aware popover. Renders into <body> with fixed positioning so it can
 * never be clipped by sidebars, scroll containers or the screen edge. It flips
 * above the anchor when there is not enough room below and caps its height to
 * the visible viewport (respecting mobile browser chrome via visualViewport).
 */
const AnchoredPopover = ({
  anchorRef,
  open,
  onClose,
  width = 320,
  align = 'end', // 'start' | 'end'
  label,
  className = '',
  children,
}) => {
  const popRef = useRef(null);
  const [style, setStyle] = useState({ visibility: 'hidden' });

  const place = useCallback(() => {
    const anchor = anchorRef?.current;
    if (!anchor) return;
    const vv = window.visualViewport;
    const vw = vv ? vv.width : window.innerWidth;
    const vh = vv ? vv.height : window.innerHeight;
    const r = anchor.getBoundingClientRect();
    const w = Math.min(width, vw - MARGIN * 2);
    let left = align === 'start' ? r.left : r.right - w;
    left = Math.max(MARGIN, Math.min(left, vw - w - MARGIN));

    const spaceBelow = vh - r.bottom - MARGIN * 2;
    const spaceAbove = r.top - MARGIN * 2;
    const popH = popRef.current?.scrollHeight || 0;
    const flip = popH > spaceBelow && spaceAbove > spaceBelow;
    const next = {
      position: 'fixed',
      left,
      width: w,
      maxHeight: Math.max(160, flip ? spaceAbove : spaceBelow),
      zIndex: 1000,
      visibility: 'visible',
      transformOrigin: `${align === 'start' ? 'left' : 'right'} ${flip ? 'bottom' : 'top'}`,
    };
    if (flip) next.bottom = vh - r.top + MARGIN;
    else next.top = r.bottom + MARGIN;
    setStyle(next);
  }, [anchorRef, width, align]);

  useLayoutEffect(() => {
    if (!open) return undefined;
    place();
    // Second pass once content has measured.
    const id = requestAnimationFrame(place);
    return () => cancelAnimationFrame(id);
  }, [open, place]);

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => {
      if (popRef.current?.contains(e.target) || anchorRef?.current?.contains(e.target)) return;
      onClose?.();
    };
    const onKey = (e) => {
      if (e.key === 'Escape') onClose?.();
    };
    const onReflow = () => place();
    document.addEventListener('pointerdown', onDown);
    document.addEventListener('keydown', onKey);
    window.addEventListener('resize', onReflow);
    window.addEventListener('scroll', onReflow, true);
    window.visualViewport?.addEventListener('resize', onReflow);
    return () => {
      document.removeEventListener('pointerdown', onDown);
      document.removeEventListener('keydown', onKey);
      window.removeEventListener('resize', onReflow);
      window.removeEventListener('scroll', onReflow, true);
      window.visualViewport?.removeEventListener('resize', onReflow);
    };
  }, [open, onClose, place, anchorRef]);

  if (!open) return null;

  return createPortal(
    <div
      ref={popRef}
      role="dialog"
      aria-label={label}
      style={style}
      className={`hk-popover overflow-y-auto overscroll-contain custom-scrollbar rounded-xl border border-fantasy-border shadow-2xl ${className}`}
    >
      {children}
    </div>,
    document.body
  );
};

export default AnchoredPopover;
