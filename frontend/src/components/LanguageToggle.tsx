import { useTranslation } from 'react-i18next';

/**
 * Language toggle for the top bar: one button that flips ko <-> en, styled like the
 * mode-switch button next to it. The choice is persisted per browser by the i18n
 * detector, so it survives a reload and is independent of the signed-in account.
 *
 * The face is the SHORT form of the language it switches TO — "한" or "EN" — so the button
 * stays the width of the icon button beside it. The full name is in the accessible label and
 * the tooltip, which is where a screen reader and a hesitating cursor both look.
 */
export function LanguageToggle() {
  const { i18n, t } = useTranslation();
  const current = i18n.resolvedLanguage ?? 'en';
  const next = current.startsWith('ko') ? 'en' : 'ko';
  const full = next === 'en' ? 'English' : '한국어';
  return (
    <button
      type="button"
      className="h-[34px] min-w-[34px] max-md:h-11 max-md:min-w-11 rounded-ctl border border-border bg-surface-2
                 px-2 text-sm font-semibold hover:bg-surface"
      onClick={() => void i18n.changeLanguage(next)}
      title={`${t('common.language')} · ${full}`}
      aria-label={`${t('common.language')}: ${full}`}
    >
      {next === 'en' ? 'EN' : '한'}
    </button>
  );
}
