import fdb
from fastapi import HTTPException
import time
from config import DB_CONFIG, MAX_POOL_SIZE, CONNECTION_TIMEOUT
import os

# Глобальные настройки для улучшения производительности
_connection_pool = []
_max_pool_size = 5

def get_db_connection():
    """
    Получить соединение с базой данных с улучшенными настройками производительности
    """
    try:
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
        sql = """
        select
            g.marking as g_marking,
            whm.goodsid,
            whm.width,
            whm.height,
            whm.qty - whm.reserveqty as qty
        from warehouseremainder whm
        join goods g on g.goodsid = whm.goodsid
        where whm.goodsid = ?
        """
        cur.execute(sql, (goodsid,))
        result = [
            {
                "g_marking": row[0],
                "goodsid": row[1],
                "width": row[2],
                "height": row[3],
                "qty": row[4]
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
                "wh_measureid": row[8]
            }
            for row in cur.fetchall()
        ]
        con.close()
        return {"main_material": result}
    except Exception as e:
        print("DB ERROR (warehouse-main-material):", e)
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

def upload_optimization_to_db(grorderid: int, sheets_data: list):
    """
    Загрузка данных оптимизации в таблицу OPTDATA
    
    Args:
        grorderid: ID сменного задания
        sheets_data: Список данных о листах
    
    Returns:
        dict: Результат операции
    """
    con = None
    try:
        print(f"🔄 DB: Начало загрузки оптимизации в базу для grorderid={grorderid}")
        
        con = get_db_connection()
        cur = con.cursor()
        
        # Начинаем транзакцию
        con.begin()
        
        # 1. Удаляем существующие данные для этого grorderid
        delete_sql = "DELETE FROM OPTDATA WHERE GRORDERID = ?"
        print(f"🗑️ DB: Удаление существующих записей для grorderid={grorderid}")
        cur.execute(delete_sql, (grorderid,))
        deleted_count = cur.rowcount if hasattr(cur, 'rowcount') else 0
        print(f"🗑️ DB: Удалено {deleted_count} записей")
        
        # 2. Вставляем новые данные
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
        
        for sheet in sheets_data:
            params = (
                grorderid,
                sheet['goodsid'], sheet['num_glass'], sheet['width'], sheet['height'],
                sheet['trash_area'], sheet['percent_full'], sheet['percent_waste'],
                sheet['piece_count'], sheet['sum_area'],
                sheet['xml_data'],
                sheet['qty'], sheet['is_remainder']
            )
            cur.execute(insert_sql, params)
            inserted_count += 1
            print(f"🔄 DB: Вставлено {inserted_count} листов")
        con.commit()
        print(f"✅ DB: Транзакция успешно закоммичена. Вставлено {inserted_count} листов.")
        
        return {"success": True, "inserted_count": inserted_count}

    except Exception as e:
        print(f"❌ DB: Ошибка во время транзакции: {e}. Откат изменений.")
        if con:
            con.rollback()
        raise  # Передаем исключение выше для обработки в API

    finally:
        if con:
            con.close()
            print("🔒 DB: Соединение с базой данных закрыто.")
