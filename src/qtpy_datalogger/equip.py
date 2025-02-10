"""Functions for creating, configuring, and updating QT Py sensor nodes."""

import contextlib
import datetime
import logging
import pathlib
import shutil
import subprocess
import sys
import textwrap
import urllib.request
from collections.abc import Generator
from enum import StrEnum
from typing import Any, NamedTuple

import bs4
import circup
import findimports
import packaging.version
import toml

from . import discovery

logger = logging.getLogger(__name__)

_EXIT_SUCCESS = 0
_EXIT_BOARD_LOOKUP_FAILURE = 51

_SNSR_ROOT_FOLDER = "snsr"
_SNSR_NOTICE_FILE = "notice.toml"

_HOMEPAGE_URL = "https://github.com/wireddown/qt-py-s3-daq-app/wiki"
_NEW_BUG_URL = "https://github.com/wireddown/qt-py-s3-daq-app/issues/new?template=bug-report.md"
_board_support_matrix_page = "https://docs.circuitpython.org/en/stable/shared-bindings/support_matrix.html"


_PC_ONLY_IMPORTS = [
    "typing",
]


class Behavior(StrEnum):
    """Supported installation behaviors for QT Py sensor nodes."""

    Upgrade = "Upgrade"
    Compare = "Compare"
    Describe = "Describe"
    Force = "Force"


class SnsrNotice(NamedTuple):
    """Represents the contents of the notice.toml file for a sensor_node."""

    comment: str
    version: str
    commit: str
    timestamp: datetime.datetime


class SnsrNodeBundle(NamedTuple):
    """Represents the version, contents, and dependencies for a sensor_node."""

    notice: SnsrNotice
    device_files: list[pathlib.Path]
    circuitpy_version: str
    board_id: str
    circuitpy_dependencies: list[str]
    installed_circuitpy_modules: list[tuple[str, str]]


@contextlib.contextmanager
def suppress_unless_debug() -> Generator[None, Any, None]:
    """Suppress logger.info() messages unless logging has been set to DEBUG / --verbose."""
    initial_log_level = logger.getEffectiveLevel()
    should_suppress = initial_log_level > logging.DEBUG
    try:
        if should_suppress:
            logger.setLevel(logging.WARNING)
        yield
    finally:
        logger.setLevel(initial_log_level)


def handle_equip(behavior: Behavior, root: pathlib.Path | None) -> None:
    """Handle the equip CLI command."""
    logger.debug(f"behavior: '{behavior}', root: '{root}'")

    this_file = pathlib.Path(__file__)
    this_folder = this_file.parent
    this_sensor_node_root = this_folder.joinpath("sensor_node")
    runtime_bundle = _detect_snsr_bundle(this_sensor_node_root)

    if behavior == Behavior.Describe:
        self_description = _format_bundle_description(runtime_bundle)
        _ = [logger.info(line) for line in self_description]
        raise SystemExit(_EXIT_SUCCESS)

    if not root:
        qtpy_device = discovery.discover_and_select_qtpy()
        if not qtpy_device:
            logger.error("No QT Py devices found!")
            raise SystemExit(discovery._EXIT_DISCOVERY_FAILURE)
        root = pathlib.Path(qtpy_device[discovery._INFO_KEY_drive_letter]).resolve()

    device_bundle = _detect_snsr_bundle(root)
    comparison_information = {
        "device bundle": device_bundle,
        "runtime bundle": runtime_bundle,
    }

    if behavior == Behavior.Compare:
        comparison_report = _format_bundle_comparison(comparison_information)
        _ = [logger.info(line) for line in comparison_report]
        raise SystemExit(_EXIT_SUCCESS)

    should_install, skip_reason = _should_install(behavior, comparison_information)

    if should_install:
        _equip_snsr_node(behavior, comparison_information)
    else:
        logger.info(f"Skipping installation: {skip_reason}")


def _detect_snsr_bundle(main_folder: pathlib.Path) -> SnsrNodeBundle:
    """Build and return a SnsrNodeBundle by probing the specified folder."""
    # Begin with default sentinel values
    snsr_notice = SnsrNotice(
        comment="(uninitialized)",
        version="(missing)",
        commit="(missing)",
        timestamp=datetime.datetime.fromisoformat("0001-01-01T01:01:01+00:00"),
    )
    device_files = []
    circuitpy_version = "9.2.1"
    board_id = "adafruit_qtpy_esp32s3_nopsram"
    circuitpy_dependencies = []
    installed_circuitpy_modules = []

    # Are we detecting a device or ourselves?
    this_file = pathlib.Path(__file__)
    this_folder_parent = this_file.parent
    main_folder_parent = main_folder.parent
    detecting_self = this_folder_parent == main_folder_parent

    notice_file = main_folder.joinpath(_SNSR_ROOT_FOLDER, _SNSR_NOTICE_FILE)

    detect_message = f"Probing for sensor_node at '{main_folder}'"
    if detecting_self:
        snsr_notice = _get_package_notice_info(allow_dev_version=True)
        detect_message = ""
    elif notice_file.exists():
        file_contents = notice_file.read_text()
        snsr_notice_toml = toml.loads(file_contents)
        snsr_notice = SnsrNotice(**snsr_notice_toml)

    # We only want to print information about the device, not ourselves
    should_log_info_messages = len(detect_message) > 0
    if should_log_info_messages or logger.isEnabledFor(logging.DEBUG):
        logger.info(detect_message)
        logger.info(f" - version    {snsr_notice.version}")
        logger.info(f" - timestamp  {snsr_notice.timestamp.strftime('%Y.%m.%d  %H:%M:%S')}")

    device_files = _recursive_folder_scan(main_folder)

    boot_out_file = main_folder.joinpath("boot_out.txt")
    if boot_out_file.exists():
        lines = boot_out_file.read_text().splitlines()
        logger.debug(f"Parsing '{boot_out_file}' with contents")
        _ = [logger.debug(line) for line in lines]
        circuitpy_version_line = lines[0]
        board_id_line = lines[1]
        circuitpy_version = circuitpy_version_line.split(";")[0].split(" ")[-3]
        board_id = board_id_line.split(":")[-1]

    circuitpy_dependencies = _get_circuitpython_dependencies(device_files, board_id, should_log_info_messages)
    installed_circuitpy_modules = _query_modules_from_circup(main_folder, should_log_info_messages)

    snsr_bundle = SnsrNodeBundle(
        snsr_notice,
        device_files,
        circuitpy_version,
        board_id,
        circuitpy_dependencies,
        installed_circuitpy_modules,
    )
    return snsr_bundle


def _format_bundle_description(bundle: SnsrNodeBundle) -> list[str]:
    """Format and return a list of lines that describes this package's sensor_node bundle."""
    report_contents = textwrap.dedent(
        f"""
        QT Py Data Logger Sensor Node
          Version:    {bundle.notice.version}  ({bundle.notice.commit})
          Timestamp:  {bundle.notice.timestamp.strftime("%Y.%m.%d  %H:%M:%S")}
          Homepage:   {_HOMEPAGE_URL}

        Dependencies
          CircuitPython module           PC package name
          ====================   -{"-" * 31}-
        """
    ).splitlines()
    for circuitpy_library in bundle.circuitpy_dependencies:
        library_stub = "adafruit-circuitpython-{}".format(circuitpy_library.replace("adafruit_", ""))
        report_contents.append(f"  {circuitpy_library:>19}    {library_stub:>32}")
    return report_contents


def _format_bundle_comparison(comparison_information: dict[str, SnsrNodeBundle]) -> list[str]:
    """Format and return a list of lines that compares the specified sensor_node bundles."""
    device_bundle = comparison_information["device bundle"]
    runtime_bundle = comparison_information["runtime bundle"]

    newer_mark = "(newer)"
    older_mark = "       "
    same_mark = "(same) "
    try:
        device_version = packaging.version.Version(device_bundle.notice.version)
    except packaging.version.InvalidVersion:
        device_version = packaging.version.Version("0")
    device_timestamp = device_bundle.notice.timestamp
    self_version = packaging.version.Version(runtime_bundle.notice.version)
    self_timestamp = runtime_bundle.notice.timestamp

    self_is_newer = self_version > device_version
    if self_version == device_version:
        self_is_newer = self_timestamp > device_timestamp

    device_mark = older_mark if self_is_newer else newer_mark
    self_mark = newer_mark if self_is_newer else older_mark
    if self_version == device_version and self_timestamp == device_timestamp:
        device_mark = same_mark
        self_mark = same_mark

    report_contents = textwrap.dedent(
        f"""
        Comparing sensor_node device with this package
            Trait        Device {device_mark}                     Self {self_mark}
         ===========  -{"-" * 31}-  ----------------------
          Version      {device_version!s:<31}    {self_version!s}
          Timestamp    {device_timestamp.strftime("%Y.%m.%d  %H:%M:%S"):<31}    {self_timestamp.strftime("%Y.%m.%d  %H:%M:%S")}
          CircuitPy    {device_bundle.circuitpy_version:<31}    (PC host)
          Board ID     {device_bundle.board_id:<31}    (PC host)
          Location     {device_bundle.device_files[0]!s:<31}    (builtin)
        """
    )
    return report_contents.splitlines()


def _should_install(behavior: Behavior, comparison_information: dict[str, SnsrNodeBundle]) -> tuple[bool, str]:
    """
    Use the comparison_information to decide whether to install or upgrade the sensor_node bundle.

    Returns a tuple with
    - a bool indicating whether the bundle should be installed
    - a string message explaining why the bundle should not be installed
    """
    my_bundle = comparison_information["runtime bundle"]
    device_bundle = comparison_information["device bundle"]

    my_version = packaging.version.Version(my_bundle.notice.version)
    should_install = False

    # Do the first lines from the device's code.py and our code.py match?
    device_main_folder = device_bundle.device_files[0]
    device_codepy_file = device_main_folder.joinpath("code.py")
    device_codepy_is_snsr_node = False
    if device_codepy_file.exists():
        device_first_line = device_codepy_file.read_text().splitlines()[0]
        snsr_codepy_first_line = my_bundle.device_files[0].joinpath("code.py").read_text().splitlines()[0]
        device_codepy_is_snsr_node = device_first_line == snsr_codepy_first_line

    skip_reason = ""
    if device_codepy_is_snsr_node:
        device_snsr_version = packaging.version.Version(device_bundle.notice.version)
        device_snsr_timestamp = device_bundle.notice.timestamp
        my_timestamp = my_bundle.notice.timestamp
        if my_version > device_snsr_version:
            logger.info("Upgrading version")
            logger.info(f"  Device is version  '{device_snsr_version}'")
            logger.info(f"  Runtime is version '{my_version}'")
            should_install = True
        elif my_timestamp > device_snsr_timestamp:
            logger.info("Upgrading snapshot")
            logger.info(f"  Device has timestamp  '{device_snsr_timestamp}'")
            logger.info(f"  Runtime has timestamp '{my_timestamp}'")
            should_install = True
        elif behavior == Behavior.Force:
            logger.info("Forcing installation")
            should_install = True
        else:
            skip_reason = "not an upgrade, use '--force' to override"
    else:
        logger.info("Initializing new QT Py Sensor Node")
        should_install = True

    return should_install, skip_reason


def _equip_snsr_node(behavior: Behavior, comparison_information: dict[str, SnsrNodeBundle]) -> None:
    """Install the sensor_node bundle and its CircuitPython dependencies."""
    device_bundle = comparison_information["device bundle"]
    device_main_folder = device_bundle.device_files[0]
    my_bundle = comparison_information["runtime bundle"]

    logger.info(f"Installing sensor_node v{my_bundle.notice.version} to '{device_main_folder}'")
    logger.info("  Copying snsr bundle")
    my_main_folder = my_bundle.device_files[0]
    device_snsr_root = device_main_folder.joinpath(_SNSR_ROOT_FOLDER)
    if device_snsr_root.exists():
        shutil.rmtree(device_snsr_root)
    shutil.copytree(
        src=my_main_folder,
        dst=device_main_folder,
        ignore=shutil.ignore_patterns("*.pyc", "__pycache__"),
        dirs_exist_ok=True,
    )

    notice_file = device_main_folder.joinpath(_SNSR_ROOT_FOLDER, _SNSR_NOTICE_FILE)
    notice_contents = _create_notice_file_contents(allow_dev_version=True)
    notice_file.write_text(notice_contents)

    circup_packages = my_bundle.circuitpy_dependencies
    return_code = _EXIT_SUCCESS
    if circup_packages:
        circup_install_command = [
            "circup",
            "--path",
            str(device_main_folder),
            "--board-id",
            device_bundle.board_id,
            "--cpy-version",
            device_bundle.circuitpy_version,
            "install",
            "--upgrade",
        ]
        circup_install_command.extend(circup_packages)
        logger.info("  Installing external dependencies with circup")
        logger.info(f"  Invoking '{' '.join(circup_install_command)}'")
        logger.info("")
        result = subprocess.run(circup_install_command, stdout=sys.stdout, stderr=subprocess.STDOUT, check=False)  # noqa: S603 -- command is well-formed and user cannot execute arbitrary code
        logger.info("")
        return_code = result.returncode

    if return_code == _EXIT_SUCCESS:
        logger.info("Installation complete")
    else:
        logger.error(f"circup exited with code '{return_code}'")


def _create_notice_file_contents(allow_dev_version: bool) -> str:
    """Format the notice.toml file for the package."""
    snsr_notice = _get_package_notice_info(allow_dev_version)
    file_contents = toml.dumps(snsr_notice._asdict())
    return file_contents


def _get_package_notice_info(allow_dev_version: bool) -> SnsrNotice:
    """Detect and generate the information used in the notice.toml file."""
    logger.debug("Getting notice information from notice file")

    this_file = pathlib.Path(__file__)
    this_folder = this_file.parent
    notice_toml = this_folder.joinpath("sensor_node", _SNSR_ROOT_FOLDER, _SNSR_NOTICE_FILE)
    notice_contents = toml.load(notice_toml)
    snsr_notice = SnsrNotice(**notice_contents)
    my_comment = snsr_notice.comment
    my_version = snsr_notice.version
    my_commit = snsr_notice.commit
    my_timestamp = snsr_notice.timestamp

    if __package__:
        # We're installed
        import importlib.metadata

        logger.debug("Updating version from __package__ metadata")
        my_version = importlib.metadata.version(str(__package__))

    # When we're running from the git source, we're in development mode
    this_package_parent = this_file.parent.parent
    in_dev_mode = this_package_parent.name == "src"
    if in_dev_mode:
        logger.debug("Updating notice information from development environment")
        if allow_dev_version:
            logger.debug("Including the version")
            my_version = f"{my_version}.post0.dev0"

        most_recent_commit_info = ["git", "log", "--max-count=1", "--format=%h %aI"]
        sha_with_timestamp = subprocess.check_output(most_recent_commit_info).strip()  # noqa: S603 -- command is well-formed and user cannot execute arbitrary code
        sha_and_timestamp = sha_with_timestamp.decode("UTF-8").split(" ")
        my_commit = sha_and_timestamp[0]
        my_timestamp = datetime.datetime.fromisoformat(sha_and_timestamp[1])

    my_comment = f"Generated by '{__name__}.py'"
    return SnsrNotice(my_comment, my_version, my_commit, my_timestamp)


def _get_plugins(folder_list: list[pathlib.Path]) -> list[str]:
    """Return a list of the installed sensor_node plugins."""
    main_folder = folder_list[0]
    snsr_root = main_folder.joinpath(_SNSR_ROOT_FOLDER)
    plugins = [entry for entry in folder_list if entry.is_relative_to(snsr_root) and entry.is_dir()]
    return [entry.name for entry in plugins[1:]]


def _recursive_folder_scan(main_folder: pathlib.Path) -> list[pathlib.Path]:
    """Return a sorted list of all the files and folders under the specified folder."""
    logger.debug(f"Scanning folder '{main_folder}'")

    full_list = [main_folder]
    full_list.extend(_collect_file_list(main_folder))
    return full_list


def _collect_file_list(folder: pathlib.Path) -> list[pathlib.Path]:
    """Recursively collect the files and folders under the specified folder and return a sorted list."""
    if folder.is_dir():
        folder_contents = sorted(folder.iterdir())
        subfolders = [entry for entry in folder_contents if entry.is_dir()]
        for subfolder in subfolders:
            subfolder_list = _collect_file_list(subfolder)
            folder_contents.extend(subfolder_list)
        return sorted(folder_contents)
    return [folder]


def _get_circuitpython_dependencies(device_files: list[pathlib.Path], device_id: str, log_info: bool) -> list[str]:
    """Scan the sensor_node files for Python dependencies and return a list of external module imports."""
    # Get the folder and file names under the snsr folder
    main_folder = device_files[0]
    snsr_folder = main_folder.joinpath(_SNSR_ROOT_FOLDER)
    snsr_node_listing = [entry for entry in device_files if entry.is_relative_to(snsr_folder)]
    snsr_node_folders = [entry for entry in snsr_node_listing if entry.is_dir()]
    snsr_node_files = [entry for entry in snsr_node_listing if entry.is_file() and str(entry).endswith(".py")]

    # Collect the used and unused imports from each file
    all_used_imports = []
    all_unused_imports = []
    for file in snsr_node_files:
        used_imports, unused_imports = findimports.find_imports_and_track_names(str(file))
        all_used_imports.extend(used_imports)
        all_unused_imports.extend(unused_imports)
    all_import_names = sorted({module.name for module in all_used_imports})
    _ = [logger.debug(f" * {name}") for name in all_import_names]
    all_base_imports = sorted({name.split(".", maxsplit=1)[0] for name in all_import_names} - {*_PC_ONLY_IMPORTS})
    if all_unused_imports:
        logger.warning("Detected unused imports")
        _ = [logger.warning(f" * {module.name}") for module in all_unused_imports]

    # Group the internal module names
    internal_folders = [folder.name for folder in snsr_node_folders]
    internal_files = [file.stem for file in snsr_node_files]
    internal_modules = {*internal_folders, *internal_files}
    internal_modules.discard("__init__")
    internal_modules.discard("__pycache__")

    # Group the builtin CircuitPython module names
    this_file = pathlib.Path(__file__)
    builtin_circuitpython_modules_file = this_file.with_name("builtin_circuitpython_modules.toml")
    builtin_circuitpython_modules = toml.load(builtin_circuitpython_modules_file)
    stdlib_module_names = builtin_circuitpython_modules["standard_library"]
    builtin_module_names = builtin_circuitpython_modules.get(device_id, [])
    if not builtin_module_names:
        logger.warning(f"Missing information for builtin modules on CircuitPython device '{device_id}'")
        logger.warning(f"  Visit '{_board_support_matrix_page}' and find your BOARD NAME")
        logger.warning(
            "  Then use 'qtpy-datalogger --list-builtin-modules \"BOARD NAME\" -' to get the builtin modules"
        )
        logger.warning(f"  And create a new Issue with this information at '{_NEW_BUG_URL}'")
    all_builtin_circuitpython_modules = {*stdlib_module_names, *builtin_module_names}
    name_collisions = all_builtin_circuitpython_modules & internal_modules
    if name_collisions:
        logger.warning("Detected module name collisions")
        _ = [logger.warning(f" * {module}") for module in name_collisions]

    # The external CircuitPython module names remain after we remove the internal names and the builtin names
    external_module_names = {*all_base_imports} - internal_modules - all_builtin_circuitpython_modules

    # Show an import report
    if all_base_imports and (log_info or logger.isEnabledFor(logging.DEBUG)):

        def get_module_mark(module_name: str) -> str:
            if module_name in external_module_names:
                return "*"
            if module_name in all_builtin_circuitpython_modules:
                return "."
            return "~"

        grouped_by_source = sorted([f"{get_module_mark(module):>2} {module}" for module in all_base_imports])
        logger.info(f"Found {len(all_base_imports)} total module references   * external   . builtin   ~ internal")
        _ = [logger.info(line) for line in grouped_by_source]
    return sorted(external_module_names)


def _query_modules_from_circup(main_folder: pathlib.Path, log_info: bool) -> list[tuple[str, str]]:
    """Use circup to detect the installed CircuitPython modules and versions found in the specified folder."""
    if main_folder.joinpath("lib").exists() and (log_info or logger.isEnabledFor(logging.DEBUG)):
        logger.info("Detecting installed external CircuitPython modules")
    with suppress_unless_debug():
        circup_backend = circup.DiskBackend(str(main_folder), logger)
        installed_cp_modules = circup_backend.get_device_versions()
    if installed_cp_modules and (log_info or logger.isEnabledFor(logging.DEBUG)):
        _ = [
            logger.info(f" * {name:<20} {details['__version__']}")
            for name, details in sorted(installed_cp_modules.items())
        ]
    modules_with_version = [(name, details["__version__"]) for name, details in sorted(installed_cp_modules.items())]
    return modules_with_version


def _handle_generate_notice() -> str:
    """Handle the CLI option '--generate-notice'."""
    # We do not allow dev versions because we use this to stamp the version at release build time
    return _create_notice_file_contents(allow_dev_version=False)


def _handle_list_builtin_modules(board_id: str) -> str:
    """Handle the CLI option '--list-builtin-modules'."""

    # We define these as functions to reclaim their memory usage from parsing the HTML contents, which can be very large
    def fetch_find_extract_builtin_modules_for_board_id(reference_url: str, board_id: str) -> tuple[str, list[str]]:
        live_html_bytes = urllib.request.urlopen(reference_url).read()  # noqa: S310 -- URL is hardcoded to https
        live_html = live_html_bytes.decode("UTF-8")
        soup = bs4.BeautifulSoup(live_html, "html.parser")
        page_title = soup.title.text.split("-")[0].strip()  # pyright: ignore
        reference_version = soup.title.text.split("—")[-1].strip()  # pyright: ignore
        logger.info(f"Loaded '{page_title}' from '{reference_version}'")

        def row_matches_board_id(tag: bs4.Tag) -> bool:
            if tag.name != "tr":
                return False
            if not tag.td:
                return False
            if not tag.td.p:
                return False
            return tag.td.p.text == board_id

        the_table = soup.find("table", class_="support-matrix-table")
        the_row = the_table.find(name=row_matches_board_id)  # pyright: ignore
        if not the_row:
            logger.error(f"Cannot find CircuitPython board with name '{board_id}'!")
            logger.error(f"Confirm spelling from '{reference_url}'")
            raise SystemExit(_EXIT_BOARD_LOOKUP_FAILURE)
        row_cells = the_row.find_all("td")  # pyright: ignore
        modules_cell = row_cells[-1]
        builtin_module_names = [entry.text for entry in modules_cell.find_all("span", class_="pre")]  # pyright: ignore
        return reference_version, builtin_module_names

    def fetch_find_extract_standard_library_modules(reference_url: str) -> list[str]:
        live_html_bytes = urllib.request.urlopen(reference_url).read()  # noqa: S310 -- URL is hardcoded to https
        live_html = live_html_bytes.decode("UTF-8")
        soup = bs4.BeautifulSoup(live_html, "html.parser")
        the_stdlib_section = soup.find(id="python-standard-libraries")
        list_items = the_stdlib_section.select("li a span")  # pyright: ignore
        stdlib_module_names = [entry.text for entry in list_items]
        return stdlib_module_names

    logger.info(f"Parsing builtin modules for '{board_id}'")
    standard_library_page = "https://docs.circuitpython.org/en/stable/docs/library/index.html"

    reference_version, builtin_module_names = fetch_find_extract_builtin_modules_for_board_id(
        _board_support_matrix_page,
        board_id,
    )
    stdlib_module_names = fetch_find_extract_standard_library_modules(standard_library_page)

    full_contents = {
        "reference": reference_version,
        "urls": [_board_support_matrix_page, standard_library_page],
        "standard_library": stdlib_module_names,
        board_id: builtin_module_names,
    }
    return toml.dumps(full_contents)
