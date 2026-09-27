import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import mdx from '@astrojs/mdx';
import starlightLinksValidator from 'starlight-links-validator';
import starlightLlmsTxt from 'starlight-llms-txt';
import starlightDotMd from 'starlight-dot-md';

export default defineConfig({
  site: 'https://wontaeJeong.github.io',
  base: '/agent-optimizer',
  integrations: [
    starlight({
      title: 'Agent Optimizer 가이드',
      description: 'Agent 최적화 실험을 시작하고 팀 컴포넌트를 연결하는 가이드',
      locales: { root: { label: '한국어', lang: 'ko' } },
      customCss: ['./src/styles/site.css'],
      sidebar: [
        { slug: 'index' },
        { label: '시작하기', items: [
          { slug: 'getting-started/first-run' },
          { slug: 'getting-started/results' },
        ] },
        { label: '실험하기', items: [
          { slug: 'guides/experiment' },
          { slug: 'concepts/overview' },
        ] },
        { label: '팀 컴포넌트 개발', items: [
          { slug: 'developer/components' },
          { slug: 'developer/overview' },
          { slug: 'developer/validation' },
        ] },
      ],
      social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/wontaeJeong/agent-optimizer' }],
      editLink: { baseUrl: 'https://github.com/wontaeJeong/agent-optimizer/edit/main/website/' },
      plugins: [starlightLinksValidator(), starlightLlmsTxt(), starlightDotMd()],
    }),
    mdx(),
  ],
});
