import { existsSync, mkdirSync, readdirSync, copyFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SKILLS_SOURCE = join(__dirname, "skills");

function copySkills(sourceDir, targetBase) {
  if (!existsSync(sourceDir)) return;

  const targetDir = join(targetBase, ".opencode", "skills");
  if (!existsSync(targetDir)) mkdirSync(targetDir, { recursive: true });

  for (const entry of readdirSync(sourceDir, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const src = join(sourceDir, entry.name, "SKILL.md");
    const dstDir = join(targetDir, entry.name);
    const dst = join(dstDir, "SKILL.md");
    if (existsSync(src) && !existsSync(dst)) {
      mkdirSync(dstDir, { recursive: true });
      copyFileSync(src, dst);
    }
  }
}

export const WorkflowKitPlugin = async ({ directory }) => {
  if (directory) copySkills(SKILLS_SOURCE, directory);

  const home = process.env.HOME || process.env.USERPROFILE;
  if (home) {
    const globalTarget = join(home, ".config", "opencode");
    copySkills(SKILLS_SOURCE, globalTarget);
  }

  return {};
};
