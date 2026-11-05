// Build step for the static site: writes public/config.js from environment variables and copies
// data/prompts.json into public/. Used by Vercel / Cloudflare Pages ("npm run build") and locally.
import { readFileSync, writeFileSync, existsSync, copyFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

const envFile = join(root, ".env");
if (existsSync(envFile)) {
  for (const line of readFileSync(envFile, "utf8").split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
    if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^['"]|['"]$/g, "");
  }
}

const fail = (msg) => { console.error(`\nBUILD FAILED: ${msg}\n`); process.exit(1); };
const url = (process.env.SUPABASE_URL || "").trim().replace(/\/+$/, "");
const key = (process.env.SUPABASE_ANON_KEY || process.env.SUPABASE_PUBLISHABLE_KEY || "").trim();
if (!url) fail("SUPABASE_URL is not set (see .env.example).");
if (!/^https?:\/\//.test(url)) fail("SUPABASE_URL must start with https://");
if (!key) fail("SUPABASE_ANON_KEY is not set (see .env.example).");

// Refuse to ship an admin key to the browser.
let role = "";
if (key.startsWith("eyJ")) {
  try { role = JSON.parse(Buffer.from(key.split(".")[1], "base64url").toString()).role || ""; } catch {}
}
if (key.startsWith("sb_secret_") || role === "service_role") {
  fail("SUPABASE_ANON_KEY is an ADMIN (service_role/secret) key. Use the anon/publishable key instead.");
}

const config = {
  supabaseUrl: url,
  supabaseKey: key,
  bucket: (process.env.SUPABASE_BUCKET || "recordings").trim(),
  sessionGoal: Math.max(1, parseInt(process.env.SESSION_GOAL || "50", 10) || 50),
  contactText: (process.env.CONTACT_TEXT || "").trim(),
};
writeFileSync(join(root, "public", "config.js"), `window.BV_CONFIG=${JSON.stringify(config)};\n`);

const prompts = JSON.parse(readFileSync(join(root, "data", "prompts.json"), "utf8"));
if (!Array.isArray(prompts) || !prompts.length) fail("data/prompts.json is empty or invalid.");
copyFileSync(join(root, "data", "prompts.json"), join(root, "public", "prompts.json"));

console.log(`Built public/config.js (${url}) and public/prompts.json (${prompts.length} prompts).`);
