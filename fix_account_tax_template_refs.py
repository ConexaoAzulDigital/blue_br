#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Refatora referências a 'account.tax.template' (v16) para 'account.tax' (v18)
e certifica 'account' em depends dos manifests.

- Converte em .py:
    _inherit = 'account.tax.template'           -> 'account.tax'
    fields.Many2one('account.tax.template', ...) -> 'account.tax'
    fields.One2many('account.tax.template', ...) -> 'account.tax'
    fields.Many2many('account.tax.template', ...) -> 'account.tax'
- Converte em .xml:
    <record model="account.tax.template" ...>   -> model="account.tax"
    domain/context/attrs onde houver a string exata -> troca direta conservadora
- Remove em XML atributos/campos óbvios de template que travam (ex.: chart_template_id)
- Adiciona 'account' no depends de cada __manifest__.py que tocar em taxes.

Uso:
  python fix_account_tax_template_refs.py /docker/azul/18/mod/blue_br --dry-run
  python fix_account_tax_template_refs.py /docker/azul/18/mod/blue_br
"""

import argparse
import os
import re
from pathlib import Path

PY_REL_RE = re.compile(
    r"""(['"])account\.tax\.template\1""",
    flags=re.MULTILINE
)

PY_INHERIT_LINE = re.compile(
    r"""(^[ \t]*_inherit[ \t]*=[ \t]*)(['"])account\.tax\.template\2([ \t]*$)""",
    flags=re.MULTILINE
)

PY_CLASS_MODEL_HDR = re.compile(
    r"""(^[ \t]*class[ \t]+\w+[ \t]*\([ \t]*models\.Model[ \t]*\)[ \t]*:)""",
    flags=re.MULTILINE
)

XML_MODEL_ATTR = re.compile(
    r'''(<record\b[^>]*\bmodel\s*=\s*")account\.tax\.template(")''',
    flags=re.IGNORECASE
)

XML_GENERIC_STR = re.compile(
    r"""account\.tax\.template""",
    flags=re.IGNORECASE
)

# Campos de template que não existem mais e travam ao carregar dados
XML_TEMPLATE_FIELDS_TO_DROP = [
    'chart_template_id',
]

MANIFEST_DEPENDS = re.compile(
    r"""(^[ \t]*'depends'\s*:\s*\[)(.*?)(\],?)""",
    flags=re.DOTALL | re.MULTILINE
)

def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        return path.read_text(encoding='latin-1')

def write_backup_and_save(path: Path, new: str, old: str):
    bak = path.with_suffix(path.suffix + '.bak')
    if not bak.exists():
        bak.write_text(old, encoding='utf-8')
    path.write_text(new, encoding='utf-8')

def fix_python_file(path: Path, dry: bool) -> bool:
    if path.suffix != '.py':
        return False
    src = read_text(path)
    orig = src

    # Troca relações ('account.tax.template' -> 'account.tax')
    src = PY_REL_RE.sub(r"\1account.tax\1", src)

    # Em casos de _inherit = 'account.tax.template' -> 'account.tax'
    src = PY_INHERIT_LINE.sub(r"\1'account.tax'\3", src)

    if src != orig and not dry:
        write_backup_and_save(path, src, orig)
        print(f"[OK] PY  : {path}")
    return src != orig

def strip_xml_template_fields(txt: str) -> str:
    # Remove linhas simples do tipo <field name="chart_template_id">...</field>
    for fname in XML_TEMPLATE_FIELDS_TO_DROP:
        txt = re.sub(
            rf'''[ \t]*<field[^>]*\bname\s*=\s*["']{re.escape(fname)}["'][^>]*/>\s*\n?''',
            '',
            txt,
            flags=re.IGNORECASE
        )
        txt = re.sub(
            rf'''[ \t]*<field[^>]*\bname\s*=\s*["']{re.escape(fname)}["'][^>]*>.*?</field>\s*\n?''',
            '',
            txt,
            flags=re.IGNORECASE | re.DOTALL
        )
    return txt

def fix_xml_file(path: Path, dry: bool) -> bool:
    if path.suffix != '.xml':
        return False
    src = read_text(path)
    orig = src

    # 1) <record model="account.tax.template" ...> -> account.tax
    src = XML_MODEL_ATTR.sub(r'\1account.tax\2', src)

    # 2) Qualquer ocorrência literal remanescente de 'account.tax.template' -> 'account.tax'
    src = XML_GENERIC_STR.sub('account.tax', src)

    # 3) Remover campos problemáticos de templates
    src = strip_xml_template_fields(src)

    if src != orig and not dry:
        write_backup_and_save(path, src, orig)
        print(f"[OK] XML : {path}")
    return src != orig

def ensure_manifest_depends_account(path: Path, dry: bool) -> bool:
    """
    Se o módulo tem .py/.xml com 'account.tax' (após refactor) e não depende de 'account',
    adiciona 'account' em depends.
    """
    if path.name != '__manifest__.py':
        return False
    src = read_text(path)
    orig = src

    # Heurística: se o próprio módulo aponta para taxes (agora 'account.tax'), é recomendável depender de 'account'
    module_dir = path.parent
    touches_tax = False
    for p in module_dir.rglob('*'):
        if p.is_file() and p.suffix in ('.py', '.xml'):
            try:
                t = read_text(p)
            except Exception:
                continue
            if 'account.tax' in t:
                touches_tax = True
                break

    if not touches_tax:
        return False

    # já depende?
    if "'account'" in src or '"account"' in src:
        return False

    def add_account_dep(m):
        head, body, tail = m.group(1), m.group(2), m.group(3)
        # injeta 'account' no começo da lista (evita vírgula duplicada/format bagunçado)
        body_clean = body.strip()
        if body_clean:
            new_body = "'account', " + body_clean
        else:
            new_body = "'account'"
        return f"{head}{new_body}{tail}"

    new_src, n = MANIFEST_DEPENDS.subn(add_account_dep, src, count=1)
    if n == 0:
        # não encontrou depends -> cria uma entrada depends minimalista
        new_src = src.rstrip() + "\n\n# AUTO-FIX: adicionando depends\n"
        new_src += "depends = ['account']\n"

    if new_src != orig and not dry:
        write_backup_and_save(path, new_src, orig)
        print(f"[OK] MAN : {path} (added 'account' to depends)")
    return new_src != orig

def main():
    ap = argparse.ArgumentParser(description="Fix refs to account.tax.template (v18)")
    ap.add_argument("root", help="Diretório raiz (ex.: /docker/azul/18/mod/blue_br)")
    ap.add_argument("--dry-run", action="store_true", help="Mostrar mudanças sem gravar")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        raise SystemExit(f"Diretório não encontrado: {root}")

    py_changes = xml_changes = man_changes = 0
    for p in root.rglob('*'):
        if not p.is_file():
            continue
        if p.suffix == '.py':
            py_changes += 1 if fix_python_file(p, args.dry_run) else 0
        elif p.suffix == '.xml':
            xml_changes += 1 if fix_xml_file(p, args.dry_run) else 0
        elif p.name == '__manifest__.py':
            man_changes += 1 if ensure_manifest_depends_account(p, args.dry_run) else 0

    print(f"\nResumo:")
    print(f"  Arquivos .py alterados : {py_changes}")
    print(f"  Arquivos .xml alterados: {xml_changes}")
    print(f"  Manifests ajustados    : {man_changes}")
    print(f"  M
