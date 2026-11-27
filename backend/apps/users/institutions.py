"""Validated catalog writes and bounded, all-or-nothing imports shared by API/admin."""
import csv
from datetime import date, datetime
from io import BytesIO, StringIO
from zipfile import BadZipFile, ZipFile
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException

from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from .institution_fields import validate_aliases, validate_levels
from .models import Institution, User

FIELDS = ('code', 'name', 'aliases', 'province', 'campus', 'levels', 'external_code',
          'source_url', 'source_checked_at', 'active')
REQUIRED = {'code', 'name', 'province', 'levels', 'source_url', 'source_checked_at'}
MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 500


def require_catalog_admin(actor, *permissions):
    user = User.objects.filter(pk=actor.pk, role=User.Role.ADMIN, status=User.Status.ACTIVE, is_active=True).first()
    if user is None or not all(user.has_perm('users.' + name + '_institution') for name in permissions):
        raise PermissionError('Catalog administration permission required.')
    return user


def prepare_institution(values, instance=None):
    if not isinstance(values, dict) or set(values) - set(FIELDS):
        raise ValidationError({'detail': 'Unexpected catalog fields.'})
    obj = instance or Institution()
    if instance and 'code' in values and values['code'] != instance.code:
        raise ValidationError({'code': 'The stable catalog code cannot be changed.'})
    for field, value in values.items():
        setattr(obj, field, value)
    validate_aliases(obj.aliases)
    validate_levels(obj.levels)
    for field in ('name', 'province', 'campus'):
        if not isinstance(getattr(obj, field), str):
            raise ValidationError({field: 'Expected text.'})
    if type(obj.active) is not bool:
        raise ValidationError({'active': 'Expected a boolean.'})
    if isinstance(obj.source_checked_at, str):
        try:
            obj.source_checked_at = date.fromisoformat(obj.source_checked_at)
        except ValueError as exc:
            raise ValidationError({'source_checked_at': 'Use YYYY-MM-DD.'}) from exc
    if not isinstance(obj.source_checked_at, date) or obj.source_checked_at > timezone.localdate():
        raise ValidationError({'source_checked_at': 'Use a real source review date, not a future date.'})
    if not isinstance(obj.source_url, str) or not obj.source_url.startswith('https://'):
        raise ValidationError({'source_url': 'Provide an HTTPS source URL.'})
    obj.prepare_search()
    if not obj.province_key or not obj.name or not any(c.isalnum() for c in obj.name):
        raise ValidationError({'name': 'Provide a school name and province.'})
    obj.full_clean()
    return obj


def record_change(actor, obj, created):
    LogEntry.objects.log_actions(user_id=actor.pk, queryset=[obj],
        action_flag=ADDITION if created else CHANGE, change_message='Institution catalog update', single_object=True)


@transaction.atomic
def save_institution(*, actor, values, institution_id=None):
    user = require_catalog_admin(actor, 'change' if institution_id else 'add')
    obj = Institution.objects.select_for_update().get(pk=institution_id) if institution_id else None
    obj = prepare_institution(values, obj)
    try:
        with transaction.atomic():
            obj.save()
    except IntegrityError as exc:
        raise ValidationError({'code': 'Catalog code or school identity already exists.'}) from exc
    record_change(user, obj, institution_id is None)
    return obj


def read_import(upload):
    data = upload.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValidationError({'file': 'Maximum upload size is 2 MiB.'})
    name = upload.name.lower()
    try:
        if name.endswith('.csv'):
            rows = list(csv.reader(StringIO(data.decode('utf-8-sig')), strict=True))
        elif name.endswith('.xlsx'):
            from openpyxl import load_workbook
            with ZipFile(BytesIO(data)) as archive:
                if len(archive.infolist()) > 100 or sum(i.file_size for i in archive.infolist()) > 10 * 1024**2:
                    raise ValidationError({'file': 'Expanded workbook exceeds limits.'})
                if any('vbaProject' in i.filename or 'externalLinks/' in i.filename for i in archive.infolist()):
                    raise ValidationError({'file': 'Macros and external links are not accepted.'})
            book = load_workbook(BytesIO(data), read_only=True, data_only=False, keep_links=False)
            try:
                if len(book.worksheets) != 1:
                    raise ValidationError({'file': 'Use one worksheet only.'})
                if (book.active.max_row or 0) > MAX_ROWS + 1 or (book.active.max_column or 0) > len(FIELDS):
                    raise ValidationError({'file': 'Too many rows or columns.'})
                # Do not trust a workbook's declared dimensions to hide trailing rows.
                book.active.reset_dimensions()
                rows = []
                for cells in book.active.iter_rows(max_col=len(FIELDS) + 1):
                    if len(rows) > MAX_ROWS or cells[-1].value is not None:
                        raise ValidationError({'file': 'Too many rows or columns.'})
                    if any(c.data_type == 'f' for c in cells):
                        raise ValidationError({'file': 'Formulas are not accepted.'})
                    values = [c.value for c in cells[:-1]]
                    if not rows:
                        while values and values[-1] is None:
                            values.pop()
                    else:
                        if any(v is not None for v in values[len(rows[0]):]):
                            raise ValidationError({'file': 'Row contains unexpected extra columns.'})
                        values = values[:len(rows[0])]
                    rows.append(values)
            finally:
                book.close()
        else:
            raise ValidationError({'file': 'Use UTF-8 CSV or XLSX.'})
    except (UnicodeError, csv.Error, BadZipFile, ValueError, KeyError, OSError, ParseError, DefusedXmlException) as exc:
        raise ValidationError({'file': 'Invalid CSV/XLSX file.'}) from exc
    if not rows or len(rows) < 2 or len(rows) > MAX_ROWS + 1:
        raise ValidationError({'file': 'Provide between 1 and 500 data rows.'})
    header = rows[0]
    if not all(isinstance(x, str) for x in header) or len(set(header)) != len(header) or set(header) - set(FIELDS) or not REQUIRED <= set(header):
        raise ValidationError({'file': 'Invalid, repeated or missing column headers.'})
    records = []
    for line in rows[1:]:
        if len(line) != len(header):
            raise ValidationError({'file': 'Each row must match the header columns.'})
        record = dict(zip(header, line))
        for field in ('aliases', 'levels'):
            value = record.get(field) or ''
            if not isinstance(value, str):
                raise ValidationError({'file': 'Aliases and levels must be pipe-separated text.'})
            record[field] = [v.strip() for v in value.split('|') if v.strip()]
        for field in ('campus', 'external_code'):
            record[field] = record.get(field) or ''
        active = record.get('active', True)
        if isinstance(active, str):
            if active.casefold() not in ('true', 'false'):
                raise ValidationError({'file': 'Active must be true or false.'})
            active = active.casefold() == 'true'
        record['active'] = active
        if isinstance(record['source_checked_at'], (date, datetime)):
            record['source_checked_at'] = record['source_checked_at'].date() if isinstance(record['source_checked_at'], datetime) else record['source_checked_at']
        records.append(record)
    return records


@transaction.atomic
def import_institutions(*, actor, upload, dry_run=True):
    user = require_catalog_admin(actor, 'add', 'change')
    if type(dry_run) is not bool:
        raise ValidationError({'dry_run': 'Expected a boolean.'})
    records = read_import(upload)
    report = dict(dry_run=dry_run, valid=True, applied=False, created=0, updated=0, unchanged=0, rejected=0, errors=[])
    prepared, codes, identities = [], set(), set()
    for number, record in enumerate(records, 2):
        try:
            obj = Institution.objects.select_for_update().filter(code=record['code']).first()
            old = {field: getattr(obj, field) for field in FIELDS} if obj else None
            obj = prepare_institution(record, obj)
            if obj.code in codes or obj.identity_key in identities:
                raise ValidationError({'code': 'Duplicate code or school identity in this file.'})
            codes.add(obj.code); identities.add(obj.identity_key)
            kind = 'created' if old is None else 'unchanged' if old == {f: getattr(obj, f) for f in FIELDS} else 'updated'
            report[kind] += 1
            prepared.append((obj, kind))
        except ValidationError as exc:
            report['errors'].append({'row': number, 'fields': exc.message_dict if hasattr(exc, 'message_dict') else exc.messages})
    report.update(valid=not report['errors'], rejected=len(report['errors']))
    if not dry_run and report['valid']:
        try:
            with transaction.atomic():
                for obj, kind in prepared:
                    if kind != 'unchanged':
                        obj.save()
                        record_change(user, obj, kind == 'created')
        except IntegrityError as exc:
            raise ValidationError({'file': 'Catalog changed concurrently; preview the file again.'}) from exc
        report['applied'] = True
    return report
