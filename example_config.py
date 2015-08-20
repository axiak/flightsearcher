API_KEY = "api key"

ROUTES = {
    'BOS': [
        'PDX',
        'SFO',
        'PHL',
        'LHR',
        'MLA',
        'PVG',
        'NRT',
        'KEF',
        'HEL',
        'CPH',
        'MIA'
    ],
}


TRIP_RANGE_DAYS = (3, 14)

TRIP_DISTANCE_RANGE_DAYS = (14, 120)

RANGE_EXPONENT = 1.7
OFFSET_EXPONENT = 1.8

QPX_FREE_QUOTA = 50
QPX_QUERY_COST = 0.035

COST_PER_RUN = 1.0 # One dollar a day

# Sleep at the start so that it runs at different times each day
RANDOM_SLEEP_TIME = 3600 * 16
