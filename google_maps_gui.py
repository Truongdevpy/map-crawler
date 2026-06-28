#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import io
import json
import queue
import re
import threading
import webbrowser
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import quote_plus
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import crawl_google_maps_selenium as crawler
import google_maps_jobs as jobs


APP_TITLE = "Google Maps Destination Crawler"
SETTINGS_PATH = Path(".google_maps_gui_settings.json")
PLACE_TYPE_LABEL = "Loại cần lấy (gõ tay hoặc chọn)"
PLACE_TYPES = jobs.PLACE_TYPES
CATEGORY_PRESETS = jobs.CATEGORY_PRESETS
LOCATION_PRESETS = jobs.LOCATION_PRESETS

EXPORT_MODE_LABELS = {
    crawler.EXPORT_MODE_END: "Ghi file khi cào xong",
    crawler.EXPORT_MODE_LIVE: "Ghi từng dòng trong lúc cào",
}

EXPORT_FORMAT_LABELS = {
    crawler.EXPORT_FORMAT_CSV: "CSV",
    crawler.EXPORT_FORMAT_JSONL: "JSONL",
    crawler.EXPORT_FORMAT_SQLITE: "SQLite",
    crawler.EXPORT_FORMAT_XLSX: "Excel .xlsx",
}

WRITE_MODE_LABELS = {
    crawler.WRITE_MODE_OVERWRITE: "Ghi đè",
    crawler.WRITE_MODE_APPEND: "Ghi tiếp / gộp vào file cũ",
}

SPLIT_LABELS = {
    crawler.SPLIT_NONE: "Không tách file",
    crawler.SPLIT_CATEGORY: "Tách theo danh mục",
    crawler.SPLIT_LOCATION: "Tách theo vị trí",
}

DEDUPE_LABELS = {
    "destination_id": "Theo ID địa điểm",
    "name_address": "Theo tên + địa chỉ",
    "coordinates": "Theo tọa độ",
}

JOB_STATUS_LABELS = {
    "pending": "Chờ chạy",
    "running": "Đang chạy",
    "done": "Xong",
    "error": "Lỗi",
}

FIELD_LABELS = {
    "name": "Tên",
    "normalized_name": "Tên chuẩn hóa",
    "category": "Danh mục",
    "destination_id": "ID điểm đến",
    "address": "Địa chỉ",
    "province": "Tỉnh/Thành",
    "district": "Quận/Huyện",
    "ward": "Phường/Xã",
    "description": "Mô tả",
    "price_min": "Giá thấp nhất",
    "price_max": "Giá cao nhất",
    "rating": "Đánh giá",
    "latitude": "Vĩ độ",
    "longitude": "Kinh độ",
    "image_url": "Ảnh",
    "phone": "Số điện thoại",
    "website": "Website",
    "open_hours": "Giờ mở cửa",
    "estimated_duration_minutes": "Thời lượng ước tính",
    "suitable_time": "Thời gian phù hợp",
    "tags": "Tags",
    "source_count": "Số nguồn",
    "confidence_score": "Độ tin cậy",
    "created_at": "Ngày tạo",
    "updated_at": "Ngày cập nhật",
}


FIELD_LABELS.update({
    "price_text": "Giá raw",
    "review_count": "Số lượt đánh giá",
    "maps_url": "Link Google Maps",
})


PREVIEW_CONTEXT_COPY_FIELDS = [
    "name",
    "category",
    "address",
    "district",
    "phone",
    "website",
    "maps_url",
    "rating",
    "review_count",
    "price_text",
    "latitude",
    "longitude",
    "image_url",
]

JOB_CONTEXT_FIELDS = ["status", "query", "limit", "output", "saved", "failed"]

def label_for_value(labels: dict[str, str], value: str) -> str:
    return labels.get(value, value)

def value_from_label(labels: dict[str, str], value: str) -> str:
    reverse = {label: key for key, label in labels.items()}
    return reverse.get(value, value)

def export_mode_value(value: str) -> str:
    return value_from_label(EXPORT_MODE_LABELS, value)

def export_format_value(value: str) -> str:
    return value_from_label(EXPORT_FORMAT_LABELS, value)

def write_mode_value(value: str) -> str:
    return value_from_label(WRITE_MODE_LABELS, value)

def split_mode_value(value: str) -> str:
    return value_from_label(SPLIT_LABELS, value)

def dedupe_mode_value(value: str) -> str:
    return value_from_label(DEDUPE_LABELS, value)

def job_status_label(status: str) -> str:
    return JOB_STATUS_LABELS.get(status, status)

def build_query(place_type: str, keyword: str, location: str, query_template: str = jobs.QUERY_TEMPLATE) -> str:
    return jobs.build_query(query_template, place_type, keyword, location)


def normalize_worker_count(value: str) -> int:
    try:
        worker_count = int(value)
    except (TypeError, ValueError):
        return 1
    return crawler.normalize_max_workers(worker_count)


def default_output_path(now: datetime | None = None, export_format: str = crawler.EXPORT_FORMAT_CSV) -> Path:
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    suffix = {
        crawler.EXPORT_FORMAT_CSV: ".csv",
        crawler.EXPORT_FORMAT_JSONL: ".jsonl",
        crawler.EXPORT_FORMAT_SQLITE: ".sqlite",
        crawler.EXPORT_FORMAT_XLSX: ".xlsx",
    }.get(export_format, ".csv")
    return Path(f"data/google_maps_{timestamp}{suffix}")


def read_settings_file(path: Path | str = SETTINGS_PATH) -> dict[str, Any]:
    settings_path = Path(path)
    if not settings_path.exists():
        return {}
    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}

def write_settings_file(path: Path | str, payload: Mapping[str, Any]) -> None:
    settings_path = Path(path)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8")

def selected_fields_from_values(values: dict[str, bool]) -> list[str]:
    selected = [field for field in crawler.SCHEMA_FIELDS if values.get(field)]
    return selected or list(crawler.SCHEMA_FIELDS)


def parse_positive_int(value: str, label: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise ValueError(f"{label} phải là số nguyên.") from exc
    if number < 1:
        raise ValueError(f"{label} phải lớn hơn 0.")
    return number


def parse_limit_for_mode(value: str, label: str, all_results: bool = False) -> int:
    if all_results:
        return crawler.ALL_RESULTS_LIMIT
    return parse_positive_int(value, label)

def format_job_limit(limit: int) -> str:
    return crawler.format_limit_label(limit)

def parse_non_negative_float(value: str, label: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise ValueError(f"{label} phải là số.") from exc
    if number < 0:
        raise ValueError(f"{label} không được âm.")
    return number


def build_jobs_from_inputs(
    place_types: str,
    keywords: str,
    locations: str,
    limit: int,
    query_template: str,
    output_template: str = "",
    export_format: str = crawler.EXPORT_FORMAT_CSV,
    location_preset: str = "",
    all_results: bool = False,
) -> list[jobs.CrawlJob]:
    template = output_template.strip()
    if template and "{date}" not in template:
        template = str(Path(template))
    location_values = jobs.locations_for_preset(location_preset, locations)
    effective_limit = crawler.ALL_RESULTS_LIMIT if all_results else limit
    crawl_jobs = jobs.expand_jobs(
        place_types=place_types,
        keywords=keywords,
        locations=location_values,
        limit=effective_limit,
        query_template=query_template or jobs.QUERY_TEMPLATE,
        output_template=template,
    )
    if template:
        return crawl_jobs

    suffix = {
        crawler.EXPORT_FORMAT_CSV: ".csv",
        crawler.EXPORT_FORMAT_JSONL: ".jsonl",
        crawler.EXPORT_FORMAT_SQLITE: ".sqlite",
        crawler.EXPORT_FORMAT_XLSX: ".xlsx",
    }.get(export_format, ".csv")
    for job in crawl_jobs:
        job.output = str(jobs.format_output_path(f"data/{{type}}_{{location}}_{{date}}{suffix}", place_type=job.place_type, location=job.location))
    return crawl_jobs


def sort_places(places: Iterable[crawler.Place], field: str, descending: bool = False) -> list[crawler.Place]:
    def key(place: crawler.Place) -> tuple[int, Any]:
        value = getattr(place, field, "")
        if value is None or value == "":
            return (1, "")
        if isinstance(value, (int, float)):
            return (0, value)
        try:
            return (0, float(value))
        except (TypeError, ValueError):
            return (0, str(value).lower())

    return sorted(places, key=key, reverse=descending)


def filter_places(
    places: Iterable[crawler.Place],
    rating_min: str = "",
    price_max: str = "",
    district: str = "",
) -> list[crawler.Place]:
    rating_value = float(rating_min) if rating_min.strip() else None
    price_value = int(price_max) if price_max.strip() else None
    district_value = district.strip().lower()
    filtered: list[crawler.Place] = []
    for place in places:
        if rating_value is not None and (place.rating is None or place.rating < rating_value):
            continue
        if price_value is not None and place.price_min is not None and place.price_min > price_value:
            continue
        if district_value and district_value not in (place.district or "").lower():
            continue
        filtered.append(place)
    return filtered


def should_use_multi_job_config(
    category_preset: str = "",
    location_preset: str = "",
    multi_types: str = "",
    multi_locations: str = "",
) -> bool:
    if jobs.categories_for_preset(category_preset):
        return True
    if jobs.resolve_preset_name(location_preset, LOCATION_PRESETS) in LOCATION_PRESETS:
        return True
    return len(jobs.split_multi_value(multi_types)) > 1 or len(jobs.split_multi_value(multi_locations)) > 1

def place_types_for_start(place_type: str, multi_types: str, category_preset: str = "") -> str:
    preset_types = jobs.categories_for_preset(category_preset)
    if preset_types:
        return ", ".join(preset_types)
    return multi_types.strip() or place_type.strip()

def locations_for_start(location: str, multi_locations: str) -> str:
    return multi_locations.strip() or location.strip()

def build_implicit_start_jobs_from_inputs(
    place_type: str,
    keyword: str,
    location: str,
    multi_types: str,
    multi_locations: str,
    limit: int,
    query_template: str,
    output: str = "",
    output_template: str = "",
    export_format: str = crawler.EXPORT_FORMAT_CSV,
    category_preset: str = "",
    location_preset: str = "",
    all_results: bool = False,
    limit_override: int | None = None,
) -> list[jobs.CrawlJob]:
    effective_limit = limit if limit_override is None else limit_override
    if not should_use_multi_job_config(category_preset, location_preset, multi_types, multi_locations):
        return [
            jobs.CrawlJob(
                place_type=place_type.strip(),
                keyword=keyword.strip(),
                location=location.strip(),
                limit=effective_limit,
                output=output.strip(),
                query_template=query_template.strip() or jobs.QUERY_TEMPLATE,
            )
        ]

    return build_jobs_from_inputs(
        place_types=place_types_for_start(place_type, multi_types, category_preset),
        keywords=keyword,
        locations=locations_for_start(location, multi_locations),
        limit=effective_limit,
        query_template=query_template,
        output_template=output_template,
        export_format=export_format,
        location_preset=location_preset,
        all_results=all_results and limit_override is None,
    )

def format_query_preview_for_inputs(
    place_type: str,
    keyword: str,
    location: str,
    multi_types: str,
    multi_locations: str,
    limit: int,
    query_template: str,
    output: str = "",
    output_template: str = "",
    export_format: str = crawler.EXPORT_FORMAT_CSV,
    category_preset: str = "",
    location_preset: str = "",
    all_results: bool = False,
) -> str:
    if should_use_multi_job_config(category_preset, location_preset, multi_types, multi_locations):
        crawl_jobs = build_implicit_start_jobs_from_inputs(
            place_type=place_type,
            keyword=keyword,
            location=location,
            multi_types=multi_types,
            multi_locations=multi_locations,
            limit=limit,
            query_template=query_template,
            output=output,
            output_template=output_template,
            export_format=export_format,
            category_preset=category_preset,
            location_preset=location_preset,
            all_results=all_results,
        )
        sample = " | ".join(job.query for job in crawl_jobs[:3])
        more = "" if len(crawl_jobs) <= 3 else f" | ... (+{len(crawl_jobs) - 3} job)"
        return f"Sẽ tạo {len(crawl_jobs)} job. Ví dụ: {sample}{more}"

    query = build_query(place_type, keyword, location, query_template)
    return query or "Nhập ít nhất một loại, từ khóa hoặc vị trí."

def place_to_context_row(place: crawler.Place, fields: Iterable[str] | None = None) -> dict[str, Any]:
    row = asdict(place)
    selected_fields = list(fields or row.keys())
    return {field: row.get(field, "") for field in selected_fields}

def format_rows_for_clipboard(rows: Iterable[dict[str, Any]], fields: Iterable[str], export_format: str = "tsv") -> str:
    row_list = list(rows)
    field_list = list(fields)
    if export_format == "json":
        return json.dumps(
            [{field: row.get(field, "") for field in field_list} for row in row_list],
            ensure_ascii=False,
            indent=2,
        )

    buffer = io.StringIO(newline="")
    delimiter = "," if export_format == "csv" else "\t"
    writer = csv.writer(buffer, delimiter=delimiter)
    writer.writerow(field_list)
    for row in row_list:
        writer.writerow(["" if row.get(field) is None else row.get(field, "") for field in field_list])
    return buffer.getvalue()

def format_place_contact_card(row: dict[str, Any]) -> str:
    lines: list[str] = []
    primary = str(row.get("name") or "").strip()
    if primary:
        lines.append(primary)
    for field in ("category", "rating", "review_count", "price_text", "address", "phone", "website", "maps_url"):
        value = row.get(field)
        if value not in (None, ""):
            label = FIELD_LABELS.get(field, field)
            lines.append(f"{label}: {value}")
    latitude = row.get("latitude")
    longitude = row.get("longitude")
    if latitude not in (None, "") and longitude not in (None, ""):
        lines.append(f"Tọa độ: {latitude},{longitude}")
    return "\n".join(lines)

def maps_open_url(row: dict[str, Any]) -> str:
    maps_url = str(row.get("maps_url") or "").strip()
    if maps_url:
        return maps_url

    query = " ".join(
        str(row.get(field) or "").strip()
        for field in ("name", "address", "district", "province")
        if str(row.get(field) or "").strip()
    )
    return f"https://www.google.com/maps/search/{quote_plus(query)}" if query else "https://www.google.com/maps"

def open_url_for_field(row: dict[str, Any], field: str) -> str:
    if field == "maps_url":
        return maps_open_url(row)
    value = str(row.get(field) or "").strip()
    if not value:
        return ""
    if field == "website":
        return crawler.extract_url_from_text(value)
    if field == "image_url" and value.startswith(("http://", "https://")):
        return value
    if value.startswith(("http://", "https://")):
        return value
    return ""

def clone_job_for_context(job: jobs.CrawlJob, limit_override: int | None = None) -> jobs.CrawlJob:
    return jobs.CrawlJob(
        place_type=job.place_type,
        keyword=job.keyword,
        location=job.location,
        limit=job.limit if limit_override is None else limit_override,
        output=job.output,
        query_template=job.query_template,
        status="pending",
        done=0,
        saved=0,
        failed=0,
        exclude_keywords=list(job.exclude_keywords),
    )

def job_to_context_row(job: jobs.CrawlJob) -> dict[str, Any]:
    return {
        "status": job_status_label(job.status),
        "query": job.query,
        "limit": format_job_limit(job.limit),
        "output": job.output,
        "saved": job.saved,
        "failed": job.failed,
    }

def format_jobs_for_clipboard(crawl_jobs: Iterable[jobs.CrawlJob], export_format: str = "tsv") -> str:
    rows = [job_to_context_row(job) for job in crawl_jobs]
    return format_rows_for_clipboard(rows, JOB_CONTEXT_FIELDS, export_format)

def field_from_tree_column(fields: list[str], column_id: str) -> str:
    if not column_id.startswith("#"):
        return ""
    try:
        index = int(column_id[1:]) - 1
    except ValueError:
        return ""
    return fields[index] if 0 <= index < len(fields) else ""


class GoogleMapsCrawlerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1280x820")
        self.root.minsize(1080, 720)

        self.log_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.stop_event: threading.Event | None = None
        self.pause_event = threading.Event()
        self.job_queue: list[jobs.CrawlJob] = []
        self.preview_places: list[crawler.Place] = []
        self.preview_fields: list[str] = list(crawler.SCHEMA_FIELDS)

        self.place_type_var = tk.StringVar(value=PLACE_TYPES[0])
        self.keyword_var = tk.StringVar()
        self.location_var = tk.StringVar(value="Đà Nẵng")
        self.multi_types_var = tk.StringVar(value=PLACE_TYPES[0])
        self.multi_locations_var = tk.StringVar(value="Đà Nẵng")
        self.query_template_var = tk.StringVar(value=jobs.QUERY_TEMPLATE)
        self.category_preset_var = tk.StringVar(value="")
        self.location_preset_var = tk.StringVar(value="")
        self.exclude_keywords_var = tk.StringVar(value="đã đóng cửa, tạm ngưng")
        self.limit_var = tk.StringVar(value="50")
        self.all_results_var = tk.BooleanVar(value=False)
        self.delay_var = tk.StringVar(value="1.5")
        self.scroll_pause_var = tk.StringVar(value="1.2")
        self.timeout_var = tk.StringVar(value="20")
        self.worker_count_var = tk.StringVar(value="1")
        self.output_var = tk.StringVar(value=str(default_output_path()))
        self.output_template_var = tk.StringVar(value="data/{type}_{location}_{date}.csv")
        self.export_mode_var = tk.StringVar(value=label_for_value(EXPORT_MODE_LABELS, crawler.EXPORT_MODE_END))
        self.export_format_var = tk.StringVar(value=label_for_value(EXPORT_FORMAT_LABELS, crawler.EXPORT_FORMAT_CSV))
        self.write_mode_var = tk.StringVar(value=label_for_value(WRITE_MODE_LABELS, crawler.WRITE_MODE_OVERWRITE))
        self.split_by_var = tk.StringVar(value=label_for_value(SPLIT_LABELS, crawler.SPLIT_NONE))
        self.dedupe_mode_var = tk.StringVar(value=label_for_value(DEDUPE_LABELS, "destination_id"))
        self.resume_var = tk.BooleanVar(value=True)
        self.headless_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Sẵn sàng")
        self.settings_path_var = tk.StringVar(value=str(SETTINGS_PATH.resolve()))
        self.settings_status_var = tk.StringVar(value="Tự lưu khi đóng app")
        self.progress_text_var = tk.StringVar(value="0/0")
        self.progress_value_var = tk.DoubleVar(value=0)
        self.rating_filter_var = tk.StringVar()
        self.price_filter_var = tk.StringVar()
        self.district_filter_var = tk.StringVar()
        self.sort_field_var = tk.StringVar(value="rating")
        self.sort_desc_var = tk.BooleanVar(value=True)
        self.field_vars = {field: tk.BooleanVar(value=True) for field in crawler.SCHEMA_FIELDS}

        self.start_button: ttk.Button
        self.pause_button: ttk.Button
        self.resume_button: ttk.Button
        self.stop_button: ttk.Button
        self.limit_spinbox: ttk.Spinbox
        self.type_box: ttk.Combobox
        self.query_preview: ttk.Label
        self.log_text: tk.Text
        self.preview_tree: ttk.Treeview
        self.job_tree: ttk.Treeview

        self._load_settings()
        self._build_ui()
        self._refresh_limit_state()
        self._refresh_query_preview()
        self._refresh_job_tree()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(150, self._drain_log_queue)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        outer = ttk.Frame(self.root, padding=12)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(outer)
        notebook.grid(row=0, column=0, sticky="nsew")

        job_tab = ttk.Frame(notebook, padding=12)
        config_tab = ttk.Frame(notebook, padding=12)
        fields_tab = ttk.Frame(notebook, padding=12)
        preview_tab = ttk.Frame(notebook, padding=12)
        log_tab = ttk.Frame(notebook, padding=12)

        notebook.add(job_tab, text="Hàng đợi job")
        notebook.add(config_tab, text="Cấu hình")
        notebook.add(fields_tab, text="Trường dữ liệu")
        notebook.add(preview_tab, text="Xem trước")
        notebook.add(log_tab, text="Nhật ký")

        self._build_job_tab(job_tab)
        self._build_config_tab(config_tab)
        self._build_fields_tab(fields_tab)
        self._build_preview_tab(preview_tab)
        self._build_log_tab(log_tab)
        self._build_footer(outer)

    def _build_job_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        actions = ttk.Frame(parent)
        actions.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        buttons = [
            ("Thêm job", self._add_single_job),
            ("Tạo từ multi query", self._generate_jobs),
            ("Nhập TXT/CSV", self._import_jobs),
            ("Lưu preset", self._save_preset),
            ("Tải preset", self._load_preset),
            ("Chạy lại job lỗi", self._retry_failed_jobs),
            ("Xóa job", self._remove_selected_jobs),
            ("Xóa tất cả", self._clear_jobs),
        ]
        for index, (text, command) in enumerate(buttons):
            ttk.Button(actions, text=text, command=command).grid(row=0, column=index, padx=(0, 8))

        columns = ("status", "query", "limit", "output", "saved", "failed")
        self.job_tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="extended")
        self.job_tree.grid(row=1, column=0, sticky="nsew")
        widths = {"status": 110, "query": 360, "limit": 70, "output": 360, "saved": 80, "failed": 80}
        for column in columns:
            self.job_tree.heading(column, text=column)
            self.job_tree.column(column, width=widths[column], minwidth=60, stretch=column in {"query", "output"})
        y_scroll = ttk.Scrollbar(parent, orient="vertical", command=self.job_tree.yview)
        y_scroll.grid(row=1, column=1, sticky="ns")
        self.job_tree.configure(yscrollcommand=y_scroll.set)
        self.job_tree.bind("<Button-3>", self._show_job_context_menu)
        self.job_tree.bind("<Button-2>", self._show_job_context_menu)

    def _build_config_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(3, weight=1)

        self._add_label(parent, PLACE_TYPE_LABEL, 0, 0)
        self.type_box = ttk.Combobox(parent, textvariable=self.place_type_var, values=PLACE_TYPES, state="normal")
        self.type_box.grid(row=0, column=1, sticky="ew", padx=(8, 18), pady=5)

        self._add_label(parent, "Vị trí đơn", 0, 2)
        ttk.Entry(parent, textvariable=self.location_var).grid(row=0, column=3, sticky="ew", padx=(8, 0), pady=5)

        self._add_label(parent, "Từ khóa thêm", 1, 0)
        ttk.Entry(parent, textvariable=self.keyword_var).grid(row=1, column=1, sticky="ew", padx=(8, 18), pady=5)

        self._add_label(parent, "Số lượng/job", 1, 2)
        limit_frame = ttk.Frame(parent)
        limit_frame.grid(row=1, column=3, sticky="ew", padx=(8, 0), pady=5)
        limit_frame.columnconfigure(0, weight=1)
        self.limit_spinbox = ttk.Spinbox(limit_frame, from_=1, to=5000, textvariable=self.limit_var, width=12)
        self.limit_spinbox.grid(row=0, column=0, sticky="ew")
        ttk.Checkbutton(
            limit_frame,
            text="Cào hết kết quả tìm thấy",
            variable=self.all_results_var,
            command=self._refresh_limit_state,
        ).grid(row=0, column=1, sticky="w", padx=(10, 0))

        self._add_label(parent, "Mẫu câu tìm kiếm", 2, 0)
        ttk.Entry(parent, textvariable=self.query_template_var).grid(row=2, column=1, columnspan=3, sticky="ew", padx=(8, 0), pady=5)

        self._add_label(parent, "Nhiều loại", 3, 0)
        ttk.Entry(parent, textvariable=self.multi_types_var).grid(row=3, column=1, sticky="ew", padx=(8, 18), pady=5)

        self._add_label(parent, "Nhiều vị trí", 3, 2)
        ttk.Entry(parent, textvariable=self.multi_locations_var).grid(row=3, column=3, sticky="ew", padx=(8, 0), pady=5)

        self._add_label(parent, "Preset danh mục", 4, 0)
        preset_box = ttk.Combobox(parent, textvariable=self.category_preset_var, values=list(CATEGORY_PRESETS), state="readonly")
        preset_box.grid(row=4, column=1, sticky="ew", padx=(8, 18), pady=5)
        ttk.Button(parent, text="Áp dụng preset", command=self._apply_category_preset).grid(row=4, column=2, sticky="ew", padx=(0, 8), pady=5)

        self._add_label(parent, "Preset vùng", 5, 0)
        location_preset_box = ttk.Combobox(parent, textvariable=self.location_preset_var, values=[""] + list(LOCATION_PRESETS), state="readonly")
        location_preset_box.grid(row=5, column=1, sticky="ew", padx=(8, 18), pady=5)
        ttk.Button(parent, text="Áp dụng vùng", command=self._apply_location_preset).grid(row=5, column=2, sticky="ew", padx=(0, 8), pady=5)

        self._add_label(parent, "Exclude keywords", 6, 0)
        ttk.Entry(parent, textvariable=self.exclude_keywords_var).grid(row=6, column=1, columnspan=3, sticky="ew", padx=(8, 0), pady=5)

        self._add_label(parent, "File output", 7, 0)
        ttk.Entry(parent, textvariable=self.output_var).grid(row=7, column=1, sticky="ew", padx=(8, 18), pady=5)
        ttk.Button(parent, text="Chọn...", command=self._choose_output).grid(row=7, column=2, sticky="ew", padx=(0, 8), pady=5)

        self._add_label(parent, "Tên file template", 8, 0)
        ttk.Entry(parent, textvariable=self.output_template_var).grid(row=8, column=1, columnspan=3, sticky="ew", padx=(8, 0), pady=5)

        self._add_label(parent, "Định dạng", 9, 0)
        ttk.Combobox(parent, textvariable=self.export_format_var, values=list(EXPORT_FORMAT_LABELS.values()), state="readonly").grid(row=9, column=1, sticky="ew", padx=(8, 18), pady=5)

        self._add_label(parent, "Chế độ xuất", 9, 2)
        ttk.Combobox(parent, textvariable=self.export_mode_var, values=list(EXPORT_MODE_LABELS.values()), state="readonly").grid(row=9, column=3, sticky="ew", padx=(8, 0), pady=5)

        self._add_label(parent, "Ghi file", 10, 0)
        ttk.Combobox(parent, textvariable=self.write_mode_var, values=list(WRITE_MODE_LABELS.values()), state="readonly").grid(row=10, column=1, sticky="ew", padx=(8, 18), pady=5)

        self._add_label(parent, "Tách file", 10, 2)
        ttk.Combobox(parent, textvariable=self.split_by_var, values=list(SPLIT_LABELS.values()), state="readonly").grid(row=10, column=3, sticky="ew", padx=(8, 0), pady=5)

        self._add_label(parent, "Chống trùng", 11, 0)
        ttk.Combobox(parent, textvariable=self.dedupe_mode_var, values=list(DEDUPE_LABELS.values()), state="readonly").grid(row=11, column=1, sticky="ew", padx=(8, 18), pady=5)

        flags = ttk.Frame(parent)
        flags.grid(row=11, column=2, columnspan=2, sticky="w", padx=(8, 0), pady=5)
        ttk.Checkbutton(flags, text="Chạy tiếp từ file/checkpoint", variable=self.resume_var).grid(row=0, column=0, padx=(0, 18))
        ttk.Checkbutton(flags, text="Chạy ẩn Chrome", variable=self.headless_var).grid(row=0, column=1)

        timing = ttk.LabelFrame(parent, text="Độ trễ / thời gian chờ / số luồng", padding=10)
        timing.grid(row=12, column=0, columnspan=4, sticky="ew", pady=(12, 0))
        for column in range(8):
            timing.columnconfigure(column, weight=1)
        labels = [("Độ trễ mỗi nơi", self.delay_var), ("Độ trễ cuộn", self.scroll_pause_var), ("Chờ tối đa", self.timeout_var), ("Số luồng", self.worker_count_var)]
        for index, (label, variable) in enumerate(labels):
            ttk.Label(timing, text=label).grid(row=0, column=index * 2, sticky="w", padx=(0, 6))
            ttk.Entry(timing, textvariable=variable, width=12).grid(row=0, column=index * 2 + 1, sticky="ew", padx=(0, 12))

        query_frame = ttk.LabelFrame(parent, text="Xem trước câu tìm kiếm", padding=10)
        query_frame.grid(row=13, column=0, columnspan=4, sticky="ew", pady=(12, 0))
        query_frame.columnconfigure(0, weight=1)
        self.query_preview = ttk.Label(query_frame, text="", anchor="w")
        self.query_preview.grid(row=0, column=0, sticky="ew")
        for var in (
            self.place_type_var,
            self.keyword_var,
            self.location_var,
            self.query_template_var,
            self.multi_types_var,
            self.multi_locations_var,
            self.category_preset_var,
            self.location_preset_var,
            self.limit_var,
            self.output_template_var,
            self.export_format_var,
            self.all_results_var,
        ):
            var.trace_add("write", lambda *_: self._refresh_query_preview())

        settings_frame = ttk.LabelFrame(parent, text="Lưu cấu hình", padding=10)
        settings_frame.grid(row=14, column=0, columnspan=4, sticky="ew", pady=(12, 0))
        settings_frame.columnconfigure(1, weight=1)
        ttk.Label(settings_frame, text="File cấu hình").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(settings_frame, textvariable=self.settings_path_var, state="readonly").grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ttk.Button(settings_frame, text="Lưu cấu hình", command=self._save_settings_now).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(settings_frame, text="Tải cấu hình", command=self._load_settings_now).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(settings_frame, text="Mở thư mục", command=self._open_settings_folder).grid(row=0, column=4)
        ttk.Label(settings_frame, textvariable=self.settings_status_var).grid(row=1, column=1, columnspan=4, sticky="w", pady=(6, 0))

        note = ttk.Label(
            parent,
            text="Tool không thêm proxy, stealth hay bypass CAPTCHA. Nếu Google chặn, hãy tăng delay, giảm luồng hoặc dùng Places API chính thức.",
            wraplength=980,
        )
        note.grid(row=15, column=0, columnspan=4, sticky="ew", pady=(14, 0))

    def _build_fields_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        actions = ttk.Frame(parent)
        actions.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Button(actions, text="Chọn tất cả", command=lambda: self._set_all_fields(True)).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Bỏ chọn tất cả", command=lambda: self._set_all_fields(False)).grid(row=0, column=1)

        grid = ttk.Frame(parent)
        grid.grid(row=1, column=0, sticky="nsew")
        for column in range(3):
            grid.columnconfigure(column, weight=1)
        for index, field in enumerate(crawler.SCHEMA_FIELDS):
            row = index // 3
            column = index % 3
            label = f"{field} - {FIELD_LABELS.get(field, field)}"
            ttk.Checkbutton(grid, text=label, variable=self.field_vars[field]).grid(row=row, column=column, sticky="w", padx=(0, 18), pady=5)

    def _build_preview_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        filters = ttk.Frame(parent)
        filters.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        for column in range(12):
            filters.columnconfigure(column, weight=1)
        ttk.Label(filters, text="Rating >=").grid(row=0, column=0, sticky="w")
        ttk.Entry(filters, textvariable=self.rating_filter_var, width=8).grid(row=0, column=1, sticky="ew", padx=(6, 12))
        ttk.Label(filters, text="Giá max").grid(row=0, column=2, sticky="w")
        ttk.Entry(filters, textvariable=self.price_filter_var, width=10).grid(row=0, column=3, sticky="ew", padx=(6, 12))
        ttk.Label(filters, text="Quận/Huyện").grid(row=0, column=4, sticky="w")
        ttk.Entry(filters, textvariable=self.district_filter_var).grid(row=0, column=5, sticky="ew", padx=(6, 12))
        ttk.Label(filters, text="Sắp xếp").grid(row=0, column=6, sticky="w")
        ttk.Combobox(filters, textvariable=self.sort_field_var, values=crawler.SCHEMA_FIELDS, state="readonly", width=18).grid(row=0, column=7, sticky="ew", padx=(6, 12))
        ttk.Checkbutton(filters, text="Giảm dần", variable=self.sort_desc_var).grid(row=0, column=8, sticky="w")
        ttk.Button(filters, text="Áp dụng", command=self._apply_preview_filter).grid(row=0, column=9, padx=(8, 0))

        self.preview_tree = ttk.Treeview(parent, show="headings")
        self.preview_tree.grid(row=1, column=0, sticky="nsew")
        y_scroll = ttk.Scrollbar(parent, orient="vertical", command=self.preview_tree.yview)
        x_scroll = ttk.Scrollbar(parent, orient="horizontal", command=self.preview_tree.xview)
        y_scroll.grid(row=1, column=1, sticky="ns")
        x_scroll.grid(row=2, column=0, sticky="ew")
        self.preview_tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self._configure_preview_columns(crawler.SCHEMA_FIELDS)
        self.preview_tree.bind("<Button-3>", self._show_preview_context_menu)
        self.preview_tree.bind("<Button-2>", self._show_preview_context_menu)

    def _build_log_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        self.log_text = tk.Text(parent, height=18, wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(parent, command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.tag_configure("info", foreground="#1f2937")
        self.log_text.tag_configure("warning", foreground="#a16207")
        self.log_text.tag_configure("error", foreground="#b91c1c")
        self.log_text.tag_configure("success", foreground="#047857")
        self.log_text.bind("<Button-3>", self._show_log_context_menu)
        self.log_text.bind("<Button-2>", self._show_log_context_menu)

    def _build_footer(self, parent: ttk.Frame) -> None:
        footer = ttk.Frame(parent)
        footer.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        footer.columnconfigure(8, weight=1)
        self.start_button = ttk.Button(footer, text="Chạy hàng đợi", command=self._start)
        self.start_button.grid(row=0, column=0, padx=(0, 8))
        ttk.Button(footer, text="Test crawl 1 dòng", command=self._start_test).grid(row=0, column=1, padx=(0, 8))
        self.pause_button = ttk.Button(footer, text="Tạm dừng", command=self._pause, state="disabled")
        self.pause_button.grid(row=0, column=2, padx=(0, 8))
        self.resume_button = ttk.Button(footer, text="Tiếp tục", command=self._resume, state="disabled")
        self.resume_button.grid(row=0, column=3, padx=(0, 8))
        self.stop_button = ttk.Button(footer, text="Dừng", command=self._stop, state="disabled")
        self.stop_button.grid(row=0, column=4, padx=(0, 8))
        ttk.Button(footer, text="Mở file", command=self._open_output_file).grid(row=0, column=5, padx=(0, 8))
        ttk.Button(footer, text="Mở thư mục", command=self._open_output_folder).grid(row=0, column=6, padx=(0, 12))
        ttk.Progressbar(footer, variable=self.progress_value_var, maximum=100, length=180).grid(row=0, column=7, padx=(0, 8))
        ttk.Label(footer, textvariable=self.progress_text_var).grid(row=0, column=8, sticky="w")
        ttk.Label(footer, textvariable=self.status_var, anchor="e").grid(row=0, column=9, sticky="e")

    def _add_label(self, parent: ttk.Frame, text: str, row: int, column: int) -> None:
        ttk.Label(parent, text=text).grid(row=row, column=column, sticky="w", pady=5)

    def _popup_menu(self, menu: tk.Menu, event: tk.Event) -> None:
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _add_menu_command(self, menu: tk.Menu, label: str, command, enabled: bool = True) -> None:
        menu.add_command(label=label, command=command, state="normal" if enabled else "disabled")

    def _copy_to_clipboard(self, text: str, label: str = "") -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set(f"Đã copy {label}" if label else "Đã copy")

    def _tree_row_from_item(self, tree: ttk.Treeview, item: str, fields: list[str]) -> dict[str, Any]:
        values = tree.item(item, "values")
        return {field: values[index] if index < len(values) else "" for index, field in enumerate(fields)}

    def _preview_rows_from_items(self, items: Iterable[str]) -> list[dict[str, Any]]:
        return [self._tree_row_from_item(self.preview_tree, item, self.preview_fields) for item in items]

    def _all_preview_rows(self) -> list[dict[str, Any]]:
        return self._preview_rows_from_items(self.preview_tree.get_children())

    def _copy_preview_rows(self, items: Iterable[str], export_format: str, label: str) -> None:
        rows = self._preview_rows_from_items(items)
        self._copy_to_clipboard(format_rows_for_clipboard(rows, self.preview_fields, export_format), label)

    def _copy_preview_field(self, items: Iterable[str], field: str) -> None:
        rows = self._preview_rows_from_items(items)
        values = [str(row.get(field) or "") for row in rows]
        self._copy_to_clipboard("\n".join(values), FIELD_LABELS.get(field, field))

    def _copy_preview_contact_card(self, row: dict[str, Any]) -> None:
        self._copy_to_clipboard(format_place_contact_card(row), "thẻ thông tin")

    def _copy_preview_coordinates(self, row: dict[str, Any]) -> None:
        latitude = row.get("latitude")
        longitude = row.get("longitude")
        value = f"{latitude},{longitude}" if latitude not in (None, "") and longitude not in (None, "") else ""
        self._copy_to_clipboard(value, "tọa độ")

    def _open_url(self, url: str, title: str = "Không có link") -> None:
        if url:
            webbrowser.open(url)
        else:
            messagebox.showinfo(title, "Dòng này chưa có link để mở.")

    def _open_path_file(self, path_value: str) -> None:
        path = Path(path_value or "").expanduser()
        if path.exists():
            webbrowser.open(str(path.resolve()))
        else:
            messagebox.showinfo("Chưa có file", "File này chưa tồn tại.")

    def _open_path_folder(self, path_value: str) -> None:
        path = Path(path_value or "").expanduser()
        folder = path.parent if path.suffix else path
        if folder.exists():
            webbrowser.open(str(folder.resolve()))
        else:
            messagebox.showinfo("Chưa có thư mục", "Thư mục output chưa tồn tại.")

    def _show_preview_context_menu(self, event: tk.Event) -> None:
        item = self.preview_tree.identify_row(event.y)
        column_id = self.preview_tree.identify_column(event.x)
        if item:
            if item not in self.preview_tree.selection():
                self.preview_tree.selection_set(item)
            self.preview_tree.focus(item)

        selected_items = list(self.preview_tree.selection())
        row = self._tree_row_from_item(self.preview_tree, item, self.preview_fields) if item else {}
        field = field_from_tree_column(self.preview_fields, column_id)
        has_row = bool(row)
        has_selection = bool(selected_items)
        visible_items = list(self.preview_tree.get_children())
        menu = tk.Menu(self.root, tearoff=False)

        self._add_menu_command(menu, f"Sao chép ô ({field})", lambda f=field, i=item: self._copy_preview_field([i], f), has_row and bool(field))
        self._add_menu_command(menu, "Sao chép dòng này - TSV", lambda i=item: self._copy_preview_rows([i], "tsv", "dòng TSV"), has_row)
        self._add_menu_command(menu, "Sao chép dòng này - JSON", lambda i=item: self._copy_preview_rows([i], "json", "dòng JSON"), has_row)
        self._add_menu_command(menu, "Sao chép thẻ thông tin", lambda r=row: self._copy_preview_contact_card(r), has_row)
        self._add_menu_command(menu, "Sao chép tọa độ", lambda r=row: self._copy_preview_coordinates(r), has_row)

        field_menu = tk.Menu(menu, tearoff=False)
        for copy_field in PREVIEW_CONTEXT_COPY_FIELDS:
            if copy_field in self.preview_fields:
                field_menu.add_command(
                    label=f"{FIELD_LABELS.get(copy_field, copy_field)}",
                    command=lambda f=copy_field, items=tuple(selected_items or ([item] if item else [])): self._copy_preview_field(items, f),
                )
        menu.add_cascade(label="Sao chép từng trường", menu=field_menu, state="normal" if has_row else "disabled")

        menu.add_separator()
        self._add_menu_command(menu, "Sao chép các dòng chọn - TSV", lambda items=tuple(selected_items): self._copy_preview_rows(items, "tsv", "các dòng chọn TSV"), has_selection)
        self._add_menu_command(menu, "Sao chép các dòng chọn - CSV", lambda items=tuple(selected_items): self._copy_preview_rows(items, "csv", "các dòng chọn CSV"), has_selection)
        self._add_menu_command(menu, "Sao chép các dòng chọn - JSON", lambda items=tuple(selected_items): self._copy_preview_rows(items, "json", "các dòng chọn JSON"), has_selection)
        self._add_menu_command(menu, "Sao chép tất cả đang hiển thị - TSV", lambda items=tuple(visible_items): self._copy_preview_rows(items, "tsv", "tất cả TSV"), bool(visible_items))
        self._add_menu_command(menu, "Sao chép tất cả đang hiển thị - CSV", lambda items=tuple(visible_items): self._copy_preview_rows(items, "csv", "tất cả CSV"), bool(visible_items))
        self._add_menu_command(menu, "Sao chép tất cả đang hiển thị - JSON", lambda items=tuple(visible_items): self._copy_preview_rows(items, "json", "tất cả JSON"), bool(visible_items))

        menu.add_separator()
        maps_url = maps_open_url(row) if has_row else ""
        website_url = open_url_for_field(row, "website") if has_row else ""
        image_url = open_url_for_field(row, "image_url") if has_row else ""
        self._add_menu_command(menu, "Mở quán trên Google Maps", lambda url=maps_url: self._open_url(url, "Không có Google Maps"), has_row)
        self._add_menu_command(menu, "Mở website", lambda url=website_url: self._open_url(url, "Không có website"), bool(website_url))
        self._add_menu_command(menu, "Mở ảnh", lambda url=image_url: self._open_url(url, "Không có ảnh"), bool(image_url))
        self._add_menu_command(menu, "Sao chép link mở Maps", lambda url=maps_url: self._copy_to_clipboard(url, "link Maps"), has_row)

        self._popup_menu(menu, event)

    def _selected_job_indices(self) -> list[int]:
        indices: list[int] = []
        for item in self.job_tree.selection():
            try:
                index = int(item)
            except ValueError:
                continue
            if 0 <= index < len(self.job_queue):
                indices.append(index)
        return sorted(set(indices))

    def _copy_job_rows(self, indices: Iterable[int], export_format: str, label: str) -> None:
        selected_jobs = [self.job_queue[index] for index in indices if 0 <= index < len(self.job_queue)]
        self._copy_to_clipboard(format_jobs_for_clipboard(selected_jobs, export_format), label)

    def _duplicate_selected_jobs(self) -> None:
        indices = self._selected_job_indices()
        clones = [clone_job_for_context(self.job_queue[index]) for index in indices]
        self.job_queue.extend(clones)
        self._refresh_job_tree()
        self._append_log(f"Đã nhân bản {len(clones)} job.", "success")

    def _retry_selected_jobs(self) -> None:
        count = 0
        for index in self._selected_job_indices():
            job = self.job_queue[index]
            job.status = "pending"
            job.failed = 0
            count += 1
        self._refresh_job_tree()
        self._append_log(f"Đã đưa {count} job đã chọn về trạng thái chờ chạy.", "warning")

    def _start_selected_jobs(self, test_one: bool = False) -> None:
        indices = self._selected_job_indices()
        if not indices:
            messagebox.showinfo("Chưa chọn job", "Chọn ít nhất một job trong bảng.")
            return
        selected_jobs = [self.job_queue[index] for index in indices]
        if test_one:
            selected_jobs = [clone_job_for_context(job, limit_override=1) for job in selected_jobs]
        self._start_job_list(selected_jobs, test_one=test_one)

    def _show_job_context_menu(self, event: tk.Event) -> None:
        item = self.job_tree.identify_row(event.y)
        column_id = self.job_tree.identify_column(event.x)
        if item:
            if item not in self.job_tree.selection():
                self.job_tree.selection_set(item)
            self.job_tree.focus(item)

        indices = self._selected_job_indices()
        job = self.job_queue[int(item)] if item and item.isdigit() and int(item) < len(self.job_queue) else None
        field = field_from_tree_column(JOB_CONTEXT_FIELDS, column_id)
        row = job_to_context_row(job) if job else {}
        has_job = job is not None
        has_selection = bool(indices)
        output = str(row.get("output") or "")
        query_url = f"https://www.google.com/maps/search/{quote_plus(job.query)}" if job else ""

        menu = tk.Menu(self.root, tearoff=False)
        self._add_menu_command(menu, f"Sao chép ô ({field})", lambda r=row, f=field: self._copy_to_clipboard(str(r.get(f, "")), f), has_job and bool(field))
        self._add_menu_command(menu, "Sao chép câu tìm kiếm", lambda j=job: self._copy_to_clipboard(j.query, "câu tìm kiếm"), has_job)
        self._add_menu_command(menu, "Sao chép đường dẫn output", lambda value=output: self._copy_to_clipboard(value, "output"), bool(output))
        self._add_menu_command(menu, "Sao chép job chọn - TSV", lambda idx=tuple(indices): self._copy_job_rows(idx, "tsv", "job TSV"), has_selection)
        self._add_menu_command(menu, "Sao chép job chọn - CSV", lambda idx=tuple(indices): self._copy_job_rows(idx, "csv", "job CSV"), has_selection)
        self._add_menu_command(menu, "Sao chép job chọn - JSON", lambda idx=tuple(indices): self._copy_job_rows(idx, "json", "job JSON"), has_selection)

        menu.add_separator()
        self._add_menu_command(menu, "Chạy job đã chọn", lambda: self._start_selected_jobs(test_one=False), has_selection)
        self._add_menu_command(menu, "Test crawl job đã chọn (limit 1)", lambda: self._start_selected_jobs(test_one=True), has_selection)
        self._add_menu_command(menu, "Nhân bản job đã chọn", self._duplicate_selected_jobs, has_selection)
        self._add_menu_command(menu, "Chạy lại job đã chọn", self._retry_selected_jobs, has_selection)
        self._add_menu_command(menu, "Xóa job đã chọn", self._remove_selected_jobs, has_selection)

        menu.add_separator()
        self._add_menu_command(menu, "Mở query trên Google Maps", lambda url=query_url: self._open_url(url, "Không có query"), has_job)
        self._add_menu_command(menu, "Mở file output", lambda value=output: self._open_path_file(value), bool(output))
        self._add_menu_command(menu, "Mở thư mục output", lambda value=output: self._open_path_folder(value), bool(output))

        self._popup_menu(menu, event)

    def _log_selection_text(self) -> str:
        try:
            return self.log_text.get("sel.first", "sel.last")
        except tk.TclError:
            return ""

    def _copy_log_selection(self) -> None:
        self._copy_to_clipboard(self._log_selection_text(), "nhật ký đã chọn")

    def _copy_log_all(self) -> None:
        self._copy_to_clipboard(self.log_text.get("1.0", "end-1c"), "toàn bộ nhật ký")

    def _clear_log_text(self) -> None:
        self.log_text.delete("1.0", "end")

    def _select_all_log_text(self) -> None:
        self.log_text.tag_add("sel", "1.0", "end-1c")
        self.log_text.mark_set("insert", "1.0")
        self.log_text.see("insert")

    def _show_log_context_menu(self, event: tk.Event) -> None:
        has_selection = bool(self._log_selection_text())
        has_log = bool(self.log_text.get("1.0", "end-1c").strip())
        menu = tk.Menu(self.root, tearoff=False)
        self._add_menu_command(menu, "Sao chép đoạn nhật ký đã chọn", self._copy_log_selection, has_selection)
        self._add_menu_command(menu, "Sao chép toàn bộ nhật ký", self._copy_log_all, has_log)
        self._add_menu_command(menu, "Chọn toàn bộ nhật ký", self._select_all_log_text, has_log)
        menu.add_separator()
        self._add_menu_command(menu, "Xóa nhật ký", self._clear_log_text, has_log)
        self._popup_menu(menu, event)

    def _refresh_limit_state(self) -> None:
        if hasattr(self, "limit_spinbox"):
            self.limit_spinbox.configure(state="disabled" if self.all_results_var.get() else "normal")

    def _set_all_fields(self, value: bool) -> None:
        for variable in self.field_vars.values():
            variable.set(value)

    def _selected_fields(self) -> list[str]:
        return selected_fields_from_values({field: variable.get() for field, variable in self.field_vars.items()})

    def _apply_category_preset(self) -> None:
        preset = self.category_preset_var.get()
        categories = jobs.categories_for_preset(preset)
        resolved = jobs.resolve_preset_name(preset, CATEGORY_PRESETS)
        if categories:
            self.category_preset_var.set(resolved)
            self.multi_types_var.set(", ".join(categories))
            self.place_type_var.set(categories[0])

    def _apply_location_preset(self) -> None:
        locations = jobs.locations_for_preset(self.location_preset_var.get(), self.multi_locations_var.get())
        if locations:
            resolved = jobs.resolve_preset_name(self.location_preset_var.get(), LOCATION_PRESETS)
            if resolved in LOCATION_PRESETS:
                self.location_preset_var.set(resolved)
            self.multi_locations_var.set(", ".join(locations))
            self.location_var.set(locations[0])
            self._append_log(f"Đã áp dụng vùng {self.location_preset_var.get()}: {len(locations)} vị trí.", "info")

    def _refresh_query_preview(self) -> None:
        try:
            limit = parse_limit_for_mode(self.limit_var.get(), "Số lượng", self.all_results_var.get())
            preview = format_query_preview_for_inputs(
                place_type=self.place_type_var.get(),
                keyword=self.keyword_var.get(),
                location=self.location_var.get(),
                multi_types=self.multi_types_var.get(),
                multi_locations=self.multi_locations_var.get(),
                limit=limit,
                query_template=self.query_template_var.get(),
                output=self.output_var.get(),
                output_template=self.output_template_var.get(),
                export_format=export_format_value(self.export_format_var.get()),
                category_preset=self.category_preset_var.get(),
                location_preset=self.location_preset_var.get(),
                all_results=self.all_results_var.get(),
            )
        except ValueError as exc:
            preview = f"Cấu hình chưa hợp lệ: {exc}"
        self.query_preview.configure(text=preview)

    def _choose_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Chọn file output",
            initialfile=Path(self.output_var.get()).name,
            defaultextension=".csv",
            filetypes=[("Định dạng hỗ trợ", "*.csv *.jsonl *.sqlite *.xlsx"), ("Tất cả file", "*.*")],
        )
        if path:
            self.output_var.set(path)

    def _open_output_file(self) -> None:
        path = Path(self.output_var.get() or ".").expanduser()
        if path.exists():
            webbrowser.open(str(path.resolve()))
        else:
            messagebox.showinfo("Chưa có file", "File output chưa tồn tại.")

    def _open_output_folder(self) -> None:
        path = Path(self.output_var.get() or ".").expanduser()
        folder = path.parent if path.suffix else path
        folder.mkdir(parents=True, exist_ok=True)
        webbrowser.open(str(folder.resolve()))

    def _single_job_from_config(self, limit_override: int | None = None) -> jobs.CrawlJob:
        limit = limit_override if limit_override is not None else parse_limit_for_mode(
            self.limit_var.get(),
            "Số lượng",
            self.all_results_var.get(),
        )
        return jobs.CrawlJob(
            place_type=self.place_type_var.get().strip(),
            keyword=self.keyword_var.get().strip(),
            location=self.location_var.get().strip(),
            limit=limit,
            output=self.output_var.get().strip(),
            query_template=self.query_template_var.get().strip() or jobs.QUERY_TEMPLATE,
            exclude_keywords=jobs.split_multi_value(self.exclude_keywords_var.get()),
        )

    def _implicit_jobs_from_config(self, limit_override: int | None = None) -> list[jobs.CrawlJob]:
        limit = parse_limit_for_mode(self.limit_var.get(), "Số lượng", self.all_results_var.get())
        crawl_jobs = build_implicit_start_jobs_from_inputs(
            place_type=self.place_type_var.get(),
            keyword=self.keyword_var.get(),
            location=self.location_var.get(),
            multi_types=self.multi_types_var.get(),
            multi_locations=self.multi_locations_var.get(),
            limit=limit,
            query_template=self.query_template_var.get(),
            output=self.output_var.get(),
            output_template=self.output_template_var.get(),
            export_format=export_format_value(self.export_format_var.get()),
            category_preset=self.category_preset_var.get(),
            location_preset=self.location_preset_var.get(),
            all_results=self.all_results_var.get(),
            limit_override=limit_override,
        )
        exclude_keywords = jobs.split_multi_value(self.exclude_keywords_var.get())
        for job in crawl_jobs:
            job.exclude_keywords = exclude_keywords
        return crawl_jobs

    def _add_single_job(self) -> None:
        try:
            self.job_queue.append(self._single_job_from_config())
            self._refresh_job_tree()
        except ValueError as exc:
            messagebox.showerror("Cấu hình chưa hợp lệ", str(exc))

    def _generate_jobs(self) -> None:
        try:
            generated = build_jobs_from_inputs(
                place_types=place_types_for_start(
                    self.place_type_var.get(),
                    self.multi_types_var.get(),
                    self.category_preset_var.get(),
                ),
                keywords=self.keyword_var.get(),
                locations=locations_for_start(self.location_var.get(), self.multi_locations_var.get()),
                limit=parse_limit_for_mode(self.limit_var.get(), "Số lượng", self.all_results_var.get()),
                query_template=self.query_template_var.get(),
                output_template=self.output_template_var.get(),
                export_format=export_format_value(self.export_format_var.get()),
                location_preset=self.location_preset_var.get(),
                all_results=self.all_results_var.get(),
            )
        except ValueError as exc:
            messagebox.showerror("Không tạo được job", str(exc))
            return
        for job in generated:
            job.exclude_keywords = jobs.split_multi_value(self.exclude_keywords_var.get())
        self.job_queue.extend(generated)
        self._refresh_job_tree()
        self._append_log(f"Đã tạo {len(generated)} job.", "success")

    def _import_jobs(self) -> None:
        path = filedialog.askopenfilename(title="Nhập job", filetypes=[("File job", "*.txt *.csv"), ("Tất cả file", "*.*")])
        if not path:
            return
        try:
            imported = jobs.import_jobs(Path(path))
        except Exception as exc:
            messagebox.showerror("Nhập job lỗi", str(exc))
            return
        self.job_queue.extend(imported)
        self._refresh_job_tree()
        self._append_log(f"Đã nhập {len(imported)} job từ {path}", "success")

    def _save_preset(self) -> None:
        path = filedialog.asksaveasfilename(title="Lưu preset", defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        jobs.save_preset(Path(path), self.job_queue, settings=self._settings_payload(include_jobs=False))
        self._append_log(f"Đã lưu preset: {path}", "success")

    def _load_preset(self) -> None:
        path = filedialog.askopenfilename(title="Tải preset", filetypes=[("JSON", "*.json"), ("Tất cả file", "*.*")])
        if not path:
            return
        try:
            loaded_jobs, settings = jobs.load_preset(Path(path))
        except Exception as exc:
            messagebox.showerror("Tải preset lỗi", str(exc))
            return
        self.job_queue = loaded_jobs
        self._apply_settings(settings)
        self._refresh_job_tree()
        self._append_log(f"Đã tải preset: {path}", "success")

    def _retry_failed_jobs(self) -> None:
        retried = 0
        for job in self.job_queue:
            if job.status == "error":
                job.status = "pending"
                job.failed = 0
                retried += 1
        self._refresh_job_tree()
        self._append_log(f"Đã đưa {retried} job lỗi về trạng thái chờ chạy.", "warning")

    def _remove_selected_jobs(self) -> None:
        selected = {int(item) for item in self.job_tree.selection()}
        self.job_queue = [job for index, job in enumerate(self.job_queue) if index not in selected]
        self._refresh_job_tree()

    def _clear_jobs(self) -> None:
        self.job_queue.clear()
        self._refresh_job_tree()

    def _refresh_job_tree(self) -> None:
        if not hasattr(self, "job_tree"):
            return
        for item in self.job_tree.get_children():
            self.job_tree.delete(item)
        for index, job in enumerate(self.job_queue):
            self.job_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(job_status_label(job.status), job.query, format_job_limit(job.limit), job.output, job.saved, job.failed),
            )

    def _read_base_options(self, job: jobs.CrawlJob) -> crawler.CrawlOptions:
        output = Path(job.output or self.output_var.get() or default_output_path(export_format=self.export_format_var.get()))
        return crawler.CrawlOptions(
            query=job.query,
            limit=job.limit,
            out=output,
            delay=parse_non_negative_float(self.delay_var.get(), "Độ trễ mỗi nơi"),
            scroll_pause=parse_non_negative_float(self.scroll_pause_var.get(), "Độ trễ cuộn"),
            timeout=parse_non_negative_float(self.timeout_var.get(), "Thời gian chờ tối đa"),
            headless=self.headless_var.get(),
            max_workers=normalize_worker_count(self.worker_count_var.get()),
            output_fields=self._selected_fields(),
            export_mode=export_mode_value(self.export_mode_var.get()),
            export_format=export_format_value(self.export_format_var.get()),
            write_mode=write_mode_value(self.write_mode_var.get()),
            split_by=split_mode_value(self.split_by_var.get()),
            job_location=job.location,
            resume_from_existing=self.resume_var.get(),
            dedupe_mode=dedupe_mode_value(self.dedupe_mode_var.get()),
            exclude_keywords=job.exclude_keywords or jobs.split_multi_value(self.exclude_keywords_var.get()),
        )

    def _start(self) -> None:
        self._start_jobs(test_one=False)

    def _start_test(self) -> None:
        self._start_jobs(test_one=True)

    def _start_jobs(self, test_one: bool) -> None:
        try:
            crawl_jobs = [self._single_job_from_config(limit_override=1)] if test_one else (self.job_queue[:] or self._implicit_jobs_from_config())
        except ValueError as exc:
            messagebox.showerror("Cấu hình chưa hợp lệ", str(exc))
            return
        self._start_job_list(crawl_jobs, test_one=test_one)

    def _start_job_list(self, crawl_jobs: list[jobs.CrawlJob], test_one: bool = False) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("Đang chạy", "Crawler vẫn đang chạy.")
            return
        try:
            for job in crawl_jobs:
                if job.limit < 0:
                    raise ValueError("Số lượng phải là ALL hoặc lớn hơn 0.")
            job_options = [(job, self._read_base_options(job)) for job in crawl_jobs]
        except ValueError as exc:
            messagebox.showerror("Cấu hình chưa hợp lệ", str(exc))
            return

        self.log_text.delete("1.0", "end")
        self._clear_preview()
        self.preview_places = []
        self.progress_value_var.set(0)
        self.progress_text_var.set("0/0")
        self.stop_event = threading.Event()
        self.pause_event.clear()
        self._set_running(True)
        self.worker_thread = threading.Thread(target=self._run_worker, args=(job_options, test_one), daemon=True)
        self.worker_thread.start()

    def _pause(self) -> None:
        self.pause_event.set()
        self.status_var.set("Tạm dừng")
        self._append_log("Đã yêu cầu tạm dừng. Crawler sẽ dừng giữa các địa điểm.", "warning")
        self.pause_button.configure(state="disabled")
        self.resume_button.configure(state="normal")

    def _resume(self) -> None:
        self.pause_event.clear()
        self.status_var.set("Đang chạy")
        self._append_log("Đã tiếp tục.", "success")
        self.pause_button.configure(state="normal")
        self.resume_button.configure(state="disabled")

    def _stop(self) -> None:
        if self.stop_event:
            self.stop_event.set()
            self.status_var.set("Đang dừng...")
            self._append_log("Đã yêu cầu dừng. Chrome sẽ đóng sau bước hiện tại.", "warning")

    def _run_worker(self, job_options: list[tuple[jobs.CrawlJob, crawler.CrawlOptions]], test_one: bool) -> None:
        all_places: list[crawler.Place] = []
        try:
            for index, (job, options) in enumerate(job_options, start=1):
                if self.stop_event and self.stop_event.is_set():
                    break
                job.status = "running"
                self.log_queue.put(("job_update", None))
                self.log_queue.put(("log", (f"Job {index}/{len(job_options)} - Câu tìm kiếm: {options.query}", "info")))
                self.log_queue.put(("log", (f"File xuất: {options.out}", "info")))
                places = crawler.run_crawl(options, progress=self._queue_log, stop_event=self.stop_event, pause_event=self.pause_event)
                job.status = "done"
                job.done = len(places)
                job.saved = len(places)
                all_places.extend(places)
                self.log_queue.put(("preview", (all_places[:], options.output_fields or crawler.SCHEMA_FIELDS)))
                self.log_queue.put(("job_update", None))
                if test_one:
                    break
            self.log_queue.put(("done", f"Hoàn tất. Đã lưu {len(all_places)} dòng."))
        except Exception as exc:
            for job, _ in job_options:
                if job.status == "running":
                    job.status = "error"
                    job.failed += 1
            self.log_queue.put(("job_update", None))
            self.log_queue.put(("error", str(exc)))

    def _queue_log(self, message: str) -> None:
        level = "info"
        lowered = message.lower()
        if any(token in lowered for token in ("error", "lỗi", "blocked", "captcha")):
            level = "error"
        elif any(token in lowered for token in ("skipped", "warning", "pause", "excluded", "delay increased")):
            level = "warning"
        elif any(token in lowered for token in ("saved", "hoàn tất", "exported")):
            level = "success"
        self.log_queue.put(("log", (message, level)))

    def _drain_log_queue(self) -> None:
        try:
            while True:
                kind, payload = self.log_queue.get_nowait()
                if kind == "log":
                    message, level = payload
                    self._append_log(str(message), str(level))
                elif kind == "preview":
                    places, fields = payload
                    self.preview_places = places
                    self.preview_fields = fields
                    self._fill_preview(places, fields)
                elif kind == "job_update":
                    self._refresh_job_tree()
                elif kind == "done":
                    self._append_log(str(payload), "success")
                    self.status_var.set("Xong")
                    self._set_running(False)
                elif kind == "error":
                    self._append_log(f"Lỗi: {payload}", "error")
                    self.status_var.set("Lỗi")
                    self._set_running(False)
                    messagebox.showerror("Crawler lỗi", str(payload))
        except queue.Empty:
            pass
        self.root.after(150, self._drain_log_queue)

    def _append_log(self, message: str, level: str = "info") -> None:
        self.log_text.insert("end", f"{datetime.now():%H:%M:%S}  {message}\n", level)
        self.log_text.see("end")
        match = re.search(r"\[(\d+)/(\d+)\]", message)
        if match:
            current = int(match.group(1))
            total = max(1, int(match.group(2)))
            self.progress_text_var.set(f"{current}/{total}")
            self.progress_value_var.set(current / total * 100)

    def _configure_preview_columns(self, fields: list[str]) -> None:
        self.preview_tree.configure(columns=fields)
        for field in fields:
            self.preview_tree.heading(field, text=field)
            self.preview_tree.column(field, width=150, minwidth=90, stretch=False)

    def _clear_preview(self) -> None:
        for item in self.preview_tree.get_children():
            self.preview_tree.delete(item)

    def _fill_preview(self, places: list[crawler.Place], fields: list[str]) -> None:
        self.preview_fields = fields
        self._configure_preview_columns(fields)
        self._clear_preview()
        for place in places[:500]:
            row = asdict(place)
            self.preview_tree.insert("", "end", values=[row.get(field, "") for field in fields])

    def _apply_preview_filter(self) -> None:
        try:
            filtered = filter_places(self.preview_places, self.rating_filter_var.get(), self.price_filter_var.get(), self.district_filter_var.get())
        except ValueError as exc:
            messagebox.showerror("Filter lỗi", str(exc))
            return
        sorted_rows = sort_places(filtered, self.sort_field_var.get(), self.sort_desc_var.get())
        self._fill_preview(sorted_rows, self.preview_fields)

    def _set_running(self, running: bool) -> None:
        self.start_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")
        self.pause_button.configure(state="normal" if running else "disabled")
        self.resume_button.configure(state="disabled")
        if running:
            self.status_var.set("Đang chạy")

    def _settings_payload(self, include_jobs: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "place_type": self.place_type_var.get(),
            "keyword": self.keyword_var.get(),
            "location": self.location_var.get(),
            "multi_types": self.multi_types_var.get(),
            "multi_locations": self.multi_locations_var.get(),
            "category_preset": self.category_preset_var.get(),
            "location_preset": self.location_preset_var.get(),
            "query_template": self.query_template_var.get(),
            "exclude_keywords": self.exclude_keywords_var.get(),
            "limit": self.limit_var.get(),
            "all_results": self.all_results_var.get(),
            "delay": self.delay_var.get(),
            "scroll_pause": self.scroll_pause_var.get(),
            "timeout": self.timeout_var.get(),
            "workers": self.worker_count_var.get(),
            "output": self.output_var.get(),
            "output_template": self.output_template_var.get(),
            "export_mode": export_mode_value(self.export_mode_var.get()),
            "export_format": export_format_value(self.export_format_var.get()),
            "write_mode": write_mode_value(self.write_mode_var.get()),
            "split_by": split_mode_value(self.split_by_var.get()),
            "dedupe_mode": dedupe_mode_value(self.dedupe_mode_var.get()),
            "resume": self.resume_var.get(),
            "headless": self.headless_var.get(),
            "fields": {field: variable.get() for field, variable in self.field_vars.items()},
        }
        if include_jobs:
            payload["jobs"] = [job.to_dict() for job in self.job_queue]
        return payload

    def _apply_settings(self, settings: dict[str, Any]) -> None:
        mapping = {
            "place_type": self.place_type_var,
            "keyword": self.keyword_var,
            "location": self.location_var,
            "multi_types": self.multi_types_var,
            "multi_locations": self.multi_locations_var,
            "category_preset": self.category_preset_var,
            "location_preset": self.location_preset_var,
            "query_template": self.query_template_var,
            "exclude_keywords": self.exclude_keywords_var,
            "limit": self.limit_var,
            "delay": self.delay_var,
            "scroll_pause": self.scroll_pause_var,
            "timeout": self.timeout_var,
            "workers": self.worker_count_var,
            "output": self.output_var,
            "output_template": self.output_template_var,
            "export_mode": self.export_mode_var,
            "export_format": self.export_format_var,
            "write_mode": self.write_mode_var,
            "split_by": self.split_by_var,
            "dedupe_mode": self.dedupe_mode_var,
        }
        for key, variable in mapping.items():
            if key in settings:
                variable.set(str(settings[key]))
        if "category_preset" in settings:
            self.category_preset_var.set(jobs.resolve_preset_name(str(settings["category_preset"]), CATEGORY_PRESETS))
        if "location_preset" in settings:
            self.location_preset_var.set(jobs.resolve_preset_name(str(settings["location_preset"]), LOCATION_PRESETS))
        if "export_mode" in settings:
            self.export_mode_var.set(label_for_value(EXPORT_MODE_LABELS, export_mode_value(str(settings["export_mode"]))))
        if "export_format" in settings:
            self.export_format_var.set(label_for_value(EXPORT_FORMAT_LABELS, export_format_value(str(settings["export_format"]))))
        if "write_mode" in settings:
            self.write_mode_var.set(label_for_value(WRITE_MODE_LABELS, write_mode_value(str(settings["write_mode"]))))
        if "split_by" in settings:
            self.split_by_var.set(label_for_value(SPLIT_LABELS, split_mode_value(str(settings["split_by"]))))
        if "dedupe_mode" in settings:
            self.dedupe_mode_var.set(label_for_value(DEDUPE_LABELS, dedupe_mode_value(str(settings["dedupe_mode"]))))
        if "resume" in settings:
            self.resume_var.set(bool(settings["resume"]))
        if "headless" in settings:
            self.headless_var.set(bool(settings["headless"]))
        if "all_results" in settings:
            self.all_results_var.set(bool(settings["all_results"]))
        for field, selected in dict(settings.get("fields", {})).items():
            if field in self.field_vars:
                self.field_vars[field].set(bool(selected))

    def _load_settings(self) -> None:
        payload = read_settings_file(SETTINGS_PATH)
        if not payload:
            return
        self._apply_loaded_settings_payload(payload)

    def _apply_loaded_settings_payload(self, payload: dict[str, Any]) -> None:
        self._apply_settings(payload)
        loaded_jobs = []
        for item in payload.get("jobs", []):
            loaded_jobs.append(
                jobs.CrawlJob(
                    place_type=str(item.get("place_type", "")),
                    keyword=str(item.get("keyword", "")),
                    location=str(item.get("location", "")),
                    limit=int(item.get("limit", 50) or 50),
                    output=str(item.get("output", "")),
                    query_template=str(item.get("query_template", jobs.QUERY_TEMPLATE)) or jobs.QUERY_TEMPLATE,
                    status=str(item.get("status", "pending")),
                    done=int(item.get("done", 0) or 0),
                    saved=int(item.get("saved", 0) or 0),
                    failed=int(item.get("failed", 0) or 0),
                    exclude_keywords=jobs.split_multi_value(item.get("exclude_keywords", [])),
                )
            )
        self.job_queue = loaded_jobs

    def _save_settings(self) -> None:
        write_settings_file(SETTINGS_PATH, self._settings_payload())

    def _save_settings_now(self) -> None:
        try:
            self._save_settings()
        except Exception as exc:
            messagebox.showerror("Lưu cấu hình lỗi", str(exc))
            return
        message = f"Đã lưu cấu hình: {SETTINGS_PATH.resolve()}"
        self.settings_status_var.set(f"Đã lưu lúc {datetime.now().strftime('%H:%M:%S')}")
        self._append_log(message, "success")

    def _load_settings_now(self) -> None:
        if not SETTINGS_PATH.exists():
            messagebox.showinfo("Chưa có cấu hình", f"Chưa có file settings: {SETTINGS_PATH.resolve()}")
            return
        payload = read_settings_file(SETTINGS_PATH)
        if not payload:
            messagebox.showwarning("Không tải được cấu hình", "File settings trống hoặc không phải JSON hợp lệ.")
            return
        try:
            self._apply_loaded_settings_payload(payload)
        except Exception as exc:
            messagebox.showerror("Tải cấu hình lỗi", str(exc))
            return
        self._refresh_limit_state()
        self._refresh_query_preview()
        self._refresh_job_tree()
        self.settings_status_var.set(f"Đã tải lúc {datetime.now().strftime('%H:%M:%S')}")
        self._append_log(f"Đã tải cấu hình: {SETTINGS_PATH.resolve()}", "success")

    def _open_settings_folder(self) -> None:
        webbrowser.open(str(SETTINGS_PATH.resolve().parent))

    def _on_close(self) -> None:
        try:
            self._save_settings()
        finally:
            self.root.destroy()


def main() -> None:
    root = tk.Tk()
    GoogleMapsCrawlerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
