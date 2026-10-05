#!/usr/bin/env bash
# forge setup for a new machine (Linux or macOS). Safe to re-run.
#
#   bash scripts/setup.sh                      # check and install what forge needs
#   bash scripts/setup.sh --pool "/path/to/vault"   # also register the paper pool
#   bash scripts/setup.sh --test               # also convert one real paper end to end
#
# Installs only into ~/.local/share/forge (the Marker environment). Never uses sudo:
# anything that needs root is printed as a command for you to run.
set -u
FORGE="$(cd "$(dirname "$0")/.." && pwd)"
FORGE_HOME="${FORGE_HOME:-$HOME/.local/share/forge}"
VENV="$FORGE_HOME/marker-venv"
POOL=""
TEST=0
while [ $# -gt 0 ]; do
  case "$1" in
    --pool) POOL="$2"; shift 2 ;;
    --test) TEST=1; shift ;;
    *) echo "unknown option: $1"; exit 2 ;;
  esac
done

ok()   { printf '  \033[32mok\033[0m    %s\n' "$*"; }
warn() { printf '  \033[33mtodo\033[0m  %s\n' "$*"; TODO=$((TODO+1)); }
TODO=0

echo "forge setup  (forge at $FORGE)"
echo
echo "1. Basics"
if command -v python3 >/dev/null && python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
  ok "python3 $(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
else
  warn "Python 3.10+ is needed (Ubuntu: sudo apt install python3 python3-venv)"
fi
python3 -c 'import venv' 2>/dev/null && python3 -m venv --help >/dev/null 2>&1 && ok "python3 venv" || warn "python3-venv is missing (Ubuntu: sudo apt install python3-venv)"
command -v curl >/dev/null && ok "curl" || warn "curl is missing (Ubuntu: sudo apt install curl)"
command -v git >/dev/null && ok "git" || warn "git is missing (Ubuntu: sudo apt install git)"
if command -v claude >/dev/null; then
  ok "Claude Code $(claude --version 2>/dev/null | head -1)"
else
  warn "Claude Code is not installed: https://code.claude.com/docs/en/setup"
fi
chmod +x "$FORGE"/bin/* "$FORGE"/hooks/*.py 2>/dev/null

echo
echo "2. Marker (free, local PDF -> Markdown)"
if [ ! -x "$VENV/bin/marker_server" ]; then
  echo "  installing Marker into $VENV (a few minutes) ..."
  mkdir -p "$FORGE_HOME"
  python3 -m venv "$VENV" && "$VENV/bin/pip" install -q --upgrade pip \
    && "$VENV/bin/pip" install -q "marker-pdf==2.0.0" fastapi uvicorn python-multipart \
    || { warn "Marker installation failed (see the pip output above)"; }
fi
[ -x "$VENV/bin/marker_server" ] && ok "Marker installed ($VENV)"

echo
echo "3. Where Marker's model runs"
GPU=0
if command -v nvidia-smi >/dev/null && nvidia-smi -L >/dev/null 2>&1; then
  GPU=1
  ok "NVIDIA GPU: $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | head -1)"
fi
if [ "$GPU" = 1 ]; then
  if command -v docker >/dev/null && docker info 2>/dev/null | grep -qi 'nvidia'; then
    ok "Docker with the NVIDIA runtime: Marker will run its model on the GPU (vLLM container)"
    echo "        the first conversion downloads the vLLM image and the model (several GB); later ones are fast"
  elif command -v docker >/dev/null; then
    warn "Docker is installed but has no NVIDIA runtime. Install the NVIDIA Container Toolkit:"
    echo "        https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html"
    echo "        then: sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker"
    echo "        (also make sure your user can run docker: sudo usermod -aG docker \$USER, then log in again)"
    echo "        Or use llama.cpp with CUDA instead: export SURYA_INFERENCE_BACKEND=llamacpp in your shell profile"
  else
    warn "Docker is not installed. For GPU conversion install Docker and the NVIDIA Container Toolkit:"
    echo "        https://docs.docker.com/engine/install/ubuntu/"
    echo "        https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html"
    echo "        Or, without Docker: build llama.cpp with CUDA and add to your shell profile:"
    echo "          export SURYA_INFERENCE_BACKEND=llamacpp"
    echo "        (with an NVIDIA GPU, Marker otherwise always tries the Docker/vLLM route and fails without Docker)"
  fi
fi
if command -v llama-server >/dev/null; then
  ok "llama.cpp (llama-server) found: used when the GPU container is not available"
elif [ "$GPU" = 0 ]; then
  if [ "$(uname)" = Darwin ]; then
    warn "llama.cpp is missing: brew install llama.cpp"
  else
    warn "llama.cpp is missing: build it (https://github.com/ggml-org/llama.cpp) and put llama-server on PATH"
  fi
fi

echo
echo "4. Paper pool"
if [ -n "$POOL" ]; then
  "$FORGE/bin/refs" pool add "$POOL" && ok "pool registered"
else
  "$FORGE/bin/refs" pool list 2>/dev/null | head -1 | grep -q 'no pool' \
    && warn "no paper pool registered: bash scripts/setup.sh --pool \"/path/to/your/vault\"" \
    || ok "$("$FORGE/bin/refs" pool list | head -1)"
fi

if [ "$TEST" = 1 ]; then
  echo
  echo "5. End-to-end test: fetch and convert one paper (outside Claude, no time limit)"
  T="$(mktemp -d)/forge-setup-test"
  "$FORGE/bin/forge-init" "$T" >/dev/null
  ( cd "$T" && "$FORGE/bin/refs" fetch 1412.6980 && "$FORGE/bin/refs" convert --budget 3600 && "$FORGE/bin/refs" status ) \
    && ok "converted: $(ls "$T/references" | grep -v -e inbox -e '\.md$' -e '\.bib$' -e '\.log$' | head -3 | tr '\n' ' ') (in $T)" \
    || warn "the test conversion failed; see the output above and $FORGE_HOME/marker-server.log"
fi

echo
echo "In Claude Code (once per machine): /config -> turn on 'Dynamic workflows'."
echo "Use forge in a project:  claude --plugin-dir \"$FORGE\"   then /forge:init and /forge:status"
echo
[ "$TODO" = 0 ] && echo "All set." || echo "$TODO item(s) marked 'todo' above."
