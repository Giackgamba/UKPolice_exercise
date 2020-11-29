import json
import logging
import re
from datetime import date

import click
from dask.distributed import Client

from api_interface import ApiInterface
from models import init_db


log = logging.getLogger(__name__)
logging.basicConfig()


def validate_date(cts, param, value):
    match = re.match('20[0-9]{2}-(0[1-9]|1[012])', value)
    if not match:
        raise click.BadParameter(message='date is not in the right format')
    return value


@click.command()
@click.option('--current_date', '-t',
              help='The current date (YYYY-MM format)',
              default=lambda: date.today().strftime('%Y-%m'),
              callback=validate_date)
@click.option('--from_last_update', '-u',
              is_flag=True,
              help='Only run for dates after last_update')
@click.option('--limit', '-n',
              type=int,
              help='Only run for n forces and areas')
@click.option('--local', '-l',
              is_flag=True,
              default=False,
              help='Run Dask in single node mode, helpful for debugging')
def run(current_date, from_last_update, limit, local):
    init_db()

    police_api = ApiInterface('https://data.police.uk/api/')
    dates = police_api.get_all_dates()

    dates = [d for d in dates if d < current_date]

    if not local:
        # if a Client call is detected dask will automagically use it
        Client('scheduler:8786')

    if from_last_update:
        with open('last_update.json', 'r') as f:
            last_update = json.load(f)['last_update']
        dates = [d for d in dates if d > last_update]

    police_api.get_data(dates, limit)


if __name__ == '__main__':
    run()
