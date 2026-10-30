#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

NAS="${NAS:-nas}"
WORKDIR="/volume1/docker/nekro-agent/plugins/workdir"
DATA_DIR="/volume1/docker/nekro-agent/plugin_data/afx.humanoid_chat"
WITH_CONFIG=0
RELOAD=0
PROFILES_DIR=""

usage() {
  cat <<'EOF'
Usage: ./scripts/deploy.sh [options]

  --with-config       同时部署 config.yaml 到 plugin_data
  --profiles <dir>    部署 <dir>/*.yaml 到 group_profiles
  --reload            部署后通过 Nekro API 热重载 humanoid_chat
  -h, --help          显示帮助

环境变量:
  NAS                  SSH 别名，默认 nas
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-config) WITH_CONFIG=1; shift ;;
    --profiles)
      [[ $# -ge 2 ]] || { echo "缺少 --profiles 目录" >&2; exit 1; }
      PROFILES_DIR="$2"; shift 2 ;;
    --reload) RELOAD=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数: $1" >&2; usage >&2; exit 1 ;;
  esac
done

./scripts/check.sh

ssh "$NAS" "mkdir -p '$WORKDIR' '$DATA_DIR'"
scp -q humanoid_chat.py "$NAS:$WORKDIR/humanoid_chat.py"
echo "deployed: $WORKDIR/humanoid_chat.py"

if [[ "$WITH_CONFIG" -eq 1 ]]; then
  scp -q config.yaml "$NAS:$DATA_DIR/config.yaml"
  echo "deployed: $DATA_DIR/config.yaml"
fi

if [[ -n "$PROFILES_DIR" ]]; then
  [[ -d "$PROFILES_DIR" ]] || { echo "目录不存在: $PROFILES_DIR" >&2; exit 1; }
  ssh "$NAS" "mkdir -p '$DATA_DIR/group_profiles'"
  scp -q "$PROFILES_DIR"/*.yaml "$NAS:$DATA_DIR/group_profiles/"
  echo "deployed profiles: $PROFILES_DIR/*.yaml"
fi

if [[ "$RELOAD" -eq 1 ]]; then
  ssh "$NAS" '
    PW=$(docker exec nekro_agent printenv NEKRO_ADMIN_PASSWORD)
    TOKEN=$(curl -s -m 10 -X POST "http://127.0.0.1:8021/api/user/login" \
      -H "Content-Type: application/json" \
      -d "{\"username\":\"admin\",\"password\":\"$PW\"}" \
      | python3 -c "import sys,json; print(json.load(sys.stdin).get(\"access_token\",\"\"))")
    if [ -z "$TOKEN" ]; then
      echo "reload failed: admin login failed" >&2
      exit 1
    fi
    curl -s -m 30 -X POST "http://127.0.0.1:8021/api/plugins/reload?module_name=humanoid_chat" \
      -H "Authorization: Bearer $TOKEN"
  '
  echo
  echo "reload requested"
fi
