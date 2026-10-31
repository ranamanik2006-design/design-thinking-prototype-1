import random
from datetime import datetime
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

app = FastAPI(title="LPU Campus Multi-Block Water Point Telemetry")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Bridge cluster groups connected from Floor 3 onwards
CONNECTED_CLUSTERS = [
    {"cluster_id": "CL-A", "blocks": ["33", "34"]},
    {"cluster_id": "CL-B", "blocks": ["36", "37", "38"]},
    {"cluster_id": "CL-C", "blocks": ["25", "26", "27", "28"]},
]

CAMPUS_BLOCKS = ["33", "34", "36", "37", "38", "25", "26", "27", "28"]

# Base template distributing realistic failures (Empty, Hot/Warm, Chilled)
BASE_COOLERS = []
for block in CAMPUS_BLOCKS:
    # Floor 2: Generally reliable chilled cooler
    BASE_COOLERS.append({
        "id": f"WC-B{block}-F2",
        "name": f"Block {block} - Floor 2 Central",
        "block": block,
        "floor": 2,
        "near_class": 5,
        "type_profile": "chilled"
    })
    # Floor 4: Problematic unit (Compressor issue -> Warm/Hot Water)
    BASE_COOLERS.append({
        "id": f"WC-B{block}-F4",
        "name": f"Block {block} - Floor 4 Central",
        "block": block,
        "floor": 4,
        "near_class": 5,
        "type_profile": "hot_fault"
    })
    # Floor 6: Heavy rush unit (Runs out of water -> Empty/Dry)
    BASE_COOLERS.append({
        "id": f"WC-B{block}-F6",
        "name": f"Block {block} - Floor 6 Central",
        "block": block,
        "floor": 6,
        "near_class": 5,
        "type_profile": "empty_dry"
    })
    # Floor 8: Chilled top-floor cooler
    BASE_COOLERS.append({
        "id": f"WC-B{block}-F8",
        "name": f"Block {block} - Floor 8 Central",
        "block": block,
        "floor": 8,
        "near_class": 5,
        "type_profile": "chilled"
    })

def get_cluster(block_str: str):
    for group in CONNECTED_CLUSTERS:
        if block_str in group["blocks"]:
            return group
    return None

def calculate_campus_distance(u_block: str, u_floor: int, u_class: int, c_block: str, c_floor: int, c_class: int):
    same_block = (u_block == c_block)
    floor_diff = abs(u_floor - c_floor)
    corridor_diff = abs(u_class - c_class)

    dist = (floor_diff * 25) + (corridor_diff * 8)
    bridge_route_info = ""

    if not same_block:
        u_cluster = get_cluster(u_block)
        c_cluster = get_cluster(c_block)

        if u_cluster and c_cluster and (u_cluster["cluster_id"] == c_cluster["cluster_id"]):
            bridge_penalty = 50
            if u_floor < 3:
                extra_stairs = (3 - u_floor) * 25
                dist += bridge_penalty + extra_stairs
                bridge_route_info = f"Take stairs to Floor 3 bridge into Block {c_block}"
            else:
                dist += bridge_penalty
                bridge_route_info = f"Cross via Floor 3+ connector bridge into Block {c_block}"
        else:
            ground_detour = (u_floor * 25) + 120 + (c_floor * 25)
            dist += ground_detour
            bridge_route_info = f"Different wing: Cross via ground road into Block {c_block}"
    else:
        bridge_route_info = f"Same building (Block {u_block})"

    return dist, bridge_route_info

def get_live_cooler_data(user_block: str = None, user_floor: int = None, user_class: int = None):
    data = []
    for c in BASE_COOLERS:
        profile = c["type_profile"]
        
        # 1. Simulate profiles: Normal Chilled, Hot/Warm fault, or Empty
        if profile == "chilled":
            temp = round(11.0 + random.uniform(-0.8, 1.2), 1)
            tank_level = random.randint(65, 95)
            tds = random.randint(95, 115)
            status_code = "CHILLED"
            status_label = "Chilled & Ready"
            is_usable = True

        elif profile == "hot_fault":
            # Chiller turned off or compressor heating water
            temp = round(35.5 + random.uniform(-0.5, 2.5), 1)
            tank_level = random.randint(40, 75)
            tds = random.randint(110, 130)
            status_code = "HOT"
            status_label = "Hot / Chiller Failed"
            is_usable = False

        elif profile == "empty_dry":
            # Tank dry or supply cut
            temp = round(28.0 + random.uniform(-0.5, 1.0), 1)
            tank_level = random.randint(0, 4)
            tds = 0
            status_code = "EMPTY"
            status_label = "Empty / No Water"
            is_usable = False

        item = {
            "id": c["id"],
            "name": c["name"],
            "block": c["block"],
            "floor": c["floor"],
            "near_class": f"Near Room {c['floor']}0{c['near_class']}",
            "temperature_c": temp,
            "status_code": status_code,
            "status_label": status_label,
            "is_usable": is_usable,
            "tank_level_percent": tank_level,
            "tds_ppm": tds,
            "water_quality": "Normal" if tds > 0 else "No Flow",
            "last_updated": datetime.now().strftime("%H:%M:%S")
        }

        if user_block and user_floor is not None and user_class is not None:
            dist, bridge_note = calculate_campus_distance(user_block, user_floor, user_class, c["block"], c["floor"], c["near_class"])
            item["distance_meters"] = dist
            item["floor_steps"] = abs(user_floor - c["floor"])
            item["route_note"] = bridge_note

        data.append(item)

    if user_block and user_floor is not None and user_class is not None:
        data.sort(key=lambda x: x["distance_meters"])

    return data

@app.get("/")
def serve_index():
    return FileResponse("index.html")

@app.get("/api/coolers")
def list_all_coolers(block: str = Query(None), floor: int = Query(None), classroom: int = Query(None)):
    return {"coolers": get_live_cooler_data(block, floor, classroom)}

@app.get("/api/coolers/nearest")
def get_nearest(block: str = Query(...), floor: int = Query(...), classroom: int = Query(...)):
    coolers = get_live_cooler_data(block, floor, classroom)
    # Filter for the nearest USABLE (working & not empty) cooler
    usable_coolers = [c for c in coolers if c["is_usable"]]
    nearest_cooler = usable_coolers[0] if usable_coolers else (coolers[0] if coolers else None)
    return {"nearest": nearest_cooler}