/**
 * Payload enviado pelo Bot do Discord via deep-link
 * Codificado em Base64 e passado como: gaming-rumble://[BASE64]
 *
 * Exemplo decodificado:
 * {
 *   "title": "Cyberpunk 2077",
 *   "banner": "https://shared.akamai.steamstatic.com/.../header.jpg",
 *   "parts": 10,
 *   "fileSize": "55.4 GB",
 *   "magnet": "magnet:?xt=urn:btih:..."
 * }
 */
export interface GamePayload {
  title: string;        // Nome limpo do jogo
  banner: string;       // URL da header image do Steam
  parts: number;        // Quantidade de partes .rar
  fileSize: string;     // Tamanho total formatado ex: "55.4 GB"
  magnet: string;       // Magnet link completo
}

/**
 * Jogo instalado — salvo no disco pelo app
 */
export interface InstalledGame {
  id: string;
  title: string;
  banner: string;
  installPath: string;  // Ex: "C:\Gaming Rumble\Cyberpunk 2077"
  installedAt: string;  // ISO date string
  fileSize: string;
}

/**
 * Estado de download/extração em andamento
 */
export interface DownloadState {
  payload: GamePayload;
  installPath: string;
  phase: "downloading" | "extracting" | "applying_fix" | "done" | "error";
  currentPart: number;
  totalParts: number;
  progressPercent: number;
  speedMBs: number;
  eta: string;
  elapsedTime: string;
  logs: LogEntry[];
  isPaused: boolean;
  peers: number;
  seeds: number;
  fixOnly: boolean;
  errorMessage?: string;
}

export interface LogEntry {
  time: string;
  tag: "INFO" | "SUCCESS" | "EXTRACTING" | "CLEANING" | "ERROR" | "FIX" | "WARNING";
  msg: string;
}
