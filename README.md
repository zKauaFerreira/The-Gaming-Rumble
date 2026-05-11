<div align="center">

[![GR-Link Banner](public/favicon.png)](#)

# 🎮 GR-Link

> **Catálogo e ponte inteligente para o Gaming Rumble App** — exibe o acervo de jogos disponíveis, permite busca e filtragem, e ao baixar abre diretamente o app nativo via protocolo customizado.

[![React](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-007ACC?style=for-the-badge&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Vite](https://img.shields.io/badge/Vite-646CFF?style=for-the-badge&logo=vite&logoColor=white)](https://vitejs.dev/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)
[![shadcn/ui](https://img.shields.io/badge/shadcn%2Fui-000000?style=for-the-badge&logo=shadcnui&logoColor=white)](https://ui.shadcn.com/)
[![Bun](https://img.shields.io/badge/Bun-000000?style=for-the-badge&logo=bun&logoColor=white)](https://bun.sh/)
[![Vercel](https://img.shields.io/badge/Vercel-000000?style=for-the-badge&logo=vercel&logoColor=white)](https://vercel.com/)

[![Build Status](https://img.shields.io/badge/build-passing-brightgreen?style=for-the-badge)](https://github.com/)
[![License](https://img.shields.io/badge/License-MIT-yellowgreen?style=for-the-badge)](#-licença)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen?style=for-the-badge)](#-contribuindo)
[![Made with ❤️](https://img.shields.io/badge/Made%20with-%E2%9D%A4-red?style=for-the-badge)](.)

</div>

---

## 📋 Índice

<details open>
<summary><b>Clique para expandir/recolher</b></summary>

- 📖 [Sobre o Projeto](#-sobre-o-projeto)
- ✨ [Funcionalidades](#-funcionalidades)
- 🧱 [Arquitetura](#-arquitetura)
- 🔀 [Rotas](#-rotas)
- 🚀 [Pré-requisitos](#-pré-requisitos)
- 📦 [Instalação](#-instalação)
- 💻 [Executando o Projeto](#-executando-o-projeto)
- 🧪 [Build de Produção](#-build-de-produção)
- 🌍 [Variáveis de Ambiente](#-variáveis-de-ambiente)
- ⏰ [Cron Job — Atualização do Catálogo](#-cron-job--atualização-do-catálogo)
- 📡 [Como Funciona o Deep Link](#-como-funciona-o-deep-link)
- 🧩 [Exemplo de Payload](#-exemplo-de-payload)
- 🗂️ [Estrutura do Projeto](#️-estrutura-do-projeto)
- 🤝 [Contribuindo](#-contribuindo)
- 📄 [Licença](#-licença)

</details>

---

## 📖 Sobre o Projeto

O **GR-Link** tem dois papéis principais:

**1. Catálogo de Jogos** — exibe o acervo completo do Gaming Rumble com busca por nome, filtros de ordenação e paginação. Cada jogo tem um modal com requisitos de sistema, arquivos incluídos, preço na Steam e botão de compartilhamento.

**2. Ponte de Deep Link** — quando um usuário acessa um link de download gerado pelo app, o GR-Link decodifica o payload comprimido, tenta abrir o app nativo via protocolo `gaming-rumble://` e oferece fallback elegante caso o app não esteja instalado.

O catálogo é **atualizado diariamente de forma automática** via cron job na Vercel, buscando os dados mais recentes direto do repositório do Gaming Rumble.

---

## ✨ Funcionalidades

| Feature | Descrição |
|:---:|---|
| 📚 | **Catálogo completo** — +1.700 jogos com capa, descrição, tamanho e número de arquivos |
| 🔍 | **Busca com ranking** — prioriza correspondência exata > prefixo > palavra > parcial |
| 🗂️ | **Filtros de ordenação** — A→Z, Z→A, mais recente, mais antigo, maior, menor |
| 📄 | **Paginação via URL** — `/page/10` preserva a página no histórico do navegador |
| 🪟 | **Modal de detalhes** — requisitos do sistema traduzidos (EN→PT), arquivos, preço Steam |
| 🔗 | **URLs canônicas de jogo** — `/game/ark-nova` abre o modal; `?download` dispara o protocolo |
| 📋 | **Compartilhamento** — copia link com `?download` para enviar a outros usuários |
| 🔐 | **Decodificação zlib+Base64** — payload compactado e seguro via URL |
| 🚀 | **Auto-open via protocolo customizado** — abre o app nativo automaticamente |
| ⏱️ | **Fallback inteligente** — detecta em 1,5s se o app não abriu e exibe alternativas |
| 🪟 | **Auto-close tab** — fecha a aba automaticamente 5s após o app abrir |
| ⏰ | **Cron automático** — catálogo sincronizado diariamente às 17h (BRT) via Vercel |
| 📱 | **100% responsivo** — funciona em desktop e mobile |

---

## 🧱 Arquitetura

```
┌──────────────────────────────────────────────────────────┐
│                        Browser                           │
│                                                          │
│   /page/:page  ──────►  GameCatalog                      │
│   /game/:slug  ──────►  GameCatalog + GameModal          │
│   /?data=...   ──────►  Index (deep link)                │
│                                                          │
│  ┌─────────────────────────────────────────────────┐     │
│  │                 GameCatalog                     │     │
│  │  useQuery → Vercel Blob (games.json)            │     │
│  │  searchGames() → ranking por relevância         │     │
│  │  sortGames()   → 6 critérios de ordenação       │     │
│  │  GameCard[]  ──► onExpand ──► GameModal         │     │
│  └─────────────────────────────────────────────────┘     │
│                                                          │
│  ┌─────────────────────────────────────────────────┐     │
│  │                  Index (/?data=)                │     │
│  │  Base64 url-safe → unzlibSync (fflate)          │     │
│  │  JSON.parse → MapShortKeys → GameData           │     │
│  │  gaming-rumble://btoa(JSON)                     │     │
│  │       │                                         │     │
│  │   ✅ App abriu          ❌ App ausente           │     │
│  │   → "opened" state     → "fallback" state       │     │
│  │   → auto-close         → botões manuais          │     │
│  └─────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│                     Vercel (Serverless)                  │
│                                                          │
│  Cron: 0 20 * * * (17h BRT)                             │
│    └─► GET /api/cron                                     │
│            │                                             │
│            ▼                                             │
│  GitHub raw (online_fix_games.json)                      │
│            │                                             │
│            ▼                                             │
│  Vercel Blob ──► games.json (allowOverwrite)             │
└──────────────────────────────────────────────────────────┘
```

---

## 🔀 Rotas

| Rota | Comportamento |
|:---|:---|
| `/` ou `/?data=<payload>` | Deep link — decodifica payload e abre o app |
| `/page/:page` | Catálogo paginado (ex: `/page/3`) |
| `/game/:slug` | Catálogo com modal do jogo aberto (ex: `/game/ark-nova`) |
| `/game/:slug?download` | Redireciona internamente para `/?data=` com o payload do jogo |

> Páginas fora do intervalo são automaticamente redirecionadas para a última página disponível.

---

## 🚀 Pré-requisitos

| Dependência | Versão | Download |
|:---:|:---:|:---:|
| **[Node.js](https://nodejs.org/)** | `>= 18.0.0` | [📥 Baixar](https://nodejs.org/en/download) |
| **[Bun](https://bun.sh/)** | `>= 1.0` | [📥 Baixar](https://bun.sh) |

```bash
node --version    # v18.x+
bun --version     # 1.x+
```

---

## 📦 Instalação

### 1️⃣ Clone o repositório

```bash
git clone https://github.com/zKauaFerreira/gr-link.git
```

### 2️⃣ Entre no diretório

```bash
cd gr-link
```

### 3️⃣ Instale as dependências

```bash
bun install
```

---

## 💻 Executando o Projeto

```bash
bun dev
```

> ⚡ O servidor será iniciado em `http://localhost:8080` com **Hot Module Replacement (HMR)** ativado.

---

## 🧪 Build de Produção

```bash
# Build otimizado para produção
bun run build

# Preview do build
bun run preview

# Build em modo debug
bun run build:dev
```

O conteúdo gerado ficará na pasta `dist/`, pronto para deploy na Vercel. 🌐

---

## 🌍 Variáveis de Ambiente

Configure as seguintes variáveis no painel da Vercel (**Settings → Environment Variables**):

| Variável | Obrigatória | Descrição |
|:---|:---:|:---|
| `BLOB_READ_WRITE_TOKEN` | ✅ | Token de leitura/escrita do Vercel Blob (gerado em **Storage → seu blob → Settings**) |
| `CRON_SECRET` | ✅ | Segredo arbitrário que a Vercel injeta automaticamente no header `Authorization` de cada invocação do cron |

> ⚠️ Sem o `BLOB_READ_WRITE_TOKEN`, o cron irá falhar ao tentar sobrescrever o `games.json`.

---

## ⏰ Cron Job — Atualização do Catálogo

O catálogo é sincronizado automaticamente **todo dia às 17h (horário de Brasília)** pela função serverless `/api/cron`.

**Fluxo:**

```
Vercel Scheduler (17h BRT / 20h UTC)
    │
    ▼
GET /api/cron
    │  Authorization: Bearer <CRON_SECRET>
    ▼
Fetch: github.com/.../online_fix_games.json
    │
    ▼
Vercel Blob: put("games.json", body, { allowOverwrite: true })
    │
    ▼
{ ok: true, updatedAt: "..." }
```

A função pode ser invocada manualmente também, bastando enviar a requisição com o header correto.

---

## 📡 Como Funciona o Deep Link

### 🔗 URL de Acesso

```
https://seusite.com/?data=<zlib_base64url_encoded_json>
```

O payload codificado contém informações do jogo comprimidas com **zlib** e transformadas para **URL-safe Base64**:

| Chave Curta | Chave Completa | Exemplo |
|:---:|:---:|:---|
| `t` | `title` | `"Cyberpunk 2077"` |
| `b` | `banner` | `"https://cdn.exemplo.com/banner.jpg"` |
| `p` | `parts` | `3` |
| `s` | `fileSize` | `"65.2 GB"` |
| `m` | `magnet` | `"magnet:?xt=urn:btih:..."` |

### 🔄 Fluxo Completo

```
1. Usuário clica em /game/cyberpunk-2077?download
2. GR-Link encontra o jogo no catálogo pelo slug
3. Codifica os dados → zlib + Base64url → redireciona para /?data=...
4. Decodifica e exibe banner, título, tamanho e nº de arquivos
5. Tenta abrir gaming-rumble://base64_json
   │
   ├─ ✅ App instalado → marca "opened" → fecha aba em 5s
   └─ ❌ App ausente  → mostra fallback (botão "Abrir no App" + copiar Magnet)
```

---

## 🧩 Exemplo de Payload

<details>
<summary>🔨 <b>Como gerar um payload de teste</b></summary>

Execute no **console do navegador** (F12):

```javascript
// Usando fflate (já incluso no projeto)
import { zlibSync } from 'fflate';

const game = {
  t: "Meu Jogo Incrível",
  b: "https://via.placeholder.com/800x400?text=Banner",
  p: 2,
  s: "45.5 GB",
  m: "magnet:?xt=urn:btih:exemplo123456789"
};

const bytes = new TextEncoder().encode(JSON.stringify(game));
const compressed = zlibSync(bytes);
const b64 = btoa(String.fromCharCode(...compressed));
const urlSafe = b64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

console.log(`http://localhost:8080/?data=${urlSafe}`);
```

</details>

---

## 🗂️ Estrutura do Projeto

```
gr-link/
├── 📁 api/
│   └── cron.ts             # ⏰ Serverless function — atualiza o catálogo no Blob
├── 📁 src/
│   ├── 📁 assets/
│   │   └── icon.png        # Ícone do Gaming Rumble
│   ├── 📁 components/
│   │   ├── GameCatalog.tsx # 📚 Catálogo completo (busca, filtros, paginação)
│   │   ├── GameModal.tsx   # 🪟 Modal de detalhes do jogo
│   │   └── ui/             # Componentes shadcn/ui (sonner, tooltip)
│   ├── 📁 pages/
│   │   ├── Index.tsx       # 🔗 Deep link — decode + protocolo + fallback
│   │   └── NotFound.tsx    # ❌ Página 404
│   ├── 📁 lib/
│   │   ├── games.ts        # 🛠️ Tipos, slugify, sort, search, encode utilities
│   │   ├── translations.json # 🌐 Traduções EN→PT para requisitos de sistema
│   │   └── utils.ts        # Função cn() para classes Tailwind
│   ├── App.tsx             # ⚙️ Router, QueryClient, Providers
│   ├── index.css           # 🎨 Tailwind + variáveis CSS + animações custom
│   ├── main.tsx            # 🚀 Entry point do React
│   └── vite-env.d.ts       # Tipos do ambiente Vite
├── 📁 public/              # Assets públicos (favicon, robots.txt)
├── vercel.json             # ⚙️ Configuração Vercel — cron schedule
├── index.html              # HTML raiz
├── vite.config.ts          # ⚡ Configuração do Vite
├── tailwind.config.ts      # 🎨 Configuração do Tailwind CSS
├── tsconfig.json           # ⌨️ Referência TypeScript
├── eslint.config.js        # 🔍 Configuração ESLint
├── components.json         # 🧩 Configuração shadcn/ui
└── package.json            # 📦 Dependências e scripts
```

---

## 🤝 Contribuindo

Contribuições são **super bem-vindas**! Siga os passos abaixo:

### 1. 🔀 Faça um Fork do projeto

```bash
git clone https://github.com/zKauaFerreira/gr-link.git
cd gr-link
```

### 2. 🌿 Crie uma branch para sua feature

```bash
git checkout -b feature/MinhaFeature
```

### 3. ✍️ Faça suas alterações

```bash
bun install
bun dev
```

### 4. ✅ Verifique se tudo funciona

```bash
# Lint
bun run lint

# Type check
bun run tsc --noEmit

# Build
bun run build
```

### 5. 💾 Commit suas mudanças

```bash
git add .
git commit -m "feat: adiciona minha feature incrível"
```

### 6. 📤 Faça o Push e abra um PR

```bash
git push origin feature/MinhaFeature
```

> 🙏 Obrigado por contribuir! Toda PR é revisada com carinho.

<details>
<summary>📝 <b>Convenções de Commit</b></summary>

| Tipo | Descrição | Exemplo |
|:---:|---|:---|
| `feat` | Nova funcionalidade | `feat: adiciona filtro por gênero` |
| `fix` | Correção de bug | `fix: decode falhando com payload vazio` |
| `style` | Mudanças visuais | `style: melhora animação do modal` |
| `refactor` | Refatoração | `refactor: simplifica fluxo de fallback` |
| `docs` | Documentação | `docs: atualiza README com variáveis de ambiente` |
| `chore` | Manutenção | `chore: atualiza dependências` |

</details>

---

## 📄 Licença

<div align="center">

### 📜 [MIT License](LICENSE)

**GR-Link — Catálogo e ponte inteligente para o Gaming Rumble App**

Copyright © 2025 — Todos os direitos reservados.

> ⚖️ Este projeto é distribuído sob a licença MIT, o que significa que você pode:
>
> - ✅ Usar comercialmente
> - ✅ Modificar
> - ✅ Distribuir
> - ✅ Usar privadamente
>
> ⚠️ **Sem garantias** — use por sua conta e risco.

</div>

---

<div align="center">

Feito com 💙 e muito ☕ pelo time **Gaming Rumble**

[![React](https://img.shields.io/badge/React-%2320232a.svg?style=flat&logo=react&logoColor=%2361DAFB)](#)
[![TypeScript](https://img.shields.io/badge/TypeScript-%23007ACC.svg?style=flat&logo=typescript&logoColor=white)](#)
[![TailwindCSS](https://img.shields.io/badge/Tailwind_CSS-%2338B2AC.svg?style=flat&logo=tailwindcss&logoColor=white)](#)
[![shadcn/ui](https://img.shields.io/badge/shadcn%2Fui-000000?style=flat&logo=shadcnui&logoColor=white)](#)
[![Vite](https://img.shields.io/badge/Vite-%23646CFF.svg?style=flat&logo=vite&logoColor=white)](#)
[![Vercel](https://img.shields.io/badge/Vercel-%23000000.svg?style=flat&logo=vercel&logoColor=white)](#)

⭐ **Deixe uma star se o projeto te ajudou!** ⭐

</div>
