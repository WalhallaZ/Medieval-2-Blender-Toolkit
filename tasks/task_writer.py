import os
import bpy
import subprocess
import json
import re
from pathlib import Path

from ..directories import modRoot, withTrailingSep
from .iwte_run import NO_WINE, findIWTEExe, waitForTaskProcess, winePath, wineWrap

# Task files the toolkit writes for IWTE, all of them in IWTE's own iwte_tasks
# folder. Built with os.path.join rather than by adding strings: the Paths
# fields hold whatever the user typed, and a folder typed without its trailing
# separator used to give "...\IWTEiwte_tasks\toolkit_bmdb_task.txt" and a
# FileNotFoundError on every import.
TASK_FOLDER = 'iwte_tasks'
MODEL_DICTIONARY = Path(__file__).parent.parent / 'text' / 'model_dictionary.json'
TEXT_MODEL_FILE = 'descr_model_battle.txt'
BINARY_MODEL_FILE = os.path.join('unit_models', 'battle_models.modeldb')
MODELDB_TASK = 'toolkit_bmdb_task.txt'
DIRECT_MESH_TASK_LIST = 'toolkit_mesh_tasks_list.txt'


def taskPath(iwte_path, task_name):
    return os.path.join(bpy.path.abspath(iwte_path), TASK_FOLDER, task_name)


def modDataDirectory():
    """The selected mod's data folder, normalized the same way as Blender."""
    reader = bpy.context.scene.med2_toolkit_reader
    selected = reader.mods_filtered if reader.mods_filtered != 'custom' else reader.directory_mod_data
    return bpy.path.abspath(selected)


def usesTextModelSource():
    """Whether meshes must be read from descr_model_battle rather than BMDB."""
    data_dir = modDataDirectory()
    return (os.path.isfile(os.path.join(data_dir, TEXT_MODEL_FILE)) and
            not os.path.isfile(os.path.join(data_dir, BINARY_MODEL_FILE)))


def _directMeshTaskName(model_name):
    safe_name = re.sub(r'[^A-Za-z0-9_.-]+', '_', model_name)
    return 'toolkit_mesh_%s_task.txt' % safe_name


def _modelInfo(model_name):
    with open(MODEL_DICTIONARY, 'r') as model_input:
        return json.load(model_input)[model_name]


def _writeDirectMeshTask(model_name):
    """Write one IWTE mesh_to_extract task from the text model dictionary."""
    model = _modelInfo(model_name)
    data_dir = modDataDirectory()
    mesh_name = model['Mesh'].replace('.glb', '.mesh')
    mesh_path = os.path.join(data_dir, model['Folder'], mesh_name)
    double_texture = any(len(textures) == 4 for textures in model['Textures'].values())
    task_name = _directMeshTaskName(model_name)
    task_file = taskPath(bpy.context.scene.med2_toolkit_reader.directory_iwte, task_name)
    with open(task_file, 'w') as task_file_output:
        task_file_output.writelines([
            '<task_id>                                  mesh_to_extract\n',
            '<mesh_file_full_path_in>                   "'+winePath(mesh_path)+'"\n',
            '<mesh_type>                                unit\n',
            '<mesh_double_texture>                      '+('yes' if double_texture else 'no')+'\n',
            '<cas_file_types_in_list>\n',
            '<directory_out>                            "'+winePath(withTrailingSep(bpy.context.scene.med2_toolkit_reader.directory_models))+'"\n',
            '<extract_file_name_out>                    '+model['Mesh']+'\n',
            '<create_text_file>                         no\n',
            '<create_task_file_from_input>              no\n',
        ])
    return task_name


def modDirectory():
    """The mod folder for <mod_directory_in>, with its trailing separator.

    The Paths panel holds the mod's DATA folder either way round - the dropdown
    stores it without a trailing separator, the Manual Path field with one if it
    was browsed to and without one if it was typed - so the last component is
    dropped rather than a fixed number of characters cut off the end. The old
    code cut four or five depending on which field it read, which left the
    settlement task pointing at "...\\mymod\\d" whenever the path did end in a
    separator, and at the mod's data folder rather than the mod when it did not.
    """
    reader = bpy.context.scene.med2_toolkit_reader
    if reader.mods_filtered != "custom":
        return modRoot(reader.mods_filtered)
    return modRoot(reader.directory_mod_data)


def startTask(iwte_path, task_name):
    """Hand one task file to IWTE and return the running process.

    The executable carries its version in its name, so it is matched by prefix
    rather than globbed onto the folder path. Off Windows this goes through
    Wine, and the task file has to be named by its Windows path - IWTE reads a
    POSIX one as relative to its own folder.

    Split out of runTask so a modal operator can watch the conversion from its
    own timer and keep Blender responsive, rather than holding the UI for as
    long as IWTE takes."""
    iwte_dir = bpy.path.abspath(iwte_path)
    iwte_exe = findIWTEExe(iwte_dir)
    if not iwte_exe:
        raise FileNotFoundError('No IWTE executable found in %s' % iwte_dir)
    command = wineWrap([iwte_exe, "--uh", "--st", winePath(taskPath(iwte_path, task_name))])
    if not command:
        raise FileNotFoundError(NO_WINE % "IWTE")
    return subprocess.Popen(command, cwd = iwte_dir)


def runTask(iwte_path, task_name):
    """startTask, waited on. Returns True if IWTE finished by itself; on False
    it is still going and the caller should say which models did not appear."""
    return waitForTaskProcess(startTask(iwte_path, task_name), task_name)


def appendToTask(iwte_path, task_name, entry):
    task_file_path = taskPath(iwte_path, task_name)
    with open(task_file_path, 'r') as task_file:
        lines = task_file.readlines()
    with open(task_file_path, 'a') as task_file:
        if not entry in lines:
            task_file.write('\n'+entry)

#########################
######### Units #########
#########################

def unitTaskWriter():
    iwte_path = bpy.context.scene.med2_toolkit_reader.directory_iwte
    if usesTextModelSource():
        with open(taskPath(iwte_path, DIRECT_MESH_TASK_LIST), 'w') as task_file:
            task_file.writelines([
                '<task_id>                                  multi_list\n',
                '<task_list>\n',
            ])
        return
    vanilla_path = winePath(withTrailingSep(bpy.context.scene.med2_toolkit_reader.directory_med2))
    mod_path = winePath(modDirectory())
    output_path = winePath(withTrailingSep(bpy.context.scene.med2_toolkit_reader.directory_models))
    primary_secondary = bpy.context.scene.med2_toolkit_units.primary_secondary
    with open(taskPath(iwte_path, MODELDB_TASK), 'w') as task_file:
        task_file.writelines([
            '<task_id>                                  modeldb_mesh_to_extract''\n'
            '<mod_directory_in>                         "'+mod_path+'"\n'
            '<m2_directory_in>                          "'+vanilla_path+'"\n'
            '<directory_out>                            "'+output_path+'"\n'
            '<primary_or_secondary>                     '+primary_secondary+'\n'
            '<create_text_file>                         no\n'
            '\n'
            '<modeldb_type_name_list>'
            ])

def unitTaskAppend(unit):
    iwte_path = bpy.context.scene.med2_toolkit_reader.directory_iwte
    if usesTextModelSource():
        task_name = _writeDirectMeshTask(unit)
        appendToTask(iwte_path, DIRECT_MESH_TASK_LIST, '"'+winePath(taskPath(iwte_path, task_name))+'"')
        return
    appendToTask(iwte_path, MODELDB_TASK, unit)

def unitTaskRun():
    task_name = DIRECT_MESH_TASK_LIST if usesTextModelSource() else MODELDB_TASK
    return runTask(bpy.context.scene.med2_toolkit_reader.directory_iwte, task_name)

#########################
######## Engines ########
#########################

def engineTaskWriter():
    vanilla_path = winePath(withTrailingSep(bpy.context.scene.med2_toolkit_reader.directory_med2))
    mod_path = winePath(modDirectory())
    iwte_path = bpy.context.scene.med2_toolkit_reader.directory_iwte
    output_path = winePath(withTrailingSep(bpy.context.scene.med2_toolkit_reader.directory_models))
    with open(taskPath(iwte_path, 'toolkit_engine_task.txt'), 'w') as task_file:
        task_file.writelines([
            '<task_id>                                  m2_engines_to_extract''\n'
            '<mod_directory_in>                         "'+mod_path+'"\n'
            '<m2_directory_in>                          "'+vanilla_path+'"\n'
            '<directory_out>                            "'+output_path+'"\n'
            '<extract_file_type>                        '+'glb'+'\n'
            '\n'
            '<engine_name_list>'
            ])

def engineTaskAppend(engine):
    appendToTask(bpy.context.scene.med2_toolkit_reader.directory_iwte, 'toolkit_engine_task.txt', engine)

def engineTaskRun():
    return runTask(bpy.context.scene.med2_toolkit_reader.directory_iwte, 'toolkit_engine_task.txt')

#########################
###### Settlements ######
#########################

def settlementTaskWriter():
    vanilla_path = winePath(withTrailingSep(bpy.context.scene.med2_toolkit_reader.directory_med2))
    mod_path = winePath(modDirectory())
    iwte_path = bpy.context.scene.med2_toolkit_reader.directory_iwte
    output_path = winePath(withTrailingSep(bpy.context.scene.med2_toolkit_reader.directory_settlements))
    with open(taskPath(iwte_path, 'toolkit_settlement_task.txt'), 'w') as task_file:
        task_file.writelines([
            '<task_id>                                  world_list_to_extract''\n'
            '<mod_directory_in>                         "'+mod_path+'"\n'
            '<m2_directory_in>                          "'+vanilla_path+'"\n'
            '<directory_out>                            "'+output_path+'"\n'
            '<extract_file_type>                        '+'glb'+'\n'
            '\n'
            '<world_name_list>'
            ])

def settlementTaskAppend(settlement):
    appendToTask(bpy.context.scene.med2_toolkit_reader.directory_iwte, 'toolkit_settlement_task.txt', settlement)

def settlementTaskRun():
    return runTask(bpy.context.scene.med2_toolkit_reader.directory_iwte, 'toolkit_settlement_task.txt')
