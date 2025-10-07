#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()

REC_OPEN_RE = re.compile(r'<record\b[^>]*\bmodel\s*=\s*["\']account\.chart\.template["\'][^>]*>', re.I)
REC_CLOSE_RE = re.compile(r'</record\s*>', re.I)

def comment_out_records(path: Path) -> bool:
    """Comenta blocos <record ... model="account.chart.template"> ... </record>."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="latin-1")
    pos = 0
    changed = False
    out = []
    while True:
        m = REC_OPEN_RE.search(text, pos)
        if not m:
            out.append(text[pos:])
            break
        # copy segment before
        out.append(text[pos:m.start()])
        # find matching close
        mclose = REC_CLOSE_RE.search(text, m.end())
        if not mclose:
            # sem fechamento: apenas comenta a partir do <record ...>
            block = text[m.start():]
            out.append(f"<!-- AUTO-DISABLED (v18): {block} -->")
            changed = True
            break
        block = text[m.start():mclose.end()]
        out.append(f"<!-- AUTO-DISABLED (v18):\n{block}\n-->")
        changed = True
        pos = mclose.end()
    if changed:
        bak = path.with_suffix(path.suffix + ".bak")
        if not bak.exists():
            bak.write_text(text, encoding="utf-8")
        Path(path).write_text("".join(out), encoding="utf-8")
        print(f"[XML DISABLED] {path} (backup: {bak.name})")
    return changed

def strip_from_manifest(path: Path, removed_files) -> bool:
    """Remove entradas de arquivos 'removed_files' da lista 'data' do __manifest__.py."""
    try:
        src = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        src = path.read_text(encoding="latin-1")

    changed = False
    new = src
    for f in removed_files:
        # remove com vírgula opcional e espaços
        pattern = re.escape(f)
        new2 = re.sub(rf"[ \t]*['\"]{pattern}['\"],[ \t]*\n", "", new)
        if new2 != new:
            changed = True
            new = new2
        new2 = re.sub(rf"[ \t]*['\"]{pattern}['\"][ \t]*,?", "", new)  # fallback
        if new2 != new:
            changed = True
            new = new2

    if changed:
        bak = path.with_suffix(".py.bak")
        if not bak.exists():
            bak.write_text(src, encoding="utf-8")
        path.write_text(new, encoding="utf-8")
        print(f"[MANIFEST FIX] {path} (backup: {bak.name})")
    return changed

def main():
    if not ROOT.exists():
        print(f"Diretório não encontrado: {ROOT}", file=sys.stderr)
        sys.exit(1)

    # 1) localizar XML com account.chart.template
    xml_hits = []
    for p in ROOT.rglob("*.xml"):
        # limite a /data/ para focar em arquivos de dados
        if "/data/" not in str(p):
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if 'model="account.chart.template"' in txt or "model='account.chart.template'" in txt:
            xml_hits.append(p)

    if not xml_hits:
        print("Nenhum <record model=\"account.chart.template\"> encontrado.")
        return

    # 2) comentar blocos <record>
    disabled = []
    for x in xml_hits:
        if comment_out_records(x):
            disabled.append(x)

    # 3) remover do __manifest__.py os arquivos que foram desativados (para nem tentar carregar)
    #    (opcional mas recomendado)
    by_module = {}
    for x in disabled:
        # encontrar __manifest__.py do módulo
        mod_dir = x
        while mod_dir != ROOT and not (mod_dir / "__manifest__.py").exists():
            mod_dir = mod_dir.parent
        man = mod_dir / "__manifest__.py"
        if man.exists():
            rel = x.relative_to(mod_dir).as_posix()
            by_module.setdefault(man, []).append(rel)

    for man, files in by_module.items():
        strip_from_manifest(man, files)

    print("\nResumo:")
    print(f"- XML com <record account.chart.template>: {len(xml_hits)}")
    print(f"- Desativados agora: {len(disabled)}")
    if disabled:
        for x in disabled:
            print(f"  * {x}")

if __name__ == "__main__":
    main()
