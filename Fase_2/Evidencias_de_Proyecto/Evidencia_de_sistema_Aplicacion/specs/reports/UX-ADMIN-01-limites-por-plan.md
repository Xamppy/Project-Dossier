# Verificación · UX-ADMIN-01 · Dossiers a la vez por usuario según el plan

- **Fecha:** 2026-11-11
- **Verifica:** pendiente (segundo integrante). La tabla la llenó quien implementó (FD, agente).
- **Spec:** [../proposals/UX-ADMIN-01-limites-por-plan.md](../proposals/UX-ADMIN-01-limites-por-plan.md)

## Criterios

Backend en `backend/tests/` contra PostgreSQL 18 real y la API por `TestClient`; frontend en
`frontend/src/`. `I` = `integration/test_limite_dossiers_simultaneos.py`, `S` =
`security/test_limites_plan_admin.py`.

| Criterio | Prueba que lo cubre | Estado |
|---|---|---|
| CA1 | I `::test_ca1_la_migracion_deja_los_valores_iniciales`, `::test_ca1_downgrade_quita_la_tabla_y_upgrade_la_repone` | cumple |
| CA2 | I `::test_ca2_free_puede_uno_y_el_segundo_da_409`, `::test_ca2_pro_puede_tres`; `::test_el_limite_cambiado_en_la_tabla_se_aplica_enseguida`, `::test_sin_fila_del_plan_se_usa_el_valor_inicial` | cumple |
| CA3 | I `::test_ca3_al_terminar_uno_se_libera_el_cupo` (completed, failed, cancelled) | cumple |
| CA4 | I `::test_ca4_el_tope_es_por_usuario` | cumple |
| CA5 | I `::test_ca5_un_trabajo_colgado_hace_mas_de_30_minutos_no_cuenta`, `::test_ca5_la_ventana_es_configurable`, `::test_ca5_trabajos_que_no_son_pedidos_del_usuario_no_cuentan`; `test_plan_limits.py` (ventana) | cumple |
| CA6 | I `::test_ca6_un_pedido_duplicado_devuelve_el_activo_aunque_el_tope_este_lleno` | cumple |
| CA7 | I `::test_ca7_calendario_que_supera_el_tope_no_encola_ninguna`, `::test_ca7_calendario_dentro_del_tope_encola_todas`, `::test_ca7_reuniones_ya_en_curso_no_cuentan_dos_veces`, `::test_ca7_persona_y_calendario_comparten_el_tope` | cumple |
| CA8 | I `::test_ca8_pedidos_simultaneos_no_superan_el_tope` (6 a la vez, tope 3); `stress/test_limite_dossiers_estres.py` (30 a la vez, 5 usuarios) | cumple |
| CA9 | S: lectura y cambio por el admin de plataforma con auditoría, 401 sin sesión, 403 para admin de organización y user, 422 fuera de 1–100 o con decimales/texto, 404 plan desconocido, fila faltante; `test_plan_limits.py` (esquema estricto) | cumple |
| CA10 | `components/admin/PlanLimitsPanel.test.tsx` (6 casos), `lib/translate-api-error.test.ts` (409 en siete idiomas), `components/dashboard/CalendarEventDetails.test.tsx` («…tope… traducido»), `i18n/admin-plan-limits-messages.test.ts` | cumple |

## Prueba en la aplicación en ejecución

API en `127.0.0.1:8000`, `next dev` en `localhost:3000`, base `dossier_demo`:

1. Al arrancar, la API creó `plan_settings` con Free 1, Pro 3 y Enterprise 10.
2. Con un usuario de prueba marcado como admin de plataforma, `/dashboard/admin` muestra la
   sección «Límites por plan». Al cambiar Free a 2, solo su botón «Guardar» se habilita. Al
   guardar aparece «Límite guardado.» con la fecha y el autor. En la base: valor 2 y una fila
   `ADMIN plan_settings` con `{"antes": 1, "despues": 2}`.
3. Con 2 trabajos activos, `POST /dossiers/person/research` responde **409**
   `{"code": "CONCURRENT_DOSSIER_LIMIT", "limit": 2, "active": 2}` y no crea el trabajo.
4. La base demo quedó como estaba (trabajos de prueba cancelados, Free en 1, sin admin).

**Sin cubrir:**
- La pantalla de Personas ya no deja enviar mientras ve un trabajo en curso, así que el mensaje
  traducido del 409 no se vio ahí en vivo. Se probó con Vitest, en la ficha de reunión y en el
  traductor.
- Las generaciones síncronas (corporativo manual y Personas sin `async_mode`) no crean trabajos y
  no cuentan. En la interfaz ya son de a una por pestaña.

## Suites completas

| Suite | Resultado |
|---|---|
| Backend con PostgreSQL | 1750 passed, 2 skipped (los esqueletos de S2.4 y S5.8), 0 en rojo, sin el `.env` local |
| Frontend (Vitest) | 778 passed en 58 archivos |
| ruff y mypy sobre `src/dossier` | sin hallazgos (144 archivos) |
| `tsc --noEmit` y eslint | sin errores (la advertencia de siempre en `register/page.test.tsx`) |

## Descubierto de paso

- **No hay recuperación de trabajos colgados.** Si el proceso cae a mitad de una generación,
  el trabajo queda `running` para siempre. Aquí se evita que bloquee al usuario con la ventana de
  30 minutos. La recuperación en sí se resolvió después en BUG-2026-11-11-01 (latido y barrido).
- **El frontend traduce cualquier 429 como «espera N segundos»**: por eso el tope usa 409 con
  código propio.
- **La ficha de reunión del calendario mostraba `e.message` crudo**: con errores con código se
  veía el código. Ahora los errores con código se traducen; los demás siguen igual.
