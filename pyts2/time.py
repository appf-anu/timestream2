import datetime
import re
import os.path as op

import iso8601


try:
    dataclass()
except NameError:
    from dataclasses import dataclass


TS_IMAGE_DATEFMT = "%Y_%m_%d_%H_%M_%S"
TS_IMAGE_DATETIME_RE = re.compile(r"(\d{4}_[0-1]\d_[0-3]\d_[0-2]\d_[0-5]\d_[0-5]\d)(_\d+)?(_\w+)?")


def parse_date(datestr):
    '''Parses dates in iso8601-ish formats to datetime.datetime objects'''
    if isinstance(datestr, datetime.datetime):
        return datestr

    # first, try iso8601 of some form
    try:
        date = iso8601.parse_date(datestr)
        # Remove timezone since all dates are assumed to be local time
        # FIXME this is a terrible hack. we need to find a way around this
        # eventually
        return date.replace(tzinfo=None)
    except:
        pass
    # Then the usual
    try:
        return datetime.datetime.strptime(datestr, TS_IMAGE_DATEFMT)
    except:
        pass

    # Add more things here in try-excepts if we want to accept other date
    # formats

    raise ValueError("date string '" + datestr + "' doesn't match valid date formats")


@dataclass
class TSInstant:
    """
    TSInstant: a generalised "moment in time", including both timepoint and
    optional index within a timepoint.

    >>> TSInstant(datetime.datetime(2017, 01, 02, 03, 04, 05))
    2017_01_02_03_04_05_00
    >>> TSInstant(datetime.datetime(2017, 01, 02, 03, 04, 05), 0, "0011")
    2017_01_02_03_04_05_00_0011
    """
    datetime: datetime.datetime
    subsecond: int = 0
    index: str = None

    def __init__(self, datetime, subsecond=0, index=None):
        self.datetime = parse_date(datetime)
        self.subsecond = int(subsecond)
        self.index = index

    def __str__(self):
        idx = "" if self.index is None else f"_{self.index}"
        subsec = f"_{self.subsecond:02d}"
        return f"{self.datetime.strftime('%Y_%m_%d_%H_%M_%S')}{subsec}{idx}"

    def __repr__(self):
        return str(self)

    def iso8601(self):
        return self.datetime.strftime("%Y-%m-%dT%H:%M:%S")

    @staticmethod
    def from_path(path):
        """Extract date and index from path to timestream image

        :param path: File path, with or without directory
        """
        fn = op.splitext(op.basename(path))[0]
        m = TS_IMAGE_DATETIME_RE.search(fn)
        if m is None:
            raise ValueError("path '" + path + "' doesn't contain a timestream date")

        dt, subsec, index = m.groups()

        datetime = parse_date(dt)

        if subsec is not None:
            try:
                subsec = int(subsec.lstrip("_"))
            except ValueError:
                subsec = 0

        if index is not None:
            index = index.lstrip("_")
        return TSInstant(datetime, subsec, index)
