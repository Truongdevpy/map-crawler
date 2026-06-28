import unittest
from datetime import datetime
from pathlib import Path

import google_maps_gui as gui


def make_place(**overrides):
    data = {
        "name": "A",
        "normalized_name": "a",
        "category": "khách sạn",
        "destination_id": "a1",
        "address": "Đà Nẵng",
        "province": "Đà Nẵng",
        "district": "Hải Châu",
        "ward": "",
        "description": "",
        "price_min": 100000,
        "price_max": 200000,
        "price_text": "100.000-200.000 VND",
        "rating": 4.5,
        "review_count": 123,
        "latitude": 16.1,
        "longitude": 108.2,
        "image_url": "",
        "maps_url": "https://www.google.com/maps/place/a",
        "phone": "",
        "website": "",
        "open_hours": "",
        "estimated_duration_minutes": "",
        "suitable_time": "",
        "tags": "",
        "source_count": 1,
        "confidence_score": 0.8,
        "created_at": "2026-06-28T00:00:00Z",
        "updated_at": "2026-06-28T00:00:00Z",
    }
    data.update(overrides)
    return gui.crawler.Place(**data)


class GoogleMapsGuiConfigTests(unittest.TestCase):
    def test_build_query_joins_type_keyword_and_location(self):
        self.assertEqual(
            gui.build_query("khách sạn", "view biển", "Đà Nẵng"),
            "khách sạn view biển Đà Nẵng",
        )
        self.assertEqual(gui.build_query("nhà hàng", "", "Quận 1"), "nhà hàng Quận 1")
        self.assertEqual(gui.build_query("cửa hàng đồ cổ", "", "Hội An"), "cửa hàng đồ cổ Hội An")

    def test_build_query_accepts_template(self):
        self.assertEqual(
            gui.build_query("khách sạn", "view biển", "Đà Nẵng", "{keyword} {type} gần {location}"),
            "view biển khách sạn gần Đà Nẵng",
        )

    def test_place_type_label_mentions_manual_typing(self):
        self.assertIn("gõ tay", gui.PLACE_TYPE_LABEL.lower())

    def test_normalize_worker_count_clamps_to_safe_range(self):
        self.assertEqual(gui.normalize_worker_count("0"), 1)
        self.assertEqual(gui.normalize_worker_count("2"), 2)
        self.assertEqual(gui.normalize_worker_count("10"), 3)
        self.assertEqual(gui.normalize_worker_count("abc"), 1)

    def test_default_output_path_uses_timestamp(self):
        now = datetime(2026, 6, 28, 17, 30, 45)
        self.assertEqual(
            gui.default_output_path(now),
            Path("data/google_maps_20260628_173045.csv"),
        )

    def test_parse_limit_for_all_results_ignores_number_field(self):
        self.assertEqual(gui.parse_limit_for_mode("abc", "Số lượng", all_results=True), 0)
        self.assertEqual(gui.parse_limit_for_mode("12", "Số lượng", all_results=False), 12)
        self.assertEqual(gui.format_job_limit(0), "ALL")

    def test_selected_fields_keeps_schema_order(self):
        values = {
            "rating": True,
            "name": True,
            "address": False,
            "latitude": True,
        }
        self.assertEqual(gui.selected_fields_from_values(values), ["name", "rating", "latitude"])

    def test_selected_fields_defaults_to_full_schema_when_empty(self):
        self.assertEqual(gui.selected_fields_from_values({"name": False}), gui.crawler.SCHEMA_FIELDS)

    def test_export_mode_labels_expose_live_and_end_modes(self):
        self.assertEqual(gui.EXPORT_MODE_LABELS[gui.crawler.EXPORT_MODE_END], "Ghi file khi cào xong")
        self.assertEqual(gui.EXPORT_MODE_LABELS[gui.crawler.EXPORT_MODE_LIVE], "Ghi từng dòng trong lúc cào")

    def test_place_types_include_more_travel_and_local_business_categories(self):
        expected = {
            "resort",
            "homestay",
            "bãi biển",
            "bảo tàng",
            "công viên",
            "chợ",
            "trung tâm thương mại",
            "siêu thị",
            "phòng khám",
            "trạm xăng",
            "sân bay",
            "bến xe",
        }
        self.assertTrue(expected.issubset(set(gui.PLACE_TYPES)))

    def test_category_presets_are_exposed_to_gui(self):
        self.assertIn("Du lich", gui.CATEGORY_PRESETS)
        self.assertIn("An uong", gui.CATEGORY_PRESETS)

    def test_location_presets_are_exposed_to_gui(self):
        self.assertIn("Toan quoc", gui.LOCATION_PRESETS)
        self.assertEqual(len(gui.LOCATION_PRESETS["Toan quoc"]), 34)

    def test_build_jobs_from_inputs_cross_joins_for_queue(self):
        generated = gui.build_jobs_from_inputs(
            place_types="khách sạn, resort",
            keywords="view biển",
            locations="Đà Nẵng, Hội An",
            limit=10,
            query_template="{type} {keyword} {location}",
            output_template="data/{type}_{location}_{date}.csv",
        )

        self.assertEqual(len(generated), 4)
        self.assertEqual(generated[0].query, "khách sạn view biển Đà Nẵng")
        self.assertTrue(generated[0].output.endswith(".csv"))

    def test_build_jobs_from_inputs_expands_location_preset(self):
        generated = gui.build_jobs_from_inputs(
            place_types="khach san",
            keywords="",
            locations="",
            limit=5,
            query_template="{type} {location}",
            output_template="data/{type}_{location}_{date}.csv",
            location_preset="Toan quoc",
        )

        self.assertEqual(len(generated), 34)
        self.assertEqual(generated[0].limit, 5)
        self.assertIn("Hà Nội", [job.location for job in generated])
        self.assertEqual(len({job.output for job in generated}), 34)

    def test_build_jobs_from_inputs_supports_all_results_mode(self):
        generated = gui.build_jobs_from_inputs(
            place_types="khach san",
            keywords="",
            locations="Cau Giay",
            limit=0,
            query_template="{type} {location}",
            all_results=True,
        )

        self.assertEqual(generated[0].limit, 0)

    def test_filter_and_sort_places_for_preview(self):
        places = [
            make_place(name="A", rating=4.8, price_min=200000, district="Hải Châu"),
            make_place(name="B", rating=3.9, price_min=100000, district="Sơn Trà"),
            make_place(name="C", rating=4.6, price_min=50000, district="Hải Châu"),
        ]

        filtered = gui.filter_places(places, rating_min="4.5", price_max="250000", district="hải")
        sorted_rows = gui.sort_places(filtered, "price_min", descending=False)

        self.assertEqual([place.name for place in sorted_rows], ["C", "A"])


if __name__ == "__main__":
    unittest.main()
