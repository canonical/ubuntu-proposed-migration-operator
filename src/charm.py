#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import proposed_migration
import ops
from ops.framework import StoredState

class ProposedMigrationCharm(ops.CharmBase):
    """Proposed migration charm class."""

    _stored = StoredState()

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)

        self._stored.set_default(
            installed=False
        )

        # basic hooks
        framework.observe(self.on.install, self._on_install)
        framework.observe(self.on.config_changed, self._on_config_changed)
        framework.observe(self.on.start, self._on_start)

    def _on_install(self, event: ops.InstallEvent):
        """Install the workload on the machine."""
        self.unit.status = ops.MaintenanceStatus("installing workload")
        proposed_migration.install()
        self._stored.installed = True

    def _on_start(self, event: ops.StartEvent):
        """Start the workload on the machine."""
        proposed_migration.start()
        self.unit.status = ops.ActiveStatus()

    def _on_config_changed(self, event: ops.ConfigChangedEvent):
        if not self._stored.installed:
            self.on.install.emit()
        
        self.unit.status = ops.MaintenanceStatus("configuring service")

        proposed_migration.configure()

        self.on.start.emit()

if __name__ == "__main__":  # pragma: nocover
    ops.main(ProposedMigrationCharm)