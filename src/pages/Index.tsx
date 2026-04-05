import { useEffect, useState, useCallback } from "react";

type PageState = "loading" | "fallback" | "error";

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

    // Validar que é uma string base64 válida (caracteres permitidos)
    if (!/^[A-Za-z0-9+/=_-]+$/.test(data)) {
      setState("error");
      return;
    }

    const url = `gaming-rumble://${data}`;
    setProtocolUrl(url);

    // Tentar abrir automaticamente
    tryOpenProtocol(url);

    // Detectar se o app abriu via visibilitychange
    let fallbackTimer: ReturnType<typeof setTimeout>;
    let didOpen = false;

    const handleVisibility = () => {
      if (document.hidden) {
        didOpen = true;
        clearTimeout(fallbackTimer);
      }
    };

    document.addEventListener("visibilitychange", handleVisibility);

    // Fallback após 1.5s se o app não abriu
    fallbackTimer = setTimeout(() => {
      if (!didOpen) {
        setState("fallback");
      }
    }, 1500);

    return () => {
      document.removeEventListener("visibilitychange", handleVisibility);
      clearTimeout(fallbackTimer);
    };
  }, [tryOpenProtocol]);

  if (state === "error") {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="animate-fade-in-up bg-card border border-border rounded-2xl p-8 md:p-12 max-w-md w-full text-center shadow-2xl">
          <div className="w-16 h-16 mx-auto mb-6 rounded-full bg-destructive/10 flex items-center justify-center">
            <svg className="w-8 h-8 text-destructive" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
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
      <div className="animate-fade-in-up bg-card border border-border rounded-2xl p-8 md:p-12 max-w-md w-full text-center shadow-2xl animate-pulse-glow">
        {/* Logo / Título */}
        <div className="mb-8">
          <div className="w-20 h-20 mx-auto mb-5 rounded-2xl bg-gradient-to-br from-primary/20 to-accent/20 border border-primary/30 flex items-center justify-center">
            <svg className="w-10 h-10 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M14.25 6.087c0-.355.186-.676.401-.959.221-.29.349-.634.349-1.003 0-1.036-1.007-1.875-2.25-1.875s-2.25.84-2.25 1.875c0 .369.128.713.349 1.003.215.283.401.604.401.959v0a.64.64 0 0 1-.657.643 48.39 48.39 0 0 1-4.163-.3c.186 1.613.293 3.25.315 4.907a.656.656 0 0 1-.658.663v0c-.355 0-.676-.186-.959-.401a1.647 1.647 0 0 0-1.003-.349c-1.036 0-1.875 1.007-1.875 2.25s.84 2.25 1.875 2.25c.369 0 .713-.128 1.003-.349.283-.215.604-.401.959-.401v0c.31 0 .555.26.532.57a48.039 48.039 0 0 1-.642 5.056c1.518.19 3.058.309 4.616.354a.64.64 0 0 0 .657-.643v0c0-.355-.186-.676-.401-.959a1.647 1.647 0 0 1-.349-1.003c0-1.035 1.008-1.875 2.25-1.875 1.243 0 2.25.84 2.25 1.875 0 .369-.128.713-.349 1.003-.215.283-.4.604-.4.959v0c0 .333.277.599.61.58a48.1 48.1 0 0 0 5.427-.63 48.05 48.05 0 0 0 .582-4.717.532.532 0 0 0-.533-.57v0c-.355 0-.676.186-.959.401-.29.221-.634.349-1.003.349-1.035 0-1.875-1.007-1.875-2.25s.84-2.25 1.875-2.25c.37 0 .713.128 1.003.349.283.215.604.401.959.401v0a.656.656 0 0 0 .658-.663 48.422 48.422 0 0 0-.37-5.36c-1.886.342-3.81.574-5.766.689a.578.578 0 0 1-.61-.58v0Z" />
            </svg>
          </div>
          <h1 className="text-3xl font-bold tracking-tight">Gaming Rumble</h1>
        </div>

        {/* Loader */}
        <div className="mb-6">
          <div className="w-10 h-10 mx-auto mb-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin-slow" />
          <p className="text-lg font-medium">Abrindo seu jogo...</p>
          <p className="text-sm text-muted-foreground mt-1">
            Redirecionando para o Gaming Rumble
          </p>
        </div>

        {/* Fallback */}
        <div
          className={`transition-all duration-500 ${
            state === "fallback"
              ? "opacity-100 translate-y-0"
              : "opacity-0 translate-y-4 pointer-events-none"
          }`}
        >
          <div className="border-t border-border pt-6 mt-6">
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
      </div>
    </div>
  );
};

export default Index;
