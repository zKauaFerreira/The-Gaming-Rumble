import { Icon } from "../Icon";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { getCurrentWindow } from "@tauri-apps/api/window";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface HeaderProps {
  currentView: string;
  onViewChange: (view: any) => void;
  onLogoClick: () => void;
}

export function Header({ currentView, onViewChange, onLogoClick }: HeaderProps) {
  const win = getCurrentWindow();

  const handleDrag = (e: React.MouseEvent) => {
    if (e.target instanceof HTMLElement && e.target.closest('button')) return;
    win.startDragging();
  };

  return (
    <header className="h-20 flex items-center px-8 bg-[#131315]/90 backdrop-blur-3xl border-b border-white/5 flex-shrink-0 uppercase font-black z-30" onMouseDown={handleDrag}>
      {/* Logo - esquerda */}
      <img src="/logo.svg" alt="GR" className="w-10 h-10 cursor-pointer" onClick={onLogoClick} />

      {/* Tabs - centro */}
      <nav className="flex-1 flex items-center justify-center gap-2">
        {[
          { id: "library", label: "Biblioteca", icon: "sports_esports" },
          { id: "activity", label: "Atividade", icon: "downloading" }
        ].map(t => (
          <button
            key={t.id}
            onClick={() => onViewChange(t.id)}
            className={cn(
              "px-5 h-11 text-[11px] tracking-[0.3em] transition-all rounded-2xl flex items-center gap-3 cursor-pointer",
              currentView === t.id ? "text-[#a4e6ff] bg-white/5 shadow-inner border border-white/5" : "text-slate-500 hover:text-[#e5e1e4] hover:bg-white/5"
            )}
          >
            <Icon name={t.icon} size={18} fill={currentView === t.id ? 1 : 0} />
            {t.label}
          </button>
        ))}
      </nav>

      {/* Settings + Minimize + Close - direita */}
      <div className="flex items-center gap-1">
        <button
          onClick={() => onViewChange(currentView === 'settings' ? 'library' : 'settings')}
          className={cn(
            "p-3 rounded-2xl transition-all border border-transparent cursor-pointer",
            currentView === 'settings' ? "text-[#a4e6ff] bg-white/10 border-white/10 shadow-glow-sm" : "text-slate-500 hover:text-[#a4e6ff]"
          )}
        >
          <Icon name="settings" size={20} fill={currentView === 'settings' ? 1 : 0} />
        </button>

        {/* Minimize button */}
        <button
          onClick={() => win.minimize()}
          className="p-3 rounded-2xl text-slate-500 hover:text-[#a4e6ff] hover:bg-white/10 transition-all cursor-pointer flex items-center justify-center"
        >
          <Icon name="remove" size={20} />
        </button>

        {/* Close button */}
        <button
          onClick={() => win.close()}
          className="p-3 rounded-2xl text-slate-500 hover:text-red-400 hover:bg-red-400/10 transition-all cursor-pointer"
        >
          <Icon name="close" size={20} />
        </button>
      </div>
    </header>
  );
}
