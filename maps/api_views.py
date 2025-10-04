import csv, io
from rest_framework.generics import ListAPIView, RetrieveAPIView, CreateAPIView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django_filters.rest_framework import DjangoFilterBackend
from .models import AuthoredMapRow, ChangeRequest
from .serializers import RowSerializer

class RowListView(ListAPIView):
    queryset = AuthoredMapRow.objects.all().order_by("-modified_dttm")
    serializer_class = RowSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["map_name","deleted_flag","string_01","string_02"]

class RowDetailView(RetrieveAPIView):
    lookup_field = "row_id"
    queryset = AuthoredMapRow.objects.all()
    serializer_class = RowSerializer

class RowCreateView(CreateAPIView):
    queryset = AuthoredMapRow.objects.all()
    serializer_class = RowSerializer

class RowUpdateView(APIView):
    def post(self, request):
        row_id = request.data.get("row_id")
        try:
            obj = AuthoredMapRow.objects.get(row_id=row_id)
        except AuthoredMapRow.DoesNotExist:
            return Response({"error":"row not found"}, status=404)
        ser = RowSerializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)

class RowDeleteView(APIView):
    def post(self, request):
        row_id = request.data.get("row_id")
        try:
            obj = AuthoredMapRow.objects.get(row_id=row_id)
        except AuthoredMapRow.DoesNotExist:
            return Response({"error":"row not found"}, status=404)
        obj.soft_delete(actor=request.user if request.user.is_authenticated else "api")
        return Response({"status":"deleted"})

class RowUndeleteView(APIView):
    def post(self, request):
        row_id = request.data.get("row_id")
        try:
            obj = AuthoredMapRow.objects.get(row_id=row_id)
        except AuthoredMapRow.DoesNotExist:
            return Response({"error":"row not found"}, status=404)
        obj.undelete(actor=request.user if request.user.is_authenticated else "api")
        return Response({"status":"undeleted"})

class RowUploadView(APIView):
    def post(self, request):
        f = request.FILES.get("file")
        map_name = request.data.get("map_name","default")
        if not f:
            return Response({"error":"file required"}, status=400)
        data = io.StringIO(f.read().decode("utf-8"))
        reader = csv.DictReader(data)
        count = 0
        for row in reader:
            payload = {k:v for k,v in row.items() if v is not None}
            payload["map_name"] = map_name
            ChangeRequest.objects.create(actor=request.user if request.user.is_authenticated else None, map_name=map_name, payload=payload)
            count += 1
        return Response({"status":"queued","rows":count}, status=201)
