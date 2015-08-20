#!/usr/bin/env python
import os
import time
import json
import random
import sqlite3
import datetime
import itertools
import collections

import certifi
import urllib3
import requests

from . import config

http = urllib3.PoolManager(
    cert_reqs='CERT_REQUIRED',
    ca_certs=certifi.where(),
)

def main():
    sleep_seconds = random.random() * config.RANDOM_SLEEP_TIME
    print "Sleeping {0} seconds (less than {1} in config)".format(
        sleep_seconds, config.RANDOM_SLEEP_TIME
    )
    time.sleep(sleep_seconds)
    c = get_database()
    slices = generate_all_slices()
    slices = weigh_on_previous(c, slices)
    picked = pick_slices(slices, num_api_calls())

    all_airfares = []
    for slice, _ in picked:
        air_fares = parse_results(slice, get_response(slice))
        air_fares = pick_lowest_per_airline(air_fares)
        all_airfares.extend(air_fares)

    c.executemany("INSERT INTO airfares VALUES (?,?,?,?,?,?,?,?,?,?)", all_airfares)
    c.commit()


def weigh_on_previous(c, slices):
    by_od = collections.defaultdict(list)
    for slice, weight in slices:
        by_od[(slice[0]['origin'], slice[0]['destination'])].append((slice, weight))

    range_start = datetime.date.today() - datetime.timedelta(days=7)
    range_stop = datetime.date.today() + datetime.timedelta(config.TRIP_DISTANCE_RANGE_DAYS[1] + 14)

    result = []

    for origin, destination in by_od.keys():
        cursor = c.cursor()
        cursor.execute("SELECT * FROM airfares WHERE origin = ? AND dest = ? AND date(start_date) BETWEEN date(?) and date(?)",
                       (origin, destination, range_start, range_stop))
        air_fares = map(Airfare._make, cursor.fetchall())
        for slice, weight in by_od[origin, destination]:
            if not air_fares:
                result.append((slice, weight * config.TRIP_DISTANCE_RANGE_DAYS[1]))
            else:
                result.append((slice, min(compute_distance_weight(air_fare, slice) for air_fare in air_fares) * weight))
    return result


def compute_distance_weight(air_fare, slice):
    start_date = slice[0]['date']
    stop_date = slice[1]['date']
    weights = [1]
    for slice_date, name in ((start_date, 'start_date'), (stop_date, 'end_date')):
        air_fare_date = datetime.datetime.strptime(getattr(air_fare, name), "%Y-%m-%d")
        slice_date = datetime.datetime.strptime(slice_date, "%Y-%m-%d")
        weights.append(abs((slice_date - air_fare_date).days))

    return max(weights)


def pick_lowest_per_airline(air_fares):
    result = {}
    for air_fare in air_fares:
        other = result.get(air_fare.airlines)
        if other is None or other.total_cost > air_fare.total_cost:
            result[air_fare.airlines] = air_fare
    return result.values()

def pick_slices(slices, num_to_pick):
    slices = list(slices)
    total_weight = sum(weight for _, weight in slices)
    picked = set()
    random.shuffle(slices)
    while len(picked) < num_to_pick:
        picked.add(get_index(slices, random.random() * total_weight))

    return [slices[i] for i in picked]
    

def get_index(slices, picked):
    current = 0
    for i, (_, weight) in enumerate(slices):
        current += weight
        if current > picked:
            return i
    return i


def quadratic_ranges((start, stop), exponent):
    i = 1
    current = start
    seen = set()
    while True:
        if current not in seen:
            yield current
            seen.add(current)
        current = int(start + (i ** exponent))
        if current > stop:
            break
        i += 1


def num_api_calls():
    return config.QPX_FREE_QUOTA + int(config.COST_PER_RUN / float(config.QPX_QUERY_COST))


Airfare = collections.namedtuple('Airfare', 
                                 'origin dest start_date end_date calculated_date total_cost total_mileage total_duration fare_calculation airlines'.split()
                                 )


def parse_results(input_slice, response):
    airfares = []
    for trip_option in response.get('trips', {}).get('tripOption', ()):
        total_cost = float(trip_option.get('saleTotal', 'USD0')[3:])
        slices = trip_option.get('slice', {})
        total_mileage = get_mileage(slices)
        total_duration = sum(slice['duration'] for slice in slices)
        fare_calculation = trip_option['pricing'][0]['fareCalculation']
        
        airlines = sorted(set(segment["flight"]["carrier"] for slice in slices
                              for segment in slice["segment"]))
        airfares.append(Airfare(
                input_slice[0]['origin'],
                input_slice[0]['destination'],
                parse_date(input_slice[0]['date']),
                parse_date(input_slice[1]['date']) ,
                datetime.datetime.now(),
                total_cost,
                total_mileage,
                total_duration,
                fare_calculation,
                ",".join(airlines)
        ))
    return airfares

def parse_date(input_str):
    return datetime.datetime.strptime(input_str, "%Y-%m-%d").date()


def get_mileage(slices):
    mileage = 0
    for slice in slices:
        for segment in slice['segment']:
            for leg in segment['leg']:
                mileage += leg['mileage']
    return mileage
            


def generate_all_slices():
    TODAY = datetime.date.today()
    slice_groups = []
    for origin, dest, base, length in all_trip_types():
        start = TODAY + datetime.timedelta(days=base)
        end = start + datetime.timedelta(days=length)
        slice_groups.append(([
                {
                    "origin": origin,
                    "destination": dest,
                    "date": start.strftime("%Y-%m-%d")
                },
                {
                    "origin": dest,
                    "destination": origin,
                    "date": end.strftime("%Y-%m-%d")
                }
        ], get_weight(base)))
    return slice_groups


def get_weight(base):
    return (120.0 / base) ** .4


def all_trip_types():
    for (origin, dest), base, length in itertools.product(
        od_pairs(), 
        quadratic_ranges(config.TRIP_DISTANCE_RANGE_DAYS, config.OFFSET_EXPONENT),
        quadratic_ranges(config.TRIP_RANGE_DAYS, config.RANGE_EXPONENT)
    ):
        yield origin, dest, base, length


def od_pairs():
    for origin in config.ROUTES:
        for dest in config.ROUTES[origin]:
            yield origin, dest


def generate_slices(from_, to_):
    current = datetime.datetime.now() + datetime.timedelta(days=14)
    slices = []
    for _ in range(1, 5):
        current += datetime.timedelta(days=1)
        slices.extend([
            {
                "origin": from_,
                "destination": to_,
                "date": current.strftime("%Y-%m-%d")
            },
            {
                "origin": to_,
                "destination": from_,
                "date": (current + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            }
        ])
    return slices


def pick_lowest_per_airline(air_fares):
    result = {}
    for air_fare in air_fares:
        other = result.get(air_fare.airlines)
        if other is None or other.total_cost > air_fare.total_cost:
            result[air_fare.airlines] = air_fare
    return result.values()

def pick_slices(slices, num_to_pick):
    slices = list(slices)
    total_weight = sum(weight for _, weight in slices)
    picked = set()
    random.shuffle(slices)
    while len(picked) < num_to_pick:
        picked.add(get_index(slices, random.random() * total_weight))

    return [slices[i] for i in picked]
    

def get_index(slices, picked):
    current = 0
    for i, (_, weight) in enumerate(slices):
        current += weight
        if current > picked:
            return i
    return i


def quadratic_ranges((start, stop), exponent):
    i = 1
    current = start
    seen = set()
    while True:
        if current not in seen:
            yield current
            seen.add(current)
        current = int(start + (i ** exponent))
        if current > stop:
            break
        i += 1


def num_api_calls():
    return config.QPX_FREE_QUOTA + int(config.COST_PER_RUN / float(config.QPX_QUERY_COST))


Airfare = collections.namedtuple('Airfare', 
                                 'origin dest start_date end_date calculated_date total_cost total_mileage total_duration fare_calculation airlines'.split()
                                 )


def parse_results(input_slice, response):
    airfares = []
    for trip_option in response.get('trips', {}).get('tripOption', ()):
        total_cost = float(trip_option.get('saleTotal', 'USD0')[3:])
        slices = trip_option.get('slice', {})
        total_mileage = get_mileage(slices)
        total_duration = sum(slice['duration'] for slice in slices)
        fare_calculation = trip_option['pricing'][0]['fareCalculation']
        
        airlines = sorted(set(segment["flight"]["carrier"] for slice in slices
                              for segment in slice["segment"]))
        airfares.append(Airfare(
                input_slice[0]['origin'],
                input_slice[0]['destination'],
                parse_date(input_slice[0]['date']),
                parse_date(input_slice[1]['date']) ,
                datetime.date.today(),
                total_cost,
                total_mileage,
                total_duration,
                fare_calculation,
                ",".join(airlines)
        ))
    return airfares

def parse_date(input_str):
    return datetime.datetime.strptime(input_str, "%Y-%m-%d").date()


def get_mileage(slices):
    mileage = 0
    for slice in slices:
        for segment in slice['segment']:
            for leg in segment['leg']:
                mileage += leg['mileage']
    return mileage
            


def generate_all_slices():
    TODAY = datetime.date.today()
    slice_groups = []
    for origin, dest, base, length in all_trip_types():
        start = TODAY + datetime.timedelta(days=base)
        end = start + datetime.timedelta(days=length)
        slice_groups.append(([
                {
                    "origin": origin,
                    "destination": dest,
                    "date": start.strftime("%Y-%m-%d")
                },
                {
                    "origin": dest,
                    "destination": origin,
                    "date": end.strftime("%Y-%m-%d")
                }
        ], get_weight(base)))
    return slice_groups


def get_weight(base):
    return (120.0 / base) ** .4


def all_trip_types():
    for (origin, dest), base, length in itertools.product(
        od_pairs(), 
        quadratic_ranges(config.TRIP_DISTANCE_RANGE_DAYS, config.OFFSET_EXPONENT),
        quadratic_ranges(config.TRIP_RANGE_DAYS, config.RANGE_EXPONENT)
    ):
        yield origin, dest, base, length


def od_pairs():
    for origin in config.ROUTES:
        for dest in config.ROUTES[origin]:
            yield origin, dest


def generate_slices(from_, to_):
    current = datetime.datetime.now() + datetime.timedelta(days=14)
    slices = []
    for _ in range(1, 5):
        current += datetime.timedelta(days=1)
        slices.extend([
            {
                "origin": from_,
                "destination": to_,
                "date": current.strftime("%Y-%m-%d")
            },
            {
                "origin": to_,
                "destination": from_,
                "date": (current + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            }
        ])
    return slices


def get_response(slices):
    request = {
        "request": {
            "passengers": {
                "adultCount": 1
            },
            "solutions": 100,
            "slice": slices,
        }
    }

    url = 'https://www.googleapis.com/qpxExpress/v1/trips/search?key=' + config.API_KEY
    r = requests.post(url,
                      headers={'content-type': 'application/json'},
                      data=json.dumps(request))
    return r.json()


def get_database():
    c = sqlite3.connect(os.path.join(os.path.dirname(__file__), '..', 'db', 'database.sqlite'))

    c.execute('''
CREATE TABLE IF NOT EXISTS airfares (
   origin TEXT,
   dest TEXT,
   start_date TEXT,
   end_date TEXT,
   calculated_date TEXT,
   total_cost REAL,
   total_mileage INTEGER,
   total_duration INTEGER,
   fare_calculation TEXT,
   airlines TEXT
)''')
    c.execute('''
CREATE INDEX IF NOT EXISTS idxAirfaresDates ON airfares (
   origin, dest, start_date
)''')
    return c


if __name__ == '__main__':
    main()



