import { useState, useEffect } from "react";
import { getVersion } from "@tauri-apps/api/app";
import { invoke } from "@tauri-apps/api/core";
import { openUrl } from "@tauri-apps/plugin-opener";
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

interface SystemStatus {
  protocol: string;
  protocolActive: boolean;
  aria2Version: string;
  sevenZipVersion: string;
  launcherVersion: string;
}

interface DefenderStatus {
  available: boolean;
}

interface SettingsViewProps {
  defaultDrive: string;
  onDriveChange: (drive: string) => void;
  driveSelectionLocked?: boolean;
}

const INITIAL_SYSTEM_STATUS: SystemStatus = {
  protocol: "gaming-rumble://",
  protocolActive: true,
  aria2Version: "Detectando...",
  sevenZipVersion: "Detectando...",
  launcherVersion: "Detectando..."
};

const DISABLE_DEFENDER_ON_START_KEY = "gr_disable_defender_on_start";
const GITHUB_REPO_URL = "https://github.com/zKauaFerreira/The-Gaming-Rumble/tree/main";

function GitHubIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={className} fill="currentColor">
      <path d="M12 2C6.477 2 2 6.596 2 12.264c0 4.534 2.865 8.38 6.839 9.737.5.096.682-.223.682-.496 0-.245-.009-.894-.014-1.755-2.782.617-3.369-1.395-3.369-1.395-.455-1.187-1.11-1.503-1.11-1.503-.908-.637.069-.624.069-.624 1.004.072 1.532 1.057 1.532 1.057.893 1.57 2.341 1.116 2.91.853.091-.666.349-1.116.635-1.373-2.22-.259-4.555-1.14-4.555-5.072 0-1.12.389-2.036 1.029-2.753-.103-.26-.446-1.303.098-2.716 0 0 .84-.277 2.75 1.052A9.355 9.355 0 0 1 12 6.836a9.31 9.31 0 0 1 2.504.349c1.909-1.329 2.748-1.052 2.748-1.052.546 1.413.202 2.456.1 2.716.64.717 1.027 1.633 1.027 2.753 0 3.942-2.339 4.81-4.566 5.064.359.318.679.946.679 1.907 0 1.376-.012 2.485-.012 2.822 0 .276.18.596.688.495C19.138 20.64 22 16.796 22 12.264 22 6.596 17.523 2 12 2Z" />
    </svg>
  );
}

export function SettingsView({ defaultDrive, onDriveChange, driveSelectionLocked = false }: SettingsViewProps) {
  const [drives, setDrives] = useState<DriveInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);
  const [systemStatus, setSystemStatus] = useState<SystemStatus>(INITIAL_SYSTEM_STATUS);
  const [disableDefenderOnStart, setDisableDefenderOnStart] = useState(
    () => localStorage.getItem(DISABLE_DEFENDER_ON_START_KEY) !== "false"
  );
  const [defenderBusy, setDefenderBusy] = useState(false);
  const [defenderAvailable, setDefenderAvailable] = useState(true);
  const [deleteAllStep, setDeleteAllStep] = useState<0 | 1 | 2>(0);
  const [deleteAllBusy, setDeleteAllBusy] = useState(false);

  useEffect(() => {
    invoke<DriveInfo[]>("list_drives").then(setDrives).finally(() => setLoading(false));
    invoke<boolean>("check_is_admin").then(setIsAdmin);
    invoke<DefenderStatus>("get_defender_status")
      .then((status) => {
        setDefenderAvailable(status.available);
        if (!status.available) {
          setDisableDefenderOnStart(false);
          localStorage.setItem(DISABLE_DEFENDER_ON_START_KEY, "false");
        }
      })
      .catch(() => {
        setDefenderAvailable(false);
        setDisableDefenderOnStart(false);
        localStorage.setItem(DISABLE_DEFENDER_ON_START_KEY, "false");
      });

    Promise.all([
      invoke<Omit<SystemStatus, "launcherVersion">>("get_system_status"),
      getVersion().catch(() => "Desconhecida")
    ])
      .then(([status, launcherVersion]) => {
        setSystemStatus({
          ...status,
          launcherVersion: `v${launcherVersion}`
        });
      })
      .catch(() => {
        setSystemStatus((prev) => ({
          ...prev,
          launcherVersion: "Desconhecida"
        }));
      });
  }, []);

  async function selectDrive(drive: DriveInfo) {
    if (driveSelectionLocked) return;

    try {
      await invoke("create_gaming_rumble_folder", { drive: drive.name });
      localStorage.setItem("gr_default_drive", drive.name);
      onDriveChange(drive.name);
    } catch (error) {
      console.error(error);
    }
  }

  async function handleToggleDefender() {
    if (!defenderAvailable || defenderBusy) return;

    const nextValue = !disableDefenderOnStart;
    setDisableDefenderOnStart(nextValue);
    localStorage.setItem(DISABLE_DEFENDER_ON_START_KEY, String(nextValue));
    setDefenderBusy(true);

    try {
      await invoke("set_defender_realtime_monitoring", { disabled: nextValue });
    } catch (error) {
      console.warn("[DEFENDER] Failed to update realtime monitoring:", error);
    } finally {
      setDefenderBusy(false);
    }
  }

  async function handleDeleteAllGames() {
    if (driveSelectionLocked || deleteAllBusy) return;

    setDeleteAllBusy(true);
    try {
      await invoke("delete_all_games", { drive: defaultDrive });
      setDeleteAllStep(0);
    } catch (error) {
      console.warn("[LIBRARY] Failed to delete all games:", error);
    } finally {
      setDeleteAllBusy(false);
    }
  }

  return (
    <>
      <main className="flex-1 flex flex-col overflow-hidden uppercase font-bold tracking-tight">
        <header className="px-8 pt-8 pb-4 flex justify-between items-start shrink-0">
          <div>
            <h2 className="text-xl text-[#e5e1e4] tracking-tighter">Configurações</h2>
            <p className="text-[9px] text-[#a4e6ff] tracking-[0.4em] mt-1 opacity-80 uppercase">Ajustes do Núcleo</p>
          </div>
          <div
            className={cn(
              "flex items-center gap-2 px-3 py-1.5 rounded-2xl text-[9px] tracking-widest border border-white/5 shadow-glow",
              isAdmin ? "bg-[#4ade80]/10 text-[#4ade80]" : "bg-[#ffb4ab]/10 text-[#ffb4ab]"
            )}
          >
            <Icon name={isAdmin ? "verified_user" : "gpp_maybe"} size={13} fill={1} />
            {isAdmin ? "Privilégio Admin" : "Acesso Comum"}
          </div>
        </header>

        <div className="flex-1 overflow-y-auto px-8 pb-10 flex flex-col gap-6 custom-scrollbar scroll-smooth">
          <section className="flex flex-col gap-4">
            <div>
              <p className="text-[10px] tracking-[0.3em] text-slate-500 mb-1">UNIDADE DE DESTINO PADRÃO</p>
              <p className="text-[9px] text-slate-600 normal-case font-medium">
                Os jogos serão salvos em: <span className="text-[#a4e6ff] font-mono">{defaultDrive}Gaming Rumble\</span>
              </p>
              {driveSelectionLocked && (
                <p className="mt-2 text-[9px] text-[#ffb4ab] tracking-[0.15em] uppercase">
                  Troca de disco bloqueada enquanto houver download ou instalação em andamento.
                </p>
              )}
            </div>

            <div className="flex flex-col gap-2.5">
              {loading && <p className="text-[9px] text-slate-600 italic">Varrendo unidades...</p>}
              {drives.map((disk) => {
                const usedPct = disk.total_gb > 0
                  ? Math.min(((disk.total_gb - disk.free_gb) / disk.total_gb) * 100, 100)
                  : 0;
                const isSelected = defaultDrive === disk.name;
                const displayLabel = disk.label && disk.label !== disk.name ? `${disk.label} (${disk.name})` : disk.name;

                return (
                  <button
                    key={disk.name}
                    onClick={() => selectDrive(disk)}
                    disabled={driveSelectionLocked}
                    className={cn(
                      "flex items-center gap-5 p-5 rounded-2xl transition-all text-left group relative backdrop-blur-md cursor-pointer",
                      driveSelectionLocked && "opacity-55 cursor-not-allowed",
                      isSelected ? "bg-white/[0.03] border border-white/10 shadow-glow-sm" : "bg-white/[0.01] border border-transparent hover:bg-white/[0.04]"
                    )}
                  >
                    <Icon name="hard_drive" size={28} className={isSelected ? "text-[#a4e6ff]" : "text-slate-600 group-hover:text-slate-400"} />
                    <div className="flex-1 min-w-0">
                      <div className="flex justify-between items-center mb-2">
                        <span className={cn("text-sm tracking-tight", isSelected ? "text-[#e5e1e4]" : "text-slate-400")}>{displayLabel}</span>
                        <span className="text-[10px] font-mono text-slate-500">{disk.free_gb.toFixed(1)} GB de {disk.total_gb.toFixed(0)} GB</span>
                      </div>
                      <div className="w-full h-1.5 bg-[#0e0e10] rounded-full overflow-hidden shadow-inner border border-white/5">
                        <div
                          className={cn("h-full rounded-full transition-all duration-700", isSelected ? "bg-[#a4e6ff]" : "bg-slate-700")}
                          style={{ width: `${usedPct}%` }}
                        />
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
                  <span className="text-[#a4e6ff] font-mono">{systemStatus.protocol} / {systemStatus.protocolActive ? "ATIVO" : "INATIVO"}</span>
                </div>
                <div className="flex justify-between items-center text-[10px] py-1 border-b border-white/5">
                  <span className="text-slate-400">Motor de Magnet</span>
                  <span className="text-[#a4e6ff] font-mono">{systemStatus.aria2Version}</span>
                </div>
                <div className="flex justify-between items-center text-[10px] py-1 border-b border-white/5">
                  <span className="text-slate-400">Motor de Extração</span>
                  <span className="text-[#a4e6ff] font-mono">{systemStatus.sevenZipVersion}</span>
                </div>
                <div className="flex justify-between items-center text-[10px] py-1">
                  <span className="text-slate-400">Versão do Lançador</span>
                  <span className="text-[#a4e6ff] font-mono">{systemStatus.launcherVersion}</span>
                </div>
              </div>
            </div>
          </section>

          <section className="bg-white/[0.02] rounded-3xl p-6 border border-white/5 flex flex-col gap-4">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <p className="text-[10px] tracking-[0.3em] text-slate-500 mb-2">WINDOWS DEFENDER</p>
                <h3 className="text-sm text-[#e5e1e4] tracking-tight">Desabilitar ao iniciar o aplicativo</h3>
                <p className="mt-2 text-[9px] text-slate-500 normal-case font-medium leading-5">
                  Aplica <span className="font-mono text-[#a4e6ff]">Set-MpPreference -DisableRealtimeMonitoring</span> automaticamente.
                </p>
                {!defenderAvailable && (
                  <p className="mt-2 text-[9px] text-slate-500 normal-case font-medium">
                    Microsoft Defender indisponível neste sistema. A opção fica bloqueada automaticamente.
                  </p>
                )}
                {!isAdmin && (
                  <p className="mt-2 text-[9px] text-[#ffb4ab] normal-case font-medium">
                    Requer execução como administrador para surtir efeito no Windows Defender.
                  </p>
                )}
              </div>

              <button
                type="button"
                onClick={handleToggleDefender}
                disabled={defenderBusy || !defenderAvailable}
                className={cn(
                  "relative mt-1 h-9 w-16 shrink-0 rounded-full border transition-all",
                  defenderAvailable && "cursor-pointer",
                  !defenderAvailable && "cursor-not-allowed opacity-45",
                  disableDefenderOnStart && defenderAvailable
                    ? "border-[#a4e6ff]/40 bg-[#a4e6ff]/15"
                    : "border-white/10 bg-white/[0.04]",
                  defenderBusy && "opacity-70 cursor-wait"
                )}
                title="Desabilitar Windows Defender ao iniciar"
              >
                <span
                  className={cn(
                    "absolute top-1 h-7 w-7 rounded-full transition-all",
                    disableDefenderOnStart && defenderAvailable
                      ? "left-8 bg-[#a4e6ff] shadow-[0_0_20px_rgba(164,230,255,0.35)]"
                      : "left-1 bg-slate-500"
                  )}
                />
              </button>
            </div>
          </section>

          <section className="flex flex-col gap-3">
            <button className="w-full h-12 rounded-xl bg-white/5 border border-white/5 text-slate-500 text-[10px] tracking-widest hover:text-[#ffb4ab] hover:bg-[#ffb4ab]/5 transition-all cursor-pointer">
              LIMPAR CACHE DE DOWNLOADS
            </button>
            <button
              onClick={() => setDeleteAllStep(1)}
              disabled={driveSelectionLocked || deleteAllBusy}
              className={cn(
                "w-full h-12 rounded-xl border text-[10px] tracking-widest transition-all",
                driveSelectionLocked || deleteAllBusy
                  ? "bg-[#ffb4ab]/10 border-[#ffb4ab]/10 text-[#ffb4ab]/50 cursor-not-allowed"
                  : "bg-[#ffb4ab]/10 border-[#ffb4ab]/20 text-[#ffb4ab] hover:bg-[#ffb4ab]/18 cursor-pointer"
              )}
            >
              DELETAR TODOS OS JOGOS
            </button>
            <div className="flex justify-center pt-2">
              <button
                onClick={() => openUrl(GITHUB_REPO_URL).catch(() => {})}
                className="flex h-10 w-10 items-center justify-center rounded-full text-slate-600 transition-all hover:text-[#a4e6ff] hover:bg-white/[0.03] cursor-pointer"
                title="Abrir repositório no GitHub"
              >
                <GitHubIcon className="h-5 w-5" />
              </button>
            </div>
          </section>
        </div>
      </main>

      {deleteAllStep > 0 && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center bg-[#050507]/86 backdrop-blur-md px-4">
          <div className="w-[min(480px,100%)] rounded-[28px] border border-white/10 bg-[#101013] p-6 shadow-[0_30px_100px_rgba(0,0,0,0.55)]">
            <p className="text-[10px] font-black uppercase tracking-[0.35em] text-[#ffb4ab]">Ação crítica</p>
            <h3 className="mt-3 text-2xl font-black tracking-tight text-white">
              {deleteAllStep === 1 ? "Tem certeza?" : "Tem certeza mesmo?"}
            </h3>
            <p className="mt-3 text-sm leading-6 text-slate-400 normal-case font-medium">
              {deleteAllStep === 1
                ? `Isso vai apagar todos os jogos instalados em ${defaultDrive}Gaming Rumble e limpar a biblioteca dessa unidade.`
                : "Essa ação remove pastas dos jogos e não pode ser desfeita."}
            </p>

            <div className="mt-6 flex gap-3">
              <button
                onClick={() => setDeleteAllStep(0)}
                disabled={deleteAllBusy}
                className="flex-1 h-12 rounded-2xl border border-white/10 bg-white/[0.03] text-slate-300 text-[10px] tracking-[0.2em] transition-all hover:bg-white/[0.06] cursor-pointer disabled:cursor-default disabled:opacity-60"
              >
                NÃO
              </button>
              {deleteAllStep === 1 ? (
                <button
                  onClick={() => setDeleteAllStep(2)}
                  disabled={deleteAllBusy}
                  className="flex-1 h-12 rounded-2xl border border-[#ffb4ab]/20 bg-[#ffb4ab]/10 text-[#ffb4ab] text-[10px] tracking-[0.2em] transition-all hover:bg-[#ffb4ab]/18 cursor-pointer disabled:cursor-default disabled:opacity-60"
                >
                  SIM
                </button>
              ) : (
                <button
                  onClick={handleDeleteAllGames}
                  disabled={deleteAllBusy}
                  className="flex-1 h-12 rounded-2xl border border-[#ff6b6b]/30 bg-[#ff6b6b]/15 text-[#ffb4ab] text-[10px] tracking-[0.2em] transition-all hover:bg-[#ff6b6b]/22 cursor-pointer disabled:cursor-wait disabled:opacity-60"
                >
                  {deleteAllBusy ? "APAGANDO..." : "SIM, APAGAR TUDO"}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
