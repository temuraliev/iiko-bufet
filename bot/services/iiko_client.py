"""iiko API client — поиск по номенклатуре и создание поставок iikoServer API."""
import hashlib
import logging
import re
from datetime import datetime
from xml.etree import ElementTree as ET
from xml.etree.ElementTree import Element, SubElement, tostring

from rapidfuzz import fuzz

import httpx

from config import (
    IIKO_DEFAULT_COUNTERAGENT_ID,
    IIKO_DEFAULT_STORE_ID,
    IIKO_SERVER_LOGIN,
    IIKO_SERVER_PASSWORD,
    IIKO_SERVER_URL,
    get_warehouses_config,
)

logger = logging.getLogger(__name__)


class ProductGroupError(ValueError):
    """Ошибка: в поставку попала группа (категория), а не конкретный товар."""


class IikoClient:
    """Клиент iikoServer API (полная номенклатура, включая GOODS)."""

    def __init__(self):
        self.server_url = IIKO_SERVER_URL
        self.login = IIKO_SERVER_LOGIN
        self.password = IIKO_SERVER_PASSWORD
        self._token: str | None = None
        self._products: list[dict] | None = None
        self._use_stub = not (self.server_url and self.login and self.password)

    # Типы, которые являются группами (категориями), а не товарами для поставки
    _PRODUCT_GROUP_TYPES = {"products", "productgroup"}

    # Папки, которые полностью игнорируем при поиске (товары из них не показываются)
    _EXCLUDED_GROUP_NAMES = (
        "yandex",
        "yandex - корни",
        "кухня",
        "услуги",
        "gonzo gaming - нетка",
        "gonzo gaming-нетка",
        "корни меню",
    )

    def _is_excluded_group(self, name: str) -> bool:
        """Проверяет, входит ли группа в список исключённых."""
        n = name.lower().strip()
        if n in self._EXCLUDED_GROUP_NAMES:
            return True
        if "yandex" in n:
            return True
        if "gonzo gaming" in n and "нетка" in n:
            return True
        return False

    def _build_excluded_ids(self, all_items: dict) -> set[str]:
        """Строит множество ID (групп и их потомков), которые исключаем из поиска."""
        excluded_group_ids = {
            iid
            for iid, data in all_items.items()
            if (
                not data.get("productType")
                or data.get("productType", "").lower() in self._PRODUCT_GROUP_TYPES
            )
            and self._is_excluded_group(data.get("name", ""))
        }
        excluded = set(excluded_group_ids)
        for _ in range(20):
            added = 0
            for iid, data in all_items.items():
                if iid in excluded:
                    continue
                parent = data.get("parentId", "")
                if parent and parent in excluded:
                    excluded.add(iid)
                    added += 1
            if not added:
                break
        return excluded

    def _parse_products_xml(self, xml_text: str) -> list[dict]:
        """Парсит XML от /resto/api/products в список продуктов.
        Исключает ProductGroup и товары из папок Yandex, Кухня, Услуги, Gonzo Gaming-нетка, Корни меню.
        """
        root = ET.fromstring(xml_text)
        all_items = {}
        for product in root.findall(".//productDto"):
            prod_id = (product.findtext("id") or "").strip()
            parent_id = (product.findtext("parentId") or "").strip()
            name = (product.findtext("name") or "").strip()
            product_type_raw = (product.findtext("productType") or "").strip()
            all_items[prod_id] = {
                "name": name,
                "parentId": parent_id,
                "productType": product_type_raw,
            }

        excluded_ids = self._build_excluded_ids(all_items)

        products = []
        for product in root.findall(".//productDto"):
            prod_id = (product.findtext("id") or "").strip()
            name = (product.findtext("name") or "").strip()
            if not name:
                continue
            product_type_raw = (product.findtext("productType") or "").strip()
            if product_type_raw.lower() in self._PRODUCT_GROUP_TYPES:
                continue
            if prod_id in excluded_ids:
                continue
            num = (product.findtext("num") or "").strip()
            code = (product.findtext("code") or "").strip()
            product_code = num or code or ""
            products.append({
                "id": prod_id,
                "name": name,
                "productCode": product_code,
                "number": product_code,
                "productType": product_type_raw,
                "mainUnit": (product.findtext("mainUnit") or "").strip(),
            })
        return products

    async def get_token(self) -> str:
        """Получение токена iikoServer API (auth)."""
        if self._token:
            return self._token
        pass_hash = hashlib.sha1(self.password.encode()).hexdigest()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self.server_url}/resto/api/auth",
                params={"login": self.login, "pass": pass_hash},
            )
            resp.raise_for_status()
            self._token = resp.text.strip()
            return self._token

    async def get_products(self) -> list[dict]:
        """Загружает номенклатуру с iikoServer API."""
        if self._products is not None:
            return self._products
        if self._use_stub:
            return []

        token = await self.get_token()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{self.server_url}/resto/api/products",
                params={"key": token, "revisionFrom": -1},
            )
            resp.raise_for_status()
            self._products = self._parse_products_xml(resp.text)
            return self._products

    _SKIP_WORDS = {"для", "или", "и", "в", "на", "с", "по", "из", "от", "до", "без"}

    # Словарь опечаток из PDF → правильное написание для поиска
    _TYPO_MAP = {
        "авакадо": "авокадо",
        "нохот": "нори",
        "мачёный": "маринованный",
    }

    def _normalize_query(self, query: str) -> str:
        """Применяет словарь опечаток к запросу."""
        q = query.lower().strip()
        for typo, correct in self._TYPO_MAP.items():
            q = re.sub(rf"\b{re.escape(typo)}\b", correct, q)
        return q

    def _tokenize_query(self, query: str) -> list[str]:
        """Разбивает запрос на слова по пробелам, /, -, скобкам."""
        parts = re.split(r"[\s/\-\(\)]+", query.lower())
        return [w for w in parts if len(w) >= 3 and w not in self._SKIP_WORDS]

    def _count_keyword_matches(self, query: str, name: str) -> int:
        """Сколько значимых слов из запроса есть в названии iiko."""
        words = self._tokenize_query(query)
        if not words:
            return 0
        name_lower = name.lower()
        count = 0
        for w in words:
            if w in name_lower:
                count += 1
            elif len(w) >= 5 and w[:5] in name_lower:
                count += 1
            elif len(w) >= 6 and w[:6] in name_lower:
                count += 1
        return count

    def _query_any_word_in_name(self, query: str, name: str) -> bool:
        """Хотя бы одно значимое слово запроса должно быть в названии."""
        words = self._tokenize_query(query)
        if not words:
            return True
        name_lower = name.lower()
        for w in words:
            if w in name_lower or (len(w) >= 5 and w[:5] in name_lower):
                return True
        return False

    def _search_in_products(
        self, products: list, query_lower: str, limit: int, min_score: int
    ) -> list[dict]:
        """Поиск среди списка продуктов."""
        matches = []
        for p in products:
            name = (p.get("name") or "").lower()
            code = (p.get("productCode") or p.get("number") or "").lower()
            score = max(
                fuzz.ratio(query_lower, name),
                fuzz.ratio(query_lower, code),
                fuzz.partial_ratio(query_lower, name),
                fuzz.token_set_ratio(query_lower, name),
                fuzz.token_sort_ratio(query_lower, name),
            )
            if code and query_lower == code:
                score = 100
            elif name == query_lower or name.startswith(query_lower + " ") or name.endswith(" " + query_lower):
                score = max(score, 95)  # Бонус за точное совпадение
            elif score <= 35:
                continue
            name_str = p.get("name") or ""
            if not self._query_any_word_in_name(query_lower, name_str):
                continue
            cnt = self._count_keyword_matches(query_lower, name_str)
            words = self._tokenize_query(query_lower)
            min_matches = min(2, len(words)) if len(words) >= 2 else 1
            if cnt < min_matches:
                continue

            matches.append({
                "id": p.get("id", ""),
                "name": p.get("name", ""),
                "productCode": p.get("productCode") or p.get("number", ""),
                "_score": score,
            })

        # Сортировка: сначала по score, при равном — по длине названия (короче лучше)
        matches.sort(key=lambda x: (-x["_score"], len(x["name"])))
        return [m for m in matches[:limit] if m["_score"] >= min_score]

    async def search_product(self, query: str, limit: int = 10, min_score: int = 38) -> list[dict]:
        """
        Поиск продукта по названию или коду.
        Возвращает: [{"id", "name", "productCode"}, ...]
        """
        if self._use_stub:
            return []

        products = await self.get_products()
        query_raw = query.strip()
        if not query_raw:
            return []

        query_lower = self._normalize_query(query_raw)

        # Поиск по коду, если запрос — число (например "00375") или "гранат 00375"
        parts = query_lower.split()
        code_part = next((p for p in parts if p.replace(" ", "").isdigit() and len(p) >= 3), None)
        if code_part:
            code_clean = code_part.replace(" ", "")
            code_matches = [
                p for p in products
                if (p.get("productCode") or p.get("number") or "").replace(" ", "") == code_clean
            ]
            if code_matches:
                return [{"id": p["id"], "name": p["name"], "productCode": p.get("productCode") or p.get("number", "")} for p in code_matches[:limit]]

        q_clean = query_lower.replace(" ", "")
        if q_clean.isdigit():
            code_matches = [
                p for p in products
                if (p.get("productCode") or p.get("number") or "").replace(" ", "") == q_clean
            ]
            if code_matches:
                return [{"id": p["id"], "name": p["name"], "productCode": p.get("productCode") or p.get("number", "")} for p in code_matches[:limit]]
            code_partial = [p for p in products if q_clean in ((p.get("productCode") or p.get("number") or "").replace(" ", ""))]
            if code_partial:
                return [{"id": p["id"], "name": p["name"], "productCode": p.get("productCode") or p.get("number", "")} for p in code_partial[:limit]]

        result = self._search_in_products(products, query_lower, limit, min_score)
        words: list[str] = []
        if not result:
            words = self._tokenize_query(query_lower)
            if not words:
                words = [w for w in query_lower.split() if len(w) >= 2]
            if words:
                short_query = " ".join(words[:2]) if len(words) >= 2 else words[0]
                if short_query != query_lower:
                    result = self._search_in_products(products, short_query, limit, min_score)
        if not result and words:
            longest = max(words, key=len)
            if len(longest) >= 4:
                result = self._search_in_products(products, longest, limit, min_score)
        if not result and "масло" in query_lower and "фритюр" in query_lower:
            result = self._search_in_products(products, "масло фритюра", limit, min_score)

        return [{"id": m["id"], "name": m["name"], "productCode": m["productCode"]} for m in result]

    async def get_organizations(self) -> list[dict]:
        """iikoServer API не поддерживает организации."""
        return []

    def _parse_stores_from_xml(self, xml_text: str) -> list[dict]:
        """Парсит corporateItemDto из XML."""
        root = ET.fromstring(xml_text)
        return [
            {"id": (item.findtext("id") or "").strip(), "name": (item.findtext("name") or "").strip()}
            for item in root.findall(".//corporateItemDto")
            if (item.findtext("id") or "").strip()
        ]

    async def _get_stores_and_suppliers_from_invoices(self) -> tuple[list[dict], list[dict]]:
        """
        Извлекает склады и поставщиков из экспорта приходных накладных.
        Работает если в системе есть хотя бы одна приходная накладная.
        """
        if self._use_stub:
            return [], []
        token = await self.get_token()
        # Запрашиваем документы за последний год
        date_to = datetime.now()
        date_from = date_to.replace(year=date_to.year - 1)
        params = {
            "key": token,
            "from": date_from.strftime("%Y-%m-%d"),
            "to": date_to.strftime("%Y-%m-%d"),
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self.server_url}/resto/api/documents/export/incomingInvoice",
                params=params,
            )
            if resp.status_code != 200:
                return [], []
            try:
                root = ET.fromstring(resp.text)
            except ET.ParseError:
                return [], []

        stores_seen: dict[str, str] = {}
        suppliers_seen: dict[str, str] = {}
        for doc in root.findall(".//document"):
            # defaultStore / defaultStoreId — склад (может быть id или элемент с id)
            store_elem = doc.find("defaultStore") or doc.find("defaultStoreId")
            if store_elem is not None:
                store_id = (store_elem.text or store_elem.get("id") or (store_elem.findtext("id") or "")).strip()
                store_name = (store_elem.get("name") or store_elem.findtext("name") or "").strip() or store_id[:8]
                if store_id and len(store_id) > 10:
                    stores_seen[store_id] = store_name
            # supplier / counteragentId — контрагент
            supp_elem = doc.find("supplier") or doc.find("counteragentId") or doc.find("supplierId")
            if supp_elem is not None:
                supp_id = (supp_elem.text or supp_elem.get("id") or (supp_elem.findtext("id") or "")).strip()
                supp_name = (supp_elem.get("name") or supp_elem.findtext("name") or "").strip() or supp_id[:8]
                if supp_id and len(supp_id) > 10:
                    suppliers_seen[supp_id] = supp_name

        stores = [{"id": k, "name": v} for k, v in stores_seen.items()]
        suppliers = [{"id": k, "name": v} for k, v in suppliers_seen.items()]
        return stores, suppliers

    async def get_stores(self) -> list[dict]:
        """
        Получить список складов для выбора.
        Пробует API (departments, corporateItemDto, incomingInvoice), иначе — конфиг из .env или дефолтный.
        """
        if not self._use_stub:
            token = await self.get_token()
            for endpoint in ("/resto/api/departments", "/resto/api/corporateItemDto"):
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(f"{self.server_url}{endpoint}", params={"key": token})
                    if resp.status_code == 200:
                        try:
                            result = self._parse_stores_from_xml(resp.text)
                            if result:
                                return result
                        except ET.ParseError:
                            continue
            stores, _ = await self._get_stores_and_suppliers_from_invoices()
            if stores:
                return stores
        return get_warehouses_config()

    async def get_suppliers(self) -> list[dict]:
        """
        Получить список контрагентов-поставщиков с названиями.
        Пробует: counteragents, employees (supplier=true), corporateItemDto, затем экспорт накладных.
        """
        if self._use_stub:
            return []
        token = await self.get_token()

        # 1. /resto/api/counteragents — если есть
        async with httpx.AsyncClient(timeout=30.0) as client:
            for endpoint in ("/resto/api/counteragents", "/resto/api/entities"):
                try:
                    resp = await client.get(
                        f"{self.server_url}{endpoint}",
                        params={"key": token},
                    )
                    if resp.status_code == 200 and resp.text.strip():
                        suppliers = self._parse_suppliers_xml(resp.text)
                        if suppliers:
                            return suppliers
                except Exception:
                    continue

        # 2. employees с supplier=true (имена есть)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self.server_url}/resto/api/employees",
                params={"key": token},
            )
            if resp.status_code == 200:
                try:
                    root = ET.fromstring(resp.text)
                    suppliers = []
                    for emp in root.findall(".//employee"):
                        if (emp.findtext("supplier") or "").strip().lower() == "true":
                            emp_id = (emp.findtext("id") or "").strip()
                            name = (emp.findtext("name") or "").strip()
                            if emp_id and name:
                                suppliers.append({"id": emp_id, "name": name})
                    if suppliers:
                        return suppliers
                except ET.ParseError:
                    pass

        # 3. corporateItemDto — может содержать контрагентов
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self.server_url}/resto/api/corporateItemDto",
                params={"key": token},
            )
            if resp.status_code == 200:
                suppliers = self._parse_suppliers_from_corporate(resp.text)
                if suppliers:
                    return suppliers

        # 4. Из экспорта накладных (только UUID, без имён — для fallback)
        _, suppliers = await self._get_stores_and_suppliers_from_invoices()
        return suppliers

    def _parse_suppliers_xml(self, xml_text: str) -> list[dict]:
        """Парсит XML со списком контрагентов (counteragent, entity и т.п.)."""
        try:
            root = ET.fromstring(xml_text)
            suppliers = []
            for tag in ("counteragent", "entity", "counteragentDto", "corporateItemDto"):
                for elem in root.findall(f".//{tag}"):
                    eid = (elem.findtext("id") or elem.get("id") or "").strip()
                    name = (elem.findtext("name") or elem.get("name") or "").strip()
                    if eid and len(eid) > 10 and name:
                        suppliers.append({"id": eid, "name": name})
            return suppliers
        except ET.ParseError:
            return []

    def _parse_suppliers_from_corporate(self, xml_text: str) -> list[dict]:
        """Парсит corporateItemDto — выбирает элементы типа контрагент/поставщик."""
        try:
            root = ET.fromstring(xml_text)
            suppliers = []
            for item in root.findall(".//corporateItemDto"):
                eid = (item.findtext("id") or "").strip()
                name = (item.findtext("name") or "").strip()
                item_type = (item.findtext("type") or item.get("type") or "").lower()
                if eid and len(eid) > 10 and name:
                    if "counteragent" in item_type or "supplier" in item_type:
                        suppliers.append({"id": eid, "name": name})
                    elif not item_type:
                        suppliers.append({"id": eid, "name": name})
            return suppliers
        except ET.ParseError:
            return []

    def match_supplier(self, pdf_supplier_name: str | None, suppliers: list[dict]) -> dict | None:
        """
        Сопоставляет название поставщика из PDF с поставщиками в iiko.
        Возвращает {"id", "name"} или None.
        """
        if not pdf_supplier_name or not suppliers:
            return None
        query = pdf_supplier_name.lower().strip()
        if len(query) < 3:
            return None
        best = None
        best_score = 50
        for s in suppliers:
            name = (s.get("name") or "").lower()
            if not name:
                continue
            score = max(
                fuzz.ratio(query, name),
                fuzz.partial_ratio(query, name),
                fuzz.token_set_ratio(query, name),
                fuzz.token_sort_ratio(query, name),
            )
            if score > best_score:
                best_score = score
                best = {"id": s["id"], "name": s["name"]}
        return best

    async def create_supply(
        self,
        items: list[dict],
        *,
        counteragent_id: str | None = None,
        store_id: str | None = None,
        date_incoming: str | None = None,
        comment: str | None = None,
    ) -> dict:
        """
        Создание приходной накладной.
        items: [{"productId": str, "amount": float, "sum": float?, "price": float?}, ...]
        counteragent_id: UUID поставщика (опционально)
        store_id: UUID склада (опционально)
        date_incoming: дата/время в формате YYYY-MM-DDTHH:MM (опционально)
        comment: комментарий к документу (опционально)
        """
        if self._use_stub:
            raise ValueError("iikoServer не настроен. Укажите URL, логин и пароль в .env")

        store_id = store_id or IIKO_DEFAULT_STORE_ID
        counteragent_id = counteragent_id or IIKO_DEFAULT_COUNTERAGENT_ID

        if not store_id:
            stores = await self.get_stores()
            if stores:
                store_id = stores[0]["id"]
            else:
                raise ValueError(
                    "Укажите IIKO_DEFAULT_STORE_ID в .env. "
                    "ID склада можно взять в iiko Office: Подразделения → выберите склад → скопируйте ID (UUID)."
                )

        if not counteragent_id:
            suppliers = await self.get_suppliers()
            if suppliers:
                counteragent_id = suppliers[0]["id"]
            else:
                raise ValueError(
                    "Укажите IIKO_DEFAULT_COUNTERAGENT_ID в .env. "
                    "ID контрагента возьмите в iiko Office: Контрагенты → выберите поставщика → скопируйте ID (UUID)."
                )

        token = await self.get_token()

        # Проверка: все productId должны быть реальными товарами, а не группами (Салаты и т.п.)
        valid_products = await self.get_products()
        valid_ids = {p["id"] for p in valid_products}
        for it in items:
            pid = it.get("productId")
            if pid and pid not in valid_ids:
                raise ProductGroupError(
                    "Один из товаров является группой (категорией, например «Салаты»), "
                    "а не конкретным товаром. Нажмите «Исправить сопоставление» и выберите конкретный товар."
                )

        now = datetime.now()
        date_str = date_incoming or now.strftime("%Y-%m-%dT%H:%M")
        doc_number = f"BOT-{now.strftime('%Y%m%d%H%M%S')}{now.microsecond // 1000:03d}"

        # Собираем XML по схеме incomingInvoice
        doc = Element("document")
        SubElement(doc, "documentNumber").text = doc_number
        SubElement(doc, "dateIncoming").text = date_str
        SubElement(doc, "useDefaultDocumentTime").text = "false" if date_incoming else "true"
        SubElement(doc, "defaultStore").text = store_id
        SubElement(doc, "supplier").text = counteragent_id
        SubElement(doc, "status").text = "UNCONFIRMED"
        if comment:
            SubElement(doc, "comment").text = str(comment)[:500]

        items_elem = SubElement(doc, "items")
        for idx, it in enumerate(items, 1):
            product_id = it.get("productId")
            amount = float(it.get("amount", 0))
            price = float(it.get("price") or (it.get("sum", 0) / amount if amount else 0))
            total_sum = float(it.get("sum") or (amount * price))
            discount = float(it.get("discountSum", 0))

            item_elem = SubElement(items_elem, "item")
            SubElement(item_elem, "num").text = str(idx)
            SubElement(item_elem, "product").text = str(product_id)
            SubElement(item_elem, "store").text = store_id
            SubElement(item_elem, "price").text = f"{price:.4f}"
            SubElement(item_elem, "amount").text = f"{amount:.4f}"
            SubElement(item_elem, "actualAmount").text = f"{amount:.4f}"
            SubElement(item_elem, "sum").text = f"{total_sum:.2f}"
            SubElement(item_elem, "discountSum").text = f"{discount:.2f}"

        xml_body = b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(doc, encoding="unicode").encode("utf-8")

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.server_url}/resto/api/documents/import/incomingInvoice",
                params={"key": token},
                content=xml_body,
                headers={"Content-Type": "application/xml"},
            )
            if resp.status_code == 500:
                body = (resp.text or "").strip()
                # Пытаемся извлечь текст ошибки из HTML или XML
                err_snippet = body[:500] if body else "(пусто)"
                if "<" in err_snippet:
                    err_snippet = re.sub(r"<[^>]+>", " ", err_snippet)[:400]
                err_snippet = " ".join(err_snippet.split())
                logger.error("iiko 500: %s", err_snippet[:300])
                raise ValueError(
                    f"Сервер iiko вернул ошибку 500. Возможные причины: "
                    f"товар не привязан к складу, неверный поставщик для склада, "
                    f"или проблема на стороне iiko. Ответ: {err_snippet or '(пусто)'}"
                )
            if resp.status_code == 409:
                body = resp.text[:500] if resp.text else "(пусто)"
                raise ValueError(
                    f"iiko вернул 409 Conflict. Возможные причины: дубликат номера документа, "
                    f"неверный формат или конфликт данных. Ответ сервера: {body}"
                )
            resp.raise_for_status()
            # iiko может вернуть 200 с errorMessage в теле
            try:
                root = ET.fromstring(resp.text)
            except ET.ParseError:
                raise ValueError(f"iiko вернул не XML: {resp.text[:300]}")

            valid = (root.findtext("valid") or "true").lower() == "true"
            error_msg = (root.findtext("errorMessage") or "").strip()
            warning = (root.findtext("warning") or "").strip()

            if not valid and error_msg:
                raise ValueError(f"iiko API: {error_msg}")

            return {
                "valid": valid,
                "warning": warning,
                "errorMessage": error_msg,
                "documentNumber": doc_number,
            }
