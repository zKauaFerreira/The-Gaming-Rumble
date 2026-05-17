import { useEffect, useState, useCallback, useMemo } from "react";
import { type Game } from "./GameCatalog";
import { makeProtocolUrl, toSlug, getGameDate } from "@/lib/games";
import translationsData from "@/lib/translations.json";

function ensureProtocol(url: string) {
  if (!url) return "";
  if (/^https?:\/\//i.test(url)) return url;
  if (url.startsWith("//")) return `https:${url}`;
  return `https://${url}`;
}

export function GameModal({ game, onClose }: { game: Game; onClose: () => void }) {
  const [closing, setClosing] = useState(false);
  const [copied, setCopied] = useState(false);

  const shareUrl = `${window.location.origin}/game/${toSlug(game.title)}?download`;

  const handleShare = useCallback(() => {
    navigator.clipboard.writeText(shareUrl).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [shareUrl]);

  /* ── Lock body scroll ── */
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);

  const handleClose = useCallback(() => {
    setClosing(true);
    setTimeout(onClose, 180);
  }, [onClose]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") handleClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [handleClose]);

  const req = game.steam?.pc_requirements;

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm ${
        closing ? "animate-backdrop-out" : "animate-backdrop-in"
      }`}
      onClick={handleClose}
    >
      <div
        className={`bg-card border border-border rounded-2xl max-w-2xl w-full max-h-[88vh] overflow-y-auto scrollbar-thin shadow-2xl ${
          closing ? "animate-scale-out" : "animate-scale-in"
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header image */}
        <div className="relative shrink-0">
          {game.steam?.header_image ? (
            <img
              src={game.steam.header_image}
              alt={game.title}
              className="w-full h-52 object-cover rounded-t-2xl"
            />
          ) : (
            <div className="w-full h-52 bg-gradient-to-br from-primary/20 to-background rounded-t-2xl" />
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-card via-card/20 to-transparent rounded-t-2xl" />
          <button
            onClick={handleClose}
            className="absolute top-3 right-3 w-8 h-8 rounded-full bg-black/60 flex items-center justify-center hover:bg-black/80 transition-colors duration-150"
          >
            <XIcon className="w-4 h-4 text-white" />
          </button>
        </div>

        <div className="p-6 space-y-5">
          {/* Title + chips */}
          <div>
            <h2 className="text-2xl font-bold mb-3">{game.title}</h2>
            <div className="flex flex-wrap gap-2">
              {getGameDate(game) && (
                <Chip icon={<CalendarIcon className="w-3.5 h-3.5" />}>
                  {getGameDate(game)}
                </Chip>
              )}
              <Chip icon={<HardDriveIcon className="w-3.5 h-3.5" />}>
                {game.fileSize}
              </Chip>
              <Chip icon={<FolderIcon className="w-3.5 h-3.5" />}>
                {game.files?.length ?? 1} arquivo{(game.files?.length ?? 1) !== 1 ? "s" : ""}
              </Chip>
              {game.hoster_links && Object.keys(game.hoster_links).length > 0 && (
                <Chip icon={<LinkIcon className="w-3.5 h-3.5" />}>
                  {Object.keys(game.hoster_links).length} provider{Object.keys(game.hoster_links).length !== 1 ? "s" : ""}
                </Chip>
              )}
              {game.steam?.price_brl && (
                <Chip icon={<TagIcon className="w-3.5 h-3.5" />} highlight>
                  {game.steam.is_free ? "Grátis" : game.steam.price_brl}
                </Chip>
              )}
              {game.steam?.controller_support && (
                <Chip icon={<GamepadIcon className="w-3.5 h-3.5" />}>
                  Controle {game.steam.controller_support === "full" ? "total" : "parcial"}
                </Chip>
              )}
            </div>

            {/* Tags (Genres + Categories) - Collapsible & Subtle */}
            {(game.steam?.genres || game.steam?.categories) && (
              <TagList
                genres={game.steam.genres || []}
                categories={game.steam.categories || []}
              />
            )}
          </div>

          {/* Description */}
          {game.steam?.short_description && (
            <Section title="Sobre o jogo">
              <p className="text-sm leading-relaxed">{game.steam.short_description}</p>
            </Section>
          )}

          {/* Requirements */}
          {(req?.minimum || req?.recommended) && (
            <Section title="Requisitos do sistema">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {req?.minimum && (
                  <div className="bg-secondary/40 rounded-xl p-4">
                    <p className="text-xs font-semibold text-muted-foreground mb-3 uppercase tracking-wider">
                      Mínimos
                    </p>
                    <RequirementsText text={req.minimum} />
                  </div>
                )}
                {req?.recommended && (
                  <div className="bg-secondary/40 rounded-xl p-4">
                    <p className="text-xs font-semibold text-muted-foreground mb-3 uppercase tracking-wider">
                      Recomendados
                    </p>
                    <RequirementsText text={req.recommended} />
                  </div>
                )}
              </div>
            </Section>
          )}

          {/* Files */}
          {game.files?.length > 0 && (
            <Section title="Arquivos incluídos">
              <CollapsibleList
                items={game.files}
                renderItem={(f, i) => (
                  <div
                    key={i}
                    className="flex justify-between text-xs bg-secondary/30 rounded-lg px-3 py-2"
                  >
                    <span className="text-muted-foreground truncate mr-4">{f.name}</span>
                    <span className="shrink-0 font-medium">{f.size}</span>
                  </div>
                )}
              />
            </Section>
          )}

          {/* Hoster Links */}
          {game.hoster_links && Object.keys(game.hoster_links).length > 0 && (
            <Section title="Links de Download">
              <CollapsibleList
                items={Object.entries(game.hoster_links)}
                initialCount={6}
                containerClassName="grid grid-cols-1 sm:grid-cols-2 gap-2 items-start"
                renderItem={([hoster, links]) => (
                  <HosterSection key={hoster} hoster={hoster} links={links} />
                )}
              />
            </Section>
          )}

          {/* Download + Share */}
          <div className="flex gap-2">
            <button
              onClick={() => { window.location.href = makeProtocolUrl(game); }}
              className="flex-1 px-6 py-3.5 rounded-xl bg-primary text-primary-foreground font-semibold text-base hover:brightness-110 active:scale-[0.98] transition-all duration-150 flex items-center justify-center gap-2"
            >
              <DownloadIcon className="w-5 h-5" />
              Baixar no Gaming Rumble
            </button>
            <button
              onClick={handleShare}
              title="Copiar link de compartilhamento"
              className={`shrink-0 w-12 rounded-xl border transition-all duration-150 flex items-center justify-center active:scale-95 ${
                copied
                  ? "bg-primary/15 border-primary/40 text-primary"
                  : "bg-secondary border-border text-muted-foreground hover:border-primary/40 hover:text-foreground"
              }`}
            >
              {copied ? (
                <CheckIcon className="w-4 h-4" />
              ) : (
                <ShareIcon className="w-4 h-4" />
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Collapsible Helpers ── */

function TagList({
  genres,
  categories,
}: {
  genres: { id: string | number; description: string }[];
  categories: { id: number; description: string }[];
}) {
  const [expanded, setExpanded] = useState(false);
  const allTags = useMemo(() => {
    return [
      ...genres.map((g) => ({ ...g, type: "genre" })),
      ...categories.map((c) => ({ ...c, type: "category" })),
    ];
  }, [genres, categories]);

  const initialCount = 8;
  const showButton = allTags.length > initialCount;
  const visibleTags = expanded ? allTags : allTags.slice(0, initialCount);

  return (
    <div className="mt-3">
      <div className="flex flex-wrap gap-1">
        {visibleTags.map((tag) => (
          <span
            key={`${tag.type}-${tag.id}`}
            className={`text-[9px] px-1.5 py-0.5 rounded-md border transition-colors ${
              tag.type === "genre"
                ? "bg-secondary/20 text-muted-foreground/80 border-border/30"
                : "bg-primary/5 text-primary/60 border-primary/10"
            }`}
          >
            {tag.description}
          </span>
        ))}
        {showButton && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-[9px] px-1.5 py-0.5 rounded-md bg-secondary/40 text-muted-foreground hover:bg-secondary/60 transition-colors border border-border/40 font-medium"
          >
            {expanded ? "Menos" : `+${allTags.length - initialCount}`}
          </button>
        )}
      </div>
    </div>
  );
}

function CollapsibleList<T>({
  items,
  renderItem,
  initialCount = 5,
}: {
  items: T[];
  renderItem: (item: T, index: number) => React.ReactNode;
  initialCount?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const showButton = items.length > initialCount;
  const visibleItems = expanded ? items : items.slice(0, initialCount);

  return (
    <div className="space-y-1">
      {visibleItems.map(renderItem)}
      {showButton && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full py-2 text-[10px] font-bold uppercase tracking-widest text-primary hover:text-primary/80 transition-colors flex items-center justify-center gap-1.5 bg-primary/5 rounded-lg border border-primary/10 mt-1"
        >
          {expanded ? "Ver menos" : `Ver mais (${items.length - initialCount})`}
          <ChevronDownIcon className={`w-3 h-3 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`} />
        </button>
      )}
    </div>
  );
}

function HosterSection({ hoster, links }: { hoster: string; links: any[] }) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="space-y-1 bg-secondary/20 rounded-xl p-1.5 border border-border/40">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between px-2 py-1.5 hover:bg-secondary/40 rounded-lg transition-colors group"
      >
        <span className="text-[10px] font-bold text-muted-foreground/70 uppercase tracking-tighter group-hover:text-foreground transition-colors">
          {hoster} <span className="ml-1 opacity-50">({links.length})</span>
        </span>
        <ChevronDownIcon className={`w-3 h-3 text-muted-foreground/50 transition-transform duration-200 ${isExpanded ? "rotate-180" : ""}`} />
      </button>
      
      {isExpanded && (
        <div className="space-y-1 animate-in fade-in slide-in-from-top-1 duration-200">
          <CollapsibleList
            items={links}
            renderItem={(link, i) => (
              <a
                key={i}
                href={ensureProtocol(link.direct_link || link.u)}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 px-3 py-2 bg-secondary/40 hover:bg-secondary/60 border border-border/50 rounded-lg text-xs transition-colors group"
              >
                <LinkIcon className="w-3 h-3 text-muted-foreground group-hover:text-primary transition-colors" />
                <span className="truncate flex-1">{link.file_name || link.n || `Link ${i + 1}`}</span>
                <ExternalIcon className="w-3 h-3 text-muted-foreground/50 opacity-0 group-hover:opacity-100 transition-opacity" />
              </a>
            )}
          />
        </div>
      )}
    </div>
  );
}

/* ── Translations ── */

const _entries = Object.entries(translationsData.phrase_replacements)
  .sort((a, b) => b[0].length - a[0].length); // longest first to avoid partial replacements

function escRx(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function applyTranslations(text: string): string {
  let result = text;
  for (const [en, pt] of _entries) {
    result = result.replace(new RegExp(escRx(en), "gi"), pt);
  }
  return result;
}

/* ── Requirements renderer ── */

const ALLOWED_LABELS = [
  /^(os|operating system|sistema operativ[ao])/i,
  /^(processor|processador|cpu)/i,
  /^(memory|mem[oó]ria|ram)/i,
  /^(graphics?(\s+card)?|placa\s+(gr[aá]fica|de\s+v[ií]deo)|gpu|video\s+card)/i,
  /^(storage|espa[cç]o\s+(no|em|livre\s+no)?\s*disco|disco\s+r[ií]gido|hard\s+(drive|disk))/i,
];

function isAllowedLabel(label: string) {
  return ALLOWED_LABELS.some((rx) => rx.test(label.trim()));
}

function RequirementsText({ text }: { text: string }) {
  const cleaned = text
    .replace(/^Mínimos:\n\n/, "")
    .replace(/^Recomendados:\n\n/, "")
    .replace(/^Requer um sistema operativo e processador de 64 bits\n\n/, "")
    .replace(/^Requires a 64-bit processor and operating system\n\n/i, "")
    .trim();

  const translated = applyTranslations(cleaned);
  const lines = translated.split("\n").filter((l) => l.trim());

  return (
    <div className="space-y-1.5">
      {lines.map((line, i) => {
        const match = line.match(/^([^:]+?)(\s*\*?):\s*(.+)$/);
        if (!match || !isAllowedLabel(match[1])) return null;
        return (
          <div key={i} className="text-xs leading-relaxed">
            <span className="font-semibold text-foreground/90">
              {match[1].trim()}{match[2]}:
            </span>{" "}
            <span className="text-muted-foreground">{match[3]}</span>
          </div>
        );
      })}
    </div>
  );
}

/* ── Sub-components ── */

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
        {title}
      </h3>
      {children}
    </div>
  );
}

function Chip({
  icon,
  children,
  highlight,
}: {
  icon: React.ReactNode;
  children: React.ReactNode;
  highlight?: boolean;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border ${
        highlight
          ? "bg-primary/10 border-primary/30 text-primary font-medium"
          : "bg-secondary/50 border-border text-muted-foreground"
      }`}
    >
      {icon}
      {children}
    </span>
  );
}

/* ── Icons ── */

function XIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
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

function CalendarIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
    </svg>
  );
}

function HardDriveIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 7.5l-.625 10.632a2.25 2.25 0 01-2.247 2.118H6.622a2.25 2.25 0 01-2.247-2.118L3.75 7.5M10 11.25h4M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z" />
    </svg>
  );
}

function FolderIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" />
    </svg>
  );
}

function TagIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.568 3H5.25A2.25 2.25 0 003 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 005.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 009.568 3z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 6h.008v.008H6V6z" />
    </svg>
  );
}

function GamepadIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 8a4 4 0 014-4h8a4 4 0 014 4v5a4 4 0 01-4 4H8a4 4 0 01-4-4V8z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 10v2m-1-1h2" />
      <circle cx="15" cy="10" r="0.75" fill="currentColor" stroke="none" />
      <circle cx="16.5" cy="11.5" r="0.75" fill="currentColor" stroke="none" />
    </svg>
  );
}

function ShareIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M7.217 10.907a2.25 2.25 0 100 2.186m0-2.186c.18.324.283.696.283 1.093s-.103.77-.283 1.093m0-2.186l9.566-5.314m-9.566 7.5l9.566 5.314m0 0a2.25 2.25 0 103.935 2.186 2.25 2.25 0 00-3.935-2.186zm0-12.814a2.25 2.25 0 103.933-2.185 2.25 2.25 0 00-3.933 2.185z" />
    </svg>
  );
}

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
    </svg>
  );
}

function LinkIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244" />
    </svg>
  );
}

function ExternalIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
    </svg>
  );
}

function ChevronDownIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
    </svg>
  );
}
