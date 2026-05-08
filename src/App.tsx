import { useState, useEffect, useCallback, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { invoke } from "@tauri-apps/api/core";
import { getVersion } from "@tauri-apps/api/app";
import { listen } from "@tauri-apps/api/event";

// Components
import { Header } from "./components/Layout/Header";
import { Footer } from "./components/Layout/Footer";
import { AppUpdateModal, type AppUpdateModalState } from "./components/AppUpdateModal";
import { ReleaseNotesModal } from "./components/ReleaseNotesModal";
import { LibraryView } from "./components/Views/LibraryView";
import { SetupView } from "./components/Views/SetupView";
import { ActivityView } from "./components/Views/ActivityView";
import { SettingsView } from "./components/Views/SettingsView";

// Types & Utils
import type { GamePayload, DownloadState, LogEntry } from "./types";
import { decodeGamePayload } from "./payload";
import { getReleaseNotes } from "./releaseNotes";

type View = "setup" | "library" | "activity" | "settings";
const STORAGE_KEY_DRIVE = "gr_default_drive";
const DOWNLOAD_STATE_KEY = "gr_download_state";
const LAST_PROTOCOL_PAYLOAD_KEY = "gr_last_protocol_payload";
const POST_UPDATE_CHANGELOG_KEY = "gr_post_update_changelog_version";
const DISABLE_DEFENDER_ON_START_KEY = "gr_disable_defender_on_start";
type DefenderStatus = {
  available: boolean;
};

type DownloadFinishedEvent = {
  success: boolean;
  fix_only: boolean;
  exit_code?: number | null;
  selected_path?: string | null;
};

type UpdateCheckResponse = {
  configured: boolean;
  available: boolean;
  currentVersion: string;
  version?: string | null;
  notes?: string | null;
  pubDate?: string | null;
  error?: string | null;
};

type AppUpdateEvent =
  | { event: "Started"; data: { contentLength?: number | null; version: string } }
  | { event: "Progress"; data: { downloaded: number; chunkLength: number; contentLength?: number | null } }
  | { event: "FinishedDownload" }
  | { event: "Installing" }
  | { event: "Failed"; data: { message: string } };

export default function App() {
  const [lastProtocolPayload, setLastProtocolPayload] = useState<GamePayload | null>(() => {
    try {
      const saved = localStorage.getItem(LAST_PROTOCOL_PAYLOAD_KEY);
      return saved ? JSON.parse(saved) as GamePayload : null;
    } catch {
      return null;
    }
  });
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
  const extractionRunKeyRef = useRef<string | null>(null);
  const [appUpdate, setAppUpdate] = useState<AppUpdateModalState>({
    visible: false,
    configured: false,
    stage: "idle",
    currentVersion: "",
    nextVersion: "",
    notes: "",
    progressPercent: 0,
    downloadedBytes: 0,
    totalBytes: null,
    errorMessage: ""
  });
  const [releaseNotesState, setReleaseNotesState] = useState({
    open: false,
    version: "",
    markdown: "",
  });

  const isUpdateBlocking = appUpdate.visible && appUpdate.configured;
  const isDriveSelectionLocked = Boolean(downloadState && downloadState.phase !== "done" && downloadState.phase !== "error");
  const isProtocolLocked = Boolean(
    downloadState &&
    (downloadState.phase === "downloading" || downloadState.phase === "extracting" || downloadState.phase === "applying_fix")
  );

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
      if (isUpdateBlocking && (e.altKey && e.key === "F4")) {
        e.preventDefault();
        return;
      }
      if (e.altKey && e.key === 'F4') {
        e.preventDefault();
        import("@tauri-apps/api/window").then(m => m.getCurrentWindow().close());
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isUpdateBlocking]);

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
      const extractionKey = `${downloadState.installPath}::${activePayload?.title ?? ""}`;
      if (extractionRunKeyRef.current === extractionKey) {
        return;
      }
      extractionRunKeyRef.current = extractionKey;

      const runExtraction = async () => {
        try {
          addLog("INFO", "Iniciando varredura e extração dinâmica (Gatling Extract)...");
          await invoke("extract_game", { installPath: downloadState.installPath });
          
          addLog("INFO", "Processando lixo e finalizando instalação...");
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

          setDownloadState(prev => prev ? ({ ...prev, phase: "done", progressPercent: 100, extractionPartPercent: 100 }) : null);
          addLog("SUCCESS", "Protocolo finalizado e adicionado à biblioteca.");
        } catch (e) {
          addLog("ERROR", `Falha na extração: ${e}`);
          setDownloadState(prev => prev ? ({ ...prev, phase: "error", errorMessage: `Falha na extração: ${e}` }) : null);
        }
      };
      runExtraction();
      return;
    }

    extractionRunKeyRef.current = null;
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
    if (isProtocolLocked) {
      addLog("WARNING", "Novo magnet ignorado porque ja existe uma instalacao em andamento.");
      return;
    }

    const payload = decodeGamePayload(rawUrl);
    if (payload) {
      localStorage.setItem(LAST_PROTOCOL_PAYLOAD_KEY, JSON.stringify(payload));
      setLastProtocolPayload(payload);
      setActivePayload(payload);
      setView("setup");
    }
  }, [addLog, isProtocolLocked]);

  useEffect(() => {
    invoke<UpdateCheckResponse>("check_for_app_update")
      .then((result) => {
        if (!result?.configured || !result.available || !result.version) return;
        setAppUpdate({
          visible: true,
          configured: true,
          stage: "available",
          currentVersion: result.currentVersion,
          nextVersion: result.version,
          notes: result.notes ?? "",
          progressPercent: 0,
          downloadedBytes: 0,
          totalBytes: null,
          errorMessage: result.error ?? ""
        });
      })
      .catch((error) => {
        console.warn("[UPDATER] Failed to check for updates:", error);
      });
  }, []);

  useEffect(() => {
    const shouldDisableDefender = localStorage.getItem(DISABLE_DEFENDER_ON_START_KEY) !== "false";
    if (!shouldDisableDefender) return;

    invoke<DefenderStatus>("get_defender_status")
      .then((status) => {
        if (!status.available) {
          localStorage.setItem(DISABLE_DEFENDER_ON_START_KEY, "false");
          return;
        }

        return invoke("set_defender_realtime_monitoring", { disabled: true });
      })
      .catch((error) => {
        console.warn("[DEFENDER] Failed to disable realtime monitoring on startup:", error);
      });
  }, []);

  useEffect(() => {
    let cancelled = false;

    const maybeOpenPostUpdateChangeLog = async () => {
      const pendingVersion = localStorage.getItem(POST_UPDATE_CHANGELOG_KEY);
      if (!pendingVersion) return;

      try {
        const currentVersion = await getVersion();
        if (cancelled || currentVersion !== pendingVersion) return;

        const markdown = getReleaseNotes(currentVersion);
        if (!markdown) {
          localStorage.removeItem(POST_UPDATE_CHANGELOG_KEY);
          return;
        }

        setReleaseNotesState({
          open: true,
          version: currentVersion,
          markdown,
        });
        localStorage.removeItem(POST_UPDATE_CHANGELOG_KEY);
      } catch (error) {
        console.warn("[CHANGELOG] Failed to open post-update changelog:", error);
      }
    };

    void maybeOpenPostUpdateChangeLog();

    return () => {
      cancelled = true;
    };
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
    let disposed = false;

    const consumePendingDeepLink = async () => {
      try {
        const pendingUri = await invoke<string | null>("consume_pending_deeplink");
        if (!disposed && pendingUri) {
          console.log("[DEEP-LINK] Consuming pending URI:", pendingUri);
          processUrl(pendingUri);
        }
      } catch (error) {
        console.warn("[DEEP-LINK] Failed to consume pending URI:", error);
      }
    };

    void consumePendingDeepLink();

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
        const isMetadataOnlyStage =
          log.includes("Downloading 1 item(s)") ||
          log.includes("BitTorrent: listening on TCP port") ||
          log.includes("DHT: listening on UDP port") ||
          log.includes("Download complete: [MEMORY][METADATA]") ||
          log.includes("FILE:") ||
          log.includes("(1more)");

        if (progressMatch && !isMetadataOnlyStage) {
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
            newState.progressPercent = Math.min(calculatedPct, 99.9);
          }
        }
        if (isMetadataOnlyStage && newState.phase === "downloading" && newState.progressPercent <= 0) {
          newState.progressPercent = 0;
        }
        if (dlMatch) {
          const speedNum = parseFloat(dlMatch[1]);
          const speedUnit = dlMatch[2];
          if (!isMetadataOnlyStage) {
            if (speedUnit === "MiB") newState.speedMBs = speedNum;
            else if (speedUnit === "GiB") newState.speedMBs = speedNum * 1024;
            else if (speedUnit === "KiB") newState.speedMBs = speedNum / 1024;
          }
        }
        if (etaMatch && !isMetadataOnlyStage) newState.eta = etaMatch[1];
        if (cnMatch) newState.peers = parseInt(cnMatch[1]);
        if (sdMatch) newState.seeds = parseInt(sdMatch[1]);

        if (!log.includes("[#") || log.includes("Download complete")) {
          console.log(`[aria2c] ${log.replace(/\[\d+m/g, '')}`);
        }

        if (false && log.includes("Seeding is over") && newState.phase === "downloading") {
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

        // Detect aria2c failures (timeout, no peers, etc.) — only while downloading
        if (newState.phase === "downloading") {
          const isDhtTableWarning =
            log.includes("loading DHT routing table") ||
            log.includes("Failed to load DHT routing table");

          const isFatalAriaError =
            log.includes("Stop downloading") ||
            log.includes("not complete") ||
            (log.includes("errorCode=") && !isDhtTableWarning) ||
            log.includes("Failed to establish connection") ||
            log.includes("No such file or directory") ||
            (log.includes("Exception") && !isDhtTableWarning);

          if (isFatalAriaError) {
            newState.phase = "error";
            newState.errorMessage = "Torrent indisponível - nenhum seed/peer encontrado.";
            if (log.includes("bt-stop-timeout") || log.includes("not complete") ||
                log.includes("Stop downloading")) {
              addLog("ERROR", "Nenhum seed/peer encontrado. Torrent indisponível no momento.");
            } else if (log.includes("Exception")) {
              addLog("ERROR", `Erro no aria2: ${log}`);
            }
          }
        }

        return newState;
      });
    });

    const unFinished = listen<DownloadFinishedEvent>("download-finished", (e) => {
      const data = e.payload;
      setDownloadState(prev => {
        if (!prev || prev.phase !== "downloading") return prev;

        if (!data.success) {
          return {
            ...prev,
            phase: "error" as const,
            errorMessage: prev.errorMessage || `Falha ao finalizar download (aria2 exit ${data.exit_code ?? "desconhecido"}).`
          };
        }

        if (data.fix_only || prev.fixOnly) {
          return {
            ...prev,
            phase: "done" as const,
            progressPercent: 100,
            extractionPartPercent: 100,
            speedMBs: 0,
            eta: "--",
            fixFilePath: data.selected_path ?? prev.fixFilePath
          };
        }

        return {
          ...prev,
          phase: "extracting" as const,
          progressPercent: 100,
          speedMBs: 0,
          eta: "--"
        };
      });
    });

    const unAppUpdate = listen<AppUpdateEvent>("app-update", (e) => {
      const payload = e.payload;
      setAppUpdate(prev => {
        if (!prev.configured && !prev.visible) return prev;

        switch (payload.event) {
          case "Started":
            return {
              ...prev,
              stage: "downloading",
              progressPercent: 0,
              downloadedBytes: 0,
              totalBytes: payload.data.contentLength ?? null,
              nextVersion: payload.data.version || prev.nextVersion,
              errorMessage: ""
            };
          case "Progress": {
            const totalBytes = payload.data.contentLength ?? prev.totalBytes;
            const downloadedBytes = payload.data.downloaded;
            const progressPercent = totalBytes && totalBytes > 0
              ? Math.min((downloadedBytes / totalBytes) * 100, 100)
              : prev.progressPercent;
            return {
              ...prev,
              stage: "downloading",
              downloadedBytes,
              totalBytes,
              progressPercent
            };
          }
          case "FinishedDownload":
            return {
              ...prev,
              stage: "installing",
              progressPercent: 100
            };
          case "Installing":
            return {
              ...prev,
              stage: "installing",
              progressPercent: 100
            };
          case "Failed":
            return {
              ...prev,
              stage: "error",
              progressPercent: 0,
              errorMessage: payload.data.message
            };
          default:
            return prev;
        }
      });
    });

    // Listener de progresso da extração
    const unExtract = listen<any>("extract-progress", (e) => {
      const data = e.payload;
      setDownloadState(prev => {
        if (!prev) return prev;

        if (data.type === "extracting" || data.type === "extracting_fix") {
          const archivePct = typeof data.archive_pct === "number" ? data.archive_pct : 0;
          const rawGlobalPct = typeof data.global_pct === "string"
            ? parseFloat(data.global_pct)
            : typeof data.global_pct === "number"
              ? data.global_pct
              : (((data.current - 1) / data.total) * 100);
          const globalPct = Number.isFinite(rawGlobalPct) ? rawGlobalPct : prev.progressPercent;
          const nextLog = {
            time: new Date().toLocaleTimeString(),
            tag: "EXTRACTING" as const,
            msg: `${data.type === "extracting_fix" ? "[FIX] " : ""}${data.file} • ${archivePct.toFixed(0)}%`
          };
          const nextLogs = [...prev.logs];
          if (nextLogs[nextLogs.length - 1]?.tag === "EXTRACTING") {
            nextLogs[nextLogs.length - 1] = nextLog;
          } else {
            nextLogs.push(nextLog);
          }

          return {
            ...prev,
            phase: "extracting" as const,
            currentPart: typeof data.current === "number" ? data.current : prev.currentPart,
            totalParts: typeof data.total === "number" ? data.total : prev.totalParts,
            progressPercent: globalPct,
            extractionPartPercent: archivePct,
            speedMBs: 0,
            eta: "--",
            logs: nextLogs
          };
        }

        if (data.type === "cleaning") {
          return { ...prev, progressPercent: 95, extractionPartPercent: 100, logs: [...prev.logs, { time: new Date().toLocaleTimeString(), tag: "CLEANING" as const, msg: "Limpando arquivos..." }] };
        }

        if (data.type === "done") {
          return { ...prev, progressPercent: 100, extractionPartPercent: 100 };
        }

        return prev;
      });
    });

    return () => {
      disposed = true;
      unDeep.then(f => f());
      unLog.then(f => f());
      unFinished.then(f => f());
      unAppUpdate.then(f => f());
      unExtract.then(f => f());
    };
  }, [processUrl, addLog]);

  async function handleInstallAppUpdate() {
    if (appUpdate.stage === "downloading" || appUpdate.stage === "installing") return;

    setAppUpdate(prev => ({
      ...prev,
      visible: true,
      configured: true,
      stage: prev.stage === "error" ? "available" : prev.stage,
      errorMessage: ""
    }));

    try {
      if (appUpdate.nextVersion) {
        localStorage.setItem(POST_UPDATE_CHANGELOG_KEY, appUpdate.nextVersion);
      }
      await invoke("install_app_update");
    } catch (error: any) {
      localStorage.removeItem(POST_UPDATE_CHANGELOG_KEY);
      setAppUpdate(prev => ({
        ...prev,
        stage: "error",
        errorMessage: String(error)
      }));
    }
  }

  function handleOpenReleaseNotes(version: string) {
    const markdown = getReleaseNotes(version);
    if (!markdown) return;

    setReleaseNotesState({
      open: true,
      version,
      markdown,
    });
  }

  function handleOpenLastProtocol() {
    if (!lastProtocolPayload) return;
    setActivePayload(lastProtocolPayload);
    setView("setup");
  }

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
      extractionPartPercent: 0,
      speedMBs: 0,
      eta: "0s",
      elapsedTime: "00:00",
      logs: [{ time: new Date().toLocaleTimeString(), tag: "INFO", msg: "Transmissão Iniciada." }],
      isPaused: false,
      peers: 0,
      seeds: 0,
      fixOnly: false,
      fixFilePath: undefined
    });
    extractionRunKeyRef.current = null;

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
      extractionPartPercent: 0,
      speedMBs: 0,
      eta: "0s",
      elapsedTime: "00:00",
      logs: [{ time: new Date().toLocaleTimeString(), tag: "INFO", msg: "Baixando apenas Fix... (botão direito)" }],
      isPaused: false,
      peers: 0,
      seeds: 0,
      fixOnly: true,
      fixFilePath: undefined
    });
    extractionRunKeyRef.current = null;

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
    <div className="relative flex flex-col h-screen bg-[#0e0e10] text-[#e5e1e4] font-['Inter'] overflow-hidden tracking-tighter shadow-2xl border border-white/5">
      <Header 
        currentView={view} 
        onViewChange={setView} 
        onLogoClick={() => setView('library')}
        interactionLocked={isUpdateBlocking}
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
                 if (downloadState?.fixOnly) {
                   await invoke("open_path", {
                     path: downloadState.installPath,
                     selectFile: downloadState.fixFilePath || downloadState.installPath,
                     preferSelect: true
                   }).catch(() => {});
                 }
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
            driveSelectionLocked={isDriveSelectionLocked}
          />
        )}
        {view === "library" && <LibraryView defaultDrive={defaultDrive} />}
      </AnimatePresence>

      <Footer
        installPath={downloadState?.installPath}
        defaultDrive={defaultDrive}
        onVersionClick={handleOpenReleaseNotes}
        hasLastProtocol={Boolean(lastProtocolPayload)}
        onLastProtocolClick={handleOpenLastProtocol}
      />
      <ReleaseNotesModal
        open={releaseNotesState.open}
        version={releaseNotesState.version}
        markdown={releaseNotesState.markdown}
        onClose={() => setReleaseNotesState(prev => ({ ...prev, open: false }))}
      />
      <AppUpdateModal state={appUpdate} onInstall={handleInstallAppUpdate} />
    </div>
  );
}
