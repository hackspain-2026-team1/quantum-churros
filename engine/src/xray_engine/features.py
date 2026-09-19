"""Former home of the as-of invoice stock; it now lives in ``invoices``."""

from __future__ import annotations

from .invoices import invoice_states_as_of

__all__ = ["invoice_states_as_of"]
