// Real Chromium layout checks with Anki's shipped CSS. No collection or API.
// node tests/render_reviewer_bar.cjs [--css-dir path] [--expect-mismatch] [--image path]
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const work = path.resolve(__dirname, '..');
const args = process.argv.slice(2);
const argument = flag => args.includes(flag) ? args[args.indexOf(flag) + 1] : null;
const source = argument('--source') || path.join(work, 'fragevariator/core/reviewer_bar.py');
let template = fs.readFileSync(source, 'utf8').match(/_BOTTOM_BAR_TEMPLATE = r"""([\s\S]*?)"""/)[1];
for (const [marker, value] of Object.entries({
  __SHOW_ORIGINAL_LABEL__: 'Show original',
  __HIDE_ORIGINAL_LABEL__: 'Hide original',
  __TOGGLE_ORIGINAL_MESSAGE__: 'fragevariator:toggle-original',
})) template = template.replaceAll(marker, JSON.stringify(value));
const cssDir = argument('--css-dir') || path.join(work, '.anki-runtime/_aqt/data/web/css');
const css = ['webview.css', 'reviewer-bottom.css'].map(name => fs.readFileSync(path.join(cssDir, name), 'utf8')).join('\n');
const cases = {
  'anki-native': '',
  'content-box': '#ansbut,#skip {height:20px;box-sizing:content-box}',
  'border-box': '#ansbut,#skip {height:40px;box-sizing:border-box}',
  'custom-padding': '#ansbut,#skip {height:24px;padding-top:5px;padding-bottom:11px;border-top-width:2px;border-bottom-width:3px;line-height:24px}',
  'css-zoom': '#middle {zoom:1.25}',
  'transform': '#middle {transform:scale(1.25)}',
};
const fixture = rules => `<!doctype html><html class="night-mode"><head><meta charset="utf-8">
  <style>${css}\n${rules}</style>${template}</head><body class="isWin nightMode">
  <center id="outer"><table width="100%" cellspacing="0" cellpadding="0"><tr>
  <td class="stat"><button>Edit</button><button>Info</button></td>
  <td id="middle" align="center"><table cellspacing="0" cellpadding="0"><tr>
  <td class="stat2" align="center" style="padding-top:0">
  <span class="stattxt">3 + 5 + 17</span>
  <button id="skip" onclick="pycmd('skip')">Skip</button>
  <button id="ansbut" onclick="pycmd('ans')">Show Answer</button>
  </td></tr></table></td><td class="stat" align="right"><button>More</button></td>
  </tr></table></center><script>window.messages=[];window.pycmd=x=>messages.push(x);</script>
  </body></html>`;

(async () => {
  const browser = await chromium.launch({ headless: true });
  const failures = [];
  try {
    for (const [name, rules] of Object.entries(cases)) {
      const page = await browser.newPage({ viewport: { width: 1100, height: 140 }, deviceScaleFactor: 1.25 });
      await page.setContent(fixture(rules));
      await page.evaluate(() => window.frageVariatorSetOriginal(true, '123'));
      for (const phase of ['initial', 'toggle', 'rerender']) {
        if (phase === 'toggle') {
          await page.locator('#fv-original-button').click();
          assert.equal(await page.evaluate(() => messages[0]), 'fragevariator:toggle-original:show:123');
        } else if (phase === 'rerender') {
          await page.evaluate(() => {
            const middle = document.getElementById('middle');
            middle.innerHTML = middle.innerHTML;
            document.getElementById('fv-original-button').remove();
          });
        }
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
        const sizes = await page.evaluate(() => {
          const read = id => {
            const box = document.getElementById(id).getBoundingClientRect();
            return { height: box.height, top: box.top, bottom: box.bottom };
          };
          return { original: read('fv-original-button'), answer: read('ansbut'), count: document.querySelectorAll('#fv-original-button').length };
        });
        assert.equal(sizes.count, 1);
        const differences = ['height', 'top', 'bottom'].map(key => Math.abs(sizes.original[key] - sizes.answer[key]));
        if (Math.max(...differences) > 0.1) failures.push(`${name}/${phase}: ${JSON.stringify(sizes)}`);
        if (phase === 'initial') {
          console.log(`${name}: original=${sizes.original.height}px answer=${sizes.answer.height}px top_delta=${differences[1]}px`);
          if (argument('--image') && name === 'anki-native') await page.screenshot({path: argument('--image')});
        }
      }
      await page.evaluate(() => window.frageVariatorHideOriginal('123'));
      assert.equal(await page.locator('#fv-original-button').count(), 0);
      await page.close();
    }
    if (args.includes('--expect-mismatch')) {
      assert(failures.length, 'Old code unexpectedly passes: fixture does not reproduce the bug');
      console.log(`Reproduced height/alignment failures in ${failures.length} rendered checks`);
    } else {
      assert.equal(failures.length, 0, failures.join('\n'));
      console.log('PASS: 18 rendered checks, toggle messages, rerenders, and cleanup');
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
