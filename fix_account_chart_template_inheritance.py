#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Corrige classes que estendem 'account.chart.template' de forma incorreta (models.Model)
trocando para models.AbstractModel e removendo '_name' indevido.

Uso:
  python fix_account_chart_template_inheritance.py /docker/azul/18/mod/blue_br --dry-run
  python fix_account_chart_template_inheritance.py /docker/azul/18/mod/blue_br
"""

import argparse
import os
import re
from pathlib import Path
from typing import Tuple, List

# Heurísticas textuais seguras (evita parse AST pesado mantendo simplicidade e backups)
CLASS_HEADER_RE = re.compile(
    r'^(?P<indent>[ \t]*)class[ \t]+(?P<cls>\w+)\s*\(\s*models\.Model\s*\)\s*:',
    flags=re.MULTILINE
)

INHERIT_SINGLE_RE = re.compile(
    r'^[ \t]*_inherit[ \t]*=\s*(?P<quote>[\'"]){1}account\.chart\.template(?P=quote)\s*$',
    flags=re.MULTILINE
)

INHERIT_LIST_RE = re.compile(
    r'^[ \t]*_inherit[ \t]*=\s*\[([^\]]*?)\]\s*$',
    flags=re.MULTILINE | re.DOTALL
)

NAME_RE = re.compile(
    r'^[ \t]*_name[ \t]*=\s*(?P<quote>[\'"]){1}account\.chart\.template(?P=quote)\s*$',
    flags=re.MULTILINE
)

def contains_inherit_account_chart_template(text:str) -> bool:
    if INHERIT_SINGLE_RE.search(text):
        return True
    for m in INHERIT_LIST_RE.finditer(text):
        # verifica se a lista contém 'account.chart.template'
        content = m.group(0)
        if re.search(r"[\'\"]account\.chart\.template[\'\"]", content):
            return True
    return False

def replace_model_with_abstract(text:str) -> Tuple[str, bool]:
    """
    Se o arquivo contém uma classe que herda models.Model E _inherit = 'account.chart.template'
    (ou inclui na lista), troca para models.AbstractModel e remove _name indevido.
    """
    if not contains_inherit_account_chart_template(text):
        return text, False

    # Precisa ter uma classe base models.Model
    if not CLASS_HEADER_RE.search(text):
        return text, False

    changed = False

    # 1) Trocar cabeçalho da classe (apenas onde houver _inherit do account.chart.template no mesmo bloco)
    #    Estratégia: trocar TODO cabeçalho Model -> AbstractModel no arquivo quando há inherit alvo.
    #    (Em repositórios l10n_br, geralmente é 1 classe por arquivo; isso evita regex contextuais frágeis.)
    new_text = CLASS_HEADER_RE.sub(lambda m: f"{m.group('indent')}class {m.group('cls')}(models.AbstractModel):", text)
    if new_text != text:
        changed = True
        text = new_text

    # 2) Remover _name = 'account.chart.template' (se houver)
    new_text = NAME_RE.sub(lambda m: f"# AUTO-FIX: removido (extensão de AbstractModel)\n{m.group(0).splitlines()[0].replace('_name', '# _name')}", text)
    if new_text != text:
        changed = True
        text = new_text

    # 3) Opcional: normalizar _inherit em lista para evitar duplicidade de strings (não estritamente necessário)
    # Mantemos como está para ser minimalista.

    return text, changed

def process_file(path:Path, dry_run:bool=False) -> bool:
    try:
        src = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        src = path.read_text(encoding="latin-1")

    dst, changed = replace_model_with_abstract(src)
    if changed and not dry_run:
        bak = path.with_suffix(path.suffix + ".bak")
        if not bak.exists():
            bak.write_text(src, encoding="utf-8")
        path.write_text(dst, encoding="utf-8")
        print(f"[OK] Corrigido: {path} (backup: {bak.name})")
    elif changed and dry_run:
        print(f"[DRY-RUN] Corrigiria: {path}")
    return changed

def main():
    ap = argparse.ArgumentParser(description="Fix inheritance for account.chart.template (Odoo 18)")
    ap.add_argument("root", help="Diretório raiz do repositório (ex.: /docker/azul/18/mod/blue_br)")
    ap.add_argument("--dry-run", action="store_true", help="Apenas mostra o que seria alterado")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        raise SystemExit(f"Diretório não encontrado: {root}")

    total = 0
    changed = 0
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            # foca em models/ por performance, mas se quiser varrer tudo, remova esse if
            if "models" not in dirpath:
                continue
            p = Path(dirpath) / fn
            total += 1
            if process_file(p, dry_run=args.dry_run):
                changed += 1

    print(f"\nArquivos analisados: {total} | Arquivos alterados: {changed} | Modo: {'DRY-RUN' if args.dry_run else 'WRITE'}")

if __name__ == "__main__":
    main()
