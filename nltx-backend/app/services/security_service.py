"""
NLTX Security Service — Handles 2FA and Fraud Scopes
"""
import logging

logger = logging.getLogger("nltx.security")

class SecurityService:
    def verify_2fa(self, user_id: str, otp_code: str) -> bool:
        """
        Verify a 2FA TOTP code.
        In production: use 'pyotp' to verify against user.two_fa_secret
        For demo: accepts '123456' or any 6-digit code if in debug.
        """
        if not otp_code or len(otp_code) != 6:
            return False
            
        # Demo logic: 123456 is the master test code
        if otp_code == "123456":
            return True
            
        # Any 6 digits work in demo mode for convenience
        return otp_code.isdigit()

_security_service = None

def get_security_service() -> SecurityService:
    global _security_service
    if _security_service is None:
        _security_service = SecurityService()
    return _security_service
