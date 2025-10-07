#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Remove 'payment_id' de @api.depends(...) inclusive quando o decorator está em múltiplas linhas.
- Cria backups .bak.
- Se o depends ficaria vazio, comenta a linha do decorator.
- Relata quaisquer @api.depends remanescentes com 'payment_id'.

Uso:
  python3 fix_depends_payment_id_multiline.py /docker/azul/18/mod/blue_br
"""

import argparse
import os
import re
from pathlib import Path

START_RE = re.compile(r'^([ \t]*)@api\.depends\s*\(')  # início do decorator
TOKEN_RE  = re.compile(r"""(['"])(.*?)\1""")           # tokens entre aspas
PAYMENT   = 'payment_id'

def process_file(path: Path):
    try:
        text = path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        text = path.read_text(encoding='latin-1')

    lines = text.splitlines()
    n = len(lines)
    i = 0
    changed = False
    leftovers = []

    while i < n:
        m = START_RE.match(lines[i])
        if not m:
            i += 1
            continue

        indent = m.group(1)
        # capturar bloco do decorator @api.depends( ... ) até o parêntese fechar
        buf = [lines[i]]
        paren = lines[i].count('(') - lines[i].count(')')
        j = i + 1
        while j < n and paren > 0:
            buf.append(lines[j])
            paren += lines[j].count('(') - lines[j].count(')')
            j += 1

        # conteúdo completo do decorator
        block = "\n".join(buf)
        inner = block.split('(', 1)[1].rsplit(')', 1)[0] if '(' in block and ')' in block else ''

        # extrair tokens entre aspas
        tokens = [t[1] for t in TOKEN_RE.findall(inner)]
        if not tokens or PAYMENT not in tokens:
            # nada a fazer; apenas registrar se ainda contém payment_id bruto
            if PAYMENT in inner:
                leftovers.append((path, i+1))
            i = j
            continue

        # remover payment_id
        new_tokens = [t for t in tokens if t != PAYMENT]

        # reconstruir
        if not new_tokens:
            # comentar todo o decorator (vira uma linha com comentário)
            new_block = f"{indent}# AUTO-FIX: removed @api.depends('payment_id') - field doesn't exist in v18"
        else:
            args = ", ".join(f"'{t}'" for t in new_tokens)
            new_block = f"{indent}@api.depends({args})"

        # aplicar alteração nas linhas originais
        before = lines[:i]
        after  = lines[j:]
        lines = before + [new_block] + after
        n = len(lines)
        changed = True
        i = i + 1  # avança após o decorator reescrito

    # verificar se ainda restou algum depends com payment_id (por segurança)
    out_text = "\n".join(lines)
    for idx, ln in enumerate(lines, 1):
        if '@api.depends' in ln and 'payment_id' in ln:
            leftovers.append((path, idx))

    if changed:
        bak = path.with_suffix(path.suffix + '.bak')
        if not bak.exists():
            bak.write_text(text, encoding='utf-8')
        path.write_text(out_text, encoding='utf-8')
        print(f"[FIX] {path} (backup: {bak.name})")

    return changed, leftovers

def main():
    ap = argparse.ArgumentParser(description="Remove 'payment_id' de @api.depends (multilinha).")
    ap.add_argument("root", help="Diretório raiz (ex.: /docker/azul/18/mod/blue_br)")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        raise SystemExit(f"Diretório não encontrado: {root}")

    total_changed = 0
    still_left = []

    for dp, _, files in os.walk(root):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            p = Path(dp) / fn
            chg, left = process_file(p)
            total_changed += int(chg)
            still_left.extend(left)

    print(f"\nArquivos alterados: {total_changed}")
    if still_left:
        print("ATENÇÃO: ainda existem @api.depends com 'payment_id':")
        for path, lineno in still_left:
            print(f"  - {path}:{lineno}")

if __name__ == "__main__":
    main()
