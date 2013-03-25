import logging
import requests
import tarfile

from lxml import etree

from . import discover
from . import template


log = logging.getLogger(__name__)


URLPREFIX = 'https://cloud-images.ubuntu.com/precise/current/'

PREFIXES = dict(
    server='{release}-server-cloudimg-amd64.',
    desktop='{release}-desktop-cloudimg-amd64.',
    )

SUFFIX = '.img'


def list_cloud_images(pool, release, flavor):
    """
    List all Ubuntu 12.04 Cloud image in the libvirt pool.
    Return the keys.
    """
    PREFIX = PREFIXES[flavor].format(release=release)
    for name in pool.listVolumes():
        log.debug('Considering image: %s', name)
        if not name.startswith(PREFIX):
            continue
        if not name.endswith(SUFFIX):
            continue
        if len(name) <= len(PREFIX) + len(SUFFIX):
            # no serial number in the middle
            continue
        # found one!
        log.debug('Saw image: %s', name)
        yield name


def find_cloud_image(pool, release, flavor):
    """
    Find an Ubuntu 12.04 Cloud image in the libvirt pool.
    Return the name.
    """
    names = list_cloud_images(pool, release=release, flavor=flavor)
    # converting into a list because max([]) raises ValueError, and we
    # really don't want to confuse that with exceptions from inside
    # the generator
    names = list(names)

    if not names:
        log.debug('No cloud images found.')
        return None

    # the build serial is zero-padded, hence alphabetically sortable;
    # max is the latest image
    return max(names)


def upload_volume(vol, fp):
    """
    Upload a volume into a libvirt pool.
    """

    stream = vol.connect().newStream(flags=0)
    vol.upload(stream=stream, offset=0, length=0, flags=0)

    def handler(stream, nbytes, _):
        data = fp.read(nbytes)
        return data
    stream.sendAll(handler, None)

    stream.finish()


def make_volume(
    pool,
    fp,
    release,
    flavor,
    serial,
    suffix,
    ):
    # volumes have no atomic completion marker; this will forever be
    # racy!
    name = '{prefix}{serial}{suffix}'.format(
        prefix=PREFIXES[flavor].format(release=release),
        serial=serial,
        suffix=suffix,
        )
    log.debug('Creating libvirt volume %s ...', name)
    volxml = template.volume(
        name=name,
        # TODO we really should feed in a capacity, but we don't know
        # what it should be.. libvirt pool refresh figures it out, but
        # that's probably expensive
        # capacity=2*1024*1024,
        )
    # TODO this fails if the image exists already, which means
    # there's no clean way to continue after errors, currently
    vol = pool.createXML(etree.tostring(volxml), flags=0)
    upload_volume(
        vol=vol,
        fp=fp,
        )
    return vol


def ensure_cloud_image(conn, release, flavor):
    """
    Ensure that the Ubuntu 12.04 Cloud image is in the libvirt pool.
    Returns the volume.
    """
    log.debug('Opening libvirt pool...')
    pool = conn.storagePoolLookupByName('default')

    log.debug('Listing cloud image in libvirt...')
    name = find_cloud_image(pool=pool, release=release, flavor=flavor)
    if name is not None:
        # all done
        log.debug('Already have cloud image: %s', name)
        vol = pool.storageVolLookupByName(name)
        return vol

    log.debug('Discovering cloud images...')
    image = discover.get(release=release, flavor=flavor)

    log.debug('Will fetch serial number: %s', image['serial'])

    url = image['url']
    log.info('Downloading image: %s', url)
    r = requests.get(url, stream=True)
    t = tarfile.open(fileobj=r.raw, mode='r|*', bufsize=1024*1024)

    # reference to the main volume of this vm template
    vol_disk1 = None
    vol_fs = None

    for ti in t:
        if not ti.isfile():
            continue
        if ti.name.startswith("README"):
            continue
        if ti.name.endswith("-root.tar.gz"):
            continue
        if ti.name.endswith("-loader"):
            continue
        if "-vmlinuz-" in ti.name:
            continue
        if "-initrd-" in ti.name:
            continue
        if ti.name.endswith("-root.tar.gz"):
            continue

        f = t.extractfile(ti)

        if ti.name.endswith("-disk1.img"):
            vol_disk1 = make_volume(
                pool=pool,
                fp=f,
                release=release,
                flavor=flavor,
                serial=image['serial'],
                suffix="-disk1.img",
                )
        elif ti.name.endswith(".img"):
            vol_fs = make_volume(
                pool=pool,
                fp=f,
                release=release,
                flavor=flavor,
                serial=image['serial'],
                suffix=".img",
                )
        elif ti.name.endswith("-floppy"):
            make_volume(
                pool=pool,
                fp=f,
                release=release,
                flavor=flavor,
                serial=image['serial'],
                suffix="-floppy.img",
                )
        else:
            log.warn("Unknown file in cloud-image tarball: %s", ti.name)
            continue

    # TODO only here to autodetect capacity
    pool.refresh(flags=0)

    # if we have the partitioned disk image, use it; it's closer to
    # the mainstream linux experience
    if vol_disk1 is not None:
        return vol_disk1
    return vol_fs
