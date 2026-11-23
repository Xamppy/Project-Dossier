# UX-CAL-03 · Reuniones con varias personas: el usuario elige de quién es el dossier

**Estado:** implementado, en revisión · **Fecha:** 2026-11-23

## Problema

La generación automática solo entiende el contacto escrito en la descripción del evento. En una
reunión con varios asistentes no sabe de quién hacer el dossier: no genera nada y deja un error.
Tampoco se deben generar varios dossiers de persona de una vez.

## Decisión

- **Persona de la reunión:** cada contacto declarado en la descripción y cada asistente u
  organizador del evento, sin repetir. No cuentan el propio usuario (correo de la cuenta, correo
  del calendario conectado o la marca `self` de Google) ni las salas. Un contacto declarado y un
  asistente son la misma persona si comparten correo, si el nombre coincide o si son los únicos.
- **Varias personas (dos o más):** la automatización **no genera**. El evento queda en `skipped`
  con el motivo, sin error y sin volver a programarse en cada sincronización. Si el evento pasa a
  tener una sola persona, se programa como siempre.
- **Generación manual:** el usuario elige **una** persona y se genera **solo su dossier**, por 1
  crédito. No se genera el de la empresa aunque la descripción traiga «Empresa:»: se repetiría por
  cada persona elegida y sumaría 3 créditos en Pro sin avisar. La empresa declarada (o, si falta,
  la del dominio del correo) solo sirve para identificar a la persona. El dossier de empresa se
  pide en el módulo Empresas.
- **El servidor lo exige**, no solo la pantalla: sin persona, o con una que no es de la reunión,
  responde 422 y no crea trabajo ni cobra.
- **Resumen (UX-KPI-01):** la reunión cuenta como preparada con el dossier de una de sus personas, y
  no espera ni suma el de empresa.
- Con una sola persona nada cambia.

## Contrato

- `GET /calendario/eventos-{google,outlook}` por intervalo: cada reunión suma
  `personas: [{id, nombre, correo, cargo, pais}]`.
- `POST /calendario/generar-dossiers-{google,outlook}`: campo opcional `persona_id`.
- 422 `{"code": "CALENDAR_PERSON_REQUIRED", "personas": [...]}` si falta elegir.
- 422 `{"code": "CALENDAR_PERSON_NOT_FOUND", "personas": [...]}` si la elegida no es de la reunión.
- Sin `event_id` (lote por `top`) y en los `GET` heredados, las reuniones con varias personas se
  omiten; si no queda ninguna, 422 `CALENDAR_PERSON_REQUIRED`.

## Criterios de aceptación

- **CA1** Una reunión con varias personas nunca se genera sola: ni se encola ni se marca `failed`.
- **CA2** Al quedar una sola persona, vuelve a programarse.
- **CA3** El usuario y las salas no cuentan; nadie aparece dos veces.
- **CA4** Con varias personas, «Generar dossier» abre un diálogo encima del detalle con una
  casilla por persona; marcar una desmarca la anterior y sin marca no se puede generar.
- **CA5** El trabajo genera un único dossier, el de la persona elegida, con su correo y no otro. No
  hay dossier de empresa aunque haya «Empresa:», y se estima 1 crédito.
- **CA6** La elección sobrevive a la relectura del evento que hace el trabajo en cola.
- **CA7** El cliente no puede inyectar una persona ajena a la reunión.
- **CA8** El diálogo es accesible: foco, Escape cierra solo el diálogo, Tab no sale.
- **CA9** Resumen da por preparada la reunión con un dossier de cualquiera de sus personas; sin él
  estima 1 crédito.

## Límite conocido

De un asistente sin nombre en el calendario solo se conoce el correo: el nombre se deduce de él
(`ana.perez@…` → «Ana Perez») y la empresa, de su dominio corporativo si la descripción no la dice.
