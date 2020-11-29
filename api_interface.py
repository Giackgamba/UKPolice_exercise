import json
import logging
from time import sleep

import dask
import requests
from shapely import ops
from shapely.geometry import LineString, Polygon, mapping

from models import Crime, CrimeCategory, Outcome

logging.basicConfig
log = logging.getLogger(__name__)


class ApiInterface():

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    def get_categories(self, date: str) -> list:
        """
        Return all catgories
        """
        categories = requests.get(self.base_url + '/crime-categories',
                                  params={'date': date}
                                  )
        if categories.status_code != 200:
            raise Exception
        return categories.json()

    def get_forces(self) -> list:
        """
        Return all forces
        """
        forces = requests.get(self.base_url + '/forces',
                              )
        if forces.status_code != 200:
            raise Exception
        return [force['id'] for force in forces.json()]

    def get_areas(self, force) -> list:
        """
        Return all areas for a force
        """
        areas = requests.get(self.base_url + force + '/neighbourhoods',
                             )
        if areas.status_code != 200:
            print('Hitting quota limit, sleeping a sec')
            sleep(0.1)
            return self.get_areas(force)
        return [area['id'] for area in areas.json()]

    def get_all_dates(self) -> list:
        dates = requests.get(self.base_url + '/crimes-street-dates')
        if dates.status_code != 200:
            raise Exception(dates.content)
        return sorted([d['date'] for d in dates.json()])

    def get_boundary(self, force: str, area: str) -> list:
        """
        Return the boundary of an area
        """
        coords = requests.get(self.base_url + force + '/' + area + '/boundary',
                              )
        # print('getting boundary: {}'.format(area))
        if coords.status_code != 200:
            print('Hitting quota limit, sleeping a sec')
            sleep(0.1)
            return self.get_boundary(force, area)
        boundary = [[float(coord)for coord in list(point.values())]
                    for point in coords.json()
                    ]
        return (Polygon(boundary), force)

    @staticmethod
    def merge_polygons(poly_list: list, force: str) -> Polygon:
        force_poly = ops.cascaded_union(poly_list)
        return (force_poly, force)

    def get_crimes(self, date: str, poly: Polygon, force: str):
        poly_string = self.poly_to_string(poly)
        crimes = requests.post(self.base_url + '/crimes-street/all-crime',
                               data={'date': date,
                                     'poly': poly_string})
        if crimes.status_code == 503:
            polies = self.subdivide_poly(poly)
            for p in polies:
                return self.get_crimes(date, p, force)
        if crimes.status_code == 429:
            print('Hitting crime quota limit, sleeping a sec')
            sleep(0.1)
            return self.get_crimes(date, poly, force)
        print('got crimes')
        return crimes.json()

    def get_outcomes(self, date: str, poly: Polygon,):
        poly_string = self.poly_to_string(poly)
        outcomes = requests.post(self.base_url + '/outcomes-at-location',
                                 data={'date': date,
                                       'poly': poly_string})
        if outcomes.status_code == 503:
            polies = self.subdivide_poly(poly)
            for p in polies:
                return self.get_outcomes(date, p)
        if outcomes.status_code == 429:
            print('Hitting outcome quota limit, sleeping a sec')
            sleep(0.1)
            return self.get_outcomes(date, poly)
        print('got outcomes')
        return outcomes.json()

    def download_and_load_crimes(self, date: str, poly: Polygon, force: str) -> list:
        crimes = self.get_crimes(date, poly, force)

        for crime in crimes:
            crime = Crime(crime, force)
            crime.get_or_create()

    def download_and_load_outcomes(self, date: str, poly: Polygon) -> list:

        outcomes = self.get_outcomes(date, poly)
        for outcome in outcomes:
            outcome = Outcome(outcome)
            outcome.get_or_create()

    def get_data(self, dates, limit):
        """
        Iterate the given dates to insert data in db
        Save a file with the highest date loaded
        """
        # Get categories from API and insert in DB
        categories = self.get_categories(dates[-1])
        for category in categories:
            category = CrimeCategory(category)
            category.get_or_create()

        # Create list of areas
        forces = self.get_forces()
        areas_list = list()
        for force in forces[:limit]:
            print(force)
            areas = self.get_areas(force)
            for area in areas[:limit]:
                print(area)
                # Promise to ask the boundary of each area to the API
                areas_list.append(
                    dask.delayed(self.get_boundary)(force, area))
        # Execute promises
        force_boundaries = dask.compute(*areas_list)

        # Create a list of requests
        crimes_list = list()
        outcome_list = list()
        for date in dates:
            log.info('Preparing data download for {}'.format(date))
            print('Preparing data download for {}'.format(date))

            for poly, force in force_boundaries:
                # Promise to download and save the data
                crimes_list.append(
                    dask.delayed(
                        self.download_and_load_crimes)(date, poly, force))
                outcome_list.append(
                    dask.delayed(
                        self.download_and_load_outcomes)(date, poly))
            with open('last_update.json', 'w') as f:
                json.dump({'last_update': date}, f)
        # Execute promises
        dask.compute(crimes_list + outcome_list)

    @staticmethod
    def poly_to_string(poly: Polygon) -> str:
        """
        Convert a Polygon to a string formatted as requested by the api
        """
        poly = mapping(poly)['coordinates'][0]
        return ':'.join([','.join(map(str, point)) for point in poly])

    @staticmethod
    def poly_from_string(poly_string: str) -> Polygon:
        """
        Convert from string to Polygon
        """
        poly = [
            [float(coord) for coord in point.split(',', 2)]
            for point in poly_string.split(':')
        ]
        return Polygon(poly)

    @staticmethod
    def subdivide_poly(poly: Polygon) -> list:
        """
        Divide the polygon into 4 quadrants, along the median axis
        """
        log.info('Dividing poly: {}'.format(poly))
        print('Dividing poly: {}'.format(poly))
        minx, miny, maxx, maxy = poly.bounds
        yline = LineString(
                [(minx, (miny + maxy) / 2), (maxx, (miny + maxy) / 2)])
        xline = LineString(
                [((minx + maxx) / 2, miny), ((minx + maxx) / 2, maxy)])
        lines = [xline, yline, poly.boundary]
        border_lines = ops.unary_union(lines)
        return ops.polygonize(border_lines)
