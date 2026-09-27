import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import mdx from '@astrojs/mdx';
import mermaid from 'astro-mermaid';
import starlightLinksValidator from 'starlight-links-validator';
import starlightLlmsTxt from 'starlight-llms-txt';

export default defineConfig({
  site: 'https://wontaeJeong.github.io',
  base: '/agent-optimizer',
  integrations: [
    mermaid(),
    starlight({
      title: 'Agent Optimizer 가이드',
      description: 'Agent 최적화 실험을 시작하고 팀 컴포넌트를 연결하는 가이드',
      locales: { root: { label: '한국어', lang: 'ko' } },
      sidebar: [{ slug: 'index' }],
      social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/wontaeJeong/agent-optimizer' }],
      editLink: { baseUrl: 'https://github.com/wontaeJeong/agent-optimizer/edit/main/website/' },
      plugins: [starlightLinksValidator(), starlightLlmsTxt()],
    }),
    mdx(),
  ],
});
