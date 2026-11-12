"""Клиент реестра лицензий Росздравнадзора (roszdravnadzor.gov.ru/services/licenses).

Формат ответа сайта не документирован и может меняться, поэтому разбор сделан
«терпимым»: поддерживается JSON (в т.ч. в формате DataTables) и HTML-таблица.
"""
from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx
from bs4 import BeautifulSoup

PAGE_URL = "https://roszdravnadzor.gov.ru/services/licenses"

# Подписи для известных (или ожидаемых) ключей ответа.
KNOWN_LABELS = {
    "status": "Статус",
    "lic_status": "Статус",
    "number": "Номер лицензии",
    "num": "Номер лицензии",
    "lic_num": "Номер лицензии",
    "reg_num": "Рег. номер",
    "date": "Дата",
    "lic_date": "Дата выдачи",
    "date_start": "Дата выдачи",
    "date_end": "Дата окончания",
    "name": "Наименование",
    "org_name": "Наименование",
    "full_name": "Наименование",
    "inn": "ИНН",
    "ogrn": "ОГРН",
    "address": "Адрес",
    "addr": "Адрес",
    "activity": "Вид деятельности",
    "lic_type": "Вид деятельности",
    "licensor": "Лицензирующий орган",
    "region": "Регион",
}
SKIP_KEYS = {"id", "DT_RowId", "DT_RowClass", "DT_RowData", "url", "link"}


class RznError(Exception):
    """Ошибка обращения к сайту Росздравнадзора."""


@dataclass
class LicenseRecord:
    fields: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class SearchResult:
    inn: str
    records: list[LicenseRecord]
    total: int | None = None
    source_url: str = PAGE_URL


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("label", "title", "text", "value", "name"):
            if key in value and value[key] not in (None, ""):
                return _clean(value[key])
        return "; ".join(filter(None, (_clean(v) for v in value.values())))
    if isinstance(value, list):
        return "; ".join(filter(None, (_clean(v) for v in value)))
    text = str(value)
    if "<" in text and ">" in text:
        text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _label(key: str) -> str:
    return KNOWN_LABELS.get(key, KNOWN_LABELS.get(key.lower(), key))


def _find_rows(payload: Any) -> tuple[list[Any], int | None]:
    if isinstance(payload, list):
        return payload, None
    if not isinstance(payload, dict):
        return [], None
    total = None
    for key in ("recordsFiltered", "recordsTotal", "total", "count"):
        if isinstance(payload.get(key), (int, str)) and str(payload[key]).isdigit():
            total = int(payload[key])
            break
    for key in ("data", "items", "rows", "result", "results", "list"):
        value = payload.get(key)
        if isinstance(value, list):
            return value, total
        if isinstance(value, dict):
            rows, inner_total = _find_rows(value)
            if rows:
                return rows, total if total is not None else inner_total
    return [], total


def parse_json(payload: Any, headers: list[str] | None = None) -> tuple[list[LicenseRecord], int | None]:
    rows, total = _find_rows(payload)
    records = []
    for row in rows:
        rec = LicenseRecord()
        if isinstance(row, dict):
            for key, value in row.items():
                if key in SKIP_KEYS:
                    continue
                text = _clean(value)
                if text:
                    rec.fields.append((_label(str(key)), text))
        elif isinstance(row, list):
            for i, value in enumerate(row):
                text = _clean(value)
                if text:
                    label = headers[i] if headers and i < len(headers) else f"Поле {i + 1}"
                    rec.fields.append((label, text))
        else:
            text = _clean(row)
            if text:
                rec.fields.append(("Запись", text))
        if rec.fields:
            records.append(rec)
    return records, total


def parse_html(text: str) -> list[LicenseRecord]:
    soup = BeautifulSoup(text, "html.parser")
    records = []
    for table in soup.find_all("table"):
        headers = [th.get_text(" ", strip=True) for th in table.find_all("th")]
        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if not cells:
                continue
            rec = LicenseRecord()
            for i, td in enumerate(cells):
                value = re.sub(r"\s+", " ", td.get_text(" ", strip=True))
                if value:
                    label = headers[i] if i < len(headers) else f"Поле {i + 1}"
                    rec.fields.append((label, value))
            if rec.fields:
                records.append(rec)
    return records


class RznClient:
    def __init__(
        self,
        search_url: str,
        inn_param: str = "q_inn",
        method: str = "POST",
        verify: bool | str = True,
        timeout: float = 30.0,
        page_size: int = 50,
    ) -> None:
        self.search_url = search_url
        self.inn_param = inn_param
        self.method = method.upper()
        self.page_size = page_size
        self._http = httpx.AsyncClient(
            verify=verify,
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; RznInnBot/1.0)",
                "Accept": "application/json, text/javascript, text/html, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": PAGE_URL,
            },
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def search_by_inn(self, inn: str) -> SearchResult:
        params = {
            "draw": "1",
            "start": "0",
            "length": str(self.page_size),
            self.inn_param: inn,
        }
        try:
            if self.method == "GET":
                resp = await self._http.get(self.search_url, params=params)
            else:
                resp = await self._http.post(self.search_url, data=params)
        except httpx.HTTPError as exc:
            raise RznError(f"Сайт Росздравнадзора недоступен: {exc}") from exc
        if resp.status_code >= 400:
            raise RznError(f"Сайт Росздравнадзора вернул ошибку HTTP {resp.status_code}")

        body = resp.text.strip()
        try:
            payload = json.loads(body) if body else []
        except json.JSONDecodeError:
            records, total = parse_html(body), None
        else:
            records, total = parse_json(payload)

        # Если сервер проигнорировал фильтр, оставляем только записи с нужным ИНН.
        with_inn = [r for r in records if any(inn in v for _, v in r.fields)]
        if with_inn or any(lbl == "ИНН" for r in records for lbl, _ in r.fields):
            records = with_inn
        return SearchResult(inn=inn, records=records, total=total if records else 0)
