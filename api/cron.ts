import type { IncomingMessage, ServerResponse } from "http";
import { put } from "@vercel/blob";

const GAMES_SOURCE =
  "https://raw.githubusercontent.com/zKauaFerreira/The-Gaming-Rumble/refs/heads/games/online_fix_games.json";
const STATS_SOURCE =
  "https://raw.githubusercontent.com/zKauaFerreira/The-Gaming-Rumble/refs/heads/games/stats.json";

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

  try {
    const [gamesRes, statsRes] = await Promise.all([
      fetch(GAMES_SOURCE),
      fetch(STATS_SOURCE)
    ]);

    if (!gamesRes.ok) throw new Error(`Games fetch failed: ${gamesRes.status}`);
    if (!statsRes.ok) throw new Error(`Stats fetch failed: ${statsRes.status}`);

    const [gamesBody, statsBody] = await Promise.all([
      gamesRes.arrayBuffer(),
      statsRes.arrayBuffer()
    ]);

    await Promise.all([
      put("games.json", gamesBody, {
        access: "public",
        allowOverwrite: true,
        contentType: "application/json",
      }),
      put("stats.json", statsBody, {
        access: "public",
        allowOverwrite: true,
        contentType: "application/json",
      })
    ]);

    return json(res, 200, { ok: true, updatedAt: new Date().toISOString() });
  } catch (error: any) {
    return json(res, 502, { error: error.message });
  }
}
