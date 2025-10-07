#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys, os, csv, re, difflib, argparse
from pathlib import Path

def infer_model_from_filename(path: Path) -> str | None:
    name = path.name
    if not name.endswith(".csv"):
        return None
    base = name[:-4]
    # igual ao seu monkey-patch: pega antes do primeiro '-'
    return base.split("-")[0].replace("-", "_")

def read_csv_header(path: Path):
    with path.open("r", encoding="utf-8", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except Exception:
            class D: delimiter = ","
            dialect = D()
        reader = csv.reader(f, dialect)
        try:
            header = next(reader)
        except StopIteration:
            return []
        header = [h.replace("\ufeff","").strip() for h in header]
        return header, dialect.delimiter

def replace_in_header_line(content: str, old: str, new: str):
    # troca só no cabeçalho (primeira linha), respeitando , ; \t
    first_newline = content.find("\n")
    if first_newline == -1:
        first_newline = len(content)
    head = content[:first_newline].replace("\ufeff","")
    body = content[first_newline:]
    # aceita vírgula, ponto-e-vírgula ou tab
    head_fixed = re.sub(rf'(^|,|;|\t){re.escape(old)}(,|;|\t|$)',
                        rf'\1{new}\2', head)
    return head_fixed + body, head != head_fixed

def main():
    ap = argparse.ArgumentParser(description="Valida e corrige cabeçalhos CSV contra modelos da v18.")
    ap.add_argument("--conf", required=True, help="Ex.: /etc/odoo/dev18.conf")
    ap.add_argument("--db", required=True, help="Ex.: odoo18_blue")
    ap.add_argument("root", help="Raiz do repo (ex.: /docker/azul/18/mod/blue_br)")
    ap.add_argument("--apply", action="store_true", help="Aplicar correções automáticas")
    ap.add_argument("--auto-map", default="name:display_name",
                    help="Mapeamentos automáticos (ex.: 'name:display_name;descr:description')")
    args = ap.parse_args()

    os.environ.setdefault("ODOO_RC", args.conf)

    import odoo
    odoo.tools.config.parse_config([])
    odoo.sql_db.close_all()
    registry = odoo.modules.registry.Registry(args.db)

    # monta dict de mapeamentos
    automap = {}
    if args.auto_map:
        for pair in args.auto_map.split(";"):
            if ":" in pair:
                a,b = pair.split(":",1)
                automap[a.strip()] = b.strip()

    root = Path(args.root).resolve()
    bad_count = 0
    fixed = []

    with registry.cursor() as cr:
        env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})

        for csv_path in root.rglob("*.csv"):
            if "/data/" not in str(csv_path):
                continue
            model = infer_model_from_filename(csv_path)
            if not model:
                continue

            if model not in env:
                # arquivo pode estar obsoleto ou com nome de modelo antigo
                print(f"[WARN] {csv_path} -> modelo '{model}' não existe na v18.")
                continue

            header_delim = ","
            header, header_delim = read_csv_header(csv_path)
            if not header:
                continue

            fields = set(env[model]._fields.keys())
            special = {"id","xml_id","lang"}  # campos especiais do import
            missing = []
            for h in header:
                if not h or h in special:
                    continue
                if h.endswith("/id") and h[:-3] in fields:
                    continue
                if h not in fields:
                    missing.append(h)

            if missing:
                bad_count += 1
                print(f"\n[CSV INVALID] {csv_path}")
                print(f"  modelo: {model}")
                print(f"  campos inválidos: {', '.join(missing)}")

                # sugestões de nomes próximos
                for m in missing:
                    sugg = difflib.get_close_matches(m, fields, n=5, cutoff=0.6)
                    if sugg:
                        print(f"    - sugestão p/ '{m}': {', '.join(sugg)}")

                if not args.apply:
                    continue

                # tentativas de correção seguras:
                # 1) se 'name' é inválido e modelo não tem 'name' mas tem automap[name] (padrão: display_name) -> troca
                content = csv_path.read_text(encoding="utf-8")
                changed_any = False

                for old, new in automap.items():
                    if old in missing and old not in fields and new in fields:
                        content2, changed = replace_in_header_line(content, old, new)
                        if changed:
                            content = content2
                            changed_any = True
                            print(f"  [FIX] cabeçalho: {old} -> {new}")

                if changed_any:
                    bak = csv_path.with_suffix(csv_path.suffix + ".bak")
                    if not bak.exists():
                        bak.write_text(csv_path.read_text(encoding="utf-8"), encoding="utf-8")
                    csv_path.write_text(content, encoding="utf-8")
                    fixed.append(csv_path)
                else:
                    print("  [INFO] sem correção automática segura. Ajuste manual recomendado.")

    print("\n== Resumo ==")
    print(f"CSVs problemáticos: {bad_count}")
    if fixed:
        print("CSVs corrigidos automaticamente:")
        for p in fixed:
            print(f"  - {p}")

if __name__ == "__main__":
    main()
