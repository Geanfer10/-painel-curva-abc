"""Busca no Monday o status e os orçamentos das ampliações e grava dados/monday.json.
Board: item principal = etapa (coluna "Aplicação" da planilha); subelementos = itens da planilha.
Regra: o subelemento usa o próprio Status/Orçamento; se estiverem vazios, herda os da etapa.
Roda no GitHub Actions (workflow monday.yml) com o secret MONDAY_API_TOKEN."""
import json, os, sys, urllib.request
from datetime import datetime, timezone, timedelta

BOARD, SUBBOARD = 18440874858, 18440876188
P = {"status": "color_mm99h475", "arq": "file_mm99m83g", "link": "link_mm99fbc2"}   # colunas do item principal
S = {"status": "color_mm999dqe", "arq": "file_mm99ehrn", "link": "link_mm99y4s0"}   # colunas dos subelementos
GRUPOS = {"group_mm99t87": "dmp", "group_mm99ew8h": "dpa"}
CONTA = "https://messigean18s-team.monday.com"

def api(q, v=None):
    req = urllib.request.Request("https://api.monday.com/v2",
        data=json.dumps({"query": q, "variables": v or {}}).encode(),
        headers={"Authorization": os.environ["MONDAY_API_TOKEN"], "Content-Type": "application/json", "API-Version": "2024-10"})
    r = json.load(urllib.request.urlopen(req, timeout=60))
    if r.get("errors"): sys.exit("Erro do Monday: %s" % r["errors"])
    return r["data"]

def cols(ids): return "column_values(ids: [%s]) { id text value }" % ",".join('"%s"' % i for i in ids.values())
def arqs(C): return 'assets(assets_source: columns, column_ids: ["%s"]) { name url }' % C["arq"]
CAMPOS = "items { id name group { id title } %s %s subitems { id name %s %s } }" % (cols(P), arqs(P), cols(S), arqs(S))
pg = api("query { boards(ids: %d) { items_page(limit: 200) { cursor %s } } }" % (BOARD, CAMPOS))["boards"][0]["items_page"]
itens, cursor = pg["items"], pg["cursor"]
while cursor:
    pg = api("query($c: String!) { next_items_page(limit: 200, cursor: $c) { cursor %s } }" % CAMPOS, {"c": cursor})["next_items_page"]
    itens += pg["items"]; cursor = pg["cursor"]

def ler(item, C):
    cv = {c["id"]: c for c in item.get("column_values", [])}
    def js(cid):
        try: return json.loads((cv.get(cid) or {}).get("value") or "{}") or {}
        except Exception: return {}
    # link "protected_static": baixa o arquivo direto, mas só para quem está logado no Monday
    orc = [{"nome": a["name"], "url": a["url"]} for a in item.get("assets") or [] if a.get("url")]
    return {"status": ((cv.get(C["status"]) or {}).get("text") or "").strip(),
            "arquivos": len(orc), "orcamentos": orc, "link": js(C["link"]).get("url", "") or ""}

saida, etapas = [], []
for it in itens:
    obra = GRUPOS.get(it["group"]["id"]) or ("dmp" if "dmp" in it["group"]["title"].lower() else "dpa")
    pai, url_pai = ler(it, P), f"{CONTA}/boards/{BOARD}/pulses/{it['id']}"
    etapas.append({"obra": obra, "etapa": it["name"], "status": pai["status"] or "A negociar",
                   "arquivos": pai["arquivos"], "orcamentos": pai["orcamentos"], "link": pai["link"], "url": url_pai})
    for sub in it.get("subitems") or []:
        f = ler(sub, S)
        # orçamento da etapa aparece uma vez só, na etapa; aqui ficam só os orçamentos próprios do item
        saida.append({"obra": obra, "etapa": it["name"], "nome": sub["name"],
                      "status": f["status"] or pai["status"] or "A negociar",
                      "arquivos": f["arquivos"], "orcamentos": f["orcamentos"], "link": f["link"],
                      "url": f"{CONTA}/boards/{SUBBOARD}/pulses/{sub['id']}"})
saida.sort(key=lambda x: (x["obra"], x["etapa"], x["nome"])); etapas.sort(key=lambda x: (x["obra"], x["etapa"]))
novo = {"board": f"{CONTA}/boards/{BOARD}", "etapas": etapas, "itens": saida}
caminho = "dados/monday.json"
try:
    antigo = json.load(open(caminho, encoding="utf-8"))
    if all(antigo.get(k) == novo[k] for k in ("board", "etapas", "itens")):
        print("Sem mudanças no Monday."); sys.exit(0)
except FileNotFoundError: pass
novo["atualizado"] = datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y %H:%M")
json.dump(novo, open(caminho, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"Gravado {caminho}: {len(etapas)} etapas, {len(saida)} itens.")
