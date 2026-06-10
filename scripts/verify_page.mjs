import { chromium } from "playwright";
import { existsSync } from "node:fs";

function argValue(name, fallback) {
  const index = process.argv.indexOf(name);
  if (index === -1 || index + 1 >= process.argv.length) return fallback;
  return process.argv[index + 1];
}

const targetUrl = argValue("--url", "http://127.0.0.1:8080");
const trackId = argValue("--track", "compute");

function findLocalChromium() {
  const candidates = [
    process.env.PLAYWRIGHT_EXECUTABLE_PATH,
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
  ].filter(Boolean);

  return candidates.find((path) => existsSync(path)) || "";
}

const executablePath = findLocalChromium();

async function inspectPage(page) {
  await page.waitForSelector(".ai-catalyst-wrap", { timeout: 10000 });
  await page.waitForSelector(".catalyst-card[data-story-id]", { timeout: 10000 });

  return page.evaluate(() => ({
    sectionVisible: Boolean(document.querySelector(".ai-catalyst-wrap")),
    heading: document.querySelector(".ai-catalyst-head h2")?.textContent?.trim() || "",
    meta: document.querySelector("#aiCatalystMeta")?.textContent?.trim() || "",
    trackCount: document.querySelectorAll(".catalyst-track").length,
    cardCount: document.querySelectorAll(".catalyst-card").length,
    firstCard: {
      storyId: document.querySelector(".catalyst-card")?.dataset.storyId || "",
      evidence: document.querySelector(".catalyst-card")?.dataset.evidenceLevel || "",
      chainNodes: document.querySelector(".catalyst-card")?.dataset.chainNodes || "",
    },
  }));
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    ...(executablePath ? { executablePath } : {}),
  });
  try {
    const desktop = await browser.newPage({ viewport: { width: 1440, height: 1200 } });
    await desktop.goto(targetUrl, { waitUntil: "networkidle" });
    const desktopResult = await inspectPage(desktop);

    const trackSelector = `.catalyst-track[data-track-id="${trackId}"]`;
    const trackExists = await desktop.locator(trackSelector).count();
    let filterResult = null;
    if (trackExists) {
      await desktop.click(trackSelector);
      await desktop.waitForTimeout(100);
      filterResult = await desktop.evaluate(() => ({
        active: document.querySelector(".catalyst-track.active")?.textContent?.trim() || "",
        meta: document.querySelector("#aiCatalystMeta")?.textContent?.trim() || "",
        cardCount: document.querySelectorAll(".catalyst-card").length,
        firstNodes: Array.from(document.querySelectorAll(".catalyst-card"))
          .slice(0, 3)
          .map((el) => el.dataset.chainNodes || ""),
      }));
    }

    const mobile = await browser.newPage({ viewport: { width: 390, height: 900 } });
    await mobile.goto(targetUrl, { waitUntil: "networkidle" });
    await inspectPage(mobile);
    const mobileResult = await mobile.evaluate(() => ({
      sectionWidth: Math.round(document.querySelector(".ai-catalyst-wrap").getBoundingClientRect().width),
      listColumns: getComputedStyle(document.querySelector(".ai-catalyst-list")).gridTemplateColumns,
      cardCount: document.querySelectorAll(".catalyst-card").length,
      overflowX: document.documentElement.scrollWidth > window.innerWidth,
    }));

    const result = {
      url: targetUrl,
      desktop: desktopResult,
      filter: filterResult,
      mobile: mobileResult,
    };

    if (!desktopResult.sectionVisible || desktopResult.heading !== "AI产业催化") {
      throw new Error("AI产业催化 section did not render correctly");
    }
    if (!desktopResult.firstCard.storyId || !desktopResult.firstCard.chainNodes) {
      throw new Error("Catalyst card data attributes are missing");
    }
    if (mobileResult.overflowX) {
      throw new Error("Mobile viewport has horizontal overflow");
    }

    console.log(JSON.stringify(result, null, 2));
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
