"""Host-only dashboard code.

Nothing outside this package may import from it, and deleting it must leave the
simulator working. This module deliberately imports nothing -- in particular no
Qt -- so that dpc.ui.sample stays usable in headless tests.
"""
