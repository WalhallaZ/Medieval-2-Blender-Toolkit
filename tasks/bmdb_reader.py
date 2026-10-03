"""Read model information from ``descr_model_battle.txt``.

The importer only needs a model's first mesh and its main/attachment texture
variants. Older versions reconstructed that information from the binary
``battle_models.modeldb`` archive. Mods which ship the text description file
instead can now be read directly.
"""

import json
import os
import re
from pathlib import Path

from .text_io import readModLines


DESCR_MODEL_BATTLE = 'descr_model_battle.txt'


def _texture_name(path):
    """Turn a game ``.texture`` path into IWTE's extracted ``.dds`` name."""
    base_name = path.replace('\\', '/').rsplit('/', 1)[-1]
    return re.sub(r'\.texture$', '.dds', base_name, flags=re.IGNORECASE)


def _texture_path(path):
    """Normalize a DMB texture path without losing its source directory."""
    return path.replace('\\', '/')


def parseDescrModelBattle(lines):
    """Build the toolkit model dictionary from descr_model_battle lines.

    ``texture`` records hold the two main maps (followed by an unused sprite),
    while ``texture_attachments`` supplies the matching attachment maps. A
    model's first mesh is its LOD0 mesh, which is the one IWTE extracts.
    """
    database = {}
    current = None

    def finish_current():
        if current is None or not current['mesh']:
            return
        name = current['name']
        # Keep the old reader's collision behavior in case a hand-authored DMB
        # defines a type twice.
        if name in database:
            suffix = '___duplicate'
            number = 2
            key = name + suffix
            while key in database:
                key = '%s%s%d' % (name, suffix, number)
                number += 1
        else:
            key = name
        mesh_path = current['mesh']
        database[key] = {
            'Mesh': re.sub(r'\.mesh$', '.glb', mesh_path.rsplit('/', 1)[-1], flags=re.IGNORECASE),
            'Folder': mesh_path.rsplit('/', 1)[0] if '/' in mesh_path else '',
            'Textures': current['textures'],
            # The importer uses bare DDS names, but direct mesh extraction also
            # needs the directories that hold the original .texture files.
            'TexturePaths': current['texture_paths'],
        }

    for raw_line in lines:
        # Semicolon starts a comment in Medieval II's text files. Splitting
        # fields on commas also accepts the usual tab-aligned syntax.
        line = raw_line.split(';', 1)[0].strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        keyword, values = parts
        fields = [field.strip() for field in values.split(',')]
        keyword = keyword.lower()

        if keyword == 'type':
            finish_current()
            name = fields[0].lower() if fields else ''
            current = {'name': name, 'mesh': '', 'textures': {}, 'texture_paths': {}} if name else None
        elif current is not None and keyword == 'mesh' and fields and not current['mesh']:
            current['mesh'] = fields[0].replace('\\', '/')
        elif current is not None and keyword in ('texture', 'texture_attachments') and len(fields) >= 3:
            faction = fields[0].lower()
            textures = current['textures'].setdefault(faction, [])
            texture_paths = current['texture_paths'].setdefault(faction, [])
            textures.extend([_texture_name(fields[1]), _texture_name(fields[2])])
            texture_paths.extend([_texture_path(fields[1]), _texture_path(fields[2])])

    finish_current()
    return database


def bmdbReader(mod_folder):
    """Read ``descr_model_battle.txt`` into the importer's model dictionary."""
    path = os.path.join(mod_folder, DESCR_MODEL_BATTLE)
    try:
        database = parseDescrModelBattle(readModLines(path, 'utf-8'))
    except FileNotFoundError as error:
        return 'No descr_model_battle.txt found in the specified directory.\n%s' % error

    parent_folder = Path(__file__).parent.parent
    with open(parent_folder / 'text' / 'model_dictionary.json', 'w') as models_output:
        json.dump(database, models_output, indent=2)
    return 'Finished'
