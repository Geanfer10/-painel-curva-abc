"""Leva a planilha (dados/planilha.xlsx, enviada pelo robô do PC) para o board do Monday.
- Etapa nova (coluna "Aplicação")  -> cria o item principal no grupo da obra.
- Item novo                        -> cria o subelemento dentro da etapa.
- Valor mudou                      -> atualiza "Valor previsto (R$)" (etapa e item).
- Item que saiu da planilha        -> NÃO apaga (pode ter orçamento anexado); só avisa no log.
Status, orçamentos e links do Monday nunca são alterados por este script."""
import json, os, sys, unicodedata, urllib.request
import openpyxl

BOARD, SUBBOARD = 18440874858, 18440876188
GRUPO = {"dmp": "group_mm99t87", "dpa": "group_mm99ew8h"}
ABA = {"Expansão DMP": "dmp", "DPA IV": "dpa"}
COL_STATUS, COL_VALOR, SUB_VALOR = "color_mm99h475", "numeric_mm99tkgt", "numeric_mm994a71"

def norm(s): return " ".join(unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().lower().split())

def api(q, v=None):
    req = urllib.request.Request("https://api.monday.com/v2",
        data=json.dumps({"query": q, "variables": v or {}}).encode(),
        headers={"Authorization": os.environ["MONDAY_API_TOKEN"], "Content-Type": "application/json", "API-Version": "2024-10"})
    r = json.load(urllib.request.urlopen(req, timeout=60))
    if r.get("errors"): sys.exit("Erro do Monday: %s" % r["errors"])
    return r["data"]

# ---------- 1. planilha ----------
def ler_planilha(caminho):
    wb = openpyxl.load_workbook(caminho, data_only=True, read_only=True)
    obras = {}
    for aba, obra in ABA.items():
        if aba not in wb.sheetnames: print(f"Aviso: aba '{aba}' não encontrada."); continue
        cab, etapas = None, {}
        for r in wb[aba].iter_rows(values_only=True):
            if cab is None:
                n = [norm(c) for c in r]
                if any(x in ("descricao", "insumo ou servico") for x in n) and "preco total" in n:
                    cab = {"d": next(i for i, x in enumerate(n) if x in ("descricao", "insumo ou servico")),
                           "v": n.index("preco total"), "a": n.index("aplicacao")}
                continue
            d = r[cab["d"]] if cab["d"] < len(r) else None
            if d is None or not str(d).strip(): continue
            v = r[cab["v"]] if cab["v"] < len(r) else None
            a = str(r[cab["a"]] or "Não definida").strip()
            etapas.setdefault(a, []).append((str(d).strip(), round(v, 2) if isinstance(v, (int, float)) else None))
        obras[obra] = etapas
    return obras

# ---------- 2. board ----------
def ler_board():
    q = """query { boards(ids: %d) { items_page(limit: 200) { cursor items { id name group { id }
        column_values(ids: ["%s"]) { text } subitems { id name column_values(ids: ["%s"]) { text } } } } } }""" % (BOARD, COL_VALOR, SUB_VALOR)
    pg = api(q)["boards"][0]["items_page"]; itens = pg["items"]
    if pg["cursor"]: sys.exit("Board com mais de 200 etapas: ajustar paginação.")
    board = {k: {} for k in GRUPO}
    inv = {v: k for k, v in GRUPO.items()}
    for it in itens:
        obra = inv.get(it["group"]["id"])
        if not obra: continue
        num = lambda cv: float(cv[0]["text"]) if cv and cv[0]["text"] not in (None, "") else None
        board[obra][norm(it["name"])] = {"id": it["id"], "nome": it["name"], "valor": num(it["column_values"]),
            "subs": {}}
        for s in it["subitems"] or []:  # nomes iguais (só muda espaço) ficam numa lista, casados na ordem
            board[obra][norm(it["name"])]["subs"].setdefault(norm(s["name"]), []).append({"id": s["id"], "nome": s["name"], "valor": num(s["column_values"])})
    return board

def difere(a, b): return (a is None) != (b is None) or (a is not None and abs(a - b) > 0.02)

def main():
    plan, board = ler_planilha("dados/planilha.xlsx"), ler_board()
    criadas = novos = valores = 0
    for obra, etapas in plan.items():
        for etapa, itens in etapas.items():
            total = round(sum(v for _, v in itens if v), 2)
            pai = board[obra].get(norm(etapa))
            if not pai:
                cv = json.dumps({COL_STATUS: {"label": "A negociar"}, COL_VALOR: str(total)})
                r = api("mutation($n:String!,$c:JSON!){create_item(board_id:%d,group_id:\"%s\",item_name:$n,column_values:$c){id}}" % (BOARD, GRUPO[obra]), {"n": etapa, "c": cv})
                pai = {"id": r["create_item"]["id"], "valor": total, "subs": {}}; criadas += 1
                print(f"[{obra}] etapa nova: {etapa}")
            elif difere(pai["valor"], total):
                api("mutation($c:JSON!){change_multiple_column_values(board_id:%d,item_id:%s,column_values:$c){id}}" % (BOARD, pai["id"]), {"c": json.dumps({COL_VALOR: str(total)})}); valores += 1
            for nome, v in itens:
                lst = pai["subs"].get(norm(nome)) or []
                sub = lst.pop(0) if lst else None
                cv = json.dumps({SUB_VALOR: str(v)} if v is not None else {})
                if not sub:
                    api("mutation($n:String!,$c:JSON!){create_subitem(parent_item_id:%s,item_name:$n,column_values:$c){id}}" % pai["id"], {"n": nome[:255], "c": cv}); novos += 1
                    print(f"[{obra}] item novo em {etapa}: {nome}")
                elif difere(sub["valor"], v):
                    api("mutation($c:JSON!){change_multiple_column_values(board_id:%d,item_id:%s,column_values:$c){id}}" % (SUBBOARD, sub["id"]), {"c": json.dumps({SUB_VALOR: str(v) if v is not None else ""})}); valores += 1
                    print(f"[{obra}] valor atualizado: {nome} -> {v}")
            for s in [x for l in pai["subs"].values() for x in l]: print(f"[{obra}] AVISO: '{s['nome']}' ({etapa}) está no Monday mas não na planilha.")
        for k, p in board[obra].items():
            if k not in {norm(e) for e in etapas}: print(f"[{obra}] AVISO: etapa '{p['nome']}' está no Monday mas não na planilha.")
    print(f"Planilha -> Monday: {criadas} etapas novas, {novos} itens novos, {valores} valores atualizados.")

if __name__ == "__main__": main()
