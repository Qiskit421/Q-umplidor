# 🤖 Registro de uso de IA

Aquí anotamos cada vez que usamos IA para generar, revisar o modificar algo del proyecto ***Q-umplidor***. La tabla es el resumen; el detalle de cada entrada (objetivo, resultado, revisión, cambios, prueba y aprendizaje) está en [detalle-uso-ia.md](detalle-uso-ia.md).

El estándar del cliente (doc. 04) pide que en el registro haya, como mínimo:

- un resultado **aceptado** después de verificarlo,
- un resultado **modificado** porque tenía una deficiencia,
- un resultado **rechazado**, con el motivo técnico.

La columna **Decisión** marca cuál de los tres fue cada uso.

---

| ID | Fecha | Integrante | Herramienta | Archivo(s) | Propósito | Decisión |
|----|-------|------------|-------------|------------|-----------|----------|
| IA-001 | 01/10/2026 | Marlene | Claude AI | `docs/ai-usage/` | Plantilla para registrar el uso de IA | Modificado |
| IA-002 | 01/10/2026 | Ruy Valle | Claude AI | `src/main.py` | Implementar RF-04, RF-09 y RF-07 (`sleep N &`, `listar`, `codigo`) | Modificado |
| IA-003 | 01/10/2026 | Ruy Valle | Claude AI | `verif/scripts/test_funcional_avance1.py` | Script de verificación del Avance 1 | Modificado |
| IA-004 | 07/02/2026 | Misael | ChatGPT | `src/main.py` | Ejemplo de cómo se ve en terminal enviar un trabajo y mostrar el ID | Aceptado |
| IA-005 | 10/02/2026 | Misael | ChatGPT | `casos-de-prueba.md`, `matriz-trazabilidad.md` | Ejemplos de casos de prueba y matriz de trazabilidad | Aceptado |
| IA-006 | 25/10/2026 | Oscar | Claude AI | `src/main.py` | Captura separada de stdout y stderr (RF-11) | Modificado |
| IA-007 | 25/10/2026 | Oscar | Claude AI | `docs/technical-guide/Arquitectura.md`, `docs/user-guide/guia-de-usuario.md` | Actualizar las guías técnica y de usuario al código real | Aceptado |
| IA-008 | | | | | | Rechazado |
| IA-009 | 28/10/2026 | Oscar | Claude AI | `src/main.py`, `verif/scripts/prueba_cola.sh` | Cancelación en cola (RF-10) y rechazo con cola llena (RF-25) sobre la cola del PR #130 | Modificado |
| IA-010 | 28/10/2026 | Oscar | Claude AI | `docs/incidents/INC-001.md`, guías | Redactar el incidente INC-001 y actualizar las guías con la cola | Aceptado |

> Para agregar una entrada: añade la fila aquí y su sección en `detalle-uso-ia.md` con el mismo ID.
