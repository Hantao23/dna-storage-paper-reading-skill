#!/usr/bin/env bash
set -euo pipefail

if ! command -v conda >/dev/null 2>&1; then
  echo "[ERROR] conda not found in PATH."
  exit 1
fi

ENV_NAME="${1:-paper}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_REQ="${SCRIPT_DIR}/requirements-paper.txt"
OPTIONAL_REQ="${SCRIPT_DIR}/requirements-paper-optional.txt"

echo "[INFO] installing core dependencies into conda env: ${ENV_NAME}"
conda install -n "${ENV_NAME}" -y pypdf pyyaml
conda run -n "${ENV_NAME}" python -m pip install -r "${CORE_REQ}"

echo "[INFO] installing optional dependencies (tables/images)"
if ! conda run -n "${ENV_NAME}" python -m pip install -r "${OPTIONAL_REQ}"; then
  echo "[WARN] optional dependencies failed to install. Table/image extraction will be skipped."
fi

echo "[INFO] validating key imports"
conda run -n "${ENV_NAME}" python - <<'PY'
import yaml
import pypdf
print("core-deps-ok")
try:
    import pdfplumber  # noqa: F401
    print("optional-pdfplumber-ok")
except Exception:
    print("optional-pdfplumber-missing")
try:
    import fitz  # noqa: F401
    print("optional-pymupdf-ok")
except Exception:
    print("optional-pymupdf-missing")
PY

echo "[OK] environment setup complete"
