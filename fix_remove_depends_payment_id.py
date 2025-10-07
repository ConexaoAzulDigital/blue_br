#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Remove 'payment_id' de @api.depends (Odoo 17/18) e reporta usos diretos.
- Em .py: edita decorators @api.depends(...) removendo 'payment_id'.
  * Se restar vazio, remove o decorator.
  * Reporta usos de 'payment_id' no corpo (para revisão manual).
- Em .xml: apenas RELATA ocorrências (não altera).

Uso:
  python fix_remove_depends_payment_id.py /docker/azul/18/mod/blue_br
"""

import argparse
import os
import re
from pathlib import Path
from typing import List, Tuple

# Regexes
DEPENDS_RE = re.compile(
    r"^([ \t]*)@api\.depends\((?P<args>[^)]*)\)[ \t]*$",
    re.MULTILINE,
)

# pega strings dentro de aspas simples ou duplas
TOKEN_RE = re.compile(r"""['"]([^'"]+)['"]""")

# detectar uso direto de payment_id em código (bem simples)
USE_RE = re.compile(r"\bself\.payment_id\b")

def strip_comments(line: str) -> str:
    # remove comentários no final da linha (simples)
    # não é 100% perfeito, mas suficiente p/ depends
    idx = line.find("#")
    return line if idx == -1 else line[:idx]

def clean_depends_args(argstr: str) -> Tuple[str, bool, bool]:
    """
    Remove 'payment_id' dos argumentos do depends.
    Retorna (novo_args, mudou, ficou_vazio)
    """
    original = argstr
    s = strip_comments(argstr)
    # extrai todos os tokens '...'
    tokens = TOKEN_RE.findall(s)
    if not tokens:
        return original, False, False
    new_tokens = [t for t in tokens if t != "payment_id"]
    if new_tokens == tokens:
        return original, False, False
    if not new_tokens:
        return "", True, True
    # Remonta com aspas simples separadas por vírgula e espaço
    new_arg = ", ".join(f"'{t}'" for t in new_tokens)
    return new_arg, True, False

def process_python_file(path: Path) -> Tuple[bool, List[str]]:
    try:
        src = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        src = path.read_text(encoding="latin-1")

    changed = False
    reports: List[str] = []

    # 1) remover 'payment_id' das depends
    def repl(m):
        nonlocal changed
        indent = m.group(1)
        args = m.group("args")
        new_args, did_change, became_empty = clean_depends_args(args)
        if not did_change:
            return m.group(0)
        changed = True
        if became_empty:
            # remove decorator
            return f"{indent}# AUTO-FIX: removed @api.depends('payment_id') (field not present in v18)"
        # reescreve a linha
        return f"{indent}@api.depends({new_args})"

    new_src = DEPENDS_RE.sub(repl, src)

    # 2) reportar uso direto de self.payment_id
    for i, line in enumerate(new_src.splitlines(), start=1):
        if USE_RE.search(line):
            reports.append(f"{path}:{i}: uso direto de self.payment_id (revisar lógica)")

    if changed:
        bak = path.with_suffix(path.suffix + ".bak")
        if not bak.exists():
            bak.write_text(src, encoding="utf-8")
        path.write_text(new_src, encoding="utf-8")
        print(f"[PY FIX] {path}  (backup: {bak.name})")

    return changed, reports

def process_xml_file(path: Path) -> List[str]:
    try:
        src = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        src = path.read_text(encoding="latin-1")
    reports = []
    # apenas reporta ocorrências
    for i, line in enumerate(src.splitlines(), start=1):
        if "payment_id" in line:
            reports.append(f"{path}:{i}: XML contém 'payment_id' (revisar attrs/domínios/onchange)")
    return reports

def main():
    ap = argparse.ArgumentParser(description="Remove 'payment_id' de @api.depends e reporta usos.")
    ap.add_argument("root", help="Diretório raiz do repo")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        raise SystemExit(f"Diretório não encontrado: {root}")

    py_changed = 0
    py_reports: List[str] = []
    xml_reports: List[str] = []

    for dp, _, files in os.walk(root):
        for fn in files:
            p = Path(dp) / fn
            if fn.endswith(".py"):
                chg, reps = process_python_file(p)
                py_changed += int(chg)
                py_reports.extend(reps)
            elif fn.endswith(".xml"):
                xml_reports.extend(process_xml_file(p))

    print("\nResumo:")
    print(f"- .py alterados: {py_changed}")
    if py_reports:
        print("- Revisar (uso direto de self.payment_id):")
        for r in py_reports:
            print(f"  * {r}")
    if xml_reports:
        print("- XML com 'payment_id' (revisar manualmente):")
        for r in xml_reports:
            print(f"  * {r}")

if __name__ == "__main__":
    main()
