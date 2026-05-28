// postinstall.js — copies skills to the global opencode skills directory
// Runs after `npm install` / `bun install` completes.
// CWD is guaranteed to be the package root.

import { existsSync, mkdirSync, readdirSync, copyFileSync } from "fs";
import { join } from "path";
import { homedir } from "os";

const SKILLS_SOURCE = join(import.meta.dirname, "skills");
const GLOBAL_SKILLS = join(homedir(), ".config", "opencode", "skills");

if (!existsSync(GLOBAL_SKILLS)) {
  mkdirSync(GLOBAL_SKILLS, { recursive: true });
}

for (const entry of readdirSync(SKILLS_SOURCE, { withFileTypes: true })) {
  if (!entry.isDirectory()) continue;
  const src = join(SKILLS_SOURCE, entry.name, "SKILL.md");
  const dstDir = join(GLOBAL_SKILLS, entry.name);
  const dst = join(dstDir, "SKILL.md");
  if (existsSync(src) && !existsSync(dst)) {
    mkdirSync(dstDir, { recursive: true });
    copyFileSync(src, dst);
  }
}
