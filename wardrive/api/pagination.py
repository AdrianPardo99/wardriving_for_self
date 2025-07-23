from rest_framework import pagination


class CustomPagination(pagination.PageNumberPagination):
    """
    Configuración de los parámetros nombres  valores paginación de los API-REST.
    Se establecen los nombres de parámetros default y los nombres de los campos
    *- search = text for search
    *- page = required page
    *- page_size = size page
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    page_query_param = "page"
