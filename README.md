# <p align="center">Gaming Rumble</p>

<p align="center">
  <img src="public/logo.svg" alt="Gaming Rumble" width="128" height="128">
</p>

<p align="center">
  Launcher desktop para instalação automatizada de jogos via magnet link.
</p>

---

## Sobre

Gaming Rumble é um client desktop construído com **Tauri 2 + React** que automatiza todo o processo de download, extração e organização de jogos. Basta abrir um link compatível e o app cuida do resto — sem intervenção manual.

## ⚠️ Compatibilidade

> **Este client funciona exclusivamente com magnet links do [online-fix.me](https://online-fix.me).**
>
> Magnets de outras fontes (1337x, RARBG, TorrentGalaxy, etc.) **não são suportados** e podem causar erros ou comportamento inesperado. Não há suporte para fontes alternativas.

## Como funciona

### Fluxo completo

| Etapa | Descrição |
|-------|-----------|
| **1. Deep Link** | O app recebe `gaming-rumble://[base64]` com título, banner, magnet e tamanho |
| **2. Setup** | Confirmação do caminho de instalação e verificação de espaço em disco |
| **3. Download** | aria2c baixa via BitTorrent com progresso, velocidade e ETA em tempo real |
| **4. Extração** | 7-Zip (sistema ou auto-baixado) extrai partes `.rar`, aplica patches e fixes |
| **5. Biblioteca** | Jogo adicionado à lista com atalho no Menu Iniciar criado automaticamente |

### Funcionalidades

- Download via BitTorrent com trackers otimizados
- Extração automática com senha `online-fix.me`
- Detecção inteligente do executável principal do jogo
- Criação de atalho no Menu Iniciar
- Biblioteca persistente com play/uninstall
- Sistema de pausa/retomada de downloads
- Verificação de espaço em disco antes de baixar
- Suporte a jogos multi-partes com aplicação de fix

## Stack Tecnológica

### Frontend
| Tecnologia | Uso |
|---|---|
| React 19 | Interface |
| TypeScript | Tipagem |
| Tailwind CSS 4 | Estilização |
| Framer Motion 12 | Animações |
| Material Symbols | Ícones |
| Vite 7 | Bundler |

### Backend (Tauri 2)
| Dependência | Uso |
|---|---|
| sysinfo | Listagem de discos e espaço |
| reqwest | Download do aria2c e 7-Zip |
| tokio | Runtime async |
| sevenz-rust | Extração de arquivos (fallback) |
| serde / serde_json | Serialização JSON |
| tauri-plugin-deep-link | Protocolo `gaming-rumble://` |
| tauri-plugin-single-instance | Evita múltiplas instâncias |

### Binários Externos
| Binário | Uso |
|---|---|
| aria2c.exe | Bundled — download via BitTorrent |
| 7z.exe | System (`C:\Program Files\7-Zip`) ou baixado automaticamente do ip7z/7zip |

## 🎮 Como obter o link

Os magnet links são obtidos exclusivamente em [**online-fix.me**](https://online-fix.me). Para utilizar no Gaming Rumble:

1. Copie o magnet link do jogo desejado
2. Monte o payload JSON no formato esperado
3. Converta para Base64 e abra via `gaming-rumble://[base64]`

> O site **não** aciona o protocolo automaticamente — o link precisa ser construído e convertido manualmente.

## Pré-requisitos

- **Node.js** (última versão LTS)
- **Rust** (via [rustup](https://rustup.rs/))
- **Windows 10/11** (única plataforma suportada)

## Instalação e Desenvolvimento

```bash
# Instalar dependências
npm install

# Rodar em modo desenvolvimento
npm run tauri dev

# Build para produção
npm run tauri build
```

## Estrutura do Projeto

```
Gaming Rumble/
├── src/                          # Frontend React
│   ├── App.tsx                   # Componente raiz
│   ├── types.ts                  # Interfaces TypeScript
│   ├── payload.ts                # Encode/decode de payloads Base64
│   └── components/
│       ├── Icon.tsx              # Wrapper Material Symbols
│       ├── Layout/               # Header e Footer
│       └── Views/                # Setup, Activity, Library, Settings
├── src-tauri/                    # Backend Rust (Tauri 2)
│   ├── src/commands/             # Comandos invocados pelo frontend
│   │   ├── system.rs             # Admin check, Defender, play_game
│   │   ├── disk.rs               # Listagem de drives
│   │   ├── torrent.rs            # Controle do aria2c
│   │   ├── archive.rs            # Extração 7z, flatten, cleanup
│   │   └── library.rs            # CRUD da biblioteca
│   └── tauri.conf.json           # Configuração do app
├── public/logo.svg               # Ícone do app
└── .github/workflows/build.yml   # CI — build automático na main
```

## Protocolo `gaming-rumble://`

O app registra o protocolo `gaming-rumble://` no sistema operacional. Quando um link é aberto (via navegador, Discord, etc.), o payload Base64 é decodificado:

```json
{
  "title": "Nome do Jogo",
  "banner": "https://shared.akamai.steamstatic.com/.../header.jpg",
  "parts": 4,
  "fileSize": "551.10 MB",
  "magnet": "magnet:?xt=urn:btih:..."
}
```

## Build

### Local

```bash
npm run tauri build
```

Os binários são gerados em:
- `src-tauri/target/release/bundle/msi/` — instalador MSI
- `src-tauri/target/release/bundle/nsis/` — instalador NSIS

### Automático (CI)

Um workflow GitHub Actions faz build automático a cada push na branch `main`. Os artifacts ficam disponíveis na aba **Actions** do repositório.

---

## ⚖️ Aviso Legal

> **Este software é disponibilizado "AS IS", sem garantias de qualquer tipo.**
>
> - Este client **não possui**, **não hospeda**, **não distribui** e **não facilita** o acesso a qualquer conteúdo protegido por direitos autorais.
> - Os magnet links são consumidos via protocolo `gaming-rumble://` e o app apenas automatiza o processo técnico de download e extração.
> - **Não ofereço suporte** para problemas relacionados ao conteúdo obtido — uso por conta e risco do usuário.
> - **Não respondo** por violações de direitos autorais, danos diretos, indiretos ou incidentais que possam surgir do uso deste software.
> - Ao utilizar este client, você concorda em assumir toda a responsabilidade pelo conteúdo que acessar e instalar.

---

<p align="center">Gaming Rumble Engine © 2026 — Todos os direitos reservados.</p>
