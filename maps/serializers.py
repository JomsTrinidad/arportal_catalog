from rest_framework import serializers
from .models import AuthoredMapRow, MapInfo

READ_ONLY = ("index_id","row_id","load_dttm","modified_dttm","version")
class RowSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuthoredMapRow
        fields = "__all__"
        read_only_fields = READ_ONLY

class MapInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MapInfo
        fields = "__all__"
