"""Functions for creating, configuring, and updating QT Py sensor nodes."""

import datetime
import logging
import pathlib
import shutil
import subprocess
import sys
import textwrap
import urllib.request
from enum import StrEnum
from typing import NamedTuple

import bs4
import circup
import click
import findimports
import packaging.version
import toml

from qtpy_datalogger import discovery

from .datatypes import ConnectionTransport, Default, ExitCode, Links, SnsrNotice, SnsrPath, suppress_unless_debug

logger = logging.getLogger(__name__)

_PC_ONLY_IMPORTS = [
    "typing",
]


class Behavior(StrEnum):
    """Supported installation behaviors for QT Py sensor nodes."""

    Upgrade = "Upgrade"
    Compare = "Compare"
    Describe = "Describe"
    Force = "Force"
    NewerFilesOnly = "NewerFilesOnly"


class SecretsBehavior(StrEnum):
    """Supported behaviors for handling the --secrets option."""

    Analyze = "Analyze"
    Noop = "Noop"
    Update = "Update"


class SnsrNodeBundle(NamedTuple):
    """Represents the version, contents, and dependencies for a sensor_node."""

    notice: SnsrNotice
    device_files: list[pathlib.Path]
    circuitpy_version: str
    board_id: str
    circuitpy_dependencies: list[str]
    installed_circuitpy_modules: list[tuple[str, str]]


def handle_equip(behavior: Behavior, root: pathlib.Path | None, secrets: str) -> None:
    """Handle the equip CLI command."""
    logger.debug(f"behavior: '{behavior}', root: '{root}', secrets: '{secrets}'")

    secrets_file = None
    if secrets == f"{SecretsBehavior.__name__}.{SecretsBehavior.Noop}":
        secrets_behavior = SecretsBehavior.Noop
    elif secrets == f"{SecretsBehavior.__name__}.{SecretsBehavior.Analyze}":
        secrets_behavior = SecretsBehavior.Analyze
    else:
        secrets_behavior = SecretsBehavior.Update
        if secrets == "-":
            pass
        else:
            secrets_file = pathlib.Path(secrets)
            if not (secrets_file.is_file() and secrets_file.exists()):
                logger.error(f"Cannot open secrets file '{secrets_file!s}'.")
                raise SystemExit(ExitCode.Secrets_File_Missing)

    this_file = pathlib.Path(__file__)
    this_folder = this_file.parent
    this_sensor_node_root = this_folder.joinpath("sensor_node")
    this_bundle = _detect_snsr_bundle(this_sensor_node_root)

    if behavior == Behavior.Describe:
        self_description = _format_bundle_description(this_bundle)
        _ = [logger.info(line) for line in self_description]
        raise SystemExit(ExitCode.Success)

    if not root:
        qtpy_device, communication_transport = discovery.discover_and_select_qtpy(
            Default.MqttGroup,
            ConnectionTransport.UART_Serial,
        )
        if not qtpy_device:
            logger.error("No QT Py devices found!")
            raise SystemExit(ExitCode.Discovery_Failure)
        if not communication_transport:
            logger.error(
                f"Cannot compare or equip '{qtpy_device.node_id}' with MQTT connection. Please connect with USB."
            )
            raise SystemExit(ExitCode.Equip_Without_USB_Failure)
        root = pathlib.Path(qtpy_device.drive_root).resolve()

    device_bundle = _detect_snsr_bundle(root)
    comparison_information = {
        "device bundle": device_bundle,
        "runtime bundle": this_bundle,
    }

    if behavior == Behavior.Compare:
        runtime_freshness = _compare_file_trees(this_bundle.device_files, device_bundle.device_files)
        comparison_report = _format_bundle_comparison(comparison_information, runtime_freshness)
        _ = [logger.info(line) for line in comparison_report]
        raise SystemExit(ExitCode.Success)

    should_install, skip_reason = _should_install(behavior, comparison_information)

    match secrets_behavior:
        case SecretsBehavior.Noop:
            pass
        case SecretsBehavior.Analyze:
            node_secrets = _detect_node_secrets(device_bundle.device_files[0])
            secrets_description = _format_secrets_description(node_secrets)
            _ = [logger.info(line) for line in secrets_description]
        case SecretsBehavior.Update:
            logger.info("Updating sensor_node secrets")
            _update_secrets(secrets_file, device_bundle.device_files[0])
            logger.info("Secrets updated")

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

    notice_file = main_folder.joinpath(SnsrPath.notice)

    detect_message = f"Probing for sensor_node at '{main_folder}'"
    if detecting_self:
        snsr_notice = SnsrNotice.get_package_notice_info(allow_dev_version=True)
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
          Homepage:   {Links.Homepage}

        Dependencies
          CircuitPython module           PC package name
          ====================   -{"-" * 31}-
        """
    ).splitlines()
    for circuitpy_library in bundle.circuitpy_dependencies:
        library_stub = "adafruit-circuitpython-{}".format(circuitpy_library.replace("adafruit_", ""))
        report_contents.append(f"  {circuitpy_library:>19}    {library_stub:>32}")
    return report_contents


def _format_bundle_comparison(
    comparison_information: dict[str, SnsrNodeBundle],
    file_freshness: dict[pathlib.Path, str],
) -> list[str]:
    """Format and return a list of lines that compares the specified sensor_node bundles."""
    device_bundle = comparison_information["device bundle"]
    this_bundle = comparison_information["runtime bundle"]

    newer_mark = "(newer)"
    older_mark = "       "
    same_mark = "(same) "
    try:
        device_version = packaging.version.Version(device_bundle.notice.version)
    except packaging.version.InvalidVersion:
        device_version = packaging.version.Version("0")
    device_timestamp = device_bundle.notice.timestamp
    self_version = packaging.version.Version(this_bundle.notice.version)
    self_timestamp = this_bundle.notice.timestamp

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
            Trait        Device {device_mark}                              Self {self_mark}
         ===========  -{"-" * 40}-  ----------------------
          Version      {device_version!s:<40}    {self_version!s}
          Timestamp    {device_timestamp.strftime("%Y.%m.%d  %H:%M:%S"):<40}    {self_timestamp.strftime("%Y.%m.%d  %H:%M:%S")}
          CircuitPy    {device_bundle.circuitpy_version:<40}    (PC host)
          Board ID     {device_bundle.board_id:<40}    (PC host)
          Location     {device_bundle.device_files[0]!s:<40}    (builtin)
        """
    )
    report_lines = report_contents.splitlines()

    newer_files = set()
    for path, freshness in file_freshness.items():
        full_path = this_bundle.device_files[0].joinpath(path)
        if not full_path.is_file():
            continue
        if freshness == "newer":
            newer_files.add(path)
            continue
    if newer_files:
        newer_file_lines = ["\n", "Newer files"]
        newer_file_lines.extend([f"  * {file!s}\n" for file in sorted(newer_files)])
        report_lines.extend(newer_file_lines)
    return report_lines


def _should_install(behavior: Behavior, comparison_information: dict[str, SnsrNodeBundle]) -> tuple[bool, str]:
    """
    Use the comparison_information to decide whether to install or upgrade the sensor_node bundle.

    Returns a tuple with
    - a bool indicating whether the bundle should be installed
    - a string message explaining why the bundle should not be installed
    """
    this_bundle = comparison_information["runtime bundle"]
    device_bundle = comparison_information["device bundle"]

    my_version = packaging.version.Version(this_bundle.notice.version)
    should_install = False

    # Do the first lines from the device's code.py and our code.py match?
    device_main_folder = device_bundle.device_files[0]
    device_codepy_file = device_main_folder.joinpath("code.py")
    device_codepy_is_snsr_node = False
    if device_codepy_file.exists():
        device_first_line = device_codepy_file.read_text().splitlines()[0]
        snsr_codepy_first_line = this_bundle.device_files[0].joinpath("code.py").read_text().splitlines()[0]
        device_codepy_is_snsr_node = device_first_line == snsr_codepy_first_line

    skip_reason = ""
    if device_codepy_is_snsr_node:
        device_snsr_version = packaging.version.Version(device_bundle.notice.version)
        device_snsr_timestamp = device_bundle.notice.timestamp
        my_timestamp = this_bundle.notice.timestamp

        if behavior == Behavior.NewerFilesOnly:
            logger.info("Forcing installation of newer files")
            should_install = True
        elif my_version > device_snsr_version:
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
    this_bundle = comparison_information["runtime bundle"]

    logger.info(f"Installing sensor_node v{this_bundle.notice.version} to '{device_main_folder}'")
    my_main_folder = this_bundle.device_files[0]
    device_snsr_root = device_main_folder.joinpath(SnsrPath.root)

    ignore_patterns = {"*.pyc", "__pycache__"}
    if behavior == Behavior.NewerFilesOnly:
        runtime_freshness = _compare_file_trees(this_bundle.device_files, device_bundle.device_files)
        older_files = set()
        newer_files = set()
        for path, freshness in runtime_freshness.items():
            full_path = this_bundle.device_files[0].joinpath(path)
            if not full_path.is_file():
                continue
            if freshness == "newer" and all(pattern not in str(path) for pattern in ignore_patterns):
                logger.info(f"  Newer: {path}")
                newer_files.add(path.name)
                continue
            older_files.add(path.name)
        if not newer_files:
            logger.info("All files up to date with the host")
            return
        ignored_files = older_files - newer_files
        ignore_patterns.update(ignored_files)
    elif device_snsr_root.exists():
        logger.info("  Copying snsr bundle")
        shutil.rmtree(device_snsr_root)

    shutil.copytree(
        src=my_main_folder,
        dst=device_main_folder,
        ignore=shutil.ignore_patterns(*ignore_patterns),
        dirs_exist_ok=True,
    )

    notice_file = device_main_folder.joinpath(SnsrPath.notice)
    notice_contents = _create_notice_file_contents(allow_dev_version=True)
    notice_file.write_text(notice_contents)

    if behavior == Behavior.NewerFilesOnly:
        logger.info("Bundle files updated")
        return

    circup_packages = this_bundle.circuitpy_dependencies
    return_code = ExitCode.Success
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

    if return_code == ExitCode.Success:
        logger.info("Installation complete")
    else:
        logger.error(f"circup exited with code '{return_code}'")


def _create_notice_file_contents(allow_dev_version: bool) -> str:
    """Format the notice.toml file for the package."""
    snsr_notice = SnsrNotice.get_package_notice_info(allow_dev_version)
    file_contents = toml.dumps(snsr_notice._asdict())
    return file_contents


def _get_plugins(folder_list: list[pathlib.Path]) -> list[str]:
    """Return a list of the installed sensor_node plugins."""
    main_folder = folder_list[0]
    snsr_root = main_folder.joinpath(SnsrPath.root)
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


def _compare_file_trees(tree1: list[pathlib.Path], tree2: list[pathlib.Path]) -> dict[pathlib.Path, str]:
    """Compare two lists of paths, identifying newer. A value of "newer" means tree1's file is newer than tree2's file."""
    set1 = {path.relative_to(tree1[0]) for path in tree1}
    set2 = {path.relative_to(tree2[0]) for path in tree2}
    shared_in_both = set1 & set2
    tree1_file_ages = {}
    for path in shared_in_both:
        modification_time1 = tree1[0].joinpath(path).stat().st_mtime
        modification_time2 = tree2[0].joinpath(path).stat().st_mtime
        age = "equal"
        if modification_time1 > modification_time2:
            age = "newer"
        if modification_time1 < modification_time2:
            age = "older"
        tree1_file_ages[path] = age
    for path in set1 - set2:
        tree1_file_ages[path] = "newer"
    return tree1_file_ages


def _get_circuitpython_dependencies(device_files: list[pathlib.Path], device_id: str, log_info: bool) -> list[str]:
    """Scan the sensor_node files for Python dependencies and return a list of external module imports."""
    # Get the folder and file names under the snsr folder
    main_folder = device_files[0]
    snsr_folder = main_folder.joinpath(SnsrPath.root)
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
        logger.warning(f"  Visit '{Links.Board_Support_Matrix}' and find your BOARD NAME")
        logger.warning(
            "  Then use 'qtpy-datalogger --list-builtin-modules \"BOARD NAME\" -' to get the builtin modules"
        )
        logger.warning(f"  And create a new Issue with this information at '{Links.New_Bug}'")
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


def _detect_node_secrets(device_root: pathlib.Path) -> dict[str, bool]:
    """Parse the settings.toml file on the sensor_node and return a dictionary of detected secrets."""
    expected_secrets = {
        "CIRCUITPY_WIFI_SSID": False,
        "CIRCUITPY_WIFI_PASSWORD": False,
        "QTPY_BROKER_IP_ADDRESS": False,
        "QTPY_NODE_GROUP": False,
        "QTPY_NODE_NAME": False,
    }
    settings_file = device_root.joinpath(SnsrPath.settings)
    if not settings_file.exists():
        return expected_secrets
    device_settings = toml.load(settings_file)
    detected_secrets = {
        secret: secret in device_settings
        for secret in expected_secrets
    }
    return detected_secrets


def _format_secrets_description(node_secrets: dict[str, bool]) -> list[str]:
    """Format and return a list of lines that describes this sensor_node's secrets."""
    secrets_report = []
    secrets_report.append("Detecting secrets")
    for secret_name, is_defined in node_secrets.items():
        message = "ok" if is_defined else click.style("MISSING", "yellow")
        secrets_report.append(f" * {secret_name:<24}  {message}")
    return secrets_report


def _update_secrets(new_secrets_file: pathlib.Path | None, device_root: pathlib.Path) -> None:
    """Update the secrets on the sensor_node."""
    secrets_file = device_root.joinpath(SnsrPath.settings)
    if new_secrets_file:
        shutil.copy(new_secrets_file, secrets_file)
        return

    click.echo()
    click.echo(f"Set a new value or press {click.style('<Enter>', 'bright_cyan')} to skip")
    new_secrets = {}
    detected_secrets = _detect_node_secrets(device_root)
    for secret in detected_secrets:
        user_input = click.prompt(
            text=f"  {click.style(secret, 'bright_green')}",
            default="",
            hide_input=True,
            type=str,
            show_default=False,
        )
        if user_input:
            new_secrets[secret] = user_input
    click.echo()

    final_secrets = new_secrets.copy()
    if secrets_file.exists():
        old_secrets = toml.load(secrets_file)
        final_secrets.update(old_secrets)  # Retain unrelated toml entries
        final_secrets.update(new_secrets)  # Overlay the new secrets
    with secrets_file.open("w") as secrets_fd:
        toml.dump(final_secrets, secrets_fd)


def _handle_generate_notice() -> str:
    """Handle the CLI option '--generate-notice'."""
    # We do not allow dev versions because we use this to stamp the version at release build time
    return _create_notice_file_contents(allow_dev_version=False)


def _handle_list_builtin_modules(board_id: str) -> str:
    """Handle the CLI option '--list-builtin-modules'."""

    # We define these as functions to reclaim their memory usage from parsing the HTML contents, which can be very large
    def fetch_find_extract_builtin_modules_for_board_id(reference_url: str, board_id: str) -> tuple[str, list[str]]:
        page_request = urllib.request.Request(reference_url, headers={"User-agent": "Mozilla/5.0"})  # noqa: S310 -- URL is hardcoded to https
        live_html_bytes = urllib.request.urlopen(page_request).read()  # noqa: S310 -- URL is hardcoded to https
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
            raise SystemExit(ExitCode.Board_Lookup_Failure)
        row_cells = the_row.find_all("td")  # pyright: ignore
        modules_cell = row_cells[-1]
        builtin_module_names = [entry.text for entry in modules_cell.find_all("span", class_="pre")]  # pyright: ignore
        return reference_version, builtin_module_names

    def fetch_find_extract_standard_library_modules(reference_url: str) -> list[str]:
        page_request = urllib.request.Request(reference_url, headers={"User-agent": "Mozilla/5.0"})  # noqa: S310 -- URL is hardcoded to https
        live_html_bytes = urllib.request.urlopen(page_request).read()  # noqa: S310 -- URL is hardcoded to https
        live_html = live_html_bytes.decode("UTF-8")
        soup = bs4.BeautifulSoup(live_html, "html.parser")
        the_stdlib_section = soup.find(id="python-standard-libraries")
        list_items = the_stdlib_section.select("li a span")  # pyright: ignore
        stdlib_module_names = [entry.text for entry in list_items]
        return stdlib_module_names

    logger.info(f"Parsing builtin modules for '{board_id}'")
    standard_library_page = "https://docs.circuitpython.org/en/stable/docs/library/index.html"

    reference_version, builtin_module_names = fetch_find_extract_builtin_modules_for_board_id(
        Links.Board_Support_Matrix,
        board_id,
    )
    stdlib_module_names = fetch_find_extract_standard_library_modules(standard_library_page)

    full_contents = {
        "reference": reference_version,
        "urls": [Links.Board_Support_Matrix.value, standard_library_page],
        "standard_library": stdlib_module_names,
        board_id: builtin_module_names,
    }
    return toml.dumps(full_contents)
