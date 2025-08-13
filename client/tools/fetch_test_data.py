"""
Скрипт для загрузки тестовых данных сменного задания и сохранения в файл.

Использует те же API, что и клиент, чтобы выгрузить:
- детали (details-raw)
- склад остатков по всем goodsid из деталей
- склад основных материалов по всем goodsid из деталей

Пример запуска (PowerShell):
  # Активируйте venv перед запуском!
  # .\\venv\\Scripts\\Activate.ps1
  # python .\\client\\tools\\fetch_test_data.py --grorderid 31442 --out .\\client\\test_data\\test_data_31442.json
"""

import os
import sys
import json
from datetime import datetime

# Обеспечиваем импорт модулей клиента
CLIENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if CLIENT_DIR not in sys.path:
    sys.path.insert(0, CLIENT_DIR)

from core.api_client import (  # type: ignore
    get_details_raw,
    get_warehouse_main_material,
    get_warehouse_remainders,
)


def fetch_all_for_grorder(grorderid: int) -> dict:
    """Загружает все данные для grorderid и возвращает объединённую структуру."""
    details_data = get_details_raw(grorderid) or {}

    # Нормализуем ключ для деталей
    if "items" in details_data and "details" not in details_data:
        details_data["details"] = details_data["items"]

    details_list = details_data.get("details", []) or []

    # Собираем уникальные goodsid
    unique_goodsids = set()
    for detail in details_list:
        goodsid = detail.get("goodsid")
        if goodsid:
            unique_goodsids.add(goodsid)

    all_remainders = []
    all_materials = []

    for goodsid in unique_goodsids:
        try:
            rem_resp = get_warehouse_remainders(goodsid) or {}
            if "remainders" in rem_resp:
                all_remainders.extend(rem_resp["remainders"])

            mat_resp = get_warehouse_main_material(goodsid) or {}
            if "main_material" in mat_resp:
                all_materials.extend(mat_resp["main_material"])
        except Exception as e:
            print(f"⚠️ Ошибка загрузки данных склада для goodsid={goodsid}: {e}")
            continue

    return {
        "grorderid": grorderid,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "details_data": details_data,
        "remainders": all_remainders,
        "materials": all_materials,
    }


def main(argv: list[str]) -> int:
    import argparse

    default_out_dir = os.path.join(CLIENT_DIR, "test_data")
    parser = argparse.ArgumentParser(description="Выгрузка тестовых данных сменного задания в JSON")
    parser.add_argument("--grorderid", type=int, default=31442, help="ID сменного задания")
    parser.add_argument("--out", type=str, default=os.path.join(default_out_dir, "test_data_31442.json"), help="Путь к выходному JSON")

    args = parser.parse_args(argv)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)

    print(f"Loading data for grorderid={args.grorderid}...")
    data = fetch_all_for_grorder(args.grorderid)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Saved: {args.out}")
    print(
        "Counts -> Details: {d}; Remainders: {r}; Materials: {m}".format(
            d=len(data.get('details_data', {}).get('details', [])),
            r=len(data.get('remainders', [])),
            m=len(data.get('materials', [])),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


