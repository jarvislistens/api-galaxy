/**
 * Capture the README screenshots.
 *
 * Run with both servers up:
 *   cd apps/web && npx tsx ../../scripts/screenshots.ts
 * or, without tsx:
 *   cd apps/web && npx playwright test ../../tests/e2e/screenshots.spec.ts
 *
 * Kept as a script rather than a test because a screenshot that "fails" is a judgement
 * call, not an assertion — the point is to produce images a human then looks at.
 */

import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const BASE = process.env.E2E_BASE_URL ?? "http://127.0.0.1:3000";
const DEMO = "demo-novacart";
const OUT = resolve(import.meta.dirname ?? ".", "../docs/screenshots");

const SHOTS: { name: string; path: string; wait?: number; full?: boolean }[] = [
  { name: "01-landing", path: "/", wait: 1800, full: false },
  { name: "02-overview", path: `/workspace/${DEMO}`, wait: 2200 },
  { name: "03-galaxy", path: `/workspace/${DEMO}/galaxy`, wait: 4000 },
  { name: "04-journeys", path: `/workspace/${DEMO}/journeys`, wait: 3000 },
  { name: "05-ask", path: `/workspace/${DEMO}/ask`, wait: 2000 },
  { name: "06-break-lab", path: `/workspace/${DEMO}/break-lab`, wait: 2500 },
  { name: "07-arena", path: `/workspace/${DEMO}/arena`, wait: 2000 },
  { name: "08-reports", path: `/workspace/${DEMO}/reports`, wait: 2000 },
  { name: "09-settings", path: `/workspace/${DEMO}/settings`, wait: 2000 },
  { name: "10-missions", path: `/workspace/${DEMO}/missions`, wait: 2000 },
  { name: "11-import", path: "/import", wait: 1800 },
];

async function main() {
  await mkdir(OUT, { recursive: true });
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
    colorScheme: "dark",
  });
  const page = await context.newPage();

  await page.request.post("http://127.0.0.1:8099/api/v1/projects/demo").catch(() => {});

  for (const shot of SHOTS) {
    process.stdout.write(`  ${shot.name} … `);
    try {
      await page.goto(`${BASE}${shot.path}`, { waitUntil: "networkidle", timeout: 45_000 });
      await page.waitForTimeout(shot.wait ?? 1500);
      await page.screenshot({
        path: `${OUT}/${shot.name}.png`,
        fullPage: shot.full ?? false,
      });
      console.log("ok");
    } catch (error) {
      console.log(`failed — ${String(error).split("\n")[0]}`);
    }
  }

  await browser.close();
  console.log(`\nWrote to ${OUT}`);
}

main();
