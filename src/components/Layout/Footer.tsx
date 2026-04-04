import { useState, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";

interface FooterProps {
  installPath?: string;
  defaultDrive?: string;
}

export function Footer({ installPath, defaultDrive }: FooterProps) {
  const [diskFree, setDiskFree] = useState("");
  const [drive, setDrive] = useState("");

  const targetPath = installPath || defaultDrive || "";

  useEffect(() => {
    if (targetPath) {
      const letter = targetPath.split('\\')[0] || targetPath;
      setDrive(letter);
      invoke<string>("get_disk_space", { path: targetPath.includes(':') ? targetPath.split('\\')[0] + '\\' : targetPath })
        .then(r => setDiskFree(r !== "N/A" ? r : ""))
        .catch(() => {});
    } else {
      setDrive("");
      setDiskFree("");
    }
  }, [targetPath]);

  return (
    <footer className="h-10 px-8 border-t border-white/5 bg-[#131315]/70 flex items-center justify-between text-[9px] uppercase font-black opacity-50 tracking-[0.6em] z-30">
      <span>{drive}{diskFree ? ` ${diskFree} livre` : ""}</span>
      <span>v1.0.0</span>
    </footer>
  );
}
