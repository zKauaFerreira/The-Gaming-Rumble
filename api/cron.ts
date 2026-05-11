import type { VercelRequest, VercelResponse } from "@vercel/node";
import { put } from "@vercel/blob";

const GAMES_SOURCE =
  "https://raw.githubusercontent.com/zKauaFerreira/The-Gaming-Rumble/refs/heads/games/online_fix_games.json";

export default async function handler(req: VercelRequest, res: VercelResponse) {
  const cronSecret = process.env.CRON_SECRET;
  const authHeader = req.headers["authorization"];

  if (!cronSecret || authHeader !== `Bearer ${cronSecret}`) {
    return res.status(401).end("Unauthorized");
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
