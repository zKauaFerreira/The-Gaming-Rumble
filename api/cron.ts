import type { VercelRequest, VercelResponse } from "@vercel/node";
import { put } from "@vercel/blob";

const GAMES_SOURCE =
  "https://raw.githubusercontent.com/zKauaFerreira/The-Gaming-Rumble/refs/heads/games/online_fix_games.json";

export default async function handler(req: VercelRequest, res: VercelResponse) {
  const cronSecret = process.env.CRON_SECRET;

  if (!cronSecret) {
    return res.status(500).json({ error: "CRON_SECRET not configured" });
  }

  const authHeader = req.headers["authorization"] as string | undefined;

  if (!authHeader) {
    return res.status(401).json({ error: "Authorization header missing" });
  }

  if (authHeader !== `Bearer ${cronSecret}`) {
    return res.status(403).json({ error: "Invalid token" });
  }

  const upstream = await fetch(GAMES_SOURCE);
  if (!upstream.ok) {
    return res.status(502).json({ error: `GitHub fetch failed: ${upstream.status}` });
  }

  const body = await upstream.arrayBuffer();

  await put("games.json", body, {
    access: "public",
    allowOverwrite: true,
    contentType: "application/json",
  });

  return res.json({ ok: true, updatedAt: new Date().toISOString() });
}
