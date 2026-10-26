// Builds and serves the web app for browser tests on port 3200, pointed at the
// test API on 8100. Builds into .next-e2e so the normal .next build is untouched.
// Set E2E_SKIP_BUILD=1 to reuse the last test build.
import { spawn, spawnSync } from "node:child_process";
import path from "node:path";

const web = path.resolve(import.meta.dirname, "../..");
const next = path.join(web, "node_modules", "next", "dist", "bin", "next");
const env = {
  ...process.env,
  NEXT_DIST_DIR: ".next-e2e",
  BACKEND_URL: "http://127.0.0.1:8100",
  NODE_ENV: "production",
};

if (!process.env.E2E_SKIP_BUILD) {
  const build = spawnSync(process.execPath, [next, "build"], { cwd: web, env, stdio: "inherit" });
  if (build.status !== 0) process.exit(build.status ?? 1);
}

const server = spawn(process.execPath, [next, "start", "-p", "3200"], { cwd: web, env, stdio: "inherit" });
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => server.kill(signal));
server.on("exit", (code) => process.exit(code ?? 0));
