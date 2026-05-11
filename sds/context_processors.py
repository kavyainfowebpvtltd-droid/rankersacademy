from .portal_features import get_student_portal_features


def student_portal_features(_request):
    return {
        "student_portal_features": get_student_portal_features(),
    }
