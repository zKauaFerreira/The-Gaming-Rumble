import json
import os
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_BASE_URL = "https://api.steampowered.com/IStoreService/GetAppList/v1/"
OUTPUT_FILE = "steam_applist_full.json"


def fetch_page(api_key, last_appid):
    params = {
        "key": api_key,
        "last_appid": last_appid,
    }
    url = f"{API_BASE_URL}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "Gaming-Rumble-SteamAppList/1.0"})

    with urlopen(request, timeout=60) as response:
        payload = response.read().decode("utf-8")
        return json.loads(payload)


def main():
    api_key = os.getenv("STEAM_API_KEY", "").strip()
    if not api_key:
        print("Erro: variável de ambiente STEAM_API_KEY não definida.", file=sys.stderr)
        sys.exit(1)

    apps = []
    last_appid = 0
    page = 1

    try:
        while True:
            data = fetch_page(api_key, last_appid)
            response = data.get("response", {})
            page_apps = response.get("apps", [])
            apps.extend(page_apps)

            have_more_results = bool(response.get("have_more_results"))
            last_appid = int(response.get("last_appid", 0))

            print(
                f"Página {page}: +{len(page_apps)} apps | total {len(apps)} | last_appid {last_appid}",
                flush=True,
            )

            page += 1
            if not have_more_results:
                break

    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        print(f"Erro ao consultar API da Steam: {exc}", file=sys.stderr)
        sys.exit(1)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(apps),
        "apps": apps,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    print(f"Arquivo salvo: {OUTPUT_FILE} | total apps: {len(apps)}")


if __name__ == "__main__":
    main()
