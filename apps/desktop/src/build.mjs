import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import path from "node:path";

const root = path.resolve(process.cwd(), "..", "..");
const webDist = path.join(root, "apps", "web", "dist");

if (!existsSync(webDist)) {
  throw new Error(`Missing web build output at ${webDist}`);
}

execFileSync("npx", ["electron-builder", "dist"], { stdio: "inherit", cwd: process.cwd() });
