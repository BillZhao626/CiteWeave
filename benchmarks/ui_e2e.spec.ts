import { test, expect } from '@playwright/test';
import { appendFileSync, mkdirSync } from 'node:fs';
import { randomUUID, createHash } from 'node:crypto';

// Explicit isolated server with mock generation; no route fulfills fabricated API answers.
test('independent contexts: Ask, SSE, citation, PDF and trace', async ({ browser }) => {
  test.skip(!process.env.CW_BENCH_UI_URL, 'isolated mock API/UI runtime required');
  expect(process.env.CW_BENCH_PROVIDER).toBe('mock');
  const base = process.env.CW_BENCH_UI_URL!;
  const kb = process.env.CW_BENCH_KB!;
  const output = process.env.CW_BENCH_OUTPUT!;
  const contexts = Number(process.env.CW_BENCH_CONTEXTS ?? '8');
  const rounds = Number(process.env.CW_BENCH_ROUNDS ?? '5');
  expect(contexts).toBeGreaterThan(0); expect(contexts).toBeLessThanOrEqual(8);
  expect(rounds).toBeGreaterThan(0); expect(rounds).toBeLessThanOrEqual(5);
  mkdirSync(output, { recursive: false });
  test.setTimeout(contexts * rounds * 65000);
  const runIds = new Set<string>();
  await Promise.all(Array.from({ length: contexts }, async (_, session) => {
    const context = await browser.newContext({
      extraHTTPHeaders: { Authorization: `Bearer ${process.env.CW_BENCH_TOKEN ?? ''}` },
    });
    const page = await context.newPage();
    await page.route('**/v1/queries', async route => {
      const body = route.request().postDataJSON();
      await route.continue({ postData: JSON.stringify({ ...body, profile: 'telecom-structural-v1' }) });
    });
    try {
      for (let round = 0; round < rounds; round++) {
        const question = 'Does HTTP/3 support HTTP Upgrade?';
        const row: Record<string, unknown> = { request_id: randomUUID(), session_id: session,
          round, arrival: performance.now() / 1000, admission: null, start: null,
          status: 'failure', warmup: false, provider: 'mock', estimated_yuan: null,
          question_sha256: createHash('sha256').update(question).digest('hex') };
        try {
          await page.goto(`${base}/kb/${kb}`);
          await page.locator('#question').fill(question);
          const responsePromise = page.waitForResponse(r => r.url().endsWith('/v1/queries'), { timeout: 62000 });
          await page.getByRole('button', { name: '发送问题' }).click();
          const response = await responsePromise;
          row.http_status = response.status();
          if (!response.ok()) {
            row.status = response.status() === 429 ? '429' : 'admission_rejected';
          } else {
            row.admission = performance.now() / 1000; row.start = row.admission;
            const events = (await response.text()).split('\n').filter(s => s.startsWith('data:')).map(s => JSON.parse(s.slice(5)));
            const final = events.find(e => e.type === 'final');
            expect(final).toBeTruthy();
            expect(runIds.has(final.run_id)).toBe(false); runIds.add(final.run_id);
            row.run_id = final.run_id;
            await page.getByRole('button', { name: '查看引用 E1', exact: true }).first().click();
            await expect(page.locator('.pdf-viewer canvas')).toBeVisible();
            await page.goto(`${base}/runs/${final.run_id}`);
            await expect(page.locator('main')).toBeVisible();
            row.status = 'success';
          }
        } catch (error) { row.error_code = error instanceof Error ? error.name : 'unknown'; }
        finally {
          row.finish = performance.now() / 1000;
          appendFileSync(`${output}/requests.jsonl`, JSON.stringify(row) + '\n');
        }
      }
    } finally { await context.close(); }
  }));
});
