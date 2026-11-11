# UX-ADMIN-02 · Fuentes de noticias enchufables y administrables

**Estado:** implementado (rama `feat/fuentes-noticias-enchufables`) · **Fecha:** 2026-11-11

## Problema

La prensa la consultaban GDELT y NewsAPI, escritos a mano en el agente, en el grafo y en la
lista de fuentes. Agregar otra API (Factiva, LexisNexis, Event Registry…) obligaba a tocar
varios archivos. Además la prensa solo se usaba en dossiers de empresa, y el administrador
no podía controlar costo ni uso de cada fuente.

Pedido del equipo: dejar listo el camino para que Alloxentric conecte las APIs de noticias
que quiera (1, 2, 3 o más) y que el administrador las configure desde el panel, incluido un
cobro de créditos extra por fuente.

## Decisión

1. **Adaptadores.** Cada fuente es un archivo en `backend/src/dossier/news/proveedores/` que
   expone `PROVEEDOR`, una instancia de `ProveedorNoticias` (`clave`, `nombre`,
   `variable_clave` y `buscar(consulta, limite)`). El registro los descubre solo; los
   archivos que empiezan con `_` (la plantilla) se ignoran. Un adaptador inválido o con
   clave repetida se registra en el log y se omite: nunca rompe el arranque.
2. **Claves solo en el servidor.** La clave de cada API se lee de su variable de entorno.
   El panel solo muestra si está configurada y el nombre de la variable, nunca el valor.
   Una fuente sin clave no se consulta (ya no figura como «caída»).
3. **Ajustes por fuente** en `news_source_settings` (sin fila = valores por defecto del
   adaptador): activa, empresas, personas, profundidad mínima (solo empresas: las personas
   siempre son básicas), planes (Free/Pro/Enterprise), créditos extra (0–20), máximo de
   resultados (1–50) y límite diario de consultas (vacío = sin límite). Cada cambio queda
   en `audit_logs` (`ADMIN news_source_settings`). Una fuente nueva aparece **apagada**.
4. **Límite diario** en `news_source_usage` (fuente, día UTC). La consulta se reserva con un
   `INSERT … ON CONFLICT DO UPDATE … WHERE queries < límite`: dos dossiers a la vez no pueden
   pasarse del tope. Al llegar al tope la fuente se omite (sin cobro) hasta el día siguiente.
5. **Créditos extra.** Se estima el máximo (fuentes aplicables) para validar saldo antes de
   empezar; se cobra solo por las fuentes que respondieron (con o sin resultados). El trigger
   `fn_debit_credits_on_dossier` suma `dossier_data.news_extra_credits` al costo por
   profundidad. Sin cobro (`billing = none`: caché, fallo, refinamiento, informe parcial) no
   hay extra.
6. **Prensa en personas.** Etapa nueva `person.press_search` en Personas y Calendario. Busca
   el nombre exacto entre comillas y, si se conoce, la empresa; filtra homónimos. Las
   menciones van a la IA (marcadas como datos externos no confiables) y a la tarjeta
   «Prensa» del dossier, con su procedencia en `dossier_media_mentions`.

## Fuera de alcance

- Guardar claves de APIs en la base o en el panel (riesgo innecesario).
- Agregar un proveedor solo con configuración, sin código (las APIs premium usan
  autenticaciones distintas; copiar la plantilla toma unas horas).
- Adaptadores de APIs premium: sus APIs solo se entregan con contrato.

Guía para agregar una fuente: `docs/tecnica/agregar-fuente-noticias.md`.
