#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping, Sequence


QUERY_TEMPLATE = "{type} {keyword} {location}"

PLACE_TYPES = [
    "khách sạn",
    "resort",
    "homestay",
    "villa",
    "căn hộ dịch vụ",
    "nhà nghỉ",
    "hostel",
    "nhà hàng",
    "quán ăn",
    "quán cà phê",
    "cafe",
    "coffee shop",
    "trà sữa",
    "tiệm bánh",
    "buffet",
    "quán chay",
    "quán hải sản",
    "cơm văn phòng",
    "bún phở",
    "quán nhậu",
    "quán bar",
    "karaoke",
    "spa",
    "massage",
    "salon tóc",
    "gym",
    "điểm tham quan",
    "bãi biển",
    "bảo tàng",
    "công viên",
    "khu vui chơi",
    "rạp chiếu phim",
    "di tích lịch sử",
    "chùa",
    "nhà thờ",
    "đền",
    "cầu",
    "núi",
    "thác nước",
    "hồ",
    "đảo",
    "tour du lịch",
    "công ty du lịch",
    "chợ",
    "trung tâm thương mại",
    "siêu thị",
    "cửa hàng tiện lợi",
    "cửa hàng lưu niệm",
    "cửa hàng thời trang",
    "cửa hàng đặc sản",
    "nhà sách",
    "điện máy",
    "cửa hàng điện thoại",
    "hiệu thuốc",
    "nhà thuốc",
    "bệnh viện",
    "phòng khám",
    "nha khoa",
    "ngân hàng",
    "ATM",
    "trạm xăng",
    "bãi đỗ xe",
    "gara ô tô",
    "rửa xe",
    "sửa xe máy",
    "sân bay",
    "ga tàu",
    "bến xe",
    "bến cảng",
    "trạm xe buýt",
    "thuê xe máy",
    "thuê ô tô",
    "taxi",
    "trường học",
    "đại học",
    "coworking space",
]

CATEGORY_PRESETS = {
    "Du lịch": [
        "khách sạn",
        "resort",
        "homestay",
        "villa",
        "nhà nghỉ",
        "hostel",
        "điểm tham quan",
        "bãi biển",
        "bảo tàng",
        "công viên",
        "di tích lịch sử",
        "chùa",
        "tour du lịch",
        "công ty du lịch",
    ],
    "Lưu trú": [
        "khách sạn",
        "resort",
        "homestay",
        "villa",
        "căn hộ dịch vụ",
        "nhà nghỉ",
        "hostel",
    ],
    "Ăn uống": [
        "nhà hàng",
        "quán ăn",
        "quán cà phê",
        "trà sữa",
        "tiệm bánh",
        "quán nhậu",
        "quán bar",
        "karaoke",
    ],
    "Cà phê - trà sữa": [
        "quán cà phê",
        "cafe",
        "coffee shop",
        "trà sữa",
        "tiệm bánh",
    ],
    "Giải trí": [
        "karaoke",
        "quán bar",
        "rạp chiếu phim",
        "khu vui chơi",
        "công viên",
        "gym",
    ],
    "Làm đẹp - chăm sóc": [
        "spa",
        "massage",
        "salon tóc",
        "nha khoa",
        "gym",
    ],
    "Y tế": [
        "bệnh viện",
        "phòng khám",
        "hiệu thuốc",
        "nha khoa",
        "spa",
    ],
    "Mua sắm": [
        "chợ",
        "trung tâm thương mại",
        "siêu thị",
        "cửa hàng tiện lợi",
        "cửa hàng lưu niệm",
        "cửa hàng thời trang",
        "cửa hàng đặc sản",
        "nhà sách",
    ],
    "Vận tải": [
        "sân bay",
        "ga tàu",
        "bến xe",
        "bến cảng",
        "trạm xe buýt",
        "thuê xe máy",
        "thuê ô tô",
        "taxi",
        "trạm xăng",
        "bãi đỗ xe",
    ],
    "Dịch vụ xe": [
        "trạm xăng",
        "bãi đỗ xe",
        "thuê xe máy",
        "thuê ô tô",
        "taxi",
    ],
    "Tài chính": [
        "ngân hàng",
        "ATM",
    ],
    "Giáo dục": [
        "trường học",
        "đại học",
        "nhà sách",
        "coworking space",
    ],
    "Điểm tham quan": [
        "điểm tham quan",
        "bảo tàng",
        "công viên",
        "di tích lịch sử",
        "cầu",
    ],
    "Tôn giáo": [
        "chùa",
        "nhà thờ",
        "đền",
    ],
    "Thiên nhiên": [
        "bãi biển",
        "núi",
        "thác nước",
        "hồ",
        "đảo",
        "công viên",
    ],
}


VIETNAM_LOCATIONS = [
    "Hà Nội",
    "TP. Hồ Chí Minh",
    "Hải Phòng",
    "Đà Nẵng",
    "Cần Thơ",
    "Huế",
    "Lai Châu",
    "Điện Biên",
    "Sơn La",
    "Lạng Sơn",
    "Quảng Ninh",
    "Thanh Hóa",
    "Nghệ An",
    "Hà Tĩnh",
    "Quảng Trị",
    "Quảng Ngãi",
    "Gia Lai",
    "Khánh Hòa",
    "Lâm Đồng",
    "Đắk Lắk",
    "Đồng Nai",
    "Tây Ninh",
    "Đồng Tháp",
    "An Giang",
    "Vĩnh Long",
    "Cà Mau",
    "Tuyên Quang",
    "Lào Cai",
    "Thái Nguyên",
    "Phú Thọ",
    "Bắc Ninh",
    "Hưng Yên",
    "Ninh Bình",
    "Cao Bằng",
]

NORTHERN_LOCATIONS = [
    "Hà Nội",
    "Hải Phòng",
    "Lai Châu",
    "Điện Biên",
    "Sơn La",
    "Cao Bằng",
    "Lạng Sơn",
    "Quảng Ninh",
    "Tuyên Quang",
    "Lào Cai",
    "Thái Nguyên",
    "Phú Thọ",
    "Bắc Ninh",
    "Hưng Yên",
    "Ninh Bình",
]

CENTRAL_LOCATIONS = [
    "Huế",
    "Thanh Hóa",
    "Nghệ An",
    "Hà Tĩnh",
    "Quảng Trị",
    "Đà Nẵng",
    "Quảng Ngãi",
    "Gia Lai",
    "Khánh Hòa",
    "Lâm Đồng",
    "Đắk Lắk",
]

SOUTHERN_LOCATIONS = [
    "TP. Hồ Chí Minh",
    "Cần Thơ",
    "Đồng Nai",
    "Tây Ninh",
    "Đồng Tháp",
    "An Giang",
    "Vĩnh Long",
    "Cà Mau",
]

CENTRAL_CITY_LOCATIONS = [
    "Hà Nội",
    "TP. Hồ Chí Minh",
    "Hải Phòng",
    "Đà Nẵng",
    "Cần Thơ",
    "Huế",
]

MAJOR_CITY_LOCATIONS = [
    "Hà Nội",
    "TP. Hồ Chí Minh",
    "Đà Nẵng",
    "Hải Phòng",
    "Cần Thơ",
    "Huế",
    "Nha Trang",
    "Đà Lạt",
    "Hội An",
    "Hạ Long",
    "Vũng Tàu",
    "Phú Quốc",
]

BEACH_TOURISM_LOCATIONS = [
    "Hạ Long",
    "Cát Bà",
    "Sầm Sơn",
    "Cửa Lò",
    "Đà Nẵng",
    "Hội An",
    "Quy Nhơn",
    "Tuy Hòa",
    "Nha Trang",
    "Cam Ranh",
    "Mũi Né",
    "Vũng Tàu",
    "Phú Quốc",
    "Côn Đảo",
]

NORTHWEST_LOCATIONS = ["Lai Châu", "Điện Biên", "Sơn La", "Lào Cai", "Sa Pa", "Mộc Châu"]
NORTHEAST_LOCATIONS = ["Cao Bằng", "Lạng Sơn", "Quảng Ninh", "Tuyên Quang", "Thái Nguyên", "Hà Giang"]
NORTH_CENTRAL_LOCATIONS = ["Thanh Hóa", "Nghệ An", "Hà Tĩnh", "Quảng Trị", "Huế"]
SOUTH_CENTRAL_COAST_LOCATIONS = ["Đà Nẵng", "Hội An", "Quảng Ngãi", "Quy Nhơn", "Tuy Hòa", "Khánh Hòa", "Nha Trang"]
CENTRAL_HIGHLANDS_LOCATIONS = ["Gia Lai", "Đắk Lắk", "Lâm Đồng", "Đà Lạt", "Buôn Ma Thuột"]
SOUTHEAST_LOCATIONS = ["TP. Hồ Chí Minh", "Đồng Nai", "Tây Ninh", "Vũng Tàu", "Bình Dương"]
MEKONG_DELTA_LOCATIONS = ["Cần Thơ", "Đồng Tháp", "An Giang", "Vĩnh Long", "Cà Mau", "Mỹ Tho", "Bến Tre"]

LOCATION_PRESETS = {
    "Toàn quốc": VIETNAM_LOCATIONS,
    "Miền Bắc": NORTHERN_LOCATIONS,
    "Miền Trung": CENTRAL_LOCATIONS,
    "Miền Nam": SOUTHERN_LOCATIONS,
    "Thành phố trực thuộc TW": CENTRAL_CITY_LOCATIONS,
    "Đô thị lớn": MAJOR_CITY_LOCATIONS,
    "Du lịch biển": BEACH_TOURISM_LOCATIONS,
    "Tây Bắc": NORTHWEST_LOCATIONS,
    "Đông Bắc": NORTHEAST_LOCATIONS,
    "Bắc Trung Bộ": NORTH_CENTRAL_LOCATIONS,
    "Duyên hải miền Trung": SOUTH_CENTRAL_COAST_LOCATIONS,
    "Tây Nguyên": CENTRAL_HIGHLANDS_LOCATIONS,
    "Đông Nam Bộ": SOUTHEAST_LOCATIONS,
    "Đồng bằng sông Cửu Long": MEKONG_DELTA_LOCATIONS,
}

PRESET_ALIASES = {
    "Du lich": "Du lịch",
    "An uong": "Ăn uống",
    "Y te": "Y tế",
    "Mua sam": "Mua sắm",
    "Van tai": "Vận tải",
    "Toan quoc": "Toàn quốc",
    "Mien Bac": "Miền Bắc",
    "Mien Trung": "Miền Trung",
    "Mien Nam": "Miền Nam",
    "Thanh pho truc thuoc TW": "Thành phố trực thuộc TW",
}

@dataclass
class CrawlJob:
    place_type: str = ""
    keyword: str = ""
    location: str = ""
    limit: int = 50
    output: str = ""
    query_template: str = QUERY_TEMPLATE
    status: str = "pending"
    done: int = 0
    saved: int = 0
    failed: int = 0
    exclude_keywords: list[str] = field(default_factory=list)

    @property
    def query(self) -> str:
        return build_query(self.query_template, self.place_type, self.keyword, self.location)

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["query"] = self.query
        return data


def compact_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def resolve_preset_name(preset_name: str | None, presets: Mapping[str, Sequence[str]]) -> str:
    preset = compact_spaces(preset_name or "")
    if preset in presets:
        return preset
    return PRESET_ALIASES.get(preset, preset)


def split_multi_value(value: str | Sequence[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[\n;,]+", value)
    else:
        parts = [str(item) for item in value]
    return [compact_spaces(part) for part in parts if compact_spaces(part)]


def categories_for_preset(preset_name: str | None) -> list[str]:
    preset = resolve_preset_name(preset_name, CATEGORY_PRESETS)
    return list(CATEGORY_PRESETS.get(preset, []))


def locations_for_preset(preset_name: str | None, manual_locations: str | Sequence[str] | None = None) -> list[str]:
    preset = resolve_preset_name(preset_name, LOCATION_PRESETS)
    if preset in LOCATION_PRESETS:
        return list(LOCATION_PRESETS[preset])
    return split_multi_value(manual_locations)

def build_query(template: str, place_type: str, keyword: str, location: str) -> str:
    rendered = (template or QUERY_TEMPLATE).format(
        type=place_type.strip(),
        keyword=keyword.strip(),
        location=location.strip(),
    )
    return compact_spaces(rendered)


def expand_jobs(
    place_types: str | Sequence[str],
    keywords: str | Sequence[str] | None,
    locations: str | Sequence[str],
    limit: int,
    query_template: str = QUERY_TEMPLATE,
    output_template: str = "",
    date_text: str | None = None,
) -> list[CrawlJob]:
    types = split_multi_value(place_types)
    keyword_values = split_multi_value(keywords) or [""]
    location_values = split_multi_value(locations)
    jobs: list[CrawlJob] = []

    for place_type in types:
        for keyword in keyword_values:
            for location in location_values:
                output = ""
                if output_template:
                    output = str(
                        format_output_path(
                            output_template,
                            place_type=place_type,
                            location=location,
                            date_text=date_text,
                        )
                    )
                jobs.append(
                    CrawlJob(
                        place_type=place_type,
                        keyword=keyword,
                        location=location,
                        limit=max(0, int(limit)),
                        output=output,
                        query_template=query_template,
                    )
                )
    return jobs


def import_jobs(path: Path | str) -> list[CrawlJob]:
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return _import_jobs_csv(path)
    return _import_jobs_txt(path)


def _import_jobs_txt(path: Path) -> list[CrawlJob]:
    imported: list[CrawlJob] = []
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) == 1:
            imported.append(CrawlJob(keyword=parts[0]))
        elif len(parts) == 3:
            place_type, location, limit_text = parts
            imported.append(CrawlJob(place_type=place_type, location=location, limit=_parse_limit(limit_text)))
        else:
            place_type = parts[0] if len(parts) > 0 else ""
            keyword = parts[1] if len(parts) > 1 else ""
            location = parts[2] if len(parts) > 2 else ""
            limit = _parse_limit(parts[3]) if len(parts) > 3 else 50
            output = parts[4] if len(parts) > 4 else ""
            imported.append(CrawlJob(place_type=place_type, keyword=keyword, location=location, limit=limit, output=output))
    return imported


def _import_jobs_csv(path: Path) -> list[CrawlJob]:
    imported: list[CrawlJob] = []
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            place_type = row.get("type") or row.get("place_type") or row.get("category") or ""
            imported.append(
                CrawlJob(
                    place_type=place_type.strip(),
                    keyword=(row.get("keyword") or "").strip(),
                    location=(row.get("location") or "").strip(),
                    limit=_parse_limit(row.get("limit") or "50"),
                    output=(row.get("output") or row.get("out") or "").strip(),
                    query_template=(row.get("query_template") or QUERY_TEMPLATE).strip() or QUERY_TEMPLATE,
                    exclude_keywords=split_multi_value(row.get("exclude_keywords") or ""),
                )
            )
    return imported


def _parse_limit(value: str) -> int:
    try:
        return max(0, int(str(value).strip()))
    except (TypeError, ValueError):
        return 50


def save_preset(path: Path | str, crawl_jobs: Sequence[CrawlJob], settings: Mapping[str, object] | None = None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "settings": dict(settings or {}),
        "jobs": [job.to_dict() for job in crawl_jobs],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_preset(path: Path | str) -> tuple[list[CrawlJob], dict[str, object]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    loaded_jobs = [
        CrawlJob(
            place_type=str(item.get("place_type", "")),
            keyword=str(item.get("keyword", "")),
            location=str(item.get("location", "")),
            limit=_parse_limit(str(item.get("limit", 50))),
            output=str(item.get("output", "")),
            query_template=str(item.get("query_template", QUERY_TEMPLATE)) or QUERY_TEMPLATE,
            status=str(item.get("status", "pending")),
            done=int(item.get("done", 0) or 0),
            saved=int(item.get("saved", 0) or 0),
            failed=int(item.get("failed", 0) or 0),
            exclude_keywords=split_multi_value(item.get("exclude_keywords", [])),
        )
        for item in payload.get("jobs", [])
    ]
    return loaded_jobs, dict(payload.get("settings", {}))


def dedupe_key(row: Mapping[str, object], mode: str = "destination_id") -> str:
    if mode == "name_address":
        return "|".join(
            [
                normalize_key(str(row.get("name") or row.get("normalized_name") or "")),
                normalize_key(str(row.get("address") or "")),
            ]
        )
    if mode == "coordinates":
        lat = str(row.get("latitude") or "").strip()
        lng = str(row.get("longitude") or "").strip()
        return f"{lat},{lng}" if lat and lng else ""
    return str(row.get("destination_id") or "").strip()


def dedupe_rows(rows: Iterable[Mapping[str, object]], mode: str = "destination_id", merge: bool = True) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    seen: dict[str, dict[str, object]] = {}
    for raw_row in rows:
        row = dict(raw_row)
        key = dedupe_key(row, mode)
        if not key:
            result.append(row)
            continue
        existing = seen.get(key)
        if existing is None:
            seen[key] = row
            result.append(row)
        elif merge:
            for field_name, value in row.items():
                if is_missing(existing.get(field_name)) and not is_missing(value):
                    existing[field_name] = value
    return result


def normalize_key(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^\w\s]+", " ", value, flags=re.UNICODE)
    return compact_spaces(value)


def is_missing(value: object) -> bool:
    return value is None or str(value).strip() == ""


def build_missing_field_report(rows: Sequence[Mapping[str, object]], fields: Sequence[str]) -> dict[str, object]:
    missing = {field_name: 0 for field_name in fields}
    for row in rows:
        for field_name in fields:
            if is_missing(row.get(field_name)):
                missing[field_name] += 1
    return {
        "total_rows": len(rows),
        "missing": missing,
    }


def format_output_path(
    template: str,
    *,
    place_type: str,
    location: str,
    date_text: str | None = None,
) -> Path:
    date_value = date_text or datetime.now().strftime("%Y%m%d")
    rendered = template.format(
        type=slugify_filename(place_type),
        location=slugify_filename(location),
        date=date_value,
    )
    return Path(rendered)


def slugify_filename(value: str) -> str:
    value = compact_spaces(value).replace(" ", "_")
    value = re.sub(r'[<>:"/\\|?*]+', "_", value)
    return value.strip("._") or "all"


def save_checkpoint(
    path: Path | str,
    *,
    completed_ids: Iterable[str],
    failed_rows: Sequence[Mapping[str, object]],
    extra: Mapping[str, object] | None = None,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "completed_ids": sorted(set(completed_ids)),
        "failed_rows": [dict(row) for row in failed_rows],
        "updated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
    }
    if extra:
        payload.update(dict(extra))
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_checkpoint(path: Path | str) -> dict[str, object]:
    path = Path(path)
    if not path.exists():
        return {"completed_ids": [], "failed_rows": []}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    payload.setdefault("completed_ids", [])
    payload.setdefault("failed_rows", [])
    return payload


def extract_address_parts(address: str) -> dict[str, str]:
    parts = [compact_spaces(part) for part in address.split(",") if compact_spaces(part)]
    ward = ""
    district = ""
    province = ""
    ward_prefixes = ("phuong", "xa", "thi tran", "ward")
    district_prefixes = ("quan", "huyen", "thi xa", "district")
    province_prefixes = ("tp", "thanh pho", "tinh", "city", "province")

    for part in parts:
        lowered = normalize_key(part)
        if not ward and lowered.startswith(ward_prefixes):
            ward = part
        if not district and lowered.startswith(district_prefixes):
            district = part
        if lowered.startswith(province_prefixes):
            province = part

    if not province and parts:
        province = parts[-1]
    if not district and len(parts) >= 2:
        district = parts[-2]

    return {
        "province": province,
        "district": district,
        "ward": ward,
    }


def should_exclude_row(row: Mapping[str, object], exclude_keywords: Sequence[str]) -> bool:
    if not exclude_keywords:
        return False
    haystack = " ".join(str(value) for value in row.values()).lower()
    return any(keyword.lower() in haystack for keyword in exclude_keywords if keyword)
