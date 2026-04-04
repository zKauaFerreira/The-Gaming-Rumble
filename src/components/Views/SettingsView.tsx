import { useState, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Icon } from "../Icon";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface DriveInfo {
  name: string;
  label: string;
  free_gb: number;
  total_gb: number;
}

interface SettingsViewProps {
  defaultDrive: string;
  onDriveChange: (drive: string) => void;
}

export function SettingsView({ defaultDrive, onDriveChange }: SettingsViewProps) {
  const [drives, setDrives] = useState<DriveInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    invoke<DriveInfo[]>("list_drives").then(setDrives).finally(() => setLoading(false));
    invoke<boolean>("check_is_admin").then(setIsAdmin);
  }, []);

  async function selectDrive(d: DriveInfo) {
    try {
      await invoke("create_gaming_rumble_folder", { drive: d.name });
      localStorage.setItem("gr_default_drive", d.name);
      onDriveChange(d.name);
    } catch (e) {
      console.error(e);
    }
  }

  return (
    <main className="flex-1 flex flex-col overflow-hidden uppercase font-bold tracking-tight">
      <header className="px-8 pt-8 pb-4 flex justify-between items-start shrink-0">
        <div>
          <h2 className="text-xl text-[#e5e1e4] tracking-tighter">Configurações</h2>
          <p className="text-[9px] text-[#a4e6ff] tracking-[0.4em] mt-1 opacity-80 uppercase">Ajustes do Núcleo</p>
        </div>
        <div className={cn("flex items-center gap-2 px-3 py-1.5 rounded-2xl text-[9px] tracking-widest border border-white/5 shadow-glow", 
          isAdmin ? "bg-[#4ade80]/10 text-[#4ade80]" : "bg-[#ffb4ab]/10 text-[#ffb4ab]")}>
          <Icon name={isAdmin ? "verified_user" : "gpp_maybe"} size={13} fill={1} />
          {isAdmin ? "Privilégio Admin" : "Acesso Comum"}
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-8 pb-10 flex flex-col gap-6 custom-scrollbar scroll-smooth">
        <section className="flex flex-col gap-4">
          <div>
            <p className="text-[10px] tracking-[0.3em] text-slate-500 mb-1">UNIDADE DE DESTINO PADRÃO</p>
            <p className="text-[9px] text-slate-600 normal-case font-medium">Os jogos serão salvos em: <span className="text-[#a4e6ff] font-mono">{defaultDrive}Gaming Rumble\</span></p>
          </div>
          
          <div className="flex flex-col gap-2.5">
            {loading && <p className="text-[9px] text-slate-600 italic">Varrendo unidades...</p>}
            {drives.map((disk) => {
              const usedPct = Math.min(((disk.total_gb - disk.free_gb) / disk.total_gb) * 100, 100);
              const isSelected = defaultDrive === disk.name;
              const displayLabel = disk.label && disk.label !== disk.name ? `${disk.label} (${disk.name})` : disk.name;
              return (
                <button key={disk.name} onClick={() => selectDrive(disk)}
                  className={cn(
                    "flex items-center gap-5 p-5 rounded-2xl transition-all text-left group relative backdrop-blur-md",
                    isSelected ? "bg-white/[0.03] border border-white/10 shadow-glow-sm" : "bg-white/[0.01] border border-transparent hover:bg-white/[0.04]"
                  )}>
                  <Icon name="hard_drive" size={28} className={isSelected ? "text-[#a4e6ff]" : "text-slate-600 group-hover:text-slate-400"} />
                  <div className="flex-1 min-w-0">
                    <div className="flex justify-between items-center mb-2">
                       <span className={cn("text-sm tracking-tight", isSelected ? "text-[#e5e1e4]" : "text-slate-400")}>{displayLabel}</span>
                       <span className="text-[10px] font-mono text-slate-500">{disk.free_gb.toFixed(1)} GB de {disk.total_gb.toFixed(0)} GB</span>
                    </div>
                    <div className="w-full h-1.5 bg-[#0e0e10] rounded-full overflow-hidden shadow-inner border border-white/5">
                      <div className={cn("h-full rounded-full transition-all duration-700", isSelected ? "bg-[#a4e6ff]" : "bg-slate-700")}
                        style={{ width: `${usedPct}%` }} />
                    </div>
                  </div>
                  {isSelected && <Icon name="check_circle" size={20} fill={1} className="text-[#a4e6ff] animate-in zoom-in-50" />}
                </button>
              );
            })}
          </div>
        </section>

        <section className="bg-white/[0.02] rounded-3xl p-6 border border-white/5 flex flex-col gap-4">
           <div>
             <p className="text-[10px] tracking-[0.3em] text-slate-500 mb-2">INTEGRIDADE DO SISTEMA</p>
             <div className="flex flex-col gap-2">
               <div className="flex justify-between items-center text-[10px] py-1 border-b border-white/5">
                 <span className="text-slate-400">Protocolo</span>
                 <span className="text-[#a4e6ff] font-mono">gaming-rumble:// ATIVO</span>
               </div>
               <div className="flex justify-between items-center text-[10px] py-1 border-b border-white/5">
                 <span className="text-slate-400">Motor de Magnet</span>
                 <span className="text-[#a4e6ff] font-mono">ARIA2C_CORE v1.37.0</span>
               </div>
               <div className="flex justify-between items-center text-[10px] py-1">
                 <span className="text-slate-400">Versão do Lançador</span>
                 <span className="text-slate-500 font-mono">GR_CLIENT v1.0.0-DEVEL</span>
               </div>
             </div>
           </div>
        </section>

        <section className="flex flex-col gap-3">
           <button className="w-full h-12 rounded-xl bg-white/5 border border-white/5 text-slate-500 text-[10px] tracking-widest hover:text-[#ffb4ab] hover:bg-[#ffb4ab]/5 transition-all">
             LIMPAR CACHE DE DOWNLOADS
           </button>
           <p className="text-[8px] text-slate-700 text-center uppercase tracking-[0.5em] mt-2 italic">gaming rumble engine © 2026</p>
        </section>
      </div>
    </main>
  );
}
