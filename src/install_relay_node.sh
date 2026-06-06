#!/bin/bash
# install_relay_node.sh — District Relay Node Setup
# Fixed: consistent CITYHAL_IP variable name throughout.
# Run as: sudo bash install_relay_node.sh

set -e

echo "========================================"
echo " Bioko Intranet — District Relay Node"
echo "========================================"
echo ""

read -p "Node name (luba / riaba / moka / punta_europa): " NODE_NAME
read -p "City Hall server IP on backbone (e.g. 10.10.0.1): " CITYHAL_IP
read -p "WiFi password for BIOKO_BUS network: " WIFI_PASS
read -p "This node's backbone IP (e.g. 10.10.1.1): " NODE_BACKBONE_IP
read -p "Bus WiFi subnet base (e.g. 10.10.1): " BUS_SUBNET

# Validate that CITYHAL_IP was entered
if [ -z "$CITYHAL_IP" ]; then
    echo "ERROR: City Hall IP cannot be empty."
    exit 1
fi
if [ -z "$NODE_NAME" ]; then
    echo "ERROR: Node name cannot be empty."
    exit 1
fi

APP_DIR="/opt/bioko_relay"

echo ""
echo "Configuration:"
echo "  Node:        $NODE_NAME"
echo "  City Hall:   $CITYHAL_IP"
echo "  Backbone IP: $NODE_BACKBONE_IP"
echo "  Bus subnet:  ${BUS_SUBNET}.0/24"
echo ""

# ── System packages ───────────────────────────────────────────────────────────
apt-get update -y
apt-get install -y \
    hostapd dnsmasq \
    python3 python3-pip python3-venv \
    iptables iptables-persistent \
    sqlite3

# ── Static IP for wlan0 (bus-facing AP) ──────────────────────────────────────
mkdir -p /etc/dhcpcd.conf.d
cat > /etc/dhcpcd.conf.d/bioko_relay.conf << DHCP
interface wlan0
    static ip_address=${BUS_SUBNET}.1/24
    nohook wpa_supplicant
DHCP

# ── hostapd — WiFi Access Point ───────────────────────────────────────────────
cat > /etc/hostapd/hostapd.conf << HOSTAPD
interface=wlan0
driver=nl80211
ssid=BIOKO_BUS
hw_mode=g
channel=6
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=1
wpa=2
wpa_passphrase=${WIFI_PASS}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
beacon_int=200
HOSTAPD

sed -i 's|#DAEMON_CONF=""|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd
systemctl unmask hostapd
systemctl enable hostapd

# ── dnsmasq — DHCP + hostname resolution ──────────────────────────────────────
mv /etc/dnsmasq.conf /etc/dnsmasq.conf.bak 2>/dev/null || true
cat > /etc/dnsmasq.conf << DNSMASQ
interface=wlan0
dhcp-range=${BUS_SUBNET}.10,${BUS_SUBNET}.250,255.255.255.0,12h
dhcp-option=3,${BUS_SUBNET}.1
dhcp-option=6,${CITYHAL_IP}
address=/bioko-server/${CITYHAL_IP}
dhcp-leasefile=/var/lib/misc/dnsmasq.leases
DNSMASQ
systemctl enable dnsmasq

# ── IP forwarding and NAT ─────────────────────────────────────────────────────
echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
sysctl -w net.ipv4.ip_forward=1

iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
iptables -A FORWARD -i eth0 -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -A FORWARD -i wlan0 -o eth0 -j ACCEPT
netfilter-persistent save

# ── Application directory ─────────────────────────────────────────────────────
mkdir -p "$APP_DIR"
# Copy all files including dotfiles
cp -r * "$APP_DIR/" 2>/dev/null || true
cp .env.template "$APP_DIR/.env.template" 2>/dev/null || true

python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip -q
"$APP_DIR/venv/bin/pip" install requests flask -q

# ── Environment file ──────────────────────────────────────────────────────────
cat > "$APP_DIR/.env" << ENV
NODE_NAME=${NODE_NAME}
CITYHAL_IP=${CITYHAL_IP}
NODE_BACKBONE_IP=${NODE_BACKBONE_IP}
BUS_SUBNET=${BUS_SUBNET}
API_KEY=BIOKO_BUS_KEY_CHANGE_ME
RELAY_CACHE_DB=${APP_DIR}/cache.db
HEALTH_REPORT_INTERVAL=60
ENV

# ── systemd service ───────────────────────────────────────────────────────────
cat > /etc/systemd/system/bioko-relay.service << SERVICE
[Unit]
Description=Bioko Transit Relay Node (${NODE_NAME})
After=network.target hostapd.service dnsmasq.service

[Service]
Type=simple
User=root
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/python relay_gateway.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable bioko-relay

echo ""
echo "========================================"
echo " Relay node '${NODE_NAME}' configured."
echo ""
echo " IMPORTANT: Edit ${APP_DIR}/.env"
echo " and set API_KEY to match the server."
echo ""
echo " Then start:"
echo "   sudo systemctl start hostapd"
echo "   sudo systemctl start dnsmasq"
echo "   sudo systemctl start bioko-relay"
echo ""
echo " Verify connectivity:"
echo "   ping ${CITYHAL_IP}"
echo "   curl http://bioko-server:5000/api/positions"
echo "========================================"
