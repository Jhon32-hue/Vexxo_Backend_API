# Garantias de identidad y dispositivo

## Matriz de operaciones sensibles

| Operacion | Garantia requerida | Efecto de seguridad |
|---|---|---|
| Cambio de password | sesion sin step-up pendiente + password actual | revoca todas las familias |
| Reset/recovery con MFA activo | codigo de recovery + TOTP o recovery code | revoca todas las familias |
| Enrolar o desactivar MFA | sesion sin step-up pendiente + password actual | modifica el limite de garantia |
| Confiar dispositivo | sesion sin step-up pendiente | impide promover desde sesion riesgosa |
| Desvincular identidad social | sesion sin step-up pendiente | revoca sesiones del proveedor |
| Revocar dispositivo | owner/staff autorizado | cierra sus sesiones inmediatamente |
| Suspender usuario | staff + motivo | cierra todas las sesiones inmediatamente |
| Riesgo critico | evaluacion persistida | rechaza el JWT y revoca la sesion |
| Attestation oficial | challenge de un solo uso | marca `platform_verified` con expiracion |

La firma Ed25519 prueba posesion de una llave local y marca `key_verified`. No
equivale a Play Integrity o App Attest y nunca marca `platform_verified`.

## Lifecycle de attestation

- El challenge tiene nonce, expiracion, consumo unico y limite de intentos.
- Una verificacion oficial correcta fija `platform_verification_expires_at`.
- El scheduler expira attestations vencidas cada hora.
- Fallos consecutivos incrementan anomalías; al alcanzar el umbral, el
  dispositivo pasa a sospechoso, la evidencia queda rechazada y sus sesiones se
  revocan.
- La revocacion masiva es dry-run por defecto y exige un filtro para confirmar.

```powershell
docker compose -f docker-compose.local.yml exec -T api python manage.py devices_revoke_attestations --provider play_integrity
docker compose -f docker-compose.local.yml exec -T api python manage.py devices_revoke_attestations --provider play_integrity --confirm
```

## Pruebas oficiales pendientes de valores externos

El backend puede probar nonce, replay, expiracion, errores, anomalías y
revocacion con adapters simulados. La evidencia criptografica real requiere:

- Android instalado desde un track de Google Play, proyecto/nombre de paquete
  autorizados y credenciales de Play Integrity.
- iPhone/iPad real, entitlement de App Attest, Team ID, Bundle ID y flujo desde
  Xcode/TestFlight.

Estas pruebas no se sustituyen con mocks. Hasta completarlas, los adapters
permanecen deshabilitados y `security_activation_check` debe reportarlo.

## Evidencia local

La suite de identidad y seguridad cubre rotacion JWT conservando tokens con
`kid` anterior, recovery anti-enumeracion, MFA, expiracion y revocacion de
attestation, cambio de password, dispositivo revocado, suspension con motivo y
riesgo critico. La baseline local actual ejecuto 43/43 pruebas correctamente.
