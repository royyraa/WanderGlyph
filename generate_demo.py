#!/usr/bin/env python3
"""
Generate a realistic fake Google Timeline JSON for WanderGlyph demo purposes.
Simulates a traveller visiting major US cities over several years.

Usage:
    python generate_demo.py
    python generate_demo.py --output data/demo.json --years 2020 2021 2022 2023 2024
"""

import json
import random
import argparse
import math
import os
from datetime import datetime, timedelta, timezone

# ── Major US cities with coordinates ─────────────────────────────────────────
CITIES = [
    ("New York, NY",         40.7128,  -74.0060),
    ("Los Angeles, CA",      34.0522, -118.2437),
    ("Chicago, IL",          41.8781,  -87.6298),
    ("Houston, TX",          29.7604,  -95.3698),
    ("Phoenix, AZ",          33.4484, -112.0740),
    ("Philadelphia, PA",     39.9526,  -75.1652),
    ("San Antonio, TX",      29.4241,  -98.4936),
    ("San Diego, CA",        32.7157, -117.1611),
    ("Dallas, TX",           32.7767,  -96.7970),
    ("Austin, TX",           30.2672,  -97.7431),
    ("San Francisco, CA",    37.7749, -122.4194),
    ("Seattle, WA",          47.6062, -122.3321),
    ("Denver, CO",           39.7392, -104.9903),
    ("Boston, MA",           42.3601,  -71.0589),
    ("Nashville, TN",        36.1627,  -86.7816),
    ("Miami, FL",            25.7617,  -80.1918),
    ("Atlanta, GA",          33.7490,  -84.3880),
    ("Minneapolis, MN",      44.9778,  -93.2650),
    ("Portland, OR",         45.5051, -122.6750),
    ("Las Vegas, NV",        36.1699, -115.1398),
    ("New Orleans, LA",      29.9511,  -90.0715),
    ("Kansas City, MO",      39.0997,  -94.5786),
    ("Indianapolis, IN",     39.7684,  -86.1581),
    ("Columbus, OH",         39.9612,  -82.9988),
    ("Charlotte, NC",        35.2271,  -80.8431),
    ("Raleigh, NC",          35.7796,  -78.6382),
    ("Salt Lake City, UT",   40.7608, -111.8910),
    ("Albuquerque, NM",      35.0844, -106.6504),
    ("Tucson, AZ",           32.2226, -110.9747),
    ("Memphis, TN",          35.1495,  -90.0490),
    ("Louisville, KY",       38.2527,  -85.7585),
    ("Richmond, VA",         37.5407,  -77.4360),
    ("Oklahoma City, OK",    35.4676,  -97.5164),
    ("Boise, ID",            43.6150, -116.2023),
    ("Omaha, NE",            41.2565,  -95.9345),
    ("Billings, MT",         45.7833, -108.5007),
    ("Fargo, ND",            46.8772,  -96.7898),
    ("Sioux Falls, SD",      43.5473,  -96.7283),
    ("Des Moines, IA",       41.5868,  -93.6250),
    ("Little Rock, AR",      34.7465,  -92.2896),
]

ACTIVITY_TYPES = [
    ("IN_PASSENGER_VEHICLE", "vehicle", 0.40),
    ("FLYING",               "flying",  0.15),
    ("WALKING",              "walking", 0.25),
    ("IN_TRAIN",             "transit", 0.10),
    ("CYCLING",              "cycling", 0.10),
]

VISIT_TYPES = [
    "TYPE_RESTAURANT", "TYPE_CAFE", "TYPE_SHOPPING",
    "TYPE_PARK", "TYPE_MUSEUM", "TYPE_HOTEL",
    "TYPE_GAS_STATION", "TYPE_GROCERY", "UNKNOWN",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt_latlng(lat, lon):
    return f"{lat:.7f}°, {lon:.7f}°"

def fmt_ts(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')

def jitter(val, amount=0.02):
    return val + random.uniform(-amount, amount)

def interpolate_path(lat1, lon1, lat2, lon2, n_points):
    pts = []
    for i in range(n_points):
        t   = i / max(n_points - 1, 1)
        lat = lat1 + (lat2 - lat1) * t + random.gauss(0, 0.005)
        lon = lon1 + (lon2 - lon1) * t + random.gauss(0, 0.005)
        pts.append((lat, lon))
    return pts

def haversine_km(lat1, lon1, lat2, lon2):
    R    = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a    = (math.sin(dlat/2)**2 +
            math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
            math.sin(dlon/2)**2)
    return R * 2 * math.asin(math.sqrt(a))

def pick_activity(dist_km):
    if dist_km > 500:
        return "FLYING", "flying"
    weights = [t[2] for t in ACTIVITY_TYPES if t[1] != 'flying']
    types   = [(t[0], t[1]) for t in ACTIVITY_TYPES if t[1] != 'flying']
    return random.choices(types, weights=weights)[0]


# ── Segment builders ──────────────────────────────────────────────────────────

def make_path_segment(lat1, lon1, lat2, lon2, start_dt, duration_hours):
    n_pts  = random.randint(8, 30)
    pts    = interpolate_path(lat1, lon1, lat2, lon2, n_pts)
    end_dt = start_dt + timedelta(hours=duration_hours)
    path   = []
    for i, (lat, lon) in enumerate(pts):
        t  = i / max(len(pts) - 1, 1)
        ts = start_dt + timedelta(seconds=t * duration_hours * 3600)
        path.append({"point": fmt_latlng(lat, lon), "timestamp": fmt_ts(ts)})
    return {"startTime": fmt_ts(start_dt), "endTime": fmt_ts(end_dt),
            "timelinePath": path}, end_dt

def make_activity_segment(lat1, lon1, lat2, lon2, start_dt, duration_hours):
    dist_km     = haversine_km(lat1, lon1, lat2, lon2)
    atype, _    = pick_activity(dist_km)
    end_dt      = start_dt + timedelta(hours=duration_hours)
    return {
        "startTime": fmt_ts(start_dt), "endTime": fmt_ts(end_dt),
        "startTimeTimezoneUtcOffsetMinutes": -300,
        "endTimeTimezoneUtcOffsetMinutes":   -300,
        "activity": {
            "start": {"latLng": fmt_latlng(lat1, lon1)},
            "end":   {"latLng": fmt_latlng(lat2, lon2)},
            "distanceMeters": dist_km * 1000,
            "topCandidate": {"type": atype,
                             "probability": round(random.uniform(0.7, 0.99), 2)},
        },
    }, end_dt

def make_visit_segment(lat, lon, start_dt, duration_hours):
    end_dt = start_dt + timedelta(hours=duration_hours)
    stype  = random.choice(VISIT_TYPES)
    return {
        "startTime": fmt_ts(start_dt), "endTime": fmt_ts(end_dt),
        "startTimeTimezoneUtcOffsetMinutes": -300,
        "endTimeTimezoneUtcOffsetMinutes":   -300,
        "visit": {
            "hierarchyLevel": 0,
            "probability":    round(random.uniform(0.6, 0.99), 2),
            "topCandidate": {
                "placeId":       f"ChIJ{random.randint(10000,99999)}",
                "semanticType":  stype,
                "probability":   round(random.uniform(0.5, 0.95), 2),
                "placeLocation": {"latLng": fmt_latlng(
                    jitter(lat, 0.01), jitter(lon, 0.01)
                )},
            },
        },
    }, end_dt


# ── Generator ─────────────────────────────────────────────────────────────────

def generate(years, seed=42):
    random.seed(seed)
    segments = []

    for year in years:
        n_cities   = random.randint(12, 20)
        itinerary  = random.sample(CITIES, n_cities)
        current_dt = datetime(year, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
        year_end   = datetime(year, 12, 31, 23, 59, 0, tzinfo=timezone.utc)
        prev_city  = itinerary[0]

        for city in itinerary[1:]:
            if current_dt >= year_end:
                break

            _, lat1, lon1 = prev_city
            _, lat2, lon2 = city
            dist_km       = haversine_km(lat1, lon1, lat2, lon2)
            travel_h      = max(1.0, dist_km / 80 + random.uniform(-0.5, 1.5))

            seg, current_dt = make_path_segment(lat1, lon1, lat2, lon2, current_dt, travel_h)
            segments.append(seg)

            act_seg, _ = make_activity_segment(
                lat1, lon1, lat2, lon2,
                current_dt - timedelta(hours=travel_h), travel_h
            )
            segments.append(act_seg)

            stay_days = random.randint(2, 10)
            stay_end  = min(current_dt + timedelta(days=stay_days), year_end)
            wander_dt = current_dt

            while wander_dt < stay_end:
                wlat2, wlon2 = jitter(lat2, 0.05), jitter(lon2, 0.05)
                wander_h     = random.uniform(0.5, 3.0)
                wseg, wander_dt = make_path_segment(
                    jitter(lat2, 0.02), jitter(lon2, 0.02),
                    wlat2, wlon2, wander_dt, wander_h
                )
                segments.append(wseg)

                if random.random() < 0.6:
                    visit_h   = random.uniform(0.5, 2.5)
                    vseg, wander_dt = make_visit_segment(wlat2, wlon2, wander_dt, visit_h)
                    segments.append(vseg)

                wander_dt += timedelta(hours=random.uniform(1, 6))

            current_dt = stay_end
            prev_city  = city

    random.shuffle(segments)
    return {"semanticSegments": segments}


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate fake Google Timeline JSON for WanderGlyph demos"
    )
    parser.add_argument('--output', default='data/demo.json',
                        help='Output path (default: data/demo.json)')
    parser.add_argument('--years', nargs='+', type=int,
                        default=[2020, 2021, 2022, 2023, 2024],
                        help='Years to simulate (default: 2020-2024)')
    parser.add_argument('--seed', type=int, default=42,
                        help='Random seed (default: 42)')
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    print(f"Generating demo data for {args.years}…")
    data = generate(args.years, seed=args.seed)

    path_segs = sum(1 for s in data['semanticSegments'] if 'timelinePath' in s)
    act_segs  = sum(1 for s in data['semanticSegments'] if 'activity' in s)
    visits    = sum(1 for s in data['semanticSegments'] if 'visit' in s)

    with open(args.output, 'w') as f:
        json.dump(data, f)

    print(f"Saved → {args.output}")
    print(f"  {path_segs:,} GPS path segments")
    print(f"  {act_segs:,} activity segments")
    print(f"  {visits:,} visit records")
    print(f"\nGenerate map:")
    print(f"  python wanderglyph.py --json-file {args.output} --theme dark --open")


if __name__ == '__main__':
    main()
