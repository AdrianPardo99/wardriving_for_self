def is_swagger_fake_view(view):
    return getattr(view, "swagger_fake_view", False)
