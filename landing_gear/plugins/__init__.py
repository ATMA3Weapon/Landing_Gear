"""Landing Gear first-party plugin family.

Per the spec, the plugin system lets core ecosystem extras like Ledger,
Trustd, and Trustd_auth come online out of the box instead of being
reimplemented service by service.

Import the plugin classes you need:

    from landing_gear.plugins import LedgerPlugin, TrustdPlugin, TrustdAuthPlugin
    from landing_gear.plugins import DiagnosticsPlugin
    from landing_gear.plugins import PluginBase, PluginRegistry
"""
from .base import PluginBase
from .registry import PluginRegistry
from .ledger import LedgerPlugin
from .trustd import TrustdPlugin
from .trustd_auth import TrustdAuthPlugin
from .diagnostics import DiagnosticsPlugin

__all__ = [
    'PluginBase',
    'PluginRegistry',
    'LedgerPlugin',
    'TrustdPlugin',
    'TrustdAuthPlugin',
    'DiagnosticsPlugin',
]
