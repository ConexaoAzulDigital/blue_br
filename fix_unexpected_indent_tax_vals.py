#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys, re, py_compile
from pathlib import Path

if len(sys.argv) != 2:
    print("Uso: python fix_unexpected_indent_tax_vals.py /caminho/para/account_tax_template.py")
    sys.exit(1)

p = Path(sys.argv[1]).resolve()
src = p.read_text(encoding="utf-8")

lines = src.splitlines()
n = len(lines)

def indent_len(s: str) -> int:
    s = s.replace("\t", "    ")
    return len(s) - len(s.lstrip(" "))

CLASS_RE = re.compile(r'^[ \t]*class[ \t]+\w+[ \t]*\([^)]*\)[ \t]*:\s*(#.*)?$')
DEF_TGT_RE = re.compile(r'^[ \t]*def[ \t]+_get_tax_vals\s*\(')

# Rastrea pilha de classes pelo nível de indent
stack = []  # lista de indents de classes abertas
changed = False

for i in range(n):
    ln = lines[i]
    # normaliza tabs para cálculo
    cur_indent = indent_len(ln)

    # fecha classes se o indent caiu
    while stack and cur_indent <= stack[-1]:
        stack.pop()

    if CLASS_RE.match(ln):
        # indent de classe é o indent da linha; corpo deve ser > esse valor
        stack.append(cur_indent)

    if DEF_TGT_RE.match(ln):
        # estamos dentro de uma classe?
        if stack:
            desired = stack[-1] + 4
        else:
            desired = 0

        if cur_indent != desired:
            # aplica recuo desejado preservando o conteúdo sem espaços à esquerda
            stripped = ln.lstrip(" \t")
            lines[i] = (" " * desired) + stripped
            changed = True

# Se alterou, salva backup e arquivo
if changed:
    bak = p.with_suffix(p.suffix + ".bak")
    if not bak.exists():
        bak.write_text(src, encoding="utf-8")
    p.write_text("\n".join(lines) + ("\n" if src.endswith("\n") else ""), encoding="utf-8")
    print(f"[FIXED] {p} (backup: {bak.name})")
else:
    print("[OK] Nada a alterar.")

# Validação rápida
try:
    py_compile.compile(str(p), doraise=True)
    print("[COMPILE] OK")
except Exception as e:
    print(f"[COMPILE] ERRO: {e}")
    sys.exit(2)
