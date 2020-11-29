import click
import re
import json
import logging
from datetime import date
from dask.distributed import Client

from api_interface import ApiInterface
from models import init_db

client = Client('scheduler:8786')


def validate_polygon(ctx, param, value):
    try:
        poly = ApiInterface.poly_from_string(value)
        return poly
    except ValueError:
        raise click.BadParameter(message='area is not in the right format')


def validate_date(cts, param, value):
    match = re.match('20[0-9]{2}-(0[1-9]|1[012])', value)
    if not match:
        raise click.BadParameter(message='date is not in the right format')
    return value


@click.command()
@click.option('--area', default='49,-8.5:49,2:60,2:60,-8.5',
              help="The area to scan, in the format: lat,long:lat,long...",
              callback=validate_polygon)
@click.option('--current_date', '-t',
              help='The current date',
              default=lambda: date.today().strftime('%Y-%m'),
              callback=validate_date)
@click.option('--from_last_update', '-u', is_flag=True)
def run(area, current_date, from_last_update):
    init_db()

    police_api = ApiInterface('https://data.police.uk/api/')
    dates = police_api.get_all_dates()

    dates = [d for d in dates if d < current_date]

    if from_last_update:
        with open('last_update.json', 'r') as f:
            last_update = json.load(f)['last_update']
        dates = [d for d in dates if d > last_update]

    police_api.get_data(area, dates)


if __name__ == '__main__':
    run()
