"""Local context rules for structured identity and Presidio span resolution."""

from functools import lru_cache
import hashlib
from pathlib import Path
import re
import unicodedata


def field_name(value):
    return re.sub(r"[\s_-]+", "", unicodedata.normalize("NFKC", value)).casefold()


CONTACT_FIELDS = frozenset(('contact', 'recipient', 'consignee', '联系人', '收件人', '收件信息', '联系信息'))
ADDRESS_FIELDS = frozenset(('address', 'shippingaddress', 'mailingaddress', 'homeaddress', '住址', '地址', '收件地址', '邮寄地址'))
ADDRESS_PARTS = frozenset((
    'province', 'city', 'district', 'county', 'street', 'road', 'building', 'unit', 'room',
    'line1', 'line2', 'streetnumber', 'block', 'apartment', 'postcode',
    '省', '市', '区', '县', '街道', '小区', '楼栋', '单元', '门牌', '房号', '邮编',
))
CONTACT_ANCHORS = frozenset(('phone', 'phonenumber', 'mobile', 'email', '手机', '电话', '邮箱', '收件地址'))
SOCIAL_FIELDS = frozenset(('qq', 'qqid', 'qqnumber', 'qq号', '微信', '微信号', '微信id', 'wechat', 'wechatid', 'wxid', 'weixin', 'weixinid'))
_CONTACT_NAMES = frozenset(('name', 'displayname', 'nickname', '姓名', '名称', '昵称'))


def known_identity_record(field, value):
    """Only preserve structure when all members of an explicit record are understood."""
    fields = ADDRESS_PARTS if field in ADDRESS_FIELDS else (
        _CONTACT_NAMES | CONTACT_ANCHORS | SOCIAL_FIELDS | ADDRESS_FIELDS
    )
    rows = value if isinstance(value, list) else [value]
    if not rows or any(not isinstance(row, dict) or not row for row in rows):
        return False
    for row in rows:
        for key, child in row.items():
            name = field_name(key)
            if name not in fields:
                return False
            if isinstance(child, (dict, list)) and not (
                name in ADDRESS_FIELDS and isinstance(child, dict) and known_identity_record(name, child)
            ):
                return False
    return True


def sibling_context(item, parent):
    """Interpret only the current record's role and discriminators."""
    contact = parent in CONTACT_FIELDS or any(
        field_name(key) in CONTACT_ANCHORS and type(value) in (int, str) and bool(value)
        for key, value in item.items()
    )
    social = any(
        field_name(key) in ('platform', 'channel', 'service', 'type', '平台', '渠道', '类型')
        and isinstance(value, str) and field_name(value) in SOCIAL_FIELDS
        for key, value in item.items()
    )
    return contact, social, parent in ADDRESS_FIELDS


def contextual_identity(field, context):
    contact, social, address = context
    if field in SOCIAL_FIELDS or (social and field in ('id', 'value', 'handle', 'account', 'username', '账号', '号码')):
        return 'PRIVATE_ID'
    if address and field in ADDRESS_PARTS:
        return 'LOCATION'
    if field in ADDRESS_FIELDS:
        return 'LOCATION'
    if field in CONTACT_FIELDS or (contact and field in _CONTACT_NAMES):
        return 'PERSON'
    return None


# A complete detailed address must have a street/building component and a
# numbered endpoint, or a chain of numbered details after a known region.
_HAN = r'\u3400-\u9fff'
_ROAD = r'(?:街道|大道|大街|胡同|社区|小区|花园|公寓|大厦|园区|路|街|巷|弄|村|镇|乡)'
_NUMBER = r'(?:[A-Za-z]?[0-9]{1,6}|[一二三四五六七八九十零〇两]{1,6}|[A-Z])'
_PART = rf'{_NUMBER}(?:号楼|号院|单元|栋|幢|号|座|楼|层|室|户)'
_JOIN = r'[ \t-]{0,3}'
_DETAIL = re.compile(rf'{_PART}(?:{_JOIN}{_PART}){{0,9}}')
_WITH_ROAD = re.compile(rf'[{_HAN}A-Za-z0-9·]{{1,40}}?{_ROAD}{_JOIN}{_DETAIL.pattern}')
_CUE = re.compile(r'(?:派送到|配送(?:到|至)|邮寄至|寄到|送到|寄往|寄至|送至|住在|收货地址|收件地址|联系地址|邮寄地址|详细地址|家庭地址|地址|住址)[ \t]*(?:[:：]|是|为)?[ \t]*')
_SEPARATOR = re.compile(r'[ \t,，、]{0,3}')
_ROOM_COMPONENT = rf'{_NUMBER}(?:号楼|号院|单元|栋|幢|座|楼|层|室|户|房|铺|梯|门)'
_NUMBERED_UNIT = rf'(?:{_ROOM_COMPONENT}|{_NUMBER}号)'
_EXTENDED_DETAIL = re.compile(rf'{_NUMBERED_UNIT}(?:{_JOIN}附?{_NUMBERED_UNIT}|[ \t]{{0,2}}[,，、][ \t]{{0,2}}附?{_ROOM_COMPONENT}){{0,9}}')
_ADDRESS_END = r'(?=[ \t]*(?:[,，;；。!?！？\n”"）)]|$))'
_ROOM_NUMBER = re.compile(rf'{_JOIN}[A-Za-z]?[0-9]{{2,5}}{_ADDRESS_END}')
_ROOM_AFTER = re.compile(r'(?:号楼|单元|栋|幢|座|楼|层|梯|门)$')
_COMPACT_DETAIL = re.compile(rf'[0-9]{{1,4}}-[0-9]{{1,3}}-[0-9]{{2,5}}{_ADDRESS_END}')
_PLACE = re.compile(rf'[{_HAN}A-Za-z0-9·]{{1,40}}?{_ROAD}')
_RESIDENTIAL_PLACE = re.compile(rf'[{_HAN}A-Za-z0-9·]{{1,24}}?(?:小区|花园|公寓|家园|新村|苑|园|里|邸)')
_RESIDENTIAL_SECTION = re.compile(r'[东西南北中](?:区|院|门)')
_AREA_LEVELS = (('自治区', '省'), ('自治州', '地区', '市', '盟'), ('自治县', '区', '县', '旗'), ('街道', '镇', '乡'))


@lru_cache(maxsize=1)
def _administrative_names():
    path = Path(__file__).resolve().parents[2] / 'config/privacy-cn-administrative-names.txt'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != '59fc766291587e87bedef755d01436f5a69a88acdcd8b1b8fda4990cbcc8a4d3':
        raise ValueError('privacy_address_dictionary_changed')
    names = sorted(raw.decode('utf-8').splitlines(), key=lambda name: (-len(name), name))
    return re.compile('|'.join(map(re.escape, names)))


def _numbered_end(text, start):
    detail = _EXTENDED_DETAIL.match(text, start)
    if detail is None:
        return None
    if _ROOM_AFTER.search(detail.group()):
        section = _RESIDENTIAL_SECTION.match(text, detail.end())
        if section:
            nested = _EXTENDED_DETAIL.match(text, _SEPARATOR.match(text, section.end()).end())
            if nested:
                return nested.end()
    room = _ROOM_NUMBER.match(text, detail.end()) if _ROOM_AFTER.search(detail.group()) else None
    return room.end() if room else detail.end()


def _continued_address_end(text, start):
    cursor = _SEPARATOR.match(text, start).end()
    # Across punctuation, first require a road or residence component. A bare
    # number after a region and comma could be the next sentence's identifier.
    if not any(char in ',，、' for char in text[start:cursor]):
        direct = _numbered_end(text, cursor)
        if direct is not None:
            return direct
    for _ in range(4):
        place = _PLACE.match(text, cursor) or _RESIDENTIAL_PLACE.match(text, cursor)
        if place is None:
            return None
        cursor = _SEPARATOR.match(text, place.end()).end()
        detail_end = _numbered_end(text, cursor)
        if detail_end is not None:
            return detail_end
        compact = _COMPACT_DETAIL.match(text, cursor)
        if compact:
            return compact.end()
    return None


def _area_level(name):
    return next((i for i, suffixes in enumerate(_AREA_LEVELS) if name.endswith(suffixes)), -1)


def _residential_tail_end(text, end):
    cursor = _SEPARATOR.match(text, end).end()
    if not any(char in ',，、' for char in text[end:cursor]):
        return end
    residence = _RESIDENTIAL_PLACE.match(text, cursor)
    if residence is None:
        return end
    cursor = _SEPARATOR.match(text, residence.end()).end()
    section = _RESIDENTIAL_SECTION.match(text, cursor)
    if section:
        cursor = _SEPARATOR.match(text, section.end()).end()
    detail = _numbered_end(text, cursor)
    if detail is not None:
        return detail
    compact = _COMPACT_DETAIL.match(text, cursor)
    return compact.end() if compact else end


def address_spans(text):
    """Return original-view spans anchored by a region or an address cue."""
    if not (_EXTENDED_DETAIL.search(text) or _COMPACT_DETAIL.search(text)):
        return []
    areas = _administrative_names()
    spans = []
    for anchor in areas.finditer(text):
        if spans and anchor.start() < spans[-1][1]:
            continue
        start, end = anchor.span()
        area = anchor.group()
        for _ in range(3):
            continuation = _SEPARATOR.match(text, end).end()
            next_area = areas.match(text, continuation)
            if not next_area:
                break
            if any(char in ',，、' for char in text[end:continuation]):
                if not 0 <= _area_level(area) < _area_level(next_area.group()):
                    break
            area = next_area.group()
            end = next_area.end()
        tail = _WITH_ROAD.match(text, end) or _DETAIL.match(text, end)
        end = max(tail.end() if tail else 0, _continued_address_end(text, end) or 0)
        if end:
            spans.append((start, _residential_tail_end(text, end)))
    for cue in _CUE.finditer(text):
        start = cue.end()
        if any(left <= start < right for left, right in spans):
            continue
        tail = _WITH_ROAD.match(text, start)
        end = max(tail.end() if tail else 0, _continued_address_end(text, start) or 0)
        if end:
            spans.append((start, _residential_tail_end(text, end)))
    return spans


ADDRESS_RECOGNIZER = 'GeneLoopDetailedAddress'
_PRECISE = frozenset(('EMAIL_ADDRESS', 'PHONE_NUMBER', 'IDENTITY_NUMBER', 'CREDIT_CARD',
                      'FINANCIAL_ACCOUNT', 'IP_ADDRESS', 'PRIVATE_ID', 'CREDENTIAL'))


def resolve_overlaps(findings):
    """Keep the union of detected characters and choose labels by evidence type."""
    from presidio_analyzer import RecognizerResult

    def rank(finding):
        name = (finding.recognition_metadata or {}).get('recognizer_name')
        # Format/label recognizers identify a more specific category than NER.
        if name == ADDRESS_RECOGNIZER:
            tier = 4
        elif finding.entity_type in _PRECISE:
            tier = 3 if name == f'GeneLoopPolicy-{finding.entity_type}' else 2
        else:
            tier = 1
        return tier, finding.end - finding.start, -finding.start, finding.entity_type

    ordered = sorted(findings, key=lambda item: (item.start, item.end))
    result = []
    cluster = []
    end = -1

    def emit():
        winner = max(cluster, key=rank)
        if len(cluster) == 1:
            return winner
        return RecognizerResult(winner.entity_type, cluster[0].start, end, winner.score)

    for finding in ordered:
        if cluster and finding.start >= end:
            result.append(emit())
            cluster = []
        if not cluster:
            end = finding.end
        else:
            end = max(end, finding.end)
        cluster.append(finding)
    if cluster:
        result.append(emit())
    return result
