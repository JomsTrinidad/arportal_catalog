from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import UserProfile, MapInfo, AuthoredMapRow, ChangeRequest, AuditEvent

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    fk_name = "user"

class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline, )

admin.site.unregister(User)
admin.site.register(User, UserAdmin)

@admin.register(MapInfo)
class MapInfoAdmin(admin.ModelAdmin):
    list_display = ("map_name","updated_at")
    search_fields = ("map_name","description")

@admin.register(AuthoredMapRow)
class AuthoredMapRowAdmin(admin.ModelAdmin):
    list_display = ("map_name","row_id","index_id","deleted_flag","version","modified_dttm")
    search_fields = ("map_name","row_id","string_01","string_02")

@admin.register(ChangeRequest)
class ChangeRequestAdmin(admin.ModelAdmin):
    list_display = ("id","map_name","status","created_at","actor")

@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("id","op","actor","ts","source")
