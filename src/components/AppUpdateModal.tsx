import { Icon } from "./Icon";

export interface AppUpdateModalState {
  visible: boolean;
  configured: boolean;
  stage: "idle" | "available" | "downloading" | "installing" | "error";
  currentVersion: string;
  nextVersion: string;
  notes: string;
  progressPercent: number;
  downloadedBytes: number;
  totalBytes: number | null;
  errorMessage: string;
}

interface AppUpdateModalProps {
  state: AppUpdateModalState;
  onInstall: () => void;
}

function formatBytes(bytes: number) {
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export function AppUpdateModal({ state, onInstall }: AppUpdateModalProps) {
  if (!state.visible || !state.configured) return null;

  const isBusy = state.stage === "downloading" || state.stage === "installing";
  const primaryLabel =
    state.stage === "available"
      ? "Atualizar agora"
      : state.stage === "downloading"
        ? "Baixando atualizacao..."
        : state.stage === "installing"
          ? "Instalando atualizacao..."
          : state.stage === "error"
            ? "Tentar novamente"
            : "Atualizando...";

  return (
    <div className="absolute inset-0 z-50 flex items-center justify-center bg-[#050507]/84 backdrop-blur-md">
      <div className="w-[min(560px,calc(100%-2rem))] rounded-[28px] border border-white/10 bg-[#101013] shadow-[0_30px_100px_rgba(0,0,0,0.55)] p-8 flex flex-col gap-6">
        <div className="flex items-start gap-4">
          <div className="h-16 w-16 rounded-2xl bg-[#a4e6ff]/10 border border-[#a4e6ff]/20 flex items-center justify-center text-[#a4e6ff] shrink-0">
            <Icon
              name={state.stage === "installing" ? "system_update_alt" : "download"}
              size={32}
              fill={1}
            />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[10px] uppercase tracking-[0.35em] text-[#a4e6ff] font-black">Atualizacao obrigatoria</p>
            <h2 className="mt-2 text-3xl font-black uppercase tracking-tight text-white">Nova versao disponivel</h2>
            <p className="mt-2 text-sm text-slate-400">
              {state.currentVersion} para {state.nextVersion}
            </p>
          </div>
        </div>

        <div className="rounded-2xl border border-white/6 bg-white/[0.03] p-5">
          <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.22em] text-slate-400">
            <span>
              {state.stage === "available" && "Pronto para atualizar"}
              {state.stage === "downloading" && "Baixando pacote"}
              {state.stage === "installing" && "Instalando"}
              {state.stage === "error" && "Falha na atualizacao"}
            </span>
            <span className="text-[#a4e6ff]">{state.progressPercent.toFixed(0)}%</span>
          </div>

          <div className="mt-4 h-3 rounded-full bg-[#1b1b1d] overflow-hidden border border-white/5">
            <div
              className="h-full bg-gradient-to-r from-[#a4e6ff] to-[#01c4f0] transition-[width] duration-200"
              style={{ width: `${state.progressPercent}%` }}
            />
          </div>

          <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
            <span>
              {state.totalBytes
                ? `${formatBytes(state.downloadedBytes)} / ${formatBytes(state.totalBytes)}`
                : state.stage === "installing"
                  ? "Aplicando instalador..."
                  : "Preparando update..."}
            </span>
            <span>{isBusy ? "Nao feche o aplicativo" : "Atualizacao detectada na inicializacao"}</span>
          </div>
        </div>

        {state.notes && (
          <div className="rounded-2xl border border-white/6 bg-[#0b0b0d] p-5">
            <p className="text-[10px] uppercase tracking-[0.25em] text-slate-500 font-black">Notas da versao</p>
            <p className="mt-3 text-sm leading-6 text-slate-300 whitespace-pre-wrap max-h-36 overflow-auto custom-scrollbar">
              {state.notes}
            </p>
          </div>
        )}

        {state.errorMessage && (
          <div className="rounded-2xl border border-red-400/15 bg-red-400/8 p-4 text-sm text-red-200">
            {state.errorMessage}
          </div>
        )}

        <button
          onClick={onInstall}
          disabled={isBusy}
          className="h-16 rounded-2xl bg-[#a4e6ff] text-[#042430] font-black uppercase tracking-[0.22em] text-sm disabled:opacity-70 disabled:cursor-not-allowed cursor-pointer transition-all hover:brightness-110"
        >
          {primaryLabel}
        </button>
      </div>
    </div>
  );
}
