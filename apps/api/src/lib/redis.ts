import { Redis } from "@upstash/redis/cloudflare";
import type { Env } from "../types";

export function redis(env: Env) {
  return new Redis({ url: env.UPSTASH_REDIS_URL, token: env.UPSTASH_REDIS_TOKEN });
}

function today() {
  return new Date().toISOString().split("T")[0];
}

export async function incrementDailyUsage(env: Env, userId: string) {
  const r = redis(env);
  const key = `usage:daily:${userId}:${today()}`;
  const count = await r.incr(key);
  if (count === 1) await r.expire(key, 86400);
  return count;
}

export async function getDailyUsage(env: Env, userId: string): Promise<number> {
  return (await redis(env).get<number>(`usage:daily:${userId}:${today()}`)) ?? 0;
}

export async function getPlanFromCache(env: Env, userId: string) {
  return redis(env).get<string>(`plan:${userId}`);
}

export async function setPlanCache(env: Env, userId: string, plan: string) {
  return redis(env).set(`plan:${userId}`, plan, { ex: 300 }); // 5 min TTL
}

export async function bustPlanCache(env: Env, userId: string) {
  return redis(env).del(`plan:${userId}`);
}

export async function checkRateLimit(
  env: Env,
  key: string,
  limit: number,
  windowSecs: number
): Promise<{ allowed: boolean; count: number }> {
  const r = redis(env);
  const k = `ratelimit:${key}`;
  const count = await r.incr(k);
  if (count === 1) await r.expire(k, windowSecs);
  return { allowed: count <= limit, count };
}
