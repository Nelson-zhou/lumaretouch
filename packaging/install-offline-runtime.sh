#!/usr/bin/env bash
# Directory-only bootstrap. Never fetch, unpack an archive, invoke pip, or use host Python.
set -euo pipefail
export LC_ALL=C
fail() { echo "offline runtime: $*" >&2; exit 1; }
bundle= digest= prefix=${XDG_DATA_HOME:-${HOME:?}/.local/share}/LumaRetouch/engine/venv
while (($#)); do
  case "$1" in
    --offline-bundle) (($# >= 2)) || fail 'missing bundle'; bundle=$2; shift 2;;
    --manifest-sha256) (($# >= 2)) || fail 'missing trusted digest'; digest=$2; shift 2;;
    --prefix) (($# >= 2)) || fail 'missing prefix'; prefix=$2; shift 2;;
    *) fail "unsupported offline option: $1";;
  esac
done
[[ $digest =~ ^[0-9a-f]{64}$ ]] || fail 'a separately authenticated SHA256SUMS digest is required'
[[ -d $bundle && ! -L $bundle ]] || fail 'bundle must be a real directory (archives are not accepted)'
[[ $prefix = /* ]] || fail 'prefix must be absolute'
here=$(cd -- "$(dirname -- "$0")" && pwd)
# Take a private snapshot before executing anything from the supplied directory.
# cp -P does not follow links; all links and nonregular entries are rejected below.
umask 077
scratch=$(mktemp -d)
cleanup_snapshot() {
  local outcome=$?
  # Default pre-order traversal repairs each private directory before descent.
  # -P and -type d exclude input symlinks; never chmod files on rejection.
  # The scratch root is our own mktemp directory, not the supplied bundle.
  find -P "$scratch" -type d -exec chmod u+rwx -- {} \; ||
    echo "warning: snapshot directory-mode cleanup failed: $scratch" >&2
  rm -rf -- "$scratch" ||
    echo "warning: private snapshot cleanup requires attention: $scratch" >&2
  return "$outcome"
}
trap cleanup_snapshot EXIT
cp -a -- "$bundle/." "$scratch/bundle"
cd "$scratch/bundle"
[[ -f SHA256SUMS && ! -L SHA256SUMS ]] || fail 'missing checksum inventory'
[[ $(sha256sum SHA256SUMS | cut -d' ' -f1) = "$digest" ]] || fail 'trusted inventory digest mismatch'
: > "$scratch/actual"
while IFS= read -r -d '' entry; do
  name=${entry#./}
  [[ $name =~ ^[A-Za-z0-9_./+-]+$ ]] || fail 'unsupported bundle pathname'
  [[ ! -L $entry ]] || fail "symlink forbidden: $name"
  mode=$(stat -c %a -- "$entry")
  (( (8#$mode & 06022) == 0 )) || fail "unsafe writable/privileged mode: $name"
  if [[ -d $entry ]]; then continue; fi
  [[ -f $entry ]] || fail "nonregular entry: $name"
  [[ $(stat -c %h -- "$entry") = 1 ]] || fail "hardlink forbidden: $name"
  [[ $name = SHA256SUMS ]] || printf '%s\n' "$name" >> "$scratch/actual"
done < <(find . -mindepth 1 -print0)
: > "$scratch/declared"
while IFS= read -r line || [[ -n $line ]]; do
  [[ $line =~ ^[0-9a-f]{64}'  '[A-Za-z0-9_./+-]+$ ]] || fail 'invalid checksum row'
  name=${line:66}
  [[ $name != /* && $name != SHA256SUMS && /$name/ != */../* && /$name/ != */./* && $name != *//* ]] || fail 'unsafe checksum path'
  printf '%s\n' "$name" >> "$scratch/declared"
done < SHA256SUMS
sort "$scratch/actual" > "$scratch/actual.sorted"
sort "$scratch/declared" > "$scratch/declared.sorted"
cmp -s "$scratch/actual.sorted" "$scratch/declared.sorted" || fail 'inventory differs (missing, extra or duplicate files)'
sha256sum --strict --check SHA256SUMS >/dev/null || fail 'asset integrity failure'
[[ -x payload/bin/python ]] || fail 'missing executable standalone interpreter'
# All executable/stdlib bytes are now pinned by the external digest. -I -S avoids
# environment/user-site/.pth imports. This helper is shipped source, not bundle code.
unset PYTHONHOME PYTHONPATH LD_PRELOAD LD_LIBRARY_PATH
./payload/bin/python -I -S "$here/offline-runtime.py" --bundle "$PWD" --prefix "$prefix" --manifest-sha256 "$digest"
