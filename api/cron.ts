import type { IncomingMessage, ServerResponse } from "http";
import { put } from "@vercel/blob";

const GAMES_SOURCE =
  "https://raw.githubusercontent.com/zKauaFerreira/The-Gaming-Rumble/refs/heads/games/online_fix_games.json";

function json(res: ServerResponse, status: number, body: object) {
  const payload = JSON.stringify(body);
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(payload);
}

export default async function handler(req: IncomingMessage, res: ServerResponse) {
  const cronSecret = process.env.CRON_SECRET;

  if (!cronSecret) {
    return json(res, 500, { error: "CRON_SECRET not configured" });
  }

  const authHeader = req.headers["authorization"] as string | undefined;

  if (!authHeader) {
    return json(res, 401, { error: "Authorization header missing" });
  }

  if (authHeader !== `Bearer ${cronSecret}`) {
    return json(res, 403, { error: "Invalid token" });
  }

  const upstream = await fetch(GAMES_SOURCE);
  if (!upstream.ok) {
    return json(res, 502, { error: `GitHub fetch failed: ${upstream.status}` });
  }

  const body = await upstream.arrayBuffer();

  await put("games.json", body, {
    access: "public",
    allowOverwrite: true,
    contentType: "application/json",
  });

  return json(res, 200, { ok: true, updatedAt: new Date().toISOString() });
}
