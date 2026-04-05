import { useState, useEffect, useCallback } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { invoke } from "@tauri-apps/api/core";

import { listen } from "@tauri-apps/api/event";

// Components
import { Header } from "./components/Layout/Header";
import { Footer } from "./components/Layout/Footer";
import { LibraryView } from "./components/Views/LibraryView";
import { SetupView } from "./components/Views/SetupView";
import { ActivityView } from "./components/Views/ActivityView";
import { SettingsView } from "./components/Views/SettingsView";

// Types & Utils
import type { GamePayload, DownloadState, LogEntry } from "./types";
import { decodeGamePayload } from "./payload";

type View = "setup" | "library" | "activity" | "settings";
const STORAGE_KEY_DRIVE = "gr_default_drive";

const DOWNLOAD_STATE_KEY = "gr_download_state";

export default function App() {
  const [view, setView] = useState<View>("library");
  const [downloadState, setDownloadState] = useState<DownloadState | null>(
    () => {
      try {
        const saved = localStorage.getItem(DOWNLOAD_STATE_KEY);
        return saved ? JSON.parse(saved) : null;
      } catch { return null; }
    }
  );
  const [activePayload, setActivePayload] = useState<GamePayload | null>(null);
  const [defaultDrive, setDefaultDrive] = useState(() => localStorage.getItem(STORAGE_KEY_DRIVE) ?? "C:\\");

  const addLog = useCallback((tag: LogEntry["tag"], msg: string) => {
    setDownloadState(prev => prev ? ({
      ...prev,
      logs: [...prev.logs, { time: new Date().toLocaleTimeString(), tag, msg }]
    }) : null);
    console.log(`[${tag}] ${msg}`);
  }, []);

  // Alt+F4 / close window
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.altKey && e.key === 'F4') {
        e.preventDefault();
        import("@tauri-apps/api/window").then(m => m.getCurrentWindow().close());
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Effect: Persist download state to localStorage (survives HMR/reload)
  useEffect(() => {
    if (downloadState) {
      localStorage.setItem(DOWNLOAD_STATE_KEY, JSON.stringify(downloadState));
    } else {
      localStorage.removeItem(DOWNLOAD_STATE_KEY);
    }
  }, [downloadState]);

  // Effect: Extração Automática (Extract & Destroy)
  useEffect(() => {
    if (downloadState?.phase === "extracting") {
      const runExtraction = async () => {
        try {
          addLog("INFO", "Iniciando varredura e extração dinâmica (Gatling Extract)...");
          await invoke("extract_game", { installPath: downloadState.installPath });
          
          addLog("INFO", "Processando Lixo e Finalizando Instalação...");
          const meta: any = await invoke("finalize_installation", {
            installPath: downloadState.installPath,
            title: activePayload?.title
          });
          
          if (activePayload) {
            const entry = {
                title: activePayload.title,
                install_path: downloadState.installPath,
                executable: meta.executable,
                banner: activePayload.banner,
                size_gb: meta.size_gb
            };
            await invoke("add_to_library", { drive: defaultDrive, entry });

            // Create Start Menu shortcut automatically
            invoke("create_shortcut", { title: activePayload.title, executable: meta.executable, icon: meta.executable })
              .then(() => addLog("INFO", "Atalho criado no Menu Iniciar."))
              .catch(e => console.warn("Falha ao criar atalho:", e));
          }

          setDownloadState(prev => prev ? ({ ...prev, phase: "done", progressPercent: 100 }) : null);
          addLog("SUCCESS", "Protocolo Finalizado e Adicionado à Biblioteca.");
        } catch (e) {
          addLog("ERROR", `Falha na Extração: ${e}`);
          setDownloadState(prev => prev ? ({ ...prev, phase: "error", errorMessage: `Falha na extração: ${e}` }) : null);
        }
      };
      runExtraction();
    }
  }, [downloadState?.phase, activePayload?.title, downloadState?.installPath, addLog]);

  // Effect: Cronômetro de Download
  useEffect(() => {
    let interval: any;
    if (downloadState && downloadState.phase === "downloading") {
      const start = Date.now();
      interval = setInterval(() => {
        const elapsed = Math.floor((Date.now() - start) / 1000);
        const h = Math.floor(elapsed / 3600).toString().padStart(2, '0');
        const m = Math.floor((elapsed % 3600) / 60).toString().padStart(2, '0');
        const s = (elapsed % 60).toString().padStart(2, '0');
        setDownloadState(prev => prev ? ({ ...prev, elapsedTime: `${h}:${m}:${s}` }) : null);
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [downloadState?.phase]);

  const processUrl = useCallback((rawUrl: string) => {
    const payload = decodeGamePayload(rawUrl);
    if (payload) {
      setActivePayload(payload);
      setView("setup");
    }
  }, []);

  // Persist download state to localStorage (survives HMR/reload)
  useEffect(() => {
    if (downloadState) {
      localStorage.setItem(DOWNLOAD_STATE_KEY, JSON.stringify(downloadState));
    } else {
      localStorage.removeItem(DOWNLOAD_STATE_KEY);
    }
  }, [downloadState]);

  // Restore aria2c listener when downloadState is restored from storage
  useEffect(() => {
    // Deep link from Rust backend
    const unDeep = listen<string>("deeplink", (e) => {
      console.log("[DEEP-LINK] URI received:", e.payload);
      processUrl(e.payload);
    });

    const unLog = listen<string>("download-log", (e) => {
      const log = e.payload;

      if (log.includes("[METADATA]") || log.includes("[MEMORY]")) return;

      const progressMatch = log.match(/\[#\w+\s+([\d.]+)([A-Za-z]+)\/([\d.]+)(GiB|MiB|KiB|B)\((\d+)%\)/);
      const dlMatch = log.match(/DL:([\d.]+)(MiB|KiB|GiB|B)/);
      const etaMatch = log.match(/ETA:([\dhmsm]+)/);
      const cnMatch = log.match(/CN:(\d+)/);
      const sdMatch = log.match(/SD:(\d+)/);

      setDownloadState(prev => {
        if (!prev) return prev;
        let newState = { ...prev };

        if (progressMatch) {
          const downloadedVal = parseFloat(progressMatch[1]);
          const downloadedUnit = progressMatch[2];
          const totalVal = parseFloat(progressMatch[3]);
          const totalUnit = progressMatch[4];

          function toMiB(val: number, unit: string): number {
            if (unit === "GiB") return val * 1024;
            if (unit === "MiB") return val;
            if (unit === "KiB") return val / 1024;
            return val / (1024 * 1024);
          }

          const downloadedMiB = toMiB(downloadedVal, downloadedUnit);
          const totalMiB = toMiB(totalVal, totalUnit);

          if (totalMiB >= 10 && totalMiB > 0) {
            const calculatedPct = Math.min((downloadedMiB / totalMiB) * 100, 100);
            newState.progressPercent = calculatedPct;
            // Auto-complete when download is essentially done (within 1%)
            if (calculatedPct >= 99.9) {
              newState.phase = "extracting";
              newState.progressPercent = 100;
            }
          }
        }
        if (dlMatch) {
          const speedNum = parseFloat(dlMatch[1]);
          const speedUnit = dlMatch[2];
          if (speedUnit === "MiB") newState.speedMBs = speedNum;
          else if (speedUnit === "GiB") newState.speedMBs = speedNum * 1024;
          else if (speedUnit === "KiB") newState.speedMBs = speedNum / 1024;
        }
        if (etaMatch) newState.eta = etaMatch[1];
        if (cnMatch) newState.peers = parseInt(cnMatch[1]);
        if (sdMatch) newState.seeds = parseInt(sdMatch[1]);

        if (!log.includes("[#") || log.includes("Download complete")) {
          console.log(`[aria2c] ${log.replace(/\[\d+m/g, '')}`);
        }

        if (log.includes("Seeding is over")) {
          newState.progressPercent = 100;
          // If fixOnly mode, skip extraction and open folder
          if (newState.fixOnly) {
            newState.phase = "done";
            invoke("open_path", { path: "", selectFile: newState.installPath })
              .catch(() => {});
          } else {
            newState.phase = "extracting";
          }
        }

        // Detect aria2c failures (timeout, no peers, etc.)
        if (log.includes("Stop downloading") || log.includes("not complete") ||
            log.includes("Exception caught") || log.includes("errorCode=")) {
          newState.phase = "error";
          newState.errorMessage = "Torrent indisponível — nenhum seed/peer encontrado.";
          if (log.includes("bt-stop-timeout") || log.includes("not complete") ||
              log.includes("Stop downloading")) {
            addLog("ERROR", "Nenhum seed/peer encontrado. Torrent indisponível no momento.");
          } else if (log.includes("Exception")) {
            addLog("ERROR", `Erro no aria2: ${log}`);
          }
        }

        return newState;
      });
    });

    // Listener de progresso da extração
    const unExtract = listen<any>("extract-progress", (e) => {
      const data = e.payload;
      setDownloadState(prev => {
        if (!prev) return prev;

        if (data.type === "extracting" || data.type === "extracting_fix") {
          // Reset progress to 0 for extraction, calculate per-file percentage
          const extractPct = ((data.current - 1) / data.total) * 100; // start of this file

          return {
            ...prev,
            phase: "extracting" as const,
            progressPercent: extractPct,
            speedMBs: 0,
            eta: "--",
            logs: [...prev.logs, {
              time: new Date().toLocaleTimeString(),
              tag: "EXTRACTING" as const,
              msg: `${data.type === "extracting_fix" ? "[FIX] " : ""}${data.file} (${data.current}/${data.total})`
            }]
          };
        }

        if (data.type === "cleaning") {
          return { ...prev, progressPercent: 95, logs: [...prev.logs, { time: new Date().toLocaleTimeString(), tag: "CLEANING" as const, msg: "Limpando arquivos..." }] };
        }

        if (data.type === "done") {
          return { ...prev, progressPercent: 100 };
        }

        return prev;
      });
    });

    return () => {
      unDeep.then(f => f());
      unLog.then(f => f());
      unExtract.then(f => f());
    };
  }, [processUrl]);

  async function handleStartInstall(path: string) {
    if (!activePayload) {
      console.warn("[APP] No activePayload — can't start install");
      return;
    }
    setView("activity");
    setDownloadState({
      payload: activePayload,
      installPath: path,
      phase: "downloading",
      currentPart: 0,
      totalParts: activePayload.parts,
      progressPercent: 0,
      speedMBs: 0,
      eta: "0s",
      elapsedTime: "00:00",
      logs: [{ time: new Date().toLocaleTimeString(), tag: "INFO", msg: "Transmissão Iniciada." }],
      isPaused: false,
      peers: 0,
      seeds: 0,
      fixOnly: false
    });

    try { await invoke("add_defender_exclusion", { path }); } catch {}
    try { await invoke("start_torrent", { magnet: activePayload.magnet, installPath: path }); } catch (e: any) {
      addLog("ERROR", `Falha no Motor: ${e}`);
    }
  }

  async function handleDownloadFixOnly(path: string) {
    if (!activePayload) {
      console.warn("[APP] No activePayload — can't start fix-only download");
      return;
    }
    setView("activity");
    setDownloadState({
      payload: activePayload,
      installPath: path,
      phase: "downloading",
      currentPart: 0,
      totalParts: activePayload.parts,
      progressPercent: 0,
      speedMBs: 0,
      eta: "0s",
      elapsedTime: "00:00",
      logs: [{ time: new Date().toLocaleTimeString(), tag: "INFO", msg: "Baixando apenas Fix... (botão direito)" }],
      isPaused: false,
      peers: 0,
      seeds: 0,
      fixOnly: true
    });

    try {
      await invoke("add_defender_exclusion", { path });
    } catch {}

    try {
      await invoke("start_fix_download", { magnet: activePayload.magnet, installPath: path });
    } catch (e: any) {
      addLog("ERROR", `Falha no Motor: ${e}`);
    }
  }

  return (
    <div className="flex flex-col h-screen bg-[#0e0e10] text-[#e5e1e4] font-['Inter'] overflow-hidden tracking-tighter shadow-2xl border border-white/5">
      <Header 
        currentView={view} 
        onViewChange={setView} 
        onLogoClick={() => setView('library')} 
      />

      <AnimatePresence mode="wait">
        {view === "setup" && activePayload && (
          <motion.div key="setup" className="flex-1" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }}>
             <SetupView payload={activePayload} defaultDrive={defaultDrive} onStart={handleStartInstall} onDownloadFixOnly={handleDownloadFixOnly} />
          </motion.div>
        )}
        {view === "activity" && (
          <motion.div key="activity" className="flex-1 flex items-center justify-center" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
             <ActivityView
               state={downloadState}
               isPaused={downloadState?.isPaused || false}
               onPause={async () => {
                 if (downloadState?.isPaused) {
                    await invoke("start_torrent", {
                       magnet: activePayload?.magnet,
                       installPath: downloadState.installPath
                    });
                    setDownloadState(prev => prev ? { ...prev, isPaused: false } : null);
                 } else {
                    await invoke("stop_torrent");
                    setDownloadState(prev => prev ? { ...prev, isPaused: true } : null);
                 }
               }}
               onCancel={async () => {
                 await invoke("stop_torrent");
                 if (downloadState && !downloadState.fixOnly) {
                   await invoke("delete_folder", { path: downloadState.installPath }).catch(() => {});
                 }
                 setDownloadState(null);
                 setView("library");
               }}
               onStartGame={async () => {
                 // Just close the activity view, DON'T delete the folder
                 setDownloadState(null);
                 setView("library");
               }}
             />
          </motion.div>
        )}
        {view === "settings" && (
          <SettingsView 
            defaultDrive={defaultDrive} 
            onDriveChange={(d) => setDefaultDrive(d)} 
          />
        )}
        {view === "library" && <LibraryView defaultDrive={defaultDrive} />}
      </AnimatePresence>

      <Footer installPath={downloadState?.installPath} defaultDrive={defaultDrive} />
    </div>
  );
}
