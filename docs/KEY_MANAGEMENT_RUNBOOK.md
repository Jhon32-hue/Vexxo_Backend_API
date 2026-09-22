# Runbook de llaves y cifrado

Este procedimiento cubre el runtime local actual. Las llaves nunca se escriben
en Git, modelos, logs, tickets ni documentos operativos. El backend almacena
solo `key_version`, nonce, ciphertext y el DEK envuelto.

## Responsabilidades

- Django, JWT, recovery, throttling y cifrado usan secretos independientes.
- La KEK activa solo escribe; las versiones anteriores se conservan para leer.
- Credenciales externas y documentos cifrados participan en el mismo conteo.
- Passwords, recovery codes y otros verificadores permanecen hasheados.

## Activacion local

Generar una KEK de 32 bytes sin imprimirla ni copiarla manualmente:

```powershell
.\scripts\manage_local_keyring.ps1 -Action Initialize
```

El script actualiza `.env.local`, excluido de Git, y crea un respaldo cifrado
DPAPI en `.runtime/security/local-keyring.dpapi`.

Reiniciar el stack y comprobarlo sin imprimir material sensible:

```powershell
.\scripts\run_stack.cmd local down
.\scripts\run_stack.cmd local up full
.\scripts\run_stack.cmd local security-status
.\scripts\run_stack.cmd local key-rotation-status
```

## Rotacion `v1 -> v2`

1. Ejecutar `.\scripts\manage_local_keyring.ps1 -Action Rotate`.
2. Confirmar que el status conserva `v1` y marca `v2` como activa.
3. Reiniciar API, scheduler y workers para que las escrituras nuevas usen `v2`.
4. Ejecutar el rewrap en lotes.
5. Verificar que credenciales y documentos bajo `v1` llegaron a cero.
6. Respaldar y probar restauracion antes de retirar `v1`.

```powershell
.\scripts\run_stack.cmd local rotate-keys full --limit 25
docker compose -f docker-compose.local.yml exec -T api python manage.py key_rotation_status
docker compose -f docker-compose.local.yml exec -T api python manage.py key_retirement_check v1
.\scripts\manage_local_keyring.ps1 -Action Retire -Version v1 -ConfirmRetire
```

El retiro archiva primero el respaldo completo anterior bajo
`.runtime/security/retired/` y luego genera el respaldo activo sin la version
retirada. Ambos archivos permanecen fuera de Git y protegidos por DPAPI.

El rewrap cambia solamente la envoltura del DEK. No reescribe el archivo ni el
ciphertext del secreto. `key_retirement_check` falla mientras exista cualquier
credencial o documento dependiente de la version.

Para JWT, agregar y activar la nueva llave mantiene validos los tokens firmados
con el `kid` anterior. La llave anterior solo se retira despues del TTL maximo
de refresh y de verificar que no quedan sesiones que dependan de ella.

## Respaldo y recuperacion

- Mantener dos copias cifradas fuera del repositorio y fuera del host de la app.
- Exigir dos responsables para recuperar o retirar una llave productiva.
- Respaldar el mapa completo version -> KEK; una base sin sus KEK no es recuperable.
- Ejecutar trimestralmente una restauracion aislada y descifrar una credencial y
  un documento de prueba antes de declarar valido el respaldo.
- Registrar responsable, motivo, fecha, versiones y resultado en auditoria; nunca
  registrar el valor de una llave.

## Compromiso de llave

1. Preservar logs y evidencia; no borrar la version comprometida de inmediato.
2. Crear y activar una version nueva.
3. Detener temporalmente escrituras del proveedor afectado si existe riesgo de
   exfiltracion activa.
4. Ejecutar rewrap y revisar `key_rotation_status`.
5. Revocar y renovar tokens OAuth/API del proveedor; el rewrap no invalida un
   token que ya fue robado.
6. Si se comprometio JWT, rotar firma, revocar las familias de sesiones
   afectadas y esperar el TTL antes de retirar la llave anterior.
7. Retirar la version solo despues de `key_retirement_check` y del analisis del
   incidente.

## Adapter futuro

KMS o Secret Manager reemplazaran exclusivamente la resolucion de KEK. Los
modelos y envelopes no deben cambiar ni conocer el proveedor de secretos.
