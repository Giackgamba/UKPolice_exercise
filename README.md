# UKPolice exercise

This repo contains the source code used to download all the UK Police database.
The data comes from [https://data.police.uk/](https://data.police.uk/]).

## TLDR:
To run the pipeline execute:

    docker-compose up


Go to [http://localhost:8787](http://localhost:8787) for a progress dashboard.

Go to [http://localhost:9090](http://localhost:9090) for a simple view into the database.

## Endpoints
We can map directly the `categories` table to the `/crime-categories`
and find all the avaiable dates using the `/crimes-street-dates` endpoint.

The main entrypoint to download data is `/crimes-street` which takes as input a coordinates polygon (among other option for spatial querying) and a month, and return all the crimes in the polygon registered in that month.

Using the polygon is the only way to ensure not to get duplicate data points, but to obtain the boundaries we need to know all available neighborhoods.
We then need to query the `/forces` and then `/<force>/neighborhoods` endpoints.

Once we have a valid boundary we can query `/crimes-street` and `/outcomes-at-location` to get all the crimes and the outcomes in the area.

If an area has more than 10.000 crimes in that month an error is reported, so we need to divide the polygon and ask the data again. This is unlikely to happen, but a limit nonetheless.

The API has a 15 requests/sec limit, so it's important to limit the requests' number.

## Data


A crime object is returned by the API as:

    {
        "category": "anti-social-behaviour",
        "location_type": "Force",
        "location": {
            "latitude": "52.640961",
            "street": {
                "id": 884343,
                "name": "On or near Wharf Street North"
            },
            "longitude": "-1.126371"
        },
        "context": "",
        "outcome_status": null,
        "persistent_id": "",
        "id": 54164419,
        "location_subtype": "",
        "month": "2017-01"
    }

We can insert the requested fields in the `crime` table, but we need to ensure that the `street` `id` is already present in the `streets` table.

---
An outcome object is returned as:

    {
        "category": {
            "code": "unable-to-prosecute",
            "name": "Unable to prosecute suspect"
        },
        "date": "2017-01",
        "person_id": null,
        "crime": {
            "category": "theft-from-the-person",
            "location_type": "Force",
            "location": {
                "latitude": "52.634474",
                "street": {
                    "id": 883498,
                    "name": "On or near Kate Street"
                },
                "longitude": "-1.149197"
            },
            "context": "",
            "persistent_id": "a5a98275facee535b959b236130f5ec05205869fb3d0804c9b14296fcd0bce46",
            "id": 53566126,
            "location_subtype": "ROAD",
            "month": "2016-12"
        }
    }

Here we have to check that the `category` field is present in the `categories` table before saving the record.

## Architecture

The scripts uses  the `dask` library to parallelize the computation.
In a dask system we have a central scheduler and a number of workers, each with the whole environment loaded.

Every not trivial request and db operation is distributed by the scheduler to the workers that will execute them and report back the result.

The dask scheduler has an [interactive interface](http://localhost:8787) to show progress

The `docker-compose` file describes an architecture with a MySQL DB, a scheduler, 4 workers and a producer.
The producer launches the script that initializes the db, if necessary, and send the tasks to the scheduler, that will forward them to the workers.

There is also an `adminer` container to conveniently explore the db [via browser](http://localhost:9090).


## How to run

We can build the architecture with:

    docker-compose up

When the stack is ready, the producer will start the script.
If we want to control the producer we need to run:

    docker-compose up -d my_db adminer scheduler worker_1 worker_2 worker_3 worker_4

and then we can specifically start the producer

    docker-compose run producer

The producer has a few options:

    docker-compose run producer --help
    Usage: producer.py [OPTIONS]

    Options:
    -t, --current_date TEXT  The current date (YYYY-MM format)
    -u, --from_last_update   Only run for dates after last_update
    -l, --local              run Dask in single node mode, helpful for debugging
    --help                   Show this message and exit.

 - `-l`, `--local`: Don't send the tasks to the scheduler, everything will be run sequentially; helpful for debugging.
 - `-u`, `--from_last_update`: Only run for dates after the last update; This date is stored in a file next to the producer (`last_update.json`); to reset the last update, delete the file.
 - `-t`, `--current_date`: Run for dates until this date. The current month by default; in the format `YYYY-MM`

### TODOs:

 - Better logging
 - `api_interface.py` refactor, some things should be DRYied more
 - Connection strings and global parameters, should be passed by env variables
