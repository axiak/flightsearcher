#!/usr/bin/env python
import json
import datetime
import itertools
import random
import certifi
import urllib3

import requests

from . import config

http = urllib3.PoolManager(
    cert_reqs='CERT_REQUIRED',
    ca_certs=certifi.where(),
)

"""

ROUTES = {
    'BOS': [
    'PDX',
    'SFO',
    'PHL',
    'LHR',
    'MLA',
    'PVG',
    'NRT'
    ],
}


TRIP_RANGE_DAYS = (3, 14)

OFFSET_EXPONENT = 1.7
TRIP_DISTANCE_RANGE_DAYS = (14,90)

QPX_FREE_QUOTA = 50
QPX_QUERY_COST = 0.035

COST_PER_RUN = 1.0 # One dollar a day                                                                                                                       

"""

def main():
    slices = generate_all_slices()
    picked = pick_slices(slices, num_api_calls())
    for slice, _ in picked:
        print json.dumps(get_response(slice))
        return
        
    print picked


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


def parse_results(response):
    for trip_option in response.get('trips', {}).get('tripOption', ()):
        total_cost = float(trip_option.get('saleTotal', 'USD0')[3:])
        slices = trip_option.get('slice', {})
        total_mileage = get_mileage(slices)
        total_duration = sum(slice['duration'] for slice in 

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


if __name__ == '__main__':
    main()


