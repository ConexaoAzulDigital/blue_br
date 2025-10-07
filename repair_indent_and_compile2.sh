#!/usr/bin/env bash
set -euo pipefail

# Corrige indentação básica (tabs->4 spaces), formata (se "black" ou "autopep8" existirem),
# compila cada .py com py_compile e mostra um relatório.
# Uso:
#   bash repair_indent_and_compile.sh /docker/azul/18/mod/blue_br
#   # opcional: restringir a um submódulo:
#   bash repair_indent_and_compile.sh /docker/azul/18/mod/blue_br/l10n_br_coa

ROOT="${1:-}"
[[ -n "$ROOT" && -d "$ROOT" ]] || { echo "ERRO: informe o diretório do repo"; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

echo "[1/5] Encontrando arquivos .py ..."
# Exclui diretórios comuns que não queremos varrer
mapfile -t PYFILES < <(find "$ROOT" -type f -name "*.py" \
  -not -path "*/.git/*" \
  -not -path "*/__pycache__/*" \
  -not -path "*/.venv/*" -not -path "*/venv/*" -not -path "*/env/*" \
  -not -path "*/tests/*" \
  | sort)
echo "    ${#PYFILES[@]} arquivos."

changed=0
failed=0
declare -a FAILS
declare -a CHANGED

echo "[2/5] Tabs -> espaços (4) + backups .bak ..."
for f in "${PYFILES[@]}"; do
  # tabs -> 4 spaces
  if grep -q $'\t' "$f"; then
    [[ -f "${f}.bak" ]] || cp -a "$f" "${f}.bak"
    sed -i 's/\t/    /g' "$f"
    CHANGED+=("$f")
    ((changed++)) || true
  fi
  # trailing spaces
  if grep -qE ' +$' "$f"; then
    [[ -f "${f}.bak" ]] || cp -a "$f" "${f}.bak"
    sed -i 's/[[:space:]]\+$//' "$f"
    CHANGED+=("$f")
    ((changed++)) || true
  fi
done
echo "    Arquivos alterados nessa etapa: $changed"

echo "[3/5] Formatação (se disponível: black > autopep8) ..."
if have black; then
  black -q "${PYFILES[@]}" || true
elif have autopep8; then
  autopep8 -i -a -a "${PYFILES[@]}" || true
else
  echo "    (black/autopep8 não encontrados; pulando formatação)"
fi

echo "[4/5] Validação com py_compile ..."
for f in "${PYFILES[@]}"; do
  # Passa o caminho do arquivo como argumento POSICIONAL ao python via heredoc
  if ! python3 - "$f" <<'PY'
import py_compile, sys
fname = sys.argv[1]
py_compile.compile(fname, doraise=True)
PY
  then
    echo "    FAIL: $f"
    FAILS+=("$f")
    ((failed++)) || true
  fi
done
echo "    Arquivos com erro: $failed"

echo "[5/5] Resumo"
if ((${#CHANGED[@]})); then
  echo "  - Alterados (backups .bak criados quando necessário):"
  printf '    * %s\n' "${CHANGED[@]}" | sort -u
else
  echo "  - Nenhuma alteração de indentação/trailing space."
fi

if ((${#FAILS[@]})); then
  echo "  - Ainda com erro (revisar manualmente):"
  printf '    * %s\n' "${FAILS[@]}"
  echo
  echo "Dica: verifique blocos 'class ...:' seguidos de linhas sem recuo,"
  echo "      e métodos/atributos com recuo não múltiplo de 4."
else
  echo "  - Tudo OK na compilação Python."
fi

echo
echo "Próximo passo (exemplo): atualizar módulos no Odoo:"
echo "  docker exec -it odoo18-dev odoo -c /etc/odoo/dev18.conf -d odoo18_blue \\"
echo "    -u l10n_br_account,l10n_br_coa,l10n_br_fiscal --stop-after-init"
