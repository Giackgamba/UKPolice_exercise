import logging
from time import sleep

from sqlalchemy import (Column, Float, ForeignKey, Integer, String,
                        create_engine)
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

log = logging.getLogger(__name__)

logging.basicConfig()
logging.getLogger('sqlalchemy').setLevel(logging.ERROR)


class OrmUpsert():
    """
    Helper class to add an upsert-like method to the ORM Objects
    """

    def get_or_create(self, session=None):
        """
        Get a row from a database if it exists by its primary keys
        If it exists already this does nothing
        If it does not exists, it will create it, ensuring its foreign key
        constraints are satisfied
        """
        engine = create_engine("mysql://giack:password@my_db/faire")

        current_session = sessionmaker(
            bind=engine)() if not session else session

        primary_keys = self.get_primary_keys()
        instance = self.find_by_primary_keys(current_session, primary_keys)
        if not instance:
            self.ensure_foreign_keys(current_session)
            try:
                current_session.add(self)
                current_session.commit()
            except IntegrityError:
                log.debug('Dupicate keys')
                # current_session.expunge(self)
                current_session.rollback()
            current_session.flush()
        # if not session:
        #     log.debug('Im closing the connection')
        #     current_session.close()
        return instance

    def ensure_foreign_keys(self, session):
        """
        This recursively call get_or_create to ensure foreign key consistency
        """
        for field in self.__dict__.values():
            if isinstance(field, Base):
                field.get_or_create(session)

    def find_by_primary_keys(self, current_session, primary_keys):
        """
        Find a row by its primary key
        """
        return current_session.query(type(self))\
            .filter_by(**primary_keys).first()

    def get_primary_keys(self):
        """
        Detect primary keys in the table
        """
        return {k: str(v)
                for k, v in self.__dict__.items()
                if k in self.__table__.primary_key.columns.keys()}


class CrimeCategory(Base, OrmUpsert):
    __tablename__ = 'crime_categories'

    id = Column(String(50), primary_key=True)
    description = Column(String(100), nullable=False)

    def __init__(self, category):
        self.id = category['url']
        self.description = category['name']

    def __repr__(self) -> str:
        return str(self.id)


class OutcomeCategory(Base, OrmUpsert):
    __tablename__ = 'outcome_categories'

    id = Column(String(50), primary_key=True)
    description = Column(String(100))

    def __init__(self, outcome_category):
        self.id = outcome_category['code']
        self.description = outcome_category['name']

    def __repr__(self) -> str:
        return str(self.id)


class Street(Base, OrmUpsert):
    __tablename__ = 'streets'

    id = Column(Integer, primary_key=True)
    description = Column(String(100))

    def __init__(self, street):
        self.id = street['id']
        self.description = street['name']

    def __repr__(self) -> str:
        return str(self.id)


class Crime(Base, OrmUpsert):
    __tablename__ = 'crimes'

    id = Column(Integer, primary_key=True)
    category = Column(String(100),
                      ForeignKey(CrimeCategory.__table__.c.id),
                      primary_key=True)
    street = Column(Integer,
                    ForeignKey(Street.__table__.c.id)
                    )
    city = Column(String(50))
    latitude = Column(Float)
    longitude = Column(Float)
    date = Column(String(7))
    context = Column(String(100))

    def __init__(self, api_data, city):
        self.id = api_data['id']
        self.category = api_data['category']
        self.street = Street(api_data['location']['street'])
        self.city = city  # no info in the API
        self.longitude = api_data['location']['longitude']
        self.latitude = api_data['location']['latitude']
        self.date = api_data['month']
        self.context = api_data['context']

    def __repr__(self) -> str:
        return str(self.id)


class Outcome(Base, OrmUpsert):
    __tablename__ = 'outcomes'

    crime = Column(Integer,
                   ForeignKey(Crime.__table__.c.id),
                   primary_key=True,
                   unique=False)
    category = Column(String(100),
                      ForeignKey(OutcomeCategory.__table__.c.id),
                      primary_key=True)
    date = Column(String(7))
    person_id = Column(String(32))

    def __init__(self, api_data):
        self.crime = api_data['crime']
        self.category = OutcomeCategory(api_data['category'])
        self.date = api_data['date']
        self.person_id = api_data['person_id']


def init_db():
    try:
        engine = create_engine("mysql://giack:password@my_db/faire")
        Base.metadata.create_all(engine)
    except OperationalError:
        print('waiting to connect to db')
        sleep(2)
        init_db()
