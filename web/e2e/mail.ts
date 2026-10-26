import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

/** Where the test API writes emails (config/settings/e2e.py). */
const MAIL_DIR = path.resolve(import.meta.dirname, "../../backend/var/e2e/mail");
const SEPARATOR = /^-{79}$/m;
const CODE = /^([A-Z]{4}-[A-Z]{4})$/m;

function messagesTo(address: string): string[] {
  let files: string[];
  try {
    files = readdirSync(MAIL_DIR).map((f) => path.join(MAIL_DIR, f));
  } catch {
    return [];
  }
  files.sort((a, b) => statSync(a).mtimeMs - statSync(b).mtimeMs);
  return files
    .flatMap((file) => readFileSync(file, "utf8").split(SEPARATOR))
    .filter((message) => message.includes(`To: ${address}`));
}

/** The newest email to `address`, waiting for it to arrive. */
export async function latestEmail(address: string, timeoutMs = 15_000): Promise<string> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const newest = messagesTo(address).at(-1);
    if (newest) return newest;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`No email to ${address} within ${timeoutMs} ms`);
}

/** The verification code from the newest email to `address`. */
export async function latestCode(address: string): Promise<string> {
  const code = CODE.exec(await latestEmail(address))?.[1];
  if (!code) throw new Error(`The newest email to ${address} has no verification code`);
  return code;
}
