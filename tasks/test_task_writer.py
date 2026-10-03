"""Regression tests for direct descr_model_battle mesh conversion tasks."""

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).parent.parent


def load_task_writer(reader):
    bpy = types.ModuleType('bpy')
    bpy.path = types.SimpleNamespace(abspath=lambda path: path)
    bpy.context = types.SimpleNamespace(scene=types.SimpleNamespace(med2_toolkit_reader=reader))
    sys.modules['bpy'] = bpy

    toolkit = types.ModuleType('toolkit')
    toolkit.__path__ = [str(ROOT)]
    tasks = types.ModuleType('toolkit.tasks')
    tasks.__path__ = [str(ROOT / 'tasks')]
    sys.modules['toolkit'] = toolkit
    sys.modules['toolkit.tasks'] = tasks
    for name, path in [('directories', ROOT / 'directories.py'),
                       ('tasks.iwte_run', ROOT / 'tasks' / 'iwte_run.py'),
                       ('tasks.task_writer', ROOT / 'tasks' / 'task_writer.py')]:
        spec = importlib.util.spec_from_file_location('toolkit.' + name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    return sys.modules['toolkit.tasks.task_writer']


def load_bmdb_reader():
    toolkit = types.ModuleType('toolkit')
    toolkit.__path__ = [str(ROOT)]
    tasks = types.ModuleType('toolkit.tasks')
    tasks.__path__ = [str(ROOT / 'tasks')]
    sys.modules['toolkit'] = toolkit
    sys.modules['toolkit.tasks'] = tasks
    for name, path in [('tasks.text_io', ROOT / 'tasks' / 'text_io.py'),
                       ('tasks.bmdb_reader', ROOT / 'tasks' / 'bmdb_reader.py')]:
        spec = importlib.util.spec_from_file_location('toolkit.' + name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    return sys.modules['toolkit.tasks.bmdb_reader']


class DirectMeshTaskTests(unittest.TestCase):
    def test_dmb_parser_keeps_texture_source_paths(self):
        reader = load_bmdb_reader()
        database = reader.parseDescrModelBattle([
            'type redari_tjarlai\n',
            'mesh unit_models/slavs/redari_lod0.mesh\n',
            'texture default, unit_models/slavs/redari.texture, unit_models/slavs/redari_normal.texture\n',
            'texture_attachments default, unit_models/slavs/equipment.texture, unit_models/slavs/equipment_normal.texture\n',
        ])

        model = database['redari_tjarlai']
        self.assertEqual(model['Textures']['default'],
                         ['redari.dds', 'redari_normal.dds',
                          'equipment.dds', 'equipment_normal.dds'])
        self.assertEqual(model['TexturePaths']['default'],
                         ['unit_models/slavs/redari.texture', 'unit_models/slavs/redari_normal.texture',
                          'unit_models/slavs/equipment.texture', 'unit_models/slavs/equipment_normal.texture'])

    def test_text_model_source_writes_direct_mesh_task(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / 'mod' / 'data'
            iwte = root / 'iwte'
            output = root / 'output'
            (iwte / 'iwte_tasks').mkdir(parents=True)
            data.mkdir(parents=True)
            output.mkdir()
            (data / 'descr_model_battle.txt').write_text('type sample\n')
            dictionary = root / 'model_dictionary.json'
            dictionary.write_text(json.dumps({'redari_tjarlai': {
                'Mesh': 'redari_lod0.glb',
                'Folder': 'unit_models/slavs',
                'Textures': {'default': ['redari.dds', 'redari_normal.dds',
                                         'equipment.dds', 'equipment_normal.dds']},
                'TexturePaths': {'default': ['unit_models/slavs/redari.texture',
                                             'unit_models/slavs/redari_normal.texture',
                                             'unit_models/slavs/equipment.texture',
                                             'unit_models/slavs/equipment_normal.texture']},
            }}))
            reader = types.SimpleNamespace(mods_filtered='custom', directory_mod_data=str(data),
                                           directory_iwte=str(iwte), directory_models=str(output))
            writer = load_task_writer(reader)
            writer.MODEL_DICTIONARY = dictionary

            writer.unitTaskWriter()
            writer.unitTaskAppend('redari_tjarlai')

            task = (iwte / 'iwte_tasks' / 'toolkit_mesh_redari_tjarlai_task.txt').read_text()
            task_list = (iwte / 'iwte_tasks' / writer.DIRECT_MESH_TASK_LIST).read_text()
            texture_task_name = writer._directTextureTaskName(str(data / 'unit_models' / 'slavs'))
            texture_task = (iwte / 'iwte_tasks' / texture_task_name).read_text()
            self.assertIn('<task_id>                                  mesh_to_extract', task)
            self.assertIn('redari_lod0.mesh', task)
            self.assertIn('<mesh_double_texture>                      yes', task)
            self.assertIn('<extract_file_name_out>                    redari_lod0.glb', task)
            self.assertIn('toolkit_mesh_redari_tjarlai_task.txt', task_list)
            self.assertLess(task_list.index(texture_task_name), task_list.index('toolkit_mesh_redari_tjarlai_task.txt'))
            self.assertIn('<task_id>                                  texture_to_dds_directory', texture_task)
            self.assertIn(str(data / 'unit_models' / 'slavs'), texture_task)
            self.assertIn(str(output / 'textures'), texture_task)
            self.assertIn('<directory_out_increment>                  no', texture_task)
            log = (output / writer.IMPORT_LOG_NAME).read_text()
            self.assertIn('direct_mesh=True', log)
            self.assertIn('queued direct mesh task for model=redari_tjarlai', log)


if __name__ == '__main__':
    unittest.main()
