#!/bin/sh
# Sauvegarde cohérente des cinq volumes Hpa Rating sur une VM Linux dédiée.
set -eu
umask 077
[ "$(id -u)" -eq 0 ] || { echo "Exécuter avec sudo sur la VM." >&2; exit 1; }
deploy_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
compose() { docker compose -p hpa-rating -f "$deploy_dir/compose.yaml" "$@"; }
volumes="guest_state admin_state invitations tls caddy_config"
root=/var/backups/hpa-rating
install -d -m 0700 "$root"
exec 9>"$root/.lock"
flock -n 9 || { echo "Une sauvegarde est déjà en cours." >&2; exit 1; }
mountpoint_for() { docker volume inspect --format '{{ .Mountpoint }}' "hpa-rating_$1"; }
for volume in $volumes; do
    test -d "$(mountpoint_for "$volume")"
done
running=$(compose ps --status running --services)
stamp=$(date -u +%Y%m%dT%H%M%SZ)
partial=$(mktemp -d "$root/.encours-$stamp-XXXXXXXX")
resume() {
    # Compose n'a ici que trois noms de services fixes, sans espaces.
    if [ -n "$running" ]; then compose start $running; fi
}
trap 'result=$?; trap - EXIT; resume || result=1; exit "$result"' EXIT
trap 'exit 1' HUP INT TERM
if [ -n "$running" ]; then compose stop $running; fi
for volume in $volumes; do
    tar --numeric-owner -C "$(mountpoint_for "$volume")" -czf "$partial/$volume.tar.gz" .
    gzip -t "$partial/$volume.tar.gz"
done
(cd "$partial" && sha256sum ./*.tar.gz > SHA256SUMS)
test ! -e "$root/$stamp"
mv -T "$partial" "$root/$stamp"
echo "Sauvegarde privée : $root/$stamp"
