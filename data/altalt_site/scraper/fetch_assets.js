// Second pass: product variants (Squarespace JSON view), instructional PDFs, arrangement images.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const OUT = path.join(__dirname, 'out');
const ASSETS = path.join(__dirname, 'assets');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  for (const d of ['pdf', 'arrangements', 'products_raw']) fs.mkdirSync(path.join(ASSETS, d), { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext();
  const req = ctx.request;
  const index = JSON.parse(fs.readFileSync(path.join(OUT, '_index.json'))).index;

  // 1. products
  const products = [];
  for (const p of index.filter((x) => x.url && /\/products\/.+/.test(x.url))) {
    const r = await req.get(p.url + '?format=json-pretty');
    if (!r.ok()) { console.log('ERR product', r.status(), p.url); continue; }
    const j = await r.json();
    fs.writeFileSync(path.join(ASSETS, 'products_raw', p.name + '.json'), JSON.stringify(j, null, 1));
    const it = j.item || {};
    const sc = it.structuredContent || {};
    products.push({
      url: p.url,
      title: it.title,
      categories: it.categories,
      tags: it.tags,
      excerpt: (it.excerpt || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim(),
      variants: (sc.variants || []).map((v) => ({
        sku: v.sku,
        attributes: v.attributes,
        price_cad: v.priceMoney ? Number(v.priceMoney.value) : v.price / 100,
        on_sale: v.onSale,
        sale_price_cad: v.onSale && v.salePriceMoney ? Number(v.salePriceMoney.value) : null,
        unlimited: v.unlimited,
        stock: v.qtyInStock,
        weight: v.shippingWeight && v.shippingWeight.value,
      })),
    });
    console.log('product', it.title, (sc.variants || []).length);
    await sleep(400);
  }
  fs.writeFileSync(path.join(ASSETS, 'catalog.json'), JSON.stringify(products, null, 1));

  // 2. instructional PDFs
  const diag = JSON.parse(fs.readFileSync(path.join(OUT, 'instructional_diagrams.json')));
  const pdfs = [...new Set(diag.links.map((l) => l.href).filter((h) => /\/s\/.+\.pdf$/i.test(h)))];
  for (const u of pdfs) {
    const r = await req.get(u);
    if (!r.ok()) { console.log('ERR pdf', r.status(), u); continue; }
    const b = await r.body();
    fs.writeFileSync(path.join(ASSETS, 'pdf', path.basename(new URL(u).pathname)), b);
    console.log('pdf', path.basename(u), b.length);
    await sleep(400);
  }

  // 3. arrangement images (full size)
  const sys = JSON.parse(fs.readFileSync(path.join(OUT, 'system_explained.json')));
  for (const i of sys.images.filter((x) => /\.jpg$/i.test(x.alt))) {
    const r = await req.get(i.src.replace(/\?format=.*/, '?format=1500w'));
    if (!r.ok()) { console.log('ERR img', r.status(), i.alt); continue; }
    const b = await r.body();
    fs.writeFileSync(path.join(ASSETS, 'arrangements', i.alt.replace(/\s+/g, '_')), b);
    console.log('img', i.alt, b.length);
    await sleep(300);
  }
  await browser.close();
})();
