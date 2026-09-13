import { themes as prismThemes } from 'prism-react-renderer';
import type { Config } from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

// The documentation site. A static build, published to GitHub Pages by CI — it has nothing to do
// with the Helm release and never runs inside a cluster. The pages themselves are the markdown
// under ../docs, which stays the single source of truth so a docs PR is still a markdown diff.
// The path the site is served from. The workflow sets it per repository so a fork previews at
// <owner>.github.io/<repo>/ without editing this file.
const siteBaseUrl = process.env.SITE_BASE_URL ?? '/gShare/';

const config: Config = {
  title: 'gShare',
  tagline: 'GPU sharing for interactive workloads on Kubernetes',
  favicon: 'img/favicon.png',
  future: { v4: true },

  // Published as a project site: one per repository, so it does not use up the organization's
  // single boanlab.github.io slot. The workflow overrides both when a fork builds a preview.
  url: process.env.SITE_URL ?? 'https://boanlab.github.io',
  baseUrl: siteBaseUrl,
  organizationName: 'boanlab',
  projectName: 'gshare',
  trailingSlash: false,

  // Relative links into the rest of the repository (CONTRIBUTING.md, component READMEs) are
  // not pages of this site; reported, not fatal.
  onBrokenLinks: 'warn',
  markdown: {
    // .md is CommonMark (the existing docs), .mdx is MDX (site-only pages with components).
    format: 'detect',
    mermaid: true,
    hooks: { onBrokenMarkdownLinks: 'warn' },
  },
  // ```mermaid fences render as diagrams: the session lifecycle is a state machine, and a
  // picture of it saves a paragraph on every page that touches pause, resume or terminate.
  themes: ['@docusaurus/theme-mermaid'],

  i18n: {
    // The markdown under ../docs is written in English, which is what defaultLocale names: it is
    // the source language, not the one served first. The readers are Korean, so the baseUrls below
    // put Korean at the site root and move English to /en. Because the two locales then share no
    // output path, each has to be built on its own and the trees merged; see .github/workflows/
    // docs.yml, and use `--locale` when serving one of them locally.
    defaultLocale: 'en',
    locales: ['en', 'ko'],
    localeConfigs: {
      ko: { label: '한국어', baseUrl: siteBaseUrl },
      en: { label: 'English', baseUrl: `${siteBaseUrl}en/` },
    },
  },

  presets: [
    [
      'classic',
      {
        docs: {
          path: '../docs',
          sidebarPath: './sidebars.ts',
          editUrl: 'https://github.com/boanlab/gshare/edit/main/',
          exclude: ['**/README.md~', 'paper/**', 'screenshots/**'],
        },
        blog: false,
        theme: { customCss: './src/css/custom.css' },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    colorMode: { respectPrefersColorScheme: true },
    navbar: {
      title: 'gShare',
      logo: { alt: 'gShare', src: 'img/logo.svg' },
      items: [
        { type: 'docSidebar', sidebarId: 'user', position: 'left', label: 'User guide' },
        { type: 'docSidebar', sidebarId: 'admin', position: 'left', label: 'Administrator guide' },
        { type: 'docSidebar', sidebarId: 'operations', position: 'left', label: 'Operations' },
        { type: 'docSidebar', sidebarId: 'reference', position: 'left', label: 'Reference' },
        { type: 'localeDropdown', position: 'right' },
        { href: 'https://github.com/boanlab/gshare', label: 'GitHub', position: 'right' },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Docs',
          items: [
            { label: 'User guide', to: '/docs/user-manual' },
            { label: 'Administrator guide', to: '/docs/admin-manual' },
            { label: 'Operations', to: '/docs/getting-started' },
            { label: 'Reference', to: '/docs/architecture' },
          ],
        },
        {
          title: 'Project',
          items: [
            { label: 'GitHub', href: 'https://github.com/boanlab/gshare' },
            { label: 'Helm chart', href: 'https://github.com/boanlab/gshare/tree/main/charts/gshare' },
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} gShare authors. Apache License 2.0.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'yaml', 'python', 'go', 'json'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
