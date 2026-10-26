// Starts the API for browser tests on port 8100, with fresh data under
// backend/var/e2e and the demo school seeded. Started by playwright.config.ts.
import { spawn, spawnSync } from "node:child_process";
import { rmSync } from "node:fs";
import path from "node:path";

const backend = path.resolve(import.meta.dirname, "../../../backend");
const bin = path.join(backend, ".venv", process.platform === "win32" ? "Scripts" : "bin");
const exe = (name) => path.join(bin, process.platform === "win32" ? `${name}.exe` : name);
const env = { ...process.env, DJANGO_SETTINGS_MODULE: "config.settings.e2e" };

rmSync(path.join(backend, "var", "e2e"), { recursive: true, force: true });

const seedPlatform = path.join(import.meta.dirname, "seed_platform.py");
for (const args of [
  ["manage.py", "migrate", "--noinput"],
  ["manage.py", "seed_demo"],
  ["manage.py", "shell", "--command", `exec(open(${JSON.stringify(seedPlatform)}).read())`],
]) {
  const result = spawnSync(exe("python"), args, { cwd: backend, env, stdio: "inherit" });
  if (result.status !== 0) process.exit(result.status ?? 1);
}

const server = spawn(
  exe("granian"),
  ["--interface", "asgi", "--host", "127.0.0.1", "--port", "8100", "config.asgi:application"],
  { cwd: backend, env, stdio: "inherit" },
);
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => server.kill(signal));
server.on("exit", (code) => process.exit(code ?? 0));
