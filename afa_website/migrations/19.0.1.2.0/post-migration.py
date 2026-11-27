from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools.misc import file_path

HEADER_VIEWS = ('header_brand_desktop', 'header_brand_mobile')


def _header_archs():
    tree = etree.parse(file_path('afa_website/views/branding.xml'))
    archs = {}
    for template in tree.getroot().iter('template'):
        name = template.get('id')
        if name not in HEADER_VIEWS:
            continue
        arch = etree.Element('data')
        for key, value in template.attrib.items():
            if key != 'id':
                arch.set(key, value)
        for child in template:
            arch.append(child)
        archs[name] = etree.tostring(arch, encoding='unicode')
    return archs


def migrate(cr, version):
    # Header views are noupdate records, so the XML loader skips them on
    # upgrade. Replay the new architecture through the loader write path to
    # also refresh any unmodified website-specific copies.
    env = api.Environment(cr, SUPERUSER_ID, {})
    for name, arch in _header_archs().items():
        view = env.ref('afa_website.' + name, raise_if_not_found=False)
        if view:
            view._load_records_write({'arch': arch})
