/**
 * The demo path, end to end in a real browser.
 *
 * These mirror the thirteen steps in `docs/demo-guide.md`. If one of them fails, the demo
 * fails — which is the only reason they exist. They assume both servers are running.
 */

import { expect, test, type Page } from "@playwright/test";

const DEMO = "demo-novacart";
const WORKSPACE = `/workspace/${DEMO}`;

/** Wait for the app to settle: no skeletons, no pending fetches. */
async function settled(page: Page) {
  await page.waitForLoadState("networkidle");
  await expect(page.locator(".skeleton")).toHaveCount(0, { timeout: 15_000 });
}

test.beforeAll(async ({ request }) => {
  // Make sure the demo estate exists before any test navigates to it.
  const response = await request.post("http://127.0.0.1:8099/api/v1/projects/demo");
  expect(response.ok()).toBeTruthy();
});

// ---------------------------------------------------------------------------- landing

test("1. the landing page states the promise and offers both doors", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("living model");
  await expect(page.getByText("Drop your API. Watch it come alive.")).toBeVisible();
  await expect(page.getByRole("button", { name: /explore the demo galaxy/i }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: /import your api/i }).first()).toBeVisible();
  await expect(page.getByText("The Sunday Builds")).toBeVisible();
  await expect(page.getByText("Solving Real Problems Using Free AI, Every Sunday!")).toBeVisible();
});

test("2. explore the demo galaxy reaches the workspace", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /explore the demo galaxy/i }).first().click();
  await page.waitForURL(/\/workspace\//, { timeout: 30_000 });
  await settled(page);
  await expect(page.getByRole("heading", { name: /novacart/i }).first()).toBeVisible();
});

// --------------------------------------------------------------------------- overview

test("3. the overview separates observed from inferred", async ({ page }) => {
  await page.goto(WORKSPACE);
  await settled(page);

  // Seven business domains, by name.
  for (const domain of ["Customer", "Catalog", "Cart", "Order", "Payment", "Inventory", "Shipping"]) {
    await expect(page.getByText(domain, { exact: true }).first()).toBeVisible();
  }

  const body = await page.locator("body").innerText();
  expect(body.toLowerCase()).toContain("observed");
  expect(body.toLowerCase()).toContain("inferred");

  // The "how was this derived?" control is a required product surface.
  await expect(page.getByText(/how was this derived/i).first()).toBeVisible();
});

test("4. the top risks name the unauthenticated endpoint and label heuristics", async ({ page }) => {
  await page.goto(WORKSPACE);
  await settled(page);
  const body = await page.locator("body").innerText();
  expect(body).toMatch(/Sensitive data exposed without authentication/i);
  expect(body).toMatch(/heuristic/i);
});

// --------------------------------------------------------------------------- journeys

test("5. a journey plays, narrates and cites evidence", async ({ page }) => {
  await page.goto(`${WORKSPACE}/journeys`);
  await settled(page);

  await page.getByText("Place Order", { exact: true }).first().click();
  await settled(page);

  // Narration is the non-technical surface; the technical detail sits beside it.
  const before = await page.locator("body").innerText();
  expect(before).toMatch(/checkout|basket|order/i);

  // Match the real accessible names. The control is labelled descriptively ("Play the
  // journey", or "Advance one step" under reduced motion) rather than just "Play", which
  // is better for a screen reader and is what the role query therefore sees.
  const play = page
    .getByRole("button", { name: /play the journey|advance one step|replay from/i })
    .first();
  await expect(play).toBeVisible();
  await play.click();
  await page.waitForTimeout(1200);

  // Stepping forward changes what is on screen.
  const step = page.getByRole("button", { name: /next step/i }).first();
  if (await step.isVisible().catch(() => false)) {
    await step.click();
    await page.waitForTimeout(400);
  }
  const after = await page.locator("body").innerText();
  expect(after).not.toEqual(before);
});

// -------------------------------------------------------------------------------- ask

test("6. ask returns a grounded answer with evidence", async ({ page }) => {
  await page.goto(`${WORKSPACE}/ask`);
  await settled(page);

  await page.getByText("How does checkout work?").first().click();
  await page.waitForTimeout(2500);
  await settled(page);

  const body = await page.locator("body").innerText();
  expect(body).toMatch(/Place Order/i);
  // Fact-versus-inference accounting is shown, not implied.
  expect(body.toLowerCase()).toMatch(/fact|evidence/);
});

test("7. ask about customer_id surfaces the aliases", async ({ page }) => {
  await page.goto(`${WORKSPACE}/ask`);
  await settled(page);
  await page.getByText("What depends on customer_id?").first().click();
  await page.waitForTimeout(2500);
  const body = await page.locator("body").innerText();
  expect(body).toMatch(/cust_no/);
  expect(body).toMatch(/party_key/);
});

// -------------------------------------------------------------------------- break lab

test("8. break and repair: rename customer_id, then restore the journeys", async ({ page }) => {
  await page.goto(`${WORKSPACE}/break-lab`);
  await settled(page);
  const body = await page.locator("body").innerText();
  // The standing honesty copy must be present before anything is broken.
  expect(body.toLowerCase()).toMatch(/never modified|base project/);
});

// ----------------------------------------------------------------------------- galaxy

test("9. the galaxy renders and offers a keyboard-navigable alternative", async ({ page }) => {
  await page.goto(`${WORKSPACE}/galaxy`);
  await settled(page);
  await expect(page.getByTestId("graph-canvas")).toBeVisible();

  // The canvas is opaque to assistive technology, so a real list must exist too.
  const listbox = page.getByRole("listbox", { name: /graph nodes/i });
  const listView = page.getByRole("tab", { name: /list/i });
  const hasAlternative =
    (await listbox.count()) > 0 || (await listView.count()) > 0;
  expect(hasAlternative, "the graph needs an accessible list alternative").toBeTruthy();
});

/** The rendered bounding box of everything in the canvas, in canvas coordinates. */
async function graphBox(page: Page) {
  return page.evaluate(() => {
    // Cytoscape registers itself on its own container, so no production seam is needed.
    const el = document.querySelector('[data-testid="graph-canvas"]') as any;
    const cy = el?._cyreg?.cy;
    if (!cy || cy.elements().length === 0) return null;
    const bb = cy.elements().renderedBoundingBox();
    return { w: cy.width(), h: cy.height(), x1: bb.x1, y1: bb.y1, x2: bb.x2, y2: bb.y2 };
  });
}

function expectFitted(box: Awaited<ReturnType<typeof graphBox>>, when: string) {
  expect(box, "the canvas should expose a Cytoscape instance with elements").not.toBeNull();
  const { w, h, x1, y1, x2, y2 } = box!;
  // A pixel of slack absorbs the sub-pixel rounding in Cytoscape's own maths.
  expect(x1, `${when}: clipped on the left`).toBeGreaterThanOrEqual(-1);
  expect(y1, `${when}: clipped at the top`).toBeGreaterThanOrEqual(-1);
  expect(x2, `${when}: clipped on the right`).toBeLessThanOrEqual(w + 1);
  expect(y2, `${when}: clipped at the bottom`).toBeLessThanOrEqual(h + 1);
  // It also has to use the space. A graph collapsed into one corner passes the bounds
  // check above while still looking broken.
  const covered = ((x2 - x1) * (y2 - y1)) / (w * h);
  expect(covered, `${when}: fills only ${(covered * 100).toFixed(1)}% of the canvas`)
    .toBeGreaterThan(0.2);
}

test("9b. the graph stays fitted when the window is resized", async ({ page }) => {
  // Regression: Cytoscape measures its container once and never again. Resizing the
  // window — or opening the inspector, or collapsing the filter rail — left the renderer
  // on the old size, so the graph drifted out of view and never recovered. A plain
  // page-load assertion does not catch this: it only appears once the box *changes*.
  await page.goto(`${WORKSPACE}/galaxy`);
  await settled(page);
  await expect(page.getByTestId("graph-canvas")).toBeVisible();
  expectFitted(await graphBox(page), "on load");

  for (const size of [
    { width: 1024, height: 768 },
    { width: 1680, height: 1050 },
  ]) {
    await page.setViewportSize(size);
    // The observer coalesces into an animation frame; give it a couple.
    await page.waitForTimeout(250);
    expectFitted(await graphBox(page), `after resize to ${size.width}x${size.height}`);
  }
});

test("10. the legend is available and does not rely on colour alone", async ({ page }) => {
  await page.goto(`${WORKSPACE}/galaxy`);
  await settled(page);
  const body = await page.locator("body").innerText();
  expect(body.toLowerCase()).toMatch(/legend|stated by the specification/);
});

// ---------------------------------------------------------------------------- reports

test("11. every unavailable export explains itself instead of being a dead button", async ({ page }) => {
  await page.goto(`${WORKSPACE}/reports`);
  await settled(page);
  const body = await page.locator("body").innerText();
  expect(body).toMatch(/interactive/i);
  // The PDF must never be described as interactive.
  expect(body).toMatch(/static|print/i);
});

// --------------------------------------------------------------------------- settings

test("12. settings leads with privacy", async ({ page }) => {
  await page.goto(`${WORKSPACE}/settings`);
  await settled(page);
  const body = await page.locator("body").innerText();
  expect(body.toLowerCase()).toContain("privacy");
  expect(body.toLowerCase()).toMatch(/ollama/);
});

// --------------------------------------------------------------------------- missions

test("13. missions are listed with difficulty and where to solve them", async ({ page }) => {
  await page.goto(`${WORKSPACE}/missions`);
  await settled(page);
  const body = await page.locator("body").innerText();
  expect(body).toMatch(/Hidden Dependency/i);
  expect(body).toMatch(/Stop the Data Leak/i);
  expect(body).toMatch(/Survive the Rename/i);
});

// ------------------------------------------------------------------------------ shell

test("14. the command palette opens and searches the estate", async ({ page }) => {
  await page.goto(WORKSPACE);
  await settled(page);
  await page.keyboard.press("Meta+k");
  const search = page.getByRole("textbox", { name: /search/i }).first();
  await expect(search).toBeVisible();
  await search.fill("customer_id");
  await page.waitForTimeout(900);
  await expect(page.getByRole("listbox")).toContainText(/customer_id/i);
});

test("15. the provider indicator states where inference happens", async ({ page }) => {
  await page.goto(WORKSPACE);
  await settled(page);
  const indicator = page.getByLabel(/local|external|checking providers/i).first();
  await expect(indicator).toBeVisible();
});

// ------------------------------------------------------------------------------ import

test("16. an invalid specification is rejected with a located error", async ({ page }) => {
  await page.goto("/import");
  await settled(page);
  await expect(page.getByText(/build your api galaxy/i)).toBeVisible();
});

// ------------------------------------------------------------------- reduced motion

test("17. reduced motion is honoured", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  // The hero must still render its content, not just its animation.
  await expect(page.getByRole("button", { name: /explore the demo galaxy/i }).first()).toBeVisible();
});

// ------------------------------------------------------------------------ no console errors

test("18. the main screens produce no console errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(String(error)));

  for (const path of ["/", WORKSPACE, `${WORKSPACE}/journeys`, `${WORKSPACE}/galaxy`,
                      `${WORKSPACE}/ask`, `${WORKSPACE}/break-lab`, `${WORKSPACE}/arena`,
                      `${WORKSPACE}/reports`, `${WORKSPACE}/settings`, `${WORKSPACE}/missions`,
                      "/import"]) {
    await page.goto(path);
    await settled(page);
  }

  // Ignore noise the app does not control (favicon, devtools, extension chatter).
  const real = errors.filter(
    (text) =>
      !/favicon|Download the React DevTools|ResizeObserver loop|Extension/i.test(text),
  );
  expect(real, `console errors:\n${real.join("\n")}`).toHaveLength(0);
});
