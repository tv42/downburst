import libvirt
import logging
import os.path

from lxml import etree

from . import dehumanize
from . import image
from . import iso
from . import exc
from . import meta
from . import template
from . import wait


log = logging.getLogger(__name__)


RELEASE_ALIASES = {
    '12.04': 'precise',
    '12.10': 'quantal',
    '13.04': 'raring',
    '13.10': 'saucy',
    '14.04': 'trusty',
    }


def create(args):
    args.release = RELEASE_ALIASES.get(args.release, args.release)

    log.debug('Connecting to libvirt...')
    conn = libvirt.open(args.connect)
    if conn is None:
        raise exc.LibvirtConnectionError()

    # check if the vm exists already, complain if so. this would
    # normally use conn.lookupByName, but that logs on all errors;
    # avoid the noise.
    if args.name in conn.listDefinedDomains():
        raise exc.VMExistsError(args.name)

    log.debug('Opening libvirt pool...')
    pool = conn.storagePoolLookupByName('default')

    vol = image.ensure_cloud_image(
        conn=conn,
        release=args.release,
        flavor=args.flavor,
        )

    meta_data = meta.gen_meta(
        name=args.name,
        extra_meta=args.meta_data,
        )
    user_data = meta.gen_user(
        name=args.name,
        extra_user=args.user_data,
        )

    if args.wait:
        user_data.append("""\
#!/bin/sh
# eject the cdrom (containing the cloud-init metadata)
# as a signal that we've reached full functionality;
# this is used by ``downburst create --wait``
exec eject /dev/cdrom
""")

    capacity = meta_data.get('downburst', {}).get('disk-size', '10G')
    capacity = dehumanize.parse(capacity)

    clonexml = template.volume_clone(
        name='{name}.img'.format(name=args.name),
        parent_vol=vol,
        capacity=capacity,
        )
    clone = pool.createXML(etree.tostring(clonexml), flags=0)

    iso_vol = iso.create_meta_iso(
        pool=pool,
        name=args.name,
        meta_data=meta_data,
        user_data=user_data,
        )

    ram = meta_data.get('downburst', {}).get('ram')
    ram = dehumanize.parse(ram)
    cpus = meta_data.get('downburst', {}).get('cpus')
    networks = meta_data.get('downburst', {}).get('networks')
    domainxml = template.domain(
        name=args.name,
        disk_key=clone.key(),
        iso_key=iso_vol.key(),
        ram=ram,
        cpus=cpus,
        networks=networks,
        )

    disk_name = vol.name()
    base, ext = os.path.splitext(disk_name)
    floppy_name = base +  '-floppy' + ext
    vol = pool.storageVolLookupByName(floppy_name)
    template.add_shared_floppy(domainxml, floppy_key=vol.key())
    template.boot_from(domainxml, 'fd')
    dom = conn.defineXML(etree.tostring(domainxml))
    dom.create()

    if args.wait:
        log.debug('Waiting for vm to be initialized...')
        wait.wait_for_cdrom_eject(dom)


def make(parser):
    """
    Create an Ubuntu Cloud Image vm
    """
    parser.add_argument(
        '--release',
        help='release of Ubuntu: for example, "quantal" or "precise"',
        )
    parser.add_argument(
        '--flavor',
        choices=['server', 'desktop'],
        help='flavor of Ubuntu: "server" or "desktop"',
        )
    parser.add_argument(
        '--user-data',
        metavar='FILE',
        action='append',
        help='extra user-data, a cloud-config-archive or arbitrary file',
        )
    parser.add_argument(
        '--meta-data',
        metavar='FILE',
        action='append',
        help='extra meta-data, must contain a yaml mapping',
        )
    parser.add_argument(
        '--wait',
        action='store_true',
        help='wait for VM to initialize',
        )
    parser.add_argument(
        'name',
        metavar='NAME',
        help='unique name to give to the vm',
        # TODO check valid syntax for hostname
        )
    parser.set_defaults(
        func=create,
        release="quantal",
        flavor="server",
        user_data=[],
        meta_data=[],
        )
