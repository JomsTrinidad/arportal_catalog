import csv
import io

from django.db.models import Case, When, Value, IntegerField, Max, Min
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy

from django.views.generic.edit import UpdateView
from django_tables2 import RequestConfig

from .filters import RowFilter
from .forms import AuthoredMapRowForm, CSVUploadForm
from .models import AuditEvent, AuthoredMapRow, ChangeRequest, MapInfo
from .tables import RowTable

from django.template.loader import render_to_string
from django.http import HttpResponse

import hashlib
from django.utils.timezone import now

def dashboard(request):
    """
    Home -> Catalog search.
    """
    return redirect("maps:catalog")


# -----------------------------
# Catalog search + drill-down
# -----------------------------

@login_required
def catalog(request):
    """
    Search by map_name or MapInfo.description.
    Lists grouped (map_name, version) with last_modified, tracking_id, provider_sid, approver_sid.
    """
    q = request.GET.get("q", "").strip()
    results = AuthoredMapRow.grouped_search(q)
    return render(request, "maps/catalog.html", {"q": q, "results": results})


@login_required
def map_version_view(request, map_name: str, version: int):
    """
    Show the full set of rows (and string_01..string_65) for a given map_name and version.
    FIELD_RANGE for 1..65 is provided via the context processor maps.context_processors.field_range.
    """
    rows = (
        AuthoredMapRow.objects.filter(map_name=map_name, version=version)
        .order_by("index_id")
    )
    info = MapInfo.objects.filter(map_name=map_name).first()
    return render(
        request,
        "maps/map_version.html",
        {"map_name": map_name, "version": version, "rows": rows, "info": info},
    )


# -----------------------------
# Row listing / detail / edit
# -----------------------------

@login_required
def row_list(request):
    """
    Table of rows (useful when you want to browse raw rows directly).
    """
    qs = AuthoredMapRow.objects.all().order_by("-modified_dttm")
    f = RowFilter(request.GET, queryset=qs)
    table = RowTable(f.qs)
    RequestConfig(request, paginate={"per_page": 20}).configure(table)
    return render(request, "maps/list.html", {"filter": f, "table": table})


@login_required
def row_detail(request, row_id: str):
    """
    Per-row detail page; includes actions to request delete/undelete or edit.
    """
    row = get_object_or_404(AuthoredMapRow, row_id=row_id)
    return render(request, "maps/detail.html", {"row": row})


class RowEditView(LoginRequiredMixin, UpdateView):
    """
    Direct edit (bypasses approval) – keep this for admins/staff only in the UI.
    """
    model = AuthoredMapRow
    slug_field = "row_id"
    slug_url_kwarg = "row_id"
    form_class = AuthoredMapRowForm
    template_name = "maps/edit.html"
    success_url = reverse_lazy("maps:list")


# -----------------------------
# Propose Edit (encoder -> approver)
# -----------------------------

@login_required
def propose_edit(request, row_id: str):
    """
    End-user proposes an edit to a row.
    We compute changed fields only and create a pending ChangeRequest for approvers.
    """
    row = get_object_or_404(AuthoredMapRow, row_id=row_id)

    if request.method == "POST":
        form = AuthoredMapRowForm(request.POST, instance=row)
        if form.is_valid():
            changes = {}
            for field, value in form.cleaned_data.items():
                # Skip computed/system fields
                if field in ["index_id", "row_id", "load_dttm", "modified_dttm", "version"]:
                    continue
                if getattr(row, field) != value:
                    changes[field] = value

            if not changes:
                messages.info(request, "No changes detected.")
                return redirect("maps:map_version", map_name=row.map_name, version=row.version)

            # Required identifiers for workflow
            changes.update({
                "row_id": row.row_id,
                "map_name": row.map_name,
                "operation": "update",
                "provider_sid": request.user.username,
            })

            ChangeRequest.objects.create(
                actor=request.user,
                map_name=row.map_name,
                target_row_id=row.row_id,
                payload=changes,
            )
            messages.success(request, "Proposed changes submitted for approval.")
            return redirect("maps:approvals")
    else:
        form = AuthoredMapRowForm(instance=row)

    return render(request, "maps/propose_edit.html", {"form": form, "row": row})


# -----------------------------
# CSV upload -> ChangeRequests
# -----------------------------

@login_required
def upload_csv(request):
    """
    Upload CSV and queue PENDING ChangeRequests (one per row in CSV).
    Approver will review/approve to materialize into AuthoredMapRow.
    """
    if request.method == "POST":
        form = CSVUploadForm(request.POST, request.FILES)
        if form.is_valid():
            f = form.cleaned_data["csv_file"]
            map_name = form.cleaned_data["map_name"]

            data = io.StringIO(f.read().decode("utf-8"))
            reader = csv.DictReader(data)
            count = 0
            for r in reader:
                payload = {k: v for k, v in r.items() if v is not None}
                payload["map_name"] = map_name
                # provider sid will be derived at approval if absent
                ChangeRequest.objects.create(actor=request.user, map_name=map_name, payload=payload)
                count += 1

            messages.success(request, f"Uploaded {count} rows into Change Requests (PENDING).")
            return redirect("maps:approvals")
    else:
        form = CSVUploadForm()

    return render(request, "maps/upload.html", {"form": form})


# -----------------------------
# Soft-delete / undelete requests
# -----------------------------

@login_required
def request_delete(request, row_id: str):
    """
    Create a PENDING delete request for a row (soft delete).
    """
    row = get_object_or_404(AuthoredMapRow, row_id=row_id)
    ChangeRequest.objects.create(
        actor=request.user,
        map_name=row.map_name,
        target_row_id=row.row_id,
        payload={"row_id": row.row_id, "deleted_flag": "Y", "operation": "delete"},
    )
    messages.info(request, "Delete requested, pending approval.")
    return redirect("maps:detail", row_id=row_id)


@login_required
def request_undelete(request, row_id: str):
    """
    Create a PENDING undelete request for a row.
    """
    row = get_object_or_404(AuthoredMapRow, row_id=row_id)
    ChangeRequest.objects.create(
        actor=request.user,
        map_name=row.map_name,
        target_row_id=row.row_id,
        payload={"row_id": row.row_id, "deleted_flag": "N", "is_undeleted": "Y", "operation": "undelete"},
    )
    messages.info(request, "Undelete requested, pending approval.")
    return redirect("maps:detail", row_id=row_id)


# -----------------------------
# Approvals workflow
# -----------------------------

@login_required
def approvals(request):
    """
    List PENDING change requests for review.
    """
    items = ChangeRequest.objects.filter(status="PENDING").order_by("-created_at")
    return render(request, "maps/approvals.html", {"items": items})


@login_required
def approval_detail(request, pk: int):
    """
    Review a single change request; approve applies the payload (via ChangeRequest.approve()).
    """
    cr = get_object_or_404(ChangeRequest, pk=pk)
    current = None
    if cr.target_row_id:
        try:
            current = AuthoredMapRow.objects.get(row_id=cr.target_row_id)
        except AuthoredMapRow.DoesNotExist:
            current = None

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "approve":
            cr.approve(request.user)
            messages.success(request, "Change approved.")
            return redirect("maps:approvals")
        elif action == "reject":
            cr.status = "REJECTED"
            cr.decision_by = request.user
            cr.save()
            messages.warning(request, "Change rejected.")
            return redirect("maps:approvals")

    return render(
        request,
        "maps/approval_detail.html",
        {"cr": cr, "current": current, "payload": cr.payload},
    )

@login_required
def map_version_fragment(request, map_name: str, version: int):
    # --- read and validate sorting params ---
    sort = request.GET.get("sort")
    direction = request.GET.get("dir", "asc").lower()
    allowed = {"row_id", "deleted_flag", "row_type"} | {f"string_{i:02d}" for i in range(1, 66)}
    if sort not in allowed:
        sort = None
    if direction not in {"asc", "desc"}:
        direction = "asc"

    base_qs = AuthoredMapRow.objects.filter(map_name=map_name, version=version)

    # Header first (row_type='header'), then apply chosen sort to values
    qs = base_qs.annotate(
        header_order=Case(
            When(row_type="header", then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    )

    # Split header vs values
    header = qs.filter(row_type="header").first()
    values = qs.exclude(row_type="header")

    # Build order fields for values
    order_fields = []
    if sort:
        order_fields.append(f"-{sort}" if direction == "desc" else sort)
    # Stable secondary order (by index_id so rows don’t jump unpredictably)
    order_fields.append("index_id")
    values = values.order_by(*order_fields)

    info = MapInfo.objects.filter(map_name=map_name).first()

    html = render_to_string(
        "maps/_map_version_table.html",
        {
            "map_name": map_name,
            "version": version,
            "header": header,
            "rows": values,
            "total_rows": values.count(),
            "sort": sort,
            "direction": direction,
        },
        request=request,
    )
    return HttpResponse(html)

@login_required
def propose_edit_fragment(request, row_id: str):
    """
    Shows/submits a propose-edit form *and* preserves current sorting of the table.
    Accepts ?sort=<field>&dir=asc|desc (same as map_version_fragment).
    """
    # ---- read sort params (shared with the table fragment) ----
    sort = request.GET.get("sort")
    direction = request.GET.get("dir", "asc").lower()
    allowed = {"row_id", "deleted_flag", "row_type"} | {f"string_{i:02d}" for i in range(1, 66)}
    if sort not in allowed:
        sort = None
    if direction not in {"asc", "desc"}:
        direction = "asc"

    row = get_object_or_404(AuthoredMapRow, row_id=row_id)

    if request.method == "POST":
        form = AuthoredMapRowForm(request.POST, instance=row)
        if form.is_valid():
            changes = {}
            for field, value in form.cleaned_data.items():
                if field in ["index_id", "row_id", "load_dttm", "modified_dttm", "version"]:
                    continue
                if getattr(row, field) != value:
                    changes[field] = value

            if changes:
                changes.update({
                    "row_id": row.row_id,
                    "map_name": row.map_name,
                    "operation": "update",
                    "provider_sid": request.user.username,
                })
                ChangeRequest.objects.create(
                    actor=request.user,
                    map_name=row.map_name,
                    target_row_id=row.row_id,
                    payload=changes,
                )

            # After submit (or no changes), re-render the sorted table
            base_qs = AuthoredMapRow.objects.filter(map_name=row.map_name, version=row.version)
            qs = base_qs.annotate(
                header_order=Case(
                    When(row_type="header", then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            )
            header = qs.filter(row_type="header").first()
            values = qs.exclude(row_type="header")

            order_fields = []
            if sort:
                order_fields.append(f"-{sort}" if direction == "desc" else sort)
            order_fields.append("index_id")  # stable tiebreak
            values = values.order_by(*order_fields)

            info = MapInfo.objects.filter(map_name=row.map_name).first()
            html = render_to_string(
                "maps/_map_version_table.html",
                {
                    "map_name": row.map_name,
                    "version": row.version,
                    "header": header,
                    "rows": values,
                    "total_rows": values.count(),
                    "sort": sort,
                    "direction": direction,
                },
                request=request,
            )
            return HttpResponse(html)
    else:
        form = AuthoredMapRowForm(instance=row)

    # Render the form fragment (carry sort/dir so the buttons include them)
    html = render_to_string(
        "maps/_propose_edit_form.html",
        {"form": form, "row": row, "sort": sort, "direction": direction},
        request=request,
    )
    return HttpResponse(html)


FIELD_RANGE = range(1, 66)

@login_required
def edit_mode(request, map_name: str, version: int):
    """
    Full-page edit mode with:
    - Meta (version, map_name, description, last_modified, created)
    - Per-row propose edit / delete/undelete
    - Batch Add Rows (spreadsheet-like) or Add Header (append only)
    """
    base_qs = AuthoredMapRow.objects.filter(map_name=map_name, version=version)
    qs = base_qs.annotate(
        header_order=Case(
            When(row_type="header", then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    ).order_by("header_order", "index_id")

    header = qs.filter(row_type="header").first()
    values = qs.exclude(row_type="header")
    info = MapInfo.objects.filter(map_name=map_name).first()

    agg = base_qs.aggregate(last_modified=Max("modified_dttm"), created=Min("load_dttm"))
    last_modified = agg["last_modified"]
    created = agg["created"]

    # Build header labels & active set
    header_labels = []
    active_indices = []
    last_active_idx = 0
    for i in FIELD_RANGE:
        label = ""
        if header:
            label = (getattr(header, f"string_{i:02d}", "") or "").strip()
        header_labels.append(label)
        if label:
            active_indices.append(i)
            last_active_idx = i

    # Existing row_ids (for duplicate marking of existing rows when a batch error occurs)
    existing_row_ids = list(values.values_list("row_id", flat=True))

    # Batch add UI toggles
    show_new = request.GET.get("new") == "1"
    new_row_type = request.GET.get("new_row_type", "values")  # 'values' or 'header'

    # Optional context for re-render after a failed POST
    bulk_rows = request.GET.get("bulk_rows")  # not used directly; kept for pattern
    # But we’ll pass 'bulk_rows' & 'dup_indices' directly when returning from POST

    return render(
        request,
        "maps/edit_mode.html",
        {
            "map_name": map_name,
            "version": version,
            "header": header,
            "rows": values,
            "total_rows": values.count(),
            "info": info,
            "last_modified": last_modified,
            "created": created,
            "show_new": show_new,
            "new_row_type": new_row_type,
            "FIELD_RANGE": FIELD_RANGE,
            "header_labels": header_labels,
            "active_indices": active_indices,
            "last_active_idx": last_active_idx,
            "existing_row_ids": existing_row_ids,
            # The two below are used when POST failed and we need to repopulate
            "bulk_rows": request.session.pop("bulk_rows", None),
            "dup_indices": request.session.pop("dup_indices", None),
            "dup_existing_ids": request.session.pop("dup_existing_ids", None),
        },
    )

@login_required
def propose_edit_full(request, row_id: str):
    """
    Full-page propose-edit for a single row (not in the split pane).
    """
    row = get_object_or_404(AuthoredMapRow, row_id=row_id)

    if request.method == "POST":
        form = AuthoredMapRowForm(request.POST, instance=row)
        if form.is_valid():
            changes = {}
            for field, value in form.cleaned_data.items():
                if field in ["index_id", "row_id", "load_dttm", "modified_dttm", "version"]:
                    continue
                if getattr(row, field) != value:
                    changes[field] = value

            if not changes:
                messages.info(request, "No changes detected.")
                return redirect("maps:edit_mode", map_name=row.map_name, version=row.version)

            changes.update({
                "row_id": row.row_id,
                "map_name": row.map_name,
                "operation": "update",
                "provider_sid": request.user.username,
            })

            ChangeRequest.objects.create(
                actor=request.user,
                map_name=row.map_name,
                target_row_id=row.row_id,
                payload=changes,
            )
            messages.success(request, "Proposed changes submitted for approval.")
            return redirect("maps:approvals")
    else:
        form = AuthoredMapRowForm(instance=row)

    return render(request, "maps/propose_edit_full.html", {"form": form, "row": row})


@login_required
def add_row(request, map_name: str, version: int):
    """
    Full-page add-new-row. Creates a PENDING ChangeRequest(operation='insert').
    """
    # create a temporary instance with initial map_name/version so form shows context
    temp = AuthoredMapRow(map_name=map_name, version=version, row_type="values", operation="insert")

    if request.method == "POST":
        form = AuthoredMapRowForm(request.POST, instance=temp)
        if form.is_valid():
            payload = {}
            for field, value in form.cleaned_data.items():
                # exclude system/computed fields
                if field in ["index_id", "row_id", "load_dttm", "modified_dttm", "version"]:
                    continue
                payload[field] = value

            # required identifiers
            payload.update({
                "map_name": map_name,
                "operation": "insert",
                "provider_sid": request.user.username,
                "row_type": payload.get("row_type") or "values",
            })

            ChangeRequest.objects.create(
                actor=request.user,
                map_name=map_name,
                payload=payload,
            )
            messages.success(request, "Insert request submitted for approval.")
            return redirect("maps:edit_mode", map_name=map_name, version=version)
    else:
        form = AuthoredMapRowForm(instance=temp)

    return render(request, "maps/add_row.html", {"form": form, "map_name": map_name, "version": version})

# -----------------------------
# Queue the inline insert (new-row at bottom)
# -----------------------------

@login_required
def queue_insert(request, map_name: str, version: int):
    """
    Handle the inline new-row form at the bottom of Edit Mode.
    Always enforces row_type='values'.
    Only accepts inputs for columns that already have header labels.
    Accepts tracking_id and change_note.
    Creates a PENDING ChangeRequest(operation='insert').
    """
    if request.method != "POST":
        return redirect("maps:edit_mode", map_name=map_name, version=version)

    # Determine active header columns
    header = AuthoredMapRow.objects.filter(map_name=map_name, version=version, row_type="header").first()
    active_set = set()
    if header:
        for i in range(1, 66):
            if (getattr(header, f"string_{i:02d}", "") or "").strip():
                active_set.add(i)

    payload = {
        "map_name": map_name,
        "operation": "insert",
        "provider_sid": request.user.username,
        "row_type": "values",  # enforced
        "tracking_id": (request.POST.get("tracking_id") or "").strip(),
        "change_note": (request.POST.get("change_note") or "").strip(),
    }

    any_value = False
    invalid_fields = []

    for i in range(1, 66):
        key = f"string_{i:02d}"
        val = (request.POST.get(key) or "").strip()
        if not val:
            continue
        if i not in active_set:
            invalid_fields.append(key)
            continue
        payload[key] = val
        any_value = True

    if invalid_fields:
        messages.error(
            request,
            "You entered data for columns without headers: "
            + ", ".join(invalid_fields)
            + ". Please add headers first (use 'Add New Header'), then add the row."
        )
        return redirect(f"{request.META.get('HTTP_REFERER', '') or '/'}#new-row")

    if not any_value:
        messages.warning(request, "Nothing entered. Please fill at least one string_XX field that has a header.")
        return redirect("maps:edit_mode", map_name=map_name, version=version)

    ChangeRequest.objects.create(
        actor=request.user,
        map_name=map_name,
        payload=payload,
    )
    messages.success(request, "Insert request submitted for approval.")
    return redirect("maps:edit_mode", map_name=map_name, version=version)

# -----------------------------
# Change summary page (counts of added/updated/deleted + predicted version)
# -----------------------------

@login_required
def change_summary(request, map_name: str, version: int):
    """
    Show a summary of the current user's pending changes for this map.
    Counts inserts/updates/deletes and predicts the version bump if 'replace' is requested.
    """
    pending = ChangeRequest.objects.filter(map_name=map_name, status="PENDING", actor=request.user)
    added = pending.filter(payload__operation="insert").count()
    updated = pending.filter(payload__operation="update").count()
    deleted = pending.filter(payload__operation="delete").count()

    replace = request.GET.get("replace") == "1"
    predicted_version = version + 1 if replace else version

    return render(
        request,
        "maps/change_summary.html",
        {
            "map_name": map_name,
            "version": version,
            "added": added,
            "updated": updated,
            "deleted": deleted,
            "replace": replace,
            "predicted_version": predicted_version,
        },
    )

@login_required
def request_delete(request, row_id: str):
    """
    Queue a delete request for a row (soft-delete when approved).
    Header rows cannot be deleted.
    """
    row = get_object_or_404(AuthoredMapRow, row_id=row_id)

    if row.row_type == "header":
        messages.error(request, "Header rows cannot be deleted. You may add new headers but not remove them.")
        return redirect("maps:edit_mode", map_name=row.map_name, version=row.version)

    # Already deleted?
    if str(row.deleted_flag).upper() == "Y":
        messages.info(request, "Row is already marked deleted.")
        return redirect("maps:edit_mode", map_name=row.map_name, version=row.version)

    ChangeRequest.objects.create(
        actor=request.user,
        map_name=row.map_name,
        target_row_id=row.row_id,
        payload={
            "operation": "delete",
            "row_id": row.row_id,
            "map_name": row.map_name,
            "provider_sid": request.user.username,
        },
    )
    messages.success(request, "Delete request submitted for approval.")
    return redirect("maps:edit_mode", map_name=row.map_name, version=row.version)


@login_required
def request_undelete(request, row_id: str):
    """
    Queue an undelete request for a row (restores when approved).
    """
    row = get_object_or_404(AuthoredMapRow, row_id=row_id)

    # Already active?
    if str(row.deleted_flag).upper() != "Y":
        messages.info(request, "Row is not deleted.")
        return redirect("maps:edit_mode", map_name=row.map_name, version=row.version)

    ChangeRequest.objects.create(
        actor=request.user,
        map_name=row.map_name,
        target_row_id=row.row_id,
        payload={
            "operation": "undelete",
            "row_id": row.row_id,
            "map_name": row.map_name,
            "provider_sid": request.user.username,
        },
    )
    messages.success(request, "Undelete request submitted for approval.")
    return redirect("maps:edit_mode", map_name=row.map_name, version=row.version)


# ---------------------------------------------------
# Add a small handler to append a header cell (next available only)
# ---------------------------------------------------

@login_required
def queue_add_header(request, map_name: str, version: int):
    """
    Inline 'Add New Header' — enables only the next available header cell
    (string_{last_active_idx+1}) in the header row. Queues an UPDATE ChangeRequest
    targeting the header row.
    """
    if request.method != "POST":
        return redirect("maps:edit_mode", map_name=map_name, version=version)

    header = get_object_or_404(AuthoredMapRow, map_name=map_name, version=version, row_type="header")

    # Find next available header index
    last = 0
    for i in range(1, 66):
        if (getattr(header, f"string_{i:02d}", "") or "").strip():
            last = i
    next_idx = last + 1
    if next_idx > 65:
        messages.error(request, "Maximum number of header columns (65) reached.")
        return redirect("maps:edit_mode", map_name=map_name, version=version)

    key = f"string_{next_idx:02d}"
    label = (request.POST.get(key) or "").strip()
    if not label:
        messages.warning(request, "Please enter a header label.")
        return redirect("maps:edit_mode", map_name=map_name, version=version)

    payload = {
        "operation": "update",
        "row_id": header.row_id,
        "map_name": map_name,
        "provider_sid": request.user.username,
        key: label,
        "change_note": (request.POST.get("change_note") or "").strip(),
        "tracking_id": (request.POST.get("tracking_id") or "").strip(),
    }

    ChangeRequest.objects.create(
        actor=request.user,
        map_name=map_name,
        target_row_id=header.row_id,
        payload=payload,
    )
    messages.success(request, f"Header '{key}' queued with label '{label}'.")
    return redirect("maps:edit_mode", map_name=map_name, version=version)


#---------------------------------------
# Implement bulk insert with duplicate validation
#---------------------------------------
def _compute_row_id_like_model(map_name: str, version: int, row_type: str, strings: dict) -> str:
    """
    Compute row_id similarly to model's business-hash.
    We include: map_name, version, row_type, and string_01..string_65 (empty treated as '').
    Adjust if your actual model includes more business columns in the hash.
    """
    parts = [map_name, str(version), row_type]
    for i in range(1, 66):
        parts.append(strings.get(f"string_{i:02d}", "") or "")
    payload = "||".join(parts)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()

@login_required
def queue_bulk_insert(request, map_name: str, version: int):
    """
    Batch add up to 100 rows.
    - Only accepts values for columns that already have header labels.
    - Validates duplicates within batch and against existing DB rows by row_id.
    - On error re-renders edit mode with bad rows highlighted.
    - On success, creates one ChangeRequest per row (PENDING).
    """
    if request.method != "POST":
        return redirect("maps:edit_mode", map_name=map_name, version=version)

    # Determine active header columns
    header = AuthoredMapRow.objects.filter(map_name=map_name, version=version, row_type="header").first()
    active_set = set()
    if header:
        for i in range(1, 66):
            if (getattr(header, f"string_{i:02d}", "") or "").strip():
                active_set.add(i)

    # How many rows (capped at 100)
    try:
        rows_count = int(request.POST.get("rows_count", "0"))
    except ValueError:
        rows_count = 0
    rows_count = max(0, min(100, rows_count))

    # Tracking / change note once per batch
    tracking_id = (request.POST.get("tracking_id") or "").strip()
    change_note = (request.POST.get("change_note") or "").strip()

    # Parse rows
    bulk_rows = []        # list of dicts with string_XX only
    computed_ids = []     # computed row_id per row (for duplicate detection)
    dup_indices = set()   # 0-based indices of duplicate rows within batch
    seen_ids = {}         # row_id -> first index

    # Existing row_ids for this map/version
    existing_ids = set(AuthoredMapRow.objects.filter(map_name=map_name, version=version, row_type="values").values_list("row_id", flat=True))
    dup_existing_ids = set()  # subset that collide

    for idx in range(rows_count):
        row_data = {}
        any_value = False
        for i in range(1, 66):
            key = f"rows-{idx}-string_{i:02d}"
            val = (request.POST.get(key) or "").strip()
            if not val:
                continue
            if i not in active_set:
                # entered data for a non-header column → treat as invalid by ignoring it
                # you can also abort here if you prefer hard fail.
                continue
            row_data[f"string_{i:02d}"] = val
            any_value = True

        if not any_value:
            # Skip completely empty rows (user added but didn't type anything)
            bulk_rows.append({})
            computed_ids.append(None)
            continue

        # Compute row_id like the model (map_name, version, row_type='values', strings)
        rid = _compute_row_id_like_model(map_name, version, "values", row_data)

        # Duplicate within batch?
        if rid in seen_ids:
            dup_indices.add(seen_ids[rid])
            dup_indices.add(idx)
        else:
            seen_ids[rid] = idx

        # Duplicate vs existing?
        if rid in existing_ids:
            dup_existing_ids.add(rid)

        bulk_rows.append(row_data)
        computed_ids.append(rid)

    # If duplicates found, bounce back with highlighting
    if dup_indices or dup_existing_ids:
        messages.error(
            request,
            "Duplicate rows detected. Please resolve the highlighted rows. "
            + (f"({len(dup_indices)} in batch; {len(dup_existing_ids)} conflict with existing rows.)" if dup_indices or dup_existing_ids else "")
        )
        # Preserve what the user typed so we can re-render
        request.session["bulk_rows"] = bulk_rows
        request.session["dup_indices"] = sorted(list(dup_indices))
        request.session["dup_existing_ids"] = list(dup_existing_ids)
        return redirect(f"{request.build_absolute_uri()}?new=1&new_row_type=values#new-batch")

    # No duplicates: create CRs
    created = 0
    for row_data in bulk_rows:
        if not row_data:
            continue
        payload = {
            "map_name": map_name,
            "operation": "insert",
            "provider_sid": request.user.username,
            "row_type": "values",
            "tracking_id": tracking_id,
            "change_note": change_note,
        }
        payload.update(row_data)
        ChangeRequest.objects.create(
            actor=request.user,
            map_name=map_name,
            payload=payload,
        )
        created += 1

    messages.success(request, f"Queued {created} insert(s) for approval.")
    return redirect("maps:edit_mode", map_name=map_name, version=version)
