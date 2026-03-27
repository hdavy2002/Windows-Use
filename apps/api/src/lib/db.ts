import { createDb } from "@humphi/db";
import type { Env } from "../types";

// One DB instance per request (Workers are stateless)
export function db(env: Env) {
  return createDb(env.NEON_DATABASE_URL);
}
