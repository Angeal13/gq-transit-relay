# Bioko Island Intranet — Network Plan
# Complete IP addressing, hardware BOM, and radio link specs

## IP addressing scheme

All private. No internet connection required or used.

### Backbone network (10.10.0.0/16)
Point-to-point links between Malabo and each district node.

| Device                   | IP           | Interface |
|--------------------------|--------------|-----------|
| City Hall server         | 10.10.0.1    | eth1 (to backbone radio) |
| Malabo backbone radio    | 10.10.0.2    | (Ubiquiti AirMax) |
| Luba relay node          | 10.10.1.1    | eth0 (from radio) |
| Riaba relay node         | 10.10.2.1    | eth0 (from radio) |
| Moka relay node          | 10.10.3.1    | eth0 (from radio) |
| Punta Europa relay node  | 10.10.4.1    | eth0 (from radio) |

### Bus WiFi subnets (DHCP, assigned automatically)
Each relay node's dnsmasq assigns buses IPs in its local subnet.
The 'bioko-server' hostname resolves to 10.10.0.1 everywhere.

| Terminal     | Bus subnet    | Gateway (relay node) |
|--------------|---------------|---------------------|
| Malabo depot | 10.10.0.10–250| 10.10.0.1 (direct)  |
| Luba         | 10.10.1.10–250| 10.10.1.1           |
| Riaba        | 10.10.2.10–250| 10.10.2.1           |
| Moka         | 10.10.3.10–250| 10.10.3.1           |
| Punta Europa | 10.10.4.10–250| 10.10.4.1           |

### Malabo urban WiFi coverage
In Malabo, additional APs can be deployed at key stops.
All use the same BIOKO_BUS SSID and connect to the City Hall server directly.
Suggested locations: Hospital Regional, Mercado Central, Estadio La Paz.

---

## Hardware bill of materials

### City Hall (Malabo) — 1× installation

| Item | Model | Cost | Qty | Total |
|------|-------|------|-----|-------|
| Backbone radio (master) | Ubiquiti AirMax AC M5 | $89 | 1 | $89 |
| PoE injector for radio | Ubiquiti POE-24-12W | $18 | 1 | $18 |
| Outdoor antenna (sector) | Ubiquiti AMO-5G13 | $49 | 1 | $49 |
| Rooftop mounting bracket | Generic | $15 | 1 | $15 |
| WiFi AP (bus depot) | TP-Link EAP225 Outdoor | $65 | 1 | $65 |
| **Subtotal City Hall** | | | | **$236** |

### District relay node — 4× installations (Luba, Riaba, Moka, Punta Europa)

| Item | Model | Cost | Qty per node | Total (×4) |
|------|-------|------|--------------|------------|
| Raspberry Pi 3 Model B+ | RPi Foundation | $45 | 1 | $180 |
| MicroSD 32GB | Class 10 | $8 | 1 | $32 |
| Backbone radio (slave) | Ubiquiti AirMax AC M5 | $89 | 1 | $356 |
| PoE injector | Ubiquiti POE-24-12W | $18 | 1 | $72 |
| Directional antenna | Ubiquiti AMY-9M16 | $59 | 1 | $236 |
| WiFi AP (bus terminal) | TP-Link EAP225 Outdoor | $65 | 1 | $260 |
| Solar panel 50W | Generic 12V | $35 | 1 | $140 |
| Solar charge controller | 10A PWM | $18 | 1 | $72 |
| LiFePO4 battery 20Ah | 12V | $55 | 1 | $220 |
| Weatherproof enclosure | IP65 plastic box | $22 | 1 | $88 |
| Mounting pole + hardware | Galvanized steel | $25 | 1 | $100 |
| **Subtotal per node** | | | | **$174** |
| **Subtotal 4 nodes** | | | | **$696** |

### Total intranet hardware cost

| Component | Cost |
|-----------|------|
| City Hall backbone + depot AP | $236 |
| 4 district relay nodes | $696 |
| Cabling and misc hardware | $80 |
| **TOTAL** | **$1,012** |

---

## Radio link specifications

### Malabo → Luba (80 km, longest link)
- Technology: Ubiquiti AirMax AC M5 (5 GHz licensed-exempt)
- Required line of sight: YES — mount on highest available structure
- Fresnel zone clearance: 12m at midpoint (check terrain)
- Expected throughput: 50–150 Mbps (far more than needed)
- Data per bus per day: ~8 MB (stop events + engine readings + heartbeat)
- 55 buses × 8 MB = ~440 MB/day total island — trivial for this link

### Malabo → Riaba (45 km)
- Same hardware, shorter distance → better signal margin
- Line of sight: check terrain between Malabo and Riaba coast

### Malabo → Moka (55 km, crosses highlands)
- Mount Bioko (3011m) may obstruct direct LOS
- Consider relay via a hilltop intermediate node if LOS is blocked
- Budget $174 for one additional intermediate relay if needed

### Malabo → Punta Europa (18 km)
- Short link, best signal of all four
- Could use lower-cost Ubiquiti NanoStation instead of AirMax M5

---

## What happens when internet is completely down

The system is fully self-contained. Internet outage has zero effect:

1. Buses continue recording stops and engine data
2. At each terminal, data syncs to City Hall over the private backbone
3. The map web app works for anyone on the intranet (local network)
4. WhatsApp/SMS notifications to mechanics do NOT work (need internet)
   → Fallback: mechanic checks /admin/fleet/ directly on the LAN
5. Passenger-facing map works from any device connected to a BIOKO_BUS AP
6. ETA calculations run entirely on the City Hall server — no cloud needed

The only feature that requires internet: WhatsApp/SMS alerts to mechanic.
Everything else runs indefinitely on the private intranet.
