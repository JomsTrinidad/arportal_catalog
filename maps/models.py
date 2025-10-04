import hashlib
import uuid
from datetime import datetime
from django.db import models, transaction
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Q, Max, Min, OuterRef, Subquery

PRINTABLE = set(chr(i) for i in range(32,127)) | {"\n","\r","\t"," "}

def sanitize_text(val:str)->str:
    if val is None:
        return val
    bad = [ch for ch in val if ch not in PRINTABLE]
    if bad:
        raise ValidationError(f"Non-printable characters found: {repr(''.join(sorted(set(bad))))}")
    return val.replace("\n"," ").replace("\r"," ").strip()

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    full_name = models.CharField(max_length=120, blank=True)
    company = models.CharField(max_length=120, blank=True)
    role = models.CharField(max_length=20, choices=[("owner","Owner/Admin"),("user","User")], default="user")
    phone = models.CharField(max_length=40, blank=True)
    country = models.CharField(max_length=60, blank=True)
    industry = models.CharField(max_length=80, blank=True)
    preferences = models.JSONField(default=dict, blank=True)
    onboarding_completed = models.BooleanField(default=False)
    timezone = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self): return self.full_name or self.user.username

class MapInfo(models.Model):
    map_name = models.CharField(max_length=40, unique=True)
    description = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self): return self.map_name

class AuthoredMapRow(models.Model):
    OP_CHOICES = [
        ("build", "build new map"),
        ("insert", "insert row(s)"),
        ("update", "update row(s)"),
        ("delete", "delete row(s)"),
        ("undelete", "undelete row(s)"),
        ("replace", "replace map"),
    ]
    MODE_CHOICES = [("snapshot","snapshot"),("versioning","versioning")]
    ROWTYPE_CHOICES = [("header","header"),("values","values")]

    index_id = models.PositiveIntegerField(db_index=True, editable=False)
    operation = models.CharField(max_length=16, choices=OP_CHOICES, default="insert")
    provider_sid = models.CharField(max_length=64)
    approver_sid = models.CharField(max_length=64)
    tracking_id = models.CharField(max_length=64, blank=True)
    map_name = models.CharField(max_length=40)
    mode = models.CharField(max_length=16, choices=MODE_CHOICES, default="versioning")
    row_type = models.CharField(max_length=16, choices=ROWTYPE_CHOICES, default="values")
    start_dt = models.DateField(null=True, blank=True)
    end_dt = models.DateField(null=True, blank=True)

    filename = models.CharField(max_length=255, blank=True)
    deleted_flag = models.CharField(max_length=1, default="N")
    is_undeleted = models.CharField(max_length=1, default="N")
    load_dttm = models.DateTimeField(auto_now_add=True)
    modified_dttm = models.DateTimeField(auto_now=True)
    version = models.IntegerField(default=1)
    row_id = models.CharField(max_length=32, unique=True, editable=False)
    update_rowid = models.CharField(max_length=32, blank=True)

    class Meta:
        indexes = [models.Index(fields=["map_name","row_id"]), models.Index(fields=["map_name","version","modified_dttm"])]
        unique_together = [("map_name","row_id")]

    def clean(self):
        if self.approver_sid and self.provider_sid and self.approver_sid == self.provider_sid:
            raise ValidationError("approver_sid must differ from provider_sid")
        if self.mode == "versioning":
            if not self.start_dt or not self.end_dt:
                raise ValidationError("start_dt and end_dt are required in versioning mode")
        for f in self._business_fields():
            val = getattr(self, f, None)
            if isinstance(val, str):
                setattr(self, f, sanitize_text(val))

    def _business_fields(self):
        exclude = {"index_id","row_id","update_rowid","operation","provider_sid","approver_sid","tracking_id",
                   "deleted_flag","is_undeleted","filename","load_dttm","modified_dttm","version"}
        base = [f.name for f in self._meta.get_fields() if hasattr(f, 'attname')]
        return [f for f in base if f not in exclude]

    def _compute_row_id(self):
        parts = []
        for f in self._business_fields():
            v = getattr(self, f, None)
            parts.append("" if v is None else str(v))
        h = hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()
        return h

    def save(self, *args, **kwargs):
        if not self.pk and not self.index_id:
            last = AuthoredMapRow.objects.order_by("-index_id").first()
            self.index_id = (last.index_id + 1) if last else 1
        self.row_id = self._compute_row_id()
        super().save(*args, **kwargs)

    def soft_delete(self, actor):
        self.deleted_flag = "Y"
        self.is_undeleted = "N"
        self.operation = "delete"
        self.save()
        AuditEvent.log(actor=actor, op="delete", snapshot=self)

    def undelete(self, actor):
        self.deleted_flag = "N"
        self.is_undeleted = "Y"
        self.operation = "undelete"
        self.save()
        AuditEvent.log(actor=actor, op="undelete", snapshot=self)

    @staticmethod
    def grouped_search(query:str=None):
        base = AuthoredMapRow.objects.all()
        if query:
            name_matches = Q(map_name__icontains=query)
            desc_map_names = MapInfo.objects.filter(description__icontains=query).values_list("map_name", flat=True)
            base = base.filter(name_matches | Q(map_name__in=desc_map_names))
        grouped = base.values("map_name","version").annotate(last_modified=Max("modified_dttm"),created=Min("load_dttm"),)
        latest = AuthoredMapRow.objects.filter(
            map_name=OuterRef("map_name"),
            version=OuterRef("version"),
        ).order_by("-modified_dttm")
        desc_sub = MapInfo.objects.filter(map_name=OuterRef("map_name")).values("description")[:1]
        return grouped.annotate(
            provider_sid=Subquery(latest.values("provider_sid")[:1]),
            approver_sid=Subquery(latest.values("approver_sid")[:1]),
            tracking_id=Subquery(latest.values("tracking_id")[:1]),
            description=Subquery(desc_sub),
        ).order_by("map_name","version")

# add string_01..string_65 fields
for i in range(1,66):
    f = models.CharField(max_length=255, blank=(i>=3))
    f.contribute_to_class(AuthoredMapRow, f"string_{i:02d}")

class ChangeRequest(models.Model):
    STATUS = [("PENDING","PENDING"),("APPROVED","APPROVED"),("REJECTED","REJECTED")]
    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    target_row_id = models.CharField(max_length=32, blank=True)
    map_name = models.CharField(max_length=40)
    payload = models.JSONField()
    status = models.CharField(max_length=16, choices=STATUS, default="PENDING")
    decision_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="decisions")
    decision_at = models.DateTimeField(null=True, blank=True)
    def approve(self, approver):
        if self.status != "PENDING":
            return
        with transaction.atomic():
            data = self.payload.copy()
            data.setdefault("map_name", self.map_name)
            data.setdefault("operation", "update")
            data.setdefault("provider_sid", self.actor.username if self.actor else "api")
            data.setdefault("approver_sid", approver.username)
            obj, _ = AuthoredMapRow.objects.update_or_create(
                map_name=data["map_name"],
                row_id=data.get("row_id") or "",
                defaults=data
            )
            AuditEvent.log(actor=approver, op="approve", snapshot=obj, source="ChangeRequest")
            self.status = "APPROVED"
            self.decision_by = approver
            self.decision_at = datetime.utcnow()
            self.save()

class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ts = models.DateTimeField(auto_now_add=True)
    actor = models.CharField(max_length=64)
    op = models.CharField(max_length=32)
    source = models.CharField(max_length=32, default="UI")
    snapshot = models.JSONField()
    class Meta:
        ordering = ["-ts"]
    @staticmethod
    def log(actor, op, snapshot, source="UI"):
        from django.forms.models import model_to_dict
        AuditEvent.objects.create(actor=str(actor), op=op, source=source, snapshot=model_to_dict(snapshot))
