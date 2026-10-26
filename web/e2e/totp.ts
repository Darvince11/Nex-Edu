import { createHmac } from "node:crypto";

/** Seeded for the test super admin in e2e/servers/seed_platform.py. */
export const OPS = {
  email: "ops@nexedu.test",
  password: "platform-ops-e2e-password",
  totpSecret: "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP",
};

function base32(secret: string): Buffer {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const char of secret.replace(/=+$/, "").toUpperCase()) {
    bits += alphabet.indexOf(char).toString(2).padStart(5, "0");
  }
  const bytes = bits.match(/.{8}/g) ?? [];
  return Buffer.from(bytes.map((b) => Number.parseInt(b, 2)));
}

/** The demo head teacher, given a TOTP secret by seed_platform.py. */
export const HEAD = {
  email: "head@greenfield.test",
  password: "NexEdu-demo-2026!",
  totpSecret: "KRSXG5CTMVRXEZLUKRSXG5CTMVRXEZLU",
};

/** The demo proprietor (school owner), given a TOTP secret by seed_platform.py. */
export const OWNER = {
  email: "owner@greenfield.test",
  password: "NexEdu-demo-2026!",
  totpSecret: "ONSWG4TFOQYTEMZUONSWG4TFOQYTEMZU",
};

/** A class teacher of JHS 2 A, seeded by seed_platform.py. */
export const CLASS_TEACHER = {
  email: "classteacher@greenfield.test",
  password: "NexEdu-demo-2026!",
  totpSecret: "MNWGC43TORSWCY3IMVZDEMBSGZQXGZLT",
};

/** RFC 6238 TOTP (SHA-1, 30 s, 6 digits), the same as allauth's. */
export function totp(secret: string, now = Date.now()): string {
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(now / 1000 / 30)));
  const digest = createHmac("sha1", base32(secret)).update(counter).digest();
  const offset = (digest.at(-1) ?? 0) & 0x0f;
  const value = digest.readUInt32BE(offset) & 0x7fffffff;
  return String(value % 1_000_000).padStart(6, "0");
}
