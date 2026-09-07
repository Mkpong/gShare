import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { usePlacement, useSetPlacement, type GpuPacking } from '@/api/hooks/useSystem';
import { useSearchParams } from 'react-router-dom';
import {
  useBranding, useSetBranding, useSignupPolicy, useSetSignupPolicy,
  DEFAULT_SERVICE_NAME, type SignupMode,
} from '@/api/hooks/useSystem';
import { BrandMark } from '@/components/BrandMark';
import { Field } from '@/components/Field';
import { PageHeader } from '@/components/PageHeader';
import { Tabs } from '@/components/Tabs';
import { useConfirm } from '@/components/ConfirmDialog';
import { useUiStore } from '@/store/uiStore';
import { asApiError, humanizeError } from '@/lib/errors';

// Instance-wide settings. One section today (branding); `SECTIONS` is the seam a later section
// slots into — add a key here and a panel below, and the tab row follows.
const SECTIONS = ['branding', 'signup', 'placement'] as const;
type Section = (typeof SECTIONS)[number];

const LOGO_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/svg+xml'];
const LOGO_MAX_BYTES = 180 * 1024;   // ~256 KB once base64-encoded, the API's ceiling

export function AdminSystem() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const raw = params.get('tab') ?? '';
  const active: Section = (SECTIONS as readonly string[]).includes(raw) ? (raw as Section) : 'branding';

  return (
    // Settings read as a document, not a dashboard: one centred column, so the panel does not
    // strand itself against the left edge of a wide screen.
    <div className="mx-auto w-full max-w-[1040px]">
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
      {active === 'signup' && <SignupSection />}
      {active === 'placement' && <PlacementSection />}
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
    <section className="space-y-6">
      <div>
        <h2 className="gs-h2">{t('admin.system.branding.title')}</h2>
        <p className="gs-sub mt-1">{t('admin.system.branding.subtitle')}</p>
      </div>

      {/* What the sidebar and the sign-in screen will show, before saving. */}
      <div className="rounded-ctl border border-border p-4">
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
    </section>
  );
}


const MODES: SignupMode[] = ['approval', 'open', 'closed'];

function SignupSection() {
  const { t } = useTranslation();
  const pushToast = useUiStore((s) => s.pushToast);
  const policy = useSignupPolicy().data;
  const save = useSetSignupPolicy();

  const [mode, setMode] = useState<SignupMode>('closed');
  const [domains, setDomains] = useState('');

  // The form follows the server until an administrator edits it.
  useEffect(() => {
    if (!policy) return;
    setMode(policy.mode);
    setDomains(policy.allowed_domains.join(', '));
  }, [policy]);

  const parsedDomains = domains.split(',').map((d) => d.trim().replace(/^@/, '')).filter(Boolean);
  const dirty = !!policy && (
    mode !== policy.mode || parsedDomains.join(',') !== policy.allowed_domains.join(',')
  );

  const submit = () => {
    save.mutate(
      { mode, allowed_domains: parsedDomains },
      {
        onSuccess: () => pushToast('success', t('admin.system.signup.saved')),
        onError: (e) => pushToast('error', humanizeError(asApiError(e))),
      },
    );
  };

  return (
    <section className="space-y-6">
      <div>
        <h2 className="gs-h2">{t('admin.system.signup.title')}</h2>
        <p className="gs-sub mt-1">{t('admin.system.signup.subtitle')}</p>
      </div>

      <fieldset className="space-y-2">
        <legend className="text-xs font-semibold mb-2">{t('admin.system.signup.mode')}</legend>
        {MODES.map((m) => (
          <label
            key={m}
            className={`flex items-start gap-3 rounded-ctl border p-3.5 cursor-pointer transition-colors duration-150 ${
              mode === m ? 'border-primary bg-primary-soft/40' : 'border-border hover:bg-surface-2'
            }`}
          >
            <input
              type="radio"
              name="signup-mode"
              className="mt-0.5"
              checked={mode === m}
              onChange={() => setMode(m)}
            />
            <span className="leading-snug">
              <b className="mr-2">{t(`admin.system.signup.mode_${m}`)}</b>
              <span className="text-muted text-xs">{t(`admin.system.signup.mode_${m}_hint`)}</span>
            </span>
          </label>
        ))}
      </fieldset>

      {mode !== 'closed' && (
        <Field label={t('admin.system.signup.domains')} hint={t('admin.system.signup.domainsHint')}>
          {(ids) => (
            <input
              {...ids}
              className="gs-input w-full gs-num"
              placeholder="example.ac.kr"
              value={domains}
              onChange={(e) => setDomains(e.target.value)}
            />
          )}
        </Field>
      )}

      <p className="gs-sub">{t('admin.system.signup.departmentNote')}</p>

      <div className="flex items-center gap-3 pt-1">
        <button type="button" className="gs-btn gs-btn-primary" disabled={!dirty || save.isPending} onClick={submit}>
          {t('common.save')}
        </button>
        <span className="gs-sub">{t('admin.system.signup.applyNote')}</span>
      </div>
    </section>
  );
}

// Where a fractional slice goes when more than one card fits. It used to live in the chart's
// ConfigMap, so changing it meant a redeploy; it is a running-fleet decision, so it belongs here.
function PlacementSection() {
  const { t } = useTranslation();
  const pushToast = useUiStore((s) => s.pushToast);
  const current = usePlacement().data;
  const save = useSetPlacement();
  const [packing, setPacking] = useState<GpuPacking>('binpack');

  useEffect(() => { if (current) setPacking(current.gpu_packing); }, [current]);
  const dirty = !!current && packing !== current.gpu_packing;

  return (
    <section className="space-y-6">
      <div>
        <h2 className="gs-h2">{t('admin.system.placement.title')}</h2>
        <p className="gs-sub mt-1">{t('admin.system.placement.subtitle')}</p>
      </div>

      <fieldset className="space-y-2">
        <legend className="text-xs font-semibold mb-2">{t('admin.system.placement.policy')}</legend>
        {(['binpack', 'spread'] as const).map((k) => (
          <label
            key={k}
            className={`flex items-start gap-3 rounded-card border p-3 cursor-pointer transition-colors duration-150 ${
              packing === k ? 'border-primary bg-primary-soft' : 'border-border hover:border-border-strong'
            }`}
          >
            <input
              type="radio"
              name="gs-packing"
              className="mt-0.5"
              checked={packing === k}
              onChange={() => setPacking(k)}
            />
            <span className="min-w-0">
              <span className="block font-semibold text-sm">{t(`admin.system.placement.${k}`)}</span>
              <span className="block text-muted text-xs mt-0.5">{t(`admin.system.placement.${k}Hint`)}</span>
            </span>
          </label>
        ))}
      </fieldset>

      <p className="text-muted text-2xs">{t('admin.system.placement.appliesNote')}</p>

      <div className="flex items-center gap-2">
        <button
          type="button"
          className="gs-btn gs-btn-primary disabled:opacity-50"
          disabled={!dirty || save.isPending}
          onClick={() => save.mutate({ gpu_packing: packing }, {
            onSuccess: () => pushToast('success', t('admin.system.placement.saved')),
            onError: (e) => pushToast('error', humanizeError(asApiError(e))),
          })}
        >
          {save.isPending ? t('common.saving') : t('common.save')}
        </button>
        
      </div>
    </section>
  );
}
