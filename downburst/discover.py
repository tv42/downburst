import csv
import requests
import urllib
import urlparse


BASE_URL = 'https://cloud-images.ubuntu.com/'


def extract(catalog, release, flavor):
    for row in catalog:
        if row['release'] != release:
            continue
        if row['flavor'] != flavor:
            continue
        # TODO don't hardcode
        if row['arch'] != 'amd64':
            continue
        return dict(
            serial=row['serial'],
            url=urlparse.urljoin(BASE_URL, row['path']),
            )


def parse(lines):
    return csv.DictReader(
        lines,
        dialect='excel-tab',
        fieldnames=[
            'release',
            'flavor',
            'stability',
            'serial',
            'arch',
            'path',
            'name',
            ],
        )


def fetch(release, flavor):
    url = urlparse.urljoin(BASE_URL, 'query/')
    url = urlparse.urljoin(url, urllib.quote(release, safe='')+'/')
    url = urlparse.urljoin(url, urllib.quote(flavor, safe='')+'/')

    stability = 'released'
    if flavor == 'desktop':
        stability = 'daily'
    url = urlparse.urljoin(
        url,
        urllib.quote(
            '{stability}-dl.current.txt'.format(
                stability=stability,
                ),
            safe='',
            ),
        )

    r = requests.get(url, stream=True)
    r.raise_for_status()
    return r.iter_lines()


def get(release, flavor):
    lines = fetch(release=release, flavor=flavor)
    catalog = parse(lines)
    return extract(catalog, release=release, flavor=flavor)
