#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  printf '用法：%s <生产 env 文件> <备份目录绝对路径>\n' "$0" >&2
  exit 1
fi

env_file=$1
backup_dir=$2
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
compose_file="$script_dir/../compose.production.yaml"

if [[ ! -f "$env_file" ]]; then
  printf '生产 env 文件不存在：%s\n' "$env_file" >&2
  exit 1
fi
if [[ "$backup_dir" != /* ]]; then
  printf '备份目录必须使用绝对路径。\n' >&2
  exit 1
fi

umask 077
if [[ ! -d "$backup_dir" ]]; then
  mkdir -p -- "$backup_dir"
fi
# 只接受当前用户独占的目录，不修改已有目录权限。
if [[ ! -O "$backup_dir" || ! -w "$backup_dir" || ! -x "$backup_dir" ]]; then
  printf '备份目录必须由当前用户拥有，且可写入和访问：%s\n' "$backup_dir" >&2
  exit 1
fi
directory_mode=$(stat -c '%a' -- "$backup_dir")
if [[ "$directory_mode" != 700 ]]; then
  printf '备份目录权限必须为 700：%s\n' "$backup_dir" >&2
  exit 1
fi

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
partial_file=$(mktemp "$backup_dir/metalmax-wiki_${timestamp}_XXXXXX.dump.partial")
backup_file=${partial_file%.partial}

if ! docker compose --env-file "$env_file" -f "$compose_file" exec -T db \
  sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" exec pg_dump --host=127.0.0.1 --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --format=custom --no-owner --no-acl' \
  > "$partial_file"; then
  printf '数据库备份失败，未完成文件保留于：%s\n' "$partial_file" >&2
  exit 1
fi

if [[ -e "$backup_file" ]]; then
  printf '目标已存在，保留未完成文件且不覆盖：%s\n' "$partial_file" >&2
  exit 1
fi
mv -- "$partial_file" "$backup_file"
printf '数据库备份已写入：%s\n' "$backup_file"
