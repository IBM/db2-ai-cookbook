#!/bin/bash

set -e

# Step -1: Deactivate any active virtual environment if one exists
if [[ "$VIRTUAL_ENV" != "" ]]; then
    echo "Deactivating currently active Python virtual environment"
    deactivate || true
fi

echo "Step 0: Ensure ~/.local/bin is in PATH"
export PATH="$HOME/.local/bin:$PATH"

echo "Step 1: Install essential system packages"
sudo dnf install -y \
    python3.12 \
    python3.12-devel \
    python3.12-pip \
    gcc-c++ \
    make \
    cmake \
    libcurl-devel \
    wget

echo "Step 2: Enable CodeReady Builder repo (optional)"
sudo subscription-manager repos --enable codeready-builder-for-rhel-9-$(arch)-rpms || true

echo "Step 3: Install uv (Python package manager)"
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
else
    echo "uv is already installed."
fi

echo "Step 4: Ensure uv is in PATH"
export PATH="$HOME/.local/bin:$PATH"

echo "Step 5: Remove existing virtual environment (if any)"
rm -rf .venv

echo "Step 6: Create Python 3.12 virtual environment using uv"
uv venv --python $(which python3.12)

echo "Step 7: Activate virtual environment"
source .venv/bin/activate

python -m ensurepip --upgrade
python -m pip install --upgrade pip setuptools wheel

echo "Step 8: Build and install llama-cpp-python from source"
export LLAMA_CPP_CMAKE_ARGS="-DLLAMA_NATIVE=ON"
uv pip install llama-cpp-python --no-binary :all:

echo "Step 9: Install huggingface-hub"
uv pip install huggingface-hub

echo "Step 10: Install Python dependencies from requirements.txt"
if [ -f requirements.txt ]; then
    uv pip install -r requirements.txt
else
    echo "requirements.txt not found — skipping."
fi

echo "Step 11: Download SpaCy English model"
python -m spacy download en_core_web_sm

echo "Step 12: Download GGUF embedding model"
rm -rf models
mkdir -p models
cd models
wget -O granite-embedding-30m-english-Q6_K.gguf \
  https://huggingface.co/lmstudio-community/granite-embedding-30m-english-GGUF/resolve/main/granite-embedding-30m-english-Q6_K.gguf
cd ..

echo ""
echo "Setup complete."
echo ""
echo "To activate the environment later, run:"
echo "    source .venv/bin/activate"
echo ""