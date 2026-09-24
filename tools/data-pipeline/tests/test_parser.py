from pathlib import Path

from mmwiki_data.parser import extract_page

FIXTURE = Path(__file__).parent / "fixtures" / "mm2r-table.html"


def test_extract_page_preserves_source_fields() -> None:
    result = extract_page(FIXTURE.read_bytes())

    assert result.title == "MM2R战车装备"
    assert len(result.tables) == 1
    assert result.tables[0].section == "主炮"
    assert result.tables[0].headers == ["汉译", "名称", "攻击"]
    assert result.tables[0].rows == [{"汉译": "生锈大炮", "名称": "さびた大砲", "攻击": "150"}]


def test_extract_page_limits_context_and_discards_html() -> None:
    result = extract_page(FIXTURE.read_bytes())

    assert all(len(excerpt) <= 300 for excerpt in result.excerpts)
    assert not hasattr(result, "body")
    assert not hasattr(result, "html")


def test_extract_page_warns_about_malformed_rows() -> None:
    result = extract_page(
        b"<h1>Page</h1><h2>Table</h2><table>"
        b"<tr><th>A</th><th>B</th></tr><tr><td>only one</td></tr></table>"
    )

    assert result.tables[0].rows == []
    assert result.warnings == ["Table: skipped row 2 because it has 1 cells, expected 2"]


def test_extract_page_preserves_colspan_without_inventing_values() -> None:
    result = extract_page(
        b"<h1>Page</h1><h2>Table</h2><table>"
        b"<tr><th>Name</th><th>Price</th><th>Rarity</th></tr>"
        b'<tr><td>Cannon</td><td colspan="2">4000</td></tr></table>'
    )

    assert result.tables[0].rows == [{"Name": "Cannon", "Price": "4000", "Rarity": ""}]
    assert result.tables[0].merged_cells[0].model_dump() == {
        "row_index": 2,
        "start_header": "Price",
        "end_header": "Rarity",
        "value": "4000",
    }
