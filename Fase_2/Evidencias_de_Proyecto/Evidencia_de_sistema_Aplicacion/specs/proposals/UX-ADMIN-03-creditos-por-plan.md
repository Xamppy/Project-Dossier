# UX-ADMIN-03 · Créditos al mes de cada plan, configurables

**Estado:** implementado (rama `feat/creditos-por-plan`) · **Fecha:** 2026-11-11

## Problema

Los créditos de cada plan estaban fijos en `billing/plan_catalog.py` (Free 10, Pro 500,
Enterprise 50.000 de saldo) y en las tarjetas de Configuración («500 créditos/mes»). Cambiarlos
exigía tocar código.

## Decisión

- `plan_settings.monthly_credits` (0 a 1.000.000), junto al tope de dossiers a la vez de
  UX-ADMIN-01. Valores iniciales: Free 10, Pro 500, Enterprise 50.000.
- El admin de plataforma los cambia en **Administración → Límites por plan**. Cada cambio queda
  en `audit_logs` (`ADMIN plan_settings`) con el valor anterior y el nuevo.
- Se aplican **al registrarse** (plan Free) y **al cambiar de plan**: el saldo y el tope mensual
  pasan a ser los créditos del plan. En Enterprise el valor es el saldo inicial; su tope sigue
  siendo «ilimitado».
- **El saldo de las organizaciones que ya existen no cambia.** No hay renovación mensual todavía
  (queda como mejora aparte).
- `ORG_SIGNUP_CREDITS` del `.env`, si existe, sigue mandando en el registro (compatibilidad).
- `GET /billing/plans` entrega los créditos de cada plan a las tarjetas de Configuración.

## Fuera de alcance

Renovación mensual automática, ajuste manual de créditos por organización, precio de los planes
(no hay pasarela de pago) y la regla de saldo al cambiar de plan.
