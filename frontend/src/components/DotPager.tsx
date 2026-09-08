import { useTranslation } from 'react-i18next';
import { CaretLeft, CaretRight } from '@/components/icons';

/**
 * A pager for a short grid of cards: a dot per page between two arrows, and nothing at all while
 * everything fits on one page. Deliberately not the table pager — these are a handful of cards, so
 * page numbers and row counts would be more furniture than the thing they navigate.
 *
 * Shared by the fleet rack view and the user dashboard's model availability, which page the same
 * kind of content and so must not drift into two different controls.
 */
export function DotPager({ page, pages, onPage }: {
  /** Zero-based current page. */
  page: number;
  pages: number;
  onPage: (n: number) => void;
}) {
  const { t } = useTranslation();
  if (pages <= 1) return null;
  const arrow = 'w-6 h-6 grid place-items-center rounded-ctl text-muted transition-colors duration-150 ' +
    'hover:text-text hover:bg-surface-2 disabled:opacity-35 disabled:hover:bg-transparent disabled:hover:text-muted';
  return (
    // Dots are 6px of ink, so the row around them is kept tight and pulled into the card's own
    // bottom padding — otherwise the control reads as a third row of the grid.
    <div className="mt-2 -mb-2 flex items-center justify-center gap-1.5">
      <button type="button" className={arrow} aria-label={t('common.previous')} disabled={page === 0} onClick={() => onPage(page - 1)}>
        <CaretLeft size={14} weight="bold" aria-hidden="true" />
      </button>
      {Array.from({ length: pages }, (_, i) => (
        <button
          key={i}
          type="button"
          aria-label={t('common.pageN', { page: i + 1 })}
          aria-current={i === page ? 'true' : undefined}
          onClick={() => onPage(i)}
          className={`h-1.5 rounded-full transition-all duration-150 ${
            i === page ? 'w-4 bg-primary' : 'w-1.5 bg-border hover:bg-border-strong'
          }`}
        />
      ))}
      <button type="button" className={arrow} aria-label={t('common.next')} disabled={page >= pages - 1} onClick={() => onPage(page + 1)}>
        <CaretRight size={14} weight="bold" aria-hidden="true" />
      </button>
    </div>
  );
}
