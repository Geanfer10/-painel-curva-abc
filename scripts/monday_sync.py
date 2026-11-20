"""Busca no Monday o status e os orçamentos dos itens das ampliações e grava dados/monday.json.
Roda no GitHub Actions (workflow monday.yml) com o secret MONDAY_API_TOKEN."""
import json, os, sys, urllib.request
from datetime import datetime, timezone, timedelta

BOARD = 18440874858
COL_STATUS, COL_ETAPA, COL_ARQ, COL_LINK = "color_mm99h475", "text_mm99gkgw", "file_mm99m83g", "link_mm99fbc2"
GRUPOS = {"group_mm998yjc": "dmp", "group_mm998kea": "dpa"}
CONTA = "https://messigean18s-team.monday.com"

def api(q, v=None):
    req = urllib.request.Request("https://api.monday.com/v2",
        data=json.dumps({"query": q, "variables": v or {}}).encode(),
        headers={"Authorization": os.environ["MONDAY_API_TOKEN"], "Content-Type": "application/json", "API-Version": "2024-10"})
    r = json.load(urllib.request.urlopen(req, timeout=60))
    if r.get("errors"): sys.exit("Erro do Monday: %s" % r["errors"])
    return r["data"]

CAMPOS = "items { id name group { id title } column_values(ids: [\"%s\",\"%s\",\"%s\",\"%s\"]) { id text value } }" % (COL_STATUS, COL_ETAPA, COL_ARQ, COL_LINK)
pg = api("query { boards(ids: %d) { items_page(limit: 500) { cursor %s } } }" % (BOARD, CAMPOS))["boards"][0]["items_page"]
itens, cursor = pg["items"], pg["cursor"]
while cursor:
    pg = api("query($c: String!) { next_items_page(limit: 500, cursor: $c) { cursor %s } }" % CAMPOS, {"c": cursor})["next_items_page"]
    itens += pg["items"]; cursor = pg["cursor"]

saida = []
for it in itens:
    obra = GRUPOS.get(it["group"]["id"]) or ("dmp" if "dmp" in it["group"]["title"].lower() else "dpa")
    cv = {c["id"]: c for c in it["column_values"]}
    arqs = 0
    try: arqs = len((json.loads(cv[COL_ARQ]["value"] or "{}")).get("files", []))
    except Exception: pass
    link = ""
    try: link = (json.loads(cv[COL_LINK]["value"] or "{}")).get("url", "") or ""
    except Exception: pass
    saida.append({"obra": obra, "nome": it["name"], "etapa": cv[COL_ETAPA]["text"] or "",
                  "status": cv[COL_STATUS]["text"] or "", "arquivos": arqs, "link": link,
                  "url": f"{CONTA}/boards/{BOARD}/pulses/{it['id']}"})
saida.sort(key=lambda x: (x["obra"], x["etapa"], x["nome"]))
novo = {"board": f"{CONTA}/boards/{BOARD}", "itens": saida}
caminho = "dados/monday.json"
try:
    antigo = json.load(open(caminho, encoding="utf-8"))
    if antigo.get("itens") == saida and antigo.get("board") == novo["board"]:
        print("Sem mudanças no Monday."); sys.exit(0)
except FileNotFoundError: pass
novo["atualizado"] = datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y %H:%M")
json.dump(novo, open(caminho, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"Gravado {caminho}: {len(saida)} itens.")
