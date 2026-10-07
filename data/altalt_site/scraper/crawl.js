// Crawl altalt.ca with Playwright: rendered text, links, images and a full-page screenshot per page.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const START = 'https://www.altalt.ca/';
const OUT = path.join(__dirname, 'out');
const MAX_PAGES = 120;

const norm = (u) => {
  try {
    const x = new URL(u, START);
    if (!/(^|\.)altalt\.ca$/.test(x.hostname)) return null;
    x.hash = '';
    x.search = '';
    x.hostname = 'www.altalt.ca';
    let s = x.toString();
    if (s.length > START.length && s.endsWith('/')) s = s.slice(0, -1);
    if (/\.(png|jpe?g|gif|webp|svg|pdf|zip|mp4|css|js)$/i.test(x.pathname)) return null;
    return s;
  } catch { return null; }
};
const slug = (u) => (new URL(u).pathname.replace(/^\/|\/$/g, '').replace(/[^a-z0-9]+/gi, '_') || 'home');

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 1000 } });
  const page = await ctx.newPage();
  const queue = [START];
  const seen = new Set(queue);
  const index = [];

  while (queue.length && index.length < MAX_PAGES) {
    const url = queue.shift();
    try {
      const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
      // scroll to trigger lazy-loaded content
      await page.evaluate(async () => {
        for (let y = 0; y < document.body.scrollHeight; y += 800) {
          window.scrollTo(0, y);
          await new Promise((r) => setTimeout(r, 120));
        }
        window.scrollTo(0, 0);
      });
      await page.waitForTimeout(500);
      const data = await page.evaluate(() => ({
        title: document.title,
        text: document.body.innerText,
        links: [...document.querySelectorAll('a[href]')].map((a) => ({ href: a.href, text: a.innerText.trim() })),
        images: [...document.querySelectorAll('img')].map((i) => ({
          src: i.currentSrc || i.src || i.dataset.src || '', alt: i.alt || '', w: i.naturalWidth, h: i.naturalHeight,
        })).filter((i) => i.src),
        ld: [...document.querySelectorAll('script[type="application/ld+json"]')].map((s) => s.textContent),
      }));
      const name = slug(url);
      fs.writeFileSync(path.join(OUT, name + '.json'), JSON.stringify({ url, status: resp && resp.status(), ...data }, null, 1));
      fs.writeFileSync(path.join(OUT, name + '.txt'), `URL: ${url}\nTITLE: ${data.title}\n\n${data.text}`);
      await page.screenshot({ path: path.join(OUT, name + '.png'), fullPage: true }).catch(() => {});
      index.push({ url, name, status: resp && resp.status(), title: data.title, chars: data.text.length, images: data.images.length });
      console.log(index.length, resp && resp.status(), url, data.text.length);
      for (const l of data.links) {
        const n = norm(l.href);
        if (n && !seen.has(n)) { seen.add(n); queue.push(n); }
      }
    } catch (e) {
      console.log('ERR', url, e.message.split('\n')[0]);
      index.push({ url, error: e.message.split('\n')[0] });
    }
    await page.waitForTimeout(700);
  }
  fs.writeFileSync(path.join(OUT, '_index.json'), JSON.stringify({ index, unvisited: queue }, null, 1));
  await browser.close();
})();
