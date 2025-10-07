#!/usr/bin/env bash
set -euo pipefail

# Corrige indentação em .py (tabs->4 espaços), formata (black/autopep8 se disponíveis),
# compila para validar e imprime relatório.
# Uso:
#   bash repair_indent_and_compile.sh /docker/azul/18/mod/blue_br
#   # opcional: limitar a um submódulo:
#   bash repair_indent_and_compile.sh /docker/azul/18/mod/blue_br/l10n_br_coa

ROOT="${1:-}"
[[ -n "$ROOT" && -d "$ROOT" ]] || { echo "ERRO: informe o diretório do repo"; exit 1; }

# Detecta ferramentas opcionais
have() { command -v "$1" >/dev/null 2>&1; }

echo "[1/5] Encontrando arquivos .py ..."
mapfile -t PYFILES < <(find "$ROOT" -type f -name "*.py" | sort)
echo "    ${#PYFILES[@]} arquivos."

changed=0
failed=0
declare -a FAILS
declare -a CHANGED

echo "[2/5] Tabs -> espaços (4) + backups .bak ..."
for f in "${PYFILES[@]}"; do
  if grep -q $'\t' "$f"; then
    [[ -f "${f}.bak" ]] || cp -a "$f" "${f}.bak"
    sed -i 's/\t/    /g' "$f"
    CHANGED+=("$f")
    ((changed++)) || true
  fi
  # remove trailing spaces e normaliza fim de linha
  if grep -qE ' +$' "$f"; then
    [[ -f "${f}.bak" ]] || cp -a "$f" "${f}.bak"
    sed -i 's/[[:space:]]\+$//' "$f"
    CHANGED+=("$f")
    ((changed++)) || true
  fi
done
echo "    Arquivos alterados nessa etapa: $changed"

echo "[3/5] Formatação (se disponível: black > autopep8) ..."
fmt_changed=0
if have black; then
  black -q "${PYFILES[@]}" || true
elif have autopep8; then
  autopep8 -i -a -a "${PYFILES[@]}" || true
else
  echo "    (black/autopep8 não encontrados; pulando formatação)"
fi

echo "[4/5] Validação com py_compile ..."
for f in "${PYFILES[@]}"; do
  python3 - <<PY || { echo "    FAIL: $f"; FAILS+=("$f"); ((failed++)) || true; }
import py_compile, sys
try:
    py_compile.compile(sys.argv[1], doraise=True)
except Exception as e:
    raise
PY
  "$f"
done
echo "    Arquivos com erro: $failed"

echo "[5/5] Resumo"
if ((${#CHANGED[@]})); then
  echo "  - Alterados (inclui backups .bak criados quando necessário):"
  printf '    * %s\n' "${CHANGED[@]}" | sort -u
else
  echo "  - Nenhuma alteração de indentação básica."
fi
if ((${#FAILS[@]})); then
  echo "  - Ainda com erro (revisar manualmente):"
  printf '    * %s\n' "${FAILS[@]}"
  echo
  echo "Dica: Abra cada FAIL e confira blocos def/class com recuo fora do padrão (múltiplos de 4)."
  echo "     Caso tenha sido nossa refatoração de templates, verifique se não ficou um bloco"
  echo "     com recuo extra ao redor de 'def _get_tax_vals(...)' e similares."
else
  echo "  - Tudo OK na compilação Python."
fi

echo
echo "Próximo passo (exemplo): atualizar módulo(s) impactados no Odoo:"
echo "  docker exec -it odoo18-dev odoo -c /etc/odoo/dev18.conf -d odoo18_blue \\"
echo "    -u l10n_br_coa,l10n_br_account,l10n_br_fiscal --stop-after-init"
