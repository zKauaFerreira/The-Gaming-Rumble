import sys
import io
import argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # no Actions não precisa, usa env vars nativas

import random
import math
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
try:
    import cloudscraper
    HAS_CLOUDSCRAPER = True
except ImportError:
    HAS_CLOUDSCRAPER = False
from bs4 import BeautifulSoup
import json
import hashlib
import base64
import bencode
from urllib.parse import quote, urljoin
import re
import os
import time
from datetime import datetime
from rapidfuzz import fuzz  # Para matching de strings
try:
    import psutil
except ImportError:
    psutil = None

# ==========================================
# CONFIGURAÇÕES — via env vars no GitHub Actions
# ==========================================
USER          = os.getenv("ONLINEFIX_USER", "")
PASS          = os.getenv("ONLINEFIX_PASS", "")
BASE_URL      = "https://online-fix.me/"
WEBDAV_ROOT   = "https://uploads.online-fix.me:2053/torrents/"
TORRENT_DIR   = "torrents"
DEFAULT_GITHUB_REPO = "zKauaFerreira/The-Gaming-Rumble"
DEFAULT_GITHUB_BRANCH = "games"
GITHUB_REPO   = os.getenv("GITHUB_REPOSITORY", DEFAULT_GITHUB_REPO)
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", DEFAULT_GITHUB_BRANCH)
RAW_BASE_URL  = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{TORRENT_DIR}/"
PROXY_LIST_URL = os.getenv("PROXY_LIST_URL")

HEADERS = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    "referer": BASE_URL,
}

WEBDAV_HEADERS = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "referer": BASE_URL,
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-site",
    "upgrade-insecure-requests": "1",
}

WEBDAV_OPTIONAL_TRAILING_WORDS = {
    "online",
    "arcade",
    "overdrive",
}


class OnlineFixScraper:
    def __init__(self, base_url=None):
        self.base_url = base_url or BASE_URL
        if HAS_CLOUDSCRAPER:
            self.session = cloudscraper.create_scraper(
                browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
            )
            print("Cloudscraper ativado.")
        else:
            self.session = requests.Session()

        self.session.headers.update(HEADERS)
        self.logged_in = False
        self._match_guard = self._load_match_guard_model()
        self._match_aliases = self._load_match_guard_aliases()

        # Gerenciador de Proxy
        self.proxies_list = []
        self.proxy_index = 0
        self.proxy_lock = __import__('threading').Lock()
        self._load_proxies()

        # Carregar catálogo Steam local
        self._steam_catalog = self._load_steam_catalog()

        # Criar índices para lookup O(1) - armazenar todos os apps por nome normalizado
        self._steam_index = {}
        self._inverted_index = {}
        if self._steam_catalog:
            for app in self._steam_catalog:
                name = app.get('name', '')
                if name:
                    norm_name = self._normalize(name)
                    # Armazenar todos os apps por nome normalizado
                    if norm_name not in self._steam_index:
                        self._steam_index[norm_name] = []
                    self._steam_index[norm_name].append({
                        'id': app['appid'],
                        'name': name
                    })

                    # Adicionar também variações comuns para melhorar a busca
                    variations = self._search_variations(name)
                    for variation in variations:
                        if variation != norm_name:
                            if variation not in self._steam_index:
                                self._steam_index[variation] = []
                            # Evitar duplicação do mesmo app para a mesma variação
                            if not any(existing['id'] == app['appid'] for existing in self._steam_index[variation]):
                                self._steam_index[variation].append({
                                    'id': app['appid'],
                                    'name': name
                                })

            # Criar índice invertido para busca mais eficiente
            self._common_words_set = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
                                      "of", "with", "by", "is", "are", "was", "were", "be", "been", "being",
                                      "have", "has", "had", "do", "does", "did", "will", "would", "should",
                                      "could", "may", "might", "must", "can", "of", "edition", "game",
                                      "vr", "online", "simulator", "dlc"}

            for norm_name in self._steam_index.keys():
                for word in self._textual_tokens(norm_name):
                    if word not in self._inverted_index:
                        self._inverted_index[word] = set()
                    self._inverted_index[word].add(norm_name)

    def _load_proxies(self):
        """Baixa e prepara proxies de uma ou mais URLs (separadas por \n ou ;)."""
        if not PROXY_LIST_URL:
            self.proxies_list.append(None) # IP Local de reserva se nenhum proxy configurado
            return

        # Dividir URLs por \n ou ;
        urls = []
        for part in PROXY_LIST_URL.replace(';', '\n').split('\n'):
            url = part.strip()
            if url:
                urls.append(url)

        if not urls:
            self.proxies_list.append(None) # IP Local de reserva
            print("⚠️ Nenhuma URL de proxy válida encontrada em PROXY_LIST_URL")
            return

        all_proxies = []
        for url in urls:
            try:
                r = requests.get(url.strip(), timeout=15)
                if r.status_code == 200:
                    for line in r.text.strip().split('\n'):
                        line = line.strip()
                        if not line:
                            continue
                        parts = line.split(':')
                        if len(parts) == 4:
                            ip, port, user, pw = parts
                            p_url = f"http://{user}:{pw}@{ip}:{port}"
                            all_proxies.append({"http": p_url, "https": p_url})
                        # Ignorar linhas que não estiverem no formato esperado
                else:
                    print(f"⚠️ URL de proxy retornou status {r.status_code}: {url}")
            except Exception as e:
                print(f"⚠️ Erro ao carregar proxies de {url}: {e}")

        if all_proxies:
            self.proxies_list = all_proxies
            self.proxies_list.append(None) # IP Local de reserva
            print(f"✅ Rotação de Proxies ativa: {len(self.proxies_list)} IPs carregados ({len(all_proxies)} de URLs + 1 reserva)")
        else:
            self.proxies_list.append(None) # Apenas IP local de reserva
            print("⚠️ Nenhum proxy válido carregado das URLs. Usando apenas IP local.")

    def _load_steam_catalog(self):
        """Carrega catálogo completo da Steam de steam_applist_full.json"""
        catalog_path = 'steam_applist_full.json'
        if not os.path.exists(catalog_path):
            print("⚠️ Catálogo Steam local não encontrado (steam_applist_full.json). Deseja baixar agora?")
            print("   Você pode obter em: https://api.steampowered.com/ISteamApps/GetAppList/v2/")
            print("   Salve como steam_applist_full.json")
            return []

        try:
            # Usar utf-8-sig para lidar com BOM automaticamente
            data = self._load_json_file(catalog_path)
            apps = data.get('apps', [])
            print(f"✅ Catálogo Steam carregado: {len(apps)} jogos")
            return apps
        except Exception as e:
            print(f"❌ Erro ao carregar catálogo Steam: {e}")
            return []

    def _load_json_file(self, path):
        """Carrega JSON aceitando arquivos com ou sem BOM UTF-8."""
        with open(path, 'r', encoding='utf-8-sig') as f:
            return json.load(f)

    def _search_in_catalog(self, normalized_query, original_name):
        """Robust search in the local Steam catalog.
        Returns up to 20 candidates ordered by a weighted score.
        """
        # ------------------------------------------------------------------
        # 1. Exact lookup – check for exact match first
        # ------------------------------------------------------------------
        exact_candidates = []
        if normalized_query in self._steam_index:
            exact_candidates = self._steam_index[normalized_query]

        # If we find an exact match, validate it semantically before returning
        if exact_candidates:
            result = []
            for app in exact_candidates:
                # Apply semantic checks even to exact matches
                candidate_name = app['name']
                if self._is_canonical_steam_match(original_name, candidate_name):
                    exact_match = app.copy()
                    exact_match['score'] = 100
                    result.append(exact_match)
                    continue

                # Check if keywords are semantically related
                query_parts = set(normalized_query.split())
                candidate_parts = set(self._normalize(candidate_name).split())

                common_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
                               "of", "with", "by", "is", "are", "was", "were", "be", "been", "being",
                               "have", "has", "had", "do", "does", "did", "will", "would", "should",
                               "could", "may", "might", "must", "can", "Edition", "game", "the", "of",
                               "vr", "online", "simulator", "dlc", "hd", "remastered", "complete", "pack"}

                query_keywords = {word for word in query_parts if word not in common_words and len(word) > 2}
                candidate_keywords = {word for word in candidate_parts if word not in common_words and len(word) > 2}

                # Calculate keyword similarity
                keyword_similarity = 0
                if query_keywords and candidate_keywords:
                    keyword_similarity = len(query_keywords.intersection(candidate_keywords)) / max(len(query_keywords), len(candidate_keywords))

                # If semantic similarity is too low, don't accept this exact match
                if query_keywords and candidate_keywords and keyword_similarity < 0.3:
                    # This is a poor semantic match despite being an exact text match in the index
                    continue

                exact_match = app.copy()
                # Apply the same scoring as other matches for consistency
                token_score = fuzz.token_set_ratio(normalized_query, self._normalize(candidate_name))
                partial_score = fuzz.partial_ratio(normalized_query, self._normalize(candidate_name))
                regular_ratio = fuzz.ratio(normalized_query, self._normalize(candidate_name))

                base_fuzzy_score = (0.6 * token_score) + (0.25 * regular_ratio) + (0.15 * partial_score * 0.5)
                final_score = min(base_fuzzy_score, 100)

                if final_score >= 0:  # Only add if not rejected by language check
                    exact_match['score'] = final_score
                    result.append(exact_match)

            if result:
                return result

        # Process exact matches with the same logic as other matches
        # Don't return exact matches immediately - let them go through the same scoring process
        # We'll just skip the exact match check above and let it go to the rest of the logic
        # Actually, let's just remove the early return for exact matches and let everything be scored

        # ------------------------------------------------------------------
        # 2. Extract numeric / year information from the query
        # ------------------------------------------------------------------
        query_number = self._extract_number(original_name)
        query_year = self._extract_year(original_name)

        # ------------------------------------------------------------------
        # 3. Helper: compute a weighted fuzzy score
        # ------------------------------------------------------------------
        def weighted_score(candidate_name, base_fuzzy_score, query_num, query_year):
            score = base_fuzzy_score

            # Verificar se os idiomas são completamente diferentes (ex: inglês vs chinês/japonês/coreano)
            # Se sim, aplicar uma penalidade severa
            query_has_latin = bool(re.search(r'[a-zA-Z]', normalized_query))
            candidate_has_latin = bool(re.search(r'[a-zA-Z]', self._normalize(candidate_name)))
            query_has_cjk = bool(re.search(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]', original_name))  # Chinês/Japonês
            candidate_has_cjk = bool(re.search(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]', candidate_name))  # Chinês/Japonês

            if query_has_latin and candidate_has_cjk and not candidate_has_latin:
                return -100  # Penalidade severa para idiomas completamente diferentes
            if query_has_cjk and candidate_has_latin and not candidate_has_cjk:
                return -100  # Penalidade severa para idiomas completamente diferentes

            # Verificar se as palavras principais são semanticamente diferentes
            # Por exemplo, "DiRT" vs "Dig" são semanticamente diferentes
            query_parts = set(normalized_query.split())
            candidate_parts = set(self._normalize(candidate_name).split())
            query_keywords = set(self._meaningful_tokens(original_name))
            candidate_keywords = set(self._meaningful_tokens(candidate_name))
            query_text_tokens = set(self._textual_tokens(original_name))
            candidate_text_tokens = set(self._textual_tokens(candidate_name))
            keyword_overlap = len(query_keywords.intersection(candidate_keywords))
            text_overlap = len(query_text_tokens.intersection(candidate_text_tokens))

            if query_text_tokens and not candidate_text_tokens and normalized_query != self._normalize(candidate_name):
                return -100
            if query_text_tokens and text_overlap == 0:
                return -100
            if len(query_keywords) >= 2 and keyword_overlap == 0:
                return -100

            if query_keywords and candidate_keywords:
                keyword_similarity = keyword_overlap / max(len(query_keywords), len(candidate_keywords))
                if keyword_similarity < 0.34:
                    score -= 14

            cand_num = self._extract_number(candidate_name)
            cand_numbers = self._extract_numbers(candidate_name)
            query_numbers = self._extract_numbers(original_name)
            cand_year = self._extract_year(candidate_name)

            # Penalidade/Bônus para números
            if query_numbers and cand_numbers:
                if query_numbers == cand_numbers:
                    score += 18
                else:
                    return -100
            elif query_numbers and not cand_numbers:
                score -= 35
            elif not query_numbers and cand_numbers and query_text_tokens:
                score -= 15
            elif query_num is not None and cand_num is not None:
                if query_num == cand_num:
                    score += 12
                else:
                    return -100

            # Penalidade/Bônus para anos
            if query_year is not None and cand_year is not None:
                if query_year == cand_year:
                    score += 10
                else:
                    return -100
            elif query_year is not None and cand_year is None:
                score -= 10

            if len(query_text_tokens) >= 2 and text_overlap < max(1, len(query_text_tokens) // 2):
                score -= 10

            if len(self._normalize(candidate_name)) <= 2 and len(normalized_query) > 4:
                return -100

            # Limitar o score máximo para evitar valores inflados
            score = min(score, 100)
            return score

        # ------------------------------------------------------------------
        # 4. Build candidate list – using inverted index for broader search
        # ------------------------------------------------------------------
        trash_filter = {'demo', 'trailer', 'soundtrack', 'ost', 'server',
                        'test', 'beta', 'alpha', 'gog.com'}

        # Começar com variações da query
        query_variations = self._search_variations(original_name)

        # Coletar candidatos de múltiplas fontes
        candidates = []

        # 1. Candidatos exatos das variações
        for q_variation in query_variations:
            norm_variation = self._normalize(q_variation)
            if norm_variation in self._steam_index:
                app_list = self._steam_index[norm_variation]
                for app in app_list:
                    normalized_app_name = self._normalize(app['name'])
                    token_score = fuzz.token_set_ratio(normalized_query, normalized_app_name)
                    partial_score = fuzz.partial_ratio(normalized_query, normalized_app_name)
                    regular_ratio = fuzz.ratio(normalized_query, normalized_app_name)

                    base_fuzzy_score = (0.6 * token_score) + (0.25 * regular_ratio) + (0.15 * partial_score * 0.5)
                    final_score = weighted_score(app['name'], base_fuzzy_score, query_number, query_year)

                    if final_score >= 60:  # Threshold inicial mais baixo para variações exatas
                        cand = app.copy()
                        cand['score'] = final_score
                        candidates.append(cand)

        # 2. Busca por palavras individuais usando índice invertido
        query_words = self._textual_tokens(original_name)
        for word in query_words:
            if word in self._inverted_index and len(word) > 1:
                for potential_match in self._inverted_index[word]:
                    if potential_match in self._steam_index:
                        app_list = self._steam_index[potential_match]
                        for app in app_list:
                            # Verificar se já não está na lista
                            if not any(c['id'] == app['id'] for c in candidates):
                                token_score = fuzz.token_set_ratio(normalized_query, potential_match)
                                partial_score = fuzz.partial_ratio(normalized_query, potential_match)
                                regular_ratio = fuzz.ratio(normalized_query, potential_match)

                                base_fuzzy_score = (0.6 * token_score) + (0.25 * regular_ratio) + (0.15 * partial_score * 0.5)
                                final_score = weighted_score(app['name'], base_fuzzy_score, query_number, query_year)

                                if final_score >= 65:  # Threshold moderado para matches por palavra
                                    cand = app.copy()
                                    cand['score'] = final_score
                                    candidates.append(cand)

        # 3. Busca fuzzy mais ampla se ainda não tivermos candidatos suficientes
        if len(candidates) < 10:
            for norm_name, app_list in self._steam_index.items():
                for app in app_list:
                    # Filtro básico para evitar buscas excessivamente amplas
                    if abs(len(normalized_query.split()) - len(norm_name.split())) <= 2:
                        token_score = fuzz.token_set_ratio(normalized_query, norm_name)
                        partial_score = fuzz.partial_ratio(normalized_query, norm_name)
                        regular_ratio = fuzz.ratio(normalized_query, norm_name)

                        base_fuzzy_score = (0.6 * token_score) + (0.25 * regular_ratio) + (0.15 * partial_score * 0.5)

                        if base_fuzzy_score >= 50:  # Threshold mais baixo para busca ampla
                            final_score = weighted_score(app['name'], base_fuzzy_score, query_number, query_year)

                            if final_score >= 55:  # Threshold final mais razoável
                                cand = app.copy()
                                cand['score'] = final_score
                                candidates.append(cand)

        # ------------------------------------------------------------------
        # 5. Sort, deduplicate by appid and limit to 20
        # ------------------------------------------------------------------
        seen = set()
        unique = []

        # Filtrar candidatos com scores negativos (matches inválidos de idioma)
        filtered_candidates = [c for c in candidates if c['score'] >= 0]

        for c in sorted(filtered_candidates, key=lambda x: x['score'], reverse=True):
            if c['id'] not in seen:
                seen.add(c['id'])
                unique.append(c)
                if len(unique) >= 20:
                    break
        return unique

    def _get_next_proxy(self):
        if not self.proxies_list: return None
        with self.proxy_lock:
            p = self.proxies_list[self.proxy_index]
            self.proxy_index = (self.proxy_index + 1) % len(self.proxies_list)
            return p

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------
    def login(self):
        print(f"Tentando login como {USER}...")
        try:
            # 1. Carrega a home para garantir cookies de sessão e PHPSESSID
            self.session.get(self.base_url, timeout=15)
            
            # 2. Busca o token dinâmico via AJAX (conforme observado no tráfego)
            token_url = urljoin(self.base_url, "engine/ajax/authtoken.php")
            token_headers = {
                "X-Requested-With": "XMLHttpRequest",
                "referer": self.base_url,
                "accept": "application/json, text/javascript, */*; q=0.01"
            }
            
            try:
                r_token = self.session.get(token_url, headers=token_headers, timeout=15)
                token_data = r_token.json()
                token_field = token_data.get('field')
                token_value = token_data.get('value')
                print(f"Token AJAX obtido: {token_field}")
            except Exception as e:
                print(f"Falha ao obter token via AJAX ({e}), tentando extrair do HTML...")
                r_html = self.session.get(self.base_url, timeout=15)
                soup = BeautifulSoup(r_html.content, 'html.parser', from_encoding='windows-1251')
                token_tag = soup.find('input', {'name': re.compile(r'^token_')})
                if token_tag:
                    token_field = token_tag['name']
                    token_value = token_tag['value']
                else:
                    token_field = None

            if not token_field:
                print("Erro: Não foi possível obter o token de segurança.")
                return False

            # 3. Realiza o POST de login
            payload = {
                "login_name": USER, 
                "login_password": PASS, 
                "login": "submit", 
                "login_form": "login",
                token_field: token_value
            }
            
            resp = self.session.post(self.base_url, data=payload, timeout=15)
            text = resp.content.decode('windows-1251', errors='ignore')
            cookies = {c.name for c in self.session.cookies}

            if USER in text or "Выход" in text or "dle_user_id" in cookies:
                print("Login realizado com sucesso!")
                self.logged_in = True
                return True

            print("Falha no login (credenciais incorretas ou bloqueio remanescente).")
            return False
        except Exception as e:
            print(f"Erro crítico no login: {e}")
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def format_size(self, size_bytes):
        if size_bytes <= 0: return "0 B"
        if size_bytes < 1024 ** 3:
            return f"{size_bytes / 1024 ** 2:.2f} MB"
        return f"{size_bytes / 1024 ** 3:.2f} GB"

    def _set_webdav_cookies(self):
        for cookie in list(self.session.cookies):
            self.session.cookies.set(cookie.name, cookie.value, domain='uploads.online-fix.me')

    def clean_name_for_url(self, title):
        name = re.sub(r'\s*по сети\s*', '', title, flags=re.I).strip()
        # Normaliza diferentes tipos de apóstrofos e aspas para o padrão simples '
        name = name.replace('’', "'").replace('‘', "'").replace('´', "'").replace('`', "'")
        # Remove caracteres problemáticos mas mantém o básico (incluindo o apóstrofo simples)
        name = re.sub(r"[^a-zA-Z0-9\s.'&-]", '', name).strip()
        return name

    def get_max_page(self):
        """Descobre N batches AJAX válidos com conteúdo, retorna N+1 (DOM page 1)."""
        lo, hi = 1, 150
        while lo < hi:
            mid = (lo + hi + 1) // 2
            try:
                resp = self.session.post(self.base_url, data={"show_more": str(mid)},
                                         headers={"X-Requested-With": "XMLHttpRequest"},
                                         timeout=10)
                j = resp.json()
                content = j.get("content", "")
                if content.strip():
                    lo = mid
                else:
                    hi = mid - 1
            except Exception:
                hi = mid - 1
        return lo + 1

    # ------------------------------------------------------------------
    # Torrent metadata
    # ------------------------------------------------------------------
    def get_torrent_metadata(self, torrent_content):
        try:
            decoded = bencode.decode(torrent_content)

            def g(d, key):
                return d.get(key) or d.get(key.encode() if isinstance(key, str) else key.decode())

            info = g(decoded, 'info')
            if not info: return None

            info_encoded = bencode.encode(info)
            btih = hashlib.sha1(info_encoded).hexdigest()
            name_raw = g(info, 'name') or 'unknown'
            name = name_raw.decode('utf-8', errors='ignore') if isinstance(name_raw, bytes) else str(name_raw)
            magnet = f"magnet:?xt=urn:btih:{btih}&dn={quote(name)}"

            trackers = []
            announce = g(decoded, 'announce')
            if announce:
                trackers.append(announce.decode() if isinstance(announce, bytes) else announce)
            for tl in (g(decoded, 'announce-list') or []):
                for t in tl:
                    url = t.decode() if isinstance(t, bytes) else t
                    if url not in trackers: trackers.append(url)
            for tr in trackers: magnet += f"&tr={quote(tr)}"

            ts = g(decoded, 'creation date')
            created_at = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else "Unknown"

            files_list, total_size = [], 0
            raw_files = g(info, 'files')
            if raw_files:
                for f in raw_files:
                    length = g(f, 'length') or 0
                    total_size += length
                    parts = g(f, 'path') or []
                    path_str = "/".join(p.decode('utf-8', errors='ignore') if isinstance(p, bytes) else p for p in parts)
                    files_list.append({"name": path_str, "size": self.format_size(length)})
            else:
                length = g(info, 'length') or 0
                total_size = length
                files_list.append({"name": name, "size": self.format_size(length)})

            comment_raw = g(decoded, 'comment') or ''
            comment = comment_raw.decode('utf-8', errors='ignore') if isinstance(comment_raw, bytes) else str(comment_raw)

            return {"unique_hash": btih, "magnet": magnet, "created_at": created_at,
                    "total_size": self.format_size(total_size), "files": files_list, "comment": comment}
        except Exception as e:
            print(f"    Erro bencode: {e}")
            return None

    # ------------------------------------------------------------------
    # Steam API
    # ------------------------------------------------------------------
    def _normalize(self, s):
        """Normaliza string para comparação: lowercase, sem acentos, apenas alfanumérico e espaços"""
        import unicodedata
        s = s.lower()
        # Remover acentos
        s = ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn')
        s = s.replace('&', ' and ')
        roman_map = {
            ' ix ': ' 9 ',
            ' viii ': ' 8 ',
            ' vii ': ' 7 ',
            ' vi ': ' 6 ',
            ' iv ': ' 4 ',
            ' iii ': ' 3 ',
            ' ii ': ' 2 ',
        }
        s = f" {s} "
        for roman, arabic in roman_map.items():
            s = s.replace(roman, arabic)
        # Manter apenas letras, números e espaços
        s = re.sub(r'[^a-z0-9 ]', ' ', s)
        # Normalizar espaços
        return re.sub(r'\s+', ' ', s).strip()

    def _extract_number(self, s):
        """Extrai o primeiro número inteiro encontrado na string"""
        match = re.search(r'\b\d+\b', s)
        return int(match.group()) if match else None

    def _extract_numbers(self, s):
        """Extrai números relevantes, ignorando anos para não confundir sequência com data."""
        numbers = []
        for match in re.finditer(r'\b\d+\b', s):
            value = int(match.group())
            if 1900 <= value <= 2099:
                continue
            numbers.append(value)
        return numbers

    def _extract_year(self, s):
        """Extrai ano no formato YYYY da string"""
        match = re.search(r'\b(19|20)\d{2}\b', s)
        return int(match.group()) if match else None

    def _meaningful_tokens(self, s):
        stopwords = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "should",
            "could", "may", "might", "must", "can", "edition", "game", "vr",
            "online", "simulator", "dlc", "hd", "remastered", "complete", "pack",
            "bundle", "collection", "definitive", "ultimate", "deluxe", "enhanced",
            "reloaded", "free"
        }
        noise_words = {"demo", "trailer", "soundtrack", "ost", "server", "test", "beta", "alpha", "gog", "gogcom"}
        tokens = []
        for token in self._normalize(s).split():
            if len(token) <= 1:
                continue
            if token in stopwords or token in noise_words:
                continue
            tokens.append(token)
        return tokens

    def _textual_tokens(self, s):
        return [token for token in self._meaningful_tokens(s) if re.search(r'[a-z]', token)]

    def _distinctive_tokens(self, s):
        """Tokens mais distintivos para validar se o match realmente pertence ao mesmo título/franquia."""
        generic_tokens = {
            "project", "quest", "total", "war", "wars", "world", "story", "stories",
            "edition", "definitive", "deluxe", "complete", "collection", "digital",
            "ultimate", "enhanced", "remaster", "remastered", "anniversary", "redux",
            "rise", "rising", "returns", "return", "reborn", "heroes", "hero",
            "battle", "brawl", "party", "simulator", "adventure", "survival",
            "online", "dark", "legend", "legends", "chronicles", "saga"
        }
        return [
            token for token in self._textual_tokens(s)
            if len(token) >= 3 and token not in generic_tokens
        ]

    def _load_match_guard_model(self):
        model_path = os.path.join('tools', 'match_guard_model.json')
        if not os.path.exists(model_path):
            return None
        try:
            return self._load_json_file(model_path)
        except Exception as e:
            print(f"⚠️ Falha ao carregar match_guard_model.json: {e}")
            return None

    def _load_match_guard_aliases(self):
        alias_path = os.path.join('tools', 'match_guard_aliases.json')
        if not os.path.exists(alias_path):
            return {}
        try:
            data = self._load_json_file(alias_path)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            print(f"⚠️ Falha ao carregar match_guard_aliases.json: {e}")
            return {}

    def _resolve_alias_candidate(self, title):
        if not self._match_aliases or not self._steam_catalog:
            return None
        normalized_title = self._guard_normalize(title)
        alias_target = self._match_aliases.get(normalized_title)
        if not alias_target:
            return None
        normalized_target = self._normalize(alias_target)
        for app in self._steam_catalog:
            if self._normalize(app['name']) == normalized_target:
                candidate = {
                    "id": app["appid"],
                    "name": app["name"],
                    "score": 100
                }
                return candidate
        return None

    def _guard_normalize(self, text):
        text = (text or "").lower()
        text = text.replace("’", "").replace("'", "").replace("`", "")
        text = text.replace("™", " ").replace("®", " ").replace("©", " ")
        text = re.sub(r"[':!?,.%&()+\[\]{}|/\\-]+", " ", text)
        return re.sub(r'\s+', ' ', text).strip()

    def _guard_remove_trailing_descriptors(self, text):
        reduced = self._guard_normalize(text)
        patterns = [
            r"\s+ultimate edition$",
            r"\s+definitive edition$",
            r"\s+complete edition$",
            r"\s+digital edition$",
            r"\s+enhanced edition$",
            r"\s+anniversary edition$",
            r"\s+legacy collection$",
            r"\s+classic collection$",
            r"\s+director'?s cut$",
            r"\s+directors cut$",
            r"\s+pc edition$",
            r"\s+hd remaster$",
            r"\s+remaster(?:ed)?$",
            r"\s+redux$",
            r"\s+reloaded$",
            r"\s+ultimate$",
            r"\s+definitive$",
            r"\s+enhanced$",
        ]
        changed = True
        while changed and reduced:
            changed = False
            for pattern in patterns:
                updated = re.sub(pattern, "", reduced).strip()
                if updated != reduced:
                    reduced = updated
                    changed = True
        return reduced

    def _guard_descriptor_stripped_match(self, query, candidate):
        q_stripped = self._guard_remove_trailing_descriptors(query)
        c_stripped = self._guard_remove_trailing_descriptors(candidate)
        return (
            bool(q_stripped)
            and bool(c_stripped)
            and (
                q_stripped == c_stripped
                or q_stripped == self._guard_normalize(candidate)
                or c_stripped == self._guard_normalize(query)
            )
        )

    def _guard_textual_tokens(self, text):
        return re.findall(r"[a-z0-9]+", self._guard_normalize(text))

    def _guard_stem_token(self, token):
        if token.endswith('ies') and len(token) > 4:
            return token[:-3] + 'y'
        if token.endswith('bros') and len(token) > 4:
            return token[:-1]
        if token.endswith('s') and len(token) > 3 and not token.endswith(('ss', 'us', 'is', 'os')):
            return token[:-1]
        return token

    def _guard_descriptor_tokens(self):
        return {
            "edition", "editions", "game", "games", "vr", "online", "simulator", "digital",
            "collection", "ultimate", "definitive", "complete", "remastered", "remaster",
            "enhanced", "director", "directors", "cut", "beta", "alpha", "demo", "pc",
            "hd", "bundle", "pack", "deluxe", "anniversary", "redux", "reloaded",
            "multiplayer", "coop", "co", "op", "goty", "city", "rpg", "mode", "version",
            "launch", "steam", "store", "full", "s"
        }

    def _guard_meaningful_tokens(self, text):
        descriptor_tokens = self._guard_descriptor_tokens()
        tokens = []
        for token in self._guard_textual_tokens(text):
            if len(token) < 2:
                continue
            if token in descriptor_tokens:
                continue
            tokens.append(token)
        return tokens

    def _guard_canonical_tokens(self, text, drop_descriptors=False):
        descriptor_tokens = self._guard_descriptor_tokens()
        roman_tokens = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii", "xiv", "xv", "xvi"}
        common_tokens = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by", "is", "are", "was", "were", "be", "been", "being"}
        tokens = []
        for token in self._guard_textual_tokens(text):
            if token in common_tokens:
                continue
            if drop_descriptors and token in descriptor_tokens:
                continue
            token = self._guard_stem_token(token)
            if len(token) < 2 and not token.isdigit() and token not in roman_tokens:
                continue
            tokens.append(token)
        return tokens

    def _guard_extract_numbers(self, text):
        roman_values = {
            "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8,
            "ix": 9, "x": 10, "xi": 11, "xii": 12, "xiii": 13, "xiv": 14, "xv": 15, "xvi": 16
        }
        numbers = [int(x) for x in re.findall(r"\b\d{1,4}\b", text or "")]
        romans = [roman_values[token] for token in self._guard_textual_tokens(text) if token in roman_values]
        return sorted(set(numbers + romans))

    def _guard_extract_year(self, text):
        years = [int(x) for x in re.findall(r"\b(19\d{2}|20\d{2})\b", text or "")]
        return years[0] if years else None

    def _guard_jaccard(self, a, b):
        sa, sb = set(a), set(b)
        if not sa and not sb:
            return 1.0
        if not sa or not sb:
            return 0.0
        return len(sa & sb) / len(sa | sb)

    def _guard_overlap_fraction(self, source, target):
        source_set, target_set = set(source), set(target)
        if not source_set:
            return 1.0
        return len(source_set & target_set) / len(source_set)

    def _guard_franchise_key(self, text):
        core = self._guard_canonical_tokens(text, drop_descriptors=True)
        key_tokens = []
        roman_tokens = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii", "xiv", "xv", "xvi"}
        for token in core:
            if token.isdigit() or token in roman_tokens:
                continue
            key_tokens.append(token)
            if len(key_tokens) >= 2:
                break
        return " ".join(key_tokens)

    def _guard_sequence_conflict(self, query, candidate):
        query_numbers = self._guard_extract_numbers(query)
        candidate_numbers = self._guard_extract_numbers(candidate)
        if not query_numbers or not candidate_numbers:
            return False
        query_key = self._guard_franchise_key(query)
        candidate_key = self._guard_franchise_key(candidate)
        return bool(query_key) and query_key == candidate_key and query_numbers != candidate_numbers

    def _guard_feature_vector(self, query, candidate):
        q_norm = self._guard_normalize(query)
        c_norm = self._guard_normalize(candidate)
        q_tokens = self._guard_textual_tokens(query)
        c_tokens = self._guard_textual_tokens(candidate)
        q_meaning = self._guard_meaningful_tokens(query)
        c_meaning = self._guard_meaningful_tokens(candidate)
        q_dist = [tok for tok in q_meaning if len(tok) >= 4]
        c_dist = [tok for tok in c_meaning if len(tok) >= 4]
        q_numbers = self._guard_extract_numbers(query)
        c_numbers = self._guard_extract_numbers(candidate)
        q_year = self._guard_extract_year(query)
        c_year = self._guard_extract_year(candidate)
        q_core = self._guard_canonical_tokens(query, drop_descriptors=True)
        c_core = self._guard_canonical_tokens(candidate, drop_descriptors=True)
        q_all_canon = self._guard_canonical_tokens(query, drop_descriptors=False)
        c_all_canon = self._guard_canonical_tokens(candidate, drop_descriptors=False)
        q_compact = ''.join(q_tokens)
        c_compact = ''.join(c_tokens)
        return [
            fuzz.token_set_ratio(q_norm, c_norm) / 100.0,
            fuzz.token_sort_ratio(q_norm, c_norm) / 100.0,
            fuzz.ratio(q_norm, c_norm) / 100.0,
            fuzz.partial_ratio(q_norm, c_norm) / 100.0,
            1.0 if q_norm == c_norm else 0.0,
            1.0 if q_compact == c_compact else 0.0,
            1.0 if q_norm in c_norm and q_norm != c_norm else 0.0,
            1.0 if c_norm in q_norm and q_norm != c_norm else 0.0,
            1.0 if self._guard_descriptor_stripped_match(query, candidate) else 0.0,
            1.0 if q_core and q_core == c_core else 0.0,
            1.0 if q_all_canon and q_all_canon == c_all_canon else 0.0,
            self._guard_jaccard(q_tokens, c_tokens),
            self._guard_jaccard(q_meaning, c_meaning),
            self._guard_jaccard(q_dist, c_dist),
            self._guard_jaccard(q_core, c_core),
            self._guard_overlap_fraction(q_meaning, c_meaning),
            self._guard_overlap_fraction(q_dist, c_dist),
            self._guard_overlap_fraction(q_core, c_core),
            1.0 if q_numbers == c_numbers and q_numbers else 0.0,
            1.0 if q_numbers and c_numbers and q_numbers != c_numbers else 0.0,
            1.0 if self._guard_sequence_conflict(query, candidate) else 0.0,
            1.0 if not q_numbers else 0.0,
            1.0 if not c_numbers else 0.0,
            1.0 if q_year == c_year and q_year is not None else 0.0,
            1.0 if q_year is not None and c_year is not None and q_year != c_year else 0.0,
            1.0 if self._guard_franchise_key(query) and self._guard_franchise_key(query) == self._guard_franchise_key(candidate) else 0.0,
            abs(len(q_norm) - len(c_norm)) / max(1, max(len(q_norm), len(c_norm))),
            float(len(set(q_tokens) & set(c_tokens))),
            float(len(set(q_dist) & set(c_dist))),
            float(len([tok for tok in c_core if tok not in q_core])),
            float(len([tok for tok in q_core if tok not in c_core]))
        ]

    def _guard_sigmoid(self, value):
        if value >= 0:
            z = math.exp(-value)
            return 1.0 / (1.0 + z)
        z = math.exp(value)
        return z / (1.0 + z)

    def _guard_probability(self, query, candidate):
        if not self._match_guard:
            return 0.0
        weights = self._match_guard.get("weights", [])
        bias = self._match_guard.get("bias", 0.0)
        features = self._guard_feature_vector(query, candidate)
        score = bias
        for weight, feature in zip(weights, features):
            score += weight * feature
        return self._guard_sigmoid(score)

    def _is_canonical_steam_match(self, query, candidate):
        query_core = self._guard_canonical_tokens(query, drop_descriptors=True)
        candidate_core = self._guard_canonical_tokens(candidate, drop_descriptors=True)
        return bool(query_core) and query_core == candidate_core

    def _pick_guarded_candidate(self, title, candidates):
        accepted = []
        for candidate in candidates[:5]:
            name = candidate['name']
            score = candidate['score']
            if self._guard_sequence_conflict(title, name):
                continue
            canonical = self._is_canonical_steam_match(title, name)
            guard_prob = self._guard_probability(title, name)
            query_core = self._guard_canonical_tokens(title, drop_descriptors=True)
            candidate_core = self._guard_canonical_tokens(name, drop_descriptors=True)
            core_overlap = self._guard_overlap_fraction(query_core, candidate_core)
            extra_candidate_tokens = [token for token in candidate_core if token not in query_core]

            if canonical and score >= 55:
                accepted.append((3, 0.999, score, "canon", candidate))
                continue

            if guard_prob >= 0.72 and score >= 72:
                accepted.append((2, guard_prob, score, "model", candidate))
                continue

            if score >= 90 and guard_prob >= 0.18 and core_overlap >= 0.5 and (not extra_candidate_tokens or guard_prob >= 0.45):
                accepted.append((1, guard_prob, score, "fuzzy", candidate))

        if not accepted:
            return None, None

        accepted.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        return accepted[0][4], accepted[0][3]

    def _record_low_confidence_match(self, title, candidate, reason, probability=None, score=None):
        path = 'low_confidence_matches.json'
        entry = {
            "title": title,
            "candidate": candidate,
            "reason": reason,
            "probability": round(probability, 4) if probability is not None else None,
            "score": round(score, 1) if score is not None else None,
            "logged_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        try:
            payload = []
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    payload = json.load(f)
                    if not isinstance(payload, list):
                        payload = []
            payload.append(entry)
            payload = payload[-500:]
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _proxy_log_icon(self):
        return "🌐" if self.proxies_list else "🏠"

    def _memory_usage_mb(self):
        try:
            if psutil is None:
                return 0
            return int(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024))
        except Exception:
            return 0

    def _format_game_log_line(self, current_idx, total, name, page_num, torrent_ok, steam_ok, latency_ms, reason, match_via=None):
        icon = "✅" if torrent_ok and steam_ok else "❌"
        torrent_status = "OK" if torrent_ok else "!!"
        steam_status = "OK" if steam_ok else "!!"
        safe_reason = (reason or "OK")[:18]
        safe_via = (match_via or "--")[:5]
        return (
            f"{icon} "
            f"[{current_idx:04d}/{total:04d}] "
            f"| {name[:25]:<25} "
            f"| T:{torrent_status} S:{steam_status} G:{safe_via:<5} "
            f"| {latency_ms:>4}ms "
            f"| P:{page_num:03d} "
            f"| {self._proxy_log_icon()} "
            f"| M:{self._memory_usage_mb():>4}MB "
            f"| {safe_reason:<18} "
            f"| {datetime.now().strftime('%H:%M:%S')}"
        )

    def _get_importance_weight(self, word):
        """Retorna peso de importância para uma palavra (palavras comuns têm peso menor)"""
        common_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
                       "of", "with", "by", "is", "are", "was", "were", "be", "been", "being",
                       "have", "has", "had", "do", "does", "did", "will", "would", "should",
                       "could", "may", "might", "must", "can", "of", "edition", "game"}
        return 0.1 if word in common_words else 1.0

    def _search_variations(self, name):
        base = re.sub(r'\s*по сети\s*', '', name, flags=re.I).strip()
        words = base.split()

        # Variações inteligentes de busca
        v = [
            self._normalize(base),  # Original normalizado
            self._normalize(re.sub(r'[&]', 'and', base)),  # & → and
        ]

        # Adicionar variações com dois pontos em posições estratégicas
        # Só adicionar se fizer sentido (não muito cedo ou muito tarde)
        if len(words) >= 3:
            # Tentar inserir : após 2ª palavra (comum em títulos como "Subtitle: Description")
            if len(words[0]) > 2 and len(words[1]) > 2:  # Evitar palavras muito pequenas
                v.append(self._normalize(f"{words[0]} {words[1]}: {' '.join(words[2:])}"))
            # Tentar inserir : após 1ª palavra
            if len(words[0]) > 3:  # Primeira palavra suficientemente longa
                v.append(self._normalize(f"{words[0]}: {' '.join(words[1:])}"))

        # Prefixos muito curtos acabavam puxando jogos de outra franquia.
        if len(words) >= 4 and not any(re.fullmatch(r'\d+', word) for word in words):
            if all(len(word) > 2 for word in words[:3]):
                v.append(self._normalize(" ".join(words[:3])))

        # Variação sem pontuação (para casos extremos)
        v.append(self._normalize(re.sub(r'[^\w\s]', '', base)))

        # Remover duplicatas e vazias, manter ordem
        seen = set()
        result = []
        for x in v:
            x_stripped = x.strip()
            if x_stripped and x_stripped not in seen:
                seen.add(x_stripped)
                result.append(x_stripped)
        return result  # Retornar todas as variações possíveis (menos restrições)

    def _steam_request(self, url, params=None, max_retries=5, verbose=False):  # Reduzi número de tentativas
        """Helper para requisições ao Steam com Rotação de Proxies e retentativa."""
        for attempt in range(max_retries):
            # Puxa um proxy novo para cada tentativa
            proxy = self._get_next_proxy()
            try:
                time.sleep(0.5)  # Aumentei o delay para reduzir chance de block
                r = requests.get(url, params=params, timeout=15, proxies=proxy)  # Aumentei timeout

                if r.status_code == 429:
                    wait = 60 * (attempt + 1)  # Aumentei significativamente o wait
                    if verbose:
                        print(f"    [Steam Block] Aguardando {wait}s... (Tentativa {attempt+1}/{max_retries})")
                    time.sleep(wait)
                    continue

                if r.status_code != 200:
                    return None

                return r.json()
            except Exception as e:
                if verbose:
                    print(f"    Erro na requisição Steam (tentativa {attempt+1}): {e}")
                time.sleep(2)  # Maior delay entre tentativas
        return None

    def _steam_search(self, term):
        """Busca no catálogo local do Steam com variações e tolerância a erros."""
        # Normalizar o termo de busca
        normalized_term = self._normalize(term)

        # Primeiro tenta busca exata
        exact_matches = self._search_in_catalog(normalized_term, term)
        if exact_matches:
            return exact_matches

        # Se não encontrar resultados exatos, tenta com variações
        variations = self._search_variations(term)
        for variation in variations:
            normalized_variation = self._normalize(variation)
            if normalized_variation != normalized_term:  # Evitar repetição
                var_matches = self._search_in_catalog(normalized_variation, variation)
                if var_matches:
                    return var_matches

        # Se ainda não encontrar, faz uma busca mais ampla com fuzzy matching
        return self._search_in_catalog(normalized_term, term)

    def _parse_requirements(self, html_str):
        """Converte HTML de requisitos em texto limpo com \n entre campos."""
        if not html_str or not isinstance(html_str, str):
            return None
        # Remove tags mas preserva <br> e <li> como \n
        text = re.sub(r'<br\s*/?>', '\n', html_str)
        text = re.sub(r'<li>', '\n', text)
        text = re.sub(r'<[^>]+>', '', text)
        # Colapsa múltiplas linhas vazias
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _translate_to_pt(self, text):
        """Traduz texto para português via Google Translate (free endpoint)."""
        if not text:
            return text
        try:
            url = "https://translate.googleapis.com/translate_a/single"
            params = {
                "client": "gtx", "sl": "auto", "tl": "pt",
                "dt": "t", "q": text
            }
            r = requests.get(url, params=params, timeout=8)
            result = r.json()
            translated = "".join(part[0] for part in result[0] if part[0])
            return translated
        except Exception:
            return text  # fallback: retorna original

    def _normalize_torrent_link(self, torrent_link):
        """Força links do raw para o repositório/branch atuais."""
        if not torrent_link:
            return torrent_link

        raw_match = re.search(
            r'https://raw\.githubusercontent\.com/[^/]+/[^/]+/[^/]+/(torrents/.+)$',
            torrent_link
        )
        if raw_match:
            relative_path = raw_match.group(1)
            return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{relative_path}"

        normalized = torrent_link.replace('\\', '/').lstrip('./')
        if normalized.startswith('torrents/'):
            return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{normalized}"

        return torrent_link

    def _count_local_torrent_files(self):
        total = 0
        for root, _, files in os.walk(TORRENT_DIR):
            total += sum(1 for name in files if name.lower().endswith('.torrent'))
        return total

    def _write_stats(self, downloads, requested_pages, discovered_max_page, scraped_new_games, processed_results, latest_run_new_game_names=None):
        def is_valid_stat_value(value):
            if value is None:
                return False
            text = str(value).strip()
            return text not in {"", "Unknown", "unknown", "None", "none", "null"}

        steam_with_metadata = sum(
            1 for item in downloads
            if isinstance(item.get('steam'), dict) and not item['steam'].get('not_found')
        )
        steam_without_metadata = len(downloads) - steam_with_metadata

        pages_in_json = sorted({
            item.get('page') for item in downloads
            if isinstance(item.get('page'), int)
        })

        def format_stat_datetime(value):
            if not is_valid_stat_value(value):
                return None
            text = str(value).strip()
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    return datetime.strptime(text, fmt).strftime("%d/%m/%Y")
                except ValueError:
                    pass
            try:
                return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%d/%m/%Y")
            except ValueError:
                return text

        last_scrape_at = None
        last_game_update = None
        for item in downloads:
            scraped_at = item.get('scraped_at')
            if is_valid_stat_value(scraped_at) and (last_scrape_at is None or scraped_at > last_scrape_at):
                last_scrape_at = scraped_at

            update_candidates = [
                item.get('formatted_update_date'),
                item.get('update_date'),
                item.get('last_update'),
                item.get('webdav_updated_at'),
            ]
            for candidate in update_candidates:
                if is_valid_stat_value(candidate) and (last_game_update is None or str(candidate) > str(last_game_update)):
                    last_game_update = candidate

        total_games = len(downloads)
        match_rate = round((steam_with_metadata / total_games) * 100, 2) if total_games else 0.0
        success_rate = match_rate

        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        stats = {
            "repo": GITHUB_REPO,
            "branch": GITHUB_BRANCH,
            "raw_base_url": RAW_BASE_URL,
            "total_games": total_games,
            "online_fix_total": total_games,
            "steam_with_metadata": steam_with_metadata,
            "steam_without_metadata": steam_without_metadata,
            "match_rate": match_rate,
            "success_rate": success_rate,
            "online_fix_pages_total": discovered_max_page,
            "pages_scraped_target": requested_pages,
            "pages_present_in_json": len(pages_in_json),
            "last_page_in_json": pages_in_json[-1] if pages_in_json else 0,
            "new_games_found_this_run": scraped_new_games,
            "latest_run_new_game_names": latest_run_new_game_names or [],
            "processed_games_this_run": processed_results,
            "torrent_files_total": self._count_local_torrent_files(),
            "json_entries_with_torrent": sum(1 for item in downloads if item.get('torrent_file')),
            "last_scrape_at": last_scrape_at,
            "last_scrape_at_display": format_stat_datetime(last_scrape_at),
            "last_game_update": last_game_update,
            "generated_at": generated_at,
            "generated_at_display": format_stat_datetime(generated_at),
        }

        with open('stats.json', 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)

        return stats

    def get_steam_data(self, title, verbose=False):
        """Obtém metadados da Steam usando catálogo local (offline, zero rate limit)."""
        # Normalização
        clean = self._normalize(re.sub(r'\s*по сети\s*', '', title, flags=re.I).strip())

        # URL para referência (compatibilidade)
        base_search_url = f"https://store.steampowered.com/api/storesearch/?term={quote(clean)}&l=portuguese&cc=BR"

        # 1. Verificar se catálogo está disponível
        if not self._steam_catalog:
            return {"not_found": True, "reason": "no_catalog", "search_url": base_search_url}, base_search_url

        # 2. Buscar no catálogo local usando a função aprimorada
        catalog_matches = self._steam_search(clean)

        if not catalog_matches:
            return {"not_found": True, "reason": "not_on_steam", "search_url": base_search_url}, base_search_url

        alias_candidate = self._resolve_alias_candidate(title)
        if alias_candidate:
            best = alias_candidate
            match_via = "alias"
        else:
        # 3. Pegar melhor match com canonicalização + guard model
            best, match_via = self._pick_guarded_candidate(title, catalog_matches)
            if not best:
                fallback = catalog_matches[0]
                fallback_prob = self._guard_probability(title, fallback['name'])
                self._record_low_confidence_match(title, fallback['name'], "low_confidence", fallback_prob, fallback['score'])
                if verbose:
                    print(f"    ⚠️ Score baixo ({fallback['score']:.1f}) para '{title}' → '{fallback['name']}'. Rejeitando.")
                return {"not_found": True, "reason": "low_confidence", "search_url": base_search_url}, base_search_url

        appid = best['id']
        match_score = best['score']

        title_lower = title.lower()
        best_name_lower = best['name'].lower()

        # Palavras-chave importantes que devem estar presentes para certos tipos de jogos
        if "forza" in title_lower and "forza" not in best_name_lower:
            self._record_low_confidence_match(title, best['name'], "keyword_missing", self._guard_probability(title, best['name']), match_score)
            if verbose:
                print(f"    ⚠️ Jogo Forza não encontrado corretamente: '{title}' → '{best['name']}' (palavra-chave ausente). Rejeitando.")
            return {"not_found": True, "reason": "keyword_missing", "search_url": base_search_url}, base_search_url

        if "fifa" in title_lower and "fifa" not in best_name_lower:
            self._record_low_confidence_match(title, best['name'], "keyword_missing", self._guard_probability(title, best['name']), match_score)
            if verbose:
                print(f"    ⚠️ Jogo Fifa não encontrado corretamente: '{title}' → '{best['name']}' (palavra-chave ausente). Rejeitando.")
            return {"not_found": True, "reason": "keyword_missing", "search_url": base_search_url}, base_search_url

        if "madden" in title_lower and "madden" not in best_name_lower:
            self._record_low_confidence_match(title, best['name'], "keyword_missing", self._guard_probability(title, best['name']), match_score)
            if verbose:
                print(f"    ⚠️ Jogo Madden não encontrado corretamente: '{title}' → '{best['name']}' (palavra-chave ausente). Rejeitando.")
            return {"not_found": True, "reason": "keyword_missing", "search_url": base_search_url}, base_search_url

        if verbose:
            print(f"    ✅ Catálogo: '{title}' → '{best['name']}' (score: {match_score:.1f}, appid: {appid})")

        # 6. Obter detalhes do jogo via API (única chamada)
        json_data = self._steam_request(
            "https://store.steampowered.com/api/appdetails",
            params={"appids": appid, "cc": "BR", "l": "portuguese"},
            verbose=verbose
        )

        if not json_data or not isinstance(json_data, dict):
            return {"not_found": True, "reason": "api_error", "search_url": base_search_url}, base_search_url

        try:
            data = json_data.get(str(appid), {})
            if not data or not data.get('success'):
                return {"not_found": True, "reason": "details_failed", "search_url": base_search_url}, base_search_url

            d = data.get('data', {})
            if not d:
                return {"not_found": True, "reason": "no_data", "search_url": base_search_url}, base_search_url

            def parse_req(key):
                req = d.get(key, {})
                if not isinstance(req, dict):
                    return None
                return {
                    "minimum": self._parse_requirements(req.get('minimum')),
                    "recommended": self._parse_requirements(req.get('recommended')),
                }

            price = d.get('price_overview', {})
            short_desc_native = d.get('short_description', '')
            short_desc = short_desc_native
            # Traduzir apenas se não contiver caracteres PT
            if short_desc and not re.search(r'[àáâãäéêíóôõúüçÀÁÂÃÄÉÊÍÓÔÕÚÜÇ]', short_desc):
                short_desc = self._translate_to_pt(short_desc)

            return {
                "steam_appid": appid,
                "match_score": int(match_score),
                "match_via": match_via or "catalog",
                "header_image": d.get('header_image'),
                "short_description": short_desc,
                "short_description_native": short_desc_native,
                "price_brl": price.get('final_formatted') if isinstance(price, dict) else None,
                "is_free": d.get('is_free', False),
                "pc_requirements": parse_req('pc_requirements'),
                "controller_support": d.get('controller_support'),
            }, base_search_url

        except Exception as e:
            if verbose:
                print(f"    ❌ Erro ao processar appdetails para {appid}: {e}")
            return {"not_found": True, "reason": "exception", "search_url": base_search_url}, base_search_url

    def find_torrent_robust(self, title):
        self._set_webdav_cookies()
        last_reason = {"reason": "NO_TORRENT_LINK", "status_code": 404}
        # Normaliza o título base
        name_base = re.sub(r'\s*по сети\s*', '', title, flags=re.I).strip()
        name_base = name_base.replace('’', "'").replace('‘', "'").replace('´', "'").replace('`', "'")

        clean_name = self.clean_name_for_url(title)

        def build_name_variants(raw_title):
            variants = []

            def add_variant(candidate):
                candidate = re.sub(r'\s+', ' ', str(candidate or '').strip())
                if not candidate:
                    return
                if candidate not in variants:
                    variants.append(candidate)

            add_variant(raw_title)

            if "'" not in raw_title and "s " in raw_title:
                add_variant(raw_title.replace("s ", "'s "))

            words = raw_title.split()
            trimmed_words = words[:]
            while trimmed_words and trimmed_words[-1].lower() in WEBDAV_OPTIONAL_TRAILING_WORDS:
                trimmed_words = trimmed_words[:-1]
                add_variant(" ".join(trimmed_words))

            return variants

        name_variants = build_name_variants(name_base)

        # Primeiro tenta diretamente com o nome do jogo + extensão .torrent
        # Isso pode evitar a necessidade de acessar o diretório WebDAV
        direct_variations = []
        for variant_name in name_variants:
            direct_variations.append(quote(variant_name, safe='') + '.torrent')

        # Adiciona variações com possíveis formatos de nome de arquivo
        possible_formats = [
            "{name}.v1.0-OFME.torrent",
            "{name}.v1.0.14-OFME.torrent",
            "{name}.rar.torrent",
            "{name}-OFME.torrent",
            "{name}.torrent"
        ]

        for fmt in possible_formats:
            for variant_name in name_variants:
                formatted_name = fmt.format(name=variant_name)
                quoted_name = quote(formatted_name, safe='')
                if quoted_name not in direct_variations:
                    direct_variations.append(quoted_name)

        # Tenta acesso direto primeiro
        for direct_var in direct_variations:
            time.sleep(random.uniform(0.2, 0.5))
            direct_url = f"{WEBDAV_ROOT}{direct_var}"
            try:
                for attempt in range(3):  # Menos tentativas para acesso direto
                    time.sleep(0.1)
                    resp = self.session.get(direct_url, headers=WEBDAV_HEADERS, timeout=(5, 10))

                    if resp.status_code == 429:
                        wait = 15 * (attempt + 1)
                        time.sleep(wait)
                        continue

                    if resp.status_code == 200:
                        # Verifica se é realmente um arquivo .torrent
                        content_type = resp.headers.get('content-type', '').lower()
                        content_disposition = resp.headers.get('content-disposition', '').lower()
                        if 'application/x-bittorrent' in content_type or '.torrent' in content_disposition or direct_var.endswith('.torrent'):
                            # Extrai data de criação do cabeçalho se disponível
                            webdav_date = resp.headers.get('last-modified', 'Unknown')
                            return direct_url, webdav_date, direct_url, {"reason": "OK", "status_code": 200}
                    elif resp.status_code == 401 or resp.status_code == 404:
                        last_reason = {"reason": str(resp.status_code), "status_code": resp.status_code}
                        break  # Arquivo não existe, tentar próximo
                    elif resp.status_code == 402:  # Payment Required - problema com proxy
                        last_reason = {"reason": str(resp.status_code), "status_code": resp.status_code}
                        break  # Não tentar mais variações desse tipo
                    elif resp.status_code == 403:  # Forbidden
                        last_reason = {"reason": str(resp.status_code), "status_code": resp.status_code}
                        break  # Não tentar mais variações desse tipo
                    else:
                        # Outros erros, tentar novamente
                        if attempt < 2:  # Ainda tem tentativas
                            time.sleep(1 * (attempt + 1))
                        continue
                break
            except Exception as e:
                last_reason = {"reason": type(e).__name__, "status_code": "ERR"}
                if "Payment Required" in str(e) or "402" in str(e):
                    continue  # Continuar para próxima variação em vez de parar

        # Se acesso direto falhar, tenta o método original de acesso ao diretório
        variations = [quote(variant_name, safe='') for variant_name in name_variants]

        for var in variations:
            # Delay entre tentativas de pasta no WebDAV
            time.sleep(random.uniform(0.5, 1.0))  # Aumentei o delay inicial
            folder_url = f"{WEBDAV_ROOT}{var}/"
            try:
                for attempt in range(5):  # Reduzi número de tentativas para evitar longos waits
                    time.sleep(0.2)  # Aumentei o delay entre tentativas
                    resp = self.session.get(folder_url, headers=WEBDAV_HEADERS, timeout=(10, 20))

                    if resp.status_code == 429:
                        wait = 60 * (attempt + 1)  # Aumentei o tempo de espera
                        time.sleep(wait)
                        continue

                    if resp.status_code in [401, 403, 404]:
                        last_reason = {"reason": str(resp.status_code), "status_code": resp.status_code}
                        break  # Não tentar mais variações com este padrão
                    if resp.status_code != 200:
                        last_reason = {"reason": str(resp.status_code), "status_code": resp.status_code}
                        break

                    soup = BeautifulSoup(resp.text, 'html.parser')
                    # Procura por arquivos .torrent dentro da pasta
                    links = soup.find_all('a')
                    if not links:
                        break

                    for a in links:
                        href = a.get('href', '')
                        if not href.endswith('.torrent'):
                            continue

                        torrent_url = href if href.startswith('http') else urljoin(folder_url, href)
                        webdav_date = "Unknown"
                        row = a.find_parent('tr')
                        if row:
                            cells = row.find_all('td')
                            if len(cells) >= 3:
                                webdav_date = cells[2].get_text(strip=True)
                        return torrent_url, webdav_date, folder_url, {"reason": "OK", "status_code": 200}
                    break
            except Exception as e:
                last_reason = {"reason": type(e).__name__, "status_code": "ERR"}
                if "Payment Required" in str(e) or "402" in str(e):
                    continue  # Tentar próxima variação em vez de falhar completamente
        return None, None, None, last_reason

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    def _extract_games(self, soup):
        """Extrai title+href+last_update de articles filtrando só /games/, sem DayZ."""
        content = soup.select_one("#dle-content")
        if content:
            arts = content.select("article.news")
        else:
            arts = soup.select("article.news")

        results = []
        for art in arts:
            title_tag = art.find('h2', class_='title')
            if not title_tag:
                continue
            title = title_tag.text.strip()
            if "dayz" in title.lower():
                continue
            if any(x in title.lower() for x in ["как скачивать", "how to download"]):
                continue

            a_tag = art.select_one("a.img, a.big-link")
            if not a_tag:
                a_tag = art.find('a')
            href = a_tag.get('href', '') if a_tag else ''
            if '/games/' not in href:
                continue

            # Extrair last_update do elemento <time datetime="...">
            last_update = None
            time_tag = art.find('time')
            if time_tag and time_tag.get('datetime'):
                last_update = time_tag['datetime'].strip()

            clean_title = re.sub(r'\s*по сети\s*', '', title, flags=re.I).strip()
            preview_text_tag = art.find('div', class_='preview-text')
            release_date = None
            if preview_text_tag:
                release_match = re.search(r'<b>Релиз игры:</b>\s*([\d.]+)', str(preview_text_tag))
                if release_match:
                    release_date = release_match.group(1)

            edit_tag = art.find('div', class_='edit')
            update_info = edit_tag.text.strip() if edit_tag else 'none'

            # Extrair data de atualização específica do campo edit se disponível
            update_date = None
            formatted_update_date = None
            if edit_tag:
                # Procurar por padrões de data na mensagem de atualização
                # Ex: "Обновлено 8 апреля 2026, 11:26" ou "Обновлено 4 февраля 2026, 19:15"
                update_date_match = re.search(r'Обновлено\s+(\d{1,2})\s+([а-яА-ЯёЁ]+)\s+(\d{4}),\s*(\d{1,2}):(\d{2})', edit_tag.text)
                if update_date_match:
                    day, month_name, year, hour, minute = update_date_match.groups()
                    # Converter nome do mês russo para número
                    months = {
                        'января': '01', 'февраля': '02', 'марта': '03', 'апреля': '04',
                        'мая': '05', 'июня': '06', 'июля': '07', 'августа': '08',
                        'сентября': '09', 'октября': '10', 'ноября': '11', 'декабря': '12'
                    }
                    month = months.get(month_name.lower(), '01')
                    update_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}T{hour.zfill(2)}:{minute.zfill(2)}:00+03:00"
                    formatted_update_date = f"{year}-{month.zfill(2)}-{day.zfill(2)} {hour.zfill(2)}:{minute.zfill(2)}:{'00'}"
                else:
                    # Tentar encontrar outro padrão de data
                    # Ex: procurar qualquer data no formato DD.MM.YYYY ou YYYY-MM-DD
                    date_match = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', edit_tag.text)
                    if date_match:
                        day, month, year = date_match.groups()
                        update_date = f"{year}-{month}-{day}T00:00:00+03:00"
                        formatted_update_date = f"{year}-{month}-{day} {'00:00:00'}"

            results.append({
                "title": clean_title,
                "href": href,
                "last_update": last_update,
                "release_date": release_date,
                "update_info": update_info,
                "update_date": update_date,  # Nova data de atualização extraída
                "formatted_update_date": formatted_update_date  # Data formatada no estilo created_at
            })
        return results

    def run(self, pages=None, workers=6, start_page=1):
        self.login()

        max_page = self.get_max_page()
        limit_page = pages if pages else max_page

        run_start = time.time()

        # ====== FASE 1: Coletar links — page 1 via DOM + page 2+ via AJAX ======
        print(f"FASE 1: Coletando links (DOM page 1 + AJAX pages 2-{limit_page})...")

        # Carrega dados existentes para deduplicação
        all_data = []
        existing_links = set()
        if os.path.exists('online_fix_games.json'):
            try:
                with open('online_fix_games.json', 'r', encoding='utf-8-sig') as f:
                    old_json = json.load(f)
                    all_data = old_json.get('downloads', [])
                    for item in all_data:
                        if 'url' in item:
                            existing_links.add(item['url'])
                        if item.get('torrent_file'):
                            item['torrent_file'] = self._normalize_torrent_link(item['torrent_file'])
                    print(f"📦 {len(all_data)} jogos carregados do banco de dados existente.")
            except Exception as e:
                print(f"⚠️ Erro ao carregar banco de dados atual: {e}")

        new_games = []
        seen_links = set()

        # --- Page 1: GET DOM (fonte oficial) ---
        if start_page == 1:
            print("🟢 Collecting page 1 (DOM)...")
            try:
                resp = self.session.get(self.base_url, timeout=15)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.content, 'html.parser')
                    games = self._extract_games(soup)
                    for g in games:
                        if g['href'] not in existing_links and g['href'] not in seen_links:
                            seen_links.add(g['href'])
                            g['page'] = 1
                            new_games.append(g)
                    print(f"✅ Page 1 OK ({len(games)} games)")
                else:
                    print(f"❌ Page 1 status {resp.status_code}")
            except Exception as e:
                print(f"❌ Page 1 error: {e}")

        # --- Pages 2+: POST AJAX (show_more = page - 1) ---
        ajax_start = max(start_page, 2)
        stopped = False
        for p in range(ajax_start, limit_page + 1):
            show_more_n = p - 1
            for attempt in range(10):
                proxy = self._get_next_proxy()
                try:
                    resp = self.session.post(self.base_url, data={"show_more": str(show_more_n)},
                                             headers={**HEADERS, "X-Requested-With": "XMLHttpRequest", "Accept": "*/*"},
                                             timeout=15, proxies=proxy)
                except Exception:
                    resp = None

                if resp and resp.status_code == 429:
                    print(f"[page {p}] Rate Limit! Trocando de IP...")
                    time.sleep(10)
                    continue

                if not resp or resp.status_code != 200:
                    print(f"[page {p}] Fim/erro, parando coleta.")
                    stopped = True
                    break

                try:
                    j = resp.json()
                    content = j.get("content", "")
                except Exception:
                    print(f"[page {p}] Fim (JSON inválido), parando coleta.")
                    stopped = True
                    break

                soup = BeautifulSoup(content, 'html.parser')
                games = self._extract_games(soup)
                for g in games:
                    if g['href'] not in existing_links and g['href'] not in seen_links:
                        seen_links.add(g['href'])
                        g['page'] = p
                        new_games.append(g)

                count = len(games)
                print(f"✅ Page {p} OK ({count} games)")
                time.sleep(random.uniform(0.2, 0.6))
                if count == 0:
                    print(f"[page {p}] vazio, fim real.")
                    stopped = True
                break  # Sucesso — sai do retry loop

            if stopped:
                break

        total_found = len(new_games)
        print(f"\nFASE 1: {total_found} jogos novos encontrados para processar.\n")

        if not new_games:
            print("Nenhum jogo novo. Finalizado!")
            return

        # ====== FASE 2: Baixar torrents + Steam (paralelo) ======
        print(f"FASE 2: Baixando torrents e dados Steam ({workers} workers)...\n")

        def process_game(game, current_idx, total_games):
            started_at = time.time()
            title = game['title']
            href = game['href']
            p = game['page']
            last_update = game.get('last_update')  # Extraído do HTML
            release_date = game.get('release_date')
            update_info = game.get('update_info')

            page_dir = os.path.join(TORRENT_DIR, f"batch_{p}")
            os.makedirs(page_dir, exist_ok=True)

            torrent_url, webdav_date, folder_url, torrent_meta = self.find_torrent_robust(title)
            if not torrent_url:
                latency_ms = int((time.time() - started_at) * 1000)
                print(self._format_game_log_line(current_idx, total_games, title, p, False, False, latency_ms, torrent_meta.get("reason", "NO_TORRENT_LINK")))
                return None

            t_resp = None
            for t_attempt in range(3):
                try:
                    t_resp = self.session.get(
                        torrent_url,
                        headers={**HEADERS, "referer": folder_url, "upgrade-insecure-requests": "1"},
                        timeout=(10, 30)
                    )
                    if t_resp.status_code == 429:
                        time.sleep(10)
                        continue
                    if t_resp.status_code == 200:
                        break
                except Exception:
                    time.sleep(2)

            if not t_resp or t_resp.status_code != 200:
                latency_ms = int((time.time() - started_at) * 1000)
                reason = getattr(t_resp, 'status_code', 'TORRENT_DOWNLOAD_ERR')
                print(self._format_game_log_line(current_idx, total_games, title, p, False, False, latency_ms, str(reason)))
                return None

            metadata = self.get_torrent_metadata(t_resp.content)
            if not metadata:
                latency_ms = int((time.time() - started_at) * 1000)
                print(self._format_game_log_line(current_idx, total_games, title, p, False, False, latency_ms, "BAD_TORRENT_METADATA"))
                return None

            filename = os.path.basename(torrent_url)
            with open(os.path.join(page_dir, filename), 'wb') as f:
                f.write(t_resp.content)

            torrent_link = (
                f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{page_dir}/{filename}"
                if GITHUB_REPO else os.path.join(page_dir, filename)
            )
            torrent_link = self._normalize_torrent_link(torrent_link)

            steam, _ = self.get_steam_data(title, verbose=False)
            steam_ok = bool(steam and not steam.get('not_found'))
            latency_ms = int((time.time() - started_at) * 1000)
            reason = "OK" if steam_ok else steam.get('reason', 'NO_STEAM_MATCH')
            match_via = steam.get('match_via') if steam_ok and isinstance(steam, dict) else None
            print(self._format_game_log_line(current_idx, total_games, title, p, True, steam_ok, latency_ms, str(reason), match_via))

            return {
                "title": title,
                "page": p,
                "url": href,
                "last_update": last_update,
                "release_date": release_date,
                "update_info": update_info,
                "update_date": game.get('update_date'),  # Adicionando a data de atualização extraída
                "formatted_update_date": game.get('formatted_update_date'),  # Data formatada no estilo created_at
                "unique_hash": metadata["unique_hash"],
                "fileSize": metadata["total_size"],
                "magnet": metadata["magnet"],
                "torrent_file": torrent_link,
                "created_at": metadata["created_at"],
                "webdav_updated_at": webdav_date,
                "files": metadata["files"],
                "comment": metadata["comment"],
                "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "steam": steam,
            }

        from concurrent.futures import ThreadPoolExecutor, as_completed
        results_data = []
        total_games = len(new_games)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(process_game, g, idx, total_games) for idx, g in enumerate(new_games, start=1)]
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        results_data.append(result)
                except Exception:
                    pass

        # Merge: substitui ou adiciona jogos, detectando atualizações pelo last_update
        data_lock = __import__('threading').Lock()
        added_new_game_names = []
        with data_lock:
            # Criar mapa de título -> item existente
            existing_map = {item['title']: item for item in all_data}

            for current_scraped_game in results_data:
                title = current_scraped_game['title']

                if title not in existing_map:
                    # Jogo novo, adicionar
                    all_data.append(current_scraped_game)
                    existing_map[title] = current_scraped_game
                    added_new_game_names.append(title)
                else:
                    # Jogo existe, verificar se há atualização
                    existing_game_in_all_data = existing_map[title]

                    new_update_info = current_scraped_game.get('update_info')
                    old_update_info = existing_game_in_all_data.get('update_info')
                    new_update_date = current_scraped_game.get('update_date')
                    old_update_date = existing_game_in_all_data.get('update_date')
                    new_formatted_update_date = current_scraped_game.get('formatted_update_date')
                    old_formatted_update_date = existing_game_in_all_data.get('formatted_update_date')

                    is_updated = False

                    # Verificar se há nova informação de atualização
                    if (not old_update_info or old_update_info == 'none') and (new_update_info and new_update_info != 'none'):
                        # Caso 1: O antigo não tinha informação de atualização, e o novo tem.
                        is_updated = True
                    elif new_update_info and new_update_info != 'none' and new_update_info != old_update_info:
                        # Caso 2: Ambos têm informação de atualização, e elas são diferentes.
                        is_updated = True
                    elif new_update_date and old_update_date and new_update_date != old_update_date:
                        # Caso 3: As datas de atualização são diferentes
                        is_updated = True
                    elif not old_update_date and new_update_date:
                        # Caso 4: O jogo antigo não tinha data de atualização, mas o novo tem
                        is_updated = True
                    elif new_formatted_update_date and old_formatted_update_date and new_formatted_update_date != old_formatted_update_date:
                        # Caso 5: As datas formatadas de atualização são diferentes
                        is_updated = True
                    elif not old_formatted_update_date and new_formatted_update_date:
                        # Caso 6: O jogo antigo não tinha data formatada de atualização, mas o novo tem
                        is_updated = True

                    if is_updated:
                        print(f"🔄 Atualização detectada: {title}")
                        # Remover antigo e adicionar novo
                        all_data = [item for item in all_data if item['title'] != title]
                        all_data.append(current_scraped_game)
                        existing_map[title] = current_scraped_game
                    else:
                        # Manter o existente (já está mais atualizado ou sem mudança)
                        # Atualizar apenas os campos que podem ter mudado
                        updated_existing = existing_game_in_all_data.copy()
                        updated_existing.update({
                            "last_update": current_scraped_game.get('last_update', existing_game_in_all_data.get('last_update')),
                            "release_date": current_scraped_game.get('release_date', existing_game_in_all_data.get('release_date')),
                            "update_info": current_scraped_game.get('update_info', existing_game_in_all_data.get('update_info')),
                            "update_date": current_scraped_game.get('update_date', existing_game_in_all_data.get('update_date')),
                            "formatted_update_date": current_scraped_game.get('formatted_update_date', existing_game_in_all_data.get('formatted_update_date')),
                            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
                        # Substituir o item antigo com as informações atualizadas
                        for idx, item in enumerate(all_data):
                            if item['title'] == title:
                                all_data[idx] = updated_existing
                                break
                        existing_map[title] = updated_existing

        # Salvar
        all_data.sort(key=lambda x: x.get('title', ''))
        total = len(all_data)
        print(f"\nSalvando {total} jogos em online_fix_games.json...")
        with open('online_fix_games.json', 'w', encoding='utf-8') as f:
            json.dump({"total": total, "downloads": all_data}, f, indent=4, ensure_ascii=False)

        stats = self._write_stats(
            downloads=all_data,
            requested_pages=limit_page,
            discovered_max_page=max_page,
            scraped_new_games=total_found,
            latest_run_new_game_names=added_new_game_names,
            processed_results=len(results_data),
        )
        print(
            "Stats salvos em stats.json | "
            f"Steam matched: {stats['steam_with_metadata']} | "
            f"Torrents: {stats['torrent_files_total']}"
        )

        def fmt(s):
            m, sec = divmod(int(s), 60)
            h, m = divmod(m, 60)
            return f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"

        total_elapsed = time.time() - run_start
        print(f"Finalizado! {total} jogos em {fmt(total_elapsed)}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Online Fix Scraper")
    parser.add_argument("--pages", type=int, help="Número da página final (ou total de páginas)")
    parser.add_argument("--start-page", type=int, default=1, help="Página por onde começar")
    parser.add_argument("--workers", type=int, default=6, help="Workers para download de torrents+steam (fase 2)")
    parser.add_argument("--baseurl", type=str, default=BASE_URL, help="URL base do site")
    # Usa os valores das env vars como default se existirem
    parser.add_argument("--user", type=str, default=USER, help="Usuário do Online-Fix")
    parser.add_argument("--password", type=str, default=PASS, help="Senha do Online-Fix")
    parser.add_argument("--cookie", type=str, help="Valor do cookie online_fix_auth manual")
    
    args = parser.parse_args()
    
    # Atualiza as variáveis globais para refletir os argumentos passados
    BASE_URL = args.baseurl
    # Atualiza headers globais se a URL base mudou
    HEADERS["referer"] = BASE_URL
    WEBDAV_HEADERS["referer"] = BASE_URL
    
    USER = args.user
    PASS = args.password
    
    print(f"Iniciando scraper para {BASE_URL}")
    scraper = OnlineFixScraper()
    
    if args.cookie:
        print("Usando cookie de autenticação manual.")
        scraper.session.cookies.set("online_fix_auth", args.cookie, domain="online-fix.me")
        scraper.session.cookies.set("online_fix_auth", args.cookie, domain="uploads.online-fix.me")

    scraper.run(pages=args.pages, workers=args.workers, start_page=args.start_page)
