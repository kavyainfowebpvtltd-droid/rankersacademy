STUDENT_PORTAL_FEATURE_FLAGS = {
    "subject_analysis": False,
    "gap_analysis": False,
    "reports": False,
    "study_material": False,
}


def get_student_portal_features():
    return dict(STUDENT_PORTAL_FEATURE_FLAGS)


def is_student_portal_feature_enabled(feature_key: str) -> bool:
    return STUDENT_PORTAL_FEATURE_FLAGS.get(feature_key, True)
