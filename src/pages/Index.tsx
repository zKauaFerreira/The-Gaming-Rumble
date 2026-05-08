import { useEffect, useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

interface Game {
  title: string;
  url: string;
  page: number;
  last_update: string;
  release_date: string;
  update_info: string;
  update_date: string;
  formatted_update_date: string;
  unique_hash: string;
  fileSize: string;
  magnet: string;
  torrent_file: string;
  created_at: string;
  webdav_updated_at: string;
  files: Array<{ name: string; size: string }>;
  comment: string;
  scraped_at: string;
  steam: {
    steam_appid?: number;
    match_score?: number;
    match_via?: string;
    header_image?: string;
    short_description?: string;
    short_description_native?: string;
    price_brl?: string;
    is_free?: boolean;
    pc_requirements?: {
      minimum?: string;
      recommended?: string;
    };
    controller_support?: string;
    not_found?: boolean;
    reason?: string;
    search_url?: string;
  };
}

type SortOption = "name-asc" | "name-desc" | "date-asc" | "date-desc" | "size-asc" | "size-desc";

const ITEMS_PER_PAGE = 24;

const Index = () => {
  const [searchQuery, setSearchQuery] = useState("");
  const [sortBy, setSortBy] = useState<SortOption>("name-asc");
  const [currentPage, setCurrentPage] = useState(1);

  const { data: games = [], isLoading, error } = useQuery({
    queryKey: ["games"],
    queryFn: async () => {
      const response = await fetch("/api/get-games");
      if (!response.ok) throw new Error("Failed to fetch games");
      const data = await response.json();
      return data.downloads || [];
    },
  });

  const filteredAndSortedGames = useMemo(() => {
    let result = [...games];

    // Filter by search query
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      result = result.filter((game: Game) =>
        game.title.toLowerCase().includes(query) ||
        (game.steam?.short_description_native?.toLowerCase().includes(query))
      );
    }

    // Sort
    result.sort((a: Game, b: Game) => {
      switch (sortBy) {
        case "name-asc":
          return a.title.localeCompare(b.title);
        case "name-desc":
          return b.title.localeCompare(a.title);
        case "date-asc":
          return new Date(a.last_update || "").getTime() - new Date(b.last_update || "").getTime();
        case "date-desc":
          return new Date(b.last_update || "").getTime() - new Date(a.last_update || "").getTime();
        case "size-asc":
          return parseSize(a.fileSize) - parseSize(b.fileSize);
        case "size-desc":
          return parseSize(b.fileSize) - parseSize(a.fileSize);
        default:
          return 0;
      }
    });

    return result;
  }, [games, searchQuery, sortBy]);

  const totalPages = Math.ceil(filteredAndSortedGames.length / ITEMS_PER_PAGE);
  const paginatedGames = filteredAndSortedGames.slice(
    (currentPage - 1) * ITEMS_PER_PAGE,
    currentPage * ITEMS_PER_PAGE
  );

  const handleDownload = (magnet: string) => {
    window.open(magnet, "_blank");
  };

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 mx-auto mb-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
          <p className="text-lg font-medium">Carregando jogos...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <div className="text-center">
          <h1 className="text-2xl font-bold mb-2">Erro ao carregar jogos</h1>
          <p className="text-muted-foreground">Tente novamente mais tarde.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header with search and sort */}
      <div className="sticky top-0 z-10 bg-background/95 backdrop-blur-sm border-b border-border">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex flex-col sm:flex-row gap-4 items-center justify-between">
            <h1 className="text-2xl font-bold">Gaming Rumble</h1>
            <div className="flex flex-col sm:flex-row gap-3 w-full sm:w-auto">
              <input
                type="text"
                placeholder="Buscar jogos..."
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setCurrentPage(1);
                }}
                className="px-4 py-2 bg-secondary border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary w-full sm:w-64"
              />
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as SortOption)}
                className="px-4 py-2 bg-secondary border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="name-asc">Nome (A-Z)</option>
                <option value="name-desc">Nome (Z-A)</option>
                <option value="date-desc">Mais recentes</option>
                <option value="date-asc">Mais antigos</option>
                <option value="size-desc">Maior tamanho</option>
                <option value="size-asc">Menor tamanho</option>
              </select>
            </div>
          </div>
          <p className="text-sm text-muted-foreground mt-2">
            {filteredAndSortedGames.length} {filteredAndSortedGames.length === 1 ? "jogo encontrado" : "jogos encontrados"}
          </p>
        </div>
      </div>

      {/* Games grid */}
      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {paginatedGames.map((game: Game) => (
            <div
              key={game.unique_hash}
              className="bg-card border border-border rounded-xl overflow-hidden hover:shadow-lg transition-shadow group"
            >
              {/* Banner */}
              <div className="relative aspect-video bg-gradient-to-br from-primary/20 to-background">
                {game.steam?.header_image ? (
                  <img
                    src={game.steam.header_image}
                    alt={game.title}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center">
                    <span className="text-4xl">🎮</span>
                  </div>
                )}
                {/* Download button overlay */}
                <button
                  onClick={() => handleDownload(game.magnet)}
                  className="absolute bottom-2 right-2 w-10 h-10 bg-primary rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:brightness-110"
                  title="Baixar via magnet"
                >
                  <svg className="w-5 h-5 text-primary-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                  </svg>
                </button>
              </div>

              {/* Game info */}
              <div className="p-3">
                <h3 className="font-semibold text-sm line-clamp-2 mb-2" title={game.title}>
                  {game.title}
                </h3>
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>{game.fileSize}</span>
                  {game.steam?.price_brl && !game.steam.is_free && (
                    <span className="text-green-600">{game.steam.price_brl}</span>
                  )}
                  {game.steam?.is_free && (
                    <span className="text-green-600">Grátis</span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex justify-center items-center gap-2 mt-8">
            <button
              onClick={() => handlePageChange(currentPage - 1)}
              disabled={currentPage === 1}
              className="px-4 py-2 bg-secondary border border-border rounded-lg disabled:opacity-50 disabled:cursor-not-allowed hover:bg-secondary/80 transition-colors"
            >
              Anterior
            </button>
            <div className="flex gap-1">
              {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                let pageNum;
                if (totalPages <= 5) {
                  pageNum = i + 1;
                } else if (currentPage <= 3) {
                  pageNum = i + 1;
                } else if (currentPage >= totalPages - 2) {
                  pageNum = totalPages - 4 + i;
                } else {
                  pageNum = currentPage - 2 + i;
                }
                return (
                  <button
                    key={pageNum}
                    onClick={() => handlePageChange(pageNum)}
                    className={`px-3 py-2 rounded-lg transition-colors ${
                      currentPage === pageNum
                        ? "bg-primary text-primary-foreground"
                        : "bg-secondary hover:bg-secondary/80"
                    }`}
                  >
                    {pageNum}
                  </button>
                );
              })}
            </div>
            <button
              onClick={() => handlePageChange(currentPage + 1)}
              disabled={currentPage === totalPages}
              className="px-4 py-2 bg-secondary border border-border rounded-lg disabled:opacity-50 disabled:cursor-not-allowed hover:bg-secondary/80 transition-colors"
            >
              Próxima
            </button>
          </div>
        )}

        {/* No results */}
        {filteredAndSortedGames.length === 0 && (
          <div className="text-center py-12">
            <p className="text-lg font-medium mb-2">Nenhum jogo encontrado</p>
            <p className="text-muted-foreground">Tente ajustar sua busca.</p>
          </div>
        )}
      </div>
    </div>
  );
};

function parseSize(sizeStr: string): number {
  if (!sizeStr) return 0;
  const match = sizeStr.match(/^([\d.]+)\s*(KB|MB|GB|TB)?$/i);
  if (!match) return 0;
  const value = parseFloat(match[1]);
  const unit = (match[2] || "B").toUpperCase();
  const multipliers: Record<string, number> = {
    B: 1,
    KB: 1024,
    MB: 1024 * 1024,
    GB: 1024 * 1024 * 1024,
    TB: 1024 * 1024 * 1024 * 1024,
  };
  return value * (multipliers[unit] || 1);
}

export default Index;