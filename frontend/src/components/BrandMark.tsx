import { useBranding, DEFAULT_SERVICE_NAME } from '@/api/hooks/useSystem';

/**
 * The console's identity: an administrator-set name, and either the uploaded logo or a letter
 * mark generated from the name's first character. One component so the sidebar, the sign-in
 * screen and the browser tab can never drift apart.
 */
export function brandLetter(name: string): string {
  // The character as the administrator typed it: "gShare" reads g, "SOLID LLM" reads S.
  return Array.from(name.trim())[0] ?? 'g';
}

export function BrandMark({ size = 22, logo, name, className = '' }: {
  size?: number;
  /** Pass a value to render without subscribing (the tab-icon painter does this). */
  logo?: string | null;
  name?: string;
  className?: string;
}) {
  const px = `${size}px`;
  if (logo) {
    return (
      <img
        src={logo}
        alt=""
        aria-hidden="true"
        className={`rounded-ctl object-cover shrink-0 ${className}`}
        style={{ width: px, height: px }}
      />
    );
  }
  return (
    <span
      aria-hidden="true"
      className={`rounded-ctl bg-primary text-on-primary grid place-items-center shrink-0 font-bold leading-none ${className}`}
      style={{ width: px, height: px, fontSize: `${Math.round(size * 0.58)}px` }}
    >
      {brandLetter(name ?? DEFAULT_SERVICE_NAME)}
    </span>
  );
}

/** Mark plus wordmark, both from the branding settings. */
export function Brand({ size = 22, textClass = 'font-bold text-md tracking-[-0.02em]' }: {
  size?: number;
  textClass?: string;
}) {
  const b = useBranding().data;
  const name = b?.service_name || DEFAULT_SERVICE_NAME;
  return (
    <>
      <BrandMark size={size} logo={b?.logo} name={name} />
      <span className={textClass}>{name}</span>
    </>
  );
}
