# -*- coding: utf-8 -*-

"""
.. module:: generate_mm.py
   :platform: Unix, Windows
   :synopsis: Encodes a specialization as a mindmap.

.. moduleauthor:: Mark Conway-Greenslade <momipsl@ipsl.jussieu.fr>


"""
import collections
import json
import os

import xml.etree.ElementTree as ET

from utils_constants import *
from utils_model import PropertySpecialization
from utils_model import TopicSpecialization
from utils_parser import SpecializationParser


# HTML snippet for a set of notes.
_NOTES_HTML = """
<html>
  <head></head>
  <body>
    <dl>
        {}
    </dl>
  </body>
</html>
"""

# HTML snippet for a note.
_NOTE_HTML = "<dt><b>{}</b></dt><dd>{}</dd>"

# Mind-map sections.
_SECTIONS = collections.OrderedDict()
_SECTIONS[TYPE_KEY_ENUM_CHOICE] = None
_SECTIONS[TYPE_KEY_GRID] = "science.topic"
_SECTIONS[TYPE_KEY_KEYPROPS] = "science.topic"
_SECTIONS[TYPE_KEY_PROCESS] = "science.topic"
_SECTIONS[TYPE_KEY_PROPERTY] = None
_SECTIONS[TYPE_KEY_PROPERTY_SET] = None
_SECTIONS[TYPE_KEY_REALM] = "science.realm"
_SECTIONS[TYPE_KEY_SUBPROCESS] = "science.topic"


class _Configuration(object):
    """Wraps access to configuration information stored in associated config file.

    """
    def __init__(self):
        """Instance constructor.

        """
        self._data = _CONFIG


    def get_section(self, key):
        """Returns a section within the config file.

        """
        return self._data.get(key, {})


class Generator(SpecializationParser):
    """Specialization to mindmap generator.

    """
    def __init__(self, project, root):
        """Instance constructor.

        """
        super(Generator, self).__init__(project, root)

        self.cfg = _Configuration()
        self.mmap = None
        self.nodes = {}


    def get_output(self):
        """Returns generated output as a text blob.

        """
        return ET.tostring(self.mmap)


    def on_root_parse(self, root):
        """On root parse event handler.

        """
        self.mmap = ET.Element('map', {})
        self._emit_node(self.mmap, root, style="fork")
        self._emit_change_history(root)
        self._emit_legend(root)


    def on_grid_parse(self, grid):
        """On grid parse event handler.

        """
        self._emit_node(self.root, grid)


    def on_keyprops_parse(self, key_props):
        """On key-properties parse event handler.

        """
        self._emit_node(self.root, key_props)


    def on_process_parse(self, process):
        """On process parse event handler.

        """
        self._emit_node(self.root, process)
        self._emit_notes(process)


    def on_subprocess_parse(self, subprocess):
        """On sub-process parse event handler.

        """
        self._emit_node(subprocess.parent, subprocess)


    def on_property_set_parse(self, prop_set):
        """On property set parse event handler.

        """
        if prop_set.are_cim_properties:
            return

        self._emit_node(prop_set.owner, prop_set)


    def on_property_parse(self, prop):
        """On property parse event handler.

        """
        if prop.was_injected:
            return

        self._emit_node(prop.owner, prop)
        self._emit_notes(prop)


    def on_enum_choice_parse(self, choice):
        """On enum property parse event handler.

        """
        self._emit_node(choice.enum.detail, choice, text=choice.value)


    def _emit_node(self, parent, owner, text=None, style="bubble"):
        """Sets a mindmap node.

        """
        # Get section style config.
        cfg = self.cfg.get_section(owner.type_key)

        # Initialise mindmap node attributes.
        atts = {
            'FOLDED': str(cfg['is-collapsed']).lower(),
            'COLOR': cfg['font-color'],
            'BACKGROUND_COLOR': cfg['bg-color'],
            'STYLE': style,
            'TEXT': text if text else owner.name
        }

        # Set node url.
        try:
            owner.url
        except AttributeError:
            pass
        else:
            atts['LINK'] = owner.url

        # Get node parent.
        if not isinstance(parent, ET.Element):
            parent = self.nodes[parent]

        # Create new node & cache.
        self.nodes[owner] = ET.SubElement(parent, 'node', atts)

        # Set node font / notes.
        self._emit_font(owner, cfg)
        self._emit_notes(owner)


    def _emit_font(self, owner, cfg):
        """Set node font information.

        """
        ET.SubElement(self.nodes[owner], 'font', {
            'BOLD': str(cfg['font-bold']),
            'NAME': cfg['font-name'],
            'SIZE': str(cfg['font-size'])
            })


    def _emit_notes(self, owner, notes=None):
        """Set mindmap notes.

        """
        # Set parent mm node.
        parent = owner if isinstance(owner, ET.Element) else \
                 self.nodes[owner]

        # Set notes.
        notes = notes or _get_notes(owner)

        # Convert to HTML.
        html = []
        for k, value in notes:
            try:
                owner.id
            except AttributeError:
                pass
            else:
                value = value(owner)
            html.append(_NOTE_HTML.format(k, value))
        html = _NOTES_HTML.format("".join(html))

        # Extend mindmap.
        node = ET.SubElement(parent, 'richcontent', {"TYPE": "NOTE"})
        node.append(ET.fromstring(html))


    def _emit_legend(self, root):
        """Emits mindmap legend.

        """
        cfg = self.cfg.get_section
        root_node = ET.SubElement(self.nodes[root], 'node', {
            'FOLDED': "true",
            'STYLE': "bubble",
            'TEXT': "LEGEND",
            'POSITION': "left"
            })
        for section in _SECTIONS:
            node = ET.SubElement(root_node, 'node', {
                'BACKGROUND_COLOR': cfg(section)['bg-color'],
                'COLOR': cfg(section)['font-color'],
                'STYLE': "bubble",
                'TEXT': section
                })
            self._emit_notes(node, notes=[
                ('Description', cfg(section)['description']),
                ])


    def _emit_change_history(self, root):
        """Emits change history.

        """
        root_node = ET.SubElement(self.nodes[root], 'node', {
            'FOLDED': "true",
            'STYLE': "bubble",
            'TEXT': "CHANGE HISTORY",
            'POSITION': "left"
            })
        for version, date, person, comment in root.change_history:
            node = ET.SubElement(root_node, 'node', {
                'STYLE': "bubble",
                'TEXT': version
                })
            self._emit_notes(node, [
                ("Version", version),
                ("Date", date),
                ("Person", person),
                ("Comment", comment),
            ])


def _get_notes(spec):
    """Returns notes to be appended to a mindmap node.

    """
    result = [
        ("Description", lambda i: "N/A" if i.description is None else i.description.replace("&", "and")),
        ("Spec. ID", lambda i: i.id),
    ]

    if isinstance(spec, PropertySpecialization):
        result += [
            ("Type", lambda i: i.typeof),
            ("Cardinality", lambda i: i.cardinality),
            ("Specialization ID", lambda i: i.id)
        ]

    elif isinstance(spec, TopicSpecialization) and spec.parent is None:
        result += [
            ("Contact", lambda i: i.contact),
            ("Authors", lambda i: i.authors),
            ("Contributors", lambda i: i.contributors)
        ]

    return result

# Mindmap configuration.
_CONFIG = {
	"model": {
		"bg-color": "#F5A9BC",
		"font-bold": True,
		"font-color": "#000000",
		"font-name": "courier",
		"font-size": 14,
		"is-collapsed": False,
		"description": "A model component."
	},
	"realm": {
		"bg-color": "#66cc00",
		"font-bold": True,
		"font-color": "#000000",
		"font-name": "courier",
		"font-size": 14,
		"is-collapsed": False,
		"description": "Scientific area of a numerical model."
	},
	"grid": {
		"bg-color": "#ccccff",
		"font-bold": True,
		"font-color": "#000000",
		"font-name": "courier",
		"font-size": 12,
		"is-collapsed": False,
		"description": "The grid used to layout the variables (e.g. the Global ENDGAME-grid)."
	},
	"keyprops": {
		"bg-color": "#ffff66",
		"font-bold": True,
		"font-color": "#000000",
		"font-name": "courier",
		"font-size": 12,
		"is-collapsed": False,
		"description": "Realm key properties which differ from model defaults (grid, timestep etc)."
	},
	"process": {
		"bg-color": "#FFFFFF",
		"font-bold": True,
		"font-color": "#000000",
		"font-name": "courier",
		"font-size": 12,
		"is-collapsed": False,
		"description": "Process simulated within the realm."
	},
	"subprocess": {
		"bg-color": "#ACF0F2",
		"font-bold": True,
		"font-color": "#000000",
		"font-name": "courier",
		"font-size": 12,
		"is-collapsed": False,
		"description": "A sub-process simulated within a realm process."
	},
	"property-set": {
		"bg-color": "#F3FFE2",
		"font-bold": True,
		"font-color": "#000000",
		"font-name": "courier",
		"font-size": 10,
		"is-collapsed": True,
		"description": "Provides details of specific properties of a process, sub-process, key properties, etc.  There are two possible specialisations expected: (1) A detail_vocabulary is identified, and a cardinality is assigned to that for possible responses; (2) Detail is used to provide a collection or a set of properties which are defined in the sub-class."
	},
	"property": {
		"bg-color": "#C9D787",
		"font-bold": True,
		"font-color": "#000000",
		"font-name": "courier",
		"font-size": 10,
		"is-collapsed": True,
		"description": "A property associated with a detail defined as a 4 member tuple: name, type, cardinality, description."
	},
	"enum-choice": {
		"bg-color": "#FFFFFF",
		"font-bold": True,
		"font-color": "#000000",
		"font-name": "courier",
		"font-size": 10,
		"is-collapsed": True,
		"description": "A choice within an enumeration."
	}
}
