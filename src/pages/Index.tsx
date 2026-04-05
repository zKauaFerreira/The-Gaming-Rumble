import { useEffect, useState, useCallback } from "react";
import icon from "@/assets/icon.png";

type PageState = "loading" | "opened" | "fallback" | "error" | "invalid-payload";

const REQUIRED_FIELDS = ["title", "banner", "parts", "fileSize", "magnet"] as const;

function validatePayload(base64: string): { valid: boolean; missingFields?: string[] } {
  try {
    const json = atob(base64);
    const data = JSON.parse(json);
    if (typeof data !== "object" || data === null) {
      return { valid: false };
    }
    const missing = REQUIRED_FIELDS.filter((f) => !(f in data) || data[f] === undefined || data[f] === "");
    if (missing.length > 0) {
      return { valid: false, missingFields: [...missing] };
    }
    return { valid: true };
  } catch {
    return { valid: false };
  }
}

const Index = () => {
  const [state, setState] = useState<PageState>("loading");
  const [protocolUrl, setProtocolUrl] = useState<string>("");

  const tryOpenProtocol = useCallback((url: string) => {
    window.location.href = url;
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const data = params.get("data");

    if (!data || data.trim() === "") {
      setState("error");
      return;
    }

    if (!/^[A-Za-z0-9+/=_-]+$/.test(data)) {
      setState("error");
      return;
    }

    // Validar payload base64
    const validation = validatePayload(data);
    if (!validation.valid) {
      setState("invalid-payload");
      return;
    }

    const url = `gaming-rumble://${data}`;
    setProtocolUrl(url);

    // Tentar abrir automaticamente
    tryOpenProtocol(url);

    // Detectar se o app abriu via visibilitychange + blur
    let fallbackTimer: ReturnType<typeof setTimeout>;
    let didOpen = false;

    const markOpened = () => {
      if (!didOpen) {
        didOpen = true;
        clearTimeout(fallbackTimer);
        setState("opened");
      }
    };

    const handleVisibility = () => {
      if (document.hidden) markOpened();
    };

    const handleBlur = () => markOpened();

    document.addEventListener("visibilitychange", handleVisibility);
    window.addEventListener("blur", handleBlur);

    // Fallback após 1.5s se o app não abriu
    fallbackTimer = setTimeout(() => {
      if (!didOpen) {
        setState("fallback");
      }
    }, 1500);

    return () => {
      document.removeEventListener("visibilitychange", handleVisibility);
      window.removeEventListener("blur", handleBlur);
      clearTimeout(fallbackTimer);
    };
  }, [tryOpenProtocol]);

  // Estado de erro
  if (state === "error") {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="animate-fade-in-up bg-card border border-border rounded-2xl p-8 md:p-12 max-w-md w-full text-center shadow-2xl">
          <img src={icon} alt="Gaming Rumble" className="w-16 h-16 mx-auto mb-6 rounded-2xl" />
          <div className="w-14 h-14 mx-auto mb-5 rounded-full bg-destructive/10 flex items-center justify-center">
            <svg className="w-7 h-7 text-destructive" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold mb-2">Link inválido</h1>
          <p className="text-muted-foreground mb-8">
            O link que você acessou é inválido ou incompleto. Verifique e tente novamente.
          </p>
          <button
            onClick={() => window.history.back()}
            className="px-6 py-3 rounded-xl bg-secondary text-secondary-foreground font-medium hover:bg-secondary/80 transition-colors"
          >
            ← Voltar
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className={`animate-fade-in-up bg-card border border-border rounded-2xl p-8 md:p-12 max-w-md w-full text-center shadow-2xl ${state === "loading" ? "animate-pulse-glow" : ""}`}>
        {/* Logo */}
        <div className="mb-8">
          <img src={icon} alt="Gaming Rumble" className="w-20 h-20 mx-auto mb-5 rounded-2xl" />
          <h1 className="text-3xl font-bold tracking-tight">Gaming Rumble</h1>
        </div>

        {/* Estado: App abriu com sucesso */}
        {state === "opened" && (
          <div className="animate-fade-in-up">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full flex items-center justify-center" style={{ backgroundColor: "hsl(var(--success) / 0.15)" }}>
              <svg className="w-8 h-8 animate-check-pop" style={{ color: "hsl(var(--success))" }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
              </svg>
            </div>
            <p className="text-lg font-medium">Jogo aberto com sucesso!</p>
            <p className="text-sm text-muted-foreground mt-1">
              Você já pode fechar esta aba
            </p>
          </div>
        )}

        {/* Estado: Carregando */}
        {state === "loading" && (
          <div className="mb-6">
            <div className="w-10 h-10 mx-auto mb-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin-slow" />
            <p className="text-lg font-medium">Abrindo seu jogo...</p>
            <p className="text-sm text-muted-foreground mt-1">
              Redirecionando para o Gaming Rumble
            </p>
          </div>
        )}

        {/* Estado: Fallback */}
        {state === "fallback" && (
          <div className="animate-fade-in-up">
            <div className="mb-4">
              <div className="w-10 h-10 mx-auto mb-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin-slow" />
              <p className="text-lg font-medium">Abrindo seu jogo...</p>
            </div>
            <div className="border-t border-border pt-6 mt-4">
              <p className="text-sm text-muted-foreground mb-4">
                Se nada acontecer, clique no botão abaixo
              </p>
              <button
                onClick={() => tryOpenProtocol(protocolUrl)}
                className="w-full px-6 py-3.5 rounded-xl bg-primary text-primary-foreground font-semibold text-base hover:brightness-110 active:scale-[0.98] transition-all"
              >
                Abrir manualmente
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Index;
