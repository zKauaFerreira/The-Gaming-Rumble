import {
  useState,
  useEffect,
  useRef,
  useLayoutEffect,
  useMemo,
  useCallback,
} from "react";
import { useParams, useSearchParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import icon from "@/assets/icon.png";
import { GameModal } from "./GameModal";
import {
  type Game,
  type SortId,
  GAMES_API,
  toSlug,
  findBySlug,
  sortGames,
  searchGames,
  encodeGameForDataUrl,
  makeProtocolUrl,
} from "@/lib/games";

// Re-export types consumed by GameModal
export type { Game };
export type { GameFile } from "@/lib/games";

const GAMES_PER_PAGE = 24;

type SortOption = { id: SortId; label: string; Icon: React.FC<{ className?: string }> };

const SORT_OPTIONS: SortOption[] = [
  { id: "az",       label: "A → Z",   Icon: SortAscIcon },
  { id: "za",       label: "Z → A",   Icon: SortDescIcon },
  { id: "newest",   label: "Recente", Icon: ClockIcon },
  { id: "oldest",   label: "Antigo",  Icon: HistoryIcon },
  { id: "largest",  label: "Maior",   Icon: WeightUpIcon },
  { id: "smallest", label: "Menor",   Icon: WeightDownIcon },
];

export function GameCatalog() {
  const { page: pageParam, slug } = useParams<{ page?: string; slug?: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const isDownload = searchParams.has("download");

  /* ── Init page from URL so first render is correct ── */
  const [page, setPage] = useState<number>(() => {
    const p = pageParam ? parseInt(pageParam) : 1;
    return isNaN(p) || p < 1 ? 1 : p;
  });
  const [sort, setSort] = useState<SortId | null>(null);
  const [search, setSearch] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [selectedGame, setSelectedGame] = useState<Game | null>(null);
  const [scrolled, setScrolled] = useState(false);
  const [headerH, setHeaderH] = useState(56);

  const headerRef = useRef<HTMLElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  /* ── Fetch games (cached via QueryClient) ── */
  const { data, isLoading, isError } = useQuery({
    queryKey: ["games"],
    queryFn: async () => {
      const r = await fetch(GAMES_API);
      return r.json() as Promise<{ downloads: Game[] }>;
    },
  });
  const games = useMemo(() => data?.downloads ?? [], [data]);

  /* ── Derived data — must come before effects that reference them ── */
  const processed = useMemo(
    () => (search.trim() ? searchGames(games, search) : sortGames(games, sort)),
    [games, search, sort]
  );
  const totalPages = Math.ceil(processed.length / GAMES_PER_PAGE);
  const paginated = processed.slice((page - 1) * GAMES_PER_PAGE, page * GAMES_PER_PAGE);

  /* ── Sync page from URL; clamp to totalPages ── */
  useEffect(() => {
    if (!pageParam) return;
    const p = parseInt(pageParam);
    if (isNaN(p) || p < 1) {
      navigate("/page/1", { replace: true });
    } else if (totalPages > 0 && p > totalPages) {
      navigate(`/page/${totalPages}`, { replace: true });
    } else {
      setPage(p);
    }
  }, [pageParam, totalPages, navigate]);

  /* ── Handle /game/:slug?download → encode & redirect to deep-link ── */
  useEffect(() => {
    if (!isDownload || !slug || games.length === 0) return;
    const game = findBySlug(games, slug);
    if (game) navigate(`/?data=${encodeGameForDataUrl(game)}`, { replace: true });
    else navigate("/page/1", { replace: true });
  }, [isDownload, slug, games, navigate]);

  /* ── Auto-open modal for /game/:slug ── */
  useEffect(() => {
    if (!slug || isDownload || games.length === 0) return;
    const game = findBySlug(games, slug);
    setSelectedGame(game ?? null);
  }, [slug, isDownload, games]);

  /* ── Scroll to top instantly on page change ── */
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [page]);

  /* ── Fixed header scroll detection ── */
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 80);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  /* ── Measure header height for spacer ── */
  useLayoutEffect(() => {
    if (!headerRef.current) return;
    const ro = new ResizeObserver(() => {
      setHeaderH(headerRef.current?.getBoundingClientRect().height ?? 56);
    });
    ro.observe(headerRef.current);
    return () => ro.disconnect();
  }, []);

  /* ── Focus search on open ── */
  useEffect(() => {
    if (searchOpen) searchRef.current?.focus();
  }, [searchOpen]);

  /* ── Actions ── */
  const handleSearch = (v: string) => {
    setSearch(v);
    if (page !== 1) {
      setPage(1);
      navigate("/page/1");
    }
  };

  const handleSort = (id: SortId) => {
    setSort((prev) => (prev === id ? null : id));
    if (page !== 1) {
      setPage(1);
      navigate("/page/1");
    }
  };

  const changePage = (newPage: number) => {
    setPage(newPage);
    navigate(`/page/${newPage}`);
  };

  const openModal = useCallback(
    (game: Game) => {
      navigate(`/game/${toSlug(game.title)}`);
      setSelectedGame(game);
    },
    [navigate]
  );

  const closeModal = useCallback(() => {
    setSelectedGame(null);
    navigate(`/page/${page}`);
  }, [page, navigate]);

  /* ── Pagination page numbers ── */
  const pageNumbers = useMemo(() => {
    const delta = 2;
    const start = Math.max(1, Math.min(page - delta, totalPages - delta * 2));
    const end = Math.min(totalPages, start + delta * 2);
    return Array.from({ length: Math.max(0, end - start + 1) }, (_, i) => start + i);
  }, [page, totalPages]);

  /* ── Render states ── */
  if (isLoading || (isDownload && slug)) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center animate-fade-in-up">
          <div className="w-10 h-10 border-2 border-primary/30 border-t-primary rounded-full animate-spin-slow mx-auto mb-4" />
          <p className="text-sm text-muted-foreground">
            {isDownload ? "Preparando download..." : "Carregando catálogo..."}
          </p>
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="text-center animate-fade-in-up">
          <p className="text-destructive font-medium mb-4">Erro ao carregar o catálogo.</p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 rounded-lg bg-secondary text-sm hover:bg-secondary/80 transition-colors"
          >
            Tentar novamente
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      {/* ── Fixed floating header ── */}
      <header ref={headerRef} className="fixed top-0 left-0 right-0 z-40 px-3 pt-3 pb-1.5">
        <div
          className={`flex items-center gap-2 px-3 rounded-2xl border border-border bg-card/90 backdrop-blur-md transition-all duration-300 ${
            scrolled
              ? "py-2 shadow-2xl shadow-black/50"
              : "py-2.5 shadow-xl shadow-black/25"
          }`}
        >
          {/* Logo + title */}
          <div className="flex items-center gap-2 shrink-0 cursor-pointer" onClick={() => { setPage(1); navigate("/page/1"); }}>
            <img
              src={icon}
              alt="GR"
              className={`rounded-xl shrink-0 transition-all duration-300 ${
                scrolled ? "w-7 h-7" : "w-8 h-8"
              }`}
            />
            <span className="text-sm font-semibold leading-none whitespace-nowrap">
              Gaming Rumble{" "}
              <span className="text-muted-foreground font-normal">
                ({games.length.toLocaleString()})
              </span>
            </span>
          </div>

          {/* Sort pills — horizontally scrollable, centered */}
          <div className="flex items-center justify-center gap-1.5 overflow-x-auto scrollbar-none flex-1 min-w-0 py-0.5">
            {SORT_OPTIONS.map(({ id, label, Icon }) => (
              <SortPill
                key={id}
                active={sort === id}
                Icon={Icon}
                onClick={() => handleSort(id)}
              >
                {label}
              </SortPill>
            ))}
          </div>

          {/* Right: count + search icon — pills never move */}
          <div className="flex items-center gap-1.5 shrink-0 relative">
            {/* Input absolutely positioned: expands left over pills, doesn't shift layout */}
            <div
              className="absolute right-full mr-2 top-1/2 -translate-y-1/2 overflow-hidden transition-all duration-300"
              style={{
                width: searchOpen ? 200 : 0,
                opacity: searchOpen ? 1 : 0,
                pointerEvents: searchOpen ? "auto" : "none",
              }}
            >
              <input
                ref={searchRef}
                value={search}
                onChange={(e) => handleSearch(e.target.value)}
                onBlur={() => { if (!search) setSearchOpen(false); }}
                onKeyDown={(e) => {
                  if (e.key === "Escape") { handleSearch(""); setSearchOpen(false); }
                }}
                placeholder="Buscar jogo..."
                className="w-[200px] px-3 py-1.5 rounded-lg bg-card border border-border text-sm outline-none"
              />
            </div>

            <button
              onClick={() => {
                if (search) { handleSearch(""); setSearchOpen(false); }
                else setSearchOpen(true);
              }}
              className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-secondary/70 transition-colors shrink-0"
            >
              {search ? (
                <XIcon className="w-4 h-4 text-muted-foreground" />
              ) : (
                <SearchIcon className="w-4 h-4 text-muted-foreground" />
              )}
            </button>
          </div>
        </div>
      </header>

      {/* Spacer that matches header height */}
      <div
        aria-hidden
        style={{ height: headerH, transition: "height 300ms ease" }}
      />

      {/* ── Content ── */}
      <main className="p-4 md:p-8 max-w-screen-2xl mx-auto">
        {paginated.length === 0 ? (
          <div className="text-center py-24 text-muted-foreground animate-fade-in-up">
            Nenhum jogo encontrado.
          </div>
        ) : (
          <div
            key={`${page}-${sort ?? "none"}-${search}`}
            className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-3 md:gap-4"
          >
            {paginated.map((game, i) => (
              <GameCard
                key={game.unique_hash || game.title}
                game={game}
                index={i}
                onExpand={() => openModal(game)}
              />
            ))}
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex flex-wrap items-center justify-center gap-2 mt-10">
            <button
              onClick={() => changePage(Math.max(1, page - 1))}
              disabled={page === 1}
              className="px-3 py-2 rounded-lg bg-card border border-border text-sm disabled:opacity-30 hover:bg-secondary transition-colors"
            >
              ← Anterior
            </button>

            {pageNumbers[0] > 1 && (
              <>
                <button
                  onClick={() => changePage(1)}
                  className="w-9 h-9 rounded-lg text-sm bg-card border border-border hover:bg-secondary transition-colors"
                >
                  1
                </button>
                {pageNumbers[0] > 2 && (
                  <span className="text-muted-foreground text-sm px-1">…</span>
                )}
              </>
            )}

            {pageNumbers.map((p) => (
              <button
                key={p}
                onClick={() => changePage(p)}
                className={`w-9 h-9 rounded-lg text-sm font-medium transition-colors ${
                  p === page
                    ? "bg-primary text-primary-foreground"
                    : "bg-card border border-border hover:bg-secondary"
                }`}
              >
                {p}
              </button>
            ))}

            {pageNumbers[pageNumbers.length - 1] < totalPages && (
              <>
                {pageNumbers[pageNumbers.length - 1] < totalPages - 1 && (
                  <span className="text-muted-foreground text-sm px-1">…</span>
                )}
                <button
                  onClick={() => changePage(totalPages)}
                  className="w-9 h-9 rounded-lg text-sm bg-card border border-border hover:bg-secondary transition-colors"
                >
                  {totalPages}
                </button>
              </>
            )}

            <button
              onClick={() => changePage(Math.min(totalPages, page + 1))}
              disabled={page === totalPages}
              className="px-3 py-2 rounded-lg bg-card border border-border text-sm disabled:opacity-30 hover:bg-secondary transition-colors"
            >
              Próximo →
            </button>
          </div>
        )}
      </main>

      {selectedGame && (
        <GameModal game={selectedGame} onClose={closeModal} />
      )}
    </div>
  );
}

/* ── Sort pill ── */

function SortPill({
  active,
  Icon,
  onClick,
  children,
}: {
  active: boolean;
  Icon: React.FC<{ className?: string }>;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium shrink-0 transition-all duration-200 ${
        active
          ? "bg-primary text-primary-foreground shadow-sm shadow-primary/30"
          : "bg-secondary/50 border border-border text-muted-foreground hover:border-primary/40 hover:text-foreground"
      }`}
    >
      <Icon className="w-3 h-3" />
      {children}
    </button>
  );
}

/* ── Game card ── */

function GameCard({
  game,
  index,
  onExpand,
}: {
  game: Game;
  index: number;
  onExpand: () => void;
}) {
  const [imgError, setImgError] = useState(false);

  const download = (e: React.MouseEvent) => {
    e.stopPropagation();
    window.location.href = makeProtocolUrl(game);
  };

  return (
    <div
      className="animate-card-in bg-card border border-border rounded-xl overflow-hidden flex flex-col group hover:border-primary/50 transition-colors hover:shadow-lg hover:shadow-primary/10"
      style={{ animationDelay: `${Math.min(index, 12) * 35}ms` }}
    >
      {/* Banner — clicável para abrir modal */}
      <div
        className="relative w-full h-28 bg-secondary overflow-hidden cursor-pointer"
        onClick={onExpand}
      >
        {!imgError && game.steam?.header_image ? (
          <img
            src={game.steam.header_image}
            alt={game.title}
            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="w-full h-full bg-gradient-to-br from-primary/20 to-background flex items-center justify-center p-2">
            <span className="text-xs text-muted-foreground text-center line-clamp-3 leading-tight">
              {game.title}
            </span>
          </div>
        )}
        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors duration-300" />
        {/* Expand hint icon */}
        <div className="absolute top-1.5 right-1.5 w-7 h-7 rounded-lg bg-black/60 backdrop-blur-sm flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200">
          <ChevronUpIcon className="w-3.5 h-3.5 text-white" />
        </div>
      </div>

      <div className="p-3 flex flex-col gap-1.5 flex-1">
        <h3 className="text-sm font-semibold leading-tight line-clamp-2">{game.title}</h3>
        {game.steam?.short_description && (
          <p className="text-xs text-muted-foreground line-clamp-2 flex-1 leading-relaxed">
            {game.steam.short_description}
          </p>
        )}
        <div className="flex items-center justify-between mt-auto pt-1.5">
          <span className="text-xs text-muted-foreground">{game.fileSize}</span>
          <button
            onClick={download}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:brightness-110 active:scale-95 transition-all duration-150"
          >
            <DownloadIcon className="w-3 h-3" />
            Baixar
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Icons ── */

function SearchIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <circle cx="11" cy="11" r="6" />
      <path strokeLinecap="round" d="M21 21l-4.35-4.35" />
    </svg>
  );
}

function XIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}

function ChevronUpIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 15.75l7.5-7.5 7.5 7.5" />
    </svg>
  );
}

function DownloadIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
    </svg>
  );
}

function SortAscIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round">
      <line x1="2" y1="4.5" x2="7"  y2="4.5" />
      <line x1="2" y1="7.5" x2="9"  y2="7.5" />
      <line x1="2" y1="10.5" x2="12" y2="10.5" />
    </svg>
  );
}

function SortDescIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round">
      <line x1="2" y1="4.5" x2="12" y2="4.5" />
      <line x1="2" y1="7.5" x2="9"  y2="7.5" />
      <line x1="2" y1="10.5" x2="7"  y2="10.5" />
    </svg>
  );
}

function ClockIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <circle cx="12" cy="12" r="8" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l2.5 2" />
    </svg>
  );
}

function HistoryIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l-2 2" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.05 11a9 9 0 1 0 .5-3M3 5v4l3.5.5" />
    </svg>
  );
}

function WeightUpIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 17l6-6 4 4 5-7" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M17 7h3v3" />
    </svg>
  );
}

function WeightDownIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 7l6 6 4-4 5 7" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M17 17h3v-3" />
    </svg>
  );
}
