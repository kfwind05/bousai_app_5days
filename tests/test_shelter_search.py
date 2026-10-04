import unittest
from unittest.mock import patch

import app as shelter_app


class ShelterSearchTests(unittest.TestCase):
    def setUp(self):
        self.shelters = [
            {
                "id": 1,
                "name": "洪水対応避難所",
                "disaster_types": ["洪水", "地震"],
                "pets_allowed": True,
                "barrier_free": True,
                "district": "中央地区",
            },
            {"id": 2, "name": "未設定避難所", "district": "中央地区"},
            {
                "id": 3,
                "name": "津波対応避難所",
                "disaster_types": ["津波"],
                "pets_allowed": True,
                "district": "海岸地区",
            },
        ]
        self.shelters_patch = patch.object(shelter_app, "shelters", self.shelters)
        self.save_patch = patch.object(shelter_app, "save_shelters")
        self.shelters_patch.start()
        self.save_shelters = self.save_patch.start()
        self.client = shelter_app.app.test_client()

        with self.client.session_transaction() as session:
            session["logged_in"] = True

    def tearDown(self):
        self.save_patch.stop()
        self.shelters_patch.stop()

    def test_search_page_lists_disaster_types(self):
        response = self.client.get("/shelter_search")

        self.assertEqual(response.status_code, 200)
        self.assertIn("津波".encode(), response.data)
        self.assertIn("土砂災害".encode(), response.data)
        self.assertIn("洪水".encode(), response.data)
        self.assertIn('name="pets_allowed"'.encode(), response.data)
        self.assertIn('name="barrier_free"'.encode(), response.data)
        self.assertIn("条件をクリア".encode(), response.data)
        self.assertIn("中央地区".encode(), response.data)
        self.assertIn("海岸地区".encode(), response.data)

    def test_search_results_include_only_matching_configured_shelters(self):
        response = self.client.get("/search_results?disaster_type=洪水")

        self.assertEqual(response.status_code, 200)
        self.assertIn("洪水対応避難所".encode(), response.data)
        self.assertNotIn("未設定避難所".encode(), response.data)
        self.assertNotIn("津波対応避難所".encode(), response.data)

    def test_register_saves_selected_disaster_types(self):
        response = self.client.post(
            "/shelter_register",
            data={
                "action": "register",
                "name": "新しい避難所",
                "district": "東地区",
                "disaster_types": ["洪水", "不正な種別"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.shelters[-1]["disaster_types"],
            ["洪水"],
        )
        self.assertEqual(self.shelters[-1]["district"], "東地区")
        self.save_shelters.assert_called_once()

    def test_existing_shelter_disaster_types_can_be_updated(self):
        response = self.client.post(
            "/shelter_register",
            data={
                "action": "update",
                "shelter_id": "2",
                "district": "西地区",
                "disaster_types": ["津波"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.shelters[1]["disaster_types"], ["津波"])
        self.assertEqual(self.shelters[1]["district"], "西地区")
        self.save_shelters.assert_called_once()

    def test_shelters_api_filters_by_disaster_type(self):
        response = self.client.get("/shelters?disaster_type=洪水")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [shelter["name"] for shelter in response.get_json()],
            ["洪水対応避難所"],
        )

    def test_shelters_api_rejects_unknown_disaster_type(self):
        response = self.client.get("/shelters?disaster_type=不正")

        self.assertEqual(response.status_code, 400)

    def test_search_results_require_all_selected_equipment_conditions(self):
        response = self.client.get(
            "/search_results?disaster_type=洪水&pets_allowed=true&barrier_free=true"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("洪水対応避難所".encode(), response.data)
        self.assertNotIn("未設定避難所".encode(), response.data)
        self.assertNotIn("津波対応避難所".encode(), response.data)

    def test_unconfigured_equipment_is_excluded_from_matching_results(self):
        response = self.client.get("/search_results?disaster_type=洪水&pets_allowed=true")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("未設定避難所".encode(), response.data)

    def test_shelters_api_filters_by_equipment(self):
        response = self.client.get("/shelters?pets_allowed=true&barrier_free=true")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [shelter["name"] for shelter in response.get_json()],
            ["洪水対応避難所"],
        )

    def test_shelters_api_rejects_invalid_equipment_filter(self):
        response = self.client.get("/shelters?pets_allowed=yes")

        self.assertEqual(response.status_code, 400)

    def test_search_can_match_shelter_name_without_knowing_district(self):
        response = self.client.get(
            "/search_results?keyword=津波対応&disaster_type=津波"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("津波対応避難所".encode(), response.data)
        self.assertNotIn("洪水対応避難所".encode(), response.data)

    def test_search_combines_district_and_keyword(self):
        response = self.client.get(
            "/search_results?district=中央地区&keyword=洪水&disaster_type=洪水"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("洪水対応避難所".encode(), response.data)
        self.assertNotIn("未設定避難所".encode(), response.data)

    def test_shelters_api_can_filter_by_name_keyword(self):
        response = self.client.get("/shelters?keyword=津波")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [shelter["name"] for shelter in response.get_json()],
            ["津波対応避難所"],
        )

    def test_empty_district_is_treated_as_no_district_filter(self):
        response = self.client.get("/search_results?district=&keyword=洪水")

        self.assertEqual(response.status_code, 200)
        self.assertIn("洪水対応避難所".encode(), response.data)


if __name__ == "__main__":
    unittest.main()
