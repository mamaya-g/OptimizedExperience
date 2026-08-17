from pathlib import Path

from optimized_experience.data.shows import ShowCategoryMap, load_show_category_map

EXAMPLE_CONFIG = Path(__file__).parent.parent / "config" / "show_categories.example.yaml"


def test_load_show_category_map_reads_real_config():
    show_category_map = load_show_category_map(EXAMPLE_CONFIG)
    assert show_category_map.category_for(None, "c60e9de0-df2b-4484-9b05-299939dc247a") == "PARADE"
    assert show_category_map.category_for("fantasmic", "some-entity-id") == "NIGHTTIME_SPECTACULAR"


def test_category_for_prefers_slug_over_entity_id():
    show_category_map = ShowCategoryMap(categories={"fantasmic": "NIGHTTIME_SPECTACULAR", "entity-1": "PARADE"})
    assert show_category_map.category_for("fantasmic", "entity-1") == "NIGHTTIME_SPECTACULAR"


def test_category_for_falls_back_to_entity_id_when_slug_unmapped():
    show_category_map = ShowCategoryMap(categories={"entity-1": "PARADE"})
    assert show_category_map.category_for(None, "entity-1") == "PARADE"
    assert show_category_map.category_for("unmapped-slug", "entity-1") == "PARADE"


def test_category_for_defaults_to_other_when_wholly_unmapped():
    show_category_map = ShowCategoryMap()
    assert show_category_map.category_for("unmapped-slug", "unmapped-id") == "OTHER"
