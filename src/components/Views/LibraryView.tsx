import { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { Icon } from '../Icon';

export interface LibraryEntry {
    title: string;
    install_path: string;
    executable: string;
    banner: string;
    size_gb: number;
}

export function LibraryView({ defaultDrive }: { defaultDrive: string }) {
  const [games, setGames] = useState<LibraryEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!defaultDrive) return;
    setLoading(true);
    invoke<LibraryEntry[]>('get_library', { drive: defaultDrive })
      .then(res => setGames(res || []))
      .catch(e => console.error(e))
      .finally(() => setLoading(false));
  }, [defaultDrive]);

  const removeGame = async (game: LibraryEntry) => {
    if (confirm(`Atenção: Isso removerá "${game.title}" e apagará todos os ~${game.size_gb.toFixed(1)}GB do disco. Continuar?`)) {
      setGames(games.filter(g => g.title !== game.title));
      await invoke('stop_torrent').catch(() => {});
      await invoke('delete_folder', { path: game.install_path }).catch(console.error);
      await invoke('remove_shortcut', { title: game.title }).catch(() => {});
      await invoke('remove_from_library', { drive: defaultDrive, title: game.title }).catch(console.error);
    }
  };

  const playGame = async (executable: string) => {
     if (!executable) {
        alert("Executável não encontrado. O jogo pode não ter sido extraído corretamente.");
        return;
     }
     await invoke('play_game', { executable }).catch(e => alert(`Erro ao iniciar jogo: ${e}`));
  };

  const openFolder = async (installPath: string, executable: string) => {
    await invoke('open_path', { path: installPath, selectFile: executable });
  };

  const changeExe = async (game: LibraryEntry) => {
    const filePath: string | null = await invoke('show_exe_picker', { defaultPath: game.install_path });
    if (filePath && typeof filePath === 'string') {
      await invoke('update_executable', { title: game.title, executable: filePath });
      setGames([]);
      setLoading(true);
      invoke<LibraryEntry[]>('get_library', { drive: defaultDrive })
        .then(res => setGames(res || []))
        .finally(() => setLoading(false));
    }
  };

  const createShortcut = async (game: LibraryEntry) => {
    invoke('create_shortcut', { title: game.title, executable: game.executable, icon: game.executable })
      .catch(e => console.error("Falha ao criar atalho:", e));
  };

  if (loading) {
     return <div className="flex-1 flex items-center justify-center text-slate-500 animate-pulse">CARREGANDO...</div>;
  }

  if (games.length === 0) return (
    <div className="flex-1 flex items-center justify-center bg-[#0e0e10]">
      <div className="flex flex-col items-center gap-4">
        <Icon name="sports_esports" size={64} className="text-slate-600" />
        <span className="text-sm text-slate-500 tracking-widest font-medium uppercase">Nenhum Jogo Baixado</span>
      </div>
    </div>
  );

  return (
    <div className="flex-1 overflow-y-auto w-full p-12 pr-6 custom-scrollbar flex flex-col gap-8 pb-32">
       <div className="flex items-center justify-between">
           <h2 className="text-3xl font-black text-white/90 tracking-tighter uppercase tabular-nums">
             Sua Coleção <span className="text-[#a4e6ff] text-xl ml-2">({games.length})</span>
           </h2>
       </div>

       <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 w-full">
         {games.map(game => (
            <div key={game.title} className="relative group bg-[#111113] rounded-2xl overflow-hidden border border-white/5 flex flex-col hover:border-white/10 transition-all duration-300">
               <div className="h-40 w-full overflow-hidden relative">
                  <img src={game.banner} alt={game.title} className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity duration-500" />
                  <div className="absolute inset-0 bg-gradient-to-t from-[#111113] to-transparent pointer-events-none" />
                  <div className="absolute inset-0 shadow-[inset_0_0_50px_rgba(0,0,0,0.8)] pointer-events-none" />
               </div>
               <div className="p-6 relative z-10 flex-col flex flex-1 bg-gradient-to-b from-[#111113] to-[#0a0a0a]">
                  <h3 className="text-xl font-bold text-white/90 uppercase tracking-wide truncate">{game.title}</h3>
                  <div className="mt-2 flex items-center gap-4 text-xs font-mono text-slate-500 tracking-wider">
                     <span className="flex items-center gap-1.5"><Icon name="folder" size={14} /> {(game.size_gb || 0).toFixed(1)} GB</span>
                     <span className="flex items-center gap-1.5 truncate"><Icon name="terminal" size={14} /> {game.executable ? game.executable.split('\\').pop() : 'N/A'}</span>
                  </div>

                  <div className="mt-8 flex items-center gap-3">
                     <button
                        onClick={() => playGame(game.executable)}
                        onContextMenu={(e) => { e.preventDefault(); createShortcut(game); }}
                        title="Iniciar (botão direito = criar atalho)"
                        className="flex-1 h-12 bg-[#a4e6ff]/10 hover:bg-[#a4e6ff]/20 text-[#a4e6ff] hover:text-white rounded-xl px-4 font-bold tracking-widest text-xs uppercase flex items-center justify-center gap-3 transition-colors overflow-hidden relative group/btn border border-[#a4e6ff]/20 cursor-pointer"
                     >
                        <Icon name="play_arrow" size={16} className="relative z-10" />
                        <span className="relative z-10 drop-shadow-md">Iniciar</span>
                        <div className="absolute inset-0 opacity-0 group-hover/btn:opacity-10 bg-gradient-to-r from-transparent via-[#a4e6ff] to-transparent -translate-x-full group-hover/btn:animate-[shimmer_1s_infinite]" />
                     </button>

                     <button
                        onClick={() => openFolder(game.install_path, game.executable)}
                        onContextMenu={(e) => { e.preventDefault(); changeExe(game); }}
                        title="Abrir pasta (botão direito = trocar exe)"
                        className="h-12 w-12 shrink-0 bg-white/[0.03] hover:bg-white/[0.08] text-slate-400 hover:text-white rounded-xl flex items-center justify-center transition-all group/folder border border-white/5 cursor-pointer"
                     >
                        <Icon name="folder_open" size={18} className="group-hover/folder:scale-110 transition-transform" />
                     </button>

                     <button
                        onClick={() => removeGame(game)}
                        onContextMenu={(e) => { e.preventDefault(); invoke('remove_shortcut', { title: game.title }).catch(() => {}); }}
                        title="Desinstalar (botão direito = remover atalho)"
                        className="h-12 w-12 shrink-0 bg-red-500/10 hover:bg-red-500 hover:text-white text-red-500 rounded-xl flex items-center justify-center transition-all group/del border border-red-500/20 cursor-pointer"
                     >
                        <Icon name="delete" size={18} className="group-hover/del:scale-110 transition-transform" />
                     </button>
                  </div>
               </div>
            </div>
         ))}
       </div>
    </div>
  );
}

