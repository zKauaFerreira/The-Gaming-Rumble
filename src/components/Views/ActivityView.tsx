import { motion } from "framer-motion";
import { Icon } from "../Icon";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { DownloadState } from "../../types";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface ActivityViewProps {
  state: DownloadState | null;
  onPause?: () => void;
  onCancel?: () => void;
  onStartGame?: () => void;
  isPaused?: boolean;
}

export function ActivityView({ state, onPause, onCancel, onStartGame, isPaused }: ActivityViewProps) {
  if (!state) return (
    <div className="flex flex-col items-center gap-4">
      <Icon name="hourglass_empty" size={64} className="text-slate-600" />
      <span className="text-sm text-slate-500 tracking-widest font-medium uppercase">Nenhum Download em Andamento</span>
    </div>
  );

  const {
    payload,
    progressPercent,
    extractionPartPercent,
    speedMBs,
    eta,
    elapsedTime,
    phase,
    peers,
    seeds,
    fixOnly,
    errorMessage,
    currentPart,
    totalParts
  } = state;
  const isDone = phase === "done";
  const isExtracting = phase === "extracting";
  const isError = phase === "error";
  const extractionStatus = isExtracting
    ? `${fixOnly ? "FIX" : "PARTE"} ${Math.max(currentPart || 0, 1)}/${Math.max(totalParts || 0, 1)} • ${(extractionPartPercent ?? 0).toFixed(0)}%`
    : null;

  const errorType: "torrent" | "extraction" = errorMessage?.includes("extração") || errorMessage?.includes("extrair")
    ? "extraction"
    : "torrent";

  return (
    <main className="flex-1 flex flex-col overflow-hidden relative font-bold uppercase">
      <div className="relative w-full h-40 overflow-hidden flex-shrink-0">
        <img src={payload.banner} alt="" className="w-full h-full object-cover opacity-50" />
        <div className="absolute inset-0 bg-gradient-to-b from-[#0e0e10]/40 to-[#0e0e10]" />
        <div className="absolute inset-0 flex flex-col justify-end px-8 pb-6">
          <div className="flex items-center gap-2 mb-2">
            <div className={cn("w-1.5 h-1.5 rounded-full", isDone ? "bg-[#4ade80]" : "bg-[#a4e6ff] animate-pulse")} />
            <span className="text-[9px] tracking-[0.4em] text-[#a4e6ff] font-mono">
              {isDone ? "PROTOCOLO FINALIZADO" : isExtracting ? "REESTRUTURANDO NUCLEO" : fixOnly ? "TRANSMISSAO ATIVA (FIX)" : "TRANSMISSAO ATIVA"}
            </span>
          </div>
          <h1 className="text-4xl font-black tracking-tighter text-[#e5e1e4] leading-none truncate">{payload.title}</h1>
        </div>
      </div>

      <div className="flex-1 px-8 py-6 flex flex-col gap-6 z-10">
        <div className="flex items-end justify-between mb-1">
          <div>
            <span className={cn("text-[3.5rem] font-black font-mono leading-none text-glow",
              isError ? "text-[#ffb4ab]" : "text-[#a4e6ff]")}>
              {isError ? "ERRO" : typeof progressPercent === "number" && progressPercent > 0 ? progressPercent.toFixed(2) : "0.00"}{isError ? "" : "%"}
            </span>
            <span className="text-[10px] text-slate-500 tracking-widest ml-4">
              {isError ? "FALHA NO TORRENT" : isExtracting ? "EXTRAINDO..." : isDone ? "CONCLUIDO" : isPaused ? "PAUSADO" : typeof progressPercent === "number" && progressPercent <= 0 ? "PROCESSANDO..." : "BAIXANDO..."}
            </span>
            {extractionStatus && (
              <div className="mt-2 text-[10px] text-[#a4e6ff] tracking-[0.2em] font-mono">
                {extractionStatus}
              </div>
            )}
          </div>
          {!isDone && speedMBs > 0 && (
            <div className="flex gap-3">
              <div className="bg-[#1b1b1d] px-4 py-2 rounded-xl border border-white/5 flex flex-col items-center min-w-[72px]">
                <span className="text-[7px] tracking-widest text-slate-500 uppercase">speed</span>
                <span className="text-sm text-[#a4e6ff] font-mono">{speedMBs.toFixed(1)} <span className="text-[8px] text-slate-600">mb/s</span></span>
              </div>
              <div className="bg-[#1b1b1d] px-4 py-2 rounded-xl border border-white/5 flex flex-col items-center min-w-[72px]">
                <span className="text-[7px] tracking-widest text-slate-500 uppercase">eta</span>
                <span className="text-sm text-[#a4e6ff] font-mono">{eta ? eta.replace(/(\d+h)/g, "$1 ").replace(/(\d+m)/g, "$1 ").trim() : "--:--"}</span>
              </div>
            </div>
          )}
        </div>

        <div className="w-full h-4 bg-[#1b1b1d] rounded-full overflow-hidden border border-white/5 shadow-inner">
          <motion.div
            className={cn("h-full bg-gradient-to-r shadow-[0_0_20px_rgba(164,230,255,0.3)]", isError ? "from-[#ffb4ab] to-[#ff6b6b]" : isDone ? "from-[#4ade80] to-[#22c55e]" : "from-[#a4e6ff] to-[#01c4f0]")}
            animate={{ width: `${isError ? 100 : progressPercent}%` }}
            transition={{ type: "spring", stiffness: 45, damping: 15 }}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          {isError ? (
            <>
              <div className="col-span-2 bg-[#ffb4ab]/10 border border-[#ffb4ab]/20 rounded-2xl p-4 flex flex-col gap-1 items-center">
                <span className="text-[10px] text-[#ffb4ab] tracking-widest uppercase">
                  {errorType === "extraction" ? "Falha na Extracao" : "Torrent Indisponivel"}
                </span>
                <span className="text-[8px] text-slate-400">
                  {errorType === "extraction"
                    ? "Arquivo corrompido ou invalido. Verifique a fonte do magnet link."
                    : "Nenhum peer/seed disponivel. Tente mais tarde."}
                </span>
              </div>
              {onCancel && (
                <div className="col-span-2">
                  <button onClick={onCancel} className="w-full h-16 bg-[#ffb4ab]/5 rounded-2xl border border-[#ffb4ab]/10 text-[#ffb4ab] text-[10px] tracking-[0.2em] flex items-center justify-center gap-3 hover:bg-[#ffb4ab]/15 transition-all group">
                    <Icon name="cancel" size={20} className="group-hover:scale-110 transition-transform" /> CANCELAR
                  </button>
                </div>
              )}
            </>
          ) : (
            <>
              <div className="bg-[#1b1b1d] p-5 rounded-2xl border border-white/5 flex flex-col gap-1">
                <span className="text-[9px] tracking-widest text-slate-500 uppercase">Tempo Decorrido</span>
                <span className="text-xl text-[#e5e1e4] font-mono leading-none">{elapsedTime}</span>
              </div>
              <div className="bg-[#1b1b1d] p-5 rounded-2xl border border-white/5 flex flex-col gap-1">
                <span className="text-[9px] tracking-widest text-slate-500 uppercase">Peers / Seeds</span>
                <span className="text-xl text-[#e5e1e4] font-mono leading-none">{peers || 0} / {seeds || 0}</span>
              </div>
            </>
          )}
        </div>

        {!isDone && !isError && (
          <div className="mt-auto mb-4 flex gap-4">
            <button onClick={onPause} className="flex-1 h-16 bg-white/[0.03] rounded-2xl border border-white/5 text-[10px] tracking-[0.2em] flex items-center justify-center gap-3 hover:bg-white/[0.08] transition-all group">
              <Icon name="pause_circle" size={20} className="group-hover:scale-110 transition-transform" /> PAUSAR
            </button>
            <button onClick={onCancel} className="flex-1 h-16 bg-[#ffb4ab]/5 rounded-2xl border border-[#ffb4ab]/10 text-[#ffb4ab] text-[10px] tracking-[0.2em] flex items-center justify-center gap-3 hover:bg-[#ffb4ab]/15 transition-all group">
              <Icon name="cancel" size={20} className="group-hover:scale-110 transition-transform" /> CANCELAR
            </button>
          </div>
        )}

        {isDone && onStartGame && (
          <button onClick={onStartGame} className={cn("mt-auto mb-4 h-20 font-black rounded-3xl shadow-[0_15px_40px_rgba(74,222,128,0.15)] flex items-center justify-center gap-4 group italic",
            fixOnly
              ? "bg-gradient-to-br from-[#a4e6ff] to-[#0188ca] text-[#002d38]"
              : "bg-gradient-to-br from-[#4ade80] to-[#22c55e] text-[#002d13]"
          )}>
            <span className="tracking-[0.2em] text-xl">{fixOnly ? "ABRIR PASTA" : "INICIAR JOGO"}</span>
            <Icon name={fixOnly ? "folder_open" : "play_arrow"} size={32} fill={1} />
          </button>
        )}
      </div>
    </main>
  );
}
