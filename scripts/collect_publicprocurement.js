// scripts/collect_publicprocurement.js
// Captures the FIRST browser response whose JSON body looks like search results
// (publications/items/results array). No manual HTTP request from Node.
// Usage: node scripts/collect_publicprocurement.js [term] [page] [pageSize]

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const term = (process.argv[2] || "travaux").trim();
const pageNum = parseInt(process.argv[3] || "1", 10);
const pageSizeNum = parseInt(process.argv[4] || "25", 10);

const OUTPUT_DIR = path.join(process.cwd(), "data", "raw", "publicprocurement");
const DEBUG_DIR = path.join(OUTPUT_DIR, "_debug");
const RESULT_SCORE_WINNER = 10;
const CANDIDATES_TOP_N = 10;
const BODY_PREVIEW_MAX = 500;
const TIMEOUT_AFTER_FIRST_MS = 45000;

// Ensure directories exist
if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR, { recursive: true });
if (!fs.existsSync(DEBUG_DIR)) fs.mkdirSync(DEBUG_DIR, { recursive: true });

/** URL matches any of the capture patterns (case-insensitive). */
function urlMatches(url) {
  const u = (url || "").toLowerCase();
  return (
    u.includes("api/sea/search/publications") ||
    u.includes("search/publications") ||
    u.includes("/publications") ||
    u.includes("api/sea/search")
  );
}

/**
 * Heuristic score for "this looks like search results".
 * +10 publications non-empty array, +10 items non-empty array, +8 results non-empty array,
 * +5 total/totalCount, +3 any nested array of objects length > 0.
 */
function resultScore(body) {
  if (body == null || typeof body !== "object") return 0;
  let score = 0;
  const arrPub = body.publications;
  const arrItems = body.items;
  const arrResults = body.results;
  if (Array.isArray(arrPub) && arrPub.length > 0) score += 10;
  if (Array.isArray(arrItems) && arrItems.length > 0) score += 10;
  if (Array.isArray(arrResults) && arrResults.length > 0) score += 8;
  if (typeof body.total === "number" || typeof body.totalCount === "number") score += 5;
  // +3 if any nested array of objects has length > 0
  function hasNestedArrayOfObjects(obj, depth) {
    if (depth > 3 || obj == null) return false;
    if (Array.isArray(obj)) {
      if (obj.length > 0 && typeof obj[0] === "object" && obj[0] !== null) return true;
      return obj.some((x) => hasNestedArrayOfObjects(x, depth + 1));
    }
    if (typeof obj === "object") {
      return Object.values(obj).some((v) => hasNestedArrayOfObjects(v, depth + 1));
    }
    return false;
  }
  if (hasNestedArrayOfObjects(body, 0)) score += 3;
  return score;
}

/** Best-effort totalCount from response JSON. */
function extractTotalCount(json) {
  if (json == null || typeof json !== "object") return null;
  if (typeof json.totalCount === "number") return json.totalCount;
  if (typeof json.total === "number") return json.total;
  if (typeof json.itemsCount === "number") return json.itemsCount;
  if (json.pagination != null && typeof json.pagination.total === "number") return json.pagination.total;
  if (json.page != null && typeof json.page.totalCount === "number") return json.page.totalCount;
  if (json.metadata != null && typeof json.metadata.totalCount === "number") return json.metadata.totalCount;
  const arr = json.publications || json.items || json.results;
  if (Array.isArray(arr)) return arr.length;
  return null;
}

function bodyPreview(body, maxLen = BODY_PREVIEW_MAX) {
  const s = typeof body === "string" ? body : JSON.stringify(body);
  if (s.length <= maxLen) return s;
  return s.slice(0, maxLen) + "...";
}

(async () => {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({
    ignoreHTTPSErrors: true,
    locale: "fr-FR",
    userAgent:
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    extraHTTPHeaders: {
      Accept: "application/json, text/plain, */*",
      "Accept-Language": "fr-BE,fr;q=0.9,en;q=0.8",
    },
    viewport: { width: 1280, height: 800 },
  });

  const page = await context.newPage();

  console.log("Opening website...");
  await page.goto("https://www.publicprocurement.be/bda", { waitUntil: "domcontentloaded" });

  console.log("");
  console.log("In the opened browser:");
  console.log(`1) Type this term in the search:  ${term}`);
  console.log("2) Press Enter");
  console.log("3) Wait for results to appear");
  console.log("");
  console.log("Waiting for manual search...");

  const candidates = [];
  let winnerFound = false;
  let timeout45Started = false;
  let timeout45Id = null;
  let winnerResolve;
  const waitForWinner = new Promise((r) => (winnerResolve = r));

  const finishWithWinner = (winnerUrl, winnerStatus, winnerBody) => {
    if (winnerFound) return;
    winnerFound = true;
    if (timeout45Id) clearTimeout(timeout45Id);

    const totalCount = extractTotalCount(winnerBody);
    const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
    const OUTPUT_FILE = path.join(OUTPUT_DIR, `publicprocurement_${timestamp}.json`);
    const metadata = {
      term,
      page: pageNum,
      pageSize: pageSizeNum,
      timestamp: new Date().toISOString(),
      url: winnerUrl,
      status: winnerStatus,
      totalCount,
    };
    const output = { metadata, json: winnerBody };
    fs.writeFileSync(OUTPUT_FILE, JSON.stringify(output, null, 2), "utf-8");

    console.log("");
    console.log("WINNER detected.");
    console.log(`Saved to: ${OUTPUT_FILE}`);
    console.log(`Winner URL: ${winnerUrl}`);
    if (typeof totalCount === "number") console.log(`totalCount: ${totalCount}`);
    if (winnerResolve) winnerResolve();
  };

  const finishWithNoWinner = async () => {
    if (winnerFound) return;
    const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
    const sorted = [...candidates].sort((a, b) => (b.score || 0) - (a.score || 0));
    const top = sorted.slice(0, CANDIDATES_TOP_N);
    const debugFile = path.join(DEBUG_DIR, `no_results_${timestamp}.json`);
    fs.writeFileSync(
      debugFile,
      JSON.stringify(
        {
          term,
          page: pageNum,
          pageSize: pageSizeNum,
          timestamp: new Date().toISOString(),
          candidates: top.map((c) => ({
            score: c.score,
            status: c.status,
            url: c.url,
            contentType: c.contentType,
            bodyPreview: c.bodyPreview,
          })),
        },
        null,
        2
      ),
      "utf-8"
    );
    const screenshotPath = path.join(DEBUG_DIR, `results_page_${timestamp}.png`);
    try {
      await page.screenshot({ path: screenshotPath });
    } catch (e) {
      console.error("Screenshot failed:", e.message);
    }
    console.error("");
    console.error("No WINNER within timeout. Debug saved:");
    console.error(`  ${debugFile}`);
    console.error(`  ${screenshotPath}`);
    process.exit(1);
  };

  const start45sTimeout = () => {
    if (timeout45Started) return;
    timeout45Started = true;
    timeout45Id = setTimeout(async () => {
      await finishWithNoWinner();
    }, TIMEOUT_AFTER_FIRST_MS);
  };

  page.on("response", async (response) => {
    try {
      const url = response.url();
      if (!urlMatches(url)) return;

      const status = typeof response.status === "function" ? response.status() : response.status;
      const headers = response.headers();
      const contentType = headers["content-type"] || "";

      let body = null;
      let bodyText = "";
      try {
        body = await response.json();
      } catch (e) {
        try {
          bodyText = await response.text();
        } catch (e2) {
          bodyText = String(e2.message);
        }
      }

      const parsed = body != null ? body : (bodyText ? { _rawBody: bodyText } : null);
      const score = parsed && typeof parsed === "object" ? resultScore(parsed) : 0;

      const preview = body != null ? bodyPreview(body) : bodyPreview(bodyText);
      candidates.push({
        score,
        status,
        url,
        contentType,
        bodyPreview: preview,
      });

      console.log(`  ${status} ${url}  score=${score}`);

      start45sTimeout();

      if (score >= RESULT_SCORE_WINNER && parsed && typeof parsed === "object") {
        finishWithWinner(url, status, parsed);
      }
    } catch (e) {
      console.error("Error processing response:", e.message);
    }
  });

  // Wait for winner (resolve from finishWithWinner); timeout path calls process.exit(1)
  await waitForWinner;

  await page.waitForTimeout(500);
  await context.close();
  await browser.close();
  process.exit(0);
})().catch((err) => {
  console.error("", err.message);
  process.exit(1);
});
