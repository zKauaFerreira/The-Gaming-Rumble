import type { GamePayload } from "./types";

export function encodeGamePayload(payload: GamePayload): string {
  const json = JSON.stringify(payload);
  const b64 = btoa(unescape(encodeURIComponent(json)));
  return `gaming-rumble://${b64}`;
}

export function decodeGamePayload(raw: string): GamePayload | null {
  try {
    let b64 = raw.replace(/^gaming-rumble:\/\//, "");
    if (b64.endsWith("/")) b64 = b64.slice(0, -1);
    
    const json = decodeURIComponent(escape(atob(b64)));
    const parsed = JSON.parse(json) as GamePayload;
    if (!parsed.title || !parsed.magnet || !parsed.parts) return null;
    return parsed;
  } catch {
    return null;
  }
}

// ─── Link de exemplo para testar no navegador ─────────────────────────────────
// Abra esse link no navegador para testar o deep-link do app:
//
// gaming-rumble://eyJ0aXRsZSI6Ikh1bnRlciBYIEh1bnRlciIsImJhbm5lciI6Imh0dHBzOi8vc2hhcmVkLmFrYW1haS5zdGVhbXN0YXRpYy5jb20vc3RvcmVfaXRlbV9hc3NldHMvc3RlYW0vYXBwcy8yNjUzNzAvY2Fwc3VsZV9jb21lZG93bi5qcGciLCJwYXJ0cyI6NiwiZmlsZVNpemUiOiIxMy4yIEdCIiwibWFnbmV0IjoibWFnbmV0Oj94dD11cm46YnRpaDphYmMxMjNkZWY0NTZhYmMxMjNkZWY0NTZhYmMxMjNkZWY0NTZhYmMxJmRuPUh1bnRlciUyMFglMjBIdW50ZXImdHI9dWRwJTNBJTJGJTJGdHJhY2tlci5vcGVudHJhY2tyLm9yZyUzQTEzMzcvYW5ub3VuY2UifQ==
