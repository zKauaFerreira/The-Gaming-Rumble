# 🎮 Gaming Rumble (GR-Link)

<p align="center">
  <img src="https://raw.githubusercontent.com/zKauaFerreira/The-Gaming-Rumble/refs/heads/main/public/banner.png" alt="Gaming Rumble Banner" width="100%" />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB" />
  <img src="https://img.shields.io/badge/Vite-646CFF?style=for-the-badge&logo=vite&logoColor=white" />
  <img src="https://img.shields.io/badge/TypeScript-007ACC?style=for-the-badge&logo=typescript&logoColor=white" />
  <img src="https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white" />
  <img src="https://img.shields.io/badge/Vercel-000000?style=for-the-badge&logo=vercel&logoColor=white" />
</p>

<br>

> O frontend definitivo para o ecossistema Gaming Rumble. Um catálogo de jogos de alto desempenho, focado em UX, com integração profunda via Deep Links e sincronização automatizada.

---

## 📋 Índice

- 🚀 [Recursos Principais](#-recursos-principais)
- 🔀 [Sistema de Rotas e Redirecionamento](#-sistema-de-rotas-e-redirecionamento)
- 🧱 [Arquitetura e Fluxo de Dados](#-arquitetura-e-fluxo-de-dados)
- 📡 [Protocolo gaming-rumble:// (Deep Link)](#-protocolo-gaming-rumble-deep-link)
- 🛠️ [Guia de Desenvolvimento](#️-guia-de-desenvolvimento)
- 🌍 [Variáveis de Ambiente](#-variáveis-de-ambiente)
- 📁 [Estrutura do Projeto](#-estrutura-do-projeto)
- 📜 [Licença](#-licença)

---

## 🚀 Recursos Principais

### 🖥️ Interface de Usuário (UI/UX)
- **Grid Ultra-Wide:** Otimizado para monitores de alta performance, exibindo até 10 jogos por linha em 4K.
- **Design "Glassmorphism":** Cabeçalho e rodapé com efeitos de desfoque (backdrop-blur) e transparência.
- **Barra de Status Inteligente:** Rodapé dinâmico que exibe saúde do banco (`match_rate`), total de torrents e build, com animação de auto-hide para não obstruir a navegação.
- **Badges de Status:** Identificadores visuais para jogos recém-adicionados (`NOVO`) e atualizados (`UPD`).

### 🔍 Exploração e Busca
- **Busca por Info Hash:** Permite colar o Hash do torrent diretamente na busca para localizar o jogo instantaneamente.
- **Ranking de Relevância:** Algoritmo de busca que prioriza correspondências exatas e prefixos sobre correspondências parciais.
- **Ordenação Inteligente:** Filtros por Data de Lançamento, Tamanho de Arquivo e Ordem Alfabética.

### 📦 Gestão de Downloads
- **Sistema Colapsável:** Modais limpos que escondem listas longas de arquivos ou múltiplos providers de download direto.
- **Normalização de Links:** Utilitário `ensureProtocol` que corrige URLs malformadas garantindo que o redirecionamento sempre funcione.
- **Deep Link Bridge:** Telas de espera que enriquecem os dados básicos com metadados do banco de dados (Tags, Banners HD).

---

## 🔀 Sistema de Rotas e Redirecionamento

O site utiliza o `react-router-dom` para gerenciar um fluxo de navegação híbrido:

| Rota | Descrição Técnica |
|---|---|
| `/page/:page` | Exibe o catálogo. Faz o "clamping" automático (ex: se pedir página 999, vai para a última disponível). |
| `/game/:id` | **Rota Dual:** Se `:id` for um slug (nome), abre o modal. Se for um Hash (40 chars), resolve o jogo e redireciona a URL para o slug. |
| `/game/:slug?download` | Gatilho silencioso: codifica os dados, envia para a bridge e abre o app nativo. |
| `/?data=<payload>` | Rota de processamento de Deep Link via parâmetro de busca. |
| `/d/:id` | Redirecionador curto amigável para uso em bots do Discord. |

---

## 🧱 Arquitetura e Fluxo de Dados

### Sincronização Serverless
O site não possui um banco de dados SQL tradicional. Ele utiliza o **Vercel Blob** como um armazenamento de objetos ultrarrápido, alimentado por um cron job.

1.  **Trigger:** Vercel Cron aciona `/api/cron` a cada 24h.
2.  **Ingestão:** A função serverless baixa o `online_fix_games.json` e o `stats.json` direto do repositório de dados no GitHub.
3.  **Processamento:** Os dados são validados e salvos no Blob Storage com `allowOverwrite: true`.
4.  **Consumo:** O cliente React usa `TanStack Query` para buscar esses arquivos, aplicando uma camada de cache de 5 minutos e **Cache-Busting** (`?t=...`) para ignorar caches de CDN.

### Diagrama de Sequência de Download
```mermaid
sequenceDiagram
    User->>Site: Clica em "Baixar"
    Site->>Site: Serializa JSON do Jogo (Base64)
    Site->>Browser: Abre URL customizada gaming-rumble://[b64]
    Browser->>OS: Identifica Protocolo Registrado
    OS->>App Nativo: Passa o payload Base64
    App Nativo->>User: Exibe tela de download com Magnet e Hosters
```

---

## 📡 Protocolo `gaming-rumble://` (Deep Link)

### Estrutura do Payload (V2)
O payload enviado ao app nativo é um objeto JSON codificado em Base64 URL-safe.

```typescript
interface ProtocolPayload {
  title: string;      // Nome do jogo
  banner: string;     // URL da imagem de cabeçalho
  parts: number;      // Quantidade de arquivos/partes
  fileSize: string;   // Tamanho formatado (ex: "10 GB")
  magnet: string;     // Link magnet completo
  hash: string;       // Info Hash completo do torrent
  h?: {               // Opcional: Download Direto
    [provider: string]: Array<{
      n: string;      // Nome do arquivo
      u: string;      // URL direta
    }>
  }
}
```

### Exemplo de Implementação (Site)
```javascript
const json = JSON.stringify(payload);
// Unescape/Encode garante suporte a caracteres UTF-8 (acentos, etc)
const b64 = btoa(unescape(encodeURIComponent(json)));
window.location.href = `gaming-rumble://${b64}`;
```

---

## 🛠️ Guia de Desenvolvimento

### Stack Tecnológica
- **Framework:** React 18 com Vite (SWC)
- **Estilização:** Tailwind CSS + `tailwindcss-animate`
- **Estado Global/Server:** TanStack Query V5 (SWR pattern)
- **Utilidades:** `fflate` (compressão zlib), `lucide-react` (ícones)

### Comandos Úteis
| Comando | Descrição |
|---|---|
| `bun dev` | Inicia o servidor de desenvolvimento em `localhost:8080` |
| `bun run build` | Gera a build otimizada na pasta `dist/` |
| `bun run lint` | Executa o ESLint para verificar padrões de código |
| `bun run tsc` | Executa a verificação de tipos do TypeScript |

---

## 🌍 Variáveis de Ambiente

O arquivo `.env` deve ser configurado para que o site saiba onde buscar os dados.

```env
# URL do JSON principal (Vercel Blob ou GitHub)
VITE_GAMES_API_URL=https://mkuqgpwafiakxxi1.public.blob.vercel-storage.com/games.json

# URL do JSON de estatísticas (Opcional)
VITE_STATS_API_URL=https://mkuqgpwafiakxxi1.public.blob.vercel-storage.com/stats.json

# Apenas para a Vercel (API/Cron)
BLOB_READ_WRITE_TOKEN=vercel_blob_rw_...
CRON_SECRET=seu_segredo_aqui
```

---

## 📁 Estrutura do Projeto

```txt
gr-link/
├── api/
│   ├── cron.ts            # Sincronizador atômico (Games + Stats)
│   └── update-games.js    # Fallback/Update manual
├── src/
│   ├── components/
│   │   ├── GameCatalog.tsx # O "coração" do site (Grid, Header, Footer)
│   │   ├── GameModal.tsx   # Modal detalhado com lógica de colapso
│   │   └── ui/             # Primitivos de UI (Tooltip, Sonner, etc)
│   ├── lib/
│   │   ├── games.ts        # Business Logic, Sorting e Protocol Schema
│   │   └── translations.json # Engine de tradução para requisitos
│   ├── pages/
│   │   ├── Index.tsx       # Landing/Bridge principal (?data=)
│   │   └── ShortLink.tsx   # Bridge para links curtos (/d/)
│   └── ...
├── vercel.json             # Agendamento de cron e regras de SPA
└── ...
```

---

## 📜 Licença

Este software é fornecido "como está", para fins educacionais e de demonstração técnica.

Consulte o arquivo [LICENSE](LICENSE) para mais detalhes sobre permissões e restrições.

---
<p align="center">Feito com ❤️ pela comunidade Gaming Rumble</p>
