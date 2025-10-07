#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Normalizador de 'attrs' e 'states' em XMLs de views do Odoo (16.0 -> 18.0)

O que faz:
- Em atributos 'attrs':
  * Substitui '==' por '=' em domínios condicionais
  * Garante escape correto de '&' como '&amp;' sem duplo-escape
  * Padroniza espaços e vírgulas
- Em atributos 'states':
  * Remove espaços redundantes ao redor de vírgulas
  * Mantém ordem e conteúdo

Uso:
  python normalize_odoo_attrs.py /caminho/da/pasta [--dry-run] [--ext .xml]
"""

import argparse
import os
import re
from pathlib import Path
from typing import Tuple

# Regexes para localizar atributos XML de forma robusta (sem parse completo)
# Captura algo como: attrs=" {...} " respeitando aspas duplas externas
ATTRS_RE = re.compile(
    r'(?P<prefix>\sattrs\s*=\s*")(?P<body>[^"]*?)(?P<suffix>")',
    flags=re.DOTALL | re.UNICODE,
)

STATES_RE = re.compile(
    r'(?P<prefix>\sstates\s*=\s*")(?P<body>[^"]*?)(?P<suffix>")',
    flags=re.DOTALL | re.UNICODE,
)

# Troca '==' por '=' apenas dentro de tuplas/listas/domínios (entre colchetes/chaves)
# Mantemos '!=' e 'not in', 'in' etc.
EQ_RE = re.compile(r"\s==\s")

# Garante que '&' solto dentro de attrs vire '&amp;', sem tocar o que já é '&amp;'
# Estratégia: primeiro protege '&amp;' já existentes; depois escapa '&' remanescentes;
# por fim restaura os protegidos.
AMP_PROTECT_TOKEN = "__AMP_PROTECTED__"
RAW_AMP_RE = re.compile(r"&(?![a-zA-Z]+;|#\d+;)")
AMP_RESTORE_RE = re.compile(AMP_PROTECT_TOKEN)

# Espaços redundantes em estruturas Python-like dentro de attrs
MULTISPACE_RE = re.compile(r"[ \t]{2,}")
SPACE_AROUND_COMMA_RE = re.compile(r"\s*,\s*")
SPACE_AROUND_COLON_RE = re.compile(r"\s*:\s*")
SPACE_AROUND_OP_RE = re.compile(r"\s*([=\[\]\(\)\{\}])\s*")

def normalize_attrs_body(body: str) -> str:
    original = body

    # 1) Proteger &amp; existentes
    body = body.replace("&amp;", AMP_PROTECT_TOKEN)

    # 2) Escapar '&' cruas (não-entidades)
    body = RAW_AMP_RE.sub("&amp;", body)

    # 3) Restaurar &amp; originais
    body = AMP_RESTORE_RE.sub("&amp;", body)

    # 4) Converter '==' para '=' (sem tocar '!=')
    body = EQ_RE.sub(" = ", body)

    # 5) Normalizações leves de espaços
    #    - vírgulas: ",'x' , 'y'  , 'z' " -> "','x','y','z'"
    body = SPACE_AROUND_COMMA_RE.sub(", ", body)

    #    - chaves/colchetes/parênteses colados de forma legível
    #      Ex.: "{ 'a':[('x','=',1)] }" -> "{ 'a': [ ('x', '=', 1) ] }"
    #      Usamos uma abordagem conservadora:
    body = SPACE_AROUND_OP_RE.sub(lambda m: f"{m.group(1)}", body)
    # recolocar espaços mínimos após símbolos onde faz sentido
    body = body.replace("{", "{ ").replace("}", " }")
    body = body.replace("[", "[ ").replace("]", " ]")
    body = body.replace("(", "( ").replace(")", " )")

    #   - normalizar múltiplos espaços
    body = MULTISPACE_RE.sub(" ", body)
    #   - espaços depois de vírgula
    body = SPACE_AROUND_COMMA_RE.sub(", ", body)
    #   - normalizar ' : '
    body = SPACE_AROUND_COLON_RE.sub(": ", body)

    # 6) Pequenos toques estéticos:
    #    - remover espaço desnecessário antes de vírgulas
    body = re.sub(r"\s+,", ",", body)
    #    - manter uma vírgula seguida de espaço
    body = re.sub(r",(?=[^\s])", ", ", body)

    # 7) Enxugar espaços duplos restantes
    body = MULTISPACE_RE.sub(" ", body).strip()

    return body if body != original else original

def normalize_states_body(body: str) -> str:
    original = body
    # Quebra por vírgula, tira espaços, junta de volta com vírgula
    parts = [p.strip() for p in body.split(",") if p.strip()]
    new_body = ",".join(parts)
    return new_body if new_body != original else original

def process_xml_text(text: str) -> Tuple[str, bool]:
    """Retorna (novo_texto, houve_mudanca)"""
    changed = False

    def _attrs_sub(m: re.Match) -> str:
        nonlocal changed
        prefix, body, suffix = m.group("prefix"), m.group("body"), m.group("suffix")
        new_body = normalize_attrs_body(body)
        if new_body != body:
            changed = True
        return f"{prefix}{new_body}{suffix}"

    def _states_sub(m: re.Match) -> str:
        nonlocal changed
        prefix, body, suffix = m.group("prefix"), m.group("body"), m.group("suffix")
        new_body = normalize_states_body(body)
        if new_body != body:
            changed = True
        return f"{prefix}{new_body}{suffix}"

    text = ATTRS_RE.sub(_attrs_sub, text)
    text = STATES_RE.sub(_states_sub, text)
    return text, changed

def process_file(path: Path, dry_run: bool = False) -> bool:
    try:
        data = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # tenta latin-1 como fallback
        data = path.read_text(encoding="latin-1")

    new_data, changed = process_xml_text(data)

    if changed:
        if dry_run:
            print(f"[DRY-RUN] Mudaria: {path}")
        else:
            backup = path.with_suffix(path.suffix + ".bak")
            if not backup.exists():
                backup.write_text(data, encoding="utf-8")
            path.write_text(new_data, encoding="utf-8")
            print(f"[OK] Normalizado: {path} (backup em {backup.name})")
    return changed

def main():
    ap = argparse.ArgumentParser(description="Normalizador de attrs/states para Odoo 16->18")
    ap.add_argument("root", help="Diretório raiz para varrer (ex.: /docker/azul/18/mod/blue_br)")
    ap.add_argument("--ext", default=".xml", help="Extensão de arquivo (default: .xml)")
    ap.add_argument("--dry-run", action="store_true", help="Apenas mostra o que mudaria, não grava")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        raise SystemExit(f"Diretório não encontrado: {root}")

    total = 0
    changed = 0
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.lower().endswith(args.ext.lower()):
                total += 1
                p = Path(dirpath) / fn
                if process_file(p, dry_run=args.dry_run):
                    changed += 1

    print(f"\nArquivos varridos: {total} | Arquivos alterados: {changed} | Modo: {'DRY-RUN' if args.dry_run else 'WRITE'}")

if __name__ == "__main__":
    main()
