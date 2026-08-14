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

USER = "ubuntu"

PROPOSED_MIGRATION_PATH = Path(f"~{USER}/proposed-migration").expanduser()
CODE_PATH = PROPOSED_MIGRATION_PATH / "code"
PUBLIC_HTML_PATH = Path(f"~{USER}/public_html").expanduser()

BRITNEY1_LOCATION = PROPOSED_MIGRATION_PATH / "code" / "b1"
BRITNEY2_REPO = "https://git.launchpad.net/~ural/britney/+git/britney2-ubuntu"
BRITNEY2_LOCATION = PROPOSED_MIGRATION_PATH / "code" / "b2"
BRITNEY2_BRANCH = "autopkgtest-init-state-dir"

SCRIPTS_DEST = Path("/usr/local/bin")
CONF_PATH = PROPOSED_MIGRATION_PATH / "conf"

RELEASES_CONF_PATH = Path("/etc/proposed-migration")

# britney expects a *bunch* of magic directories to be present
BRITNEY_DIRS = [
    PROPOSED_MIGRATION_PATH / "d-i",
    PROPOSED_MIGRATION_PATH / "data",
    PROPOSED_MIGRATION_PATH / "var",
    PROPOSED_MIGRATION_PATH / "var" / "lock",
    PROPOSED_MIGRATION_PATH / "ssh",
    PROPOSED_MIGRATION_PATH / "Heidi",
    PROPOSED_MIGRATION_PATH / "input",
]

# britney also expects these symlinks, format (link_name, target)
BRITNEY_SYMLINKS = [
    (PROPOSED_MIGRATION_PATH / "var" / "data-b2", PROPOSED_MIGRATION_PATH / "data"),
    (PROPOSED_MIGRATION_PATH / "log", PUBLIC_HTML_PATH / "proposed-migration" / "log"),
    (PROPOSED_MIGRATION_PATH / "data" / "output", PROPOSED_MIGRATION_PATH / "output"),
]

DEB_DEPENDENCIES = [
    "procmail",
    "python3-keyring",
    "python3-amqplib",
]

CHARM_SOURCE_PATH = Path(__file__).parent.parent
CHARM_APP_DATA = CHARM_SOURCE_PATH / "app"


def render_template(template_path: Path, template_vars: dict, destination: Path):
    j2env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(template_path.parent),
        autoescape=jinja2.select_autoescape(),
    )
    template = j2env.get_template(template_path.name)
    with open(destination, "w") as f:
        f.write(template.render(template_vars))

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

def install_scripts():
    logger.info("installing scripts")
    scripts_path = CHARM_APP_DATA / "bin"
    runner_path = scripts_path / "runner"
    shutil.copytree(scripts_path, SCRIPTS_DEST, symlinks=True, dirs_exist_ok=True)
    shutil.copytree(runner_path, BRITNEY1_LOCATION, symlinks=True, dirs_exist_ok=True)
    logger.info("creating symlink for run_britney script")
    runner_script = BRITNEY1_LOCATION / "run_britney"
    if not SCRIPTS_DEST.joinpath("run_britney").is_symlink():
        SCRIPTS_DEST.joinpath("run_britney").symlink_to(runner_script)

def install_systemd_units():
    logger.info("installing systemd units")
    units_path = CHARM_APP_DATA / "units"
    units_to_install = [u.name for u in (units_path).glob("*")]
    units_to_enable = [u.name for u in (units_path).glob("*.timer")]

    system_units_dir = Path("/etc/systemd/system/")
    for unit in units_to_install:
        if unit.endswith(".j2"):
            unit_basename = unit.removesuffix(".j2")
            render_template(
                units_path / unit,
                {"user": USER},
                system_units_dir / unit_basename,
            )
        else:
            shutil.copy(units_path / unit, system_units_dir)

    systemd.daemon_reload()
    if units_to_enable:
        systemd.service_enable("--now", *units_to_enable)

def create_directories():
    logger.info("creating directories")
    for directory in [
        PROPOSED_MIGRATION_PATH,
        CODE_PATH,
        PUBLIC_HTML_PATH,
        BRITNEY1_LOCATION,
    ] + BRITNEY_DIRS:
        # use run_as_user instead of Path.mkdir
        # for appropriate permissions
        run_as_user(f"mkdir -p {directory}")
    logger.info("creating symlinks")
    for link, target in BRITNEY_SYMLINKS:
        # using Path.exists() can return false positives if the symlink exists but is broken
        # so use Path.is_symlink() to check if the symlink exists instead
        if not Path(link).is_symlink():
            # use run_as_user instead of Path.symlink_to
            # for appropriate permissions
            run_as_user(f"ln -s {target} {link}")

def clone_repositories():
    logger.info("cloning repositories")
    for repo, location, branch in [
        (
            BRITNEY2_REPO,
            BRITNEY2_LOCATION,
            BRITNEY2_BRANCH,
        ),
    ]:
        shutil.rmtree(location, ignore_errors=True)
        # TODO: the currently packaged version of pygit2 does not support cloning through
        # a proxy. the next release should hopefully include this feature.
        # pygit2.clone_repository(repo, location, checkout_branch=branch)
        run_as_user(f"git clone --depth 1 --branch '{branch}' '{repo}' '{location}'")

def install_proxy():
    if not is_proxy_defined():
        return
    # the rsync_proxy needs to be constructed manually
    rsync_proxy = os.getenv("JUJU_CHARM_HTTP_PROXY", "").replace("http://", "")
    logger.info("installing proxy environment file")
    Path("/etc/environment.d").mkdir(exist_ok=True)
    with open("/etc/environment.d/proxy.conf", "w") as file:
        file.write(
            dedent(
                f"""\
                http_proxy={os.getenv("JUJU_CHARM_HTTP_PROXY", "")}
                https_proxy={os.getenv("JUJU_CHARM_HTTPS_PROXY", "")}
                no_proxy={os.getenv("JUJU_CHARM_NO_PROXY", "")}
                rsync_proxy={rsync_proxy}
                """
            )
        )

    os.environ["http_proxy"] = os.getenv("JUJU_CHARM_HTTP_PROXY", "")
    os.environ["https_proxy"] = os.getenv("JUJU_CHARM_HTTPS_PROXY", "")
    os.environ["no_proxy"] = os.getenv("JUJU_CHARM_NO_PROXY", "")
    os.environ["rsync_proxy"] = rsync_proxy

def install():
    """Install proposed migration charm."""
    install_proxy()
    logger.info("updating package index")
    apt.update()
    logger.info("installing packages")
    apt.add_package(DEB_DEPENDENCIES)
    create_directories()
    clone_repositories()
    install_scripts()
    install_systemd_units()

def start():
    pass

def write_amqp_password(amqp_password: str):
    logger.info("writing amqp password")
    password_path = PROPOSED_MIGRATION_PATH / "amqp_password.txt"
    with open(password_path, "w") as f:
        f.write(amqp_password)

def write_releases_conf(devel_release: str, all_releases: str):
    logger.info("writing releases configuration")
    RELEASES_CONF_PATH.mkdir(parents=True, exist_ok=True)
    render_template(
        CONF_PATH / "releases.conf.j2",
        {
            "devel_release": devel_release,
            "all_releases": all_releases,
        },
        RELEASES_CONF_PATH / "releases.conf",
    )

def write_britney_conf(swift_url: str, autopkgtest_url: str, amqp_url: str):
    logger.info("writing britney configuration")
    render_template(
        CONF_PATH / "britney.conf.j2",
        {
            "swift_url": swift_url,
            "autopkgtest_url": autopkgtest_url,
            "amqp_url": amqp_url,
        },
        BRITNEY2_LOCATION / "britney.conf",
    )

def configure(amqp_password: str, swift_url: str, autopkgtest_url: str, amqp_url: str, devel_release: str, all_releases: str):
    write_amqp_password(amqp_password)
    write_releases_conf(devel_release, all_releases)
    write_britney_conf(swift_url, autopkgtest_url, amqp_url)
