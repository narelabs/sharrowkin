#!/usr/bin/env node
/**
 * CI Contrast Check — validates WCAG 2.1 contrast ratios for design tokens.
 *
 * Parses ui/styles/tokens.css, extracts oklch color values for both themes,
 * converts to sRGB, and checks contrast ratios for critical text/surface pairs.
 *
 * Exit code 1 if any pair fails:
 *   - Normal text: ratio >= 4.5
 *   - Large text:  ratio >= 3.0
 */

import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const TOKENS_PATH = resolve(__dirname, "../styles/tokens.css");

// ─── oklch → sRGB conversion ────────────────────────────────────────────────

/**
 * Convert oklch(L C H) to linear sRGB [0..1] via OKLab intermediate.
 * L is lightness [0..1], C is chroma [0..∞], H is hue in degrees.
 */
function oklchToLinearRgb(L, C, H) {
  // oklch → oklab
  const hRad = (H * Math.PI) / 180;
  const a = C * Math.cos(hRad);
  const b = C * Math.sin(hRad);

  // oklab → linear LMS (approximate inverse of cube-root)
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.2914855480 * b;

  const l = l_ * l_ * l_;
  const m = m_ * m_ * m_;
  const s = s_ * s_ * s_;

  // LMS → linear sRGB
  const r = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s;
  const g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s;
  const bVal = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s;

  return [r, g, bVal];
}

/**
 * Convert linear sRGB component to sRGB gamma-corrected [0..1].
 */
function linearToSrgb(c) {
  if (c <= 0.0031308) return 12.92 * c;
  return 1.055 * Math.pow(c, 1 / 2.4) - 0.055;
}

/**
 * Parse an oklch(...) string and return sRGB [0..1] triplet.
 */
function parseOklch(value) {
  // Match: oklch(L C H) or oklch(L C H / alpha)
  const match = value.match(
    /oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)(?:\s*\/\s*[\d.]+)?\s*\)/
  );
  if (!match) return null;

  const L = parseFloat(match[1]);
  const C = parseFloat(match[2]);
  const H = parseFloat(match[3]);

  const [rLin, gLin, bLin] = oklchToLinearRgb(L, C, H);

  // Clamp to [0, 1] after gamma correction
  const r = Math.max(0, Math.min(1, linearToSrgb(rLin)));
  const g = Math.max(0, Math.min(1, linearToSrgb(gLin)));
  const b = Math.max(0, Math.min(1, linearToSrgb(bLin)));

  return [r, g, b];
}

// ─── WCAG 2.1 relative luminance & contrast ratio ───────────────────────────

/**
 * Relative luminance from sRGB [0..1] triplet.
 */
function relativeLuminance([r, g, b]) {
  const toLinear = (c) =>
    c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  return 0.2126 * toLinear(r) + 0.7152 * toLinear(g) + 0.0722 * toLinear(b);
}

/**
 * WCAG contrast ratio between two sRGB [0..1] triplets.
 */
function contrastRatio(color1, color2) {
  const l1 = relativeLuminance(color1);
  const l2 = relativeLuminance(color2);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

// ─── CSS parsing ────────────────────────────────────────────────────────────

/**
 * Extract CSS custom properties from a theme block.
 * Returns a Map<varName, oklchValue>.
 */
function extractThemeVars(css, selectorRegex) {
  const vars = new Map();
  const selectorMatch = css.match(selectorRegex);
  if (!selectorMatch) return vars;

  // Find the block after the selector
  const startIdx = selectorMatch.index + selectorMatch[0].length;
  let braceCount = 0;
  let blockStart = -1;
  let blockEnd = -1;

  for (let i = startIdx; i < css.length; i++) {
    if (css[i] === "{") {
      if (braceCount === 0) blockStart = i + 1;
      braceCount++;
    } else if (css[i] === "}") {
      braceCount--;
      if (braceCount === 0) {
        blockEnd = i;
        break;
      }
    }
  }

  if (blockStart === -1 || blockEnd === -1) return vars;

  const block = css.slice(blockStart, blockEnd);
  const propRegex = /--([\w-]+)\s*:\s*([^;]+);/g;
  let match;
  while ((match = propRegex.exec(block)) !== null) {
    const name = `--${match[1]}`;
    const value = match[2].trim();
    if (value.startsWith("oklch(")) {
      vars.set(name, value);
    }
  }

  return vars;
}

// ─── Main ───────────────────────────────────────────────────────────────────

function main() {
  const css = readFileSync(TOKENS_PATH, "utf-8");

  const darkVars = extractThemeVars(css, /:root\[data-theme="dark"\]/);
  const lightVars = extractThemeVars(css, /:root\[data-theme="light"\]/);

  if (darkVars.size === 0) {
    console.error("ERROR: Could not parse dark theme variables from tokens.css");
    process.exit(1);
  }
  if (lightVars.size === 0) {
    console.error("ERROR: Could not parse light theme variables from tokens.css");
    process.exit(1);
  }

  // Pairs to check: [foreground, background, label, minRatio]
  const pairs = [
    ["--color-text", "--color-surface", "text / surface", 4.5],
    ["--color-text-muted", "--color-surface", "text-muted / surface", 4.5],
    ["--color-accent", "--color-bg", "accent / bg", 3.0],
  ];

  let allPassed = true;
  const results = [];

  for (const [theme, vars] of [
    ["dark", darkVars],
    ["light", lightVars],
  ]) {
    for (const [fgVar, bgVar, label, minRatio] of pairs) {
      const fgOklch = vars.get(fgVar);
      const bgOklch = vars.get(bgVar);

      if (!fgOklch || !bgOklch) {
        results.push({
          theme,
          label,
          status: "SKIP",
          ratio: "N/A",
          required: minRatio,
          reason: `Missing var: ${!fgOklch ? fgVar : bgVar}`,
        });
        continue;
      }

      const fgRgb = parseOklch(fgOklch);
      const bgRgb = parseOklch(bgOklch);

      if (!fgRgb || !bgRgb) {
        results.push({
          theme,
          label,
          status: "SKIP",
          ratio: "N/A",
          required: minRatio,
          reason: "Could not parse oklch value",
        });
        continue;
      }

      const ratio = contrastRatio(fgRgb, bgRgb);
      const passed = ratio >= minRatio;

      if (!passed) allPassed = false;

      results.push({
        theme,
        label,
        status: passed ? "PASS" : "FAIL",
        ratio: ratio.toFixed(2),
        required: minRatio,
      });
    }
  }

  // Print results
  console.log("\n╔══════════════════════════════════════════════════════════════╗");
  console.log("║          WCAG 2.1 Contrast Ratio Check                     ║");
  console.log("╠══════════════════════════════════════════════════════════════╣");
  console.log(
    "║ " +
      "Theme".padEnd(7) +
      "Pair".padEnd(24) +
      "Ratio".padEnd(8) +
      "Min".padEnd(6) +
      "Status".padEnd(6) +
      " ║"
  );
  console.log("╠══════════════════════════════════════════════════════════════╣");

  for (const r of results) {
    const statusIcon =
      r.status === "PASS" ? "✓" : r.status === "FAIL" ? "✗" : "?";
    console.log(
      "║ " +
        r.theme.padEnd(7) +
        r.label.padEnd(24) +
        String(r.ratio).padEnd(8) +
        String(r.required).padEnd(6) +
        `${statusIcon} ${r.status}`.padEnd(6) +
        " ║"
    );
  }

  console.log("╚══════════════════════════════════════════════════════════════╝\n");

  if (!allPassed) {
    console.error("FAILED: One or more contrast pairs do not meet WCAG requirements.");
    process.exit(1);
  }

  console.log("All contrast checks passed ✓\n");
  process.exit(0);
}

main();
