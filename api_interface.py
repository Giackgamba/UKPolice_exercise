import dask
import requests
import logging
import json
from time import sleep
from shapely import ops
from shapely.geometry import LineString, Polygon, mapping

from models import CrimeCategory, Outcome

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

    def get_boundary(self, force, area) -> list:
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

    def get_all_dates(self) -> list:
        dates = requests.get(self.base_url + '/crimes-street-dates')
        if dates.status_code != 200:
            raise Exception
        return sorted([d['date'] for d in dates.json()])

    def download_and_load_crimes(self, date: str, poly: Polygon, force: str) -> list:
        poly_string = self.poly_to_string(poly)
        outcomes = requests.post(self.base_url + '/outcomes-at-location',
                                 data={'date': date,
                                       'poly': poly_string})
        if outcomes.status_code == 503:
            polies = self.subdivide_poly(poly)
            for p in polies:
                return self.download_and_load_crimes(date, p)
        if outcomes.status_code != 200:
            print('Hitting quota limit, sleeping a sec')
            print(outcomes.url)
            sleep(1)
            return self.download_and_load_crimes(date, poly, force)

        result = list()
        for outcome in outcomes.json():
            outcome.update({'city': force})
            outcome = Outcome(outcome)
            result.append(outcome.get_or_create())
        return result

    def get_data(self, poly, dates):
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
        areas_list = list()
        forces = self.get_forces()
        for force in forces[:5]:
            print(force)
            areas = self.get_areas(force)
            for area in areas[:5]:
                print(area)
                areas_list.append(dask.delayed(self.get_boundary)(force, area))
        # Ask the boundary of each area to the API
        boundaries = dask.compute(*areas_list)

        # Create a list of requests
        outcomes_list = list()
        for date in dates[-1:]:
            log.info('Downloading data for {}'.format(date))
            print('Downloading data for {}'.format(date))

            for poly, force in boundaries:
                outcomes_list.append(dask.delayed(self.download_and_load_crimes)(date, poly, force))
            with open('last_update.json', 'w') as f:
                json.dump({'last-update': date}, f)
        # Execute the requests
        dask.compute(*outcomes_list)

        # Create a list of DB insert operations
        # insert_list = list()
        # for outcome_tuple in outcomes:
        #     for api_data in outcome_tuple:
        #         outcome = Outcome(api_data)
        #         insert_list.append(dask.delayed(outcome.get_or_create)())
        #     # Execute them
        # dask.compute(*insert_list)

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
