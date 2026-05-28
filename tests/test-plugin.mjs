import { existsSync, readdirSync, rmSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";
import { tmpdir } from "os";

let passed = 0;
let failed = 0;

function assert(desc, ok) {
  ok ? (passed++, console.log(`  PASS: ${desc}`)) : (failed++, console.log(`  FAIL: ${desc}`));
}

const pkgDir = dirname(dirname(fileURLToPath(import.meta.url)));
const testDir = join(tmpdir(), "workflow-kit-test");
const expectedSkills = ["execute", "init", "maintain", "monitor", "plan", "status", "synthesize"];

// Cleanup from previous runs
try { rmSync(testDir, { recursive: true }); } catch {}

// Test 1: Package structure
assert("package.json exists", existsSync(join(pkgDir, "package.json")));
assert("opencode-plugin.js exists", existsSync(join(pkgDir, "opencode-plugin.js")));
assert("postinstall.js exists", existsSync(join(pkgDir, "postinstall.js")));

// Test 2: Skills in package
const skills = readdirSync(join(pkgDir, "skills"));
assert("All skills present in package", expectedSkills.every((s) => skills.includes(s)));

// Test 3: Each skill has SKILL.md
for (const s of expectedSkills) {
  assert(`${s}/SKILL.md exists`, existsSync(join(pkgDir, "skills", s, "SKILL.md")));
}

// Test 4: Plugin loads and works
const { WorkflowKitPlugin } = await import(join(pkgDir, "opencode-plugin.js"));

const result = await WorkflowKitPlugin({ directory: testDir });
assert("Plugin returns hooks object", typeof result === "object" && result !== null);

const projectSkills = join(testDir, ".opencode", "skills");
assert("Project skills directory created", existsSync(projectSkills));

const projectSkillList = readdirSync(projectSkills);
assert("All skills deployed to project", expectedSkills.every((s) => projectSkillList.includes(s)));

// Test 5: Idempotent — running again doesn't create duplicates or error
const countBefore = readdirSync(projectSkills).length;
await WorkflowKitPlugin({ directory: testDir });
const countAfter = readdirSync(projectSkills).length;
assert("Idempotent (no duplicates)", countAfter === countBefore);

// Test 6: Plugin handles edge cases gracefully
const nullDir = await WorkflowKitPlugin({ directory: null });
assert("Null directory handled", typeof nullDir === "object");

const emptyCtx = await WorkflowKitPlugin({});
assert("Empty context handled", typeof emptyCtx === "object");

// Cleanup
try { rmSync(testDir, { recursive: true }); } catch {}

console.log(`\nResults: ${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
