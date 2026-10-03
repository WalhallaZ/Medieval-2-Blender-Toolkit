
from pathlib import Path
import json, os, re, bpy

script_folder = Path(__file__).parent


#   -------------  #
#   Path handling  #
#   -------------  #

# Nothing may assume a path ends in a separator, and nothing may assume the
# separator is a backslash. A path the user typed by hand into one of the Paths
# fields has whatever they typed - the file browser appends a trailing one, the
# keyboard does not - and directories.json travels between Windows and Linux, so
# an entry saved on one is read on the other. The three places that used to
# assume otherwise all misbehaved: the mod dropdown split on a literal backslash
# and raised IndexError on every Linux path, the IWTE task writers joined folder
# to file name with plain + and produced ".../IWTEiwte_tasks/...", and they cut
# a fixed number of characters off the data folder to get the mod folder.
SEPARATORS = ('\\', '/')


def cleanDirectory(path):
    """A directory path with the quotes and stray whitespace taken off. Kept
    separate from normpath so a path meant for a Windows-only tool is not
    rewritten with forward slashes when Blender is running on Linux."""
    return (path or '').strip().strip('"').strip("'")


def pathParts(path):
    """Components of a path, splitting on BOTH separators and ignoring a
    trailing one. os.path only knows the separators of the platform it is
    running on, and these paths cross platforms in directories.json."""
    return [part for part in re.split(r'[\\/]+', cleanDirectory(path)) if part]


def withTrailingSep(path):
    """A directory path that definitely ends in a separator, in the style the
    path is already written in. IWTE's task files want their directories that
    way, and that is where the values below end up."""
    path = cleanDirectory(path)
    if not path or path.endswith(SEPARATORS):
        return path
    # the separator the path is already written in, so a forward-slash path is
    # not finished off with a backslash just because this is Windows
    if '\\' in path:
        return path + '\\'
    if '/' in path:
        return path + '/'
    return path + os.sep


def modFolderName(data_folder):
    """Mod folder name for a path pointing at that mod's data folder - the
    label the Mod dropdown shows."""
    parts = pathParts(data_folder)
    if len(parts) > 1:
        return parts[-2]
    return parts[-1] if parts else cleanDirectory(data_folder)


def modRoot(data_folder):
    """The mod folder holding a data folder, with a trailing separator - what
    IWTE task files want as <mod_directory_in>. Sliced at the last separator
    rather than rebuilt from the parts so a leading separator or a drive letter
    survives, and so the path keeps the separator style it arrived in."""
    path = cleanDirectory(data_folder).rstrip('\\/')
    cut = max(path.rfind('\\'), path.rfind('/'))
    if cut < 0:
        return withTrailingSep(data_folder)
    return path[:cut + 1]

DEFAULT_DIRECTORIES = {
    "directory_med2": "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Medieval II Total War",
    "directory_iwte": "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Medieval II Total War\\mods",
    "directory_mod_list": "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Medieval II Total War\\mods",
    "directory_mod_data": "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Medieval II Total War\\mods",
    "directory_models": "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Medieval II Total War\\mods",
    "directory_settlements": "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Medieval II Total War\\mods",
    "directory_unit_export": "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Medieval II Total War\\mods",
    "directory_unit_cards": "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Medieval II Total War\\mods",
    "directory_strat": "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Medieval II Total War\\mods",
    "directory_iwte_task_template": "",
    # blank means "look in the mod's own eopData\unitTypes folder"
    "directory_eop": ""
}

# directories.json is useful while the add-on is installed, but it lives under
# the add-on itself and is replaced by a fresh test install.  Blender keeps
# AddonPreferences in its user configuration, so mirror these path fields
# there as the durable copy.
PERSISTENT_DIRECTORY_KEYS = (
    "directory_med2", "directory_iwte", "directory_mod_data",
    "directory_models", "directory_settlements", "directory_unit_export",
    "directory_unit_cards", "directory_strat", "directory_iwte_task_template",
    "directory_eop",
)
_syncing_persistent_directories = False
_persistent_directories_save_pending = False

DEFAULT_MENU_SETTINGS = {
    "hide_toggle": False,
    "use_existing": False,
    "frame_toggle": False,
    "textured_toggle": False,
    "use_existing_settlement": False,
    "hide_complexes": True,
    "delete_with_item": True,
    "auto_prune_list": True,
    "auto_card_camera": True
}

# Files that ship empty since their content is generated by "Read Mod Data".
DEFAULT_DATA_FILES = {
    "directories.json": DEFAULT_DIRECTORIES,
    "menu_settings.json": DEFAULT_MENU_SETTINGS,
    "available_factions.json": {},
    "unit_dictionary.json": {},
    "model_dictionary.json": {},
    "settlement_pkgs.json": {},
    "settlement_folders.json": [],
    "attachment_dictionary.json": [],
}

def ensureDataFiles():
    text_folder = script_folder/'text'
    text_folder.mkdir(parents=True, exist_ok=True)
    for file_name, default_content in DEFAULT_DATA_FILES.items():
        file_path = text_folder/file_name
        if not file_path.exists():
            with open(file_path, 'w') as default_output:
                json.dump(default_content, default_output, indent=2)
            continue
        # A test install can leave an empty or an older paths file behind.
        # Keep the user's entries, but restore every missing default so the
        # Properties class never fails while the add-on is loading.
        if file_name not in {'directories.json', 'menu_settings.json'}:
            continue
        try:
            with open(file_path, 'r') as data_input:
                existing = json.load(data_input)
        except (OSError, ValueError):
            existing = {}
        if not isinstance(existing, dict):
            existing = {}
        repaired = dict(default_content)
        repaired.update(existing)
        if repaired != existing:
            with open(file_path, 'w') as data_output:
                json.dump(repaired, data_output, indent=2)


def _toolkitPreferences(context):
    """The add-on preferences, if Blender has registered them yet."""
    package = __package__.split('.', 1)[0]
    entry = context.preferences.addons.get(package) if context else None
    return entry.preferences if entry is not None else None


def _savePersistentDirectories():
    global _persistent_directories_save_pending
    _persistent_directories_save_pending = False
    try:
        bpy.ops.wm.save_userpref()
    except RuntimeError:
        # Blender may still be starting or shutting down. The values remain in
        # the active preferences and will be saved by Blender normally.
        pass
    return None


def _schedulePersistentDirectoriesSave():
    global _persistent_directories_save_pending
    if not _persistent_directories_save_pending:
        _persistent_directories_save_pending = True
        bpy.app.timers.register(_savePersistentDirectories, first_interval=0.25)


def persistFolderPaths(self, context):
    """Mirror a Paths-panel edit into Blender preferences immediately."""
    if _syncing_persistent_directories:
        return
    preferences = _toolkitPreferences(context)
    reader = getattr(context.scene, 'med2_toolkit_reader', None) if context else None
    if preferences is None or reader is None:
        return
    for key in PERSISTENT_DIRECTORY_KEYS:
        setattr(preferences, key, getattr(reader, key))
    _schedulePersistentDirectoriesSave()


def restorePersistentFolderPaths():
    """Restore Paths-panel values after registration, or migrate the legacy file."""
    global _syncing_persistent_directories
    context = bpy.context
    preferences = _toolkitPreferences(context)
    reader = getattr(context.scene, 'med2_toolkit_reader', None)
    if preferences is None or reader is None:
        return
    _syncing_persistent_directories = True
    try:
        for key in PERSISTENT_DIRECTORY_KEYS:
            saved = getattr(preferences, key, '')
            if saved:
                setattr(reader, key, saved)
            else:
                setattr(preferences, key, getattr(reader, key))
    finally:
        _syncing_persistent_directories = False
    _schedulePersistentDirectoriesSave()

def saveFolderPaths():
    mod_list = bpy.context.scene.med2_toolkit_reader.list_holder
    if bpy.context.scene.med2_toolkit_reader.mods_filtered != "custom":
        mod_data = bpy.context.scene.med2_toolkit_reader.mods_filtered
        temp_list = [mod for mod in mod_list.split(',') if mod]
        # the selected mod is moved to the front so it is the one restored next
        # session. It is not always in the list: an enum whose items callback
        # came back empty hands back a stale value, and list.remove raised
        # ValueError on it, which took the whole Read Mod Data down
        if mod_data in temp_list:
            temp_list.remove(mod_data)
        temp_list.insert(0, mod_data)
        mod_list = ','.join(temp_list)
    else:
        mod_data = bpy.context.scene.med2_toolkit_reader.directory_mod_data
    # start from the existing file so extra keys (last-used defaults stored
    # with storeValue) survive the rewrite
    try:
        with open(script_folder/('text/directories.json'), 'r') as directories_input:
            directories = json.load(directories_input)
    except (OSError, ValueError):
        directories = {}
    directories.update({
        "directory_med2": bpy.context.scene.med2_toolkit_reader.directory_med2,
        "directory_iwte": bpy.context.scene.med2_toolkit_reader.directory_iwte,
        "directory_mod_list": mod_list,
        "directory_mod_data": mod_data,
        "directory_models": bpy.context.scene.med2_toolkit_reader.directory_models,
        "directory_settlements": bpy.context.scene.med2_toolkit_reader.directory_settlements,
        "directory_unit_export": bpy.context.scene.med2_toolkit_reader.directory_unit_export,
        "directory_unit_cards": bpy.context.scene.med2_toolkit_reader.directory_unit_cards,
        "directory_strat": bpy.context.scene.med2_toolkit_reader.directory_strat,
        "directory_iwte_task_template": bpy.context.scene.med2_toolkit_reader.directory_iwte_task_template,
        "directory_eop": bpy.context.scene.med2_toolkit_reader.directory_eop
    })
    with open(script_folder/('text/directories.json'), 'w') as directories_output:
        json.dump(directories, directories_output, indent=2)
    return{"FINISHED"}


# Parsed text/*.json files keyed by path, invalidated by mtime. Enum item
# callbacks run on every redraw, and reparsing a big unit dictionary each
# time visibly lags the UI.
_json_cache = {}

def readJsonCached(path):
    """Parse one of the generated data JSONs, cached until the file changes.
    Returns {} when the file is missing or invalid. Callers must not mutate
    the returned object."""
    key = str(path)
    try:
        mtime = os.path.getmtime(key)
    except OSError:
        return {}
    cached = _json_cache.get(key)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    try:
        with open(key, 'r') as json_input:
            data = json.load(json_input)
    except (OSError, ValueError):
        data = {}
    _json_cache[key] = (mtime, data)
    return data


def loadStoredValue(key, default=""):
    """Read one extra value (e.g. a last-used default) from directories.json."""
    try:
        with open(script_folder/('text/directories.json'), 'r') as directories_input:
            return json.load(directories_input).get(key, default)
    except (OSError, ValueError):
        return default


def storeValue(key, value):
    """Persist one extra value into directories.json."""
    try:
        with open(script_folder/('text/directories.json'), 'r') as directories_input:
            directories = json.load(directories_input)
    except (OSError, ValueError):
        directories = {}
    directories[key] = value
    with open(script_folder/('text/directories.json'), 'w') as directories_output:
        json.dump(directories, directories_output, indent=2)


def saveSettings():
    settings = {
        "hide_toggle" : bpy.context.scene.med2_toolkit_units.hide_toggle,
        "use_existing" : bpy.context.scene.med2_toolkit_units.use_existing,
        "frame_toggle" : bpy.context.scene.med2_toolkit_units.frame_toggle,
        "textured_toggle" : bpy.context.scene.med2_toolkit_units.textured_toggle,
        "delete_with_item" : bpy.context.scene.med2_toolkit_units.delete_with_item,
        "auto_prune_list" : bpy.context.scene.med2_toolkit_units.auto_prune_list,
        "use_existing_settlement" : bpy.context.scene.med2_toolkit_settlements.use_existing_settlement,
        "hide_complexes" : bpy.context.scene.med2_toolkit_settlements.hide_complexes,
        "auto_card_camera" : bpy.context.scene.med2_toolkit_cards.auto_card_camera
    }
    with open(script_folder/('text/menu_settings.json'), 'w') as settings_output:
        json.dump(settings, settings_output, indent=2)
    return{"FINISHED"}
