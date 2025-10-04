from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from maps.models import UserProfile, AuthoredMapRow, AuditEvent, MapInfo
from io import StringIO
import csv


HEADER = {
    "operation": "insert",
    "mode": "snapshot",      # snapshot => no start_dt/end_dt required
    "row_type": "header",
    "string_01": "country_code",
    "string_02": "country_name",
    "string_03": "continent",
    "version": 1,
}

# Full ISO 3166-1 alpha-2 codes with ASCII country names.
# continent left blank intentionally (fill later if desired).
ISO_ALPHA2_CSV = """code,name,continent
AF,Afghanistan,
AX,Aland Islands,
AL,Albania,
DZ,Algeria,
AS,American Samoa,
AD,Andorra,
AO,Angola,
AI,Anguilla,
AQ,Antarctica,
AG,Antigua and Barbuda,
AR,Argentina,
AM,Armenia,
AW,Aruba,
AU,Australia,
AT,Austria,
AZ,Azerbaijan,
BS,Bahamas,
BH,Bahrain,
BD,Bangladesh,
BB,Barbados,
BY,Belarus,
BE,Belgium,
BZ,Belize,
BJ,Benin,
BM,Bermuda,
BT,Bhutan,
BO,Bolivia,
BQ,Bonaire Sint Eustatius and Saba,
BA,Bosnia and Herzegovina,
BW,Botswana,
BV,Bouvet Island,
BR,Brazil,
IO,British Indian Ocean Territory,
BN,Brunei Darussalam,
BG,Bulgaria,
BF,Burkina Faso,
BI,Burundi,
CV,Cabo Verde,
KH,Cambodia,
CM,Cameroon,
CA,Canada,
KY,Cayman Islands,
CF,Central African Republic,
TD,Chad,
CL,Chile,
CN,China,
CX,Christmas Island,
CC,Cocos Islands,
CO,Colombia,
KM,Comoros,
CG,Congo,
CD,Congo The Democratic Republic of the,
CK,Cook Islands,
CR,Costa Rica,
CI,Cote d'Ivoire,
HR,Croatia,
CU,Cuba,
CW,Curacao,
CY,Cyprus,
CZ,Czechia,
DK,Denmark,
DJ,Djibouti,
DM,Dominica,
DO,Dominican Republic,
EC,Ecuador,
EG,Egypt,
SV,El Salvador,
GQ,Equatorial Guinea,
ER,Eritrea,
EE,Estonia,
SZ,Eswatini,
ET,Ethiopia,
FK,Falkland Islands,
FO,Faroe Islands,
FJ,Fiji,
FI,Finland,
FR,France,
GF,French Guiana,
PF,French Polynesia,
TF,French Southern Territories,
GA,Gabon,
GM,Gambia,
GE,Georgia,
DE,Germany,
GH,Ghana,
GI,Gibraltar,
GR,Greece,
GL,Greenland,
GD,Grenada,
GP,Guadeloupe,
GU,Guam,
GT,Guatemala,
GG,Guernsey,
GN,Guinea,
GW,Guinea-Bissau,
GY,Guyana,
HT,Haiti,
HM,Heard Island and McDonald Islands,
VA,Holy See,
HN,Honduras,
HK,Hong Kong,
HU,Hungary,
IS,Iceland,
IN,India,
ID,Indonesia,
IR,Iran,
IQ,Iraq,
IE,Ireland,
IM,Isle of Man,
IL,Israel,
IT,Italy,
JM,Jamaica,
JP,Japan,
JE,Jersey,
JO,Jordan,
KZ,Kazakhstan,
KE,Kenya,
KI,Kiribati,
KP,Korea North,
KR,Korea South,
KW,Kuwait,
KG,Kyrgyzstan,
LA,Lao People's Democratic Republic,
LV,Latvia,
LB,Lebanon,
LS,Lesotho,
LR,Liberia,
LY,Libya,
LI,Liechtenstein,
LT,Lithuania,
LU,Luxembourg,
MO,Macao,
MK,North Macedonia,
MG,Madagascar,
MW,Malawi,
MY,Malaysia,
MV,Maldives,
ML,Mali,
MT,Malta,
MH,Marshall Islands,
MQ,Martinique,
MR,Mauritania,
MU,Mauritius,
YT,Mayotte,
MX,Mexico,
FM,Micronesia,
MD,Moldova,
MC,Monaco,
MN,Mongolia,
ME,Montenegro,
MS,Montserrat,
MA,Morocco,
MZ,Mozambique,
MM,Myanmar,
NA,Namibia,
NR,Nauru,
NP,Nepal,
NL,Netherlands,
NC,New Caledonia,
NZ,New Zealand,
NI,Nicaragua,
NE,Niger,
NG,Nigeria,
NU,Niue,
NF,Norfolk Island,
MP,Northern Mariana Islands,
NO,Norway,
OM,Oman,
PK,Pakistan,
PW,Palau,
PS,Palestine State of,
PA,Panama,
PG,Papua New Guinea,
PY,Paraguay,
PE,Peru,
PH,Philippines,
PN,Pitcairn,
PL,Poland,
PT,Portugal,
PR,Puerto Rico,
QA,Qatar,
RE,Reunion,
RO,Romania,
RU,Russia,
RW,Rwanda,
BL,Saint Barthelemy,
SH,Saint Helena Ascension and Tristan da Cunha,
KN,Saint Kitts and Nevis,
LC,Saint Lucia,
MF,Saint Martin,
PM,Saint Pierre and Miquelon,
VC,Saint Vincent and the Grenadines,
WS,Samoa,
SM,San Marino,
ST,Sao Tome and Principe,
SA,Saudi Arabia,
SN,Senegal,
RS,Serbia,
SC,Seychelles,
SL,Sierra Leone,
SG,Singapore,
SX,Sint Maarten,
SK,Slovakia,
SI,Slovenia,
SB,Solomon Islands,
SO,Somalia,
ZA,South Africa,
GS,South Georgia and the South Sandwich Islands,
SS,South Sudan,
ES,Spain,
LK,Sri Lanka,
SD,Sudan,
SR,Suriname,
SJ,Svalbard and Jan Mayen,
SE,Sweden,
CH,Switzerland,
SY,Syria,
TW,Taiwan,
TJ,Tajikistan,
TZ,Tanzania,
TH,Thailand,
TL,Timor-Leste,
TG,Togo,
TK,Tokelau,
TO,Tonga,
TT,Trinidad and Tobago,
TN,Tunisia,
TR,Turkey,
TM,Turkmenistan,
TC,Turks and Caicos Islands,
TV,Tuvalu,
UG,Uganda,
UA,Ukraine,
AE,United Arab Emirates,
GB,United Kingdom,
US,United States,
UM,United States Minor Outlying Islands,
UY,Uruguay,
UZ,Uzbekistan,
VU,Vanuatu,
VE,Venezuela,
VN,Viet Nam,
VG,Virgin Islands British,
VI,Virgin Islands US,
WF,Wallis and Futuna,
EH,Western Sahara,
YE,Yemen,
ZM,Zambia,
ZW,Zimbabwe,
"""


class Command(BaseCommand):
    help = "Load demo data safely (idempotent) with header + full ISO country codes."

    def handle(self, *args, **kwargs):
        # --- Users (idempotent) ---
        encoder, _ = User.objects.get_or_create(
            username="encoder",
            defaults={"email": "encoder@example.com"}
        )
        if not encoder.has_usable_password():
            encoder.set_password("encoder")
            encoder.save()

        approver, _ = User.objects.get_or_create(
            username="approver",
            defaults={"email": "approver@example.com"}
        )
        if not approver.has_usable_password():
            approver.set_password("approver")
            approver.save()

        for u, name, role in [
            (encoder, "Encoder User", "user"),
            (approver, "Approver User", "owner"),
        ]:
            UserProfile.objects.get_or_create(user=u, defaults={"full_name": name, "role": role})

        # --- Map metadata ---
        MapInfo.objects.get_or_create(
            map_name="COUNTRY_CODES",
            defaults={"description": "ISO 3166-1 alpha-2 country codes (demo seed)."}
        )

        # --- Header row (idempotent) ---
        header_lookup = dict(
            map_name="COUNTRY_CODES",
            version=1,
            row_type="header",
            string_01="country_code",
            string_02="country_name",
            string_03="continent",
        )
        header_defaults = dict(
            operation="insert",
            provider_sid="encoder",
            approver_sid="approver",
            tracking_id="JIRA-COUNTRIES",
            mode="snapshot",
        )
        header_obj, created = AuthoredMapRow.objects.get_or_create(
            **header_lookup, defaults=header_defaults
        )
        if created:
            header_obj.full_clean(exclude=["index_id", "row_id"])
            header_obj.save()
            AuditEvent.log(actor="encoder", op="seed-header", snapshot=header_obj)

        # --- Values rows (full ISO-3166-1) ---
        reader = csv.DictReader(StringIO(ISO_ALPHA2_CSV.strip()))
        count_new, count_existing = 0, 0

        for rec in reader:
            code = (rec.get("code") or "").strip()
            name = (rec.get("name") or "").strip()
            continent = (rec.get("continent") or "").strip()  # optional/blank by default
            if not code or not name:
                continue

            values_lookup = dict(
                map_name="COUNTRY_CODES",
                version=1,
                row_type="values",
                string_01=code,         # country_code
            )
            values_defaults = dict(
                operation="insert",
                provider_sid="encoder",
                approver_sid="approver",
                tracking_id="JIRA-COUNTRIES",
                mode="snapshot",
                string_02=name,         # country_name
                string_03=continent,    # continent (blank by default)
            )

            obj, created = AuthoredMapRow.objects.get_or_create(
                **values_lookup, defaults=values_defaults
            )
            if created:
                obj.full_clean(exclude=["index_id", "row_id"])
                obj.save()
                AuditEvent.log(actor="encoder", op="seed-value", snapshot=obj)
                count_new += 1
            else:
                # Keep idempotent but update name/continent if changed
                changed = False
                if obj.string_02 != name:
                    obj.string_02 = name
                    changed = True
                if obj.string_03 != continent:
                    obj.string_03 = continent
                    changed = True
                if changed:
                    obj.full_clean(exclude=["index_id", "row_id"])
                    obj.save()
                    AuditEvent.log(actor="encoder", op="seed-update", snapshot=obj)
                count_existing += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo data ensured. Added {count_new} countries, checked {count_existing} existing."
            )
        )
