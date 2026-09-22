"""Generate the canonical local Postman collection and its human guide."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JSON_OUTPUT = ROOT / "postman" / "Vexxo_local.postman_collection.json"
GUIDE_OUTPUT = ROOT / "postman" / "Vexxo_local.postman_collection.md"


def script_event(listen: str, lines: list[str]) -> dict:
    return {
        "listen": listen,
        "script": {"type": "text/javascript", "exec": lines},
    }


def request(
    name: str,
    method: str,
    path: str,
    description: str,
    *,
    body: dict | list | str | None = None,
    formdata: list[dict] | None = None,
    public: bool = False,
    internal: bool = False,
    capture: tuple[str, str] | None = None,
    extra_tests: list[str] | None = None,
    expected: tuple[int, ...] | None = None,
    headers: list[tuple[str, str]] | None = None,
    bearer_variable: str | None = None,
) -> dict:
    method = method.upper()
    request_headers = []
    if body is not None:
        request_headers.append({"key": "Content-Type", "value": "application/json"})
    if internal:
        request_headers.append({"key": "X-Vexxo-Internal-Token", "value": "{{internal_token}}"})
    for key, value in headers or []:
        request_headers.append({"key": key, "value": value})

    payload = {
        "description": description,
        "method": method,
        "header": request_headers,
        "url": f"{{{{base_url}}}}{path}",
    }
    if public:
        payload["auth"] = {"type": "noauth"}
    elif bearer_variable:
        payload["auth"] = {
            "type": "bearer",
            "bearer": [{"key": "token", "value": f"{{{{{bearer_variable}}}}}", "type": "string"}],
        }
    if body is not None:
        raw = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, indent=2)
        payload["body"] = {"mode": "raw", "raw": raw, "options": {"raw": {"language": "json"}}}
    elif formdata is not None:
        payload["body"] = {"mode": "formdata", "formdata": formdata}

    expected_codes = expected or {
        "GET": (200,),
        "POST": (200, 201, 202),
        "PUT": (200,),
        "PATCH": (200,),
        "DELETE": (200, 204),
    }[method]
    tests = [
        f"pm.test('{name}: status esperado', function () {{",
        f"  pm.expect({list(expected_codes)}).to.include(pm.response.code);",
        "});",
    ]
    if capture:
        variable, expression = capture
        tests.extend(
            [
                "if (pm.response.code >= 200 && pm.response.code < 300 && pm.response.text()) {",
                "  const data = pm.response.json();",
                f"  const value = {expression};",
                f"  if (value !== undefined && value !== null) pm.collectionVariables.set('{variable}', value);",
                "}",
            ]
        )
    tests.extend(extra_tests or [])

    return {"name": name, "event": [script_event("test", tests)], "request": payload}


def folder(name: str, description: str, items: list[dict]) -> dict:
    return {"name": name, "description": description, "item": items}


def crud_reads(label: str, path: str, id_variable: str, description: str) -> list[dict]:
    return [
        request(f"List {label}", "GET", path, f"Lista {description}."),
        request(f"Retrieve {label}", "GET", f"{path}{{{{{id_variable}}}}}/", f"Consulta un registro de {description}."),
    ]


def build_collection() -> dict:
    variables = [
        ("base_url", "http://127.0.0.1:8000"),
        ("email", "prueba@example.com"),
        ("password", "Secret12345!"),
        ("access_token", ""),
        ("refresh_token", ""),
        ("internal_token", ""),
        ("support_access_token", ""),
        ("support_reason", "Investigacion local autorizada"),
        ("support_case", "LOCAL-001"),
        ("support_user_id", ""),
        ("request_id", ""),
        ("current_date", ""),
        ("current_month", ""),
        ("previous_month", ""),
        ("future_date_30", ""),
        ("future_date_60", ""),
        ("future_date_90", ""),
        ("future_date_365", ""),
        ("user_id", ""),
        ("device_id", ""),
        ("session_id", ""),
        ("consent_id", ""),
        ("permission_id", ""),
        ("account_id", ""),
        ("membership_id", ""),
        ("category_id", ""),
        ("vendor_id", ""),
        ("transaction_id", ""),
        ("inference_request_id", ""),
        ("income_source_id", ""),
        ("tag_id", ""),
        ("participant_id", ""),
        ("budget_id", ""),
        ("shared_budget_id", ""),
        ("team_id", ""),
        ("team_member_id", ""),
        ("contact_id", ""),
        ("debt_id", ""),
        ("debt_installment_id", ""),
        ("fx_rate_id", ""),
        ("goal_id", ""),
        ("goal_contribution_id", ""),
        ("goal_milestone_id", ""),
        ("shared_goal_id", ""),
        ("goal_contribution_idempotency_key", "postman-goal-contribution-001"),
        ("document_id", ""),
        ("ocr_request_id", ""),
        ("document_link_id", ""),
        ("ocr_idempotency_key", "postman-ocr-001"),
        ("payment_template_id", ""),
        ("schedule_run_id", ""),
        ("payment_intent_id", ""),
        ("open_banking_connection_id", ""),
        ("open_banking_external_account_id", ""),
        ("monthly_close_id", ""),
        ("report_snapshot_id", ""),
        ("report_export_id", ""),
        ("report_download_token", ""),
        ("payout_id", ""),
        ("alert_id", ""),
        ("alert_rule_id", ""),
        ("notification_id", ""),
        ("outbox_event_id", ""),
        ("social_provider", "google"),
        ("bank_provider", "local_mock"),
        ("payment_provider", "local_fake"),
    ]

    sections: list[dict] = []
    sections.append(
        folder(
            "00 - Start Here and Runtime",
            "Punto de entrada. Verifica runtime antes de ejecutar flujos. No contiene secretos ni valores cloud.",
            [
                request("Health", "GET", "/api/runtime/health/", "Liveness HTTP del proceso API.", public=True),
                request("Readiness", "GET", "/api/runtime/readiness/", "Readiness de API y PostgreSQL.", public=True),
            ],
        )
    )

    auth_items = [
        request(
            "Register",
            "POST",
            "/api/identity/users/auth/register/",
            "Crea un usuario local y dispara su bootstrap financiero asincrono mediante outbox.",
            public=True,
            body={
                "full_name": "Usuario Prueba",
                "email": "{{email}}",
                "password": "{{password}}",
                "password2": "{{password}}",
                "preferred_currency": "COP",
                "timezone_name": "America/Bogota",
                "locale": "es_CO",
            },
            expected=(201, 400),
        ),
        request(
            "Login",
            "POST",
            "/api/identity/users/auth/login/",
            "Obtiene JWT. Acepta email o username en username.",
            public=True,
            body={"username": "{{email}}", "password": "{{password}}"},
            capture=("access_token", "data.access"),
            extra_tests=[
                "if (pm.response.code === 200 && pm.response.text()) {",
                "  const data = pm.response.json();",
                "  if (data.refresh) pm.collectionVariables.set('refresh_token', data.refresh);",
                "}",
            ],
        ),
        request(
            "Refresh Token",
            "POST",
            "/api/identity/users/auth/refresh/",
            "Renueva el access token.",
            public=True,
            body={"refresh": "{{refresh_token}}"},
            capture=("access_token", "data.access"),
        ),
        request("Logout", "POST", "/api/identity/users/auth/logout/", "Revoca la sesion JWT actual.", body={"refresh": "{{refresh_token}}"}),
        request("Set Password", "POST", "/api/identity/users/auth/set-password/", "Define o cambia password autenticado.", body={"new_password": "{{password}}", "new_password2": "{{password}}"}),
        request("Request Password Reset", "POST", "/api/identity/users/auth/password-reset/request/", "Solicita enlace de recuperacion con respuesta no enumerable.", public=True, body={"email": "{{email}}"}),
        request("Request Recovery Code", "POST", "/api/identity/users/auth/password-recovery/request-code/", "Solicita OTP de recuperacion por canal configurado.", public=True, body={"phone_number": "+573001234567"}),
        request("Confirm Recovery Code", "POST", "/api/identity/users/auth/password-recovery/confirm-code/", "Consume OTP y cambia password.", public=True, body={"phone_number": "+573001234567", "code": "000000", "password": "{{password}}", "password2": "{{password}}"}, expected=(200, 400)),
        request("Request Step Up", "POST", "/api/identity/users/auth/step-up/request-code/", "Solicita verificacion reforzada para una sesion.", body={"session_id": "{{session_id}}"}, expected=(200, 400)),
        request("Confirm Step Up", "POST", "/api/identity/users/auth/step-up/confirm-code/", "Confirma verificacion reforzada.", body={"session_id": "{{session_id}}", "code": "000000"}, expected=(200, 400)),
        request("Social Providers", "GET", "/api/identity/users/auth/social/providers/", "Lista proveedores sociales y si estan configurados.", public=True),
        request("My Social Identities", "GET", "/api/identity/users/auth/social/identities/", "Lista identidades sociales vinculadas."),
        request("Start Social Auth", "GET", "/api/identity/users/auth/social/{{social_provider}}/start/", "Inicia OAuth para el proveedor seleccionado.", public=True, expected=(200, 302, 400, 503)),
        request("Exchange Social Handoff", "POST", "/api/identity/users/auth/social/exchange/", "Intercambia handoff validado por tokens propios.", public=True, body={"provider": "{{social_provider}}", "handoff": "replace-me"}, expected=(200, 400)),
        request("Unlink Social Identity", "DELETE", "/api/identity/users/auth/social/{{social_provider}}/unlink/", "Desvincula una identidad social sin borrar el usuario.", expected=(200, 204, 400)),
    ]
    sections.append(folder("01 - Authentication and User Access", "Autenticacion, recuperacion, step-up y proveedores sociales.", auth_items))

    mobile_items = [
        request(
            "Mobile Bootstrap",
            "GET",
            "/api/mobile/bootstrap/",
            "BFF versionado para hidratar la app. Tras registrar, repetir hasta que categories.data tenga elementos.",
            capture=("category_id", "(((((data.sections || {}).categories || {}).data || []).find((item) => item.type === 'expense')) || {}).id"),
            extra_tests=[
                "const categories = (((pm.response.json().sections || {}).categories || {}).data || []);",
                "pm.test('Bootstrap financiero disponible', function () {",
                "  pm.expect(categories.length, 'El outbox aun procesa el registro; reintenta este request').to.be.above(0);",
                "});",
            ],
        ),
        request("Mobile Sync State", "GET", "/api/mobile/sync-state/", "Decide si mobile debe refrescar secciones."),
        request("Mobile Markets", "GET", "/api/mobile/markets/", "Snapshot ligero de mercados y FX para mobile."),
    ]
    sections.append(folder("02 - Mobile BFF", "Contratos de arranque y sincronizacion incremental de Flutter.", mobile_items))

    identity_items = [
        request("Me", "GET", "/api/identity/users/me/", "Perfil del usuario autenticado.", capture=("user_id", "data.id")),
        request("Dashboard", "GET", "/api/identity/users/dashboard/", "Vista agregada inicial del producto."),
        request("Complete Onboarding", "POST", "/api/identity/users/onboarding/complete/", "Marca onboarding completo con preferencias iniciales.", body={"preferred_currency": "COP", "timezone_name": "America/Bogota", "locale": "es_CO"}, expected=(200, 400)),
        request("Identity Event Contract", "GET", "/api/identity/users/event-contract/", "Catalogo versionado de eventos de identidad."),
        folder(
            "Devices",
            "Inventario y confianza de dispositivos.",
            [
                request("List Devices", "GET", "/api/identity/devices/dispositivos/", "Lista dispositivos registrados."),
                request("Device Summary", "GET", "/api/identity/devices/dispositivos/summary/", "Resumen de riesgo y confianza."),
                request("Suspicious Devices", "GET", "/api/identity/devices/dispositivos/suspicious/", "Filtra dispositivos sospechosos."),
                request("Register Device", "POST", "/api/identity/devices/dispositivos/register_device/", "Registra fingerprint de dispositivo.", body={"fingerprint": "postman-device", "device_type": "desktop", "platform": "windows", "app_version": "local"}, capture=("device_id", "data.id"), expected=(200, 201, 400)),
                request("Trust Device", "POST", "/api/identity/devices/dispositivos/{{device_id}}/trust_device/", "Eleva confianza tras step-up.", body={}, expected=(200, 400)),
                request("Revoke Device", "POST", "/api/identity/devices/dispositivos/{{device_id}}/revoke/", "Revoca un dispositivo y sesiones asociadas.", body={"reason": "postman-test"}, expected=(200, 400)),
            ],
        ),
        folder(
            "Sessions",
            "Ciclo de vida y revocacion de sesiones.",
            [
                request("List Sessions", "GET", "/api/identity/sessions/sesiones/", "Lista sesiones del usuario."),
                request("Active Sessions", "GET", "/api/identity/sessions/sesiones/active/", "Lista sesiones activas."),
                request("Session Summary", "GET", "/api/identity/sessions/sesiones/summary/", "Resumen operativo de sesiones."),
                request("Touch Session", "POST", "/api/identity/sessions/sesiones/{{session_id}}/touch/", "Actualiza actividad de sesion.", body={}, expected=(200, 400)),
                request("Revoke Session", "POST", "/api/identity/sessions/sesiones/{{session_id}}/revoke/", "Revoca una sesion concreta.", body={"reason": "user_requested"}, expected=(200, 400)),
                request("Revoke Other Sessions", "POST", "/api/identity/sessions/sesiones/revoke_others/", "Conserva la sesion actual y revoca las demas.", body={}, expected=(200, 400)),
                request("Revoke All Sessions", "POST", "/api/identity/sessions/sesiones/revoke_all/", "Revoca todas las sesiones del usuario.", body={"reason": "security_reset"}, expected=(200, 400)),
            ],
        ),
        folder(
            "Consents",
            "Permisos concedidos a proveedores e integraciones.",
            [
                request("List Consents", "GET", "/api/identity/consents/consentimientos/", "Lista consentimientos."),
                request("Active Consents", "GET", "/api/identity/consents/consentimientos/active/", "Consentimientos vigentes."),
                request("Consent Summary", "GET", "/api/identity/consents/consentimientos/summary/", "Resumen de consentimientos."),
                request("Expiring Consents", "GET", "/api/identity/consents/consentimientos/expiring/", "Consentimientos proximos a expirar."),
                request("Grant Consent", "POST", "/api/identity/consents/consentimientos/grant/", "Concede permiso versionado a un proveedor.", body={"provider": "{{bank_provider}}", "scope": ["accounts", "transactions"], "purpose": "financial_data_sync"}, capture=("consent_id", "data.id"), expected=(200, 201, 400)),
                request("Revoke Consent", "POST", "/api/identity/consents/consentimientos/{{consent_id}}/revoke/", "Revoca consentimiento e inicia teardown.", body={"reason": "user_requested"}, expected=(200, 202, 400)),
            ],
        ),
        folder(
            "Permissions",
            "Grants de permisos de producto y colaboracion.",
            [
                request("My Grants", "GET", "/api/identity/permissions/grants/mine/", "Permisos asignados al usuario."),
                request("Effective Permissions", "GET", "/api/identity/permissions/grants/effective/", "Permisos efectivos despues de resolver scopes."),
                request("Permission Summary", "GET", "/api/identity/permissions/grants/summary/", "Resumen de grants."),
                request("List Grants", "GET", "/api/identity/permissions/grants/", "Lista administrativa de grants."),
            ],
        ),
        folder(
            "Admin Users",
            "Solo administradores. Gestion de estado, verificacion y plan.",
            [
                request("List Users Admin", "GET", "/api/identity/users/admin/users/", "Lista usuarios para soporte/admin.", expected=(200, 403)),
                request("Verify User", "POST", "/api/identity/users/admin/users/{{user_id}}/verify/", "Marca usuario verificado.", body={}, expected=(200, 403)),
                request("Suspend User", "POST", "/api/identity/users/admin/users/{{user_id}}/suspend/", "Suspende acceso, audita el motivo y revoca todas las sesiones sin borrar datos.", body={"reason": "risk_review"}, expected=(200, 400, 403)),
                request("Activate User", "POST", "/api/identity/users/admin/users/{{user_id}}/activate/", "Reactiva usuario suspendido.", body={}, expected=(200, 403)),
                request("Set User Plan", "POST", "/api/identity/users/admin/users/{{user_id}}/set_plan/", "Actualiza plan efectivo.", body={"plan": "free"}, expected=(200, 400, 403)),
            ],
        ),
    ]
    sections.append(folder("03 - Identity, Security and User Types", "Perfil, dispositivos, sesiones, consentimientos, permisos y administracion.", identity_items))

    account_items = [
        request("List Accounts", "GET", "/api/finance/accounts/cuentas/", "Lista cuentas visibles y reutiliza la primera en flujos encadenados.", capture=("account_id", "((data.results || data)[0] || {}).id")),
        request("Account Summary", "GET", "/api/finance/accounts/cuentas/summary/", "Resumen de balances y monedas."),
        request("Account Plan Usage", "GET", "/api/finance/accounts/cuentas/plan_usage/", "Uso y limites del plan."),
        request("Account Operational Overview", "GET", "/api/finance/accounts/cuentas/operational_overview/", "Salud operativa del agregado."),
        request("Account Sync Overview", "GET", "/api/finance/accounts/cuentas/sync_overview/", "Estado de sincronizacion externa."),
        request("Account Event Contract", "GET", "/api/finance/accounts/cuentas/event_contract/", "Catalogo de eventos accounts.*."),
        request("Create Cash Account", "POST", "/api/finance/accounts/cuentas/", "Crea cuenta manual de efectivo.", body={"name": "Efectivo Postman", "currency": "COP", "type": "cash", "ownership": "owned", "initial_balance": "1000000.00"}, capture=("account_id", "data.id"), expected=(201, 400)),
        request("Retrieve Account", "GET", "/api/finance/accounts/cuentas/{{account_id}}/", "Detalle de cuenta y permisos."),
        request("Set Primary Account", "POST", "/api/finance/accounts/cuentas/{{account_id}}/set_primary/", "Marca cuenta principal.", body={}, expected=(200, 400)),
        request("Recalculate Balance", "POST", "/api/finance/accounts/cuentas/{{account_id}}/recalc_balance/", "Recalcula cache desde ledger para soporte.", body={"reason": "postman_reconciliation"}, expected=(200, 400)),
        request("Freeze Account", "POST", "/api/finance/accounts/cuentas/{{account_id}}/freeze/", "Congela mutaciones sensibles.", body={"reason": "user_requested"}, expected=(200, 400)),
        request("Unfreeze Account", "POST", "/api/finance/accounts/cuentas/{{account_id}}/unfreeze/", "Descongela cuenta.", body={}, expected=(200, 400)),
        request("Archive Account", "POST", "/api/finance/accounts/cuentas/{{account_id}}/archive/", "Archiva cuenta sin borrar historial.", body={"reason": "user_requested"}, expected=(200, 400)),
        request("Link Bank Provider", "POST", "/api/finance/accounts/cuentas/{{account_id}}/link_external_source/", "Vincula referencia externa normalizada.", body={"provider": "{{bank_provider}}", "external_id": "provider-account-001", "external_mask": "1234", "external_type": "checking", "allow_auto_sync": True}, expected=(200, 400)),
        request("Schedule Account Sync", "POST", "/api/finance/accounts/cuentas/{{account_id}}/schedule_sync/", "Encola sync durable sin escribir ledger directamente.", body={"trigger": "postman", "force": False}, expected=(200, 202, 400)),
        folder(
            "Sharing and Memberships",
            "Colaboracion explicita sobre cuentas.",
            [
                request("List Account Memberships", "GET", "/api/finance/accounts/membresias-cuenta/", "Lista membresias visibles."),
                request("Account Members", "GET", "/api/finance/accounts/cuentas/{{account_id}}/members/", "Miembros de una cuenta."),
                request("Create Account Invitation", "POST", "/api/finance/accounts/membresias-cuenta/", "Invita usuario con rol y permisos.", body={"account": "{{account_id}}", "email": "invitado@example.com", "role": "viewer"}, capture=("membership_id", "data.id"), expected=(201, 400)),
                request("Accept Account Invitation", "POST", "/api/finance/accounts/membresias-cuenta/{{membership_id}}/accept_invitation/", "Acepta invitacion versionada.", body={"invitation_token": "replace-me"}, expected=(200, 400, 403)),
                request("Revoke Account Membership", "POST", "/api/finance/accounts/membresias-cuenta/{{membership_id}}/revoke/", "Revoca acceso compartido.", body={"reason": "owner_requested"}, expected=(200, 400, 403)),
            ],
        ),
        folder(
            "Intelligence and Reconciliation",
            "Read models, snapshots y degradaciones operativas.",
            [
                request("Latest Balance Snapshot", "GET", "/api/finance/accounts/snapshots-balance/latest/?account={{account_id}}", "Ultimo snapshot de reconciliacion."),
                request("Snapshot Policy", "GET", "/api/finance/accounts/snapshots-balance/policy/", "Politica de retencion de snapshots."),
                request("Portfolio Overview", "GET", "/api/finance/accounts/snapshots-portafolio-cuenta/overview/", "Proyeccion consolidada de portafolio."),
                request("Portfolio Health", "GET", "/api/finance/accounts/snapshots-portafolio-cuenta/health/", "Salud de proyecciones derivadas."),
                request("Risk Snapshots", "GET", "/api/finance/accounts/snapshots-riesgo-cuenta/", "Snapshots de riesgo."),
                request("Currency Exposures", "GET", "/api/finance/accounts/exposiciones-moneda-cuenta/", "Exposicion agregada por moneda."),
                request("Account Product Signals", "GET", "/api/finance/accounts/senales-producto-cuenta/", "Senales de producto derivadas."),
                request("Balance Fallback Health", "GET", "/api/finance/accounts/fallbacks-balance-cuenta/health/", "Degradaciones del balance incremental."),
            ],
        ),
    ]
    sections.append(folder("04 - Accounts, Cash and Sharing", "Cuentas manuales/conectadas, efectivo, sharing, sync e inteligencia.", account_items))

    transaction_items = [
        request("List Transactions", "GET", "/api/finance/transactions/transactions/", "Ledger visible del usuario."),
        request("Transactions by Account", "GET", "/api/finance/transactions/transactions/?account={{account_id}}", "Consulta estandar por cuenta."),
        request("Transactions by Date", "GET", "/api/finance/transactions/transactions/?date_from={{current_date}}&date_to={{current_date}}", "Consulta estandar por rango de fechas."),
        request("Pending Transactions", "GET", "/api/finance/transactions/transactions/?status=pending", "Movimientos pendientes de confirmacion o proceso."),
        request("Expense Transactions", "GET", "/api/finance/transactions/transactions/?type=expense", "Consulta estandar de gastos."),
        request("Create Manual Expense", "POST", "/api/finance/transactions/transactions/", "Escritura manual canonica del ledger.", body={"account": "{{account_id}}", "category": "{{category_id}}", "type": "expense", "status": "posted", "amount": "25000.00", "date": "{{current_date}}", "description": "Compra local", "channel": "manual", "data_origin": "manual", "confirmed": True}, capture=("transaction_id", "data.id"), expected=(201, 400)),
        request("Retrieve Transaction", "GET", "/api/finance/transactions/transactions/{{transaction_id}}/", "Detalle contable y metadata externa."),
        request("Confirm Transaction", "POST", "/api/finance/transactions/transactions/{{transaction_id}}/marcar_confirmada/", "Confirma borrador pendiente.", body={}, expected=(200, 400)),
        request("Reassign Account", "POST", "/api/finance/transactions/transactions/{{transaction_id}}/reasignar_cuenta/", "Reasigna cuenta con reglas de balance.", body={"account_id": "{{account_id}}", "reason": "user_correction"}, expected=(200, 400)),
        request("Register Refund", "POST", "/api/finance/transactions/transactions/{{transaction_id}}/registrar_reembolso/", "Registra reembolso relacionado sin borrar el original.", body={"amount": "25000.00", "date": "{{current_date}}", "reason": "merchant_refund"}, expected=(200, 201, 400)),
        request("Add Transaction Comment", "POST", "/api/finance/transactions/transactions/{{transaction_id}}/add_comment/", "Agrega comentario trazable.", body={"comment": "Revision desde Postman"}, expected=(200, 201, 400)),
        folder(
            "Voice and AI Inference",
            "La voz publica entra por inference-request; nunca escribe ledger final directamente.",
            [
                request("Create Voice Inference Request", "POST", "/api/finance/transactions/inference-requests/", "Crea solicitud durable de voz.", body={"account_id": "{{account_id}}", "audio_object_ref": "local://audio/postman-voice-001.m4a", "audio_content_type": "audio/mp4", "audio_duration_ms": 8400, "language": "es-CO", "provider": "voice_ai"}, capture=("inference_request_id", "(data.inference_request || data).id"), expected=(200, 201, 400), headers=[("Idempotency-Key", "{{request_id}}")]),
                request("List Inference Requests", "GET", "/api/finance/transactions/inference-requests/", "Estado de inferencias del usuario."),
                request("Retry Inference Request", "POST", "/api/finance/transactions/inference-requests/{{inference_request_id}}/retry/", "Reintenta estados fallidos permitidos.", body={}, expected=(200, 202, 400)),
                request("Reject Inferred Draft", "POST", "/api/finance/transactions/transactions/{{transaction_id}}/rechazar_inferida/", "Rechaza borrador inferido pendiente.", body={"reason": "user_rejected"}, expected=(200, 400)),
            ],
        ),
        folder(
            "Classification and Participants",
            "Catalogos auxiliares y gastos con terceros.",
            [
                request("List Income Sources", "GET", "/api/finance/transactions/income-sources/", "Fuentes de ingreso."),
                request("List Tags", "GET", "/api/finance/transactions/tags/", "Etiquetas de transacciones."),
                request("List Participants", "GET", "/api/finance/transactions/transaction-participants/", "Participantes y obligaciones compartidas."),
                request("Participants by Contact", "GET", "/api/finance/transactions/transaction-participants/by_contact/?contact={{contact_id}}", "Movimientos compartidos por contacto."),
                request("Participant Summary by Contact", "GET", "/api/finance/transactions/transaction-participants/summary_by_contact/", "Resumen de saldos sociales."),
                request("Mark Participant Settled", "POST", "/api/finance/transactions/transaction-participants/{{participant_id}}/mark_settled/", "Marca obligacion entre participantes como saldada.", body={"settled_at": "{{current_date}}"}, expected=(200, 400)),
            ],
        ),
    ]
    sections.append(folder("05 - Transactions and Ledger", "Ledger canonico, consultas estandar, voz, clasificacion y participantes.", transaction_items))

    budget_items = [
        request("List Category Budgets", "GET", "/api/finance/budgets/presupuestos-categoria/?month={{current_month}}", "Presupuestos personales del mes."),
        request("Create Category Budget", "POST", "/api/finance/budgets/presupuestos-categoria/", "Crea presupuesto fijo con metricas dinamicas.", body={"month": "{{current_month}}", "category": "{{category_id}}", "amount": "500000.00", "alert_thresholds": [50, 80, 100]}, capture=("budget_id", "data.id"), expected=(201, 400)),
        request("Retrieve Category Budget", "GET", "/api/finance/budgets/presupuestos-categoria/{{budget_id}}/", "Detalle y metricas del presupuesto."),
        request("Merge Budget Period", "POST", "/api/finance/budgets/presupuestos-categoria/merge-period/", "Merge idempotente del periodo.", body={"month": "{{current_month}}", "items": [{"category": "{{category_id}}", "amount": "500000.00", "alert_thresholds": [50, 80, 100]}]}, expected=(200, 400)),
        request("Replace Budget Period", "POST", "/api/finance/budgets/presupuestos-categoria/replace-period/", "Reemplaza declarativamente el periodo.", body={"month": "{{current_month}}", "items": [{"category": "{{category_id}}", "amount": "500000.00"}]}, expected=(200, 400)),
        request("Monthly Budget Overview", "GET", "/api/finance/budgets/resumen-mensual/?month={{current_month}}", "Planned, actual, committed y disponible."),
        folder(
            "Shared Budgets",
            "Presupuestos colaborativos con acciones explicitas.",
            [
                request("List Shared Budgets", "GET", "/api/finance/budgets/presupuestos-compartidos/?month={{current_month}}", "Lista presupuestos compartidos."),
                request("Create Shared Budget", "POST", "/api/finance/budgets/presupuestos-compartidos/", "Crea presupuesto de equipo.", body={"team": "{{team_id}}", "name": "Viaje compartido", "month": "{{current_month}}", "amount": "1000000.00", "alert_thresholds": [50, 80, 100]}, capture=("shared_budget_id", "data.id"), expected=(201, 400)),
                request("Link Transaction", "POST", "/api/finance/budgets/presupuestos-compartidos/{{shared_budget_id}}/link-transaction/", "Vincula gasto mediante accion explicita.", body={"transaction_id": "{{transaction_id}}"}, expected=(200, 400)),
                request("Unlink Transaction", "POST", "/api/finance/budgets/presupuestos-compartidos/{{shared_budget_id}}/unlink-transaction/", "Retira vinculacion sin borrar ledger.", body={"transaction_id": "{{transaction_id}}"}, expected=(200, 400)),
                request("Link Payment Template", "POST", "/api/finance/budgets/presupuestos-compartidos/{{shared_budget_id}}/link-template/", "Incluye compromiso programado.", body={"payment_template_id": "{{payment_template_id}}"}, expected=(200, 400)),
            ],
        ),
    ]
    sections.append(folder("06 - Budgets", "Presupuesto personal y compartido con metricas del ledger.", budget_items))

    scheduled_items = [
        request("List Payment Templates", "GET", "/api/payments/scheduled/templates/", "Plantillas recurrentes canonicas."),
        request("Create Payment Template", "POST", "/api/payments/scheduled/templates/", "Programa un pago futuro.", body={"name": "Servicio mensual", "payment_type": "bill", "amount_mode": "fixed", "default_amount": "45000.00", "currency": "COP", "account": "{{account_id}}", "category": "{{category_id}}", "cadence": "monthly", "next_run_at": "{{current_date}}T15:00:00-05:00", "is_active": True}, capture=("payment_template_id", "data.id"), expected=(201, 400)),
        request("Request Template Run", "POST", "/api/payments/scheduled/templates/{{payment_template_id}}/request-run/", "Solicita corrida durable de plantilla.", body={}, expected=(200, 201, 202, 400)),
        request("List Schedule Runs", "GET", "/api/payments/scheduled/runs/", "Corridas materializadas pendientes o procesadas."),
        request("Operational Metrics", "GET", "/api/payments/scheduled/runs/operational-metrics/", "Metricas de corridas, retries y vencimientos."),
        request("Materialize Payment Intent", "POST", "/api/payments/scheduled/runs/{{schedule_run_id}}/materialize-intent/", "Convierte corrida en intent idempotente.", body={"provider": "{{payment_provider}}", "rail": "other"}, expected=(200, 201, 400)),
        request("Mark Run Paid", "POST", "/api/payments/scheduled/runs/{{schedule_run_id}}/mark-paid/", "Marca corrida pagada y materializa ledger.", body={"paid_at": "{{current_date}}"}, expected=(200, 400)),
        request("Mark Paid Outside", "POST", "/api/payments/scheduled/runs/{{schedule_run_id}}/mark-paid-outside/", "Registra pago fuera de Vexxo.", body={"paid_at": "{{current_date}}", "notes": "Pago externo"}, expected=(200, 400)),
        request("Postpone Run", "POST", "/api/payments/scheduled/runs/{{schedule_run_id}}/postpone/", "Pospone vencimiento con trazabilidad.", body={"due_on": "{{current_date}}", "reason": "user_requested"}, expected=(200, 400)),
        request("Skip Run", "POST", "/api/payments/scheduled/runs/{{schedule_run_id}}/skip/", "Omite una corrida sin borrar plantilla.", body={"reason": "user_requested"}, expected=(200, 400)),
        request("Retry Run", "POST", "/api/payments/scheduled/runs/{{schedule_run_id}}/retry/", "Reintenta corrida fallida.", body={}, expected=(200, 202, 400)),
        request("Cancel Run", "POST", "/api/payments/scheduled/runs/{{schedule_run_id}}/cancel/", "Cancela corrida pendiente.", body={"reason": "user_requested"}, expected=(200, 400)),
    ]
    sections.append(folder("07 - Scheduled Payments", "Plantillas, corridas, vencimientos y materializacion de pagos.", scheduled_items))

    payment_items = [
        request("List Payment Intents", "GET", "/api/payments/intents/intents/", "Intents visibles para el usuario."),
        request("Pricing Preview", "POST", "/api/payments/intents/intents/pricing-preview/", "Calcula fees antes de crear intent.", body={"amount": "30000.00", "provider": "{{payment_provider}}", "rail": "other", "country": "CO", "payment_type": "other"}, expected=(200, 400)),
        request("Create Payment Intent", "POST", "/api/payments/intents/intents/", "Crea intent idempotente sin reemplazar el ledger.", body={"account": "{{account_id}}", "amount": "30000.00", "currency": "COP", "provider": "{{payment_provider}}", "payment_type": "other", "rail": "other", "external_reference": "postman-order-{{$timestamp}}", "beneficiary_name": "Comercio Demo", "beneficiary_document": "900123456", "beneficiary_account_ref": "benef-001", "idempotency_key": "{{request_id}}"}, capture=("payment_intent_id", "data.id"), expected=(201, 400)),
        request("Retrieve Payment Intent", "GET", "/api/payments/intents/intents/{{payment_intent_id}}/", "Estado actual del intent."),
        request("List Payouts", "GET", "/api/payments/intents/payouts/", "Lotes de dispersion."),
        request("Create Payout Batch", "POST", "/api/payments/intents/payouts/", "Crea lote de payout con instrucciones.", body={"provider": "{{payment_provider}}", "rail": "bank_transfer", "currency": "COP", "instructions": [{"beneficiary_name": "Proveedor Demo", "beneficiary_document": "900999111", "beneficiary_account_ref": "acct-001", "amount": "10000.00", "external_reference": "postman-payout-{{$timestamp}}"}]}, capture=("payout_id", "data.id"), expected=(201, 400)),
        request("Provider Contracts", "GET", "/api/payments/intents/providers/contracts/", "Catalogo de contratos PSP."),
        request("Provider Contract", "GET", "/api/payments/intents/providers/{{payment_provider}}/contract/", "Contrato y capacidades de un PSP.", expected=(200, 404)),
        request("List Callback Receipts", "GET", "/api/payments/intents/callback-receipts/", "Receipts autenticados de callbacks."),
        request("List Settlements", "GET", "/api/payments/intents/settlements/", "Settlement y conciliacion de PSP."),
        request("List Operational Cases", "GET", "/api/payments/intents/operational-cases/", "Casos que requieren soporte."),
        request("Payment Worker Report", "POST", "/api/payments/intents/worker-report/", "Callback interno normalizado del worker.", internal=True, body={"payment_intent_id": "{{payment_intent_id}}", "status": "processing", "provider": "{{payment_provider}}", "provider_metadata": {"source": "postman"}}, expected=(200, 400, 401, 403)),
    ]
    sections.append(folder("08 - Payments and Providers", "Pricing, intents, payouts, callbacks, settlement y contratos por proveedor.", payment_items))

    alert_items = [
        request("List Alerts", "GET", "/api/alerts/alertas/", "Alertas activas del usuario.", capture=("alert_id", "((data.results || data)[0] || {}).id")),
        request("Retrieve Alert", "GET", "/api/alerts/alertas/{{alert_id}}/", "Detalle y payload de una alerta."),
        request("Mark Alert Read", "POST", "/api/alerts/alertas/{{alert_id}}/mark_read/", "Marca alerta leida.", body={}, expected=(200, 400)),
        request("Resolve Alert", "POST", "/api/alerts/alertas/{{alert_id}}/mark_resolved/", "Resuelve alerta.", body={}, expected=(200, 400)),
        request("Snooze Alert", "POST", "/api/alerts/alertas/{{alert_id}}/snooze/", "Pospone alerta.", body={"until": "{{current_date}}T23:59:59-05:00"}, expected=(200, 400)),
        request("List Alert Rules", "GET", "/api/alerts/rules/reglas/", "Reglas configurables de alertas."),
        request("Create Alert Rule", "POST", "/api/alerts/rules/reglas/", "Crea regla de alerta.", body={"name": "Gasto alto", "event_type": "transactions.created.v1", "is_active": True, "conditions": {"amount_gte": "500000.00"}}, capture=("alert_rule_id", "data.id"), expected=(201, 400)),
    ]
    sections.append(folder("09 - Alerts and Rules", "Alertas de producto, acciones y reglas configurables.", alert_items))

    notification_items = [
        request("List Notifications", "GET", "/api/notifications/deliveries/entregas-notificacion/", "Inbox durable.", capture=("notification_id", "((data.results || data)[0] || {}).id")),
        request("Notification Stats", "GET", "/api/notifications/deliveries/entregas-notificacion/stats/", "Conteos del inbox."),
        request("Mark Notification Read", "POST", "/api/notifications/deliveries/entregas-notificacion/{{notification_id}}/mark_read/", "Marca entrega leida.", body={}, expected=(200, 400)),
        request("Mark All Notifications Read", "POST", "/api/notifications/deliveries/entregas-notificacion/mark_all_read/", "Limpia pendientes de lectura.", body={}),
        request("My Notification Preferences", "GET", "/api/notifications/preferences/me/", "Preferencias por canal."),
        request("Update Notification Preferences", "PUT", "/api/notifications/preferences/me/", "Actualiza preferencias del usuario.", body={"email_enabled": True, "push_enabled": True, "in_app_enabled": True}, expected=(200, 400)),
        request("Latest Realtime Signal", "GET", "/api/realtime/consumers/senales-realtime/latest/", "Ultima senal ligera para polling."),
        request("Realtime Signal Stats", "GET", "/api/realtime/consumers/senales-realtime/stats/", "Metricas de senales."),
    ]
    sections.append(folder("10 - Notifications and Realtime", "Inbox durable, preferencias y senales de UX.", notification_items))

    document_items = [
        request("List Documents", "GET", "/api/documents/files/", "Lista documentos privados del usuario."),
        request(
            "Upload Document",
            "POST",
            "/api/documents/files/",
            "Carga multipart privada; selecciona un archivo local en el campo file.",
            formdata=[
                {"key": "file", "type": "file", "src": ""},
                {"key": "capture_source", "type": "text", "value": "postman"},
            ],
            capture=("document_id", "data.id"),
        ),
        request("Retrieve Document", "GET", "/api/documents/files/{{document_id}}/", "Consulta metadata y ultimo OCR del owner."),
        request(
            "Request Document OCR",
            "POST",
            "/api/documents/files/{{document_id}}/request-ocr/",
            "Encola OCR durable; texto cliente es opcional y no materializa ledger.",
            body={"client_extracted_text": "", "client_structured_hint": {}},
            headers=[("Idempotency-Key", "{{ocr_idempotency_key}}")],
            capture=("ocr_request_id", "data.id"),
            expected=(200, 202),
        ),
        request(
            "Link Document to Transaction",
            "POST",
            "/api/documents/transaction-links/",
            "Vincula evidencia con una transaccion del mismo owner.",
            body={"document": "{{document_id}}", "transaction": "{{transaction_id}}", "relationship": "receipt"},
            capture=("document_link_id", "data.id"),
            expected=(201, 400),
        ),
        request(
            "Correct OCR Field",
            "POST",
            "/api/documents/files/{{document_id}}/ocr-corrections/",
            "Agrega una correccion versionada sin sobrescribir el lineage OCR.",
            body={"ocr_request": "{{ocr_request_id}}", "field_name": "merchant_name", "value": "Comercio corregido", "notes": "Revision manual Postman"},
            expected=(201, 400, 404),
        ),
        request("List Document Links", "GET", "/api/documents/transaction-links/", "Lista vinculos documentales owner-scoped."),
        request("Soft Delete Document", "DELETE", "/api/documents/files/{{document_id}}/", "Borrado logico que preserva trazabilidad.", expected=(204, 404)),
    ]
    sections.append(folder("11 - Documents and OCR", "Archivos privados, OCR durable y vinculacion al ledger.", document_items))

    social_items = [
        request("List Contacts", "GET", "/api/contacts/", "Contactos del usuario."),
        request("Create Contact", "POST", "/api/contacts/", "Crea contacto para gastos compartidos.", body={"name": "Contacto Postman", "email": "contacto@example.com", "phone": "+573001112233"}, capture=("contact_id", "data.id"), expected=(201, 400)),
        request("Archive Contact", "POST", "/api/contacts/{{contact_id}}/archive/", "Archiva contacto sin borrar relaciones.", body={}, expected=(200, 400)),
        request("Unarchive Contact", "POST", "/api/contacts/{{contact_id}}/unarchive/", "Restaura contacto archivado.", body={}, expected=(200, 400)),
        request("List Teams", "GET", "/api/social/teams/equipos/", "Equipos visibles."),
        request("Create Team", "POST", "/api/social/teams/equipos/", "Crea equipo para colaboracion.", body={"name": "Equipo Postman", "description": "Pruebas locales"}, capture=("team_id", "data.id"), expected=(201, 400)),
        request("List Team Members", "GET", "/api/social/teams/miembros/?team={{team_id}}", "Miembros del equipo."),
        request("Add Team Member", "POST", "/api/social/teams/miembros/", "Agrega miembro a equipo.", body={"team": "{{team_id}}", "user": "{{user_id}}", "role": "member"}, capture=("team_member_id", "data.id"), expected=(201, 400)),
    ]
    sections.append(folder("11 - Contacts and Teams", "Contactos, equipos y base social para gastos compartidos.", social_items))

    catalog_items = [
        request("List Categories", "GET", "/api/finance/categories/categorias/", "Categorias personales; nunca devuelve categorias de otro owner.", capture=("category_id", "(((data.results || data).find((item) => item.type === 'expense')) || {}).id")),
        request("List Vendors", "GET", "/api/finance/vendors/proveedores/", "Comercios/proveedores normalizados."),
        request("Create Vendor", "POST", "/api/finance/vendors/proveedores/", "Crea comercio para clasificacion.", body={"name": "Comercio Postman", "tax_id": "900123456"}, capture=("vendor_id", "data.id"), expected=(201, 400)),
        request("List FX Rates", "GET", "/api/finance/fx/tasas-fx/", "Tasas FX activas."),
        request("List Debts", "GET", "/api/finance/debts/deudas/", "Deudas del usuario."),
        request("Create Debt", "POST", "/api/finance/debts/deudas/", "Crea deuda y genera sus cuotas mediante el servicio explicito. El proveedor es opcional para que el flujo pueda ejecutarse de forma independiente.", body={"name": "Credito Postman", "principal": "1200000.00", "currency": "COP", "start_date": "{{current_date}}", "interest_rate": "0.0100", "interest_type": "fixed", "total_installments": 3, "frequency": "monthly"}, capture=("debt_id", "data.id"), expected=(201, 400)),
        request("List Debt Installments", "GET", "/api/finance/debts/cuotas-deuda/?debt={{debt_id}}", "Cuotas ligadas a deuda.", capture=("debt_installment_id", "((data.results || data)[0] || {}).id")),
        request("Restructure Debt", "POST", "/api/finance/debts/deudas/{{debt_id}}/restructure/", "Reemplaza solo el calendario pendiente y conserva historia pagada.", headers=[("Idempotency-Key", "postman-debt-restructure-001")], body={"effective_date": "{{current_date}}", "reason": "Reestructuracion controlada desde Postman", "new_terms": {"frequency": "monthly", "source": "postman"}, "installments": [{"due_date": "{{future_date_30}}", "amount_due": "400000.00"}, {"due_date": "{{future_date_60}}", "amount_due": "400000.00"}, {"due_date": "{{future_date_90}}", "amount_due": "400000.00"}]}, expected=(200, 201, 400)),
        request("List Goals", "GET", "/api/planning/goals/metas/", "Metas financieras."),
        request("Create Goal", "POST", "/api/planning/goals/metas/", "Crea una meta simple.", body={"name": "Fondo de emergencia", "target_amount": "5000000.00", "target_date": "{{future_date_365}}"}, capture=("goal_id", "data.id"), expected=(201, 400)),
        request("Pause Goal", "POST", "/api/planning/goals/metas/{{goal_id}}/pause/", "Pausa una meta mediante transicion explicita.", body={"reason": "Pausa de prueba local"}, expected=(200, 400)),
        request("Resume Goal", "POST", "/api/planning/goals/metas/{{goal_id}}/resume/", "Reactiva una meta pausada.", body={"reason": "Continuar plan de ahorro"}, expected=(200, 400)),
        request("Create Goal Contribution", "POST", "/api/planning/goals/aportes/", "Registra un aporte idempotente y recalcula progreso.", body={"goal": "{{goal_id}}", "amount": "250000.00", "contributed_on": "{{current_date}}", "note": "Aporte Postman"}, headers=[("Idempotency-Key", "{{goal_contribution_idempotency_key}}")], capture=("goal_contribution_id", "data.id"), expected=(200, 201, 400)),
        request("List Goal Contributions", "GET", "/api/planning/goals/aportes/?goal={{goal_id}}", "Lista el ledger de aportes de la meta."),
        request("Reverse Goal Contribution", "POST", "/api/planning/goals/aportes/{{goal_contribution_id}}/reverse/", "Revierte un aporte conservando evidencia.", body={"reason": "Correccion de prueba Postman"}, expected=(200, 400)),
        request("Create Goal Milestone", "POST", "/api/planning/goals/milestones/", "Crea un umbral auditable de progreso.", body={"goal": "{{goal_id}}", "name": "Primer millon", "target_amount": "1000000.00"}, capture=("goal_milestone_id", "data.id"), expected=(201, 400)),
        request("Goal Projection", "GET", "/api/planning/goals/metas/{{goal_id}}/projection/", "Proyeccion determinista; no modifica el ledger.", expected=(200, 404)),
        request("Create Shared Goal", "POST", "/api/planning/shared-goals/goals/", "Comparte una meta con un equipo sin transferir ownership.", body={"goal": "{{goal_id}}", "team": "{{team_id}}", "contribution_policy": "members"}, capture=("shared_goal_id", "data.id"), expected=(201, 400)),
        request("Shared Goal Projection", "GET", "/api/planning/shared-goals/goals/{{shared_goal_id}}/projection/", "Consulta la proyeccion bajo membresia activa.", expected=(200, 403, 404)),
    ]
    sections.append(folder("12 - Finance Catalogs and Planning", "Categorias, comercios, FX, deudas y metas.", catalog_items))

    report_items = [
        request("Cashflow Report", "GET", "/api/reports/reportes/cashflow?date_from={{current_date}}&date_to={{current_date}}", "Flujo de caja por periodo."),
        request("Expenses by Category", "GET", "/api/reports/reportes/gastos-por-categoria?month={{current_month}}", "Gasto agrupado por categoria."),
        request("Monthly Budgets Report", "GET", "/api/reports/reportes/presupuestos-mensuales?month={{current_month}}", "Reporte planned/actual/committed."),
        request("Create Immutable Snapshot", "POST", "/api/reports/snapshots/", "Congela una lectura versionada con hash canonico.", headers=[("Idempotency-Key", "postman-report-snapshot-001")], body={"report_type": "cashflow", "period_start": "{{current_date}}", "period_end": "{{current_date}}", "currency": "COP", "timezone": "America/Bogota"}, capture=("report_snapshot_id", "data.id"), expected=(200, 201, 400)),
        request("Close Previous Month", "POST", "/api/reports/monthly-closes/", "Cierre mensual inmutable del ultimo mes completado.", body={"month": "{{previous_month}}", "currency": "COP", "timezone": "America/Bogota"}, capture=("monthly_close_id", "data.id"), expected=(200, 201, 400)),
        request("List Monthly Closes", "GET", "/api/reports/monthly-closes/", "Lista cierres y lineage de regeneracion."),
        request("Create Encrypted Export", "POST", "/api/reports/exports/", "Crea un job durable desde un snapshot inmutable.", body={"snapshot_id": "{{report_snapshot_id}}", "format": "json"}, capture=("report_export_id", "data.id"), extra_tests=["if (pm.response.code === 202 && pm.response.text()) {", "  const payload = pm.response.json();", "  if (payload.download_token) pm.collectionVariables.set('report_download_token', payload.download_token);", "}"], expected=(202, 400, 404, 503)),
        request("Download Report Export", "GET", "/api/reports/exports/{{report_export_id}}/download/", "Descarga de un solo uso cuando el scheduler marque el export ready.", headers=[("X-Download-Token", "{{report_download_token}}")], expected=(200, 404)),
    ]
    sections.append(folder("13 - Reports and Standard Queries", "Consultas agregadas para producto, soporte y analitica.", report_items))

    open_banking_items = [
        request("List Open Banking Providers", "GET", "/api/integrations/open-banking/providers/", "Muestra por separado configured, certified y available; credenciales solas no habilitan un proveedor."),
        request("List Colombian Institutions", "GET", "/api/integrations/open-banking/institutions/?country=CO", "Catalogo canonico independiente del provider."),
        request("Create Local Mock Connection", "POST", "/api/integrations/open-banking/connections/", "Crea consentimiento local reproducible sin credenciales externas.", headers=[("Idempotency-Key", "postman-open-banking-001")], body={"provider": "local_mock", "institution_code": "vexxo-local-development", "institution_name": "Banco local de desarrollo", "country": "CO", "scopes": ["accounts", "balances", "transactions"]}, capture=("open_banking_connection_id", "data.public_id"), expected=(200, 201, 400)),
        request("Available Bank Accounts", "GET", "/api/integrations/open-banking/connections/{{open_banking_connection_id}}/available-accounts/", "Lista productos normalizados antes de importarlos.", capture=("open_banking_external_account_id", "((data.results || [])[0] || {}).external_account_id"), expected=(200, 404, 502)),
        request("Import Bank Account", "POST", "/api/integrations/open-banking/connections/{{open_banking_connection_id}}/import-account/", "Materializa una cuenta Vexxo enlazada al producto externo.", body={"external_account_id": "{{open_banking_external_account_id}}"}, expected=(201, 400, 404)),
        request("Request Bank Sync", "POST", "/api/integrations/open-banking/connections/{{open_banking_connection_id}}/request-sync/", "Agenda sincronizacion durable y paginada.", body={}, expected=(202, 400, 404)),
        request("Reconcile Bank Connection", "POST", "/api/integrations/open-banking/connections/{{open_banking_connection_id}}/reconcile/", "Detecta diferencias sin alterar automaticamente el ledger.", body={}, expected=(200, 400, 404)),
        request("Connection Timeline", "GET", "/api/integrations/open-banking/connections/{{open_banking_connection_id}}/timeline/", "Timeline minimizado de consentimiento, sync, webhook y revocacion.", expected=(200, 404)),
        request("Revoke Bank Connection", "POST", "/api/integrations/open-banking/connections/{{open_banking_connection_id}}/revoke/", "Revoca consentimiento y detiene recoleccion futura.", body={}, expected=(200, 400, 404)),
    ]
    sections.append(folder("14 - Open Banking", "Consentimiento, catalogo, cuentas, sync, reconciliacion y revocacion local-first.", open_banking_items))

    integration_items = [
        request("Bank Account Sync", "POST", "/api/internal/integrations/banks/accounts/sync/", "Stub interno de sincronizacion bancaria.", internal=True, body={"account_id": "{{account_id}}", "mode": "success", "sync_cursor": "cursor-postman", "provider_metadata": {"provider": "{{bank_provider}}"}}, expected=(200, 400, 401, 403)),
        request("Account Intelligence Refresh", "POST", "/api/internal/integrations/banks/accounts/intelligence/refresh/", "Callback interno de inteligencia de cuenta.", internal=True, body={"owner_id": "{{user_id}}", "reason": "postman"}, expected=(200, 400, 401, 403)),
        request("Bank Transaction Sync", "POST", "/api/internal/integrations/banks/transactions/sync/", "Entrega lote normalizado al intake.", internal=True, body={"provider": "{{bank_provider}}", "account_id": "{{account_id}}", "transactions": []}, expected=(200, 400, 401, 403)),
        request("Resolve Bank Reconciliation", "POST", "/api/internal/integrations/banks/transactions/reconciliation/resolve/", "Reporta decision del adapter bancario.", internal=True, body={"issue_id": 0, "resolution_action": "apply_provider_update"}, expected=(200, 400, 401, 403)),
        request("Revoke Bank Consent Callback", "POST", "/api/internal/integrations/banks/consents/revoke/", "Cierre interno de integracion bancaria.", internal=True, body={"consent_id": "{{consent_id}}", "provider": "{{bank_provider}}"}, expected=(200, 400, 401, 403)),
        request("Voice AI Worker", "POST", "/api/internal/integrations/llm/transactions/inference/worker/", "Handler interno del worker de inferencia.", internal=True, body={"inference_request_id": "{{inference_request_id}}"}, expected=(200, 202, 400, 401, 403)),
        request("Transaction Intake Row", "POST", "/api/internal/transactions/intake/row/", "Intake interno single-row idempotente.", internal=True, body={"provider": "{{bank_provider}}", "source": "open_banking", "provider_account_id": "provider-account-001", "external_id": "provider-txn-001", "normalized_payload": {"account_id": "{{account_id}}", "amount": "25000.00", "type": "expense", "date": "{{current_date}}"}}, expected=(200, 201, 400, 401, 403)),
        request("Transaction Intake Batch", "POST", "/api/internal/transactions/intake/batches/", "Crea batch durable de intake.", internal=True, body={"provider": "{{bank_provider}}", "source": "open_banking", "provider_account_id": "provider-account-001", "rows": []}, expected=(200, 201, 400, 401, 403)),
    ]
    sections.append(folder("15 - Internal Integrations and Services", "Solo adapters/workers. Requiere internal_token y no es API mobile publica.", integration_items))

    operation_items = [
        request("Account Outbox Health", "GET", "/api/finance/accounts/outbox-cuentas/health/", "Salud del outbox accounts."),
        request("Account Event Contracts", "GET", "/api/finance/accounts/outbox-cuentas/contracts/", "Contratos publicados por accounts."),
        request("Identity Outbox Health", "GET", "/api/identity/eventing/outbox-identidad/health/", "Salud del outbox identity."),
        request("Identity Event Contracts", "GET", "/api/identity/eventing/outbox-identidad/contracts/", "Contratos publicados por identity."),
        request("List Account Outbox", "GET", "/api/finance/accounts/outbox-cuentas/", "Eventos operativos de accounts.", capture=("outbox_event_id", "((data.results || data)[0] || {}).id")),
        request("List Identity Outbox", "GET", "/api/identity/eventing/outbox-identidad/", "Eventos operativos de identity."),
        request("List Payment Outbox", "GET", "/api/payments/intents/outbox-pagos/", "Eventos operativos de payments."),
        request("Retry Account Outbox Event", "POST", "/api/finance/accounts/outbox-cuentas/{{outbox_event_id}}/retry/", "Reintenta evento fallido con auditoria.", body={}, expected=(200, 400, 403)),
        request("Release Account Outbox Lock", "POST", "/api/finance/accounts/outbox-cuentas/{{outbox_event_id}}/release_lock/", "Libera lock stale de soporte.", body={}, expected=(200, 400, 403)),
    ]
    sections.append(folder("16 - Eventing and Operations", "Outboxes, contratos, health, retries y locks.", operation_items))

    support_items = [
        request(
            "Operations Dashboard",
            "GET",
            "/api/internal/support/operations/",
            "Snapshot agregado staff-only de outboxes, OCR, scheduler, notificaciones y pagos.",
            bearer_variable="support_access_token",
            expected=(200, 401, 403),
        ),
        request(
            "Support User Search",
            "GET",
            "/api/internal/support/users/?q={{email}}",
            "Busca usuarios con credencial staff. Audita el acceso y nunca persiste la consulta en claro.",
            headers=[("X-Support-Reason", "{{support_reason}}"), ("X-Support-Case", "{{support_case}}")],
            bearer_variable="support_access_token",
            capture=("support_user_id", "((data.results || [])[0] || {}).id"),
            expected=(200, 400, 401, 403),
        ),
        request(
            "Support User Overview",
            "GET",
            "/api/internal/support/users/{{support_user_id}}/",
            "Vista 360 minimizada: identidad y conteos operativos, sin saldos ni detalles financieros.",
            headers=[("X-Support-Reason", "{{support_reason}}"), ("X-Support-Case", "{{support_case}}")],
            bearer_variable="support_access_token",
            expected=(200, 400, 401, 403, 404),
        ),
        request("Support Open Banking Timeline", "GET", "/api/internal/support/open-banking/connections/{{open_banking_connection_id}}/timeline/", "Timeline financiero minimizado y auditado para un caso de soporte.", headers=[("X-Support-Reason", "{{support_reason}}"), ("X-Support-Case", "{{support_case}}")], bearer_variable="support_access_token", expected=(200, 400, 401, 403, 404)),
        request("Audit Log", "GET", "/api/support/audit/auditoria/", "Trazabilidad de acciones sensibles."),
        request("Audit by Module", "GET", "/api/support/audit/auditoria/?module=accounts", "Consulta estandar por modulo."),
        request("Audit by Entity", "GET", "/api/support/audit/auditoria/?entity=Account&entity_id={{account_id}}", "Consulta por agregado y entidad."),
    ]
    sections.append(folder("17 - Support and Audit", "Consultas read-only para soporte y auditoria.", support_items))

    sections.append(
        folder(
            "90 - Planned Contracts - Not Executable",
            "Roadmap contractual. Estas carpetas no inventan endpoints: documentan fronteras futuras hasta que exista implementacion y pruebas.",
            [
                folder("Biometrics and Passkeys", "Registro y verificacion biometrica/passkeys con challenge server-side, attestation y revocacion. Nunca almacenar biometria cruda.", []),
                folder("Open Banking Provider Certification", "Validacion sandbox con payloads y vectores oficiales de Belvo/Salt Edge antes de activarlos.", []),
                folder("Payment Provider Webhooks", "Firmas reales por PSP, replay protection, callbacks, settlement, disputes y refunds.", []),
                folder("API Gateway and Edge Security", "Rate limits, WAF, API keys B2B, mTLS interno y politicas por consumer.", []),
                folder("Exports and Data Portability", "Exports asincronicos, expiracion de artefactos, descarga firmada y derecho de eliminacion.", []),
                folder("Realtime Gateway", "SSE/WebSocket sobre senales durables; la verdad sigue en APIs y read models.", []),
                folder("AI and Model Operations", "Versionado de prompts/modelos, evaluaciones, explicabilidad, feedback y monitoreo de drift.", []),
            ],
        )
    )

    return {
        "info": {
            "_postman_id": "1f2d8d95-f8c0-4b62-a321-7e0d8fe3e001",
            "name": "Vexxo_API",
            "description": (
                "Catalogo operativo local de Vexxo. Organizado por bounded context y casos de uso, "
                "con autenticacion heredada, variables encadenadas, consultas estandar, contratos de "
                "proveedores y operacion interna. Los secretos nunca se versionan: internal_token y "
                "cualquier credencial externa deben configurarse como valores locales o en Postman Vault."
            ),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "auth": {"type": "bearer", "bearer": [{"key": "token", "value": "{{access_token}}", "type": "string"}]},
        "event": [
            script_event(
                "prerequest",
                [
                    "const now = new Date();",
                    "pm.collectionVariables.set('current_date', now.toISOString().slice(0, 10));",
                    "pm.collectionVariables.set('current_month', now.toISOString().slice(0, 7));",
                    "const previous = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - 1, 1));",
                    "pm.collectionVariables.set('previous_month', previous.toISOString().slice(0, 7));",
                    "for (const days of [30, 60, 90, 365]) {",
                    "  const future = new Date(now);",
                    "  future.setUTCDate(future.getUTCDate() + days);",
                    "  pm.collectionVariables.set(`future_date_${days}`, future.toISOString().slice(0, 10));",
                    "}",
                    "pm.collectionVariables.set('request_id', pm.variables.replaceIn('{{$guid}}'));",
                ],
            )
        ],
        "variable": [{"key": key, "value": value, "type": "string"} for key, value in variables],
        "item": sections,
    }


def count_requests(items: list[dict]) -> int:
    return sum(1 if "request" in item else count_requests(item.get("item", [])) for item in items)


def render_guide(collection: dict) -> str:
    rows = []
    for item in collection["item"]:
        rows.append(f"| `{item['name']}` | {count_requests(item.get('item', []))} | {item.get('description', '')} |")

    return "\n".join(
        [
            "# Vexxo Postman Collection",
            "",
            "Fuente importable: [Vexxo_local.postman_collection.json](Vexxo_local.postman_collection.json)",
            "",
            "La coleccion es un catalogo operativo local del backend. El archivo se genera desde",
            "`scripts/generate_postman_collection.py` para mantener estructura, variables y guia sincronizadas.",
            "",
            "## Regeneracion",
            "",
            "```powershell",
            ".\\scripts\\run_manage_vexxo_app.cmd shell --command \"print('runtime ok')\"",
            "py -3 .\\scripts\\generate_postman_collection.py",
            "```",
            "",
            "La generacion no necesita Django ni credenciales. La primera linea solo verifica opcionalmente el runtime.",
            "",
            "## Seguridad",
            "",
            "- No guardar tokens, API keys, passwords reales ni secretos de proveedores en el JSON.",
            "- `internal_token` empieza vacio y debe configurarse localmente o mediante Postman Vault.",
            "- `support_access_token` es independiente del token del usuario y debe pertenecer a staff local.",
            "- Las consultas de soporte exigen `support_reason`; `support_case` identifica el ticket asociado.",
            "- Las carpetas internas no son superficie publica para Flutter.",
            "- `90 - Planned Contracts` documenta fronteras futuras y no contiene endpoints inventados.",
            "",
            "## Flujo minimo",
            "",
            "1. `00 / Health` y `Readiness`.",
            "2. `01 / Register` o `Login`.",
            "3. `02 / Mobile Bootstrap` hasta que el test confirme el bootstrap asincrono y guarde `category_id`.",
            "4. `04 / List Accounts` para reutilizar una cuenta o `Create Cash Account` para crearla.",
            "5. `05 / Create Manual Expense` para guardar `transaction_id`.",
            "6. `06 / Create Category Budget`.",
            "7. Consultar alertas, notificaciones, realtime y auditoria.",
            "8. Para soporte, obtener aparte un token staff, asignarlo a `support_access_token` y ejecutar `16`.",
            "",
            "## Secciones",
            "",
            "| Seccion | Requests | Proposito |",
            "|---|---:|---|",
            *rows,
            "",
            "## Variables",
            "",
            "Las variables de IDs se llenan desde tests de Postman cuando una respuesta exitosa contiene el recurso.",
            "`current_date`, `current_month` y `request_id` se recalculan antes de cada request.",
            "",
            "## Mantenimiento",
            "",
            "Cuando se agregue un endpoint:",
            "",
            "1. Agregarlo al bounded context correspondiente en el generador.",
            "2. Incluir descripcion, rol esperado, body minimo y codigos validos.",
            "3. Capturar su ID si alimenta requests posteriores.",
            "4. Regenerar JSON y guia.",
            "5. Validar el JSON y ejecutar al menos el flujo minimo local.",
            "6. Reimportar la coleccion en Postman reemplazando `Vexxo_API`.",
            "",
        ]
    )


def main() -> None:
    collection = build_collection()
    JSON_OUTPUT.write_text(json.dumps(collection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    GUIDE_OUTPUT.write_text(render_guide(collection), encoding="utf-8")
    print(f"Generated {count_requests(collection['item'])} requests in {len(collection['item'])} sections.")


if __name__ == "__main__":
    main()
