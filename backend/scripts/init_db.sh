#!/usr/bin/env bash
# ============================================================
# init_db.sh — 应用 schema.sql 到本地数据库
#
# ⚠️ 警告：会清空 schema 'public' 下所有数据！
#    仅用于 dev 环境的初始化与重置。
#
# 用法:
#   ./backend/scripts/init_db.sh
#
# 环境变量:
#   DATABASE_URL  连接串（默认从 backend/.env 读取，否则用 dev 默认值）
# ============================================================
set -euo pipefail

# 解析 backend 目录（脚本在 backend/scripts/ 下）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$BACKEND_DIR")"
SCHEMA_FILE="$REPO_ROOT/docs/data_model/schema.sql"

# 加载 .env 中的 DATABASE_URL（如存在）
if [ -f "$BACKEND_DIR/.env" ]; then
    # shellcheck disable=SC1091
    set -a; source "$BACKEND_DIR/.env"; set +a
fi

# 默认值（与 .env.example 一致）
DATABASE_URL="${DATABASE_URL:-postgresql://sz:sz_dev_password@localhost:5432/sz_dev}"

# psycopg 风格的 URL 转 psql 风格（去掉 +psycopg 后缀）
PSQL_URL="${DATABASE_URL/+psycopg/}"

echo "→ Schema: $SCHEMA_FILE"
echo "→ Target: $PSQL_URL"
echo

# 重置 public schema（最干净的清库方式）
psql "$PSQL_URL" -v ON_ERROR_STOP=1 -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" >/dev/null
echo "✓ Dropped & recreated public schema"

# 应用 schema
psql "$PSQL_URL" -v ON_ERROR_STOP=1 -f "$SCHEMA_FILE" >/dev/null
echo "✓ Applied schema.sql"

# 验证表数和视图数
TABLE_COUNT=$(psql "$PSQL_URL" -tAc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';")
VIEW_COUNT=$(psql "$PSQL_URL" -tAc \
    "SELECT count(*) FROM information_schema.views WHERE table_schema='public';")

echo
echo "Tables: $TABLE_COUNT  (expected 11)"
echo "Views:  $VIEW_COUNT  (expected 1)"

if [ "$TABLE_COUNT" != "11" ] || [ "$VIEW_COUNT" != "1" ]; then
    echo "✗ Verification failed"
    exit 1
fi
echo
echo "✅ Database initialized successfully"
