import { useEffect } from 'react';
import { useBranding, DEFAULT_SERVICE_NAME } from '@/api/hooks/useSystem';
import { brandLetter } from './BrandMark';

/**
 * Keeps the browser tab in step with the branding settings: the title is the service name, and
 * the icon is the uploaded logo, or a letter mark drawn to match the one in the sidebar. Renders
 * nothing. The static icon in index.html covers the first paint before this resolves.
 */
function letterIcon(letter: string): string {
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">` +
    `<rect width="64" height="64" rx="14" fill="#0a6a8c"/>` +
    `<text x="32" y="33" fill="#ffffff" font-size="38" font-weight="700" ` +
    `font-family="Pretendard,system-ui,-apple-system,Segoe UI,Roboto,sans-serif" ` +
    `text-anchor="middle" dominant-baseline="central">${letter}</text></svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

export function BrandDocument() {
  const b = useBranding().data;
  const name = b?.service_name || DEFAULT_SERVICE_NAME;
  const logo = b?.logo;

  useEffect(() => { document.title = name; }, [name]);

  useEffect(() => {
    const href = logo || letterIcon(brandLetter(name));
    // Replace every declared icon: leaving the PNG fallbacks behind lets a browser prefer them.
    const links = Array.from(document.querySelectorAll<HTMLLinkElement>('link[rel~="icon"]'));
    if (links.length === 0) {
      const link = document.createElement('link');
      link.rel = 'icon';
      document.head.appendChild(link);
      links.push(link);
    }
    const previous = links.map((l) => [l, l.getAttribute('href'), l.getAttribute('type')] as const);
    for (const l of links) {
      l.setAttribute('href', href);
      l.setAttribute('type', logo ? '' : 'image/svg+xml');
    }
    return () => {
      for (const [l, href0, type0] of previous) {
        if (href0 === null) l.removeAttribute('href'); else l.setAttribute('href', href0);
        if (type0 === null) l.removeAttribute('type'); else l.setAttribute('type', type0);
      }
    };
  }, [logo, name]);

  return null;
}
