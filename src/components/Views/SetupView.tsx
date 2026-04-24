import { useState, useEffect, useCallback, useMemo } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Icon } from "../Icon";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { GamePayload } from "../../types";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface SetupViewProps {
  payload: GamePayload;
  defaultDrive: string;
  onStart: (installPath: string) => void;
}

function parseSizeToGB(sizeStr: string): number {
  const match = sizeStr.match(/([\d.]+)\s*(GB|MB|TB|B)/i);
  if (!match) return 0;
  const val = parseFloat(match[1]);
  const unit = match[2].toUpperCase();
  if (unit === "TB") return val * 1024;
  if (unit === "GB") return val;
  if (unit === "MB") return val / 1024;
  return val / (1024 * 1024 * 1024);
}

function parseSizeGB(str: string): number {
  const match = str.match(/([\d.]+)\s*GB/i);
  return match ? parseFloat(match[1]) : 0;
}

export function SetupView({ payload, defaultDrive, onStart, onDownloadFixOnly }: SetupViewProps & { onDownloadFixOnly?: (path: string) => void }) {
  const [path, setPath] = useState(`${defaultDrive}Gaming Rumble\\${payload.title}`);
  const [diskFree, setDiskFree] = useState("...");

  useEffect(() => {
    setPath(`${defaultDrive}Gaming Rumble\\${payload.title}`);
  }, [defaultDrive, payload.title]);

  const fetchDisk = useCallback(() => {
    invoke<string>("get_disk_space", { path }).then(setDiskFree).catch(() => setDiskFree("N/A"));
  }, [path]);

  useEffect(() => {
    fetchDisk();
  }, [fetchDisk]);

  // Calculate required space: download size ~1.5x for extraction overhead,
  // but since the script cleans rars during extraction, use ~1.3x as buffer
  const { hasSpace, shortfall } = useMemo(() => {
    const fileGB = parseSizeToGB(payload.fileSize);
    const freeGB = parseSizeGB(diskFree);
    const required = fileGB * 1.35; // 35% buffer for extraction + overhead
    return {
      diskFreeGB: freeGB,
      requiredGB: required,
      hasSpace: freeGB >= required,
      shortfall: Math.max(0, required - freeGB)
    };
  }, [payload.fileSize, diskFree]);

  return (
    <main className="flex-1 flex flex-col overflow-hidden relative">
      <div className="absolute -top-1/4 -right-1/4 w-[500px] h-[500px] bg-[#a4e6ff]/5 rounded-full blur-[100px] pointer-events-none" />

      <div className="relative w-full h-40 overflow-hidden flex-shrink-0">
        <img src={payload.banner} alt={payload.title} className="w-full h-full object-cover opacity-60" />
        <div className="absolute inset-0 bg-gradient-to-b from-transparent to-[#0e0e10]" />
        <div className="absolute inset-0 flex flex-col justify-end px-8 pb-6">
          <span className="text-[8px] font-bold uppercase tracking-[0.4em] text-[#a4e6ff] font-mono mb-2 text-glow">REQUISITANDO ACESSO AO NÚCLEO</span>
          <h1 className="text-4xl font-black tracking-tighter text-[#e5e1e4] leading-none uppercase">{payload.title}</h1>
        </div>
      </div>

      <div className="flex-1 px-8 py-2 flex flex-col gap-6 z-10 font-bold uppercase">
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-[#1b1b1d] p-5 rounded-2xl border border-white/5 flex flex-col gap-1 shadow-2xl">
            <span className="text-[9px] tracking-widest text-slate-500">Partes + 1 Fix</span>
            <span className="text-2xl text-[#e5e1e4] font-mono leading-none tracking-tight">
              {payload.parts} + 1
            </span>
          </div>
          <div className="bg-[#1b1b1d] p-5 rounded-2xl border border-white/5 flex flex-col gap-1 shadow-2xl">
            <span className="text-[9px] tracking-widest text-slate-500">Peso Total</span>
            <span className="text-2xl text-[#e5e1e4] font-mono leading-none tracking-tight">{payload.fileSize}</span>
          </div>
          <div className="bg-[#1b1b1d] p-5 rounded-2xl border border-white/5 flex flex-col gap-1 shadow-2xl">
            <span className="text-[9px] tracking-widest text-slate-500">Espaço em Disco</span>
            <span className="text-2xl text-[#e5e1e4] font-mono leading-none tracking-tight">{diskFree}</span>
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <label className={cn("text-[9px] tracking-widest ml-1 transition-colors",
            !hasSpace && diskFree !== "..." && diskFree !== "N/A"
              ? "text-[#ffb4ab]"
              : "text-slate-500")}>
            {!hasSpace && diskFree !== "..." && diskFree !== "N/A"
              ? "Escolha outro destino"
              : "Destino da Operação"}
          </label>
          {!hasSpace && diskFree !== "..." && diskFree !== "N/A" ? (
            <div className="bg-[#ffb4ab]/10 border border-[#ffb4ab]/20 rounded-2xl flex items-center px-5 h-16 gap-3">
              <Icon name="warning" size={20} className="text-[#ffb4ab]" />
              <span className="text-[10px] text-[#ffb4ab] font-mono tracking-tight">
                Espaço insuficiente — precisa de mais {shortfall < 1 ? (shortfall * 1024).toFixed(0) + " MB" : shortfall.toFixed(1) + " GB"}
              </span>
            </div>
          ) : (
            <div className="flex gap-2">
              <div className="flex-1 bg-[#1b1b1d] rounded-2xl flex items-center px-5 h-16 border border-white/10 focus-within:border-[#a4e6ff]/40 shadow-inner group transition-all">
                <Icon name="folder_open" size={24} className="text-slate-500 mr-4 group-hover:text-[#a4e6ff] transition-colors" />
                <input className="bg-transparent border-none focus:outline-none text-[13px] text-[#e5e1e4] w-full font-mono tracking-tight cursor-not-allowed"
                  spellCheck={false} value={path} onChange={() => {}} readOnly />
              </div>
            </div>
          )}
          {hasSpace && <p className="text-[8px] text-slate-600 font-medium normal-case tracking-wide px-1 italic">Dica: O instalador será extraído e destruído após a conclusão automática.</p>}
        </div>

        <button
          onClick={() => hasSpace && onStart(path)}
          onContextMenu={(e) => {
            e.preventDefault();
            if (hasSpace && onDownloadFixOnly) onDownloadFixOnly(path);
          }}
          title={onDownloadFixOnly ? "Esquerdo: Baixar + Extrair | Direito: Baixar Fix e abrir pasta" : ""}
          disabled={!hasSpace}
          className={cn(
            "w-full h-20 font-black rounded-3xl flex items-center justify-center gap-4 group mt-auto mb-6 transition-all tracking-[0.2em] text-xl italic",
            hasSpace
              ? "bg-gradient-to-br from-[#a4e6ff] to-[#0188ca] text-[#002d38] hover:shadow-[0_20px_50px_rgba(164,230,255,0.3)] active:scale-[0.97] cursor-pointer shadow-[0_15px_40px_rgba(164,230,255,0.15)]"
              : "bg-[#ffb4ab]/20 text-[#ffb4ab] shadow-[0_15px_40px_rgba(255,180,171,0.2)] cursor-not-allowed border border-[#ffb4ab]/20"
          )}
        >
          {!hasSpace ? (
            <>
              <Icon name="warning" size={32} /> SEM ESPAÇO
            </>
          ) : (
            <>
              <span>BAIXAR</span>
              <Icon name="bolt" size={32} fill={1} className="group-hover:scale-125 transition-transform" />
            </>
          )}
        </button>
      </div>
    </main>
  );
}
