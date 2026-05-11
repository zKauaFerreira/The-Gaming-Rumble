import { zlibSync } from "fflate";

export const GAMES_API =
  "https://mkuqgpwafiakxxi1.public.blob.vercel-storage.com/games.json";

export interface GameFile {
  name: string;
  size: string;
}

export interface SteamData {
  steam_appid: number;
  header_image: string;
  short_description: string;
  short_description_native: string;
  price_brl: string;
  is_free: boolean;
  pc_requirements: { minimum: string | null; recommended: string | null };
  controller_support: string | null;
}

export interface Game {
  title: string;
  page: number;
  url: string;
  last_update: string | null;
  release_date: string | null;
  update_date: string | null;
  created_at: string | null;
  fileSize: string;
  magnet: string;
  torrent_file: string;
  unique_hash: string;
  files: GameFile[];
  comment: string;
  steam: SteamData;
}

export type SortId = "az" | "za" | "newest" | "oldest" | "largest" | "smallest";

/* ── Slug ── */

export function toSlug(title: string): string {
  return title
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-");
}

export function findBySlug(games: Game[], slug: string): Game | null {
  return games.find((g) => toSlug(g.title) === slug) ?? null;
}

/* ── Protocol URL ── */

export function makeProtocolUrl(game: Game): string {
  const payload = {
    title: game.title,
    banner: game.steam?.header_image ?? "",
    parts: game.files?.length ?? 1,
    fileSize: game.fileSize,
    magnet: game.magnet,
  };
  return `gaming-rumble://${btoa(JSON.stringify(payload))}`;
}

/* ── Encode game as zlib+base64 for /?data= deep-link URL ── */

export function encodeGameForDataUrl(game: Game): string {
  const payload = {
    t: game.title,
    b: game.steam?.header_image ?? "",
    p: game.files?.length ?? 1,
    s: game.fileSize,
    m: game.magnet,
  };
  const bytes = new TextEncoder().encode(JSON.stringify(payload));
  const compressed = zlibSync(bytes);
  const b64 = btoa(String.fromCharCode(...Array.from(compressed)));
  return b64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/* ── Sort ── */

function parseSizeToBytes(size: string): number {
  const m = size.match(/([\d.]+)\s*(TB|GB|MB|KB)/i);
  if (!m) return 0;
  const n = parseFloat(m[1]);
  switch (m[2].toUpperCase()) {
    case "TB": return n * 1e12;
    case "GB": return n * 1e9;
    case "MB": return n * 1e6;
    case "KB": return n * 1e3;
    default: return n;
  }
}

/* ── Best available date (update_date → last_update → created_at) ── */

function parseAnyDate(raw: string | null | undefined): number {
  if (!raw) return 0;
  const t = new Date(raw.replace(" ", "T")).getTime();
  return isNaN(t) ? 0 : t;
}

function bestTimestamp(game: Game): number {
  return (
    parseAnyDate(game.update_date) ||
    parseAnyDate(game.last_update) ||
    parseAnyDate(game.created_at)
  );
}

export function getGameDate(game: Game): string | null {
  const ts = bestTimestamp(game);
  if (!ts) return null;
  return new Date(ts).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export function sortGames(games: Game[], sort: SortId | null): Game[] {
  if (!sort) return games;
  const arr = [...games];
  switch (sort) {
    case "az":       return arr.sort((a, b) => a.title.localeCompare(b.title));
    case "za":       return arr.sort((a, b) => b.title.localeCompare(a.title));
    case "newest":   return arr.sort((a, b) => bestTimestamp(b) - bestTimestamp(a));
    case "oldest":   return arr.sort((a, b) => bestTimestamp(a) - bestTimestamp(b));
    case "largest":  return arr.sort((a, b) => parseSizeToBytes(b.fileSize) - parseSizeToBytes(a.fileSize));
    case "smallest": return arr.sort((a, b) => parseSizeToBytes(a.fileSize) - parseSizeToBytes(b.fileSize));
  }
}

/* ── Search with relevance ranking ── */

export function searchGames(games: Game[], query: string): Game[] {
  const q = query.trim().toLowerCase();
  if (!q) return games;

  const rank = (title: string): number => {
    const t = title.toLowerCase();
    if (t === q) return 0;
    if (t.startsWith(q)) return 1;
    const words = t.split(/[\s:_()\-]+/);
    if (words.some((w) => w === q)) return 2;
    if (words.some((w) => w.startsWith(q))) return 3;
    return 4;
  };

  return games
    .filter((g) => g.title.toLowerCase().includes(q))
    .sort((a, b) => rank(a.title) - rank(b.title));
}
