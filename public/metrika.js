/* Yandex Metrika: explicit page and outbound-link events only. */
(() => {
  'use strict';

  const script = document.currentScript;
  const eventName = 'semya-metrika';
  const numberPattern = /^[1-9]\d{0,11}$/;
  const toPublicUrl = (raw) => {
    try {
      const url = new URL(raw);
      if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return null;
      url.search = '';
      url.hash = '';
      return url;
    } catch {
      return null;
    }
  };

  if (script.hasAttribute('data-frame')) {
    if (window.parent === window) return;
    let counter;
    let lastView;
    addEventListener(eventName, ({detail}) => {
      if (!detail) return;
      if (detail.type === 'view') {
        const url = new URL(detail.url);
        if (url.origin !== location.origin || url.search) return;
        // The tag can use its document URL for technical events. This document
        // has only the clean page URL and receives no form values or DOM events.
        history.replaceState(null, '', url.href);
        if (!counter) {
          if (!numberPattern.test(detail.counter)) return;
          counter = Number(detail.counter);
          window.ym = function () { (window.ym.a ||= []).push(arguments); };
          window.ym.l = Date.now();
          window.ym(counter, 'init', {
            defer: true,
            trackHash: false,
            trackLinks: false,
            clickmap: false,
            webvisor: false,
            childIframe: false,
            ecommerce: false,
            accurateTrackBounce: true,
            disableYtm: true,
            sendTitle: false
          });
          const tag = document.createElement('script');
          tag.async = true;
          tag.referrerPolicy = 'no-referrer';
          tag.src = 'https://mc.yandex.ru/metrika/tag.js';
          document.head.append(tag);
        }
        if (lastView === url.href) return;
        window.ym(counter, 'hit', url.href, { referer: lastView || detail.referrer });
        lastView = url.href;
      } else if (counter && detail.type === 'outbound') {
        const url = toPublicUrl(detail.url);
        if (url && url.origin !== location.origin) window.ym(counter, 'extLink', url.href);
      }
    });
    return;
  }

  if (window.parent !== window) return;
  const counter = script.dataset.counter;
  const siteHosts = new Set([
    'xn-----klcacdbaguohtkvppgx2q.xn--p1ai',
    'xn-----6kcba0adcljuh3ahqihlhjqil4g2hb3f.xn--p1ai'
  ]);
  if (!numberPattern.test(counter) || location.protocol !== 'https:' || !siteHosts.has(location.hostname)) return;

  const app = script.dataset.spa === 'true' ? document.getElementById('main') : null;
  const routeId = /^[a-z0-9]+(?:[-_][a-z0-9]+)*$/;
  function pageUrl() {
    const page = new URL(location.pathname.replace(/\/index\.html$/, '/'), location.origin);
    if (app) {
      const { ready, page: section, project } = app.dataset;
      if (ready !== 'true' || !routeId.test(section || '') || !routeId.test(project || '')) return null;
      if (project !== 'family') page.hash = `/projects/${project}/${section}`;
      else if (section !== 'overview') page.hash = `/${section}`;
    }
    return page.href;
  }

  const source = toPublicUrl(document.referrer);
  const referrer = source ? `${source.origin}/` : '';
  const frame = document.createElement('iframe');
  frame.hidden = true;
  frame.tabIndex = -1;
  frame.setAttribute('aria-hidden', 'true');
  frame.title = 'Веб-аналитика';
  frame.referrerPolicy = 'no-referrer';
  frame.src = new URL('./metrika-frame.html', script.src).href;
  let ready = false;
  let lastView;
  function emit(detail) {
    if (!ready) return;
    try {
      const target = frame.contentWindow;
      if (target) target.dispatchEvent(new target.CustomEvent(eventName, { detail }));
    } catch {
      // Tracking should never interrupt navigation if the frame is blocked.
    }
  }
  function view() {
    const url = pageUrl();
    if (!ready || !url || url === lastView) return;
    emit({ type: 'view', counter, url, referrer });
    lastView = url;
  }
  function outbound(event) {
    if (!event.isTrusted || event.defaultPrevented || (event.type === 'auxclick' && event.button !== 1)) return;
    const link = event.target.closest?.('a[href]');
    if (!link) return;
    const url = toPublicUrl(link.href);
    if (url && url.origin !== location.origin) emit({ type: 'outbound', url: url.href });
  }
  frame.addEventListener('load', () => {
    ready = true;
    view();
  }, { once: true });
  document.body.append(frame);
  if (app) {
    new MutationObserver(view).observe(app, {
      attributes: true, attributeFilter: ['data-page', 'data-project', 'data-ready']
    });
  }
  document.addEventListener('click', outbound);
  document.addEventListener('auxclick', outbound);
})();
