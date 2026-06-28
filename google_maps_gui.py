#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import queue
import re
import threading
import webbrowser
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
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
    crawler.WRITE_MODE_APPEND: "Append / merge vào file cũ",
}

SPLIT_LABELS = {
    crawler.SPLIT_NONE: "Không tách file",
    crawler.SPLIT_CATEGORY: "Tách theo category",
    crawler.SPLIT_LOCATION: "Tách theo location",
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
    "price_text": "Gia raw",
    "review_count": "So luot danh gia",
    "maps_url": "Link Google Maps",
})


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
        self.export_mode_var = tk.StringVar(value=crawler.EXPORT_MODE_END)
        self.export_format_var = tk.StringVar(value=crawler.EXPORT_FORMAT_CSV)
        self.write_mode_var = tk.StringVar(value=crawler.WRITE_MODE_OVERWRITE)
        self.split_by_var = tk.StringVar(value=crawler.SPLIT_NONE)
        self.dedupe_mode_var = tk.StringVar(value="destination_id")
        self.resume_var = tk.BooleanVar(value=True)
        self.headless_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Sẵn sàng")
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

        notebook.add(job_tab, text="Job Queue")
        notebook.add(config_tab, text="Cấu hình")
        notebook.add(fields_tab, text="Trường dữ liệu")
        notebook.add(preview_tab, text="Preview")
        notebook.add(log_tab, text="Log")

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
            ("Import TXT/CSV", self._import_jobs),
            ("Lưu preset", self._save_preset),
            ("Load preset", self._load_preset),
            ("Retry job lỗi", self._retry_failed_jobs),
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

        self._add_label(parent, "Template query", 2, 0)
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
        ttk.Combobox(parent, textvariable=self.export_format_var, values=list(crawler.EXPORT_FORMATS), state="readonly").grid(row=9, column=1, sticky="ew", padx=(8, 18), pady=5)

        self._add_label(parent, "Chế độ xuất", 9, 2)
        ttk.Combobox(parent, textvariable=self.export_mode_var, values=list(crawler.EXPORT_MODES), state="readonly").grid(row=9, column=3, sticky="ew", padx=(8, 0), pady=5)

        self._add_label(parent, "Ghi file", 10, 0)
        ttk.Combobox(parent, textvariable=self.write_mode_var, values=list(crawler.WRITE_MODES), state="readonly").grid(row=10, column=1, sticky="ew", padx=(8, 18), pady=5)

        self._add_label(parent, "Tách file", 10, 2)
        ttk.Combobox(parent, textvariable=self.split_by_var, values=list(crawler.SPLIT_MODES), state="readonly").grid(row=10, column=3, sticky="ew", padx=(8, 0), pady=5)

        self._add_label(parent, "Dedupe", 11, 0)
        ttk.Combobox(parent, textvariable=self.dedupe_mode_var, values=["destination_id", "name_address", "coordinates"], state="readonly").grid(row=11, column=1, sticky="ew", padx=(8, 18), pady=5)

        flags = ttk.Frame(parent)
        flags.grid(row=11, column=2, columnspan=2, sticky="w", padx=(8, 0), pady=5)
        ttk.Checkbutton(flags, text="Resume từ file/checkpoint", variable=self.resume_var).grid(row=0, column=0, padx=(0, 18))
        ttk.Checkbutton(flags, text="Chạy ẩn Chrome", variable=self.headless_var).grid(row=0, column=1)

        timing = ttk.LabelFrame(parent, text="Delay / timeout / luồng", padding=10)
        timing.grid(row=12, column=0, columnspan=4, sticky="ew", pady=(12, 0))
        for column in range(8):
            timing.columnconfigure(column, weight=1)
        labels = [("Delay nơi", self.delay_var), ("Delay cuộn", self.scroll_pause_var), ("Timeout", self.timeout_var), ("Số luồng", self.worker_count_var)]
        for index, (label, variable) in enumerate(labels):
            ttk.Label(timing, text=label).grid(row=0, column=index * 2, sticky="w", padx=(0, 6))
            ttk.Entry(timing, textvariable=variable, width=12).grid(row=0, column=index * 2 + 1, sticky="ew", padx=(0, 12))

        query_frame = ttk.LabelFrame(parent, text="Query preview", padding=10)
        query_frame.grid(row=13, column=0, columnspan=4, sticky="ew", pady=(12, 0))
        query_frame.columnconfigure(0, weight=1)
        self.query_preview = ttk.Label(query_frame, text="", anchor="w")
        self.query_preview.grid(row=0, column=0, sticky="ew")
        for var in (self.place_type_var, self.keyword_var, self.location_var, self.query_template_var):
            var.trace_add("write", lambda *_: self._refresh_query_preview())

        note = ttk.Label(
            parent,
            text="Tool không thêm proxy, stealth hay bypass CAPTCHA. Nếu Google chặn, hãy tăng delay, giảm luồng hoặc dùng Places API chính thức.",
            wraplength=980,
        )
        note.grid(row=14, column=0, columnspan=4, sticky="ew", pady=(14, 0))

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
        ttk.Label(filters, text="District").grid(row=0, column=4, sticky="w")
        ttk.Entry(filters, textvariable=self.district_filter_var).grid(row=0, column=5, sticky="ew", padx=(6, 12))
        ttk.Label(filters, text="Sort").grid(row=0, column=6, sticky="w")
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

    def _build_footer(self, parent: ttk.Frame) -> None:
        footer = ttk.Frame(parent)
        footer.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        footer.columnconfigure(8, weight=1)
        self.start_button = ttk.Button(footer, text="Start Queue", command=self._start)
        self.start_button.grid(row=0, column=0, padx=(0, 8))
        ttk.Button(footer, text="Test crawl 1 dòng", command=self._start_test).grid(row=0, column=1, padx=(0, 8))
        self.pause_button = ttk.Button(footer, text="Pause", command=self._pause, state="disabled")
        self.pause_button.grid(row=0, column=2, padx=(0, 8))
        self.resume_button = ttk.Button(footer, text="Resume", command=self._resume, state="disabled")
        self.resume_button.grid(row=0, column=3, padx=(0, 8))
        self.stop_button = ttk.Button(footer, text="Stop", command=self._stop, state="disabled")
        self.stop_button.grid(row=0, column=4, padx=(0, 8))
        ttk.Button(footer, text="Mở file", command=self._open_output_file).grid(row=0, column=5, padx=(0, 8))
        ttk.Button(footer, text="Mở thư mục", command=self._open_output_folder).grid(row=0, column=6, padx=(0, 12))
        ttk.Progressbar(footer, variable=self.progress_value_var, maximum=100, length=180).grid(row=0, column=7, padx=(0, 8))
        ttk.Label(footer, textvariable=self.progress_text_var).grid(row=0, column=8, sticky="w")
        ttk.Label(footer, textvariable=self.status_var, anchor="e").grid(row=0, column=9, sticky="e")

    def _add_label(self, parent: ttk.Frame, text: str, row: int, column: int) -> None:
        ttk.Label(parent, text=text).grid(row=row, column=column, sticky="w", pady=5)

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
        if preset in CATEGORY_PRESETS:
            self.multi_types_var.set(", ".join(CATEGORY_PRESETS[preset]))
            self.place_type_var.set(CATEGORY_PRESETS[preset][0])

    def _apply_location_preset(self) -> None:
        locations = jobs.locations_for_preset(self.location_preset_var.get(), self.multi_locations_var.get())
        if locations:
            self.multi_locations_var.set(", ".join(locations))
            self.location_var.set(locations[0])
            self._append_log(f"Đã áp dụng vùng {self.location_preset_var.get()}: {len(locations)} vị trí.", "info")

    def _refresh_query_preview(self) -> None:
        query = build_query(self.place_type_var.get(), self.keyword_var.get(), self.location_var.get(), self.query_template_var.get())
        self.query_preview.configure(text=query or "Nhập ít nhất một loại, từ khóa hoặc vị trí.")

    def _choose_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Chọn file output",
            initialfile=Path(self.output_var.get()).name,
            defaultextension=".csv",
            filetypes=[("All supported", "*.csv *.jsonl *.sqlite *.xlsx"), ("All files", "*.*")],
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

    def _add_single_job(self) -> None:
        try:
            self.job_queue.append(self._single_job_from_config())
            self._refresh_job_tree()
        except ValueError as exc:
            messagebox.showerror("Cấu hình chưa hợp lệ", str(exc))

    def _generate_jobs(self) -> None:
        try:
            generated = build_jobs_from_inputs(
                place_types=self.multi_types_var.get() or self.place_type_var.get(),
                keywords=self.keyword_var.get(),
                locations=self.multi_locations_var.get() or self.location_var.get(),
                limit=parse_limit_for_mode(self.limit_var.get(), "Số lượng", self.all_results_var.get()),
                query_template=self.query_template_var.get(),
                output_template=self.output_template_var.get(),
                export_format=self.export_format_var.get(),
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
        path = filedialog.askopenfilename(title="Import jobs", filetypes=[("Job files", "*.txt *.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            imported = jobs.import_jobs(Path(path))
        except Exception as exc:
            messagebox.showerror("Import lỗi", str(exc))
            return
        self.job_queue.extend(imported)
        self._refresh_job_tree()
        self._append_log(f"Imported {len(imported)} job từ {path}", "success")

    def _save_preset(self) -> None:
        path = filedialog.asksaveasfilename(title="Lưu preset", defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        jobs.save_preset(Path(path), self.job_queue, settings=self._settings_payload(include_jobs=False))
        self._append_log(f"Đã lưu preset: {path}", "success")

    def _load_preset(self) -> None:
        path = filedialog.askopenfilename(title="Load preset", filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            loaded_jobs, settings = jobs.load_preset(Path(path))
        except Exception as exc:
            messagebox.showerror("Load preset lỗi", str(exc))
            return
        self.job_queue = loaded_jobs
        self._apply_settings(settings)
        self._refresh_job_tree()
        self._append_log(f"Đã load preset: {path}", "success")

    def _retry_failed_jobs(self) -> None:
        retried = 0
        for job in self.job_queue:
            if job.status == "error":
                job.status = "pending"
                job.failed = 0
                retried += 1
        self._refresh_job_tree()
        self._append_log(f"Đã đưa {retried} job lỗi về pending.", "warning")

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
                values=(job.status, job.query, format_job_limit(job.limit), job.output, job.saved, job.failed),
            )

    def _read_base_options(self, job: jobs.CrawlJob) -> crawler.CrawlOptions:
        output = Path(job.output or self.output_var.get() or default_output_path(export_format=self.export_format_var.get()))
        return crawler.CrawlOptions(
            query=job.query,
            limit=job.limit,
            out=output,
            delay=parse_non_negative_float(self.delay_var.get(), "Delay mỗi nơi"),
            scroll_pause=parse_non_negative_float(self.scroll_pause_var.get(), "Delay cuộn"),
            timeout=parse_non_negative_float(self.timeout_var.get(), "Timeout"),
            headless=self.headless_var.get(),
            max_workers=normalize_worker_count(self.worker_count_var.get()),
            output_fields=self._selected_fields(),
            export_mode=self.export_mode_var.get(),
            export_format=self.export_format_var.get(),
            write_mode=self.write_mode_var.get(),
            split_by=self.split_by_var.get(),
            job_location=job.location,
            resume_from_existing=self.resume_var.get(),
            dedupe_mode=self.dedupe_mode_var.get(),
            exclude_keywords=job.exclude_keywords or jobs.split_multi_value(self.exclude_keywords_var.get()),
        )

    def _start(self) -> None:
        self._start_jobs(test_one=False)

    def _start_test(self) -> None:
        self._start_jobs(test_one=True)

    def _start_jobs(self, test_one: bool) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("Đang chạy", "Crawler vẫn đang chạy.")
            return
        try:
            crawl_jobs = [self._single_job_from_config(limit_override=1)] if test_one else (self.job_queue[:] or [self._single_job_from_config()])
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
        self._append_log("Đã yêu cầu pause. Crawler sẽ dừng giữa các địa điểm.", "warning")
        self.pause_button.configure(state="disabled")
        self.resume_button.configure(state="normal")

    def _resume(self) -> None:
        self.pause_event.clear()
        self.status_var.set("Đang chạy")
        self._append_log("Đã resume.", "success")
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
                self.log_queue.put(("log", (f"Job {index}/{len(job_options)}: {options.query}", "info")))
                self.log_queue.put(("log", (f"Output: {options.out}", "info")))
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
            "export_mode": self.export_mode_var.get(),
            "export_format": self.export_format_var.get(),
            "write_mode": self.write_mode_var.get(),
            "split_by": self.split_by_var.get(),
            "dedupe_mode": self.dedupe_mode_var.get(),
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
        if not SETTINGS_PATH.exists():
            return
        try:
            payload = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return
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
        SETTINGS_PATH.write_text(json.dumps(self._settings_payload(), ensure_ascii=False, indent=2), encoding="utf-8")

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
