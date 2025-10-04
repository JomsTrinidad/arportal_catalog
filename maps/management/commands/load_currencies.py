from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from io import StringIO
import csv

from maps.models import UserProfile, AuthoredMapRow, AuditEvent, MapInfo

# Header row: names the columns for this map
HEADER = {
    "operation": "insert",
    "mode": "snapshot",        # snapshot => no start_dt/end_dt required
    "row_type": "header",
    "string_01": "currency_code",
    "string_02": "currency_name",
    "string_03": "country_code",  # left blank by default (multi-country currencies)
    "version": 1,
}

# ISO 4217 (active + commonly referenced) currency codes and names (ASCII).
# country_code intentionally blank so you can map specific countries later.
ISO4217_CSV = """code,name,country_code
AED,United Arab Emirates Dirham,
AFN,Afghani,
ALL,Lek,
AMD,Armenian Dram,
ANG,Netherlands Antillean Guilder,
AOA,Kwanza,
ARS,Argentine Peso,
AUD,Australian Dollar,
AWG,Aruban Florin,
AZN,Azerbaijan Manat,
BAM,Convertible Mark,
BBD,Barbados Dollar,
BDT,Taka,
BGN,Bulgarian Lev,
BHD,Bahraini Dinar,
BIF,Burundi Franc,
BMD,Bermudian Dollar,
BND,Brunei Dollar,
BOB,Boliviano,
BOV,Mvdol,
BRL,Brazilian Real,
BSD,Bahamian Dollar,
BTN,Ngultrum,
BWP,Pula,
BYN,Belarusian Ruble,
BZD,Belize Dollar,
CAD,Canadian Dollar,
CDF,Congolese Franc,
CHE,WIR Euro,
CHF,Swiss Franc,
CHW,WIR Franc,
CLF,Unidad de Fomento,
CLP,Chilean Peso,
CNY,Yuan Renminbi,
COP,Colombian Peso,
COU,Unidad de Valor Real,
CRC,Costa Rican Colon,
CUC,Peso Convertible,      # historical; kept for reference
CUP,Cuban Peso,
CVE,Cabo Verde Escudo,
CZK,Czech Koruna,
DJF,Djibouti Franc,
DKK,Danish Krone,
DOP,Dominican Peso,
DZD,Algerian Dinar,
EGP,Egyptian Pound,
ERN,Nakfa,
ETB,Ethiopian Birr,
EUR,Euro,
FJD,Fiji Dollar,
FKP,Falkland Islands Pound,
GBP,Pound Sterling,
GEL,Lari,
GHS,Ghana Cedi,
GIP,Gibraltar Pound,
GMD,Dalasi,
GNF,Guinean Franc,
GTQ,Quetzal,
GYD,Guyana Dollar,
HKD,Hong Kong Dollar,
HNL,Lempira,
HRK,Kuna,                 # historical; replaced by EUR in Croatia (2023)
HTG,Gourde,
HUF,Forint,
IDR,Rupiah,
ILS,New Israeli Shekel,
INR,Indian Rupee,
IQD,Iraqi Dinar,
IRR,Iranian Rial,
ISK,Isk,
JMD,Jamaican Dollar,
JOD,Jordanian Dinar,
JPY,Yen,
KES,Kenyan Shilling,
KGS,Som,
KHR,Riel,
KMF,Comorian Franc,
KPW,North Korean Won,
KRW,Won,
KWD,Kuwaiti Dinar,
KYD,Cayman Islands Dollar,
KZT,Tenge,
LAK,Lao Kip,
LBP,Lebanese Pound,
LKR,Sri Lanka Rupee,
LRD,Liberian Dollar,
LSL,Loti,
LYD,Libyan Dinar,
MAD,Moroccan Dirham,
MDL,Moldovan Leu,
MGA,Malagasy Ariary,
MKD,Denar,
MMK,Kyat,
MNT,Togrog,
MOP,Pataca,
MRU,Ouguiya,
MUR,Mauritius Rupee,
MVR,Rufiyaa,
MWK,Malawi Kwacha,
MXN,Mexican Peso,
MXV,Unidad de Inversion,
MYR,Malaysian Ringgit,
MZN,Mozambique Metical,
NAD,Namibia Dollar,
NGN,Naira,
NIO,Cordoba Oro,
NOK,Norwegian Krone,
NPR,Nepalese Rupee,
NZD,New Zealand Dollar,
OMR,Rial Omani,
PAB,Balboa,
PEN,Sol,
PGK,Kina,
PHP,Philippine Peso,
PKR,Pakistan Rupee,
PLN,Zloty,
PYG,Guarani,
QAR,Qatari Rial,
RON,Leu,
RSD,Serbian Dinar,
RUB,Russian Ruble,
RWF,Rwandan Franc,
SAR,Saudi Riyal,
SBD,Solomon Islands Dollar,
SCR,Seychelles Rupee,
SDG,Sudanese Pound,
SEK,Swedish Krona,
SGD,Singapore Dollar,
SHP,Saint Helena Pound,
SLE,Leone,               # new leone (Sierra Leone)
SLL,Leone (legacy),      # legacy; kept for reference
SOS,Somali Shilling,
SRD,Surinam Dollar,
SSP,South Sudanese Pound,
STN,Dobra,
SVC,El Salvador Colon,   # legacy (USD now used); kept for reference
SYP,Syrian Pound,
SZL,Lilangeni,
THB,Baht,
TJS,Somoni,
TMT,Turkmenistan New Manat,
TND,Tunisian Dinar,
TOP,Paanga,
TRY,Turkish Lira,
TTD,Trinidad and Tobago Dollar,
TWD,New Taiwan Dollar,
TZS,Tanzanian Shilling,
UAH,Hryvnia,
UGX,Uganda Shilling,
USD,US Dollar,
USN,US Dollar (Next day),
UYI,Uruguay Peso en Unidades Indexadas,
UYU,Peso Uruguayo,
UYW,Unidad Previsional,
UZS,Uzbekistan Sum,
VED,Bolivar (digital),    # alias used; current code is VES; VED kept if seen in feeds
VES,Bolivar Soberano,
VND,Dong,
VUV,Vatu,
WST,Tala,
XAF,CFA Franc BEAC,
XAG,Silver,
XAU,Gold,
XBA,Bond Markets Unit European Composite,
XBB,Bond Markets Unit European Monetary Unit,
XBC,Bond Markets Unit European Unit of Account 9,
XBD,Bond Markets Unit European Unit of Account 17,
XCD,East Caribbean Dollar,
XDR,SDR (IMF Special Drawing Right),
XOF,CFA Franc BCEAO,
XPD,Palladium,
XPF,CFP Franc,
XPT,Platinum,
XSU,Sucre,
XTS,Code reserved for testing,
XUA,ADB Unit of Account,
XXX,No currency,
YER,Yemeni Rial,
ZAR,Rand,
ZMW,Zambian Kwacha,
ZWL,Zimbabwe Dollar,
"""

class Command(BaseCommand):
    help = "Seed CURRENCY_CODES map (header + ISO 4217 currency codes). Idempotent."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Soft-delete existing CURRENCY_CODES v1 rows before seeding."
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        # --- Ensure demo users exist (re-used for provider/approver) ---
        encoder, _ = User.objects.get_or_create(
            username="encoder", defaults={"email": "encoder@example.com"}
        )
        if not encoder.has_usable_password():
            encoder.set_password("encoder"); encoder.save()

        approver, _ = User.objects.get_or_create(
            username="approver", defaults={"email": "approver@example.com"}
        )
        if not approver.has_usable_password():
            approver.set_password("approver"); approver.save()

        for u, name, role in [
            (encoder, "Encoder User", "user"),
            (approver, "Approver User", "owner"),
        ]:
            UserProfile.objects.get_or_create(user=u, defaults={"full_name": name, "role": role})

        # --- Map metadata ---
        MapInfo.objects.get_or_create(
            map_name="CURRENCY_CODES",
            defaults={"description": "ISO 4217 currency codes (code, name, optional country_code)."}
        )

        # Optional reset (soft delete existing rows for this map/version)
        if opts.get("reset"):
            qs = AuthoredMapRow.objects.filter(map_name="CURRENCY_CODES", version=1)
            updated = qs.update(deleted_flag="Y", is_undeleted="N", operation="delete")
            AuditEvent.log(actor="encoder", op="preseed-soft-delete", snapshot=qs.first() or {})
            self.stdout.write(self.style.WARNING(f"Soft-deleted {updated} existing CURRENCY_CODES rows."))

        # --- Header row (idempotent) ---
        header_lookup = dict(
            map_name="CURRENCY_CODES",
            version=1,
            row_type="header",
            string_01="currency_code",
            string_02="currency_name",
            string_03="country_code",
        )
        header_defaults = dict(
            operation="insert",
            provider_sid="encoder",
            approver_sid="approver",
            tracking_id="JIRA-CURRENCIES",
            mode="snapshot",
        )
        header_obj, created = AuthoredMapRow.objects.get_or_create(
            **header_lookup, defaults=header_defaults
        )
        if created:
            header_obj.full_clean(exclude=["index_id", "row_id"])
            header_obj.save()
            AuditEvent.log(actor="encoder", op="seed-header", snapshot=header_obj)

        # --- Values (codes + names; country_code blank by default) ---
        reader = csv.DictReader(StringIO(ISO4217_CSV.strip()))
        added, existing, updated = 0, 0, 0

        for rec in reader:
            code = (rec.get("code") or "").strip()
            name = (rec.get("name") or "").strip()
            country_code = (rec.get("country_code") or "").strip()

            if not code or not name:
                continue

            values_lookup = dict(
                map_name="CURRENCY_CODES",
                version=1,
                row_type="values",
                string_01=code,          # currency_code
            )
            values_defaults = dict(
                operation="insert",
                provider_sid="encoder",
                approver_sid="approver",
                tracking_id="JIRA-CURRENCIES",
                mode="snapshot",
                string_02=name,          # currency_name
                string_03=country_code,  # optional (blank by default)
            )

            obj, created_obj = AuthoredMapRow.objects.get_or_create(
                **values_lookup, defaults=values_defaults
            )
            if created_obj:
                obj.full_clean(exclude=["index_id", "row_id"])
                obj.save()
                AuditEvent.log(actor="encoder", op="seed-value", snapshot=obj)
                added += 1
            else:
                # keep idempotent but sync name/country_code if changed
                changed = False
                if obj.string_02 != name:
                    obj.string_02 = name; changed = True
                if obj.string_03 != country_code:
                    obj.string_03 = country_code; changed = True
                if changed:
                    obj.full_clean(exclude=["index_id", "row_id"])
                    obj.save()
                    AuditEvent.log(actor="encoder", op="seed-update", snapshot=obj)
                    updated += 1
                existing += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"CURRENCY_CODES ensured. added={added}, existing_checked={existing}, updated={updated}"
            )
        )
