import { useEffect, useState, useCallback } from "react";
import { unzlibSync } from "fflate";
import icon from "@/assets/icon.png";

type PageState = "loading" | "opened" | "fallback" | "error" | "invalid-payload";

interface GameData {
  title: string;
  banner: string;
  parts: number;
  fileSize: string;
  magnet: string;
}

const SHORT_TO_FULL: Record<string, keyof GameData> = {
  t: "title",
  b: "banner",
  p: "parts",
  s: "fileSize",
  m: "magnet",
};

function decodeData(encoded: string): GameData | null {
  try {
    // 1. Base64 url-safe → bytes
    const b64 = encoded.replace(/-/g, "+").replace(/_/g, "/");
    const binaryStr = atob(b64);
    const bytes = new Uint8Array(binaryStr.length);
    for (let i = 0; i < binaryStr.length; i++) {
      bytes[i] = binaryStr.charCodeAt(i);
    }

    // 2. Decompress zlib
    const decompressed = unzlibSync(bytes);

    // 3. JSON parse
    const str = new TextDecoder().decode(decompressed);
    const raw = JSON.parse(str);

    if (typeof raw !== "object" || raw === null) return null;

    // 4. Map short keys to full keys
    const data: Record<string, unknown> = {};
    for (const [short, full] of Object.entries(SHORT_TO_FULL)) {
      if (!(short in raw) || raw[short] === undefined || raw[short] === "") return null;
      data[full] = raw[short];
    }

    return data as unknown as GameData;
  } catch {
    return null;
  }
}

const Index = () => {
  const [state, setState] = useState<PageState>("loading");
  const [protocolUrl, setProtocolUrl] = useState<string>("");
  const [gameData, setGameData] = useState<GameData | null>(null);
  const [copied, setCopied] = useState(false);

  const tryOpenProtocol = useCallback((url: string) => {
    window.location.href = url;
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const data = params.get("data");

    if (!data || data.trim() === "") {
      setState("error");
      return;
    }

    const decoded = decodeData(data);
    if (!decoded) {
      setState("invalid-payload");
      return;
    }

    setGameData(decoded);

    // Rebuild full JSON → base64 for protocol
    const fullJson = JSON.stringify(decoded);
    const b64 = btoa(fullJson);
    const url = `gaming-rumble://${b64}`;
    setProtocolUrl(url);
    tryOpenProtocol(url);

    let fallbackTimer: ReturnType<typeof setTimeout>;
    let didOpen = false;

    const markOpened = () => {
      if (!didOpen) {
        didOpen = true;
        clearTimeout(fallbackTimer);
        setState("opened");
      }
    };

    const handleVisibility = () => { if (document.hidden) markOpened(); };
    const handleBlur = () => markOpened();

    document.addEventListener("visibilitychange", handleVisibility);
    window.addEventListener("blur", handleBlur);

    fallbackTimer = setTimeout(() => {
      if (!didOpen) setState("fallback");
    }, 1500);

    return () => {
      document.removeEventListener("visibilitychange", handleVisibility);
      window.removeEventListener("blur", handleBlur);
      clearTimeout(fallbackTimer);
    };
  }, [tryOpenProtocol]);

  // Auto-close tab after 5s on success
  useEffect(() => {
    if (state !== "opened") return;
    const timer = setTimeout(() => { window.close(); }, 5000);
    return () => clearTimeout(timer);
  }, [state]);

  const copyMagnet = useCallback(() => {
    if (!gameData?.magnet) return;
    navigator.clipboard.writeText(gameData.magnet).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [gameData]);

  // Error: no data param
  if (state === "error") {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="animate-fade-in-up bg-card border border-border rounded-2xl p-8 md:p-12 max-w-md w-full text-center shadow-2xl">
          <img src={icon} alt="Gaming Rumble" className="w-16 h-16 mx-auto mb-6 rounded-2xl" />
          <div className="w-14 h-14 mx-auto mb-5 rounded-full bg-destructive/10 flex items-center justify-center">
            <svg className="w-7 h-7 text-destructive" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold mb-2">Link inválido</h1>
          <p className="text-muted-foreground mb-8">O link que você acessou é inválido ou incompleto. Verifique e tente novamente.</p>
          <button onClick={() => window.history.back()} className="px-6 py-3 rounded-xl bg-secondary text-secondary-foreground font-medium hover:bg-secondary/80 transition-colors">← Voltar</button>
        </div>
      </div>
    );
  }

  // Error: invalid payload
  if (state === "invalid-payload") {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="animate-fade-in-up bg-card border border-border rounded-2xl p-8 md:p-12 max-w-md w-full text-center shadow-2xl">
          <img src={icon} alt="Gaming Rumble" className="w-16 h-16 mx-auto mb-6 rounded-2xl" />
          <div className="w-14 h-14 mx-auto mb-5 rounded-full bg-destructive/10 flex items-center justify-center">
            <svg className="w-7 h-7 text-destructive" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M18.364 18.364A9 9 0 0 0 5.636 5.636m12.728 12.728A9 9 0 0 1 5.636 5.636m12.728 12.728L5.636 5.636" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold mb-2">Jogo não encontrado</h1>
          <p className="text-muted-foreground mb-8">Os dados do jogo estão incompletos ou corrompidos. Solicite um novo link.</p>
          <button onClick={() => window.history.back()} className="px-6 py-3 rounded-xl bg-secondary text-secondary-foreground font-medium hover:bg-secondary/80 transition-colors">← Voltar</button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className={`animate-fade-in-up bg-card border border-border rounded-2xl max-w-lg w-full shadow-2xl overflow-hidden`}>

        {/* Banner — always visible when gameData exists */}
        {gameData && (
          <div className="relative w-full">
            <img
              src={gameData.banner}
              alt={gameData.title}
              className="w-full h-40 md:h-48 object-cover"
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = "none";
                (e.target as HTMLImageElement).parentElement?.classList.add("bg-gradient-to-br", "from-primary/20", "to-background");
              }}
            />
            {/* Overlay gradient + title */}
            <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/30 to-transparent">
              <div className="absolute bottom-3 left-4 right-4">
                <h1 className="text-lg md:text-xl font-bold text-white drop-shadow-lg leading-tight">{gameData.title}</h1>
              </div>
            </div>
          </div>
        )}

        <div className="p-6 md:p-8">
          {/* Size & Files — centered */}
          {gameData && (
            <div className="flex justify-center gap-6 text-sm text-muted-foreground mb-5">
              <span className="flex items-center gap-1.5">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 7.5l-.625 10.632a2.25 2.25 0 01-2.247 2.118H6.622a2.25 2.25 0 01-2.247-2.118L3.75 7.5m8.25 3v6.75m0 0l-3-3m3 3l3-3M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z" />
                </svg>
                {gameData.fileSize}
              </span>
              <span className="flex items-center gap-1.5">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                </svg>
                {gameData.parts} {gameData.parts === 1 ? "arquivo" : "arquivos"}
              </span>
            </div>
          )}

          {/* Loading */}
          {state === "loading" && (
            <div className="text-center">
              <div className="w-10 h-10 mx-auto mb-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin-slow" />
              <p className="text-lg font-medium">Abrindo seu jogo...</p>
              <p className="text-sm text-muted-foreground mt-1">Redirecionando para o Gaming Rumble</p>
            </div>
          )}

          {/* Opened */}
          {state === "opened" && (
            <div className="text-center">
              <div className="w-12 h-12 mx-auto mb-3 rounded-full flex items-center justify-center" style={{ backgroundColor: "hsl(var(--success) / 0.15)" }}>
                <svg className="w-6 h-6 animate-check-pop" style={{ color: "hsl(var(--success))" }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                </svg>
              </div>
              <p className="text-base font-medium text-foreground">App aberto!</p>
              <p className="text-xs text-muted-foreground mt-1">Esta aba será fechada automaticamente em instantes...</p>
            </div>
          )}

          {/* Fallback buttons */}
          {state === "fallback" && (
            <div className="space-y-3">
              <button
                onClick={() => tryOpenProtocol(protocolUrl)}
                className="w-full px-6 py-3.5 rounded-xl bg-primary text-primary-foreground font-semibold text-base hover:brightness-110 active:scale-[0.98] transition-all"
              >
                Abrir no App
              </button>
              <button
                onClick={copyMagnet}
                className="w-full px-6 py-3 rounded-xl bg-secondary text-secondary-foreground font-medium hover:bg-secondary/80 active:scale-[0.98] transition-all flex items-center justify-center gap-2"
              >
                {copied ? (
                  <>
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                    </svg>
                    Copiado!
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9.75a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184" />
                    </svg>
                    Copiar Magnet
                  </>
                )}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Index;
