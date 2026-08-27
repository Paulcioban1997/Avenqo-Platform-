#!/usr/bin/env bash
set -e

echo "=== Installing Flutter ==="

git clone https://github.com/flutter/flutter.git \
  --depth 1 \
  --branch stable \
  /tmp/flutter

export PATH="/tmp/flutter/bin:$PATH"

echo "=== Flutter version ==="
flutter --version

echo "=== Enable Flutter Web ==="
flutter config --enable-web

echo "=== Install dependencies ==="
flutter pub get

echo "=== Build Avenqo Web ==="
flutter build web \
  --release \
  --dart-define=API_BASE_URL=https://api.avenqo.ca/api/v1

echo "=== Avenqo Flutter build completed ==="