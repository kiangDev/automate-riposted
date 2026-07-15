"""
เครื่องมือช่วย debug (เสริมจาก dump_screen.py): dump ทุกหน้าต่างที่เปิดอยู่
บนเครื่องตอนนี้ ไม่ใช่แค่หน้าต่างหลักของ Riposte

ใช้ตอนไหน: dump_screen.py ปกติจะ dump แค่หน้าต่างหลัก (title มีคำว่า
"Riposte") แต่บาง popup เช่น รายการ dropdown ที่โผล่มาให้เลือกที่อยู่
มักถูกสร้างเป็นหน้าต่างแยกต่างหาก (ไม่ใช่ control ที่ซ้อนอยู่ในหน้าต่างหลัก)
ทำให้ dump_screen.py มองไม่เห็น ต้องใช้ตัวนี้แทนเพื่อไล่ดูทุกหน้าต่างที่เปิด
อยู่ ณ ขณะนั้น

วิธีใช้:
1. เปิดโปรแกรม Riposte แล้วเลื่อนไปจนถึงจุดที่ popup/dropdown โผล่ขึ้นมา
   บนจอพอดี (เช่น พิมพ์ค้นหาที่อยู่แล้วเห็นรายการ dropdown ค้างอยู่)
2. รันสคริปต์นี้ทันที (python dump_all_windows.py)
3. จะได้ไฟล์แยกทีละหน้าต่าง เช่น window_1_<ชื่อ>.txt, window_2_<ชื่อ>.txt
   ส่งไฟล์ทั้งหมดมาดูได้เลย (โดยเฉพาะไฟล์ที่ชื่อไม่คุ้น ไม่ใช่ "Riposte")
"""

import time
from pywinauto import Desktop
from pywinauto.application import Application


def safe_filename(text, fallback):
    cleaned = "".join(ch for ch in str(text) if ch.isalnum())[:40]
    return cleaned or fallback


def main():
    print("กำลังดึงรายชื่อหน้าต่างทั้งหมดที่เปิดอยู่...")
    try:
        windows = Desktop(backend="uia").windows()
    except Exception as error:
        print(f"ดึงรายชื่อหน้าต่างไม่สำเร็จ: {error}")
        return

    if not windows:
        print("ไม่พบหน้าต่างที่เปิดอยู่เลย")
        return

    print(f"พบหน้าต่างทั้งหมด {len(windows)} หน้าต่าง กำลัง dump ทีละหน้าต่าง...")

    for index, window in enumerate(windows, start=1):
        try:
            title = window.window_text() or "(ไม่มีชื่อ)"
        except Exception:
            title = "(อ่านชื่อไม่ได้)"

        print(f"[{index}] title={title!r}")

        filename = f"window_{index}_{safe_filename(title, 'untitled')}.txt"
        try:
            # แก้: Desktop().windows() คืน UIAWrapper ดิบๆ ซึ่งบางเวอร์ชัน
            # ของ pywinauto ไม่มีเมธอด print_control_identifiers ตรงๆ
            # ต้องต่อผ่าน Application().connect(handle=...) แล้วขอ
            # WindowSpecification ใหม่จาก handle เดียวกันก่อน ถึงจะ dump ได้
            app = Application(backend="uia").connect(handle=window.handle)
            win_spec = app.window(handle=window.handle)
            win_spec.print_control_identifiers(filename=filename)
            print(f"    -> บันทึกลง {filename} แล้ว")
        except Exception as error:
            print(f"    -> dump ไม่สำเร็จ: {error}")

        time.sleep(0.2)

    print("เสร็จแล้ว ส่งไฟล์ window_*.txt ทั้งหมดมาดูได้เลย "
          "(โดยเฉพาะตัวที่ไม่ใช่ Riposte POS Application)")


if __name__ == "__main__":
    main()
