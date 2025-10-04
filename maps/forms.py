from django import forms
from .models import AuthoredMapRow, ChangeRequest, MapInfo

class AuthoredMapRowForm(forms.ModelForm):
    class Meta:
        model = AuthoredMapRow
        exclude = ["index_id","row_id","load_dttm","modified_dttm","version"]
        widgets = { **{f"string_{i:02d}": forms.TextInput(attrs={"class":"form-control"}) for i in range(1,66)} }
    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("string_01"): self.add_error("string_01","Required")
        if not cleaned.get("string_02"): self.add_error("string_02","Required")
        return cleaned

class CSVUploadForm(forms.Form):
    csv_file = forms.FileField()
    map_name = forms.CharField(max_length=40)

class MapInfoForm(forms.ModelForm):
    class Meta:
        model = MapInfo
        fields = ["map_name","description"]
