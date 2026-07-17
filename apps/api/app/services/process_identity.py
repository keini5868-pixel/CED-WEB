"""Identidad de proceso — diagnóstico temporal para detectar múltiples réplicas.

`PROCESS_BOOT_ID` se genera una vez al importar el módulo (arranque del proceso).
Si distintas requests devuelven `boot_id` diferentes, hay más de una instancia
sirviendo tráfico y el estado en memoria (voice_client_session, retell_call_registry)
no se comparte entre ellas.
"""

from __future__ import annotations

import uuid

PROCESS_BOOT_ID = uuid.uuid4().hex[:12]
