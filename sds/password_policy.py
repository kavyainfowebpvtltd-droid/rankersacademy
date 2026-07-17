DEFAULT_ONE_TIME_PASSWORD = "Tra@2026"


def user_needs_password_change(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False

    if hasattr(user, "student"):
        return bool(user.student.must_change_password)

    if hasattr(user, "teacheradmin"):
        return bool(user.teacheradmin.must_change_password)

    return False


def clear_password_change_flag(user) -> None:
    if hasattr(user, "student") and user.student.must_change_password:
        user.student.must_change_password = False
        user.student.save(update_fields=["must_change_password"])

    if hasattr(user, "teacheradmin") and user.teacheradmin.must_change_password:
        user.teacheradmin.must_change_password = False
        user.teacheradmin.save(update_fields=["must_change_password"])
