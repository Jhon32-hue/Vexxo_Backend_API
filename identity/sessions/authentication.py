from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed

from identity.sessions.models import SessionRiskLevel, SessionStatus, UserSession


class SessionBoundJWTAuthentication(JWTAuthentication):
    """Reject JWTs whose persisted session was rotated or revoked.

    Accounts without session rows remain compatible during migration. Once an
    account has a session, every access token must match its active JTI.
    """

    def authenticate(self, request):
        authenticated = super().authenticate(request)
        if authenticated is None:
            return None
        user, validated_token = authenticated
        jti = str(validated_token.get("jti", "") or "")
        sessions = UserSession.objects.filter(user=user)
        session = sessions.filter(access_jti=jti, status=SessionStatus.ACTIVE).first()
        if sessions.exists() and session is None:
            raise AuthenticationFailed("Session revoked or superseded.", code="session_inactive")
        if session is not None and session.risk_level == SessionRiskLevel.CRITICAL:
            session.revoke(reason="critical_risk", commit=True)
            raise AuthenticationFailed("Critical-risk session revoked.", code="session_critical")
        request.vexxo_session = session
        return user, validated_token
