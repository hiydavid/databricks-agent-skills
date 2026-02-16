#!/usr/bin/env node
// Convert a Mermaid .mmd file (or markdown with embedded Mermaid) to .excalidraw JSON.
// Uses Puppeteer + @excalidraw/mermaid-to-excalidraw in a headless browser.
//
// Usage:
//   node scripts/mermaid-to-excalidraw.mjs <input.mmd> [output.excalidraw]
//   node scripts/mermaid-to-excalidraw.mjs <input.md> [output.excalidraw]  # extracts first mermaid block
//
// If output is omitted, replaces the extension with .excalidraw.
// Add --open to open the file in the native Excalidraw app after conversion.

import puppeteer from "puppeteer";
import { writeFileSync, readFileSync } from "fs";
import { execSync } from "child_process";

const args = process.argv.slice(2).filter((a) => a !== "--open");
const shouldOpen = process.argv.includes("--open");

if (args.length === 0) {
  console.error("Usage: mermaid-to-excalidraw.mjs <input.mmd|input.md> [output.excalidraw] [--open]");
  process.exit(1);
}

const input = args[0];
const output = args[1] || input.replace(/\.(mmd|md)$/, ".excalidraw");

let mermaidText = readFileSync(input, "utf-8").trim();

// If input is markdown, extract the first mermaid code block
if (input.endsWith(".md")) {
  const match = mermaidText.match(/```mermaid\n([\s\S]*?)```/);
  if (!match) {
    console.error("No mermaid code block found in markdown file.");
    process.exit(1);
  }
  mermaidText = match[1].trim();
}

const browser = await puppeteer.launch({ headless: true });
const page = await browser.newPage();

await page.setContent("<!DOCTYPE html><html><body></body></html>");

const result = await page.evaluate(async (mmd) => {
  try {
    await import("https://cdn.jsdelivr.net/npm/mermaid@11/+esm");
    const { parseMermaidToExcalidraw } = await import(
      "https://cdn.jsdelivr.net/npm/@excalidraw/mermaid-to-excalidraw@2/+esm"
    );
    const { elements, files } = await parseMermaidToExcalidraw(mmd);
    return { elements, files, error: null };
  } catch (e) {
    return { elements: null, files: null, error: e.message };
  }
}, mermaidText);

await browser.close();

if (result.error) {
  console.error("Conversion failed:", result.error);
  process.exit(1);
}

const excalidrawFile = {
  type: "excalidraw",
  version: 2,
  source: "mermaid-to-excalidraw",
  elements: result.elements,
  files: result.files || {},
  appState: { viewBackgroundColor: "#ffffff" },
};

writeFileSync(output, JSON.stringify(excalidrawFile, null, 2));
console.log(`Written to ${output}`);

if (shouldOpen) {
  execSync(`open "${output}"`);
  console.log("Opened in Excalidraw.");
}
