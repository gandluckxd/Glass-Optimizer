import fdb
from fastapi import HTTPException
import time
from config import DB_CONFIG, MAX_POOL_SIZE, CONNECTION_TIMEOUT, DB_OPERATION_TIMEOUT, LOG_DB_OPERATIONS
import os

# Глобальные настройки для улучшения производительности
_connection_pool = []
_max_pool_size = 5

def get_db_connection():
    """
    Получить соединение с базой данных с улучшенными настройками производительности
    """
    try:
        if LOG_DB_OPERATIONS:
            print(f"🔌 DB: Установка соединения с базой данных...")
        
        con = fdb.connect(
            port=DB_CONFIG['port'],
            host=DB_CONFIG['host'],
            database=DB_CONFIG['database'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            charset='WIN1251'
        )
        
        # Устанавливаем таймаут для транзакций
        con.default_tpb = fdb.TPB()
        con.default_tpb.isolation_level = fdb.isc_tpb_read_committed
        con.default_tpb.lock_resolution = fdb.isc_tpb_wait
        
        if LOG_DB_OPERATIONS:
            print(f"✅ DB: Соединение с базой данных установлено успешно")
        
        return con
    except Exception as e:
        print("DB ERROR:", e)
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")

def get_tables():
    try:
        con = get_db_connection()
        cur = con.cursor()
        cur.execute("SELECT RDB$RELATION_NAME FROM RDB$RELATIONS WHERE RDB$SYSTEM_FLAG=0;")
        tables = [row[0].strip() for row in cur.fetchall()]
        con.close()
        return {"tables": tables}
    except Exception as e:
        print("DB ERROR (tables):", e)
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

def get_details_raw(grorderid: int):
    """
    Получить детали для оптимизации с улучшенной производительностью
    """
    try:
        print(f"🔄 DB: Начало запроса для grorderid={grorderid}")
        con = get_db_connection()
        cur = con.cursor()
        
        # Сначала пробуем упрощенный запрос для проверки данных
        simple_sql = """
        select count(*) as cnt
        from grorders gr
        join grordersdetail grd on grd.grorderid = gr.grorderid
        where gr.grorderid = ?
        """
        
        print(f"🔍 DB: Проверка существования данных...")
        start_time = time.time()
        cur.execute(simple_sql, (grorderid,))
        count_result = cur.fetchone()
        check_time = time.time() - start_time
        
        if not count_result or count_result[0] == 0:
            print(f"⚠️ DB: Данные для grorderid={grorderid} не найдены")
            con.close()
            return {"grorder_info": {}, "items": []}
        
        print(f"✅ DB: Найдено {count_result[0]} записей, проверка заняла {check_time:.2f}с")
        
        # Основной оптимизированный запрос
        sql = """
        select
            gr.ordernames as gr_ordernames,
            gr.groupdate as groupdate,
            gr.name as gr_name,
            oi.orderitemsid,
            oi.name as oi_name,
            o.orderno,
            gp.marking as gp_marking,
            g.marking as g_marking,
            g.goodsid,
            grd.qty * itd.qty as total_qty,
            itd.width,
            itd.height
        from grorders gr
        join grordersdetail grd on grd.grorderid = gr.grorderid
        join orderitems oi on oi.orderitemsid = grd.orderitemsid
        join orders o on o.orderid = oi.orderid
        join itemsdetail itd on itd.orderitemsid = oi.orderitemsid
        join goods g on g.goodsid = itd.goodsid
        join groupgoods gg on gg.grgoodsid = itd.grgoodsid
        join groupgoodstypes ggt on ggt.ggtypeid = gg.ggtypeid
        join orderitemsgl oig on oig.orderitemsid = oi.orderitemsid
        join gpackettypes gp on gp.gptypeid = oig.gptypeid
        where gr.grorderid = ?
        and ggt.code = 'Glass'
        order by oi.orderitemsid
        """
        
        print(f"🔄 DB: Выполнение основного запроса...")
        start_time = time.time()
        
        cur.execute(sql, (grorderid,))
        rows = cur.fetchall()
        
        execution_time = time.time() - start_time
        print(f"✅ DB: Основной запрос выполнен за {execution_time:.2f}с, получено {len(rows)} записей")
        
        # Обработка результатов
        grorder_info = {}
        items = []
        
        if rows:
            first_row = rows[0]
            grorder_info = {
                "gr_ordernames": first_row[0],
                "groupdate": first_row[1],
                "gr_name": first_row[2]
            }
            
            for row in rows:
                items.append({
                    "orderitemsid": row[3],
                    "oi_name": row[4],
                    "orderno": row[5],        # ИСПРАВЛЕНО: orderno
                    "gp_marking": row[6],     # ИСПРАВЛЕНО: gp_marking 
                    "g_marking": row[7],      # ИСПРАВЛЕНО: g_marking
                    "goodsid": row[8],        # ИСПРАВЛЕНО: goodsid
                    "total_qty": row[9],      # ИСПРАВЛЕНО: total_qty
                    "width": row[10],         # ИСПРАВЛЕНО: width
                    "height": row[11]         # ИСПРАВЛЕНО: height
                })
        
        con.close()
        total_time = time.time() - start_time + check_time
        print(f"🎉 DB: Запрос завершен успешно за {total_time:.2f}с, возвращено {len(items)} элементов")
        
        return {
            "grorder_info": grorder_info,
            "items": items,
            "performance": {
                "total_time": round(total_time, 2),
                "records_count": len(items)
            }
        }
        
    except fdb.DatabaseError as e:
        print(f"❌ DB ERROR (database): {e}")
        if 'con' in locals():
            con.close()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        print(f"❌ DB ERROR (general): {e}")
        if 'con' in locals():
            con.close()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


def get_warehouse_remainders(goodsid: int):
    try:
        con = get_db_connection()
        cur = con.cursor()
        
        # Получаем стоимость товара
        price = get_goods_price(goodsid)
        
        sql = """
        select
            g.marking as g_marking,
            whm.goodsid,
            whm.width,
            whm.height,
            whm.qty - whm.reserveqty as qty,
            m.amfactor
        from warehouseremainder whm
        join goods g on g.goodsid = whm.goodsid
        join groupgoods gg on gg.grgoodsid = g.grgoodsid
        join measure m on m.measureid = gg.measureid
        where whm.goodsid = ?
        """
        cur.execute(sql, (goodsid,))
        result = [
            {
                "g_marking": row[0],
                "goodsid": row[1],
                "width": row[2],
                "height": row[3],
                "qty": row[4],
                "amfactor": row[5],
                "cost": price  # Добавляем стоимость
            }
            for row in cur.fetchall()
        ]
        con.close()
        return {"remainders": result}
    except Exception as e:
        print("DB ERROR (warehouse-remainders):", e)
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

def get_warehouse_main_material(goodsid: int):
    try:
        con = get_db_connection()
        cur = con.cursor()
        
        # Получаем стоимость товара
        price = get_goods_price(goodsid)
        
        sql = """
        select t.*, wh.qty, wh.qty / t.amfactor as res_qty, wh.measureid as wh_measureid
        from(
            select
                g.marking as g_marking,
                g.goodsid,
                ggm.measureid,
                gg.width,
                gg.height,
                m.amfactor
            from goods g
            join groupgoods gg on gg.grgoodsid = g.grgoodsid
            join grgoodsmeasure ggm on ggm.grgoodsid = gg.grgoodsid
            join measure m on m.measureid = ggm.measureid
            where g.goodsid = ?
            and ggm.ismain = 1
        ) t
        left join warehouse wh on (wh.goodsid = t.goodsid) and (wh.measureid = t.measureid)
        """
        cur.execute(sql, (goodsid,))
        result = [
            {
                "g_marking": row[0],
                "goodsid": row[1],
                "measureid": row[2],
                "width": row[3],
                "height": row[4],
                "amfactor": row[5],
                "qty": row[6],
                "res_qty": row[7],
                "wh_measureid": row[8],
                "cost": price  # Добавляем стоимость
            }
            for row in cur.fetchall()
        ]
        con.close()
        return {"main_material": result}
    except Exception as e:
        print("DB ERROR (warehouse-main-material):", e)
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")



def upload_optimization_to_db(grorderid: int, sheets_data: list, adjust_materials: bool = False):
    """
    Загрузка данных оптимизации в таблицу OPTDATA
    
    Args:
        grorderid: ID сменного задания
        sheets_data: Список данных о листах
        adjust_materials: Флаг корректировки списания материалов
    
    Returns:
        dict: Результат операции
    """
    con = None
    operation_start_time = time.time()
    
    try:
        print(f"🔄 DB: Начало загрузки оптимизации в базу для grorderid={grorderid}")
        print(f"📊 DB: Количество листов для обработки: {len(sheets_data)}")
        print(f"🔧 DB: Корректировка материалов: {adjust_materials}")
        
        # Детальная информация о листах
        if LOG_DB_OPERATIONS:
            print(f"📋 DB: Детализация входящих листов:")
            for i, sheet in enumerate(sheets_data):
                print(f"   Лист {i+1}: goodsid={sheet.get('goodsid')}, размеры={sheet.get('width')}x{sheet.get('height')}, "
                      f"qty={sheet.get('qty', 1)}, amfactor={sheet.get('amfactor', 1.0)}, is_remainder={sheet.get('is_remainder', 0)}")
                if sheet.get('free_rectangles'):
                    print(f"     Получено деловых остатков: {len(sheet.get('free_rectangles', []))}")
        
        db_connect_start = time.time()
        con = get_db_connection()
        db_connect_time = time.time() - db_connect_start
        print(f"⏱️ DB: Соединение с БД установлено за {db_connect_time:.2f} секунд")
        
        cur = con.cursor()
        
        # Начинаем транзакцию
        transaction_start = time.time()
        con.begin()
        print(f"🔄 DB: Транзакция начата")
        
        # 1. Удаляем существующие данные для этого grorderid
        delete_start = time.time()
        delete_sql = "DELETE FROM OPTDATA WHERE GRORDERID = ?"
        print(f"🗑️ DB: Удаление существующих записей для grorderid={grorderid}")
        cur.execute(delete_sql, (grorderid,))
        deleted_count = cur.rowcount if hasattr(cur, 'rowcount') else 0
        delete_time = time.time() - delete_start
        print(f"🗑️ DB: Удалено {deleted_count} записей за {delete_time:.2f} секунд")
        
        # 2. Вставляем новые данные
        insert_start = time.time()
        insert_sql = """
        INSERT INTO OPTDATA (
            OPTDATAID, GRORDERID, GOODSID, NUMGLASS, WGLASS, HGLASS, 
            TRASHSQU, PERCENTFULL, PERCENTOST, PIECECOUNT, SUMSQUPIECES, 
            DATAPIECE, DATAEMPTY, QTY, ISREMD
        ) VALUES (
            gen_id(gen_optdata, 1), ?, ?, ?, ?, ?, 
            ?, ?, ?, ?, ?, 
            ?, NULL, ?, ?
        )
        """
        
        inserted_count = 0
        insert_errors = 0
        
        print(f"🔧 DB: Начало вставки {len(sheets_data)} листов...")
        
        for i, sheet in enumerate(sheets_data):
            sheet_start = time.time()
            
            # Получаем goodsid и qty из данных листа
            goodsid = sheet.get('goodsid')
            if not goodsid:
                print(f"⚠️ DB: Лист {i+1}: пропускаем - нет goodsid")
                insert_errors += 1
                continue
                
            # qty для OPTDATA - количество листов (без amfactor)
            qty = sheet.get('qty', 1)
            # amfactor из данных листа
            amfactor = sheet.get('amfactor', 1.0)
            is_remainder = sheet.get('is_remainder', 0)
            
            print(f"🔧 DB: Обработка листа {i+1}/{len(sheets_data)}: goodsid={goodsid}, qty={qty} (листов), amfactor={amfactor}, is_remainder={is_remainder}")
            
            try:
                params = (
                    grorderid,
                    sheet['goodsid'], sheet['num_glass'], sheet['width'], sheet['height'],
                    sheet['trash_area'], sheet['percent_full'], sheet['percent_waste'],
                    sheet['piece_count'], sheet['sum_area'],
                    sheet['xml_data'],
                    qty, sheet['is_remainder']  # Используем qty (количество листов) для OPTDATA
                )
                cur.execute(insert_sql, params)
                
                # Проверяем результат вставки
                if hasattr(cur, 'rowcount'):
                    rows_affected = cur.rowcount
                    print(f"🔧 DB: INSERT в OPTDATA выполнен успешно! Затронуто строк: {rows_affected}")
                else:
                    print(f"🔧 DB: INSERT в OPTDATA выполнен, но rowcount недоступен")
                
                inserted_count += 1
                sheet_time = time.time() - sheet_start
                print(f"✅ DB: УСПЕШНО вставлен лист {inserted_count}: goodsid={goodsid}, is_remainder={is_remainder}, qty={qty} (листов) за {sheet_time:.2f}с")
                
            except Exception as e:
                insert_errors += 1
                sheet_time = time.time() - sheet_start
                print(f"❌ DB: ОШИБКА при вставке листа {i+1} в OPTDATA за {sheet_time:.2f}с: {e}")
                print(f"❌ DB: Параметры листа: goodsid={goodsid}, is_remainder={is_remainder}, qty={qty}")
                # Продолжаем обработку других листов
                continue
        
        insert_time = time.time() - insert_start
        print(f"📊 DB: Вставка завершена: {inserted_count} успешно, {insert_errors} ошибок за {insert_time:.2f} секунд")
        
        # Если включена корректировка материалов, выполняем дополнительную логику
        materials_adjusted = False
        materials_time = 0
        
        # Подсчитываем листы с остатками
        remainder_sheets = [s for s in sheets_data if s.get('is_remainder', 0)]
        print(f"🔧 DB: Найдено листов с деловыми остатками: {len(remainder_sheets)}")
        
        if remainder_sheets and LOG_DB_OPERATIONS:
            print(f"🔧 DB: Детализация листов с остатками:")
            for i, sheet in enumerate(remainder_sheets):
                print(f"   - Лист {i+1}: goodsid={sheet.get('goodsid')}, размеры={sheet.get('width')}x{sheet.get('height')}, qty={sheet.get('qty')}")
        
        if adjust_materials:
            print(f"🔧 DB: Выполняется корректировка списания материалов для grorderid={grorderid}")
            print(f"🔧 DB: Количество листов для корректировки: {len(sheets_data)}")
            
            materials_start = time.time()
            try:
                materials_result = adjust_materials_for_optimization(con, grorderid, sheets_data)
                materials_adjusted = materials_result.get('success', False)
                materials_time = time.time() - materials_start
                print(f"🔧 DB: Корректировка материалов: {'УСПЕШНО' if materials_adjusted else 'ОШИБКА'} за {materials_time:.2f}с")
                if materials_adjusted:
                    print(f"🔧 DB: Результат корректировки: {materials_result}")
            except Exception as e:
                materials_time = time.time() - materials_start
                print(f"❌ DB: Ошибка корректировки материалов за {materials_time:.2f}с: {e}")
                import traceback
                print(f"❌ DB: Трассировка ошибки: {traceback.format_exc()}")
                # Не откатываем основную транзакцию, только логируем ошибку
        else:
            print(f"🔧 DB: Корректировка материалов отключена")
            if remainder_sheets:
                print(f"⚠️ DB: ВНИМАНИЕ! Найдено {len(remainder_sheets)} листов с остатками, но корректировка отключена")
        
        # Коммитим транзакцию
        commit_start = time.time()
        con.commit()
        commit_time = time.time() - commit_start
        print(f"✅ DB: Транзакция успешно закоммичена за {commit_time:.2f}с. Вставлено {inserted_count} листов.")
        
        total_time = time.time() - operation_start_time
        print(f"🎉 DB: Операция загрузки оптимизации завершена за {total_time:.2f} секунд")
        print(f"📊 DB: Итоги операции:")
        print(f"   - Соединение с БД: {db_connect_time:.2f}с")
        print(f"   - Удаление старых записей: {delete_time:.2f}с")
        print(f"   - Вставка новых записей: {insert_time:.2f}с")
        if adjust_materials:
            print(f"   - Корректировка материалов: {materials_time:.2f}с")
        print(f"   - Коммит транзакции: {commit_time:.2f}с")
        print(f"   - Успешно вставлено: {inserted_count}")
        print(f"   - Ошибок вставки: {insert_errors}")
        
        return {
            "success": True, 
            "inserted_count": inserted_count,
            "insert_errors": insert_errors,
            "materials_adjusted": materials_adjusted,
            "performance": {
                "total_time": round(total_time, 2),
                "db_connect_time": round(db_connect_time, 2),
                "delete_time": round(delete_time, 2),
                "insert_time": round(insert_time, 2),
                "materials_time": round(materials_time, 2),
                "commit_time": round(commit_time, 2)
            }
        }

    except Exception as e:
        total_time = time.time() - operation_start_time
        print(f"❌ DB: Ошибка во время транзакции за {total_time:.2f}с: {e}")
        if con:
            try:
                con.rollback()
                print(f"🔄 DB: Транзакция откачена")
            except Exception as rollback_error:
                print(f"❌ DB: Ошибка при откате транзакции: {rollback_error}")
        raise  # Передаем исключение выше для обработки в API

    finally:
        if con:
            try:
                con.close()
                print("🔒 DB: Соединение с базой данных закрыто.")
            except Exception as close_error:
                print(f"❌ DB: Ошибка при закрытии соединения: {close_error}")

def adjust_materials_for_optimization(con, grorderid: int, sheets_data: list):
    """
    Корректировка списания материалов и приход деловых остатков
    
    Args:
        con: Соединение с базой данных
        grorderid: ID сменного задания
        sheets_data: Список данных о листах оптимизации
    
    Returns:
        dict: Результат операции
    """
    operation_start_time = time.time()
    
    try:
        print(f"🔧 DB: Начало корректировки материалов для grorderid={grorderid}")
        print(f"🔧 DB: Получено {len(sheets_data)} листов для обработки")
        
        # Проверяем, что соединение активно
        if not con or con.closed:
            print("❌ DB: Соединение с базой данных неактивно, создаем новое")
            con = get_db_connection()
        
        # Логируем информацию о листах
        remainder_count = 0
        material_count = 0
        if LOG_DB_OPERATIONS:
            print(f"📋 DB: Детализация листов для корректировки:")
            for i, sheet in enumerate(sheets_data):
                is_remainder = sheet.get('is_remainder', 0)
                goodsid = sheet.get('goodsid')
                if is_remainder:
                    remainder_count += 1
                else:
                    material_count += 1
                print(f"   Лист {i+1}: goodsid={goodsid}, is_remainder={is_remainder}, "
                      f"qty={sheet.get('qty', 1)}, amfactor={sheet.get('amfactor', 1.0)}")
        
        print(f"🔧 DB: Итого листов: {material_count} основных материалов, {remainder_count} деловых остатков")
        
        cur = con.cursor()
        
        # Получаем информацию о сменном задании для комментариев
        grorder_sql = "SELECT name FROM grorders WHERE grorderid = ?"
        cur.execute(grorder_sql, (grorderid,))
        grorder_result = cur.fetchone()
        grorder_name = grorder_result[0] if grorder_result else f"Задание {grorderid}"
        
        # 1. Работа со списаниями материалов (OUTLAY)
        print(f"🔧 DB: Обработка списаний материалов...")
        
        # Ищем существующее списание
        outlay_sql = """
        SELECT outlayid FROM outlay 
        WHERE grorderid = ? AND deleted = 0
        ORDER BY outlayid
        """
        cur.execute(outlay_sql, (grorderid,))
        outlay_result = cur.fetchone()
        
        if outlay_result:
            outlayid = outlay_result[0]
            print(f"🔧 DB: Найдено существующее списание outlayid={outlayid}")
        else:
            # Создаем новое списание
            print(f"🔧 DB: Создание нового списания материалов...")
            
            # Получаем новый GUID
            guid_sql = "SELECT guidhi, guidlo, guid FROM new_guid"
            cur.execute(guid_sql)
            guid_result = cur.fetchone()
            guidhi, guidlo, guid = guid_result
            
            # Генерируем номер накладной
            waybill_sql = "SELECT gen_id(gen_waybill, 1) FROM rdb$database"
            cur.execute(waybill_sql)
            waybill = cur.fetchone()[0]
            
            # Создаем списание
            create_outlay_sql = """
            INSERT INTO OUTLAY (
                OUTLAYID, WAYBILL, OUTLAYDATE, CUSTOMERID, OUTLAYTYPE, 
                GRORDERID, PARENTID, ISAPPROVED, RCOMMENT, WHLISTID, 
                RECCOLOR, RECFLAG, GUIDHI, GUIDLO, OWNERID, 
                DELETED, DATECREATED, DATEMODIFIED, DATEDELETED, JOBTASKID, GUID
            ) VALUES (
                gen_id(gen_outlay, 1), ?, CURRENT_DATE, NULL, 1, 
                ?, NULL, 0, ?, 0, 
                NULL, NULL, ?, ?, 0, 
                0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL, NULL, ?
            )
            """
            cur.execute(create_outlay_sql, (waybill, grorderid, grorder_name, guidhi, guidlo, guid))
            
            # Получаем ID созданного списания
            outlayid_sql = "SELECT gen_id(gen_outlay, 0) FROM rdb$database"
            cur.execute(outlayid_sql)
            outlayid = cur.fetchone()[0]
            print(f"🔧 DB: Создано новое списание outlayid={outlayid}")
        
        # Удаляем существующие элементы списания
        print(f"🔧 DB: Удаление существующих элементов списания...")
        delete_outlay_detail_sql = """
        DELETE FROM outlaydetail WHERE outlaydetailid IN (
            SELECT ot.outlaydetailid
            FROM outlaydetail ot
            JOIN goods g ON g.goodsid = ot.goodsid
            JOIN groupgoods gg ON gg.grgoodsid = g.grgoodsid
            WHERE ot.outlayid = ? AND gg.ggtypeid = 38
        )
        """
        cur.execute(delete_outlay_detail_sql, (outlayid,))
        deleted_details = cur.rowcount
        print(f"🔧 DB: Удалено {deleted_details} элементов списания")
        
        # Удаляем существующие остатки из списания
        delete_outlay_remainder_sql = """
        DELETE FROM outlayremainder WHERE outlayremainderid IN (
            SELECT otr.outlayremainderid
            FROM outlayremainder otr
            JOIN goods g ON g.goodsid = otr.goodsid
            JOIN groupgoods gg ON gg.grgoodsid = g.grgoodsid
            WHERE otr.outlayid = ? AND gg.ggtypeid = 38
        )
        """
        cur.execute(delete_outlay_remainder_sql, (outlayid,))
        deleted_remainders = cur.rowcount
        print(f"🔧 DB: Удалено {deleted_remainders} остатков из списания")
        
        # Добавляем новые элементы списания материалов
        print(f"🔧 DB: Добавление новых элементов списания...")
        print(f"🔧 DB: Всего листов для обработки: {len(sheets_data)}")
        materials_used = {}  # Словарь для подсчета использованных материалов
        remainders_used = []  # Список использованных деловых остатков
        
        for i, sheet in enumerate(sheets_data):
            goodsid = sheet.get('goodsid')
            if not goodsid:
                print(f"⚠️ DB: Лист {i+1}: пропускаем - нет goodsid")
                continue
                
            # qty для остатков - количество листов
            qty = sheet.get('qty', 1)
            # amfactor из данных листа
            amfactor = sheet.get('amfactor', 1.0)
            # Вычисляем qty_with_amfactor прямо здесь
            qty_with_amfactor = qty * amfactor
            is_remainder = sheet.get('is_remainder', 0)
            
            print(f"🔧 DB: Лист {i+1}: goodsid={goodsid}, is_remainder={is_remainder}, qty={qty} (листов), amfactor={amfactor}, qty_with_amfactor={qty_with_amfactor} (вычислено)")
            
            if is_remainder:
                # Это деловой остаток - добавляем в список для outlayremainders
                remainders_used.append({
                    'goodsid': goodsid,
                    'width': sheet.get('width', 0),
                    'height': sheet.get('height', 0),
                    'qty': qty  # Используем qty (количество листов) для остатков
                })
                print(f"🔧 DB: Использован деловой остаток goodsid={goodsid}, {sheet.get('width', 0)}x{sheet.get('height', 0)}, qty={qty} (листов)")
            else:
                # Это основной материал - подсчитываем для outlaydetail
                if goodsid not in materials_used:
                    materials_used[goodsid] = 0
                materials_used[goodsid] += qty_with_amfactor  # Используем вычисленное qty_with_amfactor для материалов
                print(f"🔧 DB: Материал goodsid={goodsid}: qty_with_amfactor={qty_with_amfactor} (вычислено: {qty} * {amfactor})")
        
        print(f"🔧 DB: Итого материалов: {len(materials_used)}, остатков: {len(remainders_used)}")
        
        # Вставляем записи о списанных материалах
        for goodsid, qty_with_amfactor in materials_used.items():
            # Получаем measureid для товара
            measure_sql = """
            SELECT ggm.measureid FROM goods g
            JOIN groupgoods gg ON gg.grgoodsid = g.grgoodsid
            JOIN grgoodsmeasure ggm ON ggm.grgoodsid = gg.grgoodsid
            WHERE g.goodsid = ? AND ggm.ismain = 1
            """
            cur.execute(measure_sql, (goodsid,))
            measure_result = cur.fetchone()
            measureid = measure_result[0] if measure_result else 1  # По умолчанию 1
            
            # Вставляем запись о списанном материале (с учетом amfactor)
            insert_outlay_detail_sql = """
            INSERT INTO OUTLAYDETAIL (
                OUTLAYDETAILID, OUTLAYID, GOODSID, QTY, MEASUREID, 
                ISAPPROVED, SELLERPRICE, SELLERCURRENCYID
            ) VALUES (
                gen_id(gen_outlaydetail, 1), ?, ?, ?, ?, 
                0, 0, 1
            )
            """
            cur.execute(insert_outlay_detail_sql, (outlayid, goodsid, qty_with_amfactor, measureid))
            print(f"🔧 DB: Добавлено списание материала goodsid={goodsid}, qty={qty_with_amfactor} (вычислено: qty * amfactor)")
        
        # Группируем остатки по размеру и подсчитываем количество листов
        print(f"🔧 DB: Группировка остатков по размеру...")
        remainder_groups = {}
        
        for remainder in remainders_used:
            goodsid = remainder['goodsid']
            width = remainder['width']
            height = remainder['height']
            
            # Создаем ключ для группировки
            key = (goodsid, width, height)
            
            if key not in remainder_groups:
                remainder_groups[key] = {
                    'goodsid': goodsid,
                    'width': width,
                    'height': height,
                    'qty': 0  # Количество листов данного размера
                }
            
            remainder_groups[key]['qty'] += 1
        
        print(f"🔧 DB: Найдено {len(remainder_groups)} уникальных размеров остатков")
        
        # Вставляем записи о списанных деловых остатках
        print(f"🔧 DB: Добавление списаний деловых остатков...")
        remainders_outlay_added = 0
        
        for i, (key, remainder_data) in enumerate(remainder_groups.items()):
            goodsid = remainder_data['goodsid']
            width = remainder_data['width']
            height = remainder_data['height']
            qty = remainder_data['qty']  # Количество листов данного размера
            
            print(f"🔧 DB: Обрабатываем остаток {i+1}: goodsid={goodsid}, {width}x{height}, qty={qty} (количество листов)")
            
            try:
                # Вставляем запись о списанном деловом остатке
                insert_outlay_remainder_sql = """
                INSERT INTO OUTLAYREMAINDER (
                    OUTLAYREMAINDERID, OUTLAYID, GOODSID, ISAPPROVED, 
                    THICK, WIDTH, HEIGHT, QTY, SELLERPRICE, SELLERCURRENCYID
                ) VALUES (
                    gen_id(gen_outlayremainder, 1), ?, ?, 0, 
                    0, ?, ?, ?, 0, 1
                )
                """
                print(f"🔧 DB: Выполняем INSERT в OUTLAYREMAINDER с параметрами: outlayid={outlayid}, goodsid={goodsid}, width={width}, height={height}, qty={qty}")
                cur.execute(insert_outlay_remainder_sql, (outlayid, goodsid, width, height, qty))
                
                # Проверяем результат вставки
                if hasattr(cur, 'rowcount'):
                    rows_affected = cur.rowcount
                    print(f"🔧 DB: INSERT выполнен успешно! Затронуто строк: {rows_affected}")
                else:
                    print(f"🔧 DB: INSERT выполнен, но rowcount недоступен")
                
                remainders_outlay_added += 1
                print(f"✅ DB: УСПЕШНО добавлено списание делового остатка goodsid={goodsid}, {width}x{height}, qty={qty} (листов)")
                
            except Exception as e:
                print(f"❌ DB: ОШИБКА при вставке в OUTLAYREMAINDER: {e}")
                print(f"❌ DB: Параметры: outlayid={outlayid}, goodsid={goodsid}, width={width}, height={height}, qty={qty}")
                # Продолжаем обработку других остатков
                continue
        
        print(f"🔧 DB: Списано деловых остатков: {remainders_outlay_added}")
        
        # 2. Работа с приходами материалов (SUPPLY) - деловые остатки
        print(f"🔧 DB: Обработка приходов деловых остатков...")
        
        # Получаем имя сменного задания для комментария
        grorder_name_sql = "SELECT name FROM grorders WHERE grorderid = ?"
        cur.execute(grorder_name_sql, (grorderid,))
        grorder_name_result = cur.fetchone()
        grorder_name = grorder_name_result[0] if grorder_name_result else f"Оптимизация {grorderid}"
        
        # Ищем существующий приход
        supply_sql = """
        SELECT supplyid FROM supply 
        WHERE grorderid = ? AND supplytype = 1 AND deleted = 0
        ORDER BY supplyid
        """
        print(f"🔧 DB: Ищем существующий приход для grorderid={grorderid} с supplytype=1")
        cur.execute(supply_sql, (grorderid,))
        supply_result = cur.fetchone()
        
        # Проверим, есть ли вообще записи в таблице supply для данного grorderid
        check_all_supply_sql = """
        SELECT supplyid, waybill, supplytype, deleted FROM supply WHERE grorderid = ?
        """
        cur.execute(check_all_supply_sql, (grorderid,))
        all_supply_results = cur.fetchall()
        print(f"🔧 DB: Найдено {len(all_supply_results)} записей в supply для grorderid={grorderid}")
        for i, (supplyid, waybill, supplytype, deleted) in enumerate(all_supply_results):
            print(f"   - Запись {i+1}: supplyid={supplyid}, waybill='{waybill}', supplytype={supplytype}, deleted={deleted}")
        
        if supply_result:
            supplyid = supply_result[0]
            print(f"🔧 DB: Найден существующий приход supplyid={supplyid}")
        else:
            # Создаем новый приход
            print(f"🔧 DB: Создание нового прихода деловых остатков...")
            print(f"🔧 DB: Причина: не найден существующий приход с supplytype=1 и deleted=0 для grorderid={grorderid}")
            
            try:
                # Получаем новый GUID
                guid_sql = "SELECT guidhi, guidlo, guid FROM new_guid"
                cur.execute(guid_sql)
                guid_result = cur.fetchone()
                guidhi, guidlo, guid = guid_result
                
                # Используем наименование сменного задания как waybill
                waybill = grorder_name
                
                # Создаем приход
                create_supply_sql = """
                INSERT INTO SUPPLY (
                    SUPPLYID, WAYBILL, SUPPLYDATE, SUPPLIERID, SUPPLYTYPE, 
                    GRORDERID, PARENTID, ISAPPROVED, RCOMMENT, WHLISTID, 
                    RECCOLOR, RECFLAG, GUIDHI, GUIDLO, OWNERID, 
                    DELETED, DATECREATED, DATEMODIFIED, DATEDELETED, JOBTASKID, GUID
                ) VALUES (
                    gen_id(gen_supply, 1), ?, CURRENT_DATE, NULL, 1, 
                    ?, NULL, 0, ?, 0, 
                    NULL, NULL, ?, ?, 0, 
                    0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL, NULL, ?
                )
                """
                print(f"🔧 DB: Создаем приход с параметрами: waybill='{waybill}', grorderid={grorderid}, comment='{grorder_name}'")
                cur.execute(create_supply_sql, (waybill, grorderid, grorder_name, guidhi, guidlo, guid))
                
                # Получаем ID созданного прихода
                supplyid_sql = "SELECT gen_id(gen_supply, 0) FROM rdb$database"
                cur.execute(supplyid_sql)
                supplyid = cur.fetchone()[0]
                print(f"🔧 DB: Создан новый приход supplyid={supplyid}")
                
            except Exception as e:
                print(f"❌ DB: ОШИБКА при создании прихода: {e}")
                # Продолжаем работу без прихода
                supplyid = None
        
        # Удаляем существующие элементы прихода
        if supplyid:
            print(f"🔧 DB: Удаление существующих элементов прихода...")
            try:
                # Проверим, сколько записей есть в supplyremainder для данного supplyid
                check_supply_remainder_sql = """
                SELECT COUNT(*) FROM supplyremainder WHERE supplyid = ?
                """
                cur.execute(check_supply_remainder_sql, (supplyid,))
                supply_remainder_count = cur.fetchone()[0]
                print(f"🔧 DB: Найдено {supply_remainder_count} записей в supplyremainder для supplyid={supplyid}")
                
                # Проверим, сколько записей соответствуют фильтру ggtypeid = 38
                check_supply_remainder_filtered_sql = """
                SELECT COUNT(*) FROM supplyremainder suprem
                JOIN goods g ON g.goodsid = suprem.goodsid
                JOIN groupgoods gg ON gg.grgoodsid = g.grgoodsid
                WHERE suprem.supplyid = ? AND gg.ggtypeid = 38
                """
                cur.execute(check_supply_remainder_filtered_sql, (supplyid,))
                supply_remainder_filtered_count = cur.fetchone()[0]
                print(f"🔧 DB: Найдено {supply_remainder_filtered_count} записей в supplyremainder с ggtypeid = 38")
                
                # Удаляем записи из supplyremainder с фильтром по ggtypeid = 38
                delete_supply_remainder_sql = """
                DELETE FROM supplyremainder WHERE supplyremainderid IN (
                    SELECT suprem.supplyremainderid
                    FROM supplyremainder suprem
                    JOIN goods g ON g.goodsid = suprem.goodsid
                    JOIN groupgoods gg ON gg.grgoodsid = g.grgoodsid
                    WHERE suprem.supplyid = ? AND gg.ggtypeid = 38
                )
                """
                cur.execute(delete_supply_remainder_sql, (supplyid,))
                deleted_supply_remainders = cur.rowcount
                print(f"🔧 DB: Удалено {deleted_supply_remainders} остатков из supplyremainder")
                
            except Exception as e:
                print(f"❌ DB: ОШИБКА при удалении существующих записей прихода: {e}")
        else:
            print(f"⚠️ DB: Приход не существует, пропускаем удаление существующих записей")
        
        # Группируем полученные деловые остатки по размеру для прихода
        print(f"🔧 DB: Группировка полученных деловых остатков по размеру для прихода...")
        supply_remainder_groups = {}
        
        for sheet in sheets_data:
            goodsid = sheet.get('goodsid')
            if not goodsid:
                continue
                
            # Получаем данные о полученных деловых остатках (free_rectangles)
            free_rectangles = sheet.get('free_rectangles', [])
            
            print(f"🔧 DB: Лист goodsid={goodsid}: найдено {len(free_rectangles)} полученных деловых остатков")
            
            for rect_data in free_rectangles:
                width = rect_data.get('width', 0)
                height = rect_data.get('height', 0)
                
                if width <= 0 or height <= 0:
                    continue
                
                print(f"🔧 DB: Обрабатываем полученный деловой остаток: goodsid={goodsid}, {width}x{height}")
                
                # Создаем ключ для группировки
                key = (goodsid, width, height)
                
                if key not in supply_remainder_groups:
                    supply_remainder_groups[key] = {
                        'goodsid': goodsid,
                        'width': width,
                        'height': height,
                        'qty': 0  # Количество остатков данного размера
                    }
                
                supply_remainder_groups[key]['qty'] += 1
        
        print(f"🔧 DB: Найдено {len(supply_remainder_groups)} уникальных размеров полученных остатков для прихода")
        
        # Добавляем полученные деловые остатки в приход
        print(f"🔧 DB: Добавление полученных деловых остатков в приход...")
        remainders_added = 0
        
        # Проверяем, что приход был создан
        if not supplyid:
            print(f"⚠️ DB: Приход не был создан, пропускаем добавление остатков в приход")
        else:
            for i, (key, remainder_data) in enumerate(supply_remainder_groups.items()):
                goodsid = remainder_data['goodsid']
                width = remainder_data['width']
                height = remainder_data['height']
                qty = remainder_data['qty']  # Количество остатков данного размера
                
                try:
                    # Получаем стоимость товара
                    price = get_goods_price(goodsid)
                    print(f"🔧 DB: Стоимость товара: {price}")
                    
                    # Вставляем полученный деловой остаток в приход
                    insert_supply_remainder_sql = """
                    INSERT INTO SUPPLYREMAINDER (
                        SUPPLYREMAINDERID, SUPPLYID, GOODSID, ISAPPROVED, 
                        THICK, WIDTH, HEIGHT, QTY, SELLERPRICE, SELLERCURRENCYID
                    ) VALUES (
                        gen_id(gen_supplyremainder, 1), ?, ?, 0, 
                        0, ?, ?, ?, ?, 1
                    )
                    """
                    print(f"🔧 DB: Выполняем INSERT в SUPPLYREMAINDER с параметрами: supplyid={supplyid}, goodsid={goodsid}, width={width}, height={height}, qty={qty}, price={price} (количество остатков)")
                    cur.execute(insert_supply_remainder_sql, (supplyid, goodsid, width, height, qty, price))
                    
                    # Проверяем результат вставки
                    if hasattr(cur, 'rowcount'):
                        rows_affected = cur.rowcount
                        print(f"🔧 DB: INSERT в SUPPLYREMAINDER выполнен успешно! Затронуто строк: {rows_affected}")
                    else:
                        print(f"🔧 DB: INSERT в SUPPLYREMAINDER выполнен, но rowcount недоступен")
                    
                    remainders_added += 1
                    print(f"✅ DB: УСПЕШНО добавлен полученный деловой остаток в приход goodsid={goodsid}, {width}x{height}, qty={qty} (остатков)")
                    
                except Exception as e:
                    print(f"❌ DB: ОШИБКА при вставке в SUPPLYREMAINDER: {e}")
                    print(f"❌ DB: Параметры: supplyid={supplyid}, goodsid={goodsid}, width={width}, height={height}, qty={qty}")
                    # Продолжаем обработку других остатков
                    continue
        
        total_time = time.time() - operation_start_time
        print(f"✅ DB: Корректировка материалов завершена успешно за {total_time:.2f} секунд")
        print(f"📊 DB: Итоги корректировки:")
        print(f"   - Списано материалов: {len(materials_used)}")
        print(f"   - Списано использованных деловых остатков: {remainders_outlay_added}")
        print(f"   - Добавлено полученных деловых остатков в приход: {remainders_added}")
        print(f"   - Общее время операции: {total_time:.2f} секунд")
        
        # Дополнительная проверка
        if remainders_outlay_added == 0 and remainder_count > 0:
            print(f"⚠️ DB: ВНИМАНИЕ! Найдено {remainder_count} деловых остатков, но создано 0 записей в OUTLAYREMAINDER")
            print(f"⚠️ DB: Возможные причины:")
            print(f"   - Остатки не были использованы в оптимизации")
            print(f"   - Проблема с флагом is_remainder")
            print(f"   - Проблема с goodsid")
        elif remainders_outlay_added > 0:
            print(f"✅ DB: УСПЕШНО! Создано {remainders_outlay_added} записей в OUTLAYREMAINDER")
        
        # Проверка полученных остатков
        if remainders_added == 0:
            print(f"⚠️ DB: ВНИМАНИЕ! Не найдено полученных деловых остатков для прихода")
            print(f"⚠️ DB: Возможные причины:")
            print(f"   - Нет полезных остатков в результате оптимизации")
            print(f"   - Остатки меньше минимальных размеров")
            print(f"   - Проблема с передачей данных free_rectangles")
        elif remainders_added > 0:
            print(f"✅ DB: УСПЕШНО! Создано {remainders_added} записей в SUPPLYREMAINDER")
        
        return {
            "success": True,
            "outlayid": outlayid,
            "supplyid": supplyid,
            "materials_count": len(materials_used),
            "remainders_outlay_count": remainders_outlay_added,
            "remainders_supply_count": remainders_added,
            "performance": {
                "total_time": round(total_time, 2)
            }
        }
        
    except Exception as e:
        total_time = time.time() - operation_start_time
        print(f"❌ DB: Ошибка корректировки материалов за {total_time:.2f}с: {e}")
        import traceback
        print(f"❌ DB: Трассировка ошибки: {traceback.format_exc()}")
        return {
            "success": False,
            "error": str(e),
            "performance": {
                "total_time": round(total_time, 2)
            }
        }

def get_goods_price(goodsid: int):
    """
    Получить стоимость товара по goodsid
    """
    try:
        con = get_db_connection()
        cur = con.cursor()
        
        # Получаем цену из поля price1
        sql = """
        SELECT 
            COALESCE(g.price1, 0) as price
        FROM goods g 
        WHERE g.goodsid = ?
        """
        
        cur.execute(sql, (goodsid,))
        result = cur.fetchone()
        
        if result:
            price = result[0] or 0
            con.close()
            return price
        else:
            con.close()
            return 0
            
    except Exception as e:
        print(f"DB ERROR (goods-price): {e}")
        return 0
