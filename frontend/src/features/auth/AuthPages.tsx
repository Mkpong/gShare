import { useState } from 'react';
import { useNavigate, useLocation, Link, Navigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/auth/authStore';
import { useUiStore } from '@/store/uiStore';
import { LanguageToggle } from '@/components/LanguageToggle';
import { ThemeToggle } from '@/components/ThemeToggle';
import { AppFooter } from '@/components/Layout';
import { Brand, BrandMark } from '@/components/BrandMark';
import { Field, DisabledReason } from '@/components/Field';
import { asApiError, humanizeError } from '@/lib/errors';
import { useBranding, useSignup, useSignupPolicy } from '@/api/hooks/useSystem';
import { ArrowLeft, ArrowRight, Coins, GraphicsCard, Hourglass } from '@/components/icons';

/** Shared shell for the signed-out screens: a landmark, a heading, and the language control. */
function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <main className="min-h-full flex flex-col bg-bg p-4">
      <div className="w-full max-w-[392px] m-auto">{children}</div>
      <AppFooter />
    </main>
  );
}

// Sign-in, with an email and a password.
export function Login() {
  const navigate = useNavigate();
  const loc = useLocation();
  const { t } = useTranslation();
  const pushToast = useUiStore((s) => s.pushToast);
  const loginPassword = useAuthStore((s) => s.loginPassword);
  const [email, setEmail] = useState('');
  const [pw, setPw] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [emailTouched, setEmailTouched] = useState(false);
  const signup = useSignup();
  const [tab, setTab] = useState<'signin' | 'signup'>('signin');
  const [name, setName] = useState('');
  const [done, setDone] = useState<'pending' | 'active' | null>(null);
  const emailMalformed = emailTouched && email.trim().length > 0 && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim());
  const returnUrl = (loc.state as { returnUrl?: string } | null)?.returnUrl ?? '/';
  const signupPolicy = useSignupPolicy().data;
  const signupOpen = (signupPolicy?.mode ?? 'closed') !== 'closed';
  const allowedDomains = signupPolicy?.allowed_domains ?? [];
  const submitDisabled = busy || !email || !pw || emailMalformed
    || (tab === 'signup' && (!name.trim() || pw.length < 8));

  async function handlePassword(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await loginPassword(email, pw);
      // A first sign-in - an account an administrator registered, or the bootstrap account -
      // has to change its password before going anywhere else.
      const mustChange = useAuthStore.getState().claims.must_change_password;
      navigate(mustChange ? '/change-password' : returnUrl, { replace: true });
    } catch (e) {
      // Inline as well as a toast: the message has to outlast the toast. A 401 stays the generic
      // wrong-credentials text; anything else (429 rate-limit, login disabled) shows its real
      // message so the user does not keep retyping a correct password.
      const err = asApiError(e);
      const msg = err.status && err.status !== 401 ? humanizeError(err) : t('auth.invalidCredentials');
      setError(msg);
      pushToast('error', msg);
    } finally {
      setBusy(false);
    }
  }

  async function handleSignup(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const r = await signup.mutateAsync({ email: email.trim(), name: name.trim(), password: pw });
      setDone(r.status);
      // An open instance signs the new account straight in; an approval one waits.
      if (r.status === 'active') {
        await loginPassword(email, pw);
        navigate(returnUrl, { replace: true });
      }
    } catch (e2) {
      const msg = humanizeError(asApiError(e2));
      setError(msg);
      pushToast('error', msg);
    } finally {
      setBusy(false);
    }
  }

  // One card, several sessions: the picture the console exists for. Fractions are a worked
  // example of a 24 GB card, not live data.
  const segments = [
    { key: 'jupyter', cls: 'gs-seg-1', frac: 0.25, label: t('auth.segJupyter') },
    { key: 'vscode', cls: 'gs-seg-2', frac: 0.25, label: t('auth.segVscode') },
    { key: 'terminal', cls: 'gs-seg-3', frac: 0.125, label: t('auth.segTerminal') },
    { key: 'free', cls: 'gs-seg-free', frac: 0.375, label: t('auth.segFree') },
  ];
  const facts = [
    { icon: GraphicsCard, title: t('auth.factAccessTitle'), body: t('auth.factAccessBody') },
    { icon: Coins, title: t('auth.factBillingTitle'), body: t('auth.factBillingBody') },
    { icon: Hourglass, title: t('auth.factIdleTitle'), body: t('auth.factIdleBody') },
  ];

  return (
    <main className="h-full overflow-y-auto flex flex-col lg:flex-row bg-bg">
      {/* Brand panel: the one diagram that explains gShare — a card split into sessions. */}
      <section className="gs-auth-hero relative overflow-hidden shrink-0 lg:w-[56%] lg:min-h-full hidden lg:flex flex-col lg:px-14 lg:pt-5 lg:pb-14 lg:border-r border-border" aria-labelledby="gs-auth-hero-title">
        <div className="relative flex items-center gap-2.5 md:-ml-4 lg:-ml-8">
          <Brand size={36} textClass="text-lg font-bold tracking-[-0.02em]" />
        </div>
        <div className="relative my-auto py-10 lg:py-14 max-w-[600px]">
          <p className="gs-num text-2xs uppercase tracking-[0.14em] text-muted">{t('auth.eyebrow')}</p>
          <p id="gs-auth-hero-title" className="mt-3 text-2xl md:text-3xl lg:text-[34px] font-bold leading-[1.25] tracking-[-0.02em] whitespace-pre-line [text-wrap:balance] [word-break:keep-all]">
            {t('auth.heroTitle')}
          </p>
          <p className="text-muted mt-4 leading-relaxed max-w-[52ch] [word-break:keep-all]">{t('auth.heroSubtitle')}</p>

          <figure className="hidden md:block mt-10" aria-label={t('auth.diagramLabel')}>
            <figcaption className="flex items-baseline justify-between gs-num text-xs text-muted">
              <span>{t('auth.diagramCard')}</span>
              <span>{t('auth.diagramSessions')}</span>
            </figcaption>
            <div className="mt-2 flex h-10 gap-1" aria-hidden="true">
              {segments.map((sg, i) => (
                <div key={sg.key} className={`gs-seg ${sg.cls}`} style={{ flexBasis: `${sg.frac * 100}%`, animationDelay: `${60 + i * 80}ms` }} />
              ))}
            </div>
            <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs" aria-hidden="true">
              {segments.map((sg) => (
                <li key={sg.key} className="flex items-center gap-1.5">
                  <span className={`gs-seg gs-seg-swatch ${sg.cls}`} />
                  <span>{sg.label}</span>
                  <span className="gs-num text-muted">{(sg.frac * 24).toFixed(sg.frac * 24 % 1 ? 1 : 0)} GB</span>
                </li>
              ))}
            </ul>
          </figure>

          <dl className="mt-10 grid sm:grid-cols-3 gap-6">
            {facts.map((f) => (
              <div key={f.title} className="flex flex-col gap-1.5">
                <dt className="flex items-center gap-1.5 text-sm font-bold">
                  <f.icon size={15} weight="bold" className="text-primary" aria-hidden="true" />
                  {f.title}
                </dt>
                <dd className="text-xs text-muted leading-relaxed m-0 [word-break:keep-all]">{f.body}</dd>
              </div>
            ))}
          </dl>
        </div>
        <div className="relative text-2xs text-muted leading-relaxed">
          <a href="https://www.apache.org/licenses/LICENSE-2.0" target="_blank" rel="noreferrer noopener" className="hover:text-text">Apache-2.0</a>
        </div>
      </section>

      {/* Sign-in panel: the console's own card on the console's own ground. */}
      <section className="shrink-0 flex-1 flex flex-col px-6 pt-4 pb-6 md:px-10 md:pt-5 md:pb-10 lg:px-14 lg:pb-14">
        <div className="flex justify-end items-center gap-2 md:-mr-4 lg:-mr-8"><LanguageToggle /><ThemeToggle /></div>
        <div className="w-full max-w-[400px] m-auto py-6">
          {/* On narrow screens the brand panel is gone, so the wordmark sits above the form. */}
          <div className="lg:hidden flex items-center justify-center gap-2.5 mb-7">
            <Brand size={36} textClass="text-lg font-bold tracking-[-0.02em]" />
          </div>
        <form className="gs-card shadow-raised w-full p-7 md:p-8 space-y-5" onSubmit={tab === 'signup' ? handleSignup : handlePassword} noValidate>
          <div className={signupOpen ? 'mb-5' : 'mb-7'}>
            <h1 className="text-xl font-bold tracking-[-0.02em]">{tab === 'signup' ? t('auth.signUp') : t('auth.signIn')}</h1>
            <p className="text-muted text-sm mt-1.5">{tab === 'signup' ? t('auth.signUpSubtitle') : t('auth.signInSubtitle')}</p>
          </div>
          {/* The sign-up tab exists only where an administrator has opened registration. */}
          {signupOpen && (
            <div className="grid grid-cols-2 gap-1 p-1 rounded-ctl bg-surface-2" role="tablist" aria-label={t('auth.signIn')}>
              {(['signin', 'signup'] as const).map((k) => (
                <button
                  key={k}
                  type="button"
                  role="tab"
                  aria-selected={tab === k}
                  className={`h-9 rounded-ctl text-sm font-semibold transition-colors duration-150 ${
                    tab === k ? 'bg-surface text-text shadow-sm' : 'text-muted hover:text-text'
                  }`}
                  onClick={() => { setTab(k); setError(null); setDone(null); }}
                >
                  {t(k === 'signin' ? 'auth.signIn' : 'auth.signUp')}
                </button>
              ))}
            </div>
          )}
          {done === 'pending' && (
            <p role="status" className="text-xs leading-relaxed rounded-ctl border border-border bg-surface-2 p-3">
              {t('auth.signUpPending')}
            </p>
          )}
          {error && <p role="alert" className="text-danger text-xs">{error}</p>}
          {tab === 'signup' && (
            <Field label={t('auth.name')} required>
              {(ids) => (
                <input
                  {...ids}
                  className="gs-input w-full h-11"
                  autoComplete="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              )}
            </Field>
          )}
          <Field
            label={t('auth.email')}
            required
            error={emailMalformed ? t('auth.emailMalformed') : null}
            hint={tab === 'signup' && allowedDomains.length > 0 ? t('auth.signUpDomains', { domains: allowedDomains.join(', ') }) : undefined}
          >
            {(ids) => (
              <input
                {...ids}
                className="gs-input w-full h-11"
                type="email"
                inputMode="email"
                autoComplete="username"
                autoFocus
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onBlur={() => setEmailTouched(true)}
              />
            )}
          </Field>
          <Field label={tab === 'signup' ? t('auth.newPassword') : t('auth.password')} required>
            {(ids) => (
              <input
                {...ids}
                className="gs-input w-full h-11"
                type="password"
                autoComplete={tab === 'signup' ? 'new-password' : 'current-password'}
                minLength={tab === 'signup' ? 8 : undefined}
                value={pw}
                onChange={(e) => setPw(e.target.value)}
              />
            )}
          </Field>
          <DisabledReason reasons={[
            tab === 'signup' && !name.trim() && t('auth.name'),
            !email && t('auth.email'),
            !pw && t('auth.password'),
          ].filter(Boolean) as string[]} />
          <button type="submit" className="gs-btn gs-btn-primary w-full justify-center h-11 text-sm disabled:opacity-50" disabled={submitDisabled}>
            {busy
              ? t(tab === 'signup' ? 'auth.signingUp' : 'auth.signingIn')
              : t(tab === 'signup' ? 'auth.signUp' : 'auth.signIn')}
            {!busy && <ArrowRight size={16} weight="bold" aria-hidden="true" />}
          </button>
          <p className="text-muted text-xs text-center pt-1">{t('auth.forgotHint')}</p>
        </form>
        </div>
      </section>
    </main>
  );
}

// Password change: forced at first sign-in (must_change), or requested by the user themselves.
export function ChangePassword() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const branding = useBranding().data;
  const isAuthed = useAuthStore((s) => s.isAuthed);
  const mustChange = useAuthStore((s) => s.claims.must_change_password);
  const changePassword = useAuthStore((s) => s.changePassword);
  const pushToast = useUiStore((s) => s.pushToast);
  const [cur, setCur] = useState('');
  const [pw, setPw] = useState('');
  const [pw2, setPw2] = useState('');
  const [busy, setBusy] = useState(false);
  const [touched, setTouched] = useState(false);

  // Validated as typed.
  const tooShort = pw.length > 0 && pw.length < 8;
  const mismatch = pw2.length > 0 && pw !== pw2;

  if (!isAuthed) return <Navigate to="/login" replace />;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (pw.length < 8 || pw !== pw2) return;
    setBusy(true);
    try {
      await changePassword(pw, mustChange ? undefined : cur);
      pushToast('success', t('auth.changed'));
      navigate('/', { replace: true });
    } catch {
      pushToast('error', mustChange ? t('auth.changeFailed') : t('auth.wrongCurrent'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell>
      <form className="gs-card space-y-4 shadow-raised" onSubmit={submit} noValidate>
        <div className="flex items-center gap-2.5 mb-3">
          <BrandMark size={22} logo={branding?.logo} name={branding?.service_name} />
          <h1 className="text-lg font-bold tracking-[-0.02em]">{t('auth.changePassword')}</h1>
          <span className="ml-auto"><LanguageToggle /></span>
        </div>
        {mustChange && <p className="text-warn text-xs">{t('auth.firstLogin')}</p>}
        {!mustChange && (
          <Field label={t('auth.currentPassword')} required>
            {(ids) => (
              <input {...ids} className="gs-input w-full" type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} />
            )}
          </Field>
        )}
        <Field
          label={t('auth.newPassword')}
          required
          hint={t('auth.passwordRule')}
          error={(touched || pw.length > 0) && tooShort ? t('auth.tooShort') : null}
        >
          {(ids) => (
            <input {...ids} className="gs-input w-full" type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} />
          )}
        </Field>
        <Field label={t('auth.confirmPassword')} required error={mismatch ? t('auth.mismatch') : null}>
          {(ids) => (
            <input {...ids} className="gs-input w-full" type="password" autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} />
          )}
        </Field>
        <DisabledReason reasons={[!pw && t('auth.newPassword'), !pw2 && t('auth.confirmPassword')].filter(Boolean) as string[]} />
        <button type="submit" className="gs-btn gs-btn-primary w-full justify-center disabled:opacity-50" disabled={busy || !pw || !pw2 || tooShort || mismatch}>
          {busy ? t('auth.changing') : t('auth.changePassword')}
        </button>
      </form>
    </AuthShell>
  );
}

function ErrorScreen({ code, title, hint }: { code: string; title: string; hint?: string }) {
  const { t } = useTranslation();
  return (
    <main className="min-h-full grid place-items-center text-center p-4">
      <div>
        <div aria-hidden="true" className="text-5xl font-extrabold text-muted">{code}</div>
        <h1 className="text-xl font-bold mt-2">{title}</h1>
        {hint && <p className="text-muted mt-1">{hint}</p>}
        <div className="mt-4 flex items-center justify-center gap-2 flex-wrap">
          <Link to="/" className="gs-btn gs-btn-primary">{t('auth.backToDashboard')}</Link>
          <button type="button" className="gs-btn" onClick={() => window.history.back()}>
            <ArrowLeft size={14} aria-hidden="true" />
            {t('common.back')}
          </button>
          <LanguageToggle />
        </div>
      </div>
    </main>
  );
}

export function Forbidden() {
  const { t } = useTranslation();
  return <ErrorScreen code="403" title={t('auth.forbiddenTitle')} hint={t('auth.forbiddenHint')} />;
}

export function NotFound() {
  const { t } = useTranslation();
  return <ErrorScreen code="404" title={t('auth.notFoundTitle')} hint={t('auth.notFoundHint')} />;
}

export function SystemError() {
  const { t } = useTranslation();
  return <ErrorScreen code="500" title={t('auth.errorTitle')} hint={t('auth.errorHint')} />;
}
