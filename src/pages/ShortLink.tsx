import { useEffect, useState, useCallback } from "react";
import { useParams, Navigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { GAMES_API, findByHash, findBySlug, makeProtocolUrl, Game } from "@/lib/games";
import icon from "@/assets/icon.png";

type PageState = "loading" | "opened" | "fallback" | "error" | "not-found";

const ShortLink = () => {
  const { id } = useParams<{ id: string }>();
  const [state, setState] = useState<PageState>("loading");
  const [protocolUrl, setProtocolUrl] = useState<string>("");
  const [gameData, setGameData] = useState<Game | null>(null);
  const [copied, setCopied] = useState(false);

  const { data: games, isLoading, isError } = useQuery({
    queryKey: ["games"],
    queryFn: async () => {
      const r = await fetch(GAMES_API);
      if (!r.ok) throw new Error("Failed to fetch games");
      const json = await r.json();
      return json.downloads as Game[];
    },
  });

  const tryOpenProtocol = useCallback((url: string) => {
    window.location.href = url;
  }, []);

  useEffect(() => {
    if (isLoading) return;

    if (isError || !games || !id) {
      setState("error");
      return;
    }

    // Try finding by hash first, then by slug
    const game = findByHash(games, id) || findBySlug(games, id);

    if (!game) {
      setState("not-found");
      return;
    }

    setGameData(game);

    // Build protocol URL
    const url = makeProtocolUrl(game);
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
  }, [id, games, isLoading, isError, tryOpenProtocol]);

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

  if (state === "error") {
    return <Navigate to="/page/1" replace />;
  }

  if (state === "not-found") {
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
          <p className="text-muted-foreground mb-8">Não encontramos nenhum jogo com este ID ou slug.</p>
          <button onClick={() => window.history.back()} className="px-6 py-3 rounded-xl bg-secondary text-secondary-foreground font-medium hover:bg-secondary/80 transition-colors">← Voltar</button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className={`animate-fade-in-up bg-card border border-border rounded-2xl max-w-lg w-full shadow-2xl overflow-hidden`}>

        {gameData && (
          <div className="relative w-full">
            <img
              src={gameData.steam?.header_image}
              alt={gameData.title}
              className="w-full h-40 md:h-48 object-cover"
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = "none";
                (e.target as HTMLImageElement).parentElement?.classList.add("bg-gradient-to-br", "from-primary/20", "to-background");
              }}
            />
            <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/30 to-transparent">
              <div className="absolute bottom-3 left-4 right-4">
                <h1 className="text-lg md:text-xl font-bold text-white drop-shadow-lg leading-tight">{gameData.title}</h1>
              </div>
            </div>
          </div>
        )}

        <div className="p-6 md:p-8">
          {gameData && (
            <>
              <div className="flex justify-center gap-6 text-sm text-muted-foreground mb-4">
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
                  {gameData.files?.length ?? 1} {gameData.files?.length === 1 ? "arquivo" : "arquivos"}
                </span>
                {gameData.hoster_links && Object.keys(gameData.hoster_links).length > 0 && (
                  <span className="flex items-center gap-1.5">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244" />
                    </svg>
                    {Object.keys(gameData.hoster_links).length} {Object.keys(gameData.hoster_links).length === 1 ? "provider" : "providers"}
                  </span>
                )}
              </div>

              {/* Tags (Genres + Categories) */}
              {(gameData.steam?.genres || gameData.steam?.categories) && (
                <div className="flex flex-wrap justify-center gap-1 mb-6">
                  {gameData.steam.genres?.slice(0, 4).map((g) => (
                    <span key={g.id} className="text-[9px] px-1.5 py-0.5 rounded-md bg-secondary/30 text-muted-foreground border border-border/30">
                      {g.description}
                    </span>
                  ))}
                  {gameData.steam.categories?.slice(0, 4).map((c) => (
                    <span key={c.id} className="text-[9px] px-1.5 py-0.5 rounded-md bg-primary/5 text-primary/60 border border-primary/10">
                      {c.description}
                    </span>
                  ))}
                </div>
              )}
            </>
          )}

          {state === "loading" && (
            <div className="text-center">
              <div className="w-10 h-10 mx-auto mb-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin-slow" />
              <p className="text-lg font-medium">Buscando informações...</p>
              <p className="text-sm text-muted-foreground mt-1">Localizando jogo no dataset</p>
            </div>
          )}

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

export default ShortLink;
