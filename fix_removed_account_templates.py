#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Detecta e (opcionalmente) corrige referências a modelos *template* removidos/refatorados
em Odoo 17/18 nos seus módulos.

Uso:
  python fix_removed_account_templates.py /docker/azul/18/mod/blue_br
  python fix_removed_account_templates.py /docker/azul/18/mod/blue_br --apply
"""

import argparse
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

# Mapeamento padrão (ajuste se necessário ao seu caso)
MODEL_MAP: Dict[str, str] = {
    # Templates contábeis clássicos -> modelos efetivos
    "account.tax.template": "account.tax",
    "account.tax.repartition.line.template": "account.tax.repartition.line",
    "account.account.template": "account.account",
    "account.group.template": "account.group",
    "account.fiscal.position.template": "account.fiscal.position",
    # Mantemos chart como abstrato, não substituímos _inherit por modelo efetivo
    # (já tratamos isso com o fix anterior para AbstractModel).
    # "account.chart.template": "account.chart.template",
}

XML_MODEL_RE = re.compile(r'(<record\s+[^>]*\bmodel\s*=\s*")[^"]+(")', re.IGNORECASE)
PY_INHERIT_LINE_RE = re.compile(r'^[ \t]*_inherit[ \t]*=\s*(?P<val>.+)$', re.MULTILINE)
PY_CLASS_HEADER_MODEL_RE = re.compile(
    r'^(?P<indent>[ \t]*)class[ \t]+(?P<cls>\w+)\s*\(\s*models\.Model\s*\)\s*:',
    re.MULTILINE
)
PY_CLASS_HEADER_ABSTRACT_RE = re.compile(
    r'^(?P<indent>[ \t]*)class[ \t]+(?P<cls>\w+)\s*\(\s*models\.AbstractModel\s*\)\s*:',
    re.MULTILINE
)

def normalize_list_literal(s: str) -> List[str]:
    vals = []
    for tok in re.findall(r"[\"']([^\"']+)[\"']", s):
        vals.append(tok.strip())
    return vals

def replace_inherit_values(orig: str) -> Tuple[str, bool, List[str]]:
    """
    Substitui valores de _inherit contendo templates removidos pelo alvo do MODEL_MAP.
    Se encontrar 'account.chart.template', apenas marca para revisão (não troca aqui).
    Retorna: (novo_texto, houve_mudanca, reviews)
    """
    changed = False
    reviews = []
    def repl(m):
        nonlocal changed, reviews
        raw = m.group('val').strip()
        vals = []
        # Suporta 'str', ["a","b"], ('a','b')
        if raw.startswith(('"', "'")):
            vals = [raw.strip().strip('"\'')]
        else:
            vals = normalize_list_literal(raw)

        new_vals = []
        for v in vals:
            if v in MODEL_MAP:
                target = MODEL_MAP[v]
                if v == "account.chart.template":
                    reviews.append(f"_inherit inclui '{v}' (abstrato). Verifique se a classe é AbstractModel.")
                    new_vals.append(v)  # não troca aqui
                else:
                    new_vals.append(target)
                    changed = True
                continue
            new_vals.append(v)

        # remonta linha
        if len(new_vals) == 1:
            return f"_inherit = '{new_vals[0]}'"
        else:
            inner = ", ".join(f"'{x}'" for x in new_vals)
            return f"_inherit = [{inner}]"

    new = PY_INHERIT_LINE_RE.sub(repl, orig)
    return new, changed, reviews

def maybe_swap_class_to_abstract(text: str, has_chart_inherit: bool) -> Tuple[str, bool]:
    """
    Se a classe herda de models.Model mas _inherit contém account.chart.template,
    sugerimos/realizamos a troca para AbstractModel (quando claro).
    Aqui fazemos a troca direta, pois é a correção canônica.
    """
    if not has_chart_inherit:
        return text, False
    if PY_CLASS_HEADER_ABSTRACT_RE.search(text):
        return text, False  # já é abstract
    if not PY_CLASS_HEADER_MODEL_RE.search(text):
        return text, False  # não achou cabeçalho "Model"
    new = PY_CLASS_HEADER_MODEL_RE.sub(
        lambda m: f"{m.group('indent')}class {m.group('cls')}(models.AbstractModel):",
        text
    )
    return new, new != text

def process_python(path: Path, apply: bool) -> Tuple[bool, List[str]]:
    try:
        src = path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        src = path.read_text(encoding='latin-1')

    # Detecta se há _inherit e possíveis trocas
    new_src, changed_inherit, reviews = replace_inherit_values(src)

    # Se houver referência a chart template no inherit, garantir AbstractModel
    has_chart = "account.chart.template" in new_src
    new_src2, changed_class = maybe_swap_class_to_abstract(new_src, has_chart)

    changed = changed_inherit or changed_class
    if changed and apply:
        bak = path.with_suffix(path.suffix + ".bak")
        if not bak.exists():
            bak.write_text(src, encoding='utf-8')
        path.write_text(new_src2, encoding='utf-8')
        print(f"[PY FIX] {path}  (backup: {bak.name})")
    elif changed:
        print(f"[PY DRY] {path} (mudaria)")

    # Sinaliza revisão extra (e.g., remoção de _name em Abstracts)
    if has_chart:
        # garantir que não exista _name = 'account.chart.template'
        if re.search(r"^[ \t]*_name[ \t]*=\s*['\"]account\.chart\.template['\"]", new_src2, re.MULTILINE):
            reviews.append(f"{path}: remover/commentar _name='account.chart.template' em classe AbstractModel.")

    return changed, reviews

def process_xml(path: Path, apply: bool) -> Tuple[bool, List[str]]:
    try:
        src = path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        src = path.read_text(encoding='latin-1')

    reviews = []
    changed = False
    def repl(m):
        nonlocal changed, reviews
        full = m.group(0)
        before, modelname, after = m.group(1), full[len(m.group(1)):-len(m.group(2))], m.group(2)
        # modelname contém o valor atual entre aspas já capturado por full; precisamos re-extrair
        model_match = re.search(r'\bmodel\s*=\s*"([^"]+)"', full, re.IGNORECASE)
        if not model_match:
            return full
        name = model_match.group(1).strip()
        if name in MODEL_MAP:
            target = MODEL_MAP[name]
            if name == "account.chart.template":
                # Não trocar automaticamente em XML (geralmente wizard/chart)
                reviews.append(f"{path}: <record model=\"{name}\"> — revisar manualmente (chart template).")
                return full
            # troca direta
            changed_xml = full.replace(f'model="{name}"', f'model="{target}"')
            changed = True
            return changed_xml
        return full

    new_src = XML_MODEL_RE.sub(repl, src)

    if changed and apply:
        bak = path.with_suffix(path.suffix + ".bak")
        if not bak.exists():
            bak.write_text(src, encoding='utf-8')
        path.write_text(new_src, encoding='utf-8')
        print(f"[XML FIX] {path}  (backup: {bak.name})")
    elif changed:
        print(f"[XML DRY] {path} (mudaria)")

    return changed, reviews

def main():
    ap = argparse.ArgumentParser(description="Fix refs a modelos template removidos (Odoo 17/18)")
    ap.add_argument("root", help="Diretório raiz (ex.: /docker/azul/18/mod/blue_br)")
    ap.add_argument("--apply", action="store_true", help="Aplicar correções (sem isso, só relata)")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        raise SystemExit(f"Diretório não encontrado: {root}")

    py_changed = xml_changed = 0
    reviews_all: List[str] = []

    for dp, _, files in os.walk(root):
        for fn in files:
            p = Path(dp) / fn
            if fn.endswith(".py"):
                chg, revs = process_python(p, apply=args.apply)
                py_changed += int(chg)
                reviews_all.extend(revs)
            elif fn.endswith(".xml"):
                chg, revs = process_xml(p, apply=args.apply)
                xml_changed += int(chg)
                reviews_all.extend(revs)

    print("\nResumo:")
    print(f"- Arquivos .py alterados: {py_changed}")
    print(f"- Arquivos .xml alterados: {xml_changed}")
    if reviews_all:
        print("- Itens para REVISÃO MANUAL:")
        for r in sorted(set(reviews_all)):
            print(f"  * {r}")

if __name__ == "__main__":
    main()
