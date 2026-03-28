"""
Endpoints de autenticacion y lifecycle del usuario.

Descripcion general:
- expone registro, login, refresh seguro, perfil propio, logout, onboarding y
  autenticacion social operativa

Analisis detallado:
- el registro de Vexxo se modela con nombre completo, correo y contrasena;
  `username` queda como identificador interno generado por backend
- login y refresh ya registran sesiones, familias de refresh y step-up si el
  dispositivo no es suficientemente confiable
- la capa social OAuth ya soporta Google y Facebook con `state`, callback,
  linking seguro y estrategia de no auto-merge agresivo por email
"""

from __future__ import annotations

from django.contrib.auth import authenticate, get_user_model
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from common.domain_events import EventPriority
from identity.devices.services import register_or_update_device
from identity.sessions.services import (
    detect_refresh_reuse,
    get_active_session_by_refresh_jti,
    register_user_session,
    revoke_session_by_refresh_token,
    revoke_session_family,
    rotate_session_refresh,
    touch_session,
)
from identity.social_identities.models import UserSocialIdentity
from identity.users.domain import (
    UserDomainEventTypes,
    build_user_social_auth_payload,
    build_user_social_identity_payload,
    get_user_event_catalog,
    get_user_event_governance,
    get_user_event_runtime,
)
from identity.users.serializers.user_serializer import UserMeSerializer, UserRegisterSerializer
from identity.users.services.event_service import publish_user_event_after_commit
from identity.users.services.oauth_service import (
    SocialOAuthError,
    build_social_authorization_url,
    build_social_state,
    consume_social_auth_handoff,
    create_social_auth_handoff,
    get_social_provider_settings,
    get_supported_social_providers,
    resolve_social_callback,
    resolve_social_redirect_uri,
    unlink_social_identity,
)

User = get_user_model()


def _issue_user_tokens(user) -> dict:
    refresh = EmailOrUsernameTokenSerializer.get_token(user)
    access = refresh.access_token
    return {
        "refresh": str(refresh),
        "access": str(access),
        "refresh_jti": str(refresh.get("jti", "")),
        "access_jti": str(access.get("jti", "")),
    }


def _resolve_login_user(login: str, password: str):
    login = (login or "").strip()
    user = authenticate(username=login, password=password)
    if user is not None:
        return user
    try:
        candidate = User.objects.get(email__iexact=login)
    except User.DoesNotExist:
        return None
    return authenticate(username=candidate.username, password=password)


def _default_device_payload(request, provider: str = "") -> dict:
    return {
        "fingerprint": request.headers.get("X-Device-Fingerprint", "") or f"oauth-{provider or 'web'}",
        "external_device_id": request.headers.get("X-External-Device-Id", ""),
        "name": request.headers.get("X-Device-Name", ""),
        "device_type": request.headers.get("X-Device-Type", "web"),
        "platform": request.headers.get("X-Platform", ""),
        "os_version": request.headers.get("X-OS-Version", ""),
        "app_version": request.headers.get("X-App-Version", ""),
        "push_token": request.headers.get("X-Push-Token", ""),
        "locale": request.headers.get("X-Locale", ""),
        "timezone_name": request.headers.get("X-Timezone", ""),
        "metadata": {
            "provider": provider,
            "source": "users.auth.social_callback" if provider else "users.auth.login",
        },
    }


def _no_store(response: Response) -> Response:
    response["Cache-Control"] = "no-store"
    response["Pragma"] = "no-cache"
    return response


def _publish_social_link_event(*, result, provider: str, source: str) -> None:
    if result.login_mode == "login_existing_identity":
        return
    publish_user_event_after_commit(
        event_type=UserDomainEventTypes.USER_SOCIAL_LINKED,
        payload=build_user_social_identity_payload(
            user=result.user,
            provider=provider,
            provider_user_id=str(result.profile.get("provider_user_id") or ""),
            identity_id=result.identity.pk,
            email=str(result.profile.get("email") or result.user.email),
            linked=True,
            extra={
                "created_user": result.created_user,
                "linked_identity": result.linked_identity,
                "login_mode": result.login_mode,
            },
        ),
        metadata={"source": source},
        priority=EventPriority.NORMAL,
        correlation_id=str((result.state_payload or {}).get("nonce") or ""),
    )


def _build_social_session_response(*, request, user, provider: str, login_mode: str, created_user: bool, linked_identity: bool, identity, source: str) -> Response:
    tokens = _issue_user_tokens(user)
    device_payload = {
        **_default_device_payload(request, provider=provider),
        "fingerprint": request.headers.get("X-Device-Fingerprint", "") or request.data.get("device_fingerprint", "") or f"oauth-{provider}",
        "external_device_id": request.data.get("external_device_id", ""),
        "name": request.data.get("device_name", ""),
        "device_type": request.data.get("device_type", "web"),
        "platform": request.data.get("platform", ""),
        "os_version": request.data.get("os_version", ""),
        "app_version": request.data.get("app_version", ""),
        "push_token": request.data.get("push_token", ""),
        "locale": request.data.get("locale", ""),
        "timezone_name": request.data.get("timezone_name", ""),
        "metadata": {
            "source": source,
            "provider_user_id": identity.provider_user_id,
        },
    }
    device = register_or_update_device(user=user, request=request, payload=device_payload)
    session = register_user_session(
        user=user,
        request=request,
        refresh_jti=tokens["refresh_jti"],
        access_jti=tokens["access_jti"],
        session_type="social",
        provider=provider,
        device=device,
        family_id=tokens["refresh_jti"],
        correlation_id=tokens["refresh_jti"],
        metadata={
            "source": source,
            "provider_user_id": identity.provider_user_id,
            "login_mode": login_mode,
        },
    )
    serializer = UserMeSerializer(user, context={"request": request})
    return _no_store(
        Response(
            {
                "detail": "Sesion social creada.",
                "provider": provider,
                "mode": login_mode,
                "created_user": bool(created_user),
                "linked_identity": bool(linked_identity),
                "user": serializer.data,
                "session": {
                    "session_id": session.pk,
                    "family_id": session.family_id,
                    "risk_level": session.risk_level,
                    "requires_step_up": bool(session.requires_step_up),
                },
                "tokens": {
                    "refresh": tokens["refresh"],
                    "access": tokens["access"],
                },
            },
            status=status.HTTP_200_OK,
        )
    )


class EmailOrUsernameTokenSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["username"] = user.username
        token["email"] = user.email
        token["plan"] = user.plan
        token["status"] = user.status
        token["base_currency"] = user.base_currency
        token["display_name"] = user.display_name
        token["onboarding_completed"] = bool(user.onboarding_completed)
        return token

    def validate(self, attrs):
        login = (attrs.get("username") or "").strip()
        password = attrs.get("password")

        user = _resolve_login_user(login, password)
        if not user:
            raise self.fail("no_active_account")

        data = super().validate({"username": user.username, "password": password})
        user.mark_seen(self.context.get("request"))
        self.user = user
        return data


class SecureTokenRefreshSerializer(TokenRefreshSerializer):
    """
    Rotacion segura de refresh token con deteccion basica de reuse.
    """

    def validate(self, attrs):
        raw_refresh = str(attrs.get("refresh") or "").strip()
        try:
            refresh = RefreshToken(raw_refresh)
        except Exception as exc:
            raise serializers.ValidationError({"detail": "Refresh token invalido."}) from exc

        incoming_jti = str(refresh.get("jti", ""))
        session = get_active_session_by_refresh_jti(refresh_jti=incoming_jti)
        if session is None:
            reused_session = detect_refresh_reuse(refresh_jti=incoming_jti)
            if reused_session is not None:
                revoke_session_family(
                    family_id=reused_session.family_id,
                    reason="refresh_token_reuse_detected",
                )
            raise serializers.ValidationError(
                {"detail": "Refresh token invalido, revocado o reutilizado."}
            )

        data = super().validate(attrs)
        new_refresh_raw = str(data.get("refresh") or raw_refresh)
        new_access_raw = str(data.get("access") or "")
        new_refresh_jti = str(RefreshToken(new_refresh_raw).get("jti", "")) if new_refresh_raw else incoming_jti
        new_access_jti = str(AccessToken(new_access_raw).get("jti", "")) if new_access_raw else ""
        rotate_session_refresh(
            session=session,
            refresh_jti=new_refresh_jti,
            access_jti=new_access_jti,
        )
        touch_session(session)
        data["session"] = {
            "session_id": session.pk,
            "family_id": session.family_id,
            "requires_step_up": bool(session.requires_step_up),
            "risk_level": session.risk_level,
        }
        return data


class SecureTokenRefreshView(TokenRefreshView):
    serializer_class = SecureTokenRefreshSerializer


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserRegisterSerializer
    permission_classes = [permissions.AllowAny]


class LoginView(TokenObtainPairView):
    serializer_class = EmailOrUsernameTokenSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code >= 400:
            return response

        user = _resolve_login_user(
            str(request.data.get("username") or ""),
            str(request.data.get("password") or ""),
        )
        if user is None:
            return response

        device = register_or_update_device(
            user=user,
            request=request,
            payload={
                **_default_device_payload(request),
                "fingerprint": request.headers.get("X-Device-Fingerprint", "") or request.data.get("device_fingerprint", ""),
                "external_device_id": request.data.get("external_device_id", ""),
                "name": request.data.get("device_name", ""),
                "device_type": request.data.get("device_type", "web"),
                "platform": request.data.get("platform", ""),
                "os_version": request.data.get("os_version", ""),
                "app_version": request.data.get("app_version", ""),
                "push_token": request.data.get("push_token", ""),
                "locale": request.data.get("locale", ""),
                "timezone_name": request.data.get("timezone_name", ""),
                "metadata": request.data.get("device_metadata", {}) or {},
            },
        )

        refresh_raw = response.data.get("refresh", "")
        access_raw = response.data.get("access", "")
        refresh_token = RefreshToken(refresh_raw) if refresh_raw else None
        access_token = AccessToken(access_raw) if access_raw else None
        session = register_user_session(
            user=user,
            request=request,
            refresh_jti=str(refresh_token.get("jti", "")) if refresh_token else "",
            access_jti=str(access_token.get("jti", "")) if access_token else "",
            session_type="password",
            device=device,
            family_id=str(refresh_token.get("jti", "")) if refresh_token else "",
            expires_at=None,
            correlation_id=str(refresh_token.get("jti", "")) if refresh_token else "",
            metadata={"source": "users.auth.login"},
        )
        response.data["session"] = {
            "session_id": session.pk,
            "family_id": session.family_id,
            "risk_level": session.risk_level,
            "requires_step_up": bool(session.requires_step_up),
        }
        return response


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserMeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        user = self.request.user
        user.mark_seen(self.request)
        return user


class CompleteOnboardingView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        if not user.onboarding_completed:
            user.onboarding_completed = True
            user.save(update_fields=["onboarding_completed", "updated_at"])
        return Response(
            {
                "detail": "Onboarding actualizado.",
                "onboarding_completed": bool(user.onboarding_completed),
            }
        )


class SocialProvidersView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({"providers": get_supported_social_providers()})


class SocialProviderStartView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, provider: str):
        try:
            provider_data = get_social_provider_settings(provider)
            redirect_uri = resolve_social_redirect_uri(
                provider,
                str(
                    request.query_params.get("redirect_uri")
                    or request.query_params.get("frontend_callback_url")
                    or ""
                ),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except SocialOAuthError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        mode = str(request.query_params.get("mode") or ("link" if getattr(request.user, "is_authenticated", False) else "login"))
        state = build_social_state(
            provider=provider,
            current_user=request.user if getattr(request.user, "is_authenticated", False) else None,
            mode=mode,
            next_url=str(request.query_params.get("next") or ""),
            redirect_uri=redirect_uri,
        )
        authorization_url = build_social_authorization_url(provider, state=state, redirect_uri=redirect_uri)
        payload = build_user_social_auth_payload(
            provider=provider,
            configured=provider_data["configured"],
            authorization_url=authorization_url,
            callback_url=redirect_uri,
            user=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
        )
        payload["state"] = state
        payload["mode"] = mode
        payload["redirect_uri"] = redirect_uri
        publish_user_event_after_commit(
            event_type=UserDomainEventTypes.USER_SOCIAL_AUTH_PREPARED,
            payload=payload,
            metadata={"source": "users.auth.social_start"},
            priority=EventPriority.LOW,
        )
        return Response(
            {
                **provider_data,
                "state": state,
                "mode": mode,
                "redirect_uri": redirect_uri,
                "authorization_url": authorization_url,
                "detail": (
                    "Proveedor listo para iniciar OAuth2."
                    if provider_data["configured"]
                    else "Proveedor aun no configurado. Completa las credenciales para habilitarlo."
                ),
            }
        )


class SocialProviderCallbackView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, provider: str):
        # Compatibilidad: este endpoint sigue soportando callback backend.
        # El camino principal recomendado para Vexxo es frontend callback +
        # POST /auth/social/exchange con provider/code/state.
        error = str(request.query_params.get("error") or "").strip()
        if error:
            return _no_store(
                Response(
                {
                    "detail": "El proveedor retorno un error OAuth.",
                    "provider": provider,
                    "error": error,
                    "error_description": str(request.query_params.get("error_description") or ""),
                },
                status=status.HTTP_400_BAD_REQUEST,
                )
            )

        try:
            result = resolve_social_callback(
                provider=provider,
                code=str(request.query_params.get("code") or ""),
                state=str(request.query_params.get("state") or ""),
                current_user=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
                redirect_uri=get_social_provider_settings(provider).get("callback_url", ""),
            )
        except SocialOAuthError as exc:
            return Response({"detail": str(exc), "provider": provider}, status=status.HTTP_400_BAD_REQUEST)

        _publish_social_link_event(
            result=result,
            provider=provider,
            source="users.auth.social_callback",
        )

        serializer = UserMeSerializer(result.user, context={"request": request})
        if getattr(request, "user", None) and request.user.is_authenticated:
            return _no_store(
                Response(
                {
                    "detail": "Proveedor social vinculado.",
                    "provider": provider,
                    "mode": result.login_mode,
                    "created_user": bool(result.created_user),
                    "linked_identity": bool(result.linked_identity),
                    "user": serializer.data,
                    "social_identity": {
                        "id": result.identity.pk,
                        "provider": result.identity.provider,
                        "provider_user_id": result.identity.provider_user_id,
                        "email": result.identity.email,
                        "email_verified": result.identity.email_verified,
                        "linked_at": result.identity.linked_at.isoformat() if result.identity.linked_at else None,
                    },
                },
                status=status.HTTP_200_OK,
                )
            )

        handoff = create_social_auth_handoff(result=result)
        return _no_store(
            Response(
                {
                    "detail": "Proveedor validado. Intercambia el handoff por una sesion via POST.",
                    "provider": provider,
                    "mode": result.login_mode,
                    "created_user": bool(result.created_user),
                    "linked_identity": bool(result.linked_identity),
                    "handoff_code": handoff.code,
                    "handoff_expires_at": handoff.expires_at.isoformat(),
                    "next_url": str((result.state_payload or {}).get("next_url") or ""),
                    "user": serializer.data,
                    "social_identity": {
                        "id": result.identity.pk,
                        "provider": result.identity.provider,
                        "provider_user_id": result.identity.provider_user_id,
                        "email": result.identity.email,
                        "email_verified": result.identity.email_verified,
                        "linked_at": result.identity.linked_at.isoformat() if result.identity.linked_at else None,
                    },
                },
                status=status.HTTP_200_OK,
            )
        )


class SocialAuthExchangeView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        handoff_code = str(request.data.get("handoff_code") or "").strip()
        if handoff_code:
            try:
                handoff = consume_social_auth_handoff(code=handoff_code)
            except SocialOAuthError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            return _build_social_session_response(
                request=request,
                user=handoff.user,
                provider=handoff.provider,
                login_mode=handoff.login_mode,
                created_user=handoff.created_user,
                linked_identity=handoff.linked_identity,
                identity=handoff.identity,
                source="users.auth.social_exchange_handoff",
            )

        provider = str(request.data.get("provider") or "").strip().lower()
        code = str(request.data.get("code") or "").strip()
        state = str(request.data.get("state") or "").strip()
        redirect_uri = str(request.data.get("redirect_uri") or request.data.get("frontend_callback_url") or "").strip()
        if not (provider and code and state):
            return Response(
                {"detail": "Debes enviar `handoff_code` o `provider`, `code` y `state`."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = resolve_social_callback(
                provider=provider,
                code=code,
                state=state,
                current_user=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
                redirect_uri=redirect_uri,
            )
        except SocialOAuthError as exc:
            return Response({"detail": str(exc), "provider": provider}, status=status.HTTP_400_BAD_REQUEST)

        _publish_social_link_event(
            result=result,
            provider=provider,
            source="users.auth.social_exchange_direct",
        )

        if getattr(request, "user", None) and request.user.is_authenticated and result.login_mode == "link":
            serializer = UserMeSerializer(result.user, context={"request": request})
            return _no_store(
                Response(
                    {
                        "detail": "Proveedor social vinculado.",
                        "provider": provider,
                        "mode": result.login_mode,
                        "created_user": bool(result.created_user),
                        "linked_identity": bool(result.linked_identity),
                        "user": serializer.data,
                        "social_identity": {
                            "id": result.identity.pk,
                            "provider": result.identity.provider,
                            "provider_user_id": result.identity.provider_user_id,
                            "email": result.identity.email,
                            "email_verified": result.identity.email_verified,
                            "linked_at": result.identity.linked_at.isoformat() if result.identity.linked_at else None,
                        },
                    },
                    status=status.HTTP_200_OK,
                )
            )

        return _build_social_session_response(
            request=request,
            user=result.user,
            provider=provider,
            login_mode=result.login_mode,
            created_user=result.created_user,
            linked_identity=result.linked_identity,
            identity=result.identity,
            source="users.auth.social_exchange_direct",
        )


class SocialIdentityListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        identities = UserSocialIdentity.objects.filter(user=request.user).order_by("provider", "-linked_at")
        return Response(
            {
                "identities": [
                    {
                        "id": identity.pk,
                        "provider": identity.provider,
                        "provider_user_id": identity.provider_user_id,
                        "email": identity.email,
                        "email_verified": identity.email_verified,
                        "full_name": identity.full_name,
                        "avatar_url": identity.avatar_url,
                        "is_active": identity.is_active,
                        "linked_at": identity.linked_at.isoformat() if identity.linked_at else None,
                        "last_login_at": identity.last_login_at.isoformat() if identity.last_login_at else None,
                        "unlinked_at": identity.unlinked_at.isoformat() if identity.unlinked_at else None,
                    }
                    for identity in identities
                ]
            }
        )


class SocialIdentityUnlinkView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, provider: str):
        active_identities = UserSocialIdentity.objects.filter(user=request.user, is_active=True)
        if active_identities.count() <= 1 and not request.user.has_usable_password():
            return Response(
                {
                    "detail": "No puedes desvincular tu ultimo proveedor social si la cuenta no tiene contrasena usable."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            identity = unlink_social_identity(user=request.user, provider=provider)
        except SocialOAuthError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        publish_user_event_after_commit(
            event_type=UserDomainEventTypes.USER_SOCIAL_UNLINKED,
            payload=build_user_social_identity_payload(
                user=request.user,
                provider=provider,
                provider_user_id=identity.provider_user_id,
                identity_id=identity.pk,
                email=identity.email,
                linked=False,
            ),
            metadata={"source": "users.auth.social_unlink"},
            priority=EventPriority.NORMAL,
        )
        return Response({"detail": "Identidad social desvinculada.", "provider": provider})


class UserEventContractView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "catalog": get_user_event_catalog(),
                "governance": get_user_event_governance(),
                "runtime": get_user_event_runtime(),
            }
        )


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            return Response(
                {"error": "Falta el token de refresh."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh)
            token.blacklist()
            revoke_session_by_refresh_token(
                refresh_jti=str(token.get("jti", "")),
                reason="logout",
            )
            return Response(
                {"detail": "Sesion cerrada correctamente."},
                status=status.HTTP_200_OK,
            )
        except Exception:
            return Response(
                {"error": "Token invalido o expirado."},
                status=status.HTTP_400_BAD_REQUEST,
            )
