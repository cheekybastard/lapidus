from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.template.defaultfilters import slugify

from lapidus.metrics.models import Project, Metric, Unit, CountObservation, RatioObservation, UNIT_TYPES, CATEGORIES, PERIODS

import datetime
import json
from urlparse import urlsplit, urlunsplit
from urllib import urlencode
from urllib2 import urlopen

import logging
# Get an instance of a logger
logger = logging.getLogger(__name__)

FACEBOOK_GRAPH_URL = 'https://graph.facebook.com/'

FACEBOOK_METRIC = {
    "name": "Facebook Shares",
    "metric": "shares",
    "type": "count",
    "cumulative": True
}


# TODO formalize the unit name, etc.

class Command(BaseCommand):
    help = """Load Facebook data for website projects."""
    
    def handle(self, *args, **options):
        verbosity = int(options.get('verbosity'))

        projects = Project.objects.filter(url__isnull=False).exclude(url__exact='')
        (unit, unit_created) = Unit.objects.get_or_create(
            name=FACEBOOK_METRIC["name"],
            slug=slugify(FACEBOOK_METRIC["name"]),
            category=1,
            period=6
        )
        observation_class = unit.observation_type.model_class()
        if verbosity >= 2:
            self.stdout.write('\nloadfacebook got {projects}\n'.format(projects=repr(projects)))
        proj_by_fbid = {}
        # make a dict of projects by Facebook-friendly url/id.
        for p in projects:
            spliturl = urlsplit(p.url)
            cleanpath = '' if spliturl.path.strip('/') == '' else spliturl.path
            fbid = urlunsplit( (spliturl.scheme, spliturl.netloc, cleanpath, spliturl.query, spliturl.fragment) )
            proj_by_fbid[fbid] = p
        # Make a single request for all of the data points
        # url_str = ','.join([key for key in proj_by_fbid.iterkeys()])
        url_list = ','.join(['"{0}"'.format(proj.url) for proj in projects])
        fql_query = 'SELECT url, normalized_url, total_count  FROM link_stat WHERE url IN ({0})'.format(url_list)
        if verbosity >= 2:
            self.stdout.write('fql_query: {fql_query}\n'.format(fql_query=fql_query))
        params = urlencode({'q': fql_query})
        fp = urlopen("{base_url}fql/?{params}".format(base_url=FACEBOOK_GRAPH_URL, params=params))
        results = json.load(fp)
        # Process results back out to their respective projects
        for result in results['data']:
            # result = results[res_key]
            proj = projects.get(url=result['url'])
            (metric, metric_created) = Metric.objects.get_or_create(unit=unit, project=proj, is_cumulative=FACEBOOK_METRIC["cumulative"])
            if result.get('total_count'):
                (observation, observation_created) = observation_class.objects.get_or_create(    metric=metric, 
                                                    from_datetime=datetime.datetime.now(), 
                                                    to_datetime=datetime.datetime.now(),
                                                    value=result['total_count']
                                                )
                self.stdout.write("{project}'s {unit} for {datetime}: {obs}\n".format(
                    project=proj.name,
                    unit=unit.name,
                    datetime=observation.from_datetime,
                    obs=repr(observation)
                ))
        