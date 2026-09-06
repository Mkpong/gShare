import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { useBranding, useSetBranding, DEFAULT_SERVICE_NAME } from '@/api/hooks/useSystem';
import { BrandMark } from '@/components/BrandMark';
import { Field } from '@/components/Field';
import { PageHeader } from '@/components/PageHeader';
import { Tabs } from '@/components/Tabs';
import { useConfirm } from '@/components/ConfirmDialog';
import { useUiStore } from '@/store/uiStore';
import { asApiError, humanizeError } from '@/lib/errors';

// Instance-wide settings. One section today (branding); `SECTIONS` is the seam a later section
// slots into — add a key here and a panel below, and the tab row follows.
const SECTIONS = ['branding'] as const;
type Section = (typeof SECTIONS)[number];

const LOGO_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/svg+xml'];
const LOGO_MAX_BYTES = 180 * 1024;   // ~256 KB once base64-encoded, the API's ceiling

export function AdminSystem() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const raw = params.get('tab') ?? '';
  const active: Section = (SECTIONS as readonly string[]).includes(raw) ? (raw as Section) : 'branding';

  return (
    <div>
      <PageHeader title={t('admin.system.title')} description={t('admin.system.subtitle')} />
      <Tabs
        ariaLabel={t('admin.system.title')}
        active={active}
        onChange={(k) => setParams((prev) => {
          const next = new URLSearchParams(prev);
          next.set('tab', k);
          return next;
        }, { replace: true })}
        items={SECTIONS.map((k) => ({ key: k, label: t(`admin.system.tab.${k}`) }))}
      />
      {active === 'branding' && <BrandingSection />}
    </div>
  );
}

function BrandingSection() {
  const { t } = useTranslation();
  const pushToast = useUiStore((s) => s.pushToast);
  const confirm = useConfirm();
  const branding = useBranding().data;
  const save = useSetBranding();
  const fileRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState('');

  // The field follows the server until the administrator starts typing.
  useEffect(() => { setName(branding?.service_name ?? ''); }, [branding?.service_name]);

  const trimmed = name.trim();
  const nameDirty = trimmed.length > 0 && trimmed !== (branding?.service_name ?? '');
  const previewName = trimmed || branding?.service_name || DEFAULT_SERVICE_NAME;

  const onError = (e: unknown) => pushToast('error', humanizeError(asApiError(e)));

  const saveName = () => {
    if (!nameDirty) return;
    save.mutate({ service_name: trimmed }, {
      onSuccess: () => pushToast('success', t('admin.system.branding.nameSaved')),
      onError,
    });
  };

  const pickLogo = (file: File) => {
    if (!LOGO_TYPES.includes(file.type)) {
      pushToast('error', t('admin.system.branding.logoType'));
      return;
    }
    if (file.size > LOGO_MAX_BYTES) {
      pushToast('error', t('admin.system.branding.logoTooBig'));
      return;
    }
    const reader = new FileReader();
    reader.onerror = () => pushToast('error', t('admin.system.branding.logoUnreadable'));
    reader.onload = () => {
      const logo = String(reader.result ?? '');
      save.mutate({ logo }, {
        onSuccess: () => pushToast('success', t('admin.system.branding.logoSaved')),
        onError,
      });
    };
    reader.readAsDataURL(file);
  };

  const removeLogo = async () => {
    const ok = await confirm({
      title: t('admin.system.branding.logoRemoveTitle'),
      body: t('admin.system.branding.logoRemoveBody'),
      confirmLabel: t('admin.system.branding.logoRemove'),
      destructive: true,
    });
    if (!ok) return;
    save.mutate({ clear_logo: true }, {
      onSuccess: () => pushToast('success', t('admin.system.branding.logoRemoved')),
      onError,
    });
  };

  return (
    <div className="gs-card max-w-[640px] space-y-6">
      <div>
        <h2 className="gs-h2">{t('admin.system.branding.title')}</h2>
        <p className="gs-sub mt-1">{t('admin.system.branding.subtitle')}</p>
      </div>

      {/* What the sidebar and the sign-in screen will show, before saving. */}
      <div className="rounded-ctl border border-border bg-surface-2 p-4">
        <p className="text-2xs uppercase tracking-[0.1em] text-muted">{t('admin.system.branding.preview')}</p>
        <div className="flex items-center gap-2.5 mt-2.5">
          <BrandMark size={36} logo={branding?.logo} name={previewName} />
          <span className="text-lg font-bold tracking-[-0.02em]">{previewName}</span>
        </div>
      </div>

      <Field label={t('admin.system.branding.name')} hint={t('admin.system.branding.nameHint')}>
        {(ids) => (
          <div className="flex gap-2">
            <input
              {...ids}
              className="gs-input flex-1"
              value={name}
              maxLength={40}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); saveName(); } }}
            />
            <button type="button" className="gs-btn" disabled={!nameDirty || save.isPending} onClick={saveName}>
              {t('common.save')}
            </button>
          </div>
        )}
      </Field>

      <div>
        <p className="text-xs font-semibold mb-1.5">{t('admin.system.branding.logo')}</p>
        <div className="flex items-center gap-2 flex-wrap">
          <input
            ref={fileRef}
            type="file"
            className="sr-only"
            accept={LOGO_TYPES.join(',')}
            onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) pickLogo(f); }}
          />
          <button type="button" className="gs-btn" disabled={save.isPending} onClick={() => fileRef.current?.click()}>
            {t('admin.system.branding.logoUpload')}
          </button>
          {branding?.logo && (
            <button type="button" className="gs-btn gs-btn-danger" disabled={save.isPending} onClick={removeLogo}>
              {t('admin.system.branding.logoRemove')}
            </button>
          )}
        </div>
        <p className="gs-sub mt-1.5">{t('admin.system.branding.logoHint')}</p>
      </div>
    </div>
  );
}
