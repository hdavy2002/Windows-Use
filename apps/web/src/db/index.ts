import { neon } from "@neondatabase/serverless";
import { drizzle } from "drizzle-orm/neon-http";
import * as schema from "./schema";

const connectionString = process.env.NEON_DATABASE_URL;

// Lazy connection — only fails when actually used, not at build time
const sql = connectionString ? neon(connectionString) : null;
export const db = sql ? drizzle(sql, { schema }) : (null as any);
