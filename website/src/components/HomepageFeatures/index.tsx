import type { ReactNode } from 'react';
import clsx from 'clsx';
import Heading from '@theme/Heading';
import Translate from '@docusaurus/Translate';
import styles from './styles.module.css';

type FeatureItem = { title: ReactNode; description: ReactNode };

// What the platform does, in the order a newcomer meets it: a session, its slice of a card,
// the credits that pay for it, and the fleet underneath.
const FeatureList: FeatureItem[] = [
  {
    title: <Translate id="home.f1.title">Interactive GPU sessions</Translate>,
    description: (
      <Translate id="home.f1.desc">
        Users open Jupyter, VS Code or a terminal on a slice of a GPU from the console. No API
        keys, no batch queue to learn — a session is a pod the platform places, bills and reclaims.
      </Translate>
    ),
  },
  {
    title: <Translate id="home.f2.title">Fractional cards, honest accounting</Translate>,
    description: (
      <Translate id="home.f2.desc">
        HAMi partitions a card by VRAM and cores; gShare admits sessions on measured occupancy,
        queues what does not fit, and pauses idle GPUs so a reserved card is never a wasted one.
      </Translate>
    ),
  },
  {
    title: <Translate id="home.f3.title">Credits, limits, tenants</Translate>,
    description: (
      <Translate id="home.f3.desc">
        Organizations, groups and users each hold wallets and resource policies. A session holds
        credits before it runs, consumes as it runs, and settles when it ends — every move audited.
      </Translate>
    ),
  },
  {
    title: <Translate id="home.f4.title">One control plane, many clusters</Translate>,
    description: (
      <Translate id="home.f4.desc">
        Attach a second GPU cluster with one script. The console narrows to the cluster you pick,
        sessions land where their data lives, and shared storage is a registered pool with a
        measured capacity.
      </Translate>
    ),
  },
];

function Feature({ title, description }: FeatureItem) {
  return (
    <div className={clsx('col col--3')}>
      <div className="padding-horiz--md">
        <Heading as="h3">{title}</Heading>
        <p>{description}</p>
      </div>
    </div>
  );
}

export default function HomepageFeatures(): ReactNode {
  return (
    <section className={styles.features}>
      <div className="container">
        <div className="row">
          {FeatureList.map((props, idx) => <Feature key={idx} {...props} />)}
        </div>
      </div>
    </section>
  );
}
