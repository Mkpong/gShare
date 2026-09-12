import type { ReactNode } from 'react';
import useBaseUrl from '@docusaurus/useBaseUrl';
import Heading from '@theme/Heading';
import Translate, { translate } from '@docusaurus/Translate';
import { Coins, StackSimple } from '@phosphor-icons/react';

import Reveal from '@site/src/components/Reveal';
import styles from './styles.module.css';

/**
 * What the platform does, in the order a newcomer meets it: a session, the money behind it, the
 * fleet underneath, and the slice of a card it actually runs on.
 *
 * Two of the four tiles carry a real console screenshot and two carry an icon, and the wide and
 * narrow tiles alternate, so the grid reads as a composition rather than as four equal boxes.
 */

type Tile = {
  wide: boolean;
  title: ReactNode;
  description: ReactNode;
  shot?: { src: string; alt: string };
  icon?: ReactNode;
};

function useTiles(): Tile[] {
  // Hooks first, in a fixed order, so the tile table below is plain data.
  const sessionShot = useBaseUrl('/img/screens/sessions.png');
  const wizardShot = useBaseUrl('/img/screens/wiz-step2.png');
  return [
    {
      wide: true,
      title: <Translate id="home.f1.title">Interactive GPU sessions</Translate>,
      description: (
        <Translate id="home.f1.desc">
          Jupyter, VS Code or a terminal on a slice of a card, opened from the console. No API key
          and no batch queue to learn.
        </Translate>
      ),
      shot: {
        src: sessionShot,
        alt: translate({
          id: 'home.f1.shotAlt',
          message: 'The session list: mode, GPU spec, uptime, estimated cost and state',
        }),
      },
    },
    {
      wide: false,
      title: <Translate id="home.f3.title">Credits, limits, tenants</Translate>,
      description: (
        <Translate id="home.f3.desc">
          A session holds credits before it runs, consumes them as it runs, and settles when it
          ends. Every move is audited.
        </Translate>
      ),
      icon: <Coins size={30} weight="duotone" aria-hidden="true" />,
    },
    {
      wide: false,
      title: <Translate id="home.f4.title">One control plane, many clusters</Translate>,
      description: (
        <Translate id="home.f4.desc">
          Attach a second GPU cluster with one script. Sessions land where their data lives, on
          storage pools with a measured capacity.
        </Translate>
      ),
      icon: <StackSimple size={30} weight="duotone" aria-hidden="true" />,
    },
    {
      wide: true,
      title: <Translate id="home.f2.title">Fractional cards, honest accounting</Translate>,
      description: (
        <Translate id="home.f2.desc">
          A tier is a fraction of one card, and the bill follows the occupancy it actually takes.
          Idle GPUs are paused and handed back.
        </Translate>
      ),
      shot: {
        src: wizardShot,
        alt: translate({
          id: 'home.f2.shotAlt',
          message: 'The session wizard picking a GPU tier, each one showing the share it bills',
        }),
      },
    },
  ];
}

export default function HomepageFeatures(): ReactNode {
  const tiles = useTiles();
  return (
    <section className={styles.features}>
      <div className="container">
        <div className={styles.grid}>
          {tiles.map((t, i) => (
            <Reveal
              key={i}
              delay={(i % 2) * 80}
              className={`${styles.cell} ${t.wide ? styles.cellWide : styles.cellNarrow}`}
            >
              <article className={styles.tile}>
                {t.icon && <span className={styles.tileIcon}>{t.icon}</span>}
                <Heading as="h3" className={styles.tileTitle}>
                  {t.title}
                </Heading>
                <p className={styles.tileDesc}>{t.description}</p>
                {t.shot && (
                  <div className={styles.tileShotFrame}>
                    <img
                      className={styles.tileShot}
                      src={t.shot.src}
                      width={2160}
                      height={1350}
                      loading="lazy"
                      alt={t.shot.alt}
                    />
                  </div>
                )}
              </article>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
