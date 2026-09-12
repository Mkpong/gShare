import type { ReactNode } from 'react';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import useBaseUrl from '@docusaurus/useBaseUrl';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';
import Translate, { translate } from '@docusaurus/Translate';
import { ArrowRight, BookOpen, ShieldCheck, Wrench, FileCode } from '@phosphor-icons/react';

import HomepageFeatures from '@site/src/components/HomepageFeatures';
import Reveal from '@site/src/components/Reveal';
import styles from './index.module.css';

/**
 * The landing page. Three rules shape it:
 *
 * 1. Show the product. The console is the whole interface, so real screenshots carry the page and
 *    the prose stays short. Nothing here is a drawn mock-up.
 * 2. One ground per theme. The hero follows the site theme instead of forcing a dark band into a
 *    light page, so a reader never walks into a different site halfway down.
 * 3. Every visible string goes through Translate; the Korean lives in i18n/ko/code.json.
 */

function Hero() {
  const shot = useBaseUrl('/img/screens/admin-dashboard-platform.png');
  return (
    <header className={styles.hero}>
      <div className={styles.heroGlow} aria-hidden="true" />
      <div className={`container ${styles.heroInner}`}>
        <div className={styles.heroCopy}>
          <Heading as="h1" className={styles.heroTitle}>
            <Translate id="home.hero.title">Several people, one GPU card</Translate>
          </Heading>
          <p className={styles.heroSub}>
            <Translate id="home.hero.sub">
              HAMi splits the card. gShare places the session, bills it, and takes the card back.
              All of it from one console.
            </Translate>
          </p>
          <div className={styles.heroActions}>
            <Link className={styles.ctaPrimary} to="/docs/getting-started">
              <Translate id="home.getStarted">Get started</Translate>
              <ArrowRight size={18} weight="duotone" aria-hidden="true" />
            </Link>
            <Link className={styles.ctaGhost} to="/docs/user-manual">
              <Translate id="home.userManual">User manual</Translate>
            </Link>
          </div>
        </div>

        <div className={styles.heroShotFrame}>
          <img
            className={styles.heroShot}
            src={shot}
            width={2160}
            height={1350}
            loading="eager"
            alt={translate({
              id: 'home.hero.shotAlt',
              message:
                'The administrator dashboard: utilisation, GPU devices, node health and storage servers',
            })}
          />
        </div>
      </div>
    </header>
  );
}

function Quickstart() {
  return (
    <section className={styles.quickstart}>
      <div className={`container ${styles.quickstartInner}`}>
        <Reveal className={styles.revealItem}>
          <Heading as="h2" className={styles.sectionTitle}>
            <Translate id="home.quickstart.title">Look around without a GPU</Translate>
          </Heading>
          <p className={styles.sectionLede}>
            <Translate id="home.quickstart.lede">
              Postgres, Redis, the API and the console come up together. Running a real session
              needs a GPU cluster.
            </Translate>
          </p>
        </Reveal>
        <Reveal className={styles.revealItem} delay={90}>
          <pre className={styles.command}>
            <code>
              <span className={styles.commandPrompt}>$</span> git clone https://github.com/boanlab/gshare{'\n'}
              <span className={styles.commandPrompt}>$</span> cd gshare{'\n'}
              <span className={styles.commandPrompt}>$</span> make compose-up{'\n'}
              <span className={styles.commandPrompt}>$</span> make smoke
            </code>
          </pre>
          <p className={styles.commandNote}>
            <Translate id="home.quickstart.note">
              Console on localhost:8000, API on localhost:8080. Tear it down with make compose-down.
            </Translate>
          </p>
        </Reveal>
      </div>
    </section>
  );
}

type DocLink = { to: string; icon: ReactNode; title: ReactNode; desc: ReactNode };

const DOC_LINKS: DocLink[] = [
  {
    to: '/docs/user-manual',
    icon: <BookOpen size={22} weight="duotone" aria-hidden="true" />,
    title: <Translate id="home.map.user.title">User manual</Translate>,
    desc: <Translate id="home.map.user.desc">Create a session, connect, volumes, credits</Translate>,
  },
  {
    to: '/docs/admin-manual',
    icon: <ShieldCheck size={22} weight="duotone" aria-hidden="true" />,
    title: <Translate id="home.map.admin.title">Administrator manual</Translate>,
    desc: <Translate id="home.map.admin.desc">Organizations, credit allocation, resource policy</Translate>,
  },
  {
    to: '/docs/operations/backup',
    icon: <Wrench size={22} weight="duotone" aria-hidden="true" />,
    title: <Translate id="home.map.ops.title">Operations</Translate>,
    desc: <Translate id="home.map.ops.desc">Deploy and upgrade, backup, monitoring</Translate>,
  },
  {
    to: '/docs/reference/helm-values',
    icon: <FileCode size={22} weight="duotone" aria-hidden="true" />,
    title: <Translate id="home.map.ref.title">Reference</Translate>,
    desc: <Translate id="home.map.ref.desc">Helm values, API, glossary</Translate>,
  },
];

function DocMap() {
  return (
    <section className={styles.docMap}>
      <div className="container">
        <ul className={styles.docList}>
          {DOC_LINKS.map((d, i) => (
            <li key={d.to}>
              <Reveal className={styles.revealItem} delay={i * 70}>
                <Link className={styles.docItem} to={d.to}>
                  <span className={styles.docIcon}>{d.icon}</span>
                  <span className={styles.docText}>
                    <span className={styles.docTitle}>{d.title}</span>
                    <span className={styles.docDesc}>{d.desc}</span>
                  </span>
                  <ArrowRight
                    className={styles.docArrow}
                    size={16}
                    weight="duotone"
                    aria-hidden="true"
                  />
                </Link>
              </Reveal>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

export default function Home(): ReactNode {
  const { siteConfig } = useDocusaurusContext();
  return (
    <Layout title={siteConfig.title} description={siteConfig.tagline}>
      <Hero />
      <main>
        <HomepageFeatures />
        <Quickstart />
        <DocMap />
      </main>
    </Layout>
  );
}
