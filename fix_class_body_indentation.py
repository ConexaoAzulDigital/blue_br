#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Corrige IndentationError após 'class ...:' quando a primeira linha do corpo
não está indentada (caso típico após refactors em Odoo 17/18).

Uso:
  python fix_class_body_indentation.py /docker/azul/18/mod/blue_br
  # opcional: restringir a um módulo:
  python fix_class_body_indentation.py /docker/azul/18/mod/blue_br/l10n_br_account
"""

import argparse
import os
from pathlib import Path
import re

CLASS_RE = re.compile(r'^([ \t]*)class\s+\w+\s*\(.*?\)\s*:\s*(#.*)?$')
DEF_OR_CLASS_AT_TOP_RE = re.compile(r'^([ \t]*)(def|class)\b')
NONEMPTY_RE = re.compile(r'\S')

def detab(line: str) -> str:
    # tabs -> 4 spaces
    return line.replace('\t', '    ')

def leading_spaces(s: str) -> int:
    return len(s) - len(s.lstrip(' '))

def fix_file(path: Path) -> bool:
    try:
        text = path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        text = path.read_text(encoding='latin-1')

    # Normalize tabs to spaces first
    lines = [detab(l.rstrip()) for l in text.splitlines()]
    changed = False
    i = 0
    n = len(lines)

    while i < n:
        m = CLASS_RE.match(lines[i])
        if not m:
            i += 1
            continue

        class_indent = leading_spaces(m.group(1).replace('\t', '    '))
        # find first non-empty, non-comment-only line after class
        j = i + 1
        while j < n:
            if NONEMPTY_RE.search(lines[j]) and not lines[j].lstrip().startswith('#'):
                break
            j += 1

        if j >= n:
            # classe no fim do arquivo sem corpo -> insere "pass"
            lines.append(' ' * (class_indent + 4) + 'pass')
            changed = True
            break

        # Se a linha não está indentada o suficiente, indentar bloco até “fechar”
        line_indent = leading_spaces(lines[j])
        if line_indent <= class_indent:
            # vamos indentar linhas consecutivas que compõem o corpo
            k = j
            while k < n:
                # Para ao encontrar uma linha vazia seguida de um novo def/class de mesmo nível,
                # ou quando encontramos um novo def/class com indent <= class_indent
                if not NONEMPTY_RE.search(lines[k]):  # linha vazia
                    # olhe a próxima “interessante”; não encerra ainda
                    pass
                else:
                    # se começa um novo def/class com indent <= class_indent, então corpo anterior acabou
                    m2 = DEF_OR_CLASS_AT_TOP_RE.match(lines[k])
                    if m2 and leading_spaces(m2.group(1)) <= class_indent:
                        break
                    # caso contrário, se a indentação atual é <= class_indent, aumente
                    if leading_spaces(lines[k]) <= class_indent:
                        lines[k] = ' ' * (class_indent + 4) + lines[k].lstrip()
                        changed = True
                k += 1
        # avança o cursor
        i = j + 1

    if changed:
        bak = path.with_suffix(path.suffix + '.bak')
        if not bak.exists():
            path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            bak.write_text(text, encoding='utf-8')  # guarda original
            # trocamos para que o arquivo final seja o fixado, e .bak o original
            # se preferir ao contrário, inverta as duas linhas acima
        else:
            path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return changed

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root', help='Diretório raiz (ex.: /docker/azul/18/mod/blue_br)')
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        raise SystemExit(f"Diretório não encontrado: {root}")

    total = 0
    fixed = 0
    for dp, _, files in os.walk(root):
        for fn in files:
            if not fn.endswith('.py'):
                continue
            # foque em models/ para ser mais assertivo
            if 'models' not in dp:
                continue
            p = Path(dp) / fn
            total += 1
            if fix_file(p):
                print(f"[FIXED] {p}")
                fixed += 1

    print(f"\nArquivos analisados: {total} | Arquivos corrigidos: {fixed}")
    if fixed == 0:
        print("Nenhuma correção necessária ou padrão diferente do esperado.")

if __name__ == '__main__':
    main()
