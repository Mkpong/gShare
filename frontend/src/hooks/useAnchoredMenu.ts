import { useLayoutEffect, useState, type RefObject } from 'react';

/**
 * Position for a dropdown that must escape a clipping ancestor.
 *
 * The topbar scrolls horizontally, so an absolutely-positioned menu inside it gets cut off; the
 * menu therefore renders `position: fixed`. Fixed coordinates are viewport-relative, so they have
 * to be measured from the trigger, or the menu opens detached from the control that was clicked.
 * The menu hangs from the trigger's right edge and is clamped to stay on screen.
 */
export function useAnchoredMenu(
  open: boolean,
  anchorRef: RefObject<HTMLElement>,
  menuWidth: number,
  /** "up" hangs the menu above the trigger — for a trigger that sits at the bottom of the screen,
   *  where a downward menu would open off-screen. */
  direction: 'down' | 'up' = 'down',
  /** Align the menu's LEFT edge with the trigger's, for a sidebar rather than a right-hand bar. */
  align: 'right' | 'left' = 'right',
): { top?: number; bottom?: number; right?: number; left?: number } | null {
  const [pos, setPos] = useState<
    { top?: number; bottom?: number; right?: number; left?: number } | null
  >(null);

  useLayoutEffect(() => {
    if (!open) { setPos(null); return; }
    const update = () => {
      const el = anchorRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const gutter = 8;
      const vertical = direction === 'up'
        ? { bottom: Math.round(window.innerHeight - r.top + 6) }
        : { top: Math.round(r.bottom + 6) };
      const horizontal = align === 'left'
        ? { left: Math.round(Math.max(gutter, Math.min(r.left, window.innerWidth - menuWidth - gutter))) }
        // Distance from the viewport's right edge to the trigger's right edge; the menu grows left.
        : { right: Math.round(Math.max(gutter, Math.min(
            window.innerWidth - r.right,
            window.innerWidth - menuWidth - gutter,
          ))) };
      setPos({ ...vertical, ...horizontal });
    };
    update();
    window.addEventListener('resize', update);
    // Capture phase: a scroll in any ancestor moves the trigger too.
    window.addEventListener('scroll', update, true);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [open, anchorRef, menuWidth, direction, align]);

  return pos;
}
