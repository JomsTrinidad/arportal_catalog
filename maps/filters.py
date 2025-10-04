import django_filters as df
from .models import AuthoredMapRow
class RowFilter(df.FilterSet):
    map_name = df.CharFilter(lookup_expr="icontains")
    string_01 = df.CharFilter(lookup_expr="icontains")
    string_02 = df.CharFilter(lookup_expr="icontains")
    class Meta:
        model = AuthoredMapRow
        fields = ["map_name","deleted_flag","string_01","string_02"]
