from rzn_bot.client import SearchResult, parse_html, parse_json
from rzn_bot.inn import validate_inn
from rzn_bot.__main__ import format_result


def test_inn_valid():
    assert validate_inn("7707083893")[0]      # ПАО Сбербанк
    assert validate_inn("500100732259")[0]    # корректный 12-значный


def test_inn_invalid():
    assert not validate_inn("7707083894")[0]
    assert not validate_inn("123")[0]
    assert not validate_inn("500100732258")[0]


def test_parse_datatables_json():
    payload = {
        "draw": 1, "recordsTotal": 100, "recordsFiltered": 1,
        "data": [{"id": 5, "status": {"label": "Действует"}, "inn": "7707083893",
                  "name": "<a href='#'>ООО &quot;Ромашка&quot;</a>", "number": "Л041-01137-77/00368329"}],
    }
    records, total = parse_json(payload)
    assert total == 1
    assert ("Статус", "Действует") in records[0].fields
    assert ("Наименование", 'ООО "Ромашка"') in records[0].fields
    assert all(label != "id" for label, _ in records[0].fields)


def test_parse_html_table():
    html = "<table><tr><th>ИНН</th><th>Статус</th></tr><tr><td>7707083893</td><td>Действует</td></tr></table>"
    records = parse_html(html)
    assert records[0].fields == [("ИНН", "7707083893"), ("Статус", "Действует")]


def test_format_empty():
    msgs = format_result(SearchResult(inn="7707083893", records=[]))
    assert "не найдено" in msgs[0]
