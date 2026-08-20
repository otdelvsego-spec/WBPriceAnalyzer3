from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from wb_app.excel_reader import parse_report, preview_sheet


HEADERS = [
    "Предмет", "Код номенклатуры", "Артикул поставщика", "Название", "Тип документа",
    "Обоснование для оплаты", "Дата заказа покупателем", "Дата продажи", "Кол-во",
    "Цена розничная", "Вайлдберриз реализовал Товар (Пр)",
    "Возмещение за выдачу и возврат товаров на ПВЗ",
    "Компенсация платёжных услуг/Комиссия за интеграцию платёжных сервисов",
    "Вознаграждение Вайлдберриз (ВВ), без НДС", "НДС с Вознаграждения Вайлдберриз",
    "К перечислению Продавцу за реализованный Товар", "Услуги по доставке товара покупателю",
    "Общая сумма штрафов", "Корректировка Вознаграждения Вайлдберриз (ВВ)",
    "Виды логистики, штрафов и корректировок ВВ", "Страна", "Srid",
    "Возмещение издержек по перевозке/по складским операциям с товаром", "Хранение",
    "Удержания", "Операции на приемке", "Компенсация скидки по программе лояльности",
    "Стоимость участия в программе лояльности", "Сумма баллов, удержанных по программе лояльности",
    "Разовое изменение срока перечисления денежных средств", "Коэффициент логистики",
]


class WBParserTests(unittest.TestCase):
    def test_detects_week_variant_and_out_of_week_correction(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "Еженедельный детализированный отчет №123.xlsx"
            workbook = Workbook()
            ws = workbook.active
            ws.append(HEADERS + ["Новый денежный столбец"])
            base = ["Горшок", 100, "A", "Товар A", "Продажа", "Продажа", "03.08.2026", "03.08.2026", 1, 1000, 800, 0, 20, 100, 20, 680, 0, 0, 0, "", "Казахстан", "s1", 0, 0, 0, 0, 0, 0, 0, 0, 1.5, 5]
            ws.append(base)
            ws.append(base[:7] + ["04.08.2026"] + base[8:])
            ws.append(base[:7] + ["02.08.2026"] + base[8:])
            workbook.save(path)
            workbook.close()

            parsed = parse_report(path)
            self.assertEqual(parsed.report_number, "123")
            self.assertEqual(parsed.report_variant, "по выкупам")
            self.assertEqual(parsed.period_start.isoformat(), "2026-08-03")
            self.assertEqual(parsed.period_end.isoformat(), "2026-08-09")
            self.assertEqual(parsed.out_of_period_rows, 1)
            self.assertEqual(parsed.unknown_columns, ["Новый денежный столбец"])
            self.assertEqual(parsed.row_count, 3)
            self.assertEqual(parsed.accrual_rows[0].logistics_coefficient, 1.5)
            headers, rows = preview_sheet(path, parsed.sheet_name)
            self.assertEqual(headers[1], "A")
            self.assertEqual(rows[1][2], "100")


if __name__ == "__main__":
    unittest.main()
