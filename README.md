# gq-transit-relay

District relay node software for the Guinea Ecuatorial private wireless intranet.
Runs on a Raspberry Pi 3 at each bus terminal — Luba, Riaba, Moka, Punta Europa (Bioko) and equivalent nodes in Rio Muni provinces.

**Part of the [GQ Transit platform](https://github.com/YOUR_USERNAME/gq-transit-infra)**

---

## What this does

Each relay node is a solar-powered Pi 3 on a pole at a bus terminal that:

1. **WiFi access point** — broadcasts hidden SSID `BIOKO_BUS` for buses arriving at the terminal
2. **Network gateway** — routes bus API traffic over the Ubiquiti point-to-point radio backbone to City Hall
3. **Local cache** — if the backbone link goes down, stores all bus events in SQLite and forwards them when the link recovers
4. **Health reporter** — sends its own status (backbone up/down, buses connected, signal strength, cache size) to City Hall every 60 seconds

## Hardware per relay node (~$372)

| Component | Cost |
|-----------|------|
| Raspberry Pi 3 Model B+ | $45 |
| Ubiquiti AirMax AC M5 radio | $89 |
| PoE injector (Ubiquiti POE-24) | $18 |
| TP-Link EAP225 Outdoor WiFi AP | $65 |
| Solar panel 50W + charge controller | $53 |
| LiFePO4 battery 20Ah 12V | $55 |
| Weatherproof IP65 enclosure + pole | $47 |

## Quick install

```bash
git clone https://github.com/YOUR_USERNAME/gq-transit-relay.git
cd gq-transit-relay/src
sudo bash install_relay_node.sh
```

The installer prompts for: node name, City Hall IP, WiFi password, backbone IP, bus subnet.

## Configuration

Edit `/opt/bioko_relay/.env` after installation:

```env
NODE_NAME=luba                    # luba | riaba | moka | punta_europa
CITYHAL_IP=10.10.0.1             # or 10.20.0.1 for Bata server
NODE_BACKBONE_IP=10.10.1.1
BUS_SUBNET=10.10.1
API_KEY=your_shared_key
```

## Network IP plan

| Node | Backbone IP | Bus subnet |
|------|-------------|------------|
| City Hall Malabo | 10.10.0.1 | 10.10.0.0/24 |
| Luba | 10.10.1.1 | 10.10.1.0/24 |
| Riaba | 10.10.2.1 | 10.10.2.0/24 |
| Moka | 10.10.3.1 | 10.10.3.0/24 |
| Punta Europa | 10.10.4.1 | 10.10.4.0/24 |
| City Hall Bata | 10.20.0.1 | 10.20.0.0/24 |

## Deploying new relay nodes (Rio Muni expansion)

Same installer, different answers to the prompts:
- Set `CITYHAL_IP=10.20.0.1` (Bata server)
- Use `10.20.X.X` backbone IPs for Rio Muni nodes
- Set `NODE_NAME` to the district (e.g. `mongomo`, `ebibeyin`)

## Diagnostics

```bash
# Check relay service
sudo systemctl status bioko-relay

# See which buses are currently connected
cat /var/lib/misc/dnsmasq.leases

# Check backbone connectivity
ping 10.10.0.1
curl http://bioko-server:5000/api/positions

# View relay health as seen by City Hall
curl http://10.10.0.1/api/relay/status
```

## License

MIT — owned by the project owner. See LICENSE.
