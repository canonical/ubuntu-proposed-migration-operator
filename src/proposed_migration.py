#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import shutil
import subprocess
import os
from pathlib import Path
from textwrap import dedent

import jinja2
from charmlibs import apt, systemd

logger = logging.getLogger(__name__)

USER = "ubuntu-archive"

# NOTE: because the ubuntu-archive user does not exist upon initializing the machine,
#       the home directory must be specified explicitly. expanduser() does *not* work

PROPOSED_MIGRATION_PATH = Path(f"/home/{USER}/proposed-migration")
CODE_PATH = PROPOSED_MIGRATION_PATH / "code"
PUBLIC_HTML_PATH = Path(f"/home/{USER}/public_html")

UBUNTU_ARCHIVE_SCRIPTS_REPO = "https://git.launchpad.net/ubuntu-archive-scripts"
UBUNTU_ARCHIVE_SCRIPTS_LOCATION = Path(f"/home/{USER}/ubuntu-archive-scripts")
UBUNTU_ARCHIVE_SCRIPTS_BRANCH = "main"
UBUNTU_ARCHIVE_TOOLS_REPO = "https://git.launchpad.net/ubuntu-archive-tools"
UBUNTU_ARCHIVE_TOOLS_LOCATION = Path(f"/home/{USER}/ubuntu-archive-tools")
UBUNTU_ARCHIVE_TOOLS_BRANCH = "main"
GERMINATE_REPO = "https://git.launchpad.net/germinate"
GERMINATE_LOCATION = Path(f"/home/{USER}/germinate")
# germinate has both a main and a master branch but we use master in the archive-toolbox
GERMINATE_BRANCH = "master"
BRITNEY1_REPO = "https://git.launchpad.net/~ubuntu-release/britney/+git/britney1-ubuntu"
BRITNEY1_LOCATION = PROPOSED_MIGRATION_PATH / "code" / "b1"
BRITNEY1_BRANCH = "main"
BRITNEY2_REPO = "https://git.launchpad.net/~ubuntu-release/britney/+git/britney2-ubuntu"
BRITNEY2_LOCATION = PROPOSED_MIGRATION_PATH / "code" / "b2"
BRITNEY2_BRANCH = "master"

DEB_DEPENDENCIES = [
    "procmail",
]

CHARM_SOURCE_PATH = Path(__file__).parent.parent
CHARM_APP_DATA = CHARM_SOURCE_PATH / "app"


def run_as_user(command: str):
    subprocess.run(
        [
            "su",
            "--login",
            "--whitelist-environment=https_proxy,http_proxy,no_proxy",
            USER,
            "--command",
            command,
        ],
        check=True,
    )

def is_proxy_defined():
    """Check if Juju defined proxy environment variables."""
    return (
        "JUJU_CHARM_HTTP_PROXY" in os.environ
        or "JUJU_CHARM_HTTPS_PROXY" in os.environ
        or "JUJU_CHARM_NO_PROXY" in os.environ
    )

def install_systemd_units():
    logger.info("installing systemd units")
    units_path = CHARM_APP_DATA / "units"
    units_to_install = [u.name for u in (units_path).glob("*")]
    units_to_enable = [u.name for u in (units_path).glob("*.timer")]

    system_units_dir = Path("/etc/systemd/system/")
    j2env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(units_path),
        autoescape=jinja2.select_autoescape(),
    )
    j2context = {
        "archive_scripts_location": UBUNTU_ARCHIVE_SCRIPTS_LOCATION,
        "user": USER,
    }
    for unit in units_to_install:
        if unit.endswith(".j2"):
            unit_basename = unit.removesuffix(".j2")
            j2template = j2env.get_template(unit)
            with open(system_units_dir / unit_basename, "w") as f:
                f.write(j2template.render(j2context))
        else:
            shutil.copy(units_path / unit, system_units_dir)

    systemd.daemon_reload()
    if units_to_enable:
        systemd.service_enable("--now", *units_to_enable)

def create_user():
    logger.info(f"creating user {USER}")
    subprocess.run(['useradd', '-m', '-p', 'ubuntu', USER])

def create_directories():
    logger.info("creating directories")
    for directory in [
        PROPOSED_MIGRATION_PATH,
        CODE_PATH,
        PUBLIC_HTML_PATH
    ]:
        directory.mkdir(exist_ok=True, parents=True)
        shutil.chown(directory, USER, USER)

def clone_repositories():
    logger.info("cloning repositories")
    for repo, location, branch in [
        (
            BRITNEY1_REPO,
            BRITNEY1_LOCATION,
            BRITNEY1_BRANCH,
        ),
        (
            BRITNEY2_REPO,
            BRITNEY2_LOCATION,
            BRITNEY2_BRANCH,
        ),
        (
            UBUNTU_ARCHIVE_SCRIPTS_REPO,
            UBUNTU_ARCHIVE_SCRIPTS_LOCATION,
            UBUNTU_ARCHIVE_SCRIPTS_BRANCH,
        ),
        (
            UBUNTU_ARCHIVE_TOOLS_REPO,
            UBUNTU_ARCHIVE_TOOLS_LOCATION,
            UBUNTU_ARCHIVE_TOOLS_BRANCH,
        ),
        (
            GERMINATE_REPO,
            GERMINATE_LOCATION,
            GERMINATE_BRANCH
        )
    ]:
        shutil.rmtree(location, ignore_errors=True)
        # TODO: the currently packaged version of pygit2 does not support cloning through
        # a proxy. the next release should hopefully include this feature.
        # pygit2.clone_repository(repo, location, checkout_branch=branch)
        run_as_user(f"git clone --depth 1 --branch '{branch}' '{repo}' '{location}'")

def install_proxy():
    if is_proxy_defined():
        logger.info("installing proxy environment file")
        Path("/etc/environment.d").mkdir(exist_ok=True)
        with open("/etc/environment.d/proxy.conf", "w") as file:
            file.write(
                dedent(
                    f"""\
                    http_proxy={os.getenv("JUJU_CHARM_HTTP_PROXY", "")}
                    https_proxy={os.getenv("JUJU_CHARM_HTTPS_PROXY", "")}
                    no_proxy={os.getenv("JUJU_CHARM_NO_PROXY", "")}
                    """
                )
            )
        
        os.environ["http_proxy"] = os.getenv("JUJU_CHARM_HTTP_PROXY", "")
        os.environ["https_proxy"] = os.getenv("JUJU_CHARM_HTTPS_PROXY", "")
        os.environ["no_proxy"] = os.getenv("JUJU_CHARM_NO_PROXY", "")

def install():
    """Install proposed migration charm."""
    install_proxy()
    create_user()
    logger.info("updating package index")
    apt.update()
    logger.info("installing packages")
    apt.add_package(DEB_DEPENDENCIES)
    create_directories()
    clone_repositories()
    install_systemd_units()

def start():
    pass

def configure():
    pass