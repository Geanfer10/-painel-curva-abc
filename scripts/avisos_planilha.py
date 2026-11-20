"""Compara a planilha nova com a última versão vista (dados/planilha_snapshot.json) e grava as
mudanças em dados/avisos.json, que o painel mostra no quadro "Mudanças na planilha".
Não precisa do Monday: roda sempre que o robô do PC envia a planilha."""
import json, os
from datetime import datetime, timezone, timedelta
from planilha_para_monday import ler_planilha, norm

SNAP, AVISOS, MAX_LOTES = "dados/planilha_snapshot.json", "dados/avisos.json", 30

def chaves(etapas):  # {(etapa_norm, nome_norm, n): (etapa, nome, valor)} — n separa nomes repetidos
    out = {}
    for etapa, itens in etapas.items():
        cont = {}
        for nome, v in itens:
            k = (norm(etapa), norm(nome)); cont[k] = cont.get(k, 0) + 1
            out[k + (cont[k],)] = (etapa, nome, v)
    return out

def comparar(antes, agora):
    mud = []
    for obra in sorted(set(antes) | set(agora)):
        a, b = antes.get(obra, {}), agora.get(obra, {})
        ea, eb = {norm(e): e for e in a}, {norm(e): e for e in b}
        for k in eb.keys() - ea.keys(): mud.append({"obra": obra, "tipo": "etapa_nova", "etapa": eb[k], "item": "", "de": None, "para": round(sum(v or 0 for _, v in b[eb[k]]), 2)})
        for k in ea.keys() - eb.keys(): mud.append({"obra": obra, "tipo": "etapa_removida", "etapa": ea[k], "item": "", "de": round(sum(v or 0 for _, v in a[ea[k]]), 2), "para": None})
        ca, cb = chaves(a), chaves(b)
        for k in cb.keys() - ca.keys():
            if k[0] in ea: e, n, v = cb[k]; mud.append({"obra": obra, "tipo": "novo", "etapa": e, "item": n, "de": None, "para": v})
        for k in ca.keys() - cb.keys():
            if k[0] in eb: e, n, v = ca[k]; mud.append({"obra": obra, "tipo": "removido", "etapa": e, "item": n, "de": v, "para": None})
        for k in ca.keys() & cb.keys():
            va, vb = ca[k][2], cb[k][2]
            if (va is None) != (vb is None) or (va is not None and abs(va - vb) > 0.005):
                mud.append({"obra": obra, "tipo": "valor", "etapa": cb[k][0], "item": cb[k][1], "de": va, "para": vb})
    return mud

def main():
    agora = ler_planilha("dados/planilha.xlsx")
    if not os.path.exists(SNAP):
        json.dump(agora, open(SNAP, "w", encoding="utf-8"), ensure_ascii=False); print("Primeira versão guardada."); return
    antes = {o: {e: [tuple(x) for x in its] for e, its in et.items()} for o, et in json.load(open(SNAP, encoding="utf-8")).items()}
    mud = comparar(antes, agora)
    json.dump(agora, open(SNAP, "w", encoding="utf-8"), ensure_ascii=False)
    if not mud: print("Planilha salva sem mudanças de itens ou valores."); return
    av = json.load(open(AVISOS, encoding="utf-8")) if os.path.exists(AVISOS) else {"lotes": []}
    quando = datetime.now(timezone(timedelta(hours=-3)))
    av["lotes"] = ([{"quando": quando.strftime("%d/%m/%Y %H:%M"), "iso": quando.isoformat(timespec="minutes"), "mudancas": mud}] + av["lotes"])[:MAX_LOTES]
    json.dump(av, open(AVISOS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for m in mud: print("MUDANÇA:", m)

if __name__ == "__main__": main()
