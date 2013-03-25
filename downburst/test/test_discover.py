from .. import discover

CSV = """\
precise	server	release	20130222	armhf	server/releases/precise/release-20130222/ubuntu-12.04-server-cloudimg-armhf.tar.gz	ubuntu-precise-12.04-armhf-server-20130222
precise	server	release	20130222	i386	server/releases/precise/release-20130222/ubuntu-12.04-server-cloudimg-i386.tar.gz	ubuntu-precise-12.04-i386-server-20130222
precise	server	release	20130222	amd64	server/releases/precise/release-20130222/ubuntu-12.04-server-cloudimg-amd64.tar.gz	ubuntu-precise-12.04-amd64-server-20130222
"""

def test_extract():
    catalog = discover.parse(iter(CSV.splitlines()))
    PATH = (
	'server/releases/precise/release-20130222'
	+ '/ubuntu-12.04-server-cloudimg-amd64.tar.gz'
	)
    URL = 'https://cloud-images.ubuntu.com/' + PATH
    got = discover.extract(catalog, release='precise', flavor='server')
    assert got is not None
    assert got == dict(
	serial='20130222',
	url=URL,
	)
