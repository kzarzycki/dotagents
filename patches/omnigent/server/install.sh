#!/usr/bin/env bash
# Put the Omnigent server's deploy under root, once per server machine:
#
#   sudo ~/.dotagents/patches/omnigent/server/install.sh
#
# Afterwards the agent user may run `sudo systemctl start omnigent-deploy.service`
# and nothing else as root, and needs no docker group: omnigent-update starts the
# unit, which builds and restarts the server from root's own signed checkout and
# the root-only compose file. Idempotent: an existing /etc/omnigent/compose.yaml
# or .env is kept, since root edits them there from then on.
set -euo pipefail
user=${SUDO_USER:?run with sudo, as the agent user that runs omnigent-update}
home=$(getent passwd "$user" | cut -d: -f6)
here=$(cd "$(dirname "$0")" && pwd)
old=$home/services/omnigent
install -d -m 0755 -o root -g root /etc/omnigent /srv/omnigent
# compose.yaml and .env hold the database password and the cookie secret: root only
if [ ! -f /etc/omnigent/compose.yaml ]; then
  sed 's#context: ./source#context: /srv/omnigent/source#' "$old/compose.yaml" > /etc/omnigent/compose.yaml
  grep -q 'context: /srv/omnigent/source' /etc/omnigent/compose.yaml
fi
[ -f /etc/omnigent/.env ] || install -m 0600 "$old/.env" /etc/omnigent/.env
chown root:root /etc/omnigent/compose.yaml /etc/omnigent/.env
chmod 0600 /etc/omnigent/compose.yaml /etc/omnigent/.env
install -m 0644 -o root -g root "$here/../allowed_signers" /etc/omnigent/allowed_signers
install -m 0755 -o root -g root "$here/omnigent-deploy" /usr/local/sbin/omnigent-deploy
install -m 0644 -o root -g root "$here/omnigent-deploy.service" /etc/systemd/system/omnigent-deploy.service
sed "s/@USER@/$user/g" "$here/sudoers.in" > /etc/sudoers.d/omnigent-deploy
chmod 0440 /etc/sudoers.d/omnigent-deploy
visudo -cf /etc/sudoers.d/omnigent-deploy
systemctl daemon-reload
echo "installed; $user may now: sudo systemctl start omnigent-deploy.service"
