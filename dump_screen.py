"""
เครื่องมือช่วย debug: dump control tree ของหน้าจอ Riposte ปัจจุบัน

วิธีใช้:
1. เปิดโปรแกรม Riposte ค้างไว้
2. เลื่อน/คลิกไปหน้าที่ต้องการดู (ด้วยมือ ปกติ) เช่น หน้าเลือกกล่อง,
   หน้ากรอกน้ำหนัก, หน้ากรอกที่อยู่ ฯลฯ
3. รันสคริปต์นี้ (python dump_screen.py หรือใส่ชื่อไฟล์ output เอง เช่น
   python dump_screen.py screen_box_select.txt)
4. จะได้ไฟล์ .txt ที่มี control tree ของหน้าจอ ณ ตอนนั้น -> ส่งไฟล์นั้นมาดูได้เลย

แนะนำ: ทำแบบนี้ทีละหน้า ไล่ตาม flow ทั้งหมด (เลือกกล่อง, ถัดไป, ยืนยัน,
น้ำหนัก, รหัสไปรษณีย์, เลือกบริการ EMS, ที่อยู่, ชื่อ-นามสกุล-เบอร์โทร)
แล้วส่งไฟล์ทั้งหมดมาในคราวเดียว จะได้แก้ auto_id ให้ครบทุกจุดในรอบเดียว
ไม่ต้องรอ fail ทีละจุด

หมายเหตุ: หน้าต่างของ Riposte มีนาฬิกา/ตัวเลขที่อัปเดตตลอดเวลา (มุมขวาบน)
ซึ่งบางครั้งทำให้การ dump ทั้งหน้าต่างพัง (COM event error) สคริปต์นี้เลย
ลอง retry อัตโนมัติ และถ้ายังไม่ผ่านจะ fallback ไป dump เฉพาะส่วนเนื้อหา
หลัก (ไม่รวม header ที่มีนาฬิกา) แทน
"""

import sys
import time
from pywinauto.application import Application


def try_dump(target, output_filename, label, attempts=3, delay=1.5):
    """พยายาม dump control identifiers หลายรอบ เผื่อ COM event ชนกันชั่วคราว"""
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            target.print_control_identifiers(filename=output_filename)
            print(f"[{label}] บันทึกลง '{output_filename}' สำเร็จ (ครั้งที่ {attempt})")
            return True
        except Exception as error:
            last_error = error
            print(f"[{label}] ลองครั้งที่ {attempt}/{attempts} ไม่สำเร็จ: {error}")
            time.sleep(delay)

    print(f"[{label}] dump ไม่สำเร็จหลังจากลอง {attempts} ครั้ง: {last_error}")
    return False


def main():
    output_filename = sys.argv[1] if len(sys.argv) > 1 else "screen_dump.txt"

    print("กำลังเชื่อมต่อโปรแกรม Riposte...")
    try:
        app = Application(backend="uia").connect(
            title_re=r".*Riposte.*", timeout=15
        )
        main_window = app.window(title_re=r".*Riposte.*")
        main_window.wait("exists visible", timeout=15)
        main_window.set_focus()
    except Exception as error:
        print(f"เชื่อมต่อไม่สำเร็จ: {error}")
        print("ตรวจสอบว่าเปิดโปรแกรม Riposte อยู่หรือไม่")
        return

    # ลอง dump ทั้งหน้าต่างก่อน
    if try_dump(main_window, output_filename, "ทั้งหน้าต่าง"):
        return

    # ถ้าไม่สำเร็จ (มักเพราะนาฬิกา/badge ใน header กำลังอัปเดต)
    # ให้ลอง dump เฉพาะส่วนเนื้อหาหลัก แทน
    # ซึ่งเป็นส่วนที่มีปุ่ม/ช่องกรอกทั้งหมดที่เราต้องการจริงๆ
    # หมายเหตุ: auto_id="Menu.MainMenu" ไม่มีอยู่จริง (ตรวจสอบจาก controls
    # dump แล้วว่า pane เนื้อหาหลักของทุกหน้าใช้ title="Main" คงที่ ส่วน
    # auto_id จะเปลี่ยนไปตามหน้า เช่น "EG.Shipping.MailPieceCategory")
    # เลยเปลี่ยนมาค้นด้วย title="Main" แทน
    print("กำลังลอง dump เฉพาะส่วนเนื้อหาหลัก (ไม่รวม header ที่มีนาฬิกา)...")
    try:
        main_pane = main_window.child_window(
            title="Main", control_type="Custom"
        )
        fallback_filename = f"main_only_{output_filename}"
        if try_dump(main_pane, fallback_filename, "เฉพาะ Main pane"):
            return
    except Exception as error:
        print(f"หา Main pane ไม่เจอ: {error}")

    print(
        "dump ไม่สำเร็จทั้งสองวิธี -- ลองปิดโปรแกรมอื่นที่แย่ง focus, "
        "หรือรอสักครู่แล้วลองใหม่อีกครั้ง"
    )


if __name__ == "__main__":
    main()