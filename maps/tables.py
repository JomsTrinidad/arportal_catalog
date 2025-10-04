import django_tables2 as tables
from .models import AuthoredMapRow
class RowTable(tables.Table):
    detail = tables.TemplateColumn('<a href="/maps/{{record.row_id}}/">View</a>', orderable=False)
    class Meta:
        model = AuthoredMapRow
        template_name = "django_tables2/bootstrap.html"
        fields = ("map_name","row_id","deleted_flag","version","string_01","string_02")
